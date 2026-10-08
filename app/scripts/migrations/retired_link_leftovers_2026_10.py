#!/usr/bin/env python3
"""
Retired link leftovers — a read-only guard (Activity links arc PR 5)
====================================================================

Two stored shapes are retired (ADR-090 §7, ``docs/roadmap/activity-links-arc.md``):

- ``PRACTICED_AT_EVENT`` is not a ``RelationshipName``. An event demonstrating a principle
  is ``(Event)-[:DEMONSTRATES_PRINCIPLE]->(Principle)``; an event reinforcing a habit is
  ``(Event)-[:REINFORCES_HABIT]->(Habit)``.
- A task's principles are ``(Task)-[:ALIGNED_WITH_PRINCIPLE]->(Principle)`` edges, written
  by task create and update; ``aligned_principle_uids`` is never a node property.

No code writes or reads either shape, so this script converts nothing: it reads, and exits
2 while the graph holds any of

- a ``PRACTICED_AT_EVENT`` edge, of any shape;
- a vault tracker row for an Edge file naming the type
  (``entity_uid`` ``edge:<from>|PRACTICED_AT_EVENT|<to>``) — the row cannot be decoded, so
  deleting the file would leave its edge behind;
- a tracker row whose ``authored_edges`` holds a ``PRACTICED_AT_EVENT|…`` key — it cannot
  be decoded either, so the edge it records would never be retracted;
- a node carrying ``aligned_principle_uids``.

Each is listed, for a person to decide what it becomes. Exit 0 means nothing of either
shape is stored. It never writes.

Run under ``direnv exec .`` so the credentials resolve:

    uv run scripts/migrations/retired_link_leftovers_2026_10.py
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.neo_labels import NeoLabel

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

# The retired type is not a RelationshipName member any more, so it is named as a string.
_PRACTICED = "PRACTICED_AT_EVENT"
_PROPERTY = "aligned_principle_uids"
_TRACKER = NeoLabel.INGESTION_METADATA.value

_EDGES = f"""
MATCH (a)-[r:{_PRACTICED}]->(b)
RETURN a.uid AS source_uid, labels(a) AS source_labels,
       b.uid AS target_uid, labels(b) AS target_labels
ORDER BY source_uid, target_uid
"""

_EDGE_FILE_ROWS = f"""
MATCH (row:{_TRACKER})
WHERE row.entity_uid STARTS WITH 'edge:' AND row.entity_uid CONTAINS $infix
RETURN row.file_path AS file_path, row.entity_uid AS entity_uid
ORDER BY file_path
"""

_TRACKER_KEYS = f"""
MATCH (row:{_TRACKER})
WHERE any(key IN coalesce(row.authored_edges, []) WHERE key STARTS WITH $prefix)
RETURN row.file_path AS file_path,
       [key IN row.authored_edges WHERE key STARTS WITH $prefix] AS keys
ORDER BY file_path
"""

_PROPERTY_NODES = f"""
MATCH (n)
WHERE n.{_PROPERTY} IS NOT NULL
RETURN n.uid AS uid, labels(n) AS labels, n.{_PROPERTY} AS value
ORDER BY uid
"""


@dataclass(frozen=True)
class Census:
    """What the graph still stores of the two retired shapes."""

    edges: list[Row]
    edge_file_rows: list[Row]
    tracker_keys: list[Row]
    property_nodes: list[Row]

    @property
    def clean(self) -> bool:
        return not (self.edges or self.edge_file_rows or self.tracker_keys or self.property_nodes)


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> Census:
    """Read every stored remnant of the two retired shapes."""
    return Census(
        edges=await _fetch(driver, _EDGES),
        edge_file_rows=await _fetch(driver, _EDGE_FILE_ROWS, {"infix": f"|{_PRACTICED}|"}),
        tracker_keys=await _fetch(driver, _TRACKER_KEYS, {"prefix": f"{_PRACTICED}|"}),
        property_nodes=await _fetch(driver, _PROPERTY_NODES),
    )


def _print_census(found: Census) -> None:
    print(f"{_PRACTICED} edges: {len(found.edges)}")
    for row in found.edges:
        print(
            f"  {row['source_uid']} {row['source_labels']} → "
            f"{row['target_uid']} {row['target_labels']}"
        )
    print(f"Edge-file tracker rows naming {_PRACTICED}: {len(found.edge_file_rows)}")
    for row in found.edge_file_rows:
        print(f"  {row['file_path']}  ({row['entity_uid']})")
    print(f"Tracker rows with a {_PRACTICED} key: {len(found.tracker_keys)}")
    for row in found.tracker_keys:
        print(f"  {row['file_path']}  {row['keys']}")
    print(f"Nodes carrying {_PROPERTY}: {len(found.property_nodes)}")
    for row in found.property_nodes:
        print(f"  {row['uid']} {row['labels']}  {row['value']}")


async def main() -> int:
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = await Neo4jConnection().connect()
    try:
        found = await census(driver)
        _print_census(found)
        if not found.clean:
            print(
                "\nSTOP: the graph stores a retired shape the new code no longer reads. "
                "Decide what each listed item becomes before running the new code. "
                "Nothing was written."
            )
            return 2
        print("\nOK: nothing of either retired shape is stored.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
