#!/usr/bin/env python3
"""
User uids into the generated shape
==================================

Renames every :User whose uid is not ``user_{16 hex}`` (a ``user_{username}``
uid) in place, folds every username to the username rule, and moves everything
that names a renamed uid or is derived from one:

    a user                       (user_admin)                 →  hashed_uid("user", old uid)
    a username                   (Mike)                       →  fold_username(it) (mike)
    a periodic note it owns      (periodic_note_uid(kind,
                                  old owner, period))         →  periodic_note_uid(kind,
                                                                   new owner, period)
    a default group it owns      (default_group_uid(old))     →  default_group_uid(new owner)
    a property naming a renamed uid — a string, a list
    element, a string in a JSON map, a ``|``-joined token of
    a tracker row's authored-edge key                         →  the new uid
    a vault file's ``teacher:`` / ``user_uid:`` /
    ``ownership:`` frontmatter line naming a renamed user —
    by its uid, or on ``user_uid:`` / ``ownership:`` by its
    bare username                                             →  the new uid

A user's new uid is a hash of its old one, so every run of the census plans the
same names. A periodic note's and a default group's are the uids their writers
derive from the owner, so the next sync and the next enrollment find them. Each
node keeps its labels, properties, embedding and edges. A session stays live in
the graph; the browser holding it signs in again, because its cookie names the
old uid (``AuthContextMiddleware`` clears a cookie that disagrees with its
session).

What the run establishes, and reads on every run: every :User uid is a generated
user uid, and every username is folded and inside the username rule; every
periodic note sits at ``periodic_note_uid`` of its one owner, and
every default group at ``default_group_uid`` of its one owner with
``is_default``; no node or edge property names a retired uid, except the text
that quotes one (``QUOTING_PROPERTIES``, left as written); no vault file names a
retired user uid.

The run STOPS (exit 2) before any write while the graph or a vault holds
something the rename cannot account for:

- a username that folds outside the username rule, or two that fold to one;
- a periodic note not at ``periodic_note_uid`` of its one owner, a group with
  ``is_default`` not at ``default_group_uid`` of its one owner, or a group there
  without it;
- a renamed node holding chunks — their uids derive from the holder's, and the
  run re-mints none (no periodic note, group or user holds any);
- a new uid any node already holds, or two nodes the run would give one uid;
- a value naming a renamed uid any other way — inside text that is not a JSON
  map or a tracker row's edge key — outside ``QUOTING_PROPERTIES``;
- a vault file naming a renamed user anywhere but the frontmatter keys
  ``VAULT_OWNER_KEYS``, a file that is not UTF-8, or a per-user vault directory
  named by a renamed user.

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the
credentials resolve):

1. Stop the app and any vault-sync script, and take an Aura on-demand snapshot.
   Then merge and pull. Do not boot the app before step 4: boot refuses an owner
   in ``.env`` that is not a user uid.
2. Census (no flag); ``--manifest PATH`` writes every planned write as JSON.
3. ``--confirm``: the graph in one transaction — each statement matches its node
   or edge by element id AND the value the census read, and a count that differs
   from the plan rolls it back — then the vault files, then a read-back. A run
   whose graph write landed and whose file edits did not is re-run: the census
   finds a vault value whose hash is a live user's uid and plans that edit.
4. Set the owners the run prints in ``.env``, then boot the app and sign in again.

Usage:
    uv run scripts/migrations/user_uids_2026_10.py                  # census
    uv run scripts/migrations/user_uids_2026_10.py --manifest m.json
    uv run scripts/migrations/user_uids_2026_10.py --confirm        # rename
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.neo_labels import NeoLabel
from core.models.group.group import default_group_uid
from core.models.relationship_names import RelationshipName
from core.models.user.user import fold_username, username_problem
from core.models.user_entry.user_entry import periodic_note_uid
from core.utils.uid_grammar import hashed_uid, is_generated_uid

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record
# A property value the run reads or writes: a string or a list of strings.
type Value = str | list[str]

USER_PREFIX = "user"

_ENTITY = NeoLabel.ENTITY.value
_USER = NeoLabel.USER.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_GROUP = NeoLabel.GROUP.value
_TRACKER = NeoLabel.INGESTION_METADATA.value
_OWNS = RelationshipName.OWNS.value
_HAS_CONTENT = RelationshipName.HAS_CONTENT.value
_HAS_CHUNK = RelationshipName.HAS_CHUNK.value
_HAS_REFERENCE_CHUNK = RelationshipName.HAS_REFERENCE_CHUNK.value

#: ``(label, property)`` pairs whose text may quote a uid — a reply's prose, a
#: file's path, a submitted file's body. The run leaves them as written and
#: reports what they quote.
QUOTING_PROPERTIES: frozenset[tuple[str, str]] = frozenset(
    {
        (NeoLabel.CONVERSATION_MESSAGE.value, "content"),
        (NeoLabel.ENTRY_REPORT.value, "report_file_path"),
        (NeoLabel.USER_ENTRY.value, "content"),
    }
)

#: The frontmatter keys a vault file names an account with.
VAULT_OWNER_KEYS: tuple[str, ...] = ("teacher", "user_uid", "ownership")
#: The owner keys a bare username may fill (``_named_uid``).
BARE_OWNER_KEYS: tuple[str, ...] = ("user_uid", "ownership")
_OWNER_LINE = re.compile(
    rf"(?P<key>{'|'.join(VAULT_OWNER_KEYS)}):[ \t]*(?P<q>[\"']?)(?P<value>[A-Za-z0-9._-]+)(?P=q)[ \t]*\r?"
)

#: The settings that name an account by uid (``VaultConfig.validate_owners``).
OWNER_SETTINGS: tuple[str, ...] = (
    "SKUEL_DEFAULT_USER_UID",
    "SKUEL_PERSONAL_VAULT_OWNER",
    "SKUEL_CONTENT_VAULT_OWNER",
)
#: The account an unset content-vault owner names in a graph this run migrates.
FORMER_CONTENT_OWNER_DEFAULT = "user_admin"

_VAULT_SUFFIXES = frozenset({".md", ".yaml", ".yml"})

_UID_ROWS = f"""
MATCH (n) WHERE n.uid IS NOT NULL
OPTIONAL MATCH (o:{_USER})-[:{_OWNS}]->(n)
WITH n, collect(o.uid) AS owners
RETURN elementId(n) AS id, n.uid AS uid, labels(n) AS labels, owners, n.title AS title,
       n.metadata AS metadata, n.is_default AS is_default,
       n.embedding IS NOT NULL AS embedded,
       EXISTS {{ (n)-[:{_HAS_CONTENT}]->()-[:{_HAS_CHUNK}]->() }}
         OR EXISTS {{ (n)-[:{_HAS_REFERENCE_CHUNK}]->() }} AS chunked
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
RETURN count(n) AS written
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
    """One node's move: old uid → new uid."""

    node_id: str
    label: str
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


@dataclass(frozen=True)
class FileEdit:
    """One vault file whose frontmatter names a renamed user, before and after."""

    path: Path
    before: str
    after: str
    lines: tuple[int, ...]  # 1-based, for the report


@dataclass
class Plan:
    """What the run would write, and every reason it must not."""

    renames: list[Rename] = field(default_factory=list)
    rewrites: list[Rewrite] = field(default_factory=list)
    files: list[FileEdit] = field(default_factory=list)
    quoted: Counter[str] = field(default_factory=Counter)  # "Label.key" quoting a renamed uid
    embedded: int = 0  # renamed nodes carrying an embedding
    stops: list[str] = field(default_factory=list)

    @property
    def writes(self) -> int:
        return len(self.renames) + len(self.rewrites)

    def new_uid_of(self) -> dict[str, str]:
        """Every renamed uid → its new uid."""
        return {r.old: r.new for r in self.renames}

    def user_moves(self) -> dict[str, str]:
        """Every renamed user's old uid → its new uid."""
        return {r.old: r.new for r in self.renames if r.label == _USER}


def _label_of(labels: Iterable[str]) -> str:
    """The labels a node is reported under: every label but ``Entity``, joined."""
    return ":".join(sorted(label for label in labels if label != _ENTITY)) or _ENTITY


def _period_of(row: Row) -> tuple[str, str] | None:
    """``(entry_kind, period_key)`` of a periodic note's row, ``None`` for any other node."""
    if _USER_ENTRY not in row["labels"] or not isinstance(row["metadata"], str):
        return None
    try:
        metadata = json.loads(row["metadata"])
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, dict):
        return None
    kind, period = metadata.get("entry_kind"), metadata.get("period_key")
    if isinstance(kind, str) and kind and isinstance(period, str) and period:
        return kind, period
    return None


def plan_renames(rows: list[Row], plan: Plan) -> None:
    """Plan every user's rename, and every periodic note and default group it owns."""
    users = {str(row["uid"]): row for row in rows if _USER in row["labels"]}
    moves = {
        uid: hashed_uid(USER_PREFIX, uid) for uid in users if not is_generated_uid(uid, USER_PREFIX)
    }
    for old, new in sorted(moves.items()):
        _rename(users[old], new, plan)
    for row in rows:
        uid, owners = str(row["uid"]), [str(owner) for owner in row["owners"]]
        period = _period_of(row)
        if period is not None:
            kind, key = period
            if len(owners) != 1 or uid != periodic_note_uid(kind, owners[0], key):
                plan.stops.append(
                    f"periodic note {uid}: not periodic_note_uid of its owner {sorted(owners)}"
                )
            elif owners[0] in moves:
                _rename(row, periodic_note_uid(kind, moves[owners[0]], key), plan)
        if _GROUP in row["labels"]:
            at_derived = len(owners) == 1 and uid == default_group_uid(owners[0])
            if row["is_default"] is True and not at_derived:
                plan.stops.append(
                    f"group {uid}: is_default, not default_group_uid of its owner {sorted(owners)}"
                )
            elif at_derived and row["is_default"] is not True:
                plan.stops.append(f"group {uid}: a default group without is_default")
            elif at_derived and owners[0] in moves:
                _rename(row, default_group_uid(moves[owners[0]]), plan)


def plan_usernames(rows: list[Row], plan: Plan) -> None:
    """Fold every username (a user's ``title``) to the username rule.

    Sign-up stores a username folded and every lookup folds what it is given, so
    a stored name that is not folded is one no lookup finds. Stops on a name that
    folds outside the rule (``username_problem``) and on two that fold to one.
    """
    holders: dict[str, list[str]] = {}
    for row in rows:
        title = row["title"]
        if _USER not in row["labels"] or not isinstance(title, str):
            continue
        uid, name = str(row["uid"]), fold_username(title)
        holders.setdefault(name, []).append(uid)
        problem = username_problem(name)
        if problem:
            plan.stops.append(f"user {uid}: username {title!r} folds outside the rule — {problem}")
        elif name != title:
            plan.rewrites.append(Rewrite("node", str(row["id"]), _USER, "title", title, name))
    for name, uids in sorted(holders.items()):
        if len(uids) > 1:
            plan.stops.append(f"users {sorted(uids)}: their usernames all fold to {name!r}")


def _rename(row: Row, new: str, plan: Plan) -> None:
    label, uid = _label_of(row["labels"]), str(row["uid"])
    if row["chunked"]:
        plan.stops.append(f"{label} {uid}: holds chunks, whose uids derive from this one")
        return
    plan.renames.append(Rename(str(row["id"]), label, uid, new))
    if row["embedded"]:
        plan.embedded += 1


def uid_pattern(uids: Iterable[str]) -> re.Pattern[str]:
    """Any of ``uids`` as a whole token — not inside a longer uid.

    A uid's characters are ``[a-z0-9._-]``; anything else around one — the ``|``
    of a tracker row's edge key, a ``:``, a quote, a space — bounds it. A ``.``
    after one bounds it too unless a letter or digit follows (``ask user_x.`` ends
    a sentence; ``user_x.y`` is a longer uid).
    """
    alternatives = "|".join(re.escape(uid) for uid in sorted(uids, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9._-])(?:{alternatives})(?![a-z0-9_-])(?!\.[a-z0-9])")


def _json_values(parsed: object, new_uid_of: Mapping[str, str]) -> object:
    """``parsed`` with every string value that is a renamed uid replaced by its new uid."""
    if isinstance(parsed, str):
        return new_uid_of.get(parsed, parsed)
    if isinstance(parsed, list):
        return [_json_values(item, new_uid_of) for item in parsed]
    if isinstance(parsed, dict):
        return {key: _json_values(value, new_uid_of) for key, value in parsed.items()}
    return parsed


def rewrite_of(
    value: object, new_uid_of: Mapping[str, str], names: re.Pattern[str], *, tracker: bool
) -> tuple[str, Value | None]:
    """How the run treats one property value, and the value it writes.

    ``("untouched", None)`` — it names no renamed uid. ``("rewrite", new)`` — every
    renamed uid it names is a whole value (the string, a list element, or a string
    inside a JSON map or list that reads back to its own text), or a token of a
    tracker row's text — an authored-edge key like ``REVIEWED_BY|outgoing|{uid}``,
    which the run's vault edit makes the file declare. ``("quotes", None)`` — it
    names one inside other text.
    """

    def tokens(text: str) -> str:
        return names.sub(lambda match: new_uid_of[match.group(0)], text)

    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value) or not any(
            names.search(item) for item in value
        ):
            return "untouched", None
        if not tracker and any(item not in new_uid_of and names.search(item) for item in value):
            return "quotes", None
        return "rewrite", [
            new_uid_of[item] if item in new_uid_of else tokens(item) for item in value
        ]
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
    if tracker:
        return "rewrite", tokens(value)
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
    names = uid_pattern(new_uid_of)
    for row in rows:
        tracker = target == "node" and _TRACKER in row["labels"]
        for key, value in row["props"]:
            verdict, after = rewrite_of(value, new_uid_of, names, tracker=tracker)
            where = f"{_holder(target, row)}.{key}"
            if verdict == "rewrite" and after is not None:
                plan.rewrites.append(
                    Rewrite(target, str(row["id"]), _holder(target, row), str(key), value, after)
                )
            elif verdict == "quotes" and _quotes_by_design(target, row, str(key)):
                plan.quoted[where] += 1
            elif verdict == "quotes":
                plan.stops.append(f"{target} {where} names a renamed uid inside other text")


def plan_collisions(plan: Plan, held: Counter[str]) -> None:
    """Stop on any uid that would name more than one node.

    ``held`` counts the nodes holding each uid, in any label. A new uid must be
    free graph-wide and planned once.
    """
    for new_uid, count in sorted(Counter(r.new for r in plan.renames).items()):
        if count > 1:
            plan.stops.append(f"{count} nodes would all become {new_uid}")
    for rename in plan.renames:
        if rename.new in held:
            plan.stops.append(f"{rename.new} (for {rename.old}) is already held by a node")


def _vault_files(root: Path) -> Iterable[Path]:
    """Every markdown and YAML file under ``root``, hidden folders skipped."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix.lower() in _VAULT_SUFFIXES:
                yield path


def _frontmatter_end(text: str) -> int:
    """The index where a file's frontmatter ends (0 when it has none)."""
    if not text.startswith("---"):
        return 0
    end = text.find("\n---", 3)
    return end if end != -1 else 0


def _owner_value(line: str) -> re.Match[str] | None:
    """A ``VAULT_OWNER_KEYS`` line's match — ``key``, ``value`` — or ``None``.

    The value may be quoted; the quotes, the gap after the colon and any
    trailing blank or ``\r`` are kept by an edit.
    """
    return _OWNER_LINE.fullmatch(line)


def _named_uid(key: str, value: str) -> str:
    """The user uid an owner line names: its value, or ``user_{value}`` for a bare username.

    In a vault this run migrates, a bare ``ownership:`` / ``user_uid:`` value names
    the uid ``user_{value}`` (``ownership: linguistic76`` names ``user_linguistic76``);
    ``teacher:`` names a uid and nothing else.
    """
    if key in BARE_OWNER_KEYS and not value.startswith(f"{USER_PREFIX}_"):
        return f"{USER_PREFIX}_{value}"
    return value


def plan_vaults(
    roots: Iterable[Path], user_vaults_root: Path | None, live_users: set[str], plan: Plan
) -> None:
    """Plan each vault file edit that moves a renamed user's old uid to its new one.

    A frontmatter owner line is edited when the uid it names (``_named_uid``) is
    one the plan renames, or — on a re-run after the graph moved — one whose hash
    is a live user's uid. Any other mention of a retired uid stops the run.
    """
    texts: dict[Path, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in _vault_files(root):
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    texts[path] = handle.read()
            except UnicodeDecodeError:
                plan.stops.append(f"vault file {path}: not UTF-8 — the run cannot read it")
    moves = plan.user_moves()

    def new_uid(named: str) -> str | None:
        if named in moves:
            return moves[named]
        derived = hashed_uid(USER_PREFIX, named)
        if named not in live_users and derived in live_users:
            moves[named] = derived
            return derived
        return None

    edits: dict[Path, dict[int, str]] = {}
    for path, text in sorted(texts.items()):
        end, offset = _frontmatter_end(text), 0
        for number, line in enumerate(text.split("\n"), start=1):
            match = _owner_value(line) if offset < end else None
            offset += len(line) + 1
            if match is None:
                continue
            new = new_uid(_named_uid(match["key"], match["value"]))
            if new is not None:
                start, stop = match.span("value")
                edits.setdefault(path, {})[number] = line[:start] + new + line[stop:]
    if not moves:
        return
    if user_vaults_root is not None:
        for old in sorted(moves):
            if (user_vaults_root / old).exists():
                plan.stops.append(
                    f"per-user vault {user_vaults_root / old}: rename it to {moves[old]}"
                )
    names = uid_pattern(moves)
    for path, text in sorted(texts.items()):
        edited = edits.get(path, {})
        lines = text.split("\n")
        for number, line in enumerate(lines, start=1):
            match = names.search(line) if number not in edited else None
            if match:
                plan.stops.append(
                    f"vault file {path}:{number} names {match.group(0)} outside its "
                    f"{'/'.join(VAULT_OWNER_KEYS)} frontmatter — edit it to {moves[match.group(0)]}"
                )
        if edited:
            after = [edited.get(number, line) for number, line in enumerate(lines, start=1)]
            plan.files.append(FileEdit(path, text, "\n".join(after), tuple(sorted(edited))))


def owner_settings(moves: Mapping[str, str], environ: Mapping[str, str]) -> list[str]:
    """The ``.env`` lines to set — every owner setting that names a renamed user.

    The content-vault owner is required; when it is unset, the line is printed for
    the new uid of ``FORMER_CONTENT_OWNER_DEFAULT``, the account it names here.
    """
    lines = []
    for name in OWNER_SETTINGS:
        value = environ.get(name, "").strip()
        if value in moves:
            lines.append(f"{name}={moves[value]}")
        elif not value and name == "SKUEL_CONTENT_VAULT_OWNER":
            default = moves.get(FORMER_CONTENT_OWNER_DEFAULT)
            if default:
                lines.append(f"{name}={default}")
    return lines


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(
    driver: AsyncDriver, vault_roots: Iterable[Path], user_vaults_root: Path | None
) -> Plan:
    """Read every uid, property and vault file, and plan the rename."""
    plan = Plan()
    uid_rows = await _fetch(driver, _UID_ROWS)
    plan_renames(uid_rows, plan)
    plan_usernames(uid_rows, plan)
    plan_rewrites("node", await _fetch(driver, _NODE_VALUES), plan)
    plan_rewrites("edge", await _fetch(driver, _EDGE_VALUES), plan)
    plan_collisions(plan, Counter(str(row["uid"]) for row in uid_rows))
    live_users = {str(row["uid"]) for row in uid_rows if _USER in row["labels"]}
    plan_vaults(vault_roots, user_vaults_root, live_users | set(plan.user_moves().values()), plan)
    return plan


class CountMismatchError(Exception):
    """A statement inside the transaction wrote a different number of rows than planned."""


async def migrate(driver: AsyncDriver, plan: Plan) -> dict[str, int]:
    """Write the graph half of the plan in one transaction; return each statement's count.

    Raises (writing nothing) when the plan has a stop, or when any count inside
    the transaction differs from the plan — the transaction is rolled back.
    """
    if plan.stops:
        raise CountMismatchError(f"{len(plan.stops)} stop(s): the plan is not safe to apply")
    statements: list[tuple[str, str, list[dict[str, Any]]]] = [  # boundary: neo4j parameters
        (
            "renamed",
            _RENAME,
            [{"id": r.node_id, "old": r.old, "new": r.new} for r in plan.renames],
        ),
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


def edit_vaults(plan: Plan) -> int:
    """Write the planned vault edits; return how many files changed.

    Each file is written only while it still holds the text the census read.
    """
    changed = 0
    for edit in plan.files:
        with edit.path.open(encoding="utf-8", newline="") as handle:
            if handle.read() != edit.before:
                raise CountMismatchError(f"vault file {edit.path} changed since the census")
        with edit.path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(edit.after)
        changed += 1
    return changed


def manifest(plan: Plan) -> dict[str, Any]:  # boundary: JSON document
    """Every planned write — the record of what ``--confirm`` changes."""
    return {
        "renames": [{"label": r.label, "old": r.old, "new": r.new} for r in plan.renames],
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
        "files": [{"path": str(f.path), "lines": list(f.lines)} for f in plan.files],
        "quoted_left": dict(plan.quoted),
        "stops": plan.stops,
    }


def _print_plan(plan: Plan) -> None:
    by_label = Counter(r.label for r in plan.renames)
    print(f"Nodes to rename: {len(plan.renames)} ({plan.embedded} embedded)")
    for label, count in sorted(by_label.items()):
        sample = next(r for r in plan.renames if r.label == label)
        print(f"  {label:<22} {count:>5}  e.g. {sample.old}  →  {sample.new}")
    by_value = Counter(f"{w.target} {w.holder}.{w.key}" for w in plan.rewrites)
    print(f"Values to rewrite: {len(plan.rewrites)}")
    for where, count in sorted(by_value.items()):
        print(f"  {where:<46} {count:>5}")
    print(f"Vault files to edit: {len(plan.files)}")
    for edit in plan.files:
        print(f"  {edit.path}  (line {', '.join(str(n) for n in edit.lines)})")
    if plan.quoted:
        print("Left as written (text quoting a renamed uid):")
        for where, count in sorted(plan.quoted.items()):
            print(f"  {where:<46} {count:>5}")
    if plan.stops:
        print(f"\nSTOPS: {len(plan.stops)}")
        for stop in plan.stops:
            print(f"  {stop}")


async def read_back(
    driver: AsyncDriver,
    before: Plan,
    vault_roots: Iterable[Path],
    user_vaults_root: Path | None,
) -> list[str]:
    """Every way the graph and vaults differ from what the rename promises; empty when they hold."""
    roots = list(vault_roots)
    after = await census(driver, roots, user_vaults_root)
    failures: list[str] = list(after.stops)
    if after.renames or after.rewrites or after.files:
        failures.append(
            f"{len(after.renames)} uid(s), {len(after.rewrites)} value(s) and "
            f"{len(after.files)} vault file(s) still to move"
        )
    retired = before.new_uid_of()
    if not retired:
        return failures
    names = uid_pattern(retired)
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
    parser = argparse.ArgumentParser(description="Rename every user uid into the generated shape")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the rename (default is a census: print the plan, change nothing)",
    )
    parser.add_argument("--manifest", type=Path, help="Write every planned write to this JSON file")
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
    from core.config.unified_config import VaultConfig

    vault = VaultConfig()
    roots = [vault.vault_path, vault.ingestion_path]
    user_vaults_root = vault.user_vaults_path
    driver = await Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        print("Vaults: " + ", ".join(str(root) for root in roots))
        plan = await census(driver, roots, user_vaults_root)
        _print_plan(plan)
        if args.manifest:
            args.manifest.write_text(json.dumps(manifest(plan), indent=1))
            print(f"\nManifest: {args.manifest}")

        if plan.stops:
            print("\nSTOP: the graph or a vault holds what the rename cannot account for.")
            print("Nothing was written.")
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Stop the app, then re-run with --confirm.")
            return 0
        if plan.writes:
            written = await migrate(driver, plan)
            print("\n" + "; ".join(f"{name}: {count}" for name, count in written.items()))
        else:
            print("\nNothing to rename in the graph.")
        print(f"Vault files edited: {edit_vaults(plan)}")

        print("\n=== AFTER ===")
        failures = await read_back(driver, plan, roots, user_vaults_root)
        if failures:
            print("\nFAILED:")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print("Read-back holds: every user uid generated, every value on its new uid.")
        settings = owner_settings(plan.user_moves(), os.environ)
        if settings:
            print("\nSet in .env before booting (boot refuses an owner that is not a user uid):")
            for line in settings:
                print(f"  {line}")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
