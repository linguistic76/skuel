"""
Flatten KU UIDs - Universal Hierarchical Pattern Migration
==========================================================

Migrates KU UIDs from hierarchical (ku.yoga.meditation.basics)
to flat format (ku_meditation-basics_a1b2c3d4).

CRITICAL: Backup database before running!

Usage:
    poetry run python scripts/migrations/flatten_ku_uids.py --dry-run
    poetry run python scripts/migrations/flatten_ku_uids.py --execute

See: /docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md
"""

import asyncio
import uuid
from neo4j import AsyncGraphDatabase
from core.utils.uid_generator import UIDGenerator
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.flatten_ku_uids")


async def analyze_hierarchical_kus(driver):
    """Find all KUs with hierarchical UIDs."""
    query = """
    MATCH (ku:Ku)
    WHERE ku.uid CONTAINS '.'
    AND size(split(ku.uid, '.')) > 2
    RETURN ku.uid as old_uid, ku.title as title, size(split(ku.uid, '.')) as depth
    ORDER BY depth DESC, old_uid ASC
    """

    result = await driver.execute_query(query, routing_="r")
    return result.records


async def generate_new_uid(title: str, existing_uids: set[str]) -> str:
    """Generate flat UID, ensuring uniqueness."""
    max_attempts = 100

    for _ in range(max_attempts):
        new_uid = UIDGenerator.generate_knowledge_uid(title)
        if new_uid not in existing_uids:
            return new_uid

    # Fallback: add extra random suffix
    slug = UIDGenerator.slugify(title)
    random_suffix = uuid.uuid4().hex[:12]
    return f"ku_{slug}_{random_suffix}"


async def flatten_ku_uid(driver, old_uid: str, new_uid: str):
    """Flatten a single KU UID, preserving all relationships."""
    query = """
    MATCH (ku:Ku {uid: $old_uid})
    SET ku.uid = $new_uid,
        ku.old_uid = $old_uid,
        ku.migrated_at = datetime()
    RETURN ku.uid as new_uid
    """

    result = await driver.execute_query(
        query,
        old_uid=old_uid,
        new_uid=new_uid
    )

    return result.records[0]["new_uid"] if result.records else None


async def main(dry_run: bool = True):
    """Execute migration."""
    from core.config import neo4j_uri, neo4j_username, neo4j_password

    logger.info("=" * 80)
    logger.info("KU UID Flattening Migration")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("")

    driver = AsyncGraphDatabase.driver(
        neo4j_uri(),
        auth=(neo4j_username(), neo4j_password())
    )

    try:
        # Step 1: Analyze
        logger.info("Step 1: Analyzing hierarchical KU UIDs...")
        hierarchical_kus = await analyze_hierarchical_kus(driver)

        if not hierarchical_kus:
            logger.info("✅ No hierarchical KU UIDs found. Migration not needed.")
            return

        logger.info(f"Found {len(hierarchical_kus)} hierarchical KU UIDs")
        logger.info("")

        # Step 2: Plan flattening
        logger.info("Step 2: Planning UID flattening...")
        existing_uids = set()
        migration_plan = []

        for record in hierarchical_kus:
            old_uid = record["old_uid"]
            title = record["title"]
            depth = record["depth"]

            new_uid = await generate_new_uid(title, existing_uids)
            existing_uids.add(new_uid)

            migration_plan.append({
                "old_uid": old_uid,
                "new_uid": new_uid,
                "title": title,
                "depth": depth
            })

            logger.info(f"  {old_uid} → {new_uid} (depth: {depth})")

        logger.info("")
        logger.info(f"Migration plan created for {len(migration_plan)} KUs")

        if dry_run:
            logger.info("")
            logger.info("=" * 80)
            logger.info("DRY RUN COMPLETE - No changes made")
            logger.info("To execute migration, run with --execute flag")
            logger.info("=" * 80)
            return

        # Step 3: Execute migration
        logger.info("")
        logger.info("Step 3: Executing migration...")
        logger.warning("⚠️  EXECUTING MIGRATION - Database will be modified!")

        migrated_count = 0
        for plan in migration_plan:
            result_uid = await flatten_ku_uid(driver, plan["old_uid"], plan["new_uid"])
            if result_uid:
                migrated_count += 1
                logger.info(f"  ✅ {plan['old_uid']} → {result_uid}")
            else:
                logger.error(f"  ❌ Failed: {plan['old_uid']}")

        logger.info("")
        logger.info(f"✅ Migrated {migrated_count}/{len(migration_plan)} KU UIDs")

        # Step 4: Verify
        logger.info("")
        logger.info("Step 4: Verifying migration...")
        remaining = await analyze_hierarchical_kus(driver)

        if not remaining:
            logger.info("✅ SUCCESS: All KU UIDs flattened")
        else:
            logger.warning(f"⚠️  {len(remaining)} hierarchical UIDs remain")
            for record in remaining:
                logger.warning(f"  - {record['old_uid']}")

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
