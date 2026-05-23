"""
Canonicalize user_uid owners - Underscore Convention Migration
==============================================================

Normalizes legacy non-canonical ``user_uid`` owner values on :Entity nodes to the
canonical ``user_<name>`` form, so ownership comparisons (exact string match) reach
the right user:

    user:system  -> user_system
    system        -> user_system
    user:mike     -> user_mike

The canonical format is enforced going forward by TypeConverter.to_user_uid and the
ingestion validator; this script fixes data created before that.

CRITICAL: Back up the database before running.

Usage:
    uv run python scripts/migrations/canonicalize_user_uid_2026_05.py            # dry-run
    uv run python scripts/migrations/canonicalize_user_uid_2026_05.py --execute  # live

See: /docs/migrations/USER_UID_CANONICALIZATION_2026-05.md
"""

import asyncio

from neo4j import AsyncGraphDatabase

from core.models.type_hints import TypeConverter, UserUID
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.canonicalize_user_uid")


async def find_noncanonical_owners(driver) -> list[dict]:
    """Return distinct non-canonical user_uid owner values with counts."""
    query = """
    MATCH (n:Entity)
    WHERE n.user_uid IS NOT NULL AND NOT n.user_uid STARTS WITH 'user_'
    RETURN n.user_uid AS owner, count(*) AS c
    ORDER BY c DESC
    """
    result = await driver.execute_query(query, routing_="r")
    return [{"owner": r["owner"], "count": r["c"]} for r in result.records]


async def rewrite_owner(driver, old_owner: str, new_owner: str) -> int:
    """Set user_uid=new_owner on every :Entity currently owned by old_owner."""
    query = """
    MATCH (n:Entity {user_uid: $old_owner})
    SET n.user_uid = $new_owner
    RETURN count(n) AS c
    """
    result = await driver.execute_query(query, old_owner=old_owner, new_owner=new_owner)
    return result.records[0]["c"] if result.records else 0


async def main(dry_run: bool = True) -> None:
    from core.config import get_settings

    logger.info("=" * 80)
    logger.info("user_uid Canonicalization Migration")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("=" * 80)

    db = get_settings().database
    driver = AsyncGraphDatabase.driver(
        db.neo4j_uri, auth=(db.neo4j_username, db.neo4j_password)
    )
    try:
        owners = await find_noncanonical_owners(driver)
        if not owners:
            logger.info("✅ No non-canonical user_uid owners found. Nothing to do.")
            return

        total = sum(o["count"] for o in owners)
        logger.info(f"Found {len(owners)} non-canonical owner(s) across {total} node(s):")
        plan: list[tuple[str, UserUID, int]] = []
        for o in owners:
            canonical = TypeConverter.normalize_user_uid(o["owner"])
            plan.append((o["owner"], canonical, o["count"]))
            logger.info(f"  {o['owner']!r} → {canonical!r}  ({o['count']} nodes)")

        if dry_run:
            logger.info("DRY RUN COMPLETE — no changes made. Re-run with --execute.")
            return

        logger.warning("⚠️  EXECUTING — database will be modified!")
        migrated = 0
        for src_owner, dst_owner, _ in plan:
            migrated += await rewrite_owner(driver, src_owner, dst_owner)
        logger.info(f"✅ Rewrote {migrated} node(s).")

        remaining = await find_noncanonical_owners(driver)
        if not remaining:
            logger.info("✅ SUCCESS: all :Entity owners are now canonical (user_<name>).")
        else:
            logger.warning(f"⚠️  {len(remaining)} non-canonical owner(s) remain: {remaining}")
    finally:
        await driver.close()
    logger.info("=" * 80)
    logger.info("Migration complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    import sys

    asyncio.run(main(dry_run="--execute" not in sys.argv))
