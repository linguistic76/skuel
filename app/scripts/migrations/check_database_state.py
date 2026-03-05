"""
Check what's actually in the Neo4j database
============================================

Shows all node labels, relationship types, and sample data.
"""

import asyncio
from pathlib import Path

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection


async def check_database():
    """Check database state."""
    # Load .env file
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    # Get connection
    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    print("=" * 80)
    print("Database State Check")
    print("=" * 80)
    print(f"Connecting to: {conn.uri}")
    print()

    try:
        await driver.verify_connectivity()
        print("✅ Connected")
        print()

        # Get all node labels
        labels_result = await driver.execute_query(
            "CALL db.labels() YIELD label RETURN label ORDER BY label",
            routing_="r"
        )

        print("NODE LABELS:")
        if not labels_result.records:
            print("  (no labels found - database is empty)")
        else:
            for record in labels_result.records:
                label = record["label"]
                # Count nodes with this label
                count_result = await driver.execute_query(
                    f"MATCH (n:{label}) RETURN count(n) as count",
                    routing_="r"
                )
                count = count_result.records[0]["count"]
                print(f"  {label}: {count} nodes")

        print()

        # Get all relationship types
        rels_result = await driver.execute_query(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType",
            routing_="r"
        )

        print("RELATIONSHIP TYPES:")
        if not rels_result.records:
            print("  (no relationships found)")
        else:
            for record in rels_result.records:
                rel_type = record["relationshipType"]
                # Count relationships of this type
                count_result = await driver.execute_query(
                    f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count",
                    routing_="r"
                )
                count = count_result.records[0]["count"]
                print(f"  {rel_type}: {count} relationships")

        print()
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_database())
