#!/usr/bin/env python3
"""
Backfill the turn-in snapshot's version, ``turn_in_revision``
=============================================================

The turn-in writer stamps ``turn_in_revision`` onto every UserEntry beside its
exercise snapshot — the attempt number the ``FULFILLS_EXERCISE {revision}`` edge
carries, copied so the version survives the exercise's deletion exactly as the
title does (Submit & Share arc R12); every surface prints "<exercise> · v<N>"
from it. This script stamps the turn-ins that carry no value, once.

How each candidate's version is resolved (in order, one source per row):

1. **The edge** — ``FULFILLS_EXERCISE.revision`` where the exercise still lives.
2. **The stray node property** — ``revision_number``, which nothing writes on a
   UserEntry any more (ADR-054 moved it onto the edge).
3. **The attempt's ordinal** — for an entry whose exercise is gone and that
   carries neither: its position by ``created_at`` among the same owner's
   turn-ins on the same snapshot uid (the order the writer minted them in).

The same ``--confirm`` write removes the stray ``revision_number`` from every
UserEntry node (the ADR-054 invariant, ``test_collapse_to_user_entry.py``:
"revision_number has moved off the node"). Nothing else is touched; an entry
that is not a turn-in (no snapshot uid) is never a candidate.

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must report 0 candidates. The second census
catches a turn-in the old code wrote in between (it would carry no stamp).

Usage:
    uv run scripts/migrations/backfill_turn_in_revision_2026_09.py            # census
    uv run scripts/migrations/backfill_turn_in_revision_2026_09.py --confirm  # stamp
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars (strings, ints, temporal), so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

_ENTITY = NeoLabel.ENTITY.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_EXERCISE = NeoLabel.EXERCISE.value
_FULFILLS = RelationshipName.FULFILLS_EXERCISE.value

# The one resolution, shared by the census and the write: every stamp-less
# turn-in with the version each source offers and its ordinal in its exchange.
_RESOLVE = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.turn_in_exercise_uid IS NOT NULL AND e.turn_in_revision IS NULL
OPTIONAL MATCH (e)-[r:{_FULFILLS}]->(:{_ENTITY}:{_EXERCISE})
WITH e, max(r.revision) AS edge_revision
OPTIONAL MATCH (sibling:{_ENTITY}:{_USER_ENTRY})
  WHERE sibling.user_uid = e.user_uid
    AND sibling.turn_in_exercise_uid = e.turn_in_exercise_uid
    AND sibling.created_at < e.created_at
WITH e, edge_revision, count(sibling) + 1 AS ordinal
WITH e,
     coalesce(edge_revision, e.revision_number, ordinal) AS revision,
     CASE
       WHEN edge_revision IS NOT NULL THEN 'edge'
       WHEN e.revision_number IS NOT NULL THEN 'property'
       ELSE 'ordinal'
     END AS source
"""

_CANDIDATES = (
    _RESOLVE
    + """
RETURN e.uid AS uid, e.title AS title, e.user_uid AS owner,
       e.turn_in_exercise_uid AS root_uid, revision, source
ORDER BY source, owner, root_uid, revision
"""
)

_STAMP = (
    _RESOLVE
    + """
SET e.turn_in_revision = toInteger(revision)
RETURN count(e) AS stamped
"""
)

_STRAY_ROWS = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.revision_number IS NOT NULL
RETURN e.uid AS uid, e.title AS title, e.revision_number AS revision_number,
       e.turn_in_revision AS turn_in_revision
ORDER BY uid
"""

_DROP_STRAY = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.revision_number IS NOT NULL
REMOVE e.revision_number
RETURN count(e) AS cleared
"""

_STAMPED_TOTAL = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.turn_in_revision IS NOT NULL
RETURN count(e) AS stamped
"""


async def _fetch(driver: AsyncDriver, query: str) -> list[Row]:
    result = await driver.execute_query(query)
    return [dict(record) for record in result.records]


async def _census(driver: AsyncDriver) -> tuple[list[Row], list[Row]]:
    """Print the census; return (stamp candidates, stray-property rows)."""
    candidates = await _fetch(driver, _CANDIDATES)
    print(f"\nTurn-ins without turn_in_revision (ALL are stamped): {len(candidates)}")
    for row in candidates:
        print(
            f"  {row['uid']}  owner={row['owner']}  root={row['root_uid']}  "
            f"v{row['revision']}  from={row['source']}  title={row['title']!r}"
        )
    strays = await _fetch(driver, _STRAY_ROWS)
    print(f"\nUserEntry nodes carrying the stray revision_number (ALL are cleared): {len(strays)}")
    for row in strays:
        print(
            f"  {row['uid']}  revision_number={row['revision_number']}  "
            f"turn_in_revision={row['turn_in_revision']}  title={row['title']!r}"
        )
    total = await _fetch(driver, _STAMPED_TOTAL)
    print(f"\nTurn-ins already carrying turn_in_revision: {int(total[0]['stamped']) if total else 0}")
    return candidates, strays


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stamp turn_in_revision on pre-PR-7 turn-ins; clear the stray revision_number"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the stamp (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        candidates, strays = await _census(driver)
        print(f"\nWould stamp: {len(candidates)} turn-in(s); would clear: {len(strays)} node(s)")
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to stamp.")
            return 0
        if not candidates and not strays:
            print("\nNothing to do.")
            return 0

        if candidates:
            done = await _fetch(driver, _STAMP)
            print(f"\nStamped {int(done[0]['stamped']) if done else 0} turn-in(s).")
        if strays:
            done = await _fetch(driver, _DROP_STRAY)
            print(f"Cleared revision_number from {int(done[0]['cleared']) if done else 0} node(s).")

        print("\n=== AFTER ===")
        remaining, strays_left = await _census(driver)
        if remaining or strays_left:
            print(
                f"\nFAILED: {len(remaining)} turn-in(s) still unstamped, "
                f"{len(strays_left)} stray revision_number(s) remain."
            )
            return 1
        print("\nOK: every turn-in carries turn_in_revision; no UserEntry carries revision_number.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
