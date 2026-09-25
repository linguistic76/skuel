#!/usr/bin/env python3
"""
Backfill the turn-in snapshot — ``turn_in_exercise_uid`` / ``turn_in_exercise_title``
=====================================================================================

Every turn-in carries a snapshot of the root exercise it was filed against:
its uid and its title as they read at submission. The GradeBook, the
exchange thread, the review queue's copy collapse and the report titles all
key on it, so an exchange outlives the deletion of its exercise (Submit &
Share arc R12 — ``docs/roadmap/submission-sharing-arc.md``, PR 4a). The
writer stamps it on every new turn-in; this script stamps it on the turn-ins
that predate it.

What is stamped, and from where (first hit wins):

- **A turn-in with a ``FULFILLS_EXERCISE`` edge** — the root is the target
  Exercise; a RevisedExercise target resolves through its ``REVISES_EXERCISE``
  original, then its ``original_exercise_uid``, then itself (the writer's
  own rule).
- **A turn-in with only a ``FULFILLS_REVISED_EXERCISE`` edge** — the root is
  the revision's ``REVISES_EXERCISE`` original, else its
  ``original_exercise_uid``, else the revision.
- **An edge-less entry that still names an exercise in
  ``fulfills_exercise_uid`` and carries a turn-in trace** (an ``Interaction``
  ``RECORDS`` it — minted only when a frozen copy files) — the exercise was
  deleted before the snapshot existed and the property is the only thing
  left of the exchange. The uid resolves through a live RevisedExercise's
  ``original_exercise_uid`` when it names one. With no live node the title
  is the "Exercise removed" placeholder.

**Skipped, listed, never touched:** an entry whose ``fulfills_exercise_uid``
is declared intent only — a living vault note with no edge and no turn-in
trace. It is not a turn-in and must not join an exchange.

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must report 0 candidates. Un-backfilled
turn-ins are invisible to the snapshot-keyed reads: they drop out of their
exchange into Other feedback — the defect the snapshot removes.

Usage:
    uv run scripts/migrations/backfill_turn_in_exercise_snapshot_2026_09.py            # census
    uv run scripts/migrations/backfill_turn_in_exercise_snapshot_2026_09.py --confirm  # stamp
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.user_entry.user_entry import EXERCISE_REMOVED_TITLE

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars (strings, ints, booleans), so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

_ENTITY = NeoLabel.ENTITY.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_EXERCISE = NeoLabel.EXERCISE.value
_REVISED = NeoLabel.REVISED_EXERCISE.value
_INTERACTION = NeoLabel.INTERACTION.value
_FULFILLS = RelationshipName.FULFILLS_EXERCISE.value
_FULFILLS_REVISED = RelationshipName.FULFILLS_REVISED_EXERCISE.value
_REVISES = RelationshipName.REVISES_EXERCISE.value
_RECORDS = RelationshipName.RECORDS.value

# The one resolution, shared by the census and the write: every candidate
# (a snapshot-less entry that is a turn-in by edge or by trace) with its
# resolved root uid, the title to stamp, and which source resolved it.
_RESOLVE = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.turn_in_exercise_uid IS NULL
  AND (
    EXISTS {{ (e)-[:{_FULFILLS}]->() }}
    OR EXISTS {{ (e)-[:{_FULFILLS_REVISED}]->() }}
    OR (e.fulfills_exercise_uid IS NOT NULL
        AND EXISTS {{ (:{_ENTITY}:{_INTERACTION})-[:{_RECORDS}]->(e) }})
  )
OPTIONAL MATCH (e)-[:{_FULFILLS}]->(direct:{_ENTITY})
  WHERE direct.entity_type IN $exercise_types
OPTIONAL MATCH (direct)-[:{_REVISES}]->(direct_orig:{_ENTITY}:{_EXERCISE})
OPTIONAL MATCH (e)-[:{_FULFILLS_REVISED}]->(re:{_ENTITY}:{_REVISED})
OPTIONAL MATCH (re)-[:{_REVISES}]->(re_orig:{_ENTITY}:{_EXERCISE})
OPTIONAL MATCH (prop:{_ENTITY} {{uid: e.fulfills_exercise_uid}})
  WHERE prop.entity_type IN $exercise_types
OPTIONAL MATCH (prop)-[:{_REVISES}]->(prop_orig:{_ENTITY}:{_EXERCISE})
WITH e, direct, re, prop,
     coalesce(
       CASE WHEN direct.entity_type = $exercise THEN direct.uid END,
       direct_orig.uid, direct.original_exercise_uid, direct.uid,
       re_orig.uid, re.original_exercise_uid, re.uid,
       CASE WHEN prop.entity_type = $exercise THEN prop.uid END,
       prop_orig.uid, prop.original_exercise_uid, prop.uid,
       e.fulfills_exercise_uid
     ) AS root_uid,
     CASE
       WHEN direct IS NOT NULL THEN 'edge'
       WHEN re IS NOT NULL THEN 'revised_edge'
       ELSE 'property'
     END AS source
OPTIONAL MATCH (root:{_ENTITY} {{uid: root_uid}})
  WHERE root.entity_type IN $exercise_types
WITH e, root_uid, source, root,
     coalesce(root.title, direct.title, re.title, prop.title) AS live_title
"""

_CANDIDATES = (
    _RESOLVE
    + """
RETURN e.uid AS uid, e.title AS title, e.pipeline AS pipeline, e.user_uid AS owner,
       root_uid, source, root IS NOT NULL AS root_live,
       coalesce(live_title, $placeholder) AS snapshot_title,
       live_title IS NULL AS title_is_placeholder
ORDER BY source, owner, uid
"""
)

_STAMP = (
    _RESOLVE
    + """
SET e.turn_in_exercise_uid = root_uid,
    e.turn_in_exercise_title = coalesce(live_title, $placeholder)
RETURN count(e) AS stamped
"""
)

# Declared intent that is NOT a turn-in: the property with no edge and no
# Interaction trace. Listed so the operator sees what the backfill leaves
# alone — a living vault note keeps its intent and joins no exchange.
_INTENT_ONLY = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.turn_in_exercise_uid IS NULL
  AND e.fulfills_exercise_uid IS NOT NULL
  AND NOT EXISTS {{ (e)-[:{_FULFILLS}]->() }}
  AND NOT EXISTS {{ (e)-[:{_FULFILLS_REVISED}]->() }}
  AND NOT EXISTS {{ (:{_ENTITY}:{_INTERACTION})-[:{_RECORDS}]->(e) }}
RETURN e.uid AS uid, e.title AS title, e.pipeline AS pipeline, e.user_uid AS owner,
       e.fulfills_exercise_uid AS declared_uid
ORDER BY owner, uid
"""

_STAMPED_TOTAL = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.turn_in_exercise_uid IS NOT NULL
RETURN count(e) AS stamped
"""

_PARAMS: dict[str, Any] = {
    "exercise_types": [EntityType.EXERCISE.value, EntityType.REVISED_EXERCISE.value],
    "exercise": EntityType.EXERCISE.value,
    "placeholder": EXERCISE_REMOVED_TITLE,
}


async def _fetch(driver: AsyncDriver, query: str) -> list[Row]:
    result = await driver.execute_query(query, _PARAMS)
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> tuple[list[Row], list[Row]]:
    """Print the census; return (candidate rows, intent-only rows)."""
    stamped = await _fetch(driver, _STAMPED_TOTAL)
    print(f"Turn-ins already carrying the snapshot: {int(stamped[0]['stamped']) if stamped else 0}")

    candidates = await _fetch(driver, _CANDIDATES)
    by_source: dict[str, int] = {}
    for row in candidates:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    print(f"\nSnapshot-less turn-ins (ALL are stamped): {len(candidates)}")
    for source, n in sorted(by_source.items()):
        print(f"  via {source}: {n}")
    for row in candidates:
        live = "live" if row["root_live"] else "REMOVED"
        title_note = "  [title: placeholder]" if row["title_is_placeholder"] else ""
        print(
            f"  {row['uid']}  [{row['pipeline']}]  (owner {row['owner']})  {row['title']!r}"
            f"\n      -> {row['root_uid']} ({row['source']}, exercise {live})"
            f"  title={row['snapshot_title']!r}{title_note}"
        )

    intent_only = await _fetch(driver, _INTENT_ONLY)
    print(f"\nDeclared-intent-only entries (NOT turn-ins — left untouched): {len(intent_only)}")
    for row in intent_only:
        print(
            f"  {row['uid']}  [{row['pipeline']}]  (owner {row['owner']})  {row['title']!r}"
            f"  declares {row['declared_uid']}"
        )
    return candidates, intent_only


async def backfill(driver: AsyncDriver) -> int:
    """Stamp every candidate; return the count stamped."""
    done = await _fetch(driver, _STAMP)
    return int(done[0]["stamped"]) if done else 0


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stamp the turn-in snapshot on every turn-in that predates it"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the snapshot (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        candidates, _ = await census(driver)
        unrecoverable = sum(1 for row in candidates if row["title_is_placeholder"])
        print(
            f"\nWould stamp: {len(candidates)} turn-in(s) "
            f"({unrecoverable} with the placeholder title — no live exercise or revision)"
        )
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to stamp.")
            return 0
        if not candidates:
            print("\nNothing to stamp.")
            return 0

        stamped = await backfill(driver)
        print(f"\nStamped {stamped} turn-in(s).")

        print("\n=== AFTER ===")
        remaining, _ = await census(driver)
        if remaining:
            print(f"\nFAILED: {len(remaining)} snapshot-less turn-in(s) remain.")
            return 1
        print("\nOK: every turn-in carries its snapshot.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
