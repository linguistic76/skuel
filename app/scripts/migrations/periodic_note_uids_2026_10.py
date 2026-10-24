#!/usr/bin/env python3
"""
Periodic-note uids into the grammar
===================================

Renames every periodic note from the colon uid to the one ``periodic_note_uid``
mints, stamps the period its old uid carried into its metadata, and points the
note's tracker row at the new uid:

    (:UserEntry {uid: "ue:{kind}:{user}:{period}"})  →  periodic_note_uid(kind, user, period)
    metadata without ``period_key``                  →  metadata.period_key = period
    (:IngestionMetadata {entity_uid: old uid})       →  entity_uid = the new uid

Each note is renamed in place: its content, embedding and edges stay, so nothing is
re-embedded or re-extracted. The new uid is the one both doors derive — the
calendar routes (``ensure_periodic_note``) and the vault door (from the note's
frontmatter) — so the next open or sync of the same period lands on this node.

What the run establishes, and reads on every run: every periodic note
(``metadata.entry_kind`` a periodic kind, with a ``period_key``) sits at
``periodic_note_uid`` of its kind, owner and period unless its uid is authored;
one note per kind, owner and period; every vault periodic note is named by
exactly one tracker row, the row of its own file; a uid names one node.

The run STOPS (exit 2) before any write while the graph holds something the
rename cannot account for:

- a ``ue:``-prefixed uid outside the old shape ``ue:{kind}:{user}:{period}``;
- an old-shape node that is not exactly ``:Entity:UserEntry``, whose owner
  (``user_uid`` and its one ``OWNS`` edge) is not the uid's, whose
  ``metadata.entry_kind`` is not the uid's kind, or whose ``period_key`` is not
  the uid's period;
- an old-shape note holding a chunk subtree — its chunk uids are derived from the
  note's uid, and this run does not re-mint them;
- a periodic note outside the old shape that is neither at its derived uid nor
  authored, or two periodic notes for one kind, owner and period;
- a new uid any node in the graph already holds, two notes the rename would give
  one uid, or a uid two nodes already hold;
- a tracker row naming an old uid that no note holds, or holds from another file;
  a vault periodic note named by no tracker row, or by more than one;
- any other property, of a node or an edge, holding an old uid — a reference the
  rename would leave naming no node (``submitted_from_uid``, ``subject_uid``, …).

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the
credentials resolve):

1. Stop the app, then merge and pull. Do not open a periodic note or sync a vault
   before step 3: either would create a second, empty note at the new uid beside
   the old one, and the run would stop on the taken uid.
2. Census (no flag); ``--manifest PATH`` writes every rename as JSON.
3. ``--confirm``: one transaction. Each statement matches a note on its old uid
   AND the metadata the census read, and a count that differs from the census
   rolls the transaction back.
4. The script reads the graph again — after a ``--confirm`` that had nothing to
   write too.
5. Boot the app.

Usage:
    uv run scripts/migrations/periodic_note_uids_2026_10.py                  # census
    uv run scripts/migrations/periodic_note_uids_2026_10.py --manifest m.json
    uv run scripts/migrations/periodic_note_uids_2026_10.py --confirm        # rename
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.user_entry.user_entry import PERIODIC_NOTE_KINDS, periodic_note_uid
from core.utils.uid_grammar import AUTHORED_UID, UidVerdict, classify
from scripts.uid_census import closing_census

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

OLD_PREFIX = "ue:"
_OLD_UID = re.compile(r"ue:(?P<kind>[a-z]+):(?P<user>[^:]+):(?P<period>[^:]+)")

_ENTITY = NeoLabel.ENTITY.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_USER = NeoLabel.USER.value
_TRACKER = NeoLabel.INGESTION_METADATA.value
_OWNS = RelationshipName.OWNS.value
_HAS_CONTENT = RelationshipName.HAS_CONTENT.value
_HAS_REFERENCE_CHUNK = RelationshipName.HAS_REFERENCE_CHUNK.value

_NOTE_ROWS = f"""
MATCH (n)
WHERE n.uid STARTS WITH $old_prefix OR n:{_USER_ENTRY}
OPTIONAL MATCH (o:{_USER})-[:{_OWNS}]->(n)
WITH n, collect(o.uid) AS owners
RETURN n.uid AS uid, labels(n) AS labels, n.user_uid AS user_uid,
       n.metadata AS metadata, owners, n.embedding IS NOT NULL AS embedded,
       EXISTS {{ (n)-[:{_HAS_CONTENT}|{_HAS_REFERENCE_CHUNK}]->() }} AS subtree
ORDER BY uid
"""

_TRACKER_ROWS = f"""
MATCH (m:{_TRACKER}) WHERE m.entity_uid IS NOT NULL
RETURN m.file_path AS path, m.entity_uid AS entity_uid
"""

# Every value that names an old uid, outside the note's own uid and its tracker row.
_OLD_UID_VALUE = "ue:(daily|weekly|monthly|quarterly|yearly):[^:]+:[^:]+"

_OLD_REFERENCES = f"""
CALL () {{
    MATCH (n) WHERE NOT n:{_TRACKER}
    UNWIND [k IN keys(n) WHERE k <> 'uid'] AS key
    WITH n, key, n[key] AS value
    WHERE (value IS :: STRING AND value =~ $old_value)
       OR (value IS :: LIST<STRING NOT NULL> AND any(s IN value WHERE s =~ $old_value))
    RETURN 'node ' + coalesce(n.uid, labels(n)[0]) AS holder, key
  UNION ALL
    MATCH ()-[r]->()
    UNWIND keys(r) AS key
    WITH r, key, r[key] AS value
    WHERE (value IS :: STRING AND value =~ $old_value)
       OR (value IS :: LIST<STRING NOT NULL> AND any(s IN value WHERE s =~ $old_value))
    RETURN 'edge ' + type(r) AS holder, key
}}
RETURN holder, key
"""

_ALL_UIDS = "MATCH (n) WHERE n.uid IS NOT NULL RETURN n.uid AS uid"

_SHARED_UIDS = """
MATCH (n) WHERE n.uid IS NOT NULL
WITH n.uid AS uid, count(n) AS holders WHERE holders > 1
RETURN uid, holders ORDER BY uid
"""

_RENAME = f"""
UNWIND $renames AS rename
MATCH (n:{_ENTITY}:{_USER_ENTRY} {{uid: rename.old}})
WHERE n.metadata = rename.metadata_before
SET n.uid = rename.new, n.metadata = rename.metadata_after
RETURN count(n) AS renamed
"""

_REPOINT = f"""
UNWIND $rows AS row
MATCH (m:{_TRACKER} {{file_path: row.path}})
WHERE m.entity_uid = row.old
SET m.entity_uid = row.new
RETURN count(m) AS repointed
"""


@dataclass(frozen=True)
class Rename:
    """One note's move: old uid → new uid, and its metadata before and after."""

    old: str
    new: str
    metadata_before: str
    metadata_after: str


@dataclass(frozen=True)
class Repoint:
    """One tracker row's move onto its note's new uid."""

    path: str
    old: str
    new: str


@dataclass
class Plan:
    """What the run would write, and every reason it must not."""

    renames: list[Rename] = field(default_factory=list)
    repoints: list[Repoint] = field(default_factory=list)
    periodic: int = 0  # periodic notes, by metadata, old shape or new
    at_derived_uid: int = 0  # periodic notes already at periodic_note_uid
    authored: int = 0  # periodic notes on an authored uid
    embedded: int = 0  # periodic notes carrying an embedding
    stops: list[str] = field(default_factory=list)

    @property
    def writes(self) -> int:
        return len(self.renames) + len(self.repoints)


def _metadata(row: Row, plan: Plan) -> dict[str, Any] | None:  # boundary: stored JSON map
    """The note's metadata map; ``None`` (and a stop) when it does not parse."""
    raw = row["metadata"]
    if raw is None:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        plan.stops.append(f"{row['uid']}: metadata is not JSON")
        return None
    if not isinstance(parsed, dict):
        plan.stops.append(f"{row['uid']}: metadata is not a map")
        return None
    return parsed


def plan_notes(rows: list[Row], plan: Plan) -> dict[str, str | None]:
    """Add every old-shape note's rename to ``plan``; return ``{uid: vault file}``.

    The returned map names every periodic note on a derived or authored uid —
    under the uid it holds after the run (the new uid for an old-shape note) —
    with the vault file that wrote it, or ``None`` for a note made in the app, so
    ``plan_tracker`` can pair tracker rows and vault notes both ways.
    """
    notes: dict[str, str | None] = {}
    notes_for: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)
    for row in rows:
        uid = str(row["uid"])
        metadata = _metadata(row, plan)
        if metadata is None:
            continue
        kind = metadata.get("entry_kind")
        old = _OLD_UID.fullmatch(uid) if uid.startswith(OLD_PREFIX) else None
        if uid.startswith(OLD_PREFIX) and (old is None or old["kind"] not in PERIODIC_NOTE_KINDS):
            plan.stops.append(
                f"{uid}: a 'ue:' uid outside the shape ue:{{kind}}:{{user}}:{{period}}"
            )
            continue
        if old is None and kind not in PERIODIC_NOTE_KINDS:
            continue  # not a periodic note
        plan.periodic += 1
        if row["embedded"]:
            plan.embedded += 1
        vault_file = metadata.get("vault_file_path")
        if old is not None:
            new = _plan_rename(row, old, metadata, plan)
            if new is None:
                continue
            notes_for[(old["user"], old["kind"], old["period"])].append(uid)
            notes[new] = str(vault_file) if vault_file else None
            continue
        period = metadata.get("period_key")
        if not period:
            continue  # a vault note without a period field: a minted uid, not derived
        owner = str(row["user_uid"])
        notes_for[(owner, str(kind), str(period))].append(uid)
        if uid == periodic_note_uid(str(kind), owner, str(period)):
            plan.at_derived_uid += 1
        elif AUTHORED_UID.fullmatch(uid):
            plan.authored += 1
        else:
            plan.stops.append(
                f"{uid}: a {kind} note of {owner} for {period}, "
                f"not at its uid {periodic_note_uid(str(kind), owner, str(period))}"
            )
            continue
        notes[uid] = str(vault_file) if vault_file else None
    for (owner, kind, period), uids in sorted(notes_for.items()):
        if len(uids) > 1:
            plan.stops.append(f"{len(uids)} {kind} notes of {owner} for {period}: {sorted(uids)}")
    return notes


def _plan_rename(
    row: Row,
    old: re.Match[str],
    metadata: dict[str, Any],  # boundary: stored JSON map
    plan: Plan,
) -> str | None:
    """Plan one old-shape note's rename; ``None`` (and a stop) when it cannot be."""
    uid = str(row["uid"])
    kind, owner, period = old["kind"], old["user"], old["period"]
    problems = []
    if sorted(row["labels"]) != sorted([_ENTITY, _USER_ENTRY]):
        problems.append(f"labels {sorted(row['labels'])}")
    if row["user_uid"] != owner:
        problems.append(f"user_uid {row['user_uid']!r}")
    if [str(o) for o in row["owners"]] != [owner]:
        problems.append(f"owned by {sorted(str(o) for o in row['owners'])}")
    if metadata.get("entry_kind") != kind:
        problems.append(f"entry_kind {metadata.get('entry_kind')!r}")
    if metadata.get("period_key") not in (None, period):
        problems.append(f"period_key {metadata.get('period_key')!r}")
    if row["subtree"]:
        problems.append("a chunk subtree, whose uids derive from this one")
    if problems:
        plan.stops.append(f"{uid}: {'; '.join(problems)}")
        return None
    new = periodic_note_uid(kind, owner, period)
    after = metadata if "period_key" in metadata else {**metadata, "period_key": period}
    plan.renames.append(
        Rename(
            old=uid,
            new=new,
            metadata_before=str(row["metadata"]),
            metadata_after=json.dumps(after),
        )
    )
    return new


def plan_tracker(rows: list[Row], notes: dict[str, str | None], plan: Plan) -> None:
    """Point every tracker row at its note's new uid; rows and vault notes pair one to one."""
    new_uid_of = {rename.old: rename.new for rename in plan.renames}
    rows_naming: Counter[str] = Counter()
    for row in rows:
        path, named = str(row["path"]), str(row["entity_uid"])
        uid = new_uid_of.get(named, named)
        if named.startswith(OLD_PREFIX) and named not in new_uid_of:
            plan.stops.append(f"tracker row {path} names {named}, which no note it can move holds")
            continue
        if uid not in notes:
            continue  # a row for something other than a periodic note
        rows_naming[uid] += 1
        vault_file = notes[uid]
        if vault_file != path:
            plan.stops.append(f"tracker row {path} names {named}, whose vault file is {vault_file}")
            continue
        if named != uid:
            plan.repoints.append(Repoint(path=path, old=named, new=uid))
    for uid, vault_file in sorted(notes.items()):
        if vault_file is not None and rows_naming[uid] != 1:
            plan.stops.append(
                f"{vault_file} (note {uid}) is named by {rows_naming[uid]} tracker rows"
            )


def plan_references(rows: list[Row], plan: Plan) -> None:
    """Stop on every property, other than a uid or a tracker row's, that names an old uid."""
    for row in rows:
        plan.stops.append(f"{row['holder']}.{row['key']} names an old periodic uid")


def plan_collisions(plan: Plan, held: Counter[str]) -> None:
    """Stop on any uid that would name, or already names, more than one node.

    ``held`` counts the nodes holding each uid in the graph, of any label. A uid
    names one node, so a uid already held twice stops the run, and a new uid must
    be free graph-wide.
    """
    for uid, count in sorted(held.items()):
        if count > 1:
            plan.stops.append(f"{uid} is already held by {count} nodes")
    for new_uid, count in sorted(Counter(rename.new for rename in plan.renames).items()):
        if count > 1:
            plan.stops.append(f"{count} notes would all become {new_uid}")
    for rename in plan.renames:
        if rename.new in held:
            plan.stops.append(f"{rename.new} (for {rename.old}) is already held by a node")


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> Plan:
    """Read every periodic note, every tracker row and every uid, and plan the rename."""
    plan = Plan()
    notes = plan_notes(await _fetch(driver, _NOTE_ROWS, {"old_prefix": OLD_PREFIX}), plan)
    plan_tracker(await _fetch(driver, _TRACKER_ROWS), notes, plan)
    plan_references(await _fetch(driver, _OLD_REFERENCES, {"old_value": _OLD_UID_VALUE}), plan)
    plan_collisions(plan, Counter(str(row["uid"]) for row in await _fetch(driver, _ALL_UIDS)))
    return plan


class CountMismatchError(Exception):
    """A statement inside the transaction wrote a different number of nodes than planned."""


async def migrate(driver: AsyncDriver, plan: Plan) -> tuple[int, int]:
    """Rename every planned note and repoint every planned tracker row, in one transaction.

    Returns ``(notes renamed, tracker rows repointed)``. Raises (writing nothing)
    when the plan has a stop, or when any count inside the transaction differs
    from the plan — the transaction is rolled back.
    """
    if plan.stops:
        raise CountMismatchError(f"{len(plan.stops)} stop(s): the plan is not safe to apply")
    # The transaction commits when the block exits cleanly and rolls back on a raise.
    async with driver.session() as session, await session.begin_transaction() as tx:
        result = await tx.run(
            _RENAME,
            renames=[
                {
                    "old": r.old,
                    "new": r.new,
                    "metadata_before": r.metadata_before,
                    "metadata_after": r.metadata_after,
                }
                for r in plan.renames
            ],
        )
        record = await result.single()
        renamed = int(record["renamed"]) if record else 0
        if renamed != len(plan.renames):
            raise CountMismatchError(f"renamed {renamed} notes, planned {len(plan.renames)}")
        result = await tx.run(
            _REPOINT, rows=[{"path": r.path, "old": r.old, "new": r.new} for r in plan.repoints]
        )
        record = await result.single()
        repointed = int(record["repointed"]) if record else 0
        if repointed != len(plan.repoints):
            raise CountMismatchError(
                f"repointed {repointed} tracker rows, planned {len(plan.repoints)}"
            )
    return renamed, repointed


def manifest(plan: Plan) -> dict[str, Any]:  # boundary: JSON document
    """Every planned write — the record of what ``--confirm`` changes."""
    return {
        "renames": [
            {"old": r.old, "new": r.new, "metadata_after": r.metadata_after} for r in plan.renames
        ],
        "tracker_repoints": [{"path": r.path, "old": r.old, "new": r.new} for r in plan.repoints],
        "stops": plan.stops,
    }


def _print_plan(plan: Plan) -> None:
    stamped = sum(1 for r in plan.renames if r.metadata_before != r.metadata_after)
    print(
        f"Periodic notes: {plan.periodic} ({plan.embedded} embedded) — {len(plan.renames)} to "
        f"rename ({stamped} gain a period_key), {plan.at_derived_uid} already at their uid, "
        f"{plan.authored} on an authored uid"
    )
    for rename in plan.renames[:3]:
        print(f"  {rename.old}  →  {rename.new}")
    print(f"Tracker rows: {len(plan.repoints)} to repoint")
    for repoint in plan.repoints[:3]:
        print(f"  {repoint.path}: {repoint.old}  →  {repoint.new}")
    if plan.stops:
        print(f"\nSTOPS: {len(plan.stops)}")
        for stop in plan.stops:
            print(f"  {stop}")


async def _read_back(driver: AsyncDriver, before: Plan) -> list[str]:
    """Every way the graph differs from what the rename promises; empty when it holds."""
    after = await census(driver)
    failures: list[str] = list(after.stops)
    if after.renames:
        failures.append(f"{len(after.renames)} note(s) still in the old shape")
    if after.repoints:
        failures.append(f"{len(after.repoints)} tracker row(s) still name an old uid")
    if after.periodic != before.periodic:
        failures.append(f"{after.periodic} periodic notes, {before.periodic} before")
    if after.embedded != before.embedded:
        failures.append(f"{after.embedded} periodic notes embedded, {before.embedded} before")
    outside = [
        rename.new for rename in before.renames if classify(rename.new) is not UidVerdict.FITS
    ]
    if outside:
        failures.append(f"{len(outside)} new uid(s) outside the grammar: {outside[:3]}")
    shared = await _fetch(driver, _SHARED_UIDS)
    if shared:
        failures.append(f"{len(shared)} uid(s) held by more than one node: {shared[:3]}")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(description="Rename periodic-note uids into the grammar")
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
            print("\nSTOP: the graph holds notes or tracker rows the rename cannot account for.")
            print("Nothing was written.")
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Stop the app, then re-run with --confirm.")
            return 0
        if plan.writes:
            renamed, repointed = await migrate(driver, plan)
            print(f"\nRenamed {renamed} notes; repointed {repointed} tracker rows.")
        else:
            print("\nNothing to rename.")

        print("\n=== AFTER ===")
        failures = await _read_back(driver, plan)
        if failures:
            print("\nFAILED:")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print("Read-back holds: every periodic note at its uid, every tracker row on it.")
        print((await closing_census(driver)).line)
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
