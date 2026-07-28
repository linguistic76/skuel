#!/usr/bin/env python3
"""Audit Goal.current_value for stale percents, and clear the ones an operator names.

Four writers in ``core/services/goals/goals_progress_service.py`` used to persist a
percent into ``current_value`` in the same update dict as ``progress_percentage``, while
``target_value`` holds domain units (5 tasks, a 30-day streak, 10 books). Those writers
now leave ``current_value`` alone, but a semantic change to a stored field does not reach
rows already written — and the goal detail page renders
``{current_value}/{target_value} {unit}``, so a five-task goal stamped ``20/5`` would
display that forever.

**Why this audits instead of migrating.** There is no reliable way to tell a corrupted
row from a valid one, because the percent overwrote the measurement without leaving any
provenance. ``current_value = progress_percentage`` fails in both directions, and code
review found both:

- False positives — an independently-authored ``target_value=10, current_value=5`` with a
  separately reported ``progress_percentage=5`` is a legitimate measurement that the
  equality would have cleared irreversibly.
- False negatives — a row stamped ``current_value=20`` whose percent later moved (e.g.
  ``complete_goal`` setting ``progress_percentage=100`` and nothing else) no longer
  satisfies the equality, so an equality-gated migration reports it clean while the
  detail page still renders ``20/5``.

Tightening the predicate trades one failure for the other. So this script does not guess:
it lists every goal carrying a nonzero ``current_value`` with the evidence needed to judge
it, and clears only UIDs the operator passes explicitly. ``--clear`` is the whole write
surface, and it names its rows.

Measured on the development graph 2026-07-28: 3 goals, 0 with a nonzero ``current_value``.
That is not evidence about any other instance, which is why this ships.

Usage:
    uv run python scripts/migrations/audit_goal_current_value_units_2026_07.py
    uv run python scripts/migrations/audit_goal_current_value_units_2026_07.py --clear goal_abc goal_def
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any, TypedDict, cast

from neo4j import AsyncDriver, AsyncGraphDatabase

from core.models.enums.goal_enums import MeasurementType
from core.utils.logging import get_logger
from core.utils.type_converters import finite_float

logger = get_logger(__name__)

# The measurement types whose current_value the four legacy writers could reach:
# update_goal_from_habit_progress (habit_based), _update_goal_from_task_completion
# (task_based, mixed) and _update_goal_from_habit_completion (habit_based, mixed).
# update_goal_progress wrote any type but has no route, so it never ran. This is
# reported as a signal, NOT used to filter — a goal's measurement_type can be edited
# after the fact, so a row outside the set is less suspicious, never proven clean.
_LEGACY_WRITER_TYPES = frozenset(
    {
        MeasurementType.TASK_BASED.value,
        MeasurementType.HABIT_BASED.value,
        MeasurementType.MIXED.value,
    }
)

AUDIT_QUERY = """
MATCH (g:Goal)
WHERE g.current_value IS NOT NULL AND g.current_value <> 0
RETURN g.uid AS uid,
       g.title AS title,
       g.measurement_type AS measurement_type,
       g.current_value AS current_value,
       g.target_value AS target_value,
       g.unit_of_measurement AS unit_of_measurement,
       g.progress_percentage AS progress_percentage
ORDER BY g.uid
"""

CLEAR_QUERY = """
UNWIND $uids AS uid
MATCH (g:Goal {uid: uid})
SET g.current_value = 0.0
RETURN count(g) AS cleared
"""


class GoalMeasurementRow(TypedDict):
    """One audited goal's measurement fields, exactly as stored.

    The three numeric fields are ``Any`` on purpose. Declaring them ``float`` would be
    the same lie that produced the malformed rows this script exists to find: Neo4j
    properties are untyped and vault ingestion copies frontmatter through unchecked, so
    a quoted ``current_value: "20"`` is stored and read back as ``str``. Every numeric
    use narrows through ``finite_float`` instead of trusting the annotation.
    """

    uid: str
    title: str | None
    measurement_type: str | None
    # boundary: untyped Neo4j properties — a quoted YAML scalar arrives here as str
    current_value: Any
    target_value: Any
    progress_percentage: Any
    unit_of_measurement: str | None


async def audit_rows(driver: AsyncDriver) -> list[GoalMeasurementRow]:
    """Every goal carrying a nonzero current_value — the full review surface."""
    result = await driver.execute_query(AUDIT_QUERY, routing_="r")
    # Driver payloads are untyped dicts; AUDIT_QUERY's RETURN aliases are the shape.
    # Same cast-at-the-record idiom as adapters/persistence/neo4j/batch_chunking_backend.py.
    return [cast("GoalMeasurementRow", record.data()) for record in result.records]


async def clear_named(driver: AsyncDriver, uids: list[str]) -> int:
    """Reset current_value to the field default on exactly the named goals."""
    result = await driver.execute_query(CLEAR_QUERY, uids=uids)
    return int(result.records[0]["cleared"]) if result.records else 0


def _suspicion(row: GoalMeasurementRow) -> str:
    """Why this row might be a stale percent. Advisory — the operator decides.

    Every numeric comparison narrows first. Comparing the stored values directly
    raised ``TypeError: '>' not supported between instances of 'str' and 'int'`` on a
    quoted ``current_value: "20"``, which aborted the whole audit — the one row class
    it most needs to report is the one that killed it.
    """
    reasons: list[str] = []
    current = finite_float(row["current_value"])
    target = finite_float(row["target_value"])
    percent = finite_float(row["progress_percentage"])

    if current is None:
        reasons.append(f"current_value is not a number ({row['current_value']!r})")
    if row["target_value"] is not None and target is None:
        reasons.append(f"target_value is not a number ({row['target_value']!r})")
    if current is not None and percent is not None and current == percent:
        reasons.append("current_value == progress_percentage")
    if current is not None and target is not None and target > 0 and current > target:
        reasons.append("current_value exceeds target_value")
    if (row["measurement_type"] or "") in _LEGACY_WRITER_TYPES:
        reasons.append("measurement_type was reachable by a legacy writer")
    return "; ".join(reasons) if reasons else "no legacy signal"


async def main(clear_uids: list[str]) -> int:
    from core.config import get_settings

    logger.info("=" * 78)
    logger.info("Goal.current_value unit audit")
    logger.info(f"Mode: {'CLEAR named uids' if clear_uids else 'AUDIT (read-only)'}")
    logger.info("=" * 78)

    db = get_settings().database
    driver = AsyncGraphDatabase.driver(db.neo4j_uri, auth=(db.neo4j_username, db.neo4j_password))
    try:
        rows = await audit_rows(driver)

        # Checked before the empty-set early return, so naming a UID that cannot be
        # cleared is always an error rather than a silently ignored argument.
        unknown = [uid for uid in clear_uids if uid not in {row["uid"] for row in rows}]
        if unknown:
            logger.error(
                f"Refusing to write: {unknown} carry no nonzero current_value "
                "(already clean, or not a goal). Re-run the audit."
            )
            return 1

        if not rows:
            logger.info("No goal carries a nonzero current_value. Nothing to review.")
            return 0

        logger.info(f"{len(rows)} goal(s) carry a nonzero current_value:")
        for row in rows:
            unit = row["unit_of_measurement"] or "units"
            logger.info(
                f"  {row['uid']} — {row['title']!r}\n"
                f"      measurement_type={row['measurement_type']} "
                f"reads {row['current_value']}/{row['target_value']} {unit} "
                f"at {row['progress_percentage']}%\n"
                f"      signal: {_suspicion(row)}"
            )

        if not clear_uids:
            logger.info(
                "Read-only. Judge each row above, then re-run with "
                "--clear <uid> [<uid> ...] to reset the stale ones to 0.0."
            )
            return 0

        cleared = await clear_named(driver, clear_uids)
        logger.info(f"Cleared current_value on {cleared} goal(s): {clear_uids}")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clear",
        nargs="+",
        default=[],
        metavar="UID",
        help="Goal UIDs whose current_value to reset to 0.0 (default: audit only)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.clear)))
