"""
Migrate LS Knowledge from Properties to Relationships
=====================================================

Migrates Learning Step knowledge storage from properties
(primary_knowledge_uids, supporting_knowledge_uids) to
CONTAINS_KNOWLEDGE relationships.

Universal Hierarchical Pattern: Move from property-based storage to
graph-native relationship storage for consistency.

Usage:
    uv run python scripts/migrations/migrate_ls_knowledge_relationships.py --dry-run
    uv run python scripts/migrations/migrate_ls_knowledge_relationships.py --execute

See: /docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md
"""

import asyncio
from neo4j import AsyncGraphDatabase
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.ls_knowledge")


async def analyze_ls_knowledge(driver):
    """Find LS nodes with knowledge properties."""
    query = """
    MATCH (ls:Ls)
    WHERE ls.primary_knowledge_uids IS NOT NULL
       OR ls.supporting_knowledge_uids IS NOT NULL
    RETURN ls.uid as ls_uid,
           ls.title as title,
           size(coalesce(ls.primary_knowledge_uids, [])) as primary_count,
           size(coalesce(ls.supporting_knowledge_uids, [])) as supporting_count
    ORDER BY ls.title
    """

    result = await driver.execute_query(query, routing_="r")
    return result.records


async def migrate_ls_knowledge(driver, dry_run: bool = True):
    """Migrate all LS knowledge from properties to relationships."""

    # Step 1: Find LS nodes with knowledge properties
    query = """
    MATCH (ls:Ls)
    WHERE ls.primary_knowledge_uids IS NOT NULL
       OR ls.supporting_knowledge_uids IS NOT NULL
    RETURN ls.uid as ls_uid,
           ls.primary_knowledge_uids as primary_uids,
           ls.supporting_knowledge_uids as supporting_uids
    """

    result = await driver.execute_query(query, routing_="r")

    logger.info(f"Found {len(result.records)} LS nodes with knowledge properties")

    if not result.records:
        logger.info("✅ No LS knowledge properties to migrate")
        return 0

    if dry_run:
        logger.info("")
        logger.info("DRY RUN - Would migrate:")
        for record in result.records:
            ls_uid = record["ls_uid"]
            primary_count = len(record["primary_uids"] or [])
            supporting_count = len(record["supporting_uids"] or [])
            logger.info(f"  {ls_uid}: {primary_count} primary, {supporting_count} supporting")
        return 0

    migrated = 0

    for record in result.records:
        ls_uid = record["ls_uid"]
        primary_uids = record["primary_uids"] or []
        supporting_uids = record["supporting_uids"] or []

        # Create primary relationships
        for ku_uid in primary_uids:
            await driver.execute_query(
                """
                MATCH (ls:Ls {uid: $ls_uid})
                MATCH (ku:Ku {uid: $ku_uid})
                MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
                SET r.type = 'primary', r.created_at = datetime()
                """,
                ls_uid=ls_uid,
                ku_uid=ku_uid
            )

        # Create supporting relationships
        for ku_uid in supporting_uids:
            await driver.execute_query(
                """
                MATCH (ls:Ls {uid: $ls_uid})
                MATCH (ku:Ku {uid: $ku_uid})
                MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
                SET r.type = 'supporting', r.created_at = datetime()
                """,
                ls_uid=ls_uid,
                ku_uid=ku_uid
            )

        # Remove properties
        await driver.execute_query(
            """
            MATCH (ls:Ls {uid: $ls_uid})
            REMOVE ls.primary_knowledge_uids, ls.supporting_knowledge_uids
            SET ls.migrated_at = datetime()
            """,
            ls_uid=ls_uid
        )

        migrated += 1
        logger.info(f"  ✅ {ls_uid}: {len(primary_uids)} primary, {len(supporting_uids)} supporting")

    logger.info(f"✅ Migrated {migrated} LS nodes")
    return migrated


async def verify_migration(driver):
    """Verify migration was successful."""
    # Check for remaining properties
    properties_query = """
    MATCH (ls:Ls)
    WHERE ls.primary_knowledge_uids IS NOT NULL
       OR ls.supporting_knowledge_uids IS NOT NULL
    RETURN count(ls) as remaining
    """

    # Check relationship creation
    relationships_query = """
    MATCH (ls:Ls)-[r:CONTAINS_KNOWLEDGE]->(ku:Ku)
    RETURN count(DISTINCT ls) as ls_count,
           count(r) as relationship_count,
           count(DISTINCT ku) as ku_count
    """

    props_result = await driver.execute_query(properties_query)
    rels_result = await driver.execute_query(relationships_query)

    remaining = props_result.records[0]["remaining"] if props_result.records else 0
    rels_record = rels_result.records[0] if rels_result.records else {}

    logger.info("")
    logger.info("Verification Results:")
    logger.info(f"  Remaining properties: {remaining}")
    logger.info(f"  LS nodes with relationships: {rels_record.get('ls_count', 0)}")
    logger.info(f"  Total CONTAINS_KNOWLEDGE relationships: {rels_record.get('relationship_count', 0)}")
    logger.info(f"  Distinct KUs referenced: {rels_record.get('ku_count', 0)}")

    return remaining == 0


async def main(dry_run: bool = True):
    """Execute migration."""
    from core.config import neo4j_uri, neo4j_username, neo4j_password

    logger.info("=" * 80)
    logger.info("LS Knowledge Relationship Migration")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("")

    driver = AsyncGraphDatabase.driver(
        neo4j_uri(),
        auth=(neo4j_username(), neo4j_password())
    )

    try:
        # Step 1: Analyze
        logger.info("Step 1: Analyzing LS knowledge properties...")
        analysis = await analyze_ls_knowledge(driver)

        if not analysis:
            logger.info("✅ No LS knowledge properties found. Migration not needed.")
            return

        total_primary = sum(r["primary_count"] for r in analysis)
        total_supporting = sum(r["supporting_count"] for r in analysis)
        logger.info(f"  Total LS nodes: {len(analysis)}")
        logger.info(f"  Total primary knowledge refs: {total_primary}")
        logger.info(f"  Total supporting knowledge refs: {total_supporting}")
        logger.info("")

        if dry_run:
            logger.info("Step 2: Planning migration...")
            await migrate_ls_knowledge(driver, dry_run=True)
            logger.info("")
            logger.info("=" * 80)
            logger.info("DRY RUN COMPLETE - No changes made")
            logger.info("To execute migration, run with --execute flag")
            logger.info("=" * 80)
            return

        # Step 2: Execute migration
        logger.info("Step 2: Executing migration...")
        logger.warning("⚠️  EXECUTING MIGRATION - Database will be modified!")
        logger.info("")

        migrated = await migrate_ls_knowledge(driver, dry_run=False)

        # Step 3: Verify
        logger.info("")
        logger.info("Step 3: Verifying migration...")
        success = await verify_migration(driver)

        if success:
            logger.info("✅ SUCCESS: All LS knowledge migrated to relationships")
        else:
            logger.warning("⚠️  WARNING: Some properties may remain")

    finally:
        await driver.close()

    logger.info("")
    logger.info("=" * 80)
    logger.info("Migration complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    import sys

    dry_run = "--execute" not in sys.argv
    asyncio.run(main(dry_run=dry_run))
