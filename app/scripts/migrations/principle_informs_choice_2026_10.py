#!/usr/bin/env python3
"""
A principle informs a choice — GUIDES_CHOICE and INFORMED_BY_PRINCIPLE → INFORMS_CHOICE
========================================================================================

Re-types the two stored shapes of one fact onto the one edge the code now
writes and reads (ADR-090, ``docs/roadmap/activity-links-arc.md`` PR 3):

    (Principle)-[:GUIDES_CHOICE]->(Choice)             written at the principle
    (Choice)-[:INFORMED_BY_PRINCIPLE]->(Principle)     written at the choice
        →  (Principle)-[:INFORMS_CHOICE]->(Choice)

A pair holding either old edge, or both, ends with exactly one new edge. The
states, per (principle, choice) pair:

- **One old edge, or both:** the new edge is MERGEd once and each old edge is
  deleted. Both statements MERGE the same edge, so the second finds the first's.
- **The new edge already there** (a link made by the new code, or an earlier
  partial run): MERGE matches it and it is kept as it is.
- **A re-run:** no old edge matches, nothing is written.
- ``alignment_score`` (the choice door's old property) is not carried: no live
  reader of it exists, and the new edge carries no property.

Both types leave the enum with this change, so nothing of either may be left
behind. The run STOPS (exit 2) before any write while the graph holds:

- a ``GUIDES_CHOICE`` edge that is not Principle → Choice, or an
  ``INFORMED_BY_PRINCIPLE`` edge that is not Choice → Principle — it would be
  stranded; a person removes each one;
- a vault tracker row for an Edge file (``entity_uid`` ``edge:<from>|<TYPE>|<to>``)
  naming either type — the Edge file must be rewritten by hand to
  ``INFORMS_CHOICE`` (from the principle, to the choice); a rewritten row would
  not match the file's next ingest.

Edges between other kinds that already carry ``INFORMS_CHOICE`` (a habit's, a
PathStep's ``choice_uids``) are not touched.

The vault trackers move with the edges. A file's ``:IngestionMetadata`` row
records the edges its frontmatter authored as ``{type}|{direction}|{uid}``
keys, and a later ingest retracts ``prior - current``. A key naming a type the
enum no longer has cannot be decoded, so the edge it recorded would never be
retracted. Each key is rewritten to the edge it now names:

    GUIDES_CHOICE|outgoing|<choice>              → INFORMS_CHOICE|outgoing|<choice>
    GUIDES_CHOICE|incoming|<principle>           → INFORMS_CHOICE|incoming|<principle>
    INFORMED_BY_PRINCIPLE|outgoing|<principle>   → INFORMS_CHOICE|incoming|<principle>
    INFORMED_BY_PRINCIPLE|incoming|<choice>      → INFORMS_CHOICE|outgoing|<choice>

Only the third occurs from a frontmatter field (a choice's former
``connections.guided_by_principle``); the others are covered so no key of a
retired type survives.

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the
credentials resolve):

1. Stop the running app.
2. If a vault file still declares ``connections.guided_by_principle`` (a choice
   file), rename it to ``connections.informing_principles``. Do NOT sync a file
   that still declares the retired field: once it is re-ingested it declares no
   principle link, and the retraction deletes the edge its tracker row records.
3. Census (no flag), then ``--confirm``.
4. ``./dev vault-sync --vault content`` if a file was edited; its fingerprint
   equals the rewritten row, so nothing is retracted.
5. Census again: 0 old edges, 0 old keys.

Usage:
    uv run scripts/migrations/principle_informs_choice_2026_10.py            # census
    uv run scripts/migrations/principle_informs_choice_2026_10.py --confirm  # re-type
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

# Neither old type is a RelationshipName member any more, so both are named as strings.
_GUIDES_CHOICE = "GUIDES_CHOICE"
_INFORMED_BY = "INFORMED_BY_PRINCIPLE"
_INFORMS = RelationshipName.INFORMS_CHOICE.value
_PRINCIPLE = NeoLabel.PRINCIPLE.value
_CHOICE = NeoLabel.CHOICE.value
_TRACKER = NeoLabel.INGESTION_METADATA.value

_EDGE_ROW_PREFIX = "edge:"

# --- census ---------------------------------------------------------------

_PRINCIPLE_SIDE_ROWS = f"""
MATCH (p:{_PRINCIPLE})-[old:{_GUIDES_CHOICE}]->(c:{_CHOICE})
RETURN p.uid AS principle_uid, c.uid AS choice_uid, properties(old) AS props
ORDER BY principle_uid, choice_uid
"""

_CHOICE_SIDE_ROWS = f"""
MATCH (c:{_CHOICE})-[old:{_INFORMED_BY}]->(p:{_PRINCIPLE})
RETURN p.uid AS principle_uid, c.uid AS choice_uid, properties(old) AS props
ORDER BY principle_uid, choice_uid
"""

_STRANDED_ROWS = f"""
MATCH (a)-[old:{_GUIDES_CHOICE}|{_INFORMED_BY}]->(b)
WHERE (type(old) = $guides AND NOT (a:{_PRINCIPLE} AND b:{_CHOICE}))
   OR (type(old) = $informed_by AND NOT (a:{_CHOICE} AND b:{_PRINCIPLE}))
RETURN type(old) AS rel_type, a.uid AS source_uid, labels(a) AS source_labels,
       b.uid AS target_uid, labels(b) AS target_labels
ORDER BY rel_type, source_uid, target_uid
"""

_NEW_ROWS = f"""
MATCH (p:{_PRINCIPLE})-[new:{_INFORMS}]->(c:{_CHOICE})
RETURN p.uid AS principle_uid, c.uid AS choice_uid, properties(new) AS props
ORDER BY principle_uid, choice_uid
"""

_EDGE_FILE_ROWS = f"""
MATCH (row:{_TRACKER})
WHERE row.entity_uid STARTS WITH $edge_prefix
  AND (row.entity_uid CONTAINS $guides_infix OR row.entity_uid CONTAINS $informed_by_infix)
RETURN row.file_path AS file_path, row.entity_uid AS entity_uid
ORDER BY file_path
"""

_TRACKER_ROWS = f"""
MATCH (row:{_TRACKER})
WHERE any(key IN coalesce(row.authored_edges, [])
          WHERE key STARTS WITH $guides_prefix OR key STARTS WITH $informed_by_prefix)
RETURN row.file_path AS file_path, row.entity_uid AS entity_uid,
       row.authored_edges AS authored_edges
ORDER BY file_path
"""

# --- write ----------------------------------------------------------------

_RETYPE_PRINCIPLE_SIDE = f"""
MATCH (p:{_PRINCIPLE})-[old:{_GUIDES_CHOICE}]->(c:{_CHOICE})
MERGE (p)-[:{_INFORMS}]->(c)
DELETE old
RETURN count(old) AS edges_migrated
"""

_RETYPE_CHOICE_SIDE = f"""
MATCH (c:{_CHOICE})-[old:{_INFORMED_BY}]->(p:{_PRINCIPLE})
MERGE (p)-[:{_INFORMS}]->(c)
DELETE old
RETURN count(old) AS edges_migrated
"""

_SET_TRACKER_KEYS = f"""
MATCH (row:{_TRACKER} {{file_path: $file_path}})
SET row.authored_edges = $authored_edges
RETURN count(row) AS rows_written
"""

_STRANDED_PARAMS = {"guides": _GUIDES_CHOICE, "informed_by": _INFORMED_BY}
_EDGE_FILE_PARAMS = {
    "edge_prefix": _EDGE_ROW_PREFIX,
    "guides_infix": f"|{_GUIDES_CHOICE}|",
    "informed_by_infix": f"|{_INFORMED_BY}|",
}
_TRACKER_PARAMS = {
    "guides_prefix": f"{_GUIDES_CHOICE}|",
    "informed_by_prefix": f"{_INFORMED_BY}|",
}

# Each old (type, direction) and the INFORMS_CHOICE direction it becomes. The choice
# side's edge pointed choice → principle, so its direction flips.
_KEY_REWRITES: dict[tuple[str, str], str] = {
    (_GUIDES_CHOICE, "outgoing"): "outgoing",
    (_GUIDES_CHOICE, "incoming"): "incoming",
    (_INFORMED_BY, "outgoing"): "incoming",
    (_INFORMED_BY, "incoming"): "outgoing",
}


class StrandedEdgesError(Exception):
    """The graph holds an old edge or Edge-file row the re-type would leave behind."""


@dataclass(frozen=True)
class Census:
    """What the graph holds of the two old shapes, the new one, and the trackers."""

    principle_side: list[Row]
    choice_side: list[Row]
    stranded: list[Row]
    edge_file_rows: list[Row]
    informs: list[Row]
    tracker_rewrites: dict[str, list[str]]

    @property
    def old_edges(self) -> int:
        return len(self.principle_side) + len(self.choice_side)

    @property
    def blocked(self) -> bool:
        """True while something only a person can fix would be left behind."""
        return bool(self.stranded or self.edge_file_rows)

    @property
    def pairs(self) -> set[tuple[str, str]]:
        return {
            (str(row["principle_uid"]), str(row["choice_uid"]))
            for row in (*self.principle_side, *self.choice_side)
        }


def rewritten_keys(keys: list[str]) -> list[str]:
    """One tracker row's keys with each old shape named as the edge it became.

    The result is sorted and de-duplicated, the form ``authored_edge_fingerprint``
    stores. A key that is not ``type|direction|uid`` passes through unchanged.
    """
    rewritten: set[str] = set()
    for key in keys:
        parts = key.split("|", 2)
        if len(parts) != 3:
            rewritten.add(key)
            continue
        rel_type, direction, target_uid = parts
        new_direction = _KEY_REWRITES.get((rel_type, direction))
        if new_direction is None:
            rewritten.add(key)
        else:
            rewritten.add(f"{_INFORMS}|{new_direction}|{target_uid}")
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
        rewritten = rewritten_keys(current)
        if rewritten != sorted(set(current)):
            tracker_rewrites[str(row["file_path"])] = rewritten
    return Census(
        principle_side=await _fetch(driver, _PRINCIPLE_SIDE_ROWS),
        choice_side=await _fetch(driver, _CHOICE_SIDE_ROWS),
        stranded=await _fetch(driver, _STRANDED_ROWS, _STRANDED_PARAMS),
        edge_file_rows=await _fetch(driver, _EDGE_FILE_ROWS, _EDGE_FILE_PARAMS),
        informs=await _fetch(driver, _NEW_ROWS),
        tracker_rewrites=tracker_rewrites,
    )


async def migrate(driver: AsyncDriver, found: Census) -> tuple[int, int, int]:
    """Re-type both shapes and rewrite the tracker rows ``found`` lists.

    Returns ``(principle-side edges, choice-side edges, tracker rows)`` written.
    Every statement is safe to repeat, so a run that failed part-way is re-run.
    Refuses, writing nothing, while ``found`` lists a stranded edge or Edge-file row.
    """
    if found.blocked:
        raise StrandedEdgesError(
            f"{len(found.stranded)} stranded edge(s) and {len(found.edge_file_rows)} "
            f"Edge-file row(s) name {_GUIDES_CHOICE} or {_INFORMED_BY}"
        )
    principle_side = await _fetch(driver, _RETYPE_PRINCIPLE_SIDE)
    choice_side = await _fetch(driver, _RETYPE_CHOICE_SIDE)
    rows_written = 0
    for file_path, keys in found.tracker_rewrites.items():
        written = await _fetch(
            driver, _SET_TRACKER_KEYS, {"file_path": file_path, "authored_edges": keys}
        )
        rows_written += int(written[0]["rows_written"]) if written else 0
    return (
        int(principle_side[0]["edges_migrated"]) if principle_side else 0,
        int(choice_side[0]["edges_migrated"]) if choice_side else 0,
        rows_written,
    )


def _print_census(found: Census) -> None:
    print(f"{_GUIDES_CHOICE} (principle → choice): {len(found.principle_side)}")
    for row in found.principle_side:
        print(f"  {row['principle_uid']} → {row['choice_uid']}  {row['props']}")
    print(f"{_INFORMED_BY} (choice → principle): {len(found.choice_side)}")
    for row in found.choice_side:
        print(f"  {row['choice_uid']} → {row['principle_uid']}  {row['props']}")
    print(f"Pairs these hold: {len(found.pairs)}")
    print(f"{_INFORMS} (principle → choice) already present: {len(found.informs)}")
    for row in found.informs:
        print(f"  {row['principle_uid']} → {row['choice_uid']}  {row['props']}")
    print(f"Tracker rows to rewrite: {len(found.tracker_rewrites)}")
    for file_path, keys in found.tracker_rewrites.items():
        print(f"  {file_path}")
        for key in keys:
            print(f"    {key}")
    if found.stranded:
        print(f"\nOld edges that do NOT join a principle and a choice: {len(found.stranded)}")
        for row in found.stranded:
            print(
                f"  {row['rel_type']}: {row['source_uid']} {row['source_labels']} → "
                f"{row['target_uid']} {row['target_labels']}"
            )
    if found.edge_file_rows:
        print(f"\nEdge-file tracker rows naming an old type: {len(found.edge_file_rows)}")
        for row in found.edge_file_rows:
            print(f"  {row['file_path']}  ({row['entity_uid']})")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Re-type {_GUIDES_CHOICE} and {_INFORMED_BY} to {_INFORMS}"
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

        if found.blocked:
            print(
                f"\nSTOP: the graph holds {_GUIDES_CHOICE} / {_INFORMED_BY} that the re-type "
                "would leave behind. Both types leave the code with this change. Remove each "
                "stranded edge, and rewrite each Edge file to "
                f"{_INFORMS} (from the principle, to the choice), then re-run. "
                "Nothing was written."
            )
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to re-type.")
            return 0
        if not found.old_edges and not found.tracker_rewrites:
            print("\nNothing to re-type.")
            return 0

        principle_side, choice_side, rows = await migrate(driver, found)
        print(
            f"\nRe-typed {principle_side} principle-side and {choice_side} choice-side "
            f"edge(s); rewrote {rows} tracker row(s)."
        )

        print("\n=== AFTER ===")
        after = await census(driver)
        _print_census(after)
        if after.old_edges or after.tracker_rewrites or after.blocked:
            print("\nFAILED: an old edge or an old tracker key remains.")
            return 1
        missing = found.pairs - {
            (str(row["principle_uid"]), str(row["choice_uid"])) for row in after.informs
        }
        if missing:
            print(f"\nFAILED: {len(missing)} pair(s) lost their link: {sorted(missing)}")
            return 1
        print(f"\nOK: {len(found.pairs)} pair(s) each hold one {_INFORMS} edge.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
