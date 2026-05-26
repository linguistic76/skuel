#!/usr/bin/env python3
# mypy: disable-error-code="union-attr,call-arg,attr-defined"
"""
One-off script: Ingest Activity Domain YAML files for a specific user.

Usage:
    uv run scripts/ingest_user_activities.py
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

load_dotenv()


async def main() -> None:
    user_uid = "user_linguistic76"
    vault_dir = Path("data/user_vaults") / user_uid

    if not vault_dir.exists():
        print(f"Directory not found: {vault_dir}")
        return

    yaml_files = sorted(vault_dir.glob("*.yaml"))
    print(f"Found {len(yaml_files)} YAML files in {vault_dir}")

    from core.config.credential_store import get_credential

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = get_credential("NEO4J_PASSWORD", fallback_to_env=True) or ""

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    try:
        from core.services.ingestion import UnifiedIngestionService

        ingestion = UnifiedIngestionService(
            driver=driver,
            embeddings_service=None,
            chunking_service=None,
        )

        result = await ingestion.ingest_directory(
            vault_dir,
            pattern="*.yaml",
            user_uid=user_uid,
        )

        if result.is_error:
            print(f"Ingestion failed: {result.expect_error()}")
            return

        stats = result.value
        print("\nIngestion complete:")
        print(f"  Total files:  {stats.total_files}")
        print(f"  Successful:   {stats.successful}")
        print(f"  Failed:       {stats.failed}")
        print(f"  Nodes created: {stats.nodes_created}")
        print(f"  Nodes updated: {stats.nodes_updated}")
        print(f"  Relationships: {stats.relationships_created}")
        print(f"  Duration:     {stats.duration_seconds:.1f}s")
        if stats.errors:
            print("\nErrors:")
            for err in stats.errors:
                print(f"  - {err}")

        # Post-ingestion fixups: OWNS edges and cross-domain relationships
        print("\n--- Post-ingestion fixups ---")

        # 1. Create OWNS relationships from User to all their entities
        async with driver.session() as session:
            owns_result = await session.run(
                """
                MATCH (u:User {uid: $user_uid})
                MATCH (e:Entity {user_uid: $user_uid})
                WHERE NOT (u)-[:OWNS]->(e)
                MERGE (u)-[:OWNS]->(e)
                RETURN count(*) AS created
                """,
                user_uid=user_uid,
            )
            record = await owns_result.single()
            print(f"  OWNS edges created: {record['created']}")

        # 2. Re-run ingestion to pick up cross-domain relationships now that
        #    all target nodes exist
        result2 = await ingestion.ingest_directory(
            vault_dir,
            pattern="*.yaml",
            user_uid=user_uid,
        )
        if result2.is_ok:
            stats2 = result2.value
            print(
                f"  Re-ingestion (for relationships): {stats2.nodes_updated} updated, {stats2.relationships_created} rels"
            )

        # 3. Verify final state
        async with driver.session() as session:
            verify = await session.run(
                """
                MATCH (e:Entity {user_uid: $user_uid})-[r]->(t:Entity)
                RETURN type(r) AS rel, e.uid AS from_uid, t.uid AS to_uid
                ORDER BY rel
                """,
                user_uid=user_uid,
            )
            records = [r async for r in verify]
            print(f"\n  Cross-domain relationships: {len(records)}")
            for r in records:
                print(f"    ({r['from_uid']})-[:{r['rel']}]->({r['to_uid']})")

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
