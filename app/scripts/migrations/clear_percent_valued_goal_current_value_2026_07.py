#!/usr/bin/env python3
"""Clear Goal.current_value rows that hold a percent rather than a domain-unit measurement.

Four writers in ``core/services/goals/goals_progress_service.py`` used to persist a
percent into ``current_value`` in the same update dict as ``progress_percentage``, while
``target_value`` holds domain units (5 tasks, a 30-day streak, 10 books). Those writers
now leave ``current_value`` alone, but a semantic change to a stored field does not
reach rows already written — and the goal detail page renders
``{current_value}/{target_value} {unit}``, so a five-task goal stamped ``20/5`` would
display that forever.

The percent cannot be converted back into a measurement: it overwrote whatever was
there. Clearing to 0.0 is the honest end state — "no measurement recorded" — and matches
the field default. ``progress_percentage`` is untouched, so no progress is lost: it is
the field every reader now uses.

**Signature.** A row is legacy when ``current_value = progress_percentage`` and the value
is nonzero — the four writers wrote one number to both keys in one statement.
``target_value = 100`` is excluded: at that target the two readings are numerically the
same, so a match there is as likely a genuine measurement (25 of 100 miles, the shape
pinned by ``tests/integration/test_goals_core_operations.py``) and clearing it would
destroy a valid value while changing no rendering.

Dry run by default. Measured on the development graph 2026-07-28: 3 goals, 0 matches.
That is not evidence about any other instance, which is why this ships.

Usage:
    uv run python scripts/migrations/clear_percent_valued_goal_current_value_2026_07.py
    uv run python scripts/migrations/clear_percent_valued_goal_current_value_2026_07.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from neo4j import AsyncGraphDatabase

from core.utils.logging import get_logger

logger = get_logger(__name__)

# The legacy signature. Kept as one string so the preview and the write cannot drift
# apart into "counted one set, updated another".
_LEGACY_MATCH = """
MATCH (g:Goal)
WHERE g.current_value IS NOT NULL
  AND g.current_value <> 0
  AND g.current_value = g.progress_percentage
  AND (g.target_value IS NULL OR g.target_value <> 100)
"""

FIND_QUERY = (
    _LEGACY_MATCH
    + """
RETURN g.uid AS uid,
       g.measurement_type AS measurement_type,
       g.current_value AS current_value,
       g.target_value AS target_value,
       g.progress_percentage AS progress_percentage
ORDER BY g.uid
"""
)

CLEAR_QUERY = (
    _LEGACY_MATCH
    + """
SET g.current_value = 0.0
RETURN count(g) AS cleared
"""
)


async def find_legacy_rows(driver: Any) -> list[dict[str, Any]]:
    """Rows whose current_value carries a percent instead of a measurement."""
    result = await driver.execute_query(FIND_QUERY, routing_="r")
    return [record.data() for record in result.records]


async def clear_legacy_rows(driver: Any) -> int:
    """Reset the matched rows to the field default. Returns the number cleared."""
    result = await driver.execute_query(CLEAR_QUERY)
    return int(result.records[0]["cleared"]) if result.records else 0


async def main(execute: bool) -> int:
    from core.config import get_settings

    logger.info("=" * 78)
    logger.info("Goal.current_value percent-value cleanup")
    logger.info(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")
    logger.info("=" * 78)

    db = get_settings().database
    driver = AsyncGraphDatabase.driver(db.neo4j_uri, auth=(db.neo4j_username, db.neo4j_password))
    try:
        rows = await find_legacy_rows(driver)
        if not rows:
            logger.info("No goals carry a percent in current_value. Nothing to do.")
            return 0

        logger.info(f"{len(rows)} goal(s) match the legacy signature:")
        for row in rows:
            logger.info(
                f"  {row['uid']} "
                f"measurement_type={row['measurement_type']} "
                f"current_value={row['current_value']} "
                f"target_value={row['target_value']} "
                f"progress_percentage={row['progress_percentage']}"
            )

        if not execute:
            logger.info("Dry run — re-run with --execute to clear current_value to 0.0.")
            return 0

        cleared = await clear_legacy_rows(driver)
        logger.info(f"Cleared current_value on {cleared} goal(s).")

        remaining = await find_legacy_rows(driver)
        if remaining:
            logger.error(f"{len(remaining)} row(s) still match after the write — investigate.")
            return 1
        logger.info("Verified: no rows match the legacy signature.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the change (default is a dry run that only reports matches)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.execute)))
