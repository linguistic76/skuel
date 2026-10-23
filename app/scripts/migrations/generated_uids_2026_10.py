#!/usr/bin/env python3
"""
Every generated uid into the one shape
======================================

Renames every node uid outside the uid grammar — a generated uid not
``{prefix}_{16 hex}``, a composite, a bare UUID — in place, and rewrites every
value in the graph that names one:

    a random-born uid  (task_a1b2c3d4, auth_<32 hex>, uuid)  →  hashed_uid(prefix, old uid)
    the default group  (group_default_{teacher})              →  default_group_uid(teacher),
                                                                  is_default = true
    a property naming a renamed uid (a string, a list element,
    or a string inside a JSON map)                            →  the new uid
    a ContentChunk of a renamed entity                        →  chunk_uid(content, new uid,
                                                                  start_index)

A random-born uid's new uid is a hash of its old one, so every run of the census
plans the same names. The default group's is the uid ``default_group_uid``
derives, so the enrollment MERGE finds it. A uid a ``UID_EXEMPTIONS`` entry names
(``user_{username}``, ``invoice:{uuid}``) is left as it is, and so is every
:User's — user uids are unruled; one in no shape is reported. Each node keeps its
labels, properties, embedding and edges.

What the run establishes, and reads on every run: every node uid but a user's
fits the grammar or has an exempt shape; a uid names one node, in any label; no node or
edge property names a retired uid, except the two that quote one as text
(``QUOTING_PROPERTIES``, left as written); every ContentChunk sits at
``chunk_uid(content, holder, start_index)`` of the one entity holding its
Content; each teacher's default group sits at ``default_group_uid`` of its one
owner with ``is_default = true``, and no other group carries ``is_default``.

The run STOPS (exit 2) before any write while the graph holds something the
rename cannot account for:

- a uid outside the grammar and every exemption with no prefix to keep
  (``{prefix}_…`` / ``{prefix}.…`` / ``{prefix}:…``, or a label with a fixed
  prefix), or one
  label whose uids would take two prefixes;
- a ``group_default_`` uid that is not ``group_default_`` + its one owner's
  uid; a group carrying ``is_default`` that is not a default group;
- a ContentChunk that is not under exactly one Content held by exactly one
  entity, or not at ``chunk_uid`` of that entity, its index and the content
  store; a renamed node holding reference chunks;
- a new uid any node already holds, two nodes the run would give one uid, or a
  uid two nodes already hold;
- a value naming a renamed uid any other way — inside a longer string that is
  not a JSON map, or in a JSON property that does not read back to its own text
  — outside ``QUOTING_PROPERTIES``; a tracker row's edge identity or
  authored-edge key naming one is what its vault file declares, so the stop names
  the file to edit.

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the
credentials resolve):

1. Stop the app and any vault-sync or backfill script, and take an Aura
   on-demand snapshot. Then merge and pull. Do not boot the app before step 4:
   its first enrollment would MERGE a second default group at the new uid, and
   the run would stop on the taken uid.
2. Census (no flag); ``--manifest PATH`` writes every planned write as JSON.
3. ``--confirm``: one transaction. Each statement matches its node or edge by
   element id AND the value the census read; a count that differs from the plan
   rolls the transaction back.
4. The script reads the graph again — after a ``--confirm`` that had nothing to
   write too. Then boot the app.

Usage:
    uv run scripts/migrations/generated_uids_2026_10.py                  # census
    uv run scripts/migrations/generated_uids_2026_10.py --manifest m.json
    uv run scripts/migrations/generated_uids_2026_10.py --confirm        # rename
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
from core.models.group.group import default_group_uid
from core.models.ps_content.content_chunks import ChunkStore, chunk_uid
from core.models.relationship_names import RelationshipName
from core.utils.uid_grammar import UID_PREFIX, UidVerdict, classify, exemptions_for, hashed_uid

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record
# A property value the run reads or writes: a string or a list of strings.
type Value = str | list[str]

OLD_DEFAULT_GROUP_PREFIX = "group_default_"

_ENTITY = NeoLabel.ENTITY.value
_USER = NeoLabel.USER.value
_TRACKER = NeoLabel.INGESTION_METADATA.value
_GROUP = NeoLabel.GROUP.value
_CONTENT = NeoLabel.CONTENT.value
_CONTENT_CHUNK = NeoLabel.CONTENT_CHUNK.value
_OWNS = RelationshipName.OWNS.value
_HAS_CONTENT = RelationshipName.HAS_CONTENT.value
_HAS_CHUNK = RelationshipName.HAS_CHUNK.value
_HAS_REFERENCE_CHUNK = RelationshipName.HAS_REFERENCE_CHUNK.value

#: Labels whose uids carry no prefix to keep, with the prefix their writer mints.
FIXED_PREFIXES: dict[str, str] = {NeoLabel.SEARCH_EVENT.value: "search"}

#: ``(label, property)`` pairs whose text may quote a uid — a reply's prose, a
#: file's path. The run leaves them as written and reports what they quote.
QUOTING_PROPERTIES: frozenset[tuple[str, str]] = frozenset(
    {
        (NeoLabel.CONVERSATION_MESSAGE.value, "content"),
        (NeoLabel.ENTRY_REPORT.value, "report_file_path"),
    }
)

_UID_ROWS = f"""
MATCH (n) WHERE n.uid IS NOT NULL
OPTIONAL MATCH (o:{_USER})-[:{_OWNS}]->(n)
WITH n, collect(o.uid) AS owners
RETURN elementId(n) AS id, n.uid AS uid, labels(n) AS labels, owners,
       n.is_default AS is_default, n.embedding IS NOT NULL AS embedded,
       EXISTS {{ (n)-[:{_HAS_REFERENCE_CHUNK}]->() }} AS reference_chunks
"""

_CHUNK_ROWS = f"""
MATCH (chunk:{_CONTENT_CHUNK})
OPTIONAL MATCH (content)-[:{_HAS_CHUNK}]->(chunk)
OPTIONAL MATCH (holder)-[:{_HAS_CONTENT}]->(content)
WITH chunk, collect(DISTINCT content) AS contents, collect(DISTINCT holder) AS holders
RETURN chunk.uid AS uid, chunk.start_index AS start_index,
       [c IN contents | labels(c)] AS content_labels,
       [h IN holders | h.uid] AS holder_uids
"""

# Every property but a node's own uid and its vectors, of every node and edge.
_NODE_VALUES = """
MATCH (n)
RETURN elementId(n) AS id, labels(n) AS labels,
       [k IN keys(n) WHERE k <> 'uid' AND NOT k STARTS WITH 'embedding' | [k, n[k]]] AS props
"""

_EDGE_VALUES = """
MATCH ()-[r]->()
WHERE size(keys(r)) > 0
RETURN elementId(r) AS id, type(r) AS type, [k IN keys(r) | [k, r[k]]] AS props
"""

_RENAME = """
UNWIND $rows AS row
MATCH (n) WHERE elementId(n) = row.id AND n.uid = row.old
SET n.uid = row.new
SET n.is_default = CASE WHEN row.default_group THEN true ELSE n.is_default END
RETURN count(n) AS written
"""

_REMINT_CHUNKS = f"""
UNWIND $rows AS row
MATCH (chunk:{_CONTENT_CHUNK} {{uid: row.old}})
SET chunk.uid = row.new
RETURN count(chunk) AS written
"""

_REWRITE_NODE_VALUES = """
UNWIND $rows AS row
MATCH (n) WHERE elementId(n) = row.id AND n[row.key] = row.before
SET n += row.patch
RETURN count(n) AS written
"""

_REWRITE_EDGE_VALUES = """
UNWIND $rows AS row
MATCH ()-[r]->() WHERE elementId(r) = row.id AND r[row.key] = row.before
SET r += row.patch
RETURN count(r) AS written
"""

_EMBEDDED_AT = """
UNWIND $ids AS id
MATCH (n) WHERE elementId(n) = id AND n.embedding IS NOT NULL
RETURN count(n) AS embedded
"""


@dataclass(frozen=True)
class Rename:
    """One node's move: old uid → new uid (and, for a default group, ``is_default``)."""

    node_id: str
    label: str
    old: str
    new: str
    default_group: bool = False


@dataclass(frozen=True)
class ChunkRemint:
    """One ContentChunk's move onto the uid its renamed holder derives."""

    old: str
    new: str


@dataclass(frozen=True)
class Rewrite:
    """One property value naming a renamed uid, before and after."""

    target: str  # "node" or "edge"
    element_id: str
    holder: str  # the node's labels or the edge's type, for the report
    key: str
    before: Value
    after: Value


@dataclass
class Plan:
    """What the run would write, and every reason it must not."""

    renames: list[Rename] = field(default_factory=list)
    chunks: list[ChunkRemint] = field(default_factory=list)
    rewrites: list[Rewrite] = field(default_factory=list)
    quoted: Counter[str] = field(default_factory=Counter)  # "Label.key" quoting a renamed uid
    left_exempt: Counter[str] = field(default_factory=Counter)  # exemption name → nodes
    users_outside: list[str] = field(default_factory=list)  # user uids in no shape, left
    embedded: int = 0  # renamed nodes carrying an embedding
    stops: list[str] = field(default_factory=list)

    @property
    def writes(self) -> int:
        return len(self.renames) + len(self.chunks) + len(self.rewrites)

    def new_uid_of(self) -> dict[str, str]:
        """Every renamed uid → its new uid, nodes and chunks alike."""
        return {r.old: r.new for r in self.renames} | {c.old: c.new for c in self.chunks}


def _label_of(labels: list[str]) -> str:
    """The labels a node is reported under: every label but ``Entity``, joined."""
    return ":".join(sorted(label for label in labels if label != _ENTITY)) or _ENTITY


def _prefix_of(uid: str, label: str) -> str | None:
    """The prefix a renamed uid keeps: its label's fixed one, or the word it starts with."""
    if label in FIXED_PREFIXES:
        return FIXED_PREFIXES[label]
    match = re.match(r"([a-z][a-z0-9]*)[._:]", uid)
    return match.group(1) if match and UID_PREFIX.fullmatch(match.group(1)) else None


def plan_renames(rows: list[Row], plan: Plan) -> None:
    """Plan every node's rename whose uid is outside the grammar and every exemption."""
    prefixes: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        uid, labels = str(row["uid"]), [str(label) for label in row["labels"]]
        label = _label_of(labels)
        if _GROUP in labels:
            _check_default_flag(row, plan)
        if classify(uid) is UidVerdict.FITS:
            continue
        exempt = exemptions_for(uid)
        if exempt:
            for exemption in exempt:
                plan.left_exempt[exemption.name] += 1
            continue
        if _USER in labels:
            plan.users_outside.append(uid)
            continue
        if row["reference_chunks"]:
            plan.stops.append(f"{uid}: holds reference chunks, whose uids derive from this one")
            continue
        if _GROUP in labels and uid.startswith(OLD_DEFAULT_GROUP_PREFIX):
            new = _plan_default_group(row, plan)
            if new is None:
                continue
            plan.renames.append(Rename(str(row["id"]), label, uid, new, default_group=True))
        else:
            prefix = _prefix_of(uid, label)
            if prefix is None:
                plan.stops.append(f"{label} {uid}: no prefix to keep")
                continue
            prefixes[label].add(prefix)
            plan.renames.append(Rename(str(row["id"]), label, uid, hashed_uid(prefix, uid)))
        if row["embedded"]:
            plan.embedded += 1
    for label, seen in sorted(prefixes.items()):
        if len(seen) > 1:
            plan.stops.append(f"{label}: uids would take {len(seen)} prefixes {sorted(seen)}")


def _check_default_flag(row: Row, plan: Plan) -> None:
    """Stop unless ``is_default = true`` marks exactly the default groups.

    A default group is a group at ``default_group_uid`` of its one owner — or, on
    the graph before the run, at ``group_default_`` + that owner.
    """
    uid, owners = str(row["uid"]), [str(owner) for owner in row["owners"]]
    at_derived = len(owners) == 1 and uid == default_group_uid(owners[0])
    old_shape = uid.startswith(OLD_DEFAULT_GROUP_PREFIX)
    if row["is_default"] is True and not (at_derived or old_shape):
        plan.stops.append(f"group {uid}: is_default on a group that is no teacher's default")
    if at_derived and row["is_default"] is not True:
        plan.stops.append(f"group {uid}: a default group without is_default")


def _plan_default_group(row: Row, plan: Plan) -> str | None:
    """The new uid of an old-shape default group; ``None`` (and a stop) when it has none."""
    uid, owners = str(row["uid"]), [str(owner) for owner in row["owners"]]
    if len(owners) != 1:
        plan.stops.append(f"default group {uid}: owned by {sorted(owners)}, not one teacher")
        return None
    if uid != f"{OLD_DEFAULT_GROUP_PREFIX}{owners[0]}":
        plan.stops.append(f"default group {uid}: its owner is {owners[0]}")
        return None
    return default_group_uid(owners[0])


def plan_chunks(rows: list[Row], plan: Plan) -> None:
    """Re-mint every chunk of a renamed holder; stop on any chunk off its derived uid."""
    new_uid_of = {r.old: r.new for r in plan.renames}
    for row in rows:
        uid = str(row["uid"])
        holders = [str(h) for h in row["holder_uids"]]
        content_labels = row["content_labels"]
        if len(content_labels) != 1 or len(holders) != 1:
            plan.stops.append(
                f"chunk {uid}: under {len(content_labels)} Content, held by {sorted(holders)}"
            )
            continue
        if sorted(content_labels[0]) != [_CONTENT]:
            plan.stops.append(f"chunk {uid}: its Content is labelled {sorted(content_labels[0])}")
            continue
        if row["start_index"] is None:
            plan.stops.append(f"chunk {uid}: no start_index")
            continue
        holder, index = holders[0], int(row["start_index"])
        if uid != chunk_uid(ChunkStore.CONTENT, holder, index):
            plan.stops.append(f"chunk {uid}: not chunk_uid of {holder} at index {index}")
            continue
        if holder in new_uid_of:
            plan.chunks.append(
                ChunkRemint(uid, chunk_uid(ChunkStore.CONTENT, new_uid_of[holder], index))
            )


def _uid_pattern(uids: set[str] | dict[str, str]) -> re.Pattern[str]:
    """Any of ``uids`` as a whole token — not inside a longer uid.

    A uid's characters are ``[a-z0-9._-]``; anything else around one — the ``:``
    of an ``edge:`` tracker identity, a ``|``, a ``/``, a space — bounds it.
    """
    alternatives = "|".join(re.escape(uid) for uid in sorted(uids, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9._-])(?:{alternatives})(?![a-z0-9._-])")


def _json_values(parsed: object, new_uid_of: dict[str, str]) -> object:
    """``parsed`` with every string value that is a renamed uid replaced by its new uid."""
    if isinstance(parsed, str):
        return new_uid_of.get(parsed, parsed)
    if isinstance(parsed, list):
        return [_json_values(item, new_uid_of) for item in parsed]
    if isinstance(parsed, dict):
        return {key: _json_values(value, new_uid_of) for key, value in parsed.items()}
    return parsed


def rewrite_of(
    value: object, new_uid_of: dict[str, str], names: re.Pattern[str]
) -> tuple[str, Value | None]:
    """How the run treats one property value, and the value it writes.

    ``("untouched", None)`` — it names no renamed uid. ``("rewrite", new)`` — every
    renamed uid it names is a whole value: the string, a list element, or a
    string inside a JSON map or list that reads back to its own text.
    ``("quotes", None)`` — it names one inside other text.
    """
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value) or not any(
            names.search(item) for item in value
        ):
            return "untouched", None
        if any(item not in new_uid_of and names.search(item) for item in value):
            return "quotes", None
        return "rewrite", [new_uid_of.get(item, item) for item in value]
    if not isinstance(value, str) or not names.search(value):
        return "untouched", None
    if value in new_uid_of:
        return "rewrite", new_uid_of[value]
    if value.startswith(("{", "[")):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return "quotes", None
        rewritten = json.dumps(_json_values(parsed, new_uid_of))
        if json.dumps(parsed) == value and not names.search(rewritten):
            return "rewrite", rewritten
    return "quotes", None


def _quotes_by_design(target: str, row: Row, key: str) -> bool:
    return target == "node" and any((label, key) in QUOTING_PROPERTIES for label in row["labels"])


def _holder(target: str, row: Row) -> str:
    return _label_of(row["labels"]) if target == "node" else str(row["type"])


def plan_rewrites(target: str, rows: list[Row], plan: Plan) -> None:
    """Plan every property value naming a renamed uid; stop on one the run cannot rewrite."""
    new_uid_of = plan.new_uid_of()
    if not new_uid_of:
        return
    names = _uid_pattern(new_uid_of)
    for row in rows:
        for key, value in row["props"]:
            verdict, after = rewrite_of(value, new_uid_of, names)
            where = f"{_holder(target, row)}.{key}"
            if verdict == "rewrite" and after is not None:
                plan.rewrites.append(
                    Rewrite(target, str(row["id"]), _holder(target, row), str(key), value, after)
                )
            elif verdict == "quotes" and _quotes_by_design(target, row, str(key)):
                plan.quoted[where] += 1
            elif verdict == "quotes" and target == "node" and _TRACKER in row["labels"]:
                # An edge identity and an authored-edge key are what a vault file
                # declares: the file names the uid, and the run edits no file.
                path = dict(row["props"]).get("file_path")
                plan.stops.append(
                    f"tracker row {path}: its file names a renamed uid ({key}) — "
                    "edit the file to the new uid first"
                )
            elif verdict == "quotes":
                plan.stops.append(f"{target} {where} names a renamed uid inside other text")


def plan_collisions(plan: Plan, held: Counter[str]) -> None:
    """Stop on any uid that would name, or already names, more than one node.

    ``held`` counts the nodes holding each uid, in any label. A uid names one
    node, so a uid already held twice stops the run, and a new uid must be free
    graph-wide and planned once.
    """
    for uid, count in sorted(held.items()):
        if count > 1:
            plan.stops.append(f"{uid} is already held by {count} nodes")
    moves = [(r.old, r.new) for r in plan.renames] + [(c.old, c.new) for c in plan.chunks]
    for new_uid, count in sorted(Counter(new for _, new in moves).items()):
        if count > 1:
            plan.stops.append(f"{count} nodes would all become {new_uid}")
    for old, new in moves:
        if new in held:
            plan.stops.append(f"{new} (for {old}) is already held by a node")


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> Plan:
    """Read every uid, chunk and property, and plan the rename."""
    plan = Plan()
    uid_rows = await _fetch(driver, _UID_ROWS)
    plan_renames(uid_rows, plan)
    plan_chunks(await _fetch(driver, _CHUNK_ROWS), plan)
    plan_rewrites("node", await _fetch(driver, _NODE_VALUES), plan)
    plan_rewrites("edge", await _fetch(driver, _EDGE_VALUES), plan)
    plan_collisions(plan, Counter(str(row["uid"]) for row in uid_rows))
    return plan


class CountMismatchError(Exception):
    """A statement inside the transaction wrote a different number of rows than planned."""


async def migrate(driver: AsyncDriver, plan: Plan) -> dict[str, int]:
    """Write the whole plan in one transaction; return the count each statement wrote.

    Raises (writing nothing) when the plan has a stop, or when any count inside
    the transaction differs from the plan — the transaction is rolled back.
    """
    if plan.stops:
        raise CountMismatchError(f"{len(plan.stops)} stop(s): the plan is not safe to apply")
    statements: list[tuple[str, str, list[dict[str, Any]]]] = [  # boundary: neo4j parameters
        (
            "renamed",
            _RENAME,
            [
                {"id": r.node_id, "old": r.old, "new": r.new, "default_group": r.default_group}
                for r in plan.renames
            ],
        ),
        ("chunks re-minted", _REMINT_CHUNKS, [{"old": c.old, "new": c.new} for c in plan.chunks]),
    ]
    for target, query in (("node", _REWRITE_NODE_VALUES), ("edge", _REWRITE_EDGE_VALUES)):
        rows = [
            {"id": w.element_id, "key": w.key, "before": w.before, "patch": {w.key: w.after}}
            for w in plan.rewrites
            if w.target == target
        ]
        statements.append((f"{target} values rewritten", query, rows))
    written: dict[str, int] = {}
    # The transaction commits when the block exits cleanly and rolls back on a raise.
    async with driver.session() as session, await session.begin_transaction() as tx:
        for name, query, rows in statements:
            result = await tx.run(query, rows=rows)
            record = await result.single()
            count = int(record["written"]) if record else 0
            if count != len(rows):
                raise CountMismatchError(f"{name}: wrote {count}, planned {len(rows)}")
            written[name] = count
    return written


def manifest(plan: Plan) -> dict[str, Any]:  # boundary: JSON document
    """Every planned write — the record of what ``--confirm`` changes."""
    return {
        "renames": [
            {"label": r.label, "old": r.old, "new": r.new, "default_group": r.default_group}
            for r in plan.renames
        ],
        "chunks": [{"old": c.old, "new": c.new} for c in plan.chunks],
        "rewrites": [
            {
                "target": w.target,
                "holder": w.holder,
                "key": w.key,
                "before": w.before,
                "after": w.after,
            }
            for w in plan.rewrites
        ],
        "quoted_left": dict(plan.quoted),
        "stops": plan.stops,
    }


def _print_plan(plan: Plan) -> None:
    by_label = Counter(r.label for r in plan.renames)
    print(f"Nodes to rename: {len(plan.renames)} ({plan.embedded} embedded)")
    for label, count in sorted(by_label.items()):
        sample = next(r for r in plan.renames if r.label == label)
        print(f"  {label:<22} {count:>5}  e.g. {sample.old}  →  {sample.new}")
    print(f"Chunks to re-mint: {len(plan.chunks)}")
    by_value = Counter(f"{w.target} {w.holder}.{w.key}" for w in plan.rewrites)
    print(f"Values to rewrite: {len(plan.rewrites)}")
    for where, count in sorted(by_value.items()):
        print(f"  {where:<46} {count:>5}")
    if plan.quoted:
        print("Left as written (text quoting a renamed uid):")
        for where, count in sorted(plan.quoted.items()):
            print(f"  {where:<46} {count:>5}")
    if plan.users_outside:
        print(f"Left, a user uid in no shape (unruled): {sorted(plan.users_outside)}")
    if plan.left_exempt:
        print(
            "Left, an exempt shape: "
            + ", ".join(f"{k} {v}" for k, v in sorted(plan.left_exempt.items()))
        )
    if plan.stops:
        print(f"\nSTOPS: {len(plan.stops)}")
        for stop in plan.stops:
            print(f"  {stop}")


async def _read_back(driver: AsyncDriver, before: Plan) -> list[str]:
    """Every way the graph differs from what the rename promises; empty when it holds."""
    after = await census(driver)
    failures: list[str] = list(after.stops)
    if after.renames:
        failures.append(f"{len(after.renames)} uid(s) still outside the grammar")
    if after.chunks or after.rewrites:
        failures.append(
            f"{len(after.chunks)} chunk(s) and {len(after.rewrites)} value(s) still to move"
        )
    retired = before.new_uid_of()
    if not retired:
        return failures
    names = _uid_pattern(retired)
    for target, query in (("node", _NODE_VALUES), ("edge", _EDGE_VALUES)):
        for row in await _fetch(driver, query):
            for key, value in row["props"]:
                texts = value if isinstance(value, list) else [value]
                if any(isinstance(text, str) and names.search(text) for text in texts) and not (
                    _quotes_by_design(target, row, str(key))
                ):
                    failures.append(f"{target} {_holder(target, row)}.{key} names a retired uid")
    held = Counter(str(row["uid"]) for row in await _fetch(driver, _UID_ROWS))
    stranded = sorted(uid for uid in retired if held[uid])
    if stranded:
        failures.append(f"{len(stranded)} retired uid(s) still held: {stranded[:3]}")
    off = sorted(new for new in retired.values() if held[new] != 1)
    if off:
        failures.append(f"{len(off)} new uid(s) not held by exactly one node: {off[:3]}")
    rows = await _fetch(driver, _EMBEDDED_AT, {"ids": [r.node_id for r in before.renames]})
    embedded = int(rows[0]["embedded"]) if rows else 0
    if embedded != before.embedded:
        failures.append(f"{embedded} renamed node(s) embedded, {before.embedded} before")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(description="Rename every generated uid into the one shape")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the rename (default is a census: print the plan, change nothing)",
    )
    parser.add_argument("--manifest", type=Path, help="Write every planned write to this JSON file")
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = await Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        plan = await census(driver)
        _print_plan(plan)
        if args.manifest:
            args.manifest.write_text(json.dumps(manifest(plan), indent=1))
            print(f"\nManifest: {args.manifest}")

        if plan.stops:
            print("\nSTOP: the graph holds uids or values the rename cannot account for.")
            print("Nothing was written.")
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Stop the app, then re-run with --confirm.")
            return 0
        if plan.writes:
            written = await migrate(driver, plan)
            print("\n" + "; ".join(f"{name}: {count}" for name, count in written.items()))
        else:
            print("\nNothing to rename.")

        print("\n=== AFTER ===")
        failures = await _read_back(driver, plan)
        if failures:
            print("\nFAILED:")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print("Read-back holds: every uid in the grammar, every value on its new uid.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
