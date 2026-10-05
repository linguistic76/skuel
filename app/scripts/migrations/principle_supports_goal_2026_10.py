#!/usr/bin/env python3
"""
A principle supports a goal — GUIDES_GOAL and goal → principle GUIDED_BY_PRINCIPLE → SUPPORTS_GOAL
====================================================================================================

Re-types the two stored shapes of one fact onto the one edge the code now
writes and reads (ADR-090, ``docs/roadmap/activity-links-arc.md`` PR 2):

    (Principle)-[:GUIDES_GOAL]->(Goal)             written at the principle
    (Goal)-[:GUIDED_BY_PRINCIPLE]->(Principle)     written at the goal
        →  (Principle)-[:SUPPORTS_GOAL {weight, essentiality}]->(Goal)

A pair holding either old edge, or both, ends with exactly one new edge. The
states, per (principle, goal) pair:

- **One old edge, or both:** the new edge is MERGEd once and each old edge is
  deleted. Both statements MERGE the same edge, so the second finds the first's.
- **The new edge already there** (a link made by the new code, or an earlier
  partial run): MERGE matches it and its ``weight`` / ``essentiality`` win;
  the defaults (``1.0``, ``supporting`` — what every door stores) fill only a
  property the edge lacks.
- **A re-run:** no old edge matches, nothing is written.
- ``alignment_strength`` (the goal door's old property) is not carried: no
  reader of it exists.

What is NOT touched:

- ``(PathStep)-[:GUIDED_BY_PRINCIPLE]->(Principle)`` — that use of the type
  stays (the arc's O2, deferred). The goal-side statement matches a ``:Goal``
  source only.
- Any ``GUIDES_GOAL`` edge that is not Principle → Goal. The type leaves the
  enum with this PR, so such an edge would be stranded: the census lists each
  one and the run STOPS (exit 2) before any write until a person removes it.

The vault trackers move with the edges. A file's ``:IngestionMetadata`` row
records the edges its frontmatter authored as ``{type}|{direction}|{uid}``
keys, and a later ingest retracts ``prior - current``. A key naming a type the
enum no longer has cannot be decoded, so the edge it recorded would never be
retracted; a goal file's old key would retract nothing while its new field's
key would be absent from the record. Each key is rewritten to the edge it now
names:

    GUIDES_GOAL|outgoing|<goal>              → SUPPORTS_GOAL|outgoing|<goal>
    GUIDED_BY_PRINCIPLE|outgoing|<principle> → SUPPORTS_GOAL|incoming|<principle>
                                               (rows whose entity is a Goal only)

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the
credentials resolve):

1. Stop the running app.
2. Edit the vault files: ``connections.guides_goal`` → ``connections.supports_goal``
   on a principle file, ``connections.aligned_with_principle`` →
   ``connections.supporting_principles`` on a goal file. Do NOT sync a file that
   still declares a retired field: once it is re-ingested (a forced sync, or an
   ordinary one after any edit to it) it declares no principle link, and the
   retraction deletes the edge its tracker row records.
3. Census (no flag), then ``--confirm``.
4. ``./dev vault-sync --vault content``; the edited files re-ingest and their
   fingerprints equal the rewritten rows, so nothing is retracted.
5. Census again: 0 old edges, 0 old keys.

Usage:
    uv run scripts/migrations/principle_supports_goal_2026_10.py            # census
    uv run scripts/migrations/principle_supports_goal_2026_10.py --confirm  # re-type
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

# GUIDES_GOAL is no longer a RelationshipName member, so it is named as a string.
_GUIDES_GOAL = "GUIDES_GOAL"
_GUIDED_BY = RelationshipName.GUIDED_BY_PRINCIPLE.value
_SUPPORTS = RelationshipName.SUPPORTS_GOAL.value
_PRINCIPLE = NeoLabel.PRINCIPLE.value
_GOAL = NeoLabel.GOAL.value
_TRACKER = NeoLabel.INGESTION_METADATA.value

DEFAULT_WEIGHT = 1.0
DEFAULT_ESSENTIALITY = "supporting"

# --- census ---------------------------------------------------------------

_PRINCIPLE_SIDE_ROWS = f"""
MATCH (p:{_PRINCIPLE})-[old:{_GUIDES_GOAL}]->(g:{_GOAL})
RETURN p.uid AS principle_uid, g.uid AS goal_uid, properties(old) AS props
ORDER BY principle_uid, goal_uid
"""

_GOAL_SIDE_ROWS = f"""
MATCH (g:{_GOAL})-[old:{_GUIDED_BY}]->(p:{_PRINCIPLE})
RETURN p.uid AS principle_uid, g.uid AS goal_uid, properties(old) AS props
ORDER BY principle_uid, goal_uid
"""

_STRANDED_GUIDES_GOAL_ROWS = f"""
MATCH (a)-[old:{_GUIDES_GOAL}]->(b)
WHERE NOT (a:{_PRINCIPLE} AND b:{_GOAL})
RETURN a.uid AS source_uid, labels(a) AS source_labels,
       b.uid AS target_uid, labels(b) AS target_labels
ORDER BY source_uid, target_uid
"""

_NEW_ROWS = f"""
MATCH (p:{_PRINCIPLE})-[new:{_SUPPORTS}]->(g:{_GOAL})
RETURN p.uid AS principle_uid, g.uid AS goal_uid, properties(new) AS props
ORDER BY principle_uid, goal_uid
"""

_OTHER_GUIDED_BY_COUNT = f"""
MATCH (a)-[r:{_GUIDED_BY}]->(b)
WHERE NOT (a:{_GOAL} AND b:{_PRINCIPLE})
RETURN count(r) AS edges
"""

_TRACKER_ROWS = f"""
MATCH (row:{_TRACKER})
WHERE any(key IN coalesce(row.authored_edges, [])
          WHERE key STARTS WITH $guides_prefix OR key STARTS WITH $guided_by_prefix)
OPTIONAL MATCH (goal:{_GOAL} {{uid: row.entity_uid}})
RETURN row.file_path AS file_path, row.entity_uid AS entity_uid,
       row.authored_edges AS authored_edges, goal IS NOT NULL AS entity_is_goal
ORDER BY file_path
"""

# --- write ----------------------------------------------------------------

_RETYPE_PRINCIPLE_SIDE = f"""
MATCH (p:{_PRINCIPLE})-[old:{_GUIDES_GOAL}]->(g:{_GOAL})
MERGE (p)-[new:{_SUPPORTS}]->(g)
SET new.weight = coalesce(new.weight, $weight),
    new.essentiality = coalesce(new.essentiality, $essentiality)
DELETE old
RETURN count(old) AS edges_migrated
"""

_RETYPE_GOAL_SIDE = f"""
MATCH (g:{_GOAL})-[old:{_GUIDED_BY}]->(p:{_PRINCIPLE})
MERGE (p)-[new:{_SUPPORTS}]->(g)
SET new.weight = coalesce(new.weight, $weight),
    new.essentiality = coalesce(new.essentiality, $essentiality)
DELETE old
RETURN count(old) AS edges_migrated
"""

_SET_TRACKER_KEYS = f"""
MATCH (row:{_TRACKER} {{file_path: $file_path}})
SET row.authored_edges = $authored_edges
RETURN count(row) AS rows_written
"""

_TRACKER_PARAMS = {
    "guides_prefix": f"{_GUIDES_GOAL}|",
    "guided_by_prefix": f"{_GUIDED_BY}|",
}
_WRITE_PARAMS: dict[str, Any] = {  # boundary: neo4j query parameters (float + str)
    "weight": DEFAULT_WEIGHT,
    "essentiality": DEFAULT_ESSENTIALITY,
}


class StrandedEdgesError(Exception):
    """The graph holds a ``GUIDES_GOAL`` edge the re-type would leave behind."""


@dataclass(frozen=True)
class Census:
    """What the graph holds of the two old shapes, the new one, and the trackers."""

    principle_side: list[Row]
    goal_side: list[Row]
    stranded: list[Row]
    supports: list[Row]
    other_guided_by: int
    tracker_rewrites: dict[str, list[str]]

    @property
    def old_edges(self) -> int:
        return len(self.principle_side) + len(self.goal_side)

    @property
    def pairs(self) -> set[tuple[str, str]]:
        return {
            (str(row["principle_uid"]), str(row["goal_uid"]))
            for row in (*self.principle_side, *self.goal_side)
        }


def rewritten_keys(keys: list[str], *, entity_is_goal: bool) -> list[str]:
    """One tracker row's keys with each old shape named as the edge it became.

    A ``GUIDED_BY_PRINCIPLE`` key is rewritten only on a goal's row: on a
    PathStep's row it names an edge that stays. The result is sorted and
    de-duplicated, the form ``authored_edge_fingerprint`` stores.
    """
    rewritten: set[str] = set()
    for key in keys:
        parts = key.split("|", 2)
        if len(parts) != 3:
            rewritten.add(key)
            continue
        rel_type, direction, target_uid = parts
        if rel_type == _GUIDES_GOAL:
            rewritten.add(f"{_SUPPORTS}|{direction}|{target_uid}")
        elif rel_type == _GUIDED_BY and entity_is_goal and direction == "outgoing":
            rewritten.add(f"{_SUPPORTS}|incoming|{target_uid}")
        else:
            rewritten.add(key)
    return sorted(rewritten)


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> Census:
    """Read both old shapes, the new one, and every tracker row naming an old shape."""
    tracker_rows = await _fetch(driver, _TRACKER_ROWS, _TRACKER_PARAMS)
    tracker_rewrites: dict[str, list[str]] = {}
    for row in tracker_rows:
        current = [str(key) for key in row["authored_edges"]]
        rewritten = rewritten_keys(current, entity_is_goal=bool(row["entity_is_goal"]))
        if rewritten != sorted(set(current)):
            tracker_rewrites[str(row["file_path"])] = rewritten
    other = await _fetch(driver, _OTHER_GUIDED_BY_COUNT)
    return Census(
        principle_side=await _fetch(driver, _PRINCIPLE_SIDE_ROWS),
        goal_side=await _fetch(driver, _GOAL_SIDE_ROWS),
        stranded=await _fetch(driver, _STRANDED_GUIDES_GOAL_ROWS),
        supports=await _fetch(driver, _NEW_ROWS),
        other_guided_by=int(other[0]["edges"]) if other else 0,
        tracker_rewrites=tracker_rewrites,
    )


async def migrate(driver: AsyncDriver, found: Census) -> tuple[int, int, int]:
    """Re-type both shapes and rewrite the tracker rows ``found`` lists.

    Returns ``(principle-side edges, goal-side edges, tracker rows)`` written.
    Every statement is safe to repeat, so a run that failed part-way is re-run.
    Refuses, writing nothing, while ``found`` lists a stranded edge.
    """
    if found.stranded:
        raise StrandedEdgesError(
            f"{len(found.stranded)} {_GUIDES_GOAL} edge(s) do not join a principle to a goal"
        )
    principle_side = await _fetch(driver, _RETYPE_PRINCIPLE_SIDE, _WRITE_PARAMS)
    goal_side = await _fetch(driver, _RETYPE_GOAL_SIDE, _WRITE_PARAMS)
    rows_written = 0
    for file_path, keys in found.tracker_rewrites.items():
        written = await _fetch(
            driver, _SET_TRACKER_KEYS, {"file_path": file_path, "authored_edges": keys}
        )
        rows_written += int(written[0]["rows_written"]) if written else 0
    return (
        int(principle_side[0]["edges_migrated"]) if principle_side else 0,
        int(goal_side[0]["edges_migrated"]) if goal_side else 0,
        rows_written,
    )


def _print_census(found: Census) -> None:
    print(f"{_GUIDES_GOAL} (principle → goal): {len(found.principle_side)}")
    for row in found.principle_side:
        print(f"  {row['principle_uid']} → {row['goal_uid']}  {row['props']}")
    print(f"{_GUIDED_BY} (goal → principle): {len(found.goal_side)}")
    for row in found.goal_side:
        print(f"  {row['goal_uid']} → {row['principle_uid']}  {row['props']}")
    print(f"Pairs these hold: {len(found.pairs)}")
    print(f"{_SUPPORTS} (principle → goal) already present: {len(found.supports)}")
    for row in found.supports:
        print(f"  {row['principle_uid']} → {row['goal_uid']}  {row['props']}")
    print(f"{_GUIDED_BY} edges of another shape (untouched): {found.other_guided_by}")
    print(f"Tracker rows to rewrite: {len(found.tracker_rewrites)}")
    for file_path, keys in found.tracker_rewrites.items():
        print(f"  {file_path}")
        for key in keys:
            print(f"    {key}")
    if found.stranded:
        print(f"\n{_GUIDES_GOAL} edges that are NOT principle → goal: {len(found.stranded)}")
        for row in found.stranded:
            print(
                f"  {row['source_uid']} {row['source_labels']} → "
                f"{row['target_uid']} {row['target_labels']}"
            )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Re-type {_GUIDES_GOAL} and goal → principle {_GUIDED_BY} to {_SUPPORTS}"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the re-type (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = await Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        found = await census(driver)
        _print_census(found)

        if found.stranded:
            print(
                f"\nSTOP: {len(found.stranded)} {_GUIDES_GOAL} edge(s) do not join a principle "
                "to a goal. The type leaves the code with this change, so they would be "
                "stranded. Remove each in the graph, then re-run. Nothing was written."
            )
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to re-type.")
            return 0
        if not found.old_edges and not found.tracker_rewrites:
            print("\nNothing to re-type.")
            return 0

        principle_side, goal_side, rows = await migrate(driver, found)
        print(
            f"\nRe-typed {principle_side} principle-side and {goal_side} goal-side edge(s); "
            f"rewrote {rows} tracker row(s)."
        )

        print("\n=== AFTER ===")
        after = await census(driver)
        _print_census(after)
        if after.old_edges or after.tracker_rewrites or after.stranded:
            print("\nFAILED: an old edge or an old tracker key remains.")
            return 1
        missing = found.pairs - {
            (str(row["principle_uid"]), str(row["goal_uid"])) for row in after.supports
        }
        if missing:
            print(f"\nFAILED: {len(missing)} pair(s) lost their link: {sorted(missing)}")
            return 1
        print(f"\nOK: {len(found.pairs)} pair(s) each hold one {_SUPPORTS} edge.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
