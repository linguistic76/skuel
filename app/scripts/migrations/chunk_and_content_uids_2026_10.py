#!/usr/bin/env python3
"""
Chunk uids into the grammar; :Content without a uid
=====================================================

Renames every chunk uid of the shape ``{parent}:chunk:{n}`` to the one the chunk
stores mint, and clears the uid a :Content node shares with its entity:

    (:ContentChunk {uid: "{parent}:chunk:{n}"})    →  chunk_uid(CONTENT, parent, n)
    (:ReferenceChunk {uid: "{parent}:chunk:{n}"})  →  chunk_uid(REFERENCE, parent, n)
    (:Content {uid: <its entity's uid>})           →  (:Content)   — no uid

Each chunk is renamed in place: its embedding, text and edges stay, so nothing is
re-embedded. The new uid is minted by ``chunk_uid`` — the same function the chunk
stores call — from the parent the chunk hangs off and the index its old uid
carries, so the next re-chunk of the same body re-creates these uids.

The run STOPS (exit 2) before any write while the graph holds something the
rename cannot account for:

- a chunk with no parent, or more than one;
- an old uid whose prefix is not its parent's uid, or whose index is not the
  ``sequence`` on its parent edge;
- a uid in neither the old shape nor the one ``chunk_uid`` mints for it;
- two chunks the rename would give one uid, or a new uid any node in the graph
  already holds;
- a uid two nodes already hold, other than a :Content node's and its entity's;
- a :Content node held by no entity or by more than one, or whose uid is not
  its entity's;
- an entity holding more than one :Content node — the uid-less MERGE would
  bind every one of them, and its chunks would be written once per Content.

States per chunk: old shape → renamed; already ``chunk_uid`` of its parent and
sequence (a re-chunk since the code changed, or an earlier run) → left alone.
A :Content node with no uid is left alone. So a re-run writes nothing.

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the
credentials resolve):

1. Stop the running app — an embedding event still queued names the old uids,
   and its vectors would be generated and then refused by the store.
2. Census (no flag); ``--manifest PATH`` writes every rename as JSON.
3. ``--confirm``: one transaction. Every rename and every cleared Content uid is
   counted inside it, and a count that differs from the census rolls it back.
4. The script reads the graph again — after a ``--confirm`` that had nothing to
   write too: no chunk uid outside the grammar, no :Content with a uid, no uid on
   two nodes, every embedding still there.
5. Boot the app (it creates the chunk uniqueness constraints).

Usage:
    uv run scripts/migrations/chunk_and_content_uids_2026_10.py                  # census
    uv run scripts/migrations/chunk_and_content_uids_2026_10.py --manifest m.json
    uv run scripts/migrations/chunk_and_content_uids_2026_10.py --confirm        # rename
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.neo_labels import NeoLabel
from core.models.ps_content.content_chunks import ChunkStore, chunk_uid
from core.models.relationship_names import RelationshipName
from core.utils.uid_grammar import UidVerdict, classify
from scripts.uid_census import closing_census

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

_OLD_CHUNK_UID = re.compile(r"(?P<parent>.+):chunk:(?P<index>\d+)")

_CONTENT = NeoLabel.CONTENT.value
_ENTITY = NeoLabel.ENTITY.value
_RESOURCE = NeoLabel.RESOURCE.value
_HAS_CONTENT = RelationshipName.HAS_CONTENT.value
_HAS_CHUNK = RelationshipName.HAS_CHUNK.value
_HAS_REFERENCE_CHUNK = RelationshipName.HAS_REFERENCE_CHUNK.value


@dataclass(frozen=True)
class ChunkLabel:
    """One chunk store: its label, its parent edge, and the store its uids are minted for."""

    store: ChunkStore
    label: str
    parent_pattern: str  # how the chunk ``k`` reaches its parent ``p``

    @property
    def rows_query(self) -> str:
        return f"""
MATCH (k:{self.label})
OPTIONAL MATCH {self.parent_pattern}
WITH k, collect({{parent_uid: p.uid, sequence: r.sequence}}) AS parents
RETURN k.uid AS uid, [x IN parents WHERE x.parent_uid IS NOT NULL] AS parents,
       k.embedding IS NOT NULL AS embedded
ORDER BY uid
"""

    @property
    def rename_query(self) -> str:
        return f"""
UNWIND $renames AS rename
MATCH (k:{self.label} {{uid: rename.old}})
MATCH {self.parent_pattern}
WHERE p.uid = rename.parent
SET k.uid = rename.new
RETURN count(k) AS renamed
"""


CHUNK_LABELS: tuple[ChunkLabel, ...] = (
    ChunkLabel(
        ChunkStore.CONTENT,
        NeoLabel.CONTENT_CHUNK.value,
        f"(p:{_ENTITY})-[:{_HAS_CONTENT}]->(:{_CONTENT})-[r:{_HAS_CHUNK}]->(k)",
    ),
    ChunkLabel(
        ChunkStore.REFERENCE,
        NeoLabel.REFERENCE_CHUNK.value,
        f"(p:{_RESOURCE})-[r:{_HAS_REFERENCE_CHUNK}]->(k)",
    ),
)

_CONTENT_ROWS = f"""
MATCH (c:{_CONTENT})
OPTIONAL MATCH (p:{_ENTITY})-[:{_HAS_CONTENT}]->(c)
WITH c, collect(p.uid) AS holders
RETURN c.uid AS uid, holders
"""

_CLEAR_CONTENT_UIDS = f"""
MATCH (p:{_ENTITY})-[:{_HAS_CONTENT}]->(c:{_CONTENT})
WHERE c.uid IS NOT NULL AND c.uid = p.uid
REMOVE c.uid
RETURN count(c) AS cleared
"""

_ALL_UIDS = f"MATCH (n) WHERE n.uid IS NOT NULL AND NOT n:{_CONTENT} RETURN n.uid AS uid"

_SHARED_UIDS = """
MATCH (n) WHERE n.uid IS NOT NULL
WITH n.uid AS uid, count(n) AS holders WHERE holders > 1
RETURN uid, holders ORDER BY uid
"""


@dataclass(frozen=True)
class Rename:
    """One chunk's move: old uid → new uid, under the parent the census found."""

    old: str
    new: str
    parent: str


@dataclass
class Plan:
    """What the run would write, and every reason it must not."""

    renames: dict[str, list[Rename]] = field(default_factory=dict)  # by chunk label
    already: Counter[str] = field(default_factory=Counter)  # chunks already in the new shape
    embedded: Counter[str] = field(default_factory=Counter)  # chunks carrying an embedding
    content_to_clear: int = 0
    content_clear: int = 0  # Content nodes with no uid already
    stops: list[str] = field(default_factory=list)

    @property
    def writes(self) -> int:
        return sum(len(r) for r in self.renames.values()) + self.content_to_clear


def plan_chunks(label: ChunkLabel, rows: list[Row], plan: Plan) -> None:
    """Add one store's renames to ``plan``; anything unaccounted for is a stop."""
    renames: list[Rename] = []
    for row in rows:
        uid = row["uid"]
        if row["embedded"]:
            plan.embedded[label.label] += 1
        parents = row["parents"]
        if uid is None:
            plan.stops.append(f"{label.label} with no uid")
            continue
        if len(parents) != 1:
            plan.stops.append(f"{label.label} {uid} has {len(parents)} parents")
            continue
        parent_uid, sequence = str(parents[0]["parent_uid"]), parents[0]["sequence"]
        if sequence is not None and uid == chunk_uid(label.store, parent_uid, int(sequence)):
            plan.already[label.label] += 1
            continue
        old = _OLD_CHUNK_UID.fullmatch(uid)
        if old is None:
            plan.stops.append(f"{label.label} {uid} is in neither the old shape nor its new one")
            continue
        if old["parent"] != parent_uid:
            plan.stops.append(f"{label.label} {uid} hangs off {parent_uid}, not its prefix")
            continue
        index = int(old["index"])
        if sequence is None or int(sequence) != index:
            plan.stops.append(f"{label.label} {uid} has sequence {sequence}, not {index}")
            continue
        renames.append(
            Rename(old=uid, new=chunk_uid(label.store, parent_uid, index), parent=parent_uid)
        )
    plan.renames[label.label] = renames


def plan_collisions(plan: Plan, held: Counter[str]) -> None:
    """Stop on any uid that would name, or already names, more than one node.

    ``held`` counts the nodes holding each uid in the graph, of any label, not
    counting :Content nodes (``plan_content`` pairs those with their entity). A
    uid names one node, so a uid already held twice stops the run, and a new chunk
    uid must be free graph-wide, not only among its own label.
    """
    for uid, count in sorted(held.items()):
        if count > 1:
            plan.stops.append(f"{uid} is already held by {count} nodes")
    renames = [rename for label_renames in plan.renames.values() for rename in label_renames]
    for new_uid, count in sorted(Counter(rename.new for rename in renames).items()):
        if count > 1:
            plan.stops.append(f"{count} chunks would all become {new_uid}")
    moving = {rename.old for rename in renames}
    for rename in renames:
        if rename.new in held and rename.new not in moving:
            plan.stops.append(f"{rename.new} (for {rename.old}) is already held by a node")


def plan_content(rows: list[Row], plan: Plan) -> None:
    """Count the Content uids to clear; Content and entities must pair one to one.

    A Content held by no entity or by several, a Content whose uid is not its
    entity's, and an entity holding more than one Content are each a stop.
    """
    held_by: Counter[str] = Counter()
    for row in rows:
        uid, holders = row["uid"], [str(h) for h in row["holders"]]
        held_by.update(holders)
        if len(holders) != 1:
            plan.stops.append(f"{_CONTENT} {uid!r} is held by {len(holders)} entities")
            continue
        if uid is None:
            plan.content_clear += 1
        elif uid == holders[0]:
            plan.content_to_clear += 1
        else:
            plan.stops.append(f"{_CONTENT} {uid!r} is held by {holders[0]}, another uid")
    for holder, count in sorted(held_by.items()):
        if count > 1:
            plan.stops.append(f"{holder} holds {count} {_CONTENT} nodes")


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> Plan:
    """Read every chunk, every :Content node and every uid, and plan the rename."""
    plan = Plan()
    for label in CHUNK_LABELS:
        plan_chunks(label, await _fetch(driver, label.rows_query), plan)
    plan_collisions(plan, Counter(str(row["uid"]) for row in await _fetch(driver, _ALL_UIDS)))
    plan_content(await _fetch(driver, _CONTENT_ROWS), plan)
    return plan


class CountMismatchError(Exception):
    """A statement inside the transaction wrote a different number of nodes than planned."""


async def migrate(driver: AsyncDriver, plan: Plan) -> tuple[dict[str, int], int]:
    """Rename every planned chunk and clear every planned Content uid, in one transaction.

    Returns ``({label: chunks renamed}, Content uids cleared)``. Raises (writing
    nothing) when the plan has a stop, or when any count inside the transaction
    differs from the plan — the transaction is rolled back.
    """
    if plan.stops:
        raise CountMismatchError(f"{len(plan.stops)} stop(s): the plan is not safe to apply")
    renamed: dict[str, int] = {}
    # The transaction commits when the block exits cleanly and rolls back on a raise.
    async with driver.session() as session, await session.begin_transaction() as tx:
        for label in CHUNK_LABELS:
            renames = plan.renames.get(label.label, [])
            if not renames:
                renamed[label.label] = 0
                continue
            result = await tx.run(
                label.rename_query,
                renames=[{"old": r.old, "new": r.new, "parent": r.parent} for r in renames],
            )
            record = await result.single()
            count = int(record["renamed"]) if record else 0
            if count != len(renames):
                raise CountMismatchError(f"{label.label}: renamed {count}, planned {len(renames)}")
            renamed[label.label] = count
        result = await tx.run(_CLEAR_CONTENT_UIDS)
        record = await result.single()
        cleared = int(record["cleared"]) if record else 0
        if cleared != plan.content_to_clear:
            raise CountMismatchError(
                f"{_CONTENT}: cleared {cleared} uids, planned {plan.content_to_clear}"
            )
    return renamed, cleared


def manifest(plan: Plan) -> dict[str, Any]:  # boundary: JSON document
    """Every planned rename, by label — the record of what ``--confirm`` writes."""
    return {
        "renames": {
            label: [{"old": r.old, "new": r.new, "parent": r.parent} for r in renames]
            for label, renames in plan.renames.items()
        },
        "content_uids_to_clear": plan.content_to_clear,
        "stops": plan.stops,
    }


def _print_plan(plan: Plan) -> None:
    for label in CHUNK_LABELS:
        renames = plan.renames.get(label.label, [])
        print(
            f"{label.label}: {len(renames)} to rename, {plan.already[label.label]} already "
            f"in the new shape, {plan.embedded[label.label]} embedded"
        )
        for rename in renames[:3]:
            print(f"  {rename.old}  →  {rename.new}")
    print(f"{_CONTENT}: {plan.content_to_clear} uid(s) to clear, {plan.content_clear} with none")
    if plan.stops:
        print(f"\nSTOPS: {len(plan.stops)}")
        for stop in plan.stops:
            print(f"  {stop}")


async def _read_back(driver: AsyncDriver, before: Plan) -> list[str]:
    """Every way the graph differs from what the rename promises; empty when it holds."""
    after = await census(driver)
    failures: list[str] = list(after.stops)
    for label in CHUNK_LABELS:
        rows = await _fetch(driver, label.rows_query)
        outside = [row["uid"] for row in rows if classify(str(row["uid"])) is not UidVerdict.FITS]
        if outside:
            failures.append(f"{len(outside)} {label.label} uid(s) outside the grammar")
        if after.renames.get(label.label):
            failures.append(f"{label.label}: {len(after.renames[label.label])} still to rename")
        if after.embedded[label.label] != before.embedded[label.label]:
            failures.append(
                f"{label.label}: {after.embedded[label.label]} embedded, "
                f"{before.embedded[label.label]} before"
            )
    if after.content_to_clear:
        failures.append(f"{after.content_to_clear} {_CONTENT} node(s) still carry a uid")
    shared = await _fetch(driver, _SHARED_UIDS)
    if shared:
        failures.append(f"{len(shared)} uid(s) held by more than one node: {shared[:3]}")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rename chunk uids into the grammar and clear :Content uids"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the rename (default is a census: print the plan, change nothing)",
    )
    parser.add_argument(
        "--manifest", type=Path, help="Write every planned rename to this JSON file"
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.graph_driver import UTC_INSTANTS
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    # The uid grammar's record is stamped only after the uid migrations.
    driver = await Neo4jConnection(requires=(UTC_INSTANTS,)).connect()
    try:
        print("=== BEFORE ===")
        plan = await census(driver)
        _print_plan(plan)
        if args.manifest:
            args.manifest.write_text(json.dumps(manifest(plan), indent=1))
            print(f"\nManifest: {args.manifest}")

        if plan.stops:
            print("\nSTOP: the graph holds chunks or Content the rename cannot account for.")
            print("Nothing was written.")
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Stop the app, then re-run with --confirm.")
            return 0
        if plan.writes:
            renamed, cleared = await migrate(driver, plan)
            print(f"\nRenamed {renamed}; cleared {cleared} {_CONTENT} uid(s).")
        else:
            print("\nNothing to rename.")

        print("\n=== AFTER ===")
        failures = await _read_back(driver, plan)
        if failures:
            print("\nFAILED:")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print(
            "\nOK: every chunk uid is in the grammar, no :Content carries a uid, "
            "no uid is on two nodes, every embedding kept."
        )
        print(await closing_census(driver))
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
