"""
Migrate: Legacy Activity Completion Aliases -> Canonical Fields
===============================================================

One-shot migration companion to the Tier 6 writer fix (PR #725). Two
activity writers persisted node properties under names no model, DTO, or
query reads back:

* ``HabitsProgressService.complete_habit_with_quality`` wrote the 30-day
  consistency score as ``consistency_30d`` — every reader consumes
  ``Habit.success_rate`` (enrichment, scheduling, AI, patterns), which no
  writer populated. The deleted context-first converter was the only code
  that ever surfaced the value, via a read-side alias.
* ``GoalsProgressService`` completion paths wrote ``completion_date`` —
  the canonical Goal/GoalDTO field is ``achieved_date``. So did
  ``GoalsCoreService.complete_goal`` (via the legacy
  ``GoalUpdateIntent.completion_date`` field) until the completion-stamping
  arc renamed the intent field on 2026-08-22 — re-run this script after
  that fix merges to retire the alias rows it kept writing.

The writers now persist the canonical names; this script moves the value
on nodes written before the fix:

* ``SET h.success_rate = h.consistency_30d`` / ``REMOVE h.consistency_30d``
  (only where ``success_rate`` is not already set — canonical wins).
* ``SET g.achieved_date = g.completion_date`` / ``REMOVE g.completion_date``
  (same guard).

Idempotent: re-running on a migrated (or fresh) database is a no-op.

Usage::

    uv run python scripts/migrate_activity_completion_aliases.py [--apply]

Without ``--apply`` the script audits only; pass the flag to actually
migrate.
"""

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.utils.logging import get_logger

load_dotenv(project_root / ".env")

logger = get_logger(__name__)

HABIT_AUDIT_QUERY = """
MATCH (h:Entity {entity_type: 'habit'}) WHERE h.consistency_30d IS NOT NULL
RETURN h.uid AS uid, h.success_rate AS success_rate, h.consistency_30d AS consistency_30d
"""

HABIT_MIGRATE_QUERY = """
MATCH (h:Entity {entity_type: 'habit'}) WHERE h.consistency_30d IS NOT NULL
SET h.success_rate = coalesce(h.success_rate, h.consistency_30d)
REMOVE h.consistency_30d
RETURN h.uid AS uid, h.success_rate AS success_rate
"""

GOAL_AUDIT_QUERY = """
MATCH (g:Entity {entity_type: 'goal'}) WHERE g.completion_date IS NOT NULL
RETURN g.uid AS uid, g.achieved_date AS achieved_date, g.completion_date AS completion_date
"""

GOAL_MIGRATE_QUERY = """
MATCH (g:Entity {entity_type: 'goal'}) WHERE g.completion_date IS NOT NULL
SET g.achieved_date = coalesce(g.achieved_date, g.completion_date)
REMOVE g.completion_date
RETURN g.uid AS uid, g.achieved_date AS achieved_date
"""


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration (default: audit only)",
    )
    args = parser.parse_args()

    conn = Neo4jConnection()
    driver = conn.connect()
    try:
        async with driver.session() as session:
            result = await session.run(HABIT_AUDIT_QUERY)
            habit_rows = [r async for r in result]
            result = await session.run(GOAL_AUDIT_QUERY)
            goal_rows = [r async for r in result]

        if not habit_rows and not goal_rows:
            print("✓ No nodes carry legacy completion aliases — nothing to do")
            return 0

        if habit_rows:
            print(f"Found {len(habit_rows)} Habit node(s) with legacy `consistency_30d`:")
            for r in habit_rows:
                print(
                    f"  {r['uid']}: success_rate={r['success_rate']!r} "
                    f"<- consistency_30d={r['consistency_30d']!r}"
                )
        if goal_rows:
            print(f"Found {len(goal_rows)} Goal node(s) with legacy `completion_date`:")
            for r in goal_rows:
                print(
                    f"  {r['uid']}: achieved_date={r['achieved_date']!r} "
                    f"<- completion_date={r['completion_date']!r}"
                )

        if not args.apply:
            print("\nAudit only — re-run with --apply to migrate")
            return 0

        async with driver.session() as session:
            result = await session.run(HABIT_MIGRATE_QUERY)
            habits_migrated = [r async for r in result]
            result = await session.run(GOAL_MIGRATE_QUERY)
            goals_migrated = [r async for r in result]
        for r in habits_migrated:
            print(f"✓ Migrated habit {r['uid']}: success_rate={r['success_rate']!r}")
        for r in goals_migrated:
            print(f"✓ Migrated goal {r['uid']}: achieved_date={r['achieved_date']!r}")
        print(f"✓ {len(habits_migrated) + len(goals_migrated)} node(s) migrated")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
