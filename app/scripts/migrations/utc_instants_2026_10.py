#!/usr/bin/env python3
"""
Migrate every stored instant to UTC
===================================

The stored corpus holds instants on four clocks (ADR-089; the arc record,
docs/roadmap/utc-instants-arc.md § Stored instants): the laptop's wall clock in
America/Vancouver, the same laptop at UTC+7 before 2026-03-27, and two writers
that already stamp true UTC. This script moves every laptop-clock stamp's digits
to UTC and leaves every other value as it is. It keeps each value's shape (R5):
an offset-less string stays offset-less, a native stays native.

Shape alone cannot tell a migrated stamp from an unmigrated one, so the
migration's state lives outside the values — an immutable manifest, one
transaction, and a durable record on the graph (``:MigrationRecord``, named
``utc_instants_2026_10``), which the graph driver's guard reads
(adapters/persistence/neo4j/graph_driver.py). This script is the one opener
exempt from that guard.

**Census** (the default, read-only). Reads every node and relationship property
holding a temporal or an ISO-datetime string, and every stamp nested in a JSON
property, and classifies each value by the rule ``RULES`` names for its (label
or type, property), cross-checked by its shape and sub-second precision (a Python
parameter carries microseconds; Cypher ``datetime()`` milliseconds). A
laptop-clock stamp is read in the zone its date gives: before 2026-03-27 at
+07:00, from 2026-03-28 in America/Vancouver. It STOPS (exit 2, nothing written)
on any value no rule settles — a property or shape missing from the table, a
laptop-clock stamp dated 2026-03-27, a stamp stamped "now" whose digits are later
than the laptop's wall clock, a key that names more than one element — and lists
each for Mike's ruling. Otherwise it writes the manifest (one row per value to
move: its durable key, property, shape, old and new value, rule) outside the
tracked tree, and prints per-rule counts with samples and the manifest's hash.
Refused (exit 1) when the record is ``applied``.

**--confirm HASH**: applies the manifest with that hash — and nothing else — in
one transaction: each value is set where it still equals the manifest's old
value, and the record is written in state ``applied``. A value that changed since
the census rolls the whole transaction back (exit 1, nothing written). Refused
when the record is ``applied`` or the manifest was taken on another graph.

**--verify**: every manifest row at its new value and the record ``applied``, and
the classification check: the nodes whose laptop-clock ``created_at`` and server
``embedding_updated_at`` were written in the same moment read 7.00 h apart before
and about 0 h after.

**--revert**: the manifest applied new → old by the same compare-and-set, and the
record set to ``reverted``, in one transaction. For the deploy sitting only: once
the app has written on the cutover code, the fix goes forward.

Runs on the laptop in the deploy sitting (§ Migration contract, step 7), with the
app stopped and after an Aura snapshot; every write needs Mike's OK on the counts.

Usage (from app/, with the laptop's .env loaded):
    uv run python scripts/migrations/utc_instants_2026_10.py                 # census
    uv run python scripts/migrations/utc_instants_2026_10.py --confirm HASH  # write
    uv run python scripts/migrations/utc_instants_2026_10.py --verify
    uv run python scripts/migrations/utc_instants_2026_10.py --revert
"""

from __future__ import annotations

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict, cast
from zoneinfo import ZoneInfo

from adapters.persistence.neo4j.graph_driver import (
    UTC_INSTANTS_MIGRATION,
    ensure_record_name_is_unique,
)
from core.models.enums.migration_enums import MigrationState
from core.models.enums.neo_labels import NeoLabel
from core.models.group.group import DEFAULT_GROUP_UID_PREFIX
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncTransaction

# One driver record, keyed by RETURN alias, or one statement's parameters;
# values are heterogeneous Neo4j scalars, so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record / query parameters

type Target = Literal["node", "rel"]
type Shape = Literal["string", "native", "json"]


class NodeKey(TypedDict):
    """A node's durable key: matched as ``(:match_label {key_prop: key})``, with ``owner_label``."""

    match_label: str
    owner_label: str
    key_prop: str
    key: str


class RelKey(TypedDict):
    """A relationship's durable key: its type and its endpoints' uids (never an element id)."""

    type: str
    start_label: str
    start_uid: str
    end_label: str
    end_uid: str


type ElementKey = NodeKey | RelKey


class JsonChange(TypedDict):
    """One nested stamp a JSON row moves, for the manifest's audit."""

    path: str
    old: str
    new: str


class JsonRow(TypedDict):
    """The census's whole-property row for a JSON property whose nested stamps move."""

    element: str
    owner: str
    prop: str
    key: NodeKey
    old: str
    new: str
    changes: list[JsonChange]


class Pair(TypedDict):
    """A laptop ``created_at`` and a server ``embedding_updated_at`` written in one moment."""

    key: NodeKey
    created_at_old: str
    created_at_new: str
    embedding_updated_at: str


class ManifestRow(TypedDict):
    """One value the migration moves: where, from what, to what, and by which rule."""

    id: int
    target: Target
    owner: str
    key: ElementKey
    property: str
    shape: Shape
    old: str
    new: str
    rule: str
    changes: NotRequired[list[JsonChange]]


class Manifest(TypedDict):
    """The immutable, content-addressed record of what ``--confirm`` applies."""

    migration: str
    format: int
    graph_uri: str
    census_at: str
    laptop_wall_clock_at_census: str
    counts: dict[str, int]
    left: dict[str, int]
    pairs: list[Pair]
    rows: list[ManifestRow]


class RecordState(TypedDict):
    """A ``:MigrationRecord`` as the state checks read it."""

    state: str | None
    manifest_hash: str | None
    stamped: str | None


MANIFEST_FORMAT = 1

#: The laptop's zone since 2026-03-28, and before 2026-03-27 (R3).
LAPTOP = ZoneInfo("America/Vancouver")
PLUS_SEVEN = timezone(timedelta(hours=7))
#: The day the laptop's zone changed: a laptop-clock stamp dated on it stops.
ZONE_CHANGE_DAY = date(2026, 3, 27)

#: A server stamp written in the same moment as a laptop stamp reads within this.
PAIR_TOLERANCE = timedelta(seconds=120)
#: The laptop's summer offset the classification check expects on a pair.
PAIR_OFFSET = timedelta(hours=7)

_RECORD = NeoLabel.MIGRATION_RECORD.value
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ISO_STAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<hm>\d{2}:\d{2})(?::(?P<s>\d{2})(?:\.(?P<frac>\d+))?)?"
    r"(?P<offset>Z|[+-]\d{2}:\d{2})?$"
)


# =============================================================================
# VALUE CLASSES — what a stored value's shape and precision say about its writer
# =============================================================================


class ValueClass(StrEnum):
    """The shape of one stored value, as the rules read it."""

    #: Offset-less string, six fractional digits — Python ``isoformat()`` of a naive datetime.
    STR_NAIVE_US = "string, offset-less, microseconds"
    #: Offset-less string, whole seconds — the same, on a whole second (a midnight, a bound).
    STR_NAIVE_S = "string, offset-less, whole seconds"
    #: Offset-less string, one to three fractional digits — Cypher ``toString(localdatetime())``.
    STR_NAIVE_MS = "string, offset-less, milliseconds"
    #: Offset-less string of any other precision (minutes only, 4/5/7+ digits).
    STR_NAIVE_OTHER = "string, offset-less, other precision"
    #: String ending ``Z`` or ``±hh:mm`` — Cypher ``toString(datetime())``, an aware
    #: ``isoformat()``, an authored offset.
    STR_OFFSET = "string with an offset"
    #: Zoned native at UTC with microsecond digits — a Python parameter.
    NATIVE_US = "native, microseconds"
    #: Zoned native at UTC on a whole millisecond — Cypher ``datetime()``.
    NATIVE_MS = "native, milliseconds"
    #: Zoned native at UTC on a whole second.
    NATIVE_S = "native, whole seconds"
    #: Zoned native with nanosecond digits, or at an offset other than UTC.
    NATIVE_OTHER = "native, other precision or offset"
    #: A LOCAL DATETIME or ZONED TIME native — no writer here produces one.
    NATIVE_UNZONED = "native without a zone"
    #: A timestamp-shaped string in a form the classifier does not read (a comma for
    #: the decimal point, an offset without its colon, a zone id) — still a stamp.
    STR_UNRECOGNIZED = "string, timestamp-shaped, in a form the classifier does not read"
    #: A list property holding stamps — no rule reads a stamp inside a list.
    LIST_OF_STAMPS = "a list holding stamps"


class Verdict(StrEnum):
    SHIFT = "shift"
    LEAVE = "leave"
    STOP = "stop"


@dataclass(frozen=True)
class Value:
    """One stored value, read from the graph."""

    text: str  # a string as stored; a native's Cypher toString()
    cls: ValueClass
    #: The digits as a naive datetime (a native's wall clock at its offset).
    digits: datetime | None
    #: For a native: whether its zone is an offset (``Z``) rather than a zone id.
    offset_zone: bool = True


def classify_string(text: str) -> Value | None:
    """An ISO-datetime string's class, or None when the string is not one."""
    match = _ISO_STAMP.match(text)
    if match is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if match["offset"]:
        return Value(text, ValueClass.STR_OFFSET, parsed.replace(tzinfo=None))
    frac = match["frac"] or ""
    if match["s"] is None:
        cls = ValueClass.STR_NAIVE_OTHER
    elif not frac:
        cls = ValueClass.STR_NAIVE_S
    elif len(frac) == 6:
        cls = ValueClass.STR_NAIVE_US
    elif len(frac) <= 3:
        cls = ValueClass.STR_NAIVE_MS
    else:
        cls = ValueClass.STR_NAIVE_OTHER
    return Value(text, cls, parsed)


_STAMP_PREFIX_T = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}")
_STAMP_PREFIX_SPACE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}")


def _reads_as_instant(text: str) -> bool:
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def classify_stamp_string(text: str) -> Value | None:
    """A timestamp-shaped string's class — an unreadable form included — or None for any other.

    A string the readers would take for an instant but the classifier does not read
    is a stamp all the same: it is ``STR_UNRECOGNIZED``, which no rule settles, so
    the census stops on it rather than passing it over. A ``T``-separated date and
    hour is a machine's; a space-separated one counts only when
    ``datetime.fromisoformat`` reads the whole string — a title that begins with a
    date and a time does not.
    """
    value = classify_string(text)
    if value is not None:
        return value
    if _STAMP_PREFIX_T.match(text) or (_STAMP_PREFIX_SPACE.match(text) and _reads_as_instant(text)):
        return Value(text, ValueClass.STR_UNRECOGNIZED, None)
    return None


def classify_native(value_type: str, text: str, zone: str | None, nanosecond: int) -> Value:
    """A temporal native's class, from its Cypher ``valueType``, ``toString`` and parts."""
    if not value_type.startswith("ZONED DATETIME"):
        return Value(text, ValueClass.NATIVE_UNZONED, None)
    base = text.split("[", 1)[0]
    try:
        digits = datetime.fromisoformat(base).replace(tzinfo=None)
    except ValueError:
        return Value(text, ValueClass.NATIVE_OTHER, None)
    if zone not in ("Z", "UTC") or nanosecond % 1000:
        return Value(text, ValueClass.NATIVE_OTHER, digits, offset_zone=zone == "Z")
    if nanosecond == 0:
        cls = ValueClass.NATIVE_S
    elif nanosecond % 1_000_000 == 0:
        cls = ValueClass.NATIVE_MS
    else:
        cls = ValueClass.NATIVE_US
    return Value(text, cls, digits, offset_zone=zone == "Z")


# =============================================================================
# RULES — (label or type, property) → what each value class there means
# =============================================================================

S, L = Verdict.SHIFT, Verdict.LEAVE

#: The mapper's ``isoformat()`` of a naive ``datetime.now()`` or default factory.
_NAIVE_WRITER = {ValueClass.STR_NAIVE_US: S, ValueClass.STR_NAIVE_S: S}
#: Cypher ``toString(datetime())``, an aware ``isoformat()``, an authored offset.
_OFFSET_STRING = {ValueClass.STR_OFFSET: L}
#: Cypher ``datetime()`` — milliseconds, or a whole second.
_SERVER_NATIVE = {ValueClass.NATIVE_MS: L, ValueClass.NATIVE_S: L}
#: ``datetime($now)`` from a naive ``datetime.now().isoformat()``.
_LAPTOP_NATIVE = {ValueClass.NATIVE_US: S}
#: An aware Python parameter, or Cypher ``datetime()``.
_AWARE_NATIVE = {ValueClass.NATIVE_US: L, ValueClass.NATIVE_MS: L, ValueClass.NATIVE_S: L}


@dataclass(frozen=True)
class Rule:
    """What each value class means on the properties a rule covers.

    A class the rule does not name stops the census. ``stamped_now`` marks a
    property its writers stamp with the current moment, so a shift candidate
    whose digits are later than the laptop's wall clock was written by a
    UTC-clock process and stops; a deadline or a period's end may lie ahead.
    """

    name: str
    verdicts: Mapping[ValueClass, Verdict]
    stamped_now: bool = True
    #: A rule settled row by row from a paired stamp (``MEMBER_OF.joined_at``).
    paired: bool = False

    def verdict(self, cls: ValueClass) -> Verdict:
        return self.verdicts.get(cls, Verdict.STOP)


LAPTOP_STRING = Rule(
    "laptop string (mapper), server native, offset string",
    {**_NAIVE_WRITER, **_OFFSET_STRING, **_SERVER_NATIVE},
)
LAPTOP_STRING_AHEAD = Rule(
    "laptop string (mapper), may lie ahead",
    {**_NAIVE_WRITER, **_OFFSET_STRING, **_SERVER_NATIVE},
    stamped_now=False,
)
CLIENT_STRING = Rule(
    "laptop string, or a client's offset string",
    {**_NAIVE_WRITER, **_OFFSET_STRING},
)
CLIENT_STRING_AHEAD = Rule(
    "laptop string, or a client's offset string, may lie ahead",
    {**_NAIVE_WRITER, **_OFFSET_STRING},
    stamped_now=False,
)
LAPTOP_STRING_OR_NATIVE = Rule(
    "laptop string or laptop native",
    {**_NAIVE_WRITER, **_LAPTOP_NATIVE},
)
LAPTOP_NATIVE = Rule("laptop native (datetime($now))", {**_LAPTOP_NATIVE})
LAPTOP_NATIVE_OR_STRING = Rule(
    "laptop native or laptop string (raw parameter)", {**_LAPTOP_NATIVE, **_NAIVE_WRITER}
)
LAPTOP_NATIVE_OR_MIDNIGHT = Rule(
    "laptop native, or a completion day's local midnight",
    {ValueClass.NATIVE_US: S, ValueClass.NATIVE_S: S},
)
PERIOD_BOUND = Rule("report period bound (laptop string)", {**_NAIVE_WRITER}, stamped_now=False)
PERIOD_CUTOFF = Rule("report data cutoff (laptop string)", {**_NAIVE_WRITER})
TRUE_UTC = Rule("true UTC (aware Python, Cypher datetime())", {**_AWARE_NATIVE, **_OFFSET_STRING})
TRUE_UTC_STRING = Rule("true UTC string (aware isoformat)", {**_OFFSET_STRING})
AUTHORED_OFFSET = Rule("authored offset", {**_OFFSET_STRING}, stamped_now=False)
OWNS_STAMP = Rule(
    "OWNS stamp: laptop string, or a backfill's UTC localdatetime()",
    {ValueClass.STR_NAIVE_US: S, ValueClass.STR_NAIVE_MS: L, **_OFFSET_STRING},
)
GROUP_CREATED = Rule(
    "group created: laptop string, or the enrollment handler's aware native",
    {**_NAIVE_WRITER, **_AWARE_NATIVE},
)
PRODUCTIVITY_STAMP = Rule("completion stamp (laptop native)", {**_LAPTOP_NATIVE})
INSIGHT_EXPIRY = Rule(
    "insight expiry: naive or aware parameter, indistinguishable", {}, stamped_now=False
)
MEMBER_OF_JOINED = Rule(
    "MEMBER_OF joined: add_member (laptop) or the enrollment handler (aware), by pairing",
    {},
    paired=True,
)


@dataclass(frozen=True)
class JsonRule:
    """A JSON property's nested stamps: paths code reads as instants, and paths it never compares."""

    name: str
    read: Mapping[str, Rule] = field(default_factory=dict)
    diagnostic: frozenset[str] = frozenset()


def _node(label: NeoLabel | str) -> str:
    return f"(:{label})"


def _rel(rel_type: RelationshipName | str) -> str:
    return f"[:{rel_type}]"


def _build_rules() -> dict[tuple[str, str], Rule]:
    rules: dict[tuple[str, str], Rule] = {}

    def put(owners: Iterable[str], props: Iterable[str], rule: Rule) -> None:
        for owner in owners:
            for prop in props:
                rules[(owner, prop)] = rule

    # Every node's created_at / updated_at: the mapper writes a naive isoformat,
    # the bulk upsert and a few writers Cypher datetime(), ingest and aware
    # writers offset strings. Labels whose writers differ are overridden below.
    put([_node(label) for label in NeoLabel], ["created_at", "updated_at"], LAPTOP_STRING)
    # Every relationship's created_at / updated_at: the edge-YAML door (any
    # RelationshipName) and the lateral door write a naive isoformat; the rest
    # Cypher datetime(). OWNS is overridden below.
    put([_rel(rel) for rel in RelationshipName], ["created_at", "updated_at"], LAPTOP_STRING)
    # An edge file may carry an authored observed_at on any relationship.
    put([_rel(rel) for rel in RelationshipName], ["observed_at"], AUTHORED_OFFSET)
    # Every node's embedding stamp: Cypher datetime(), or its carried-forward read.
    put([_node(label) for label in NeoLabel], ["embedding_updated_at"], TRUE_UTC)

    # --- nodes -------------------------------------------------------------
    put(
        [_node(NeoLabel.ENTRY_REPORT), _node(NeoLabel.REVISED_EXERCISE)],
        ["created_at", "updated_at"],
        LAPTOP_STRING_OR_NATIVE,
    )
    put([_node(NeoLabel.USER_ENTRY)], ["updated_at"], LAPTOP_STRING_OR_NATIVE)
    put(
        [_node(NeoLabel.NOTIFICATION), _node(NeoLabel.INSIGHT), _node(NeoLabel.SEARCH_EVENT)],
        ["created_at"],
        LAPTOP_NATIVE,
    )
    put([_node(NeoLabel.GROUP)], ["created_at"], GROUP_CREATED)
    put([_node(NeoLabel.INSIGHT)], ["expires_at"], INSIGHT_EXPIRY)
    put([_node(NeoLabel.INSIGHT)], ["dismissed_at", "actioned_at"], TRUE_UTC)
    put([_node(NeoLabel.SESSION)], ["created_at", "expires_at", "last_active_at"], TRUE_UTC)
    put([_node(NeoLabel.AUTH_EVENT)], ["timestamp"], TRUE_UTC)
    put([_node(NeoLabel.CONTENT)], ["created_at", "updated_at"], TRUE_UTC)
    put([_node(NeoLabel.CONTENT_CHUNK), _node(NeoLabel.REFERENCE_CHUNK)], ["created_at"], TRUE_UTC)
    put([_node(NeoLabel.CONVERSATION_MESSAGE)], ["timestamp"], TRUE_UTC)
    put([_node(NeoLabel.CONVERSATION_SESSION)], ["started_at", "last_activity"], TRUE_UTC)
    put([_node(NeoLabel.CONVERSATION_TURN)], ["timestamp"], TRUE_UTC)
    put([_node(NeoLabel.INGESTION_METADATA)], ["last_ingested_at"], TRUE_UTC)
    put([_node(NeoLabel.DEVICE)], ["enrolled_at", "revoked_at", "last_seen_at"], TRUE_UTC)
    put([_node(NeoLabel.PASSWORD_RESET_TOKEN)], ["created_at", "expires_at", "used_at"], TRUE_UTC)
    put([_node(NeoLabel.ACHIEVEMENT)], ["created_at"], TRUE_UTC)
    put([_node(NeoLabel.USER_ENTRY)], ["grounded_at"], TRUE_UTC)
    put(
        [_node(NeoLabel.USER_ENTRY)],
        ["processing_completed_at", "processing_started_at"],
        LAPTOP_STRING,
    )
    put([_node(NeoLabel.TASK)], ["vault_line_retired_at"], TRUE_UTC)
    put(
        [_node(NeoLabel.USER)],
        ["sel_last_viewed", "deleted_at"],
        TRUE_UTC,
    )
    put([_node(NeoLabel.USER)], ["pairing_code_expires_at"], TRUE_UTC)
    put([_node(NeoLabel.USER)], ["last_login_at"], TRUE_UTC_STRING)
    put([_node(NeoLabel.USER)], ["last_active_at"], CLIENT_STRING)
    put(
        [_node(NeoLabel.USER)],
        ["feedback_updated_at", "task_duration_updated_at", "vision_captured_at"],
        LAPTOP_STRING,
    )
    put([_node(NeoLabel.ACTIVITY_REPORT)], ["period_start", "period_end"], PERIOD_BOUND)
    put([_node(NeoLabel.ACTIVITY_REPORT)], ["data_cutoff"], PERIOD_CUTOFF)
    put([_node(NeoLabel.ACTIVITY_REPORT)], ["annotation_updated_at"], LAPTOP_NATIVE)
    put([_node(NeoLabel.CHOICE)], ["completed_at", "decided_at"], CLIENT_STRING)
    put([_node(NeoLabel.CHOICE)], ["decision_deadline"], CLIENT_STRING_AHEAD)
    put([_node(NeoLabel.EVENT)], ["completed_at"], CLIENT_STRING)
    put([_node(NeoLabel.EVENT)], ["rescheduled_at"], TRUE_UTC_STRING)
    put(
        [_node(NeoLabel.HABIT)],
        [
            "last_completed",
            "completed_at",
            "last_break_date",
            "miss_pattern_updated_at",
            "started_at",
        ],
        CLIENT_STRING,
    )
    put([_node(NeoLabel.HABIT_COMPLETION)], ["completed_at"], CLIENT_STRING)
    put([_node(NeoLabel.GOAL)], ["last_progress_update"], CLIENT_STRING)
    put(
        [_node(NeoLabel.KU), _node(NeoLabel.PATH_STEP)],
        [
            "last_applied_date",
            "last_reflected_date",
            "last_practiced_date",
            "last_built_into_habit_date",
            "last_choice_informed_date",
        ],
        LAPTOP_NATIVE_OR_MIDNIGHT,
    )
    put(
        [_node(NeoLabel.PRODUCTIVITY_ANALYTICS)],
        ["first_completion_at", "last_completion_at"],
        PRODUCTIVITY_STAMP,
    )

    # --- relationships ------------------------------------------------------
    put([_rel(RelationshipName.OWNS)], ["created_at", "last_accessed"], OWNS_STAMP)
    put([_rel(RelationshipName.ENROLLED_IN)], ["enrolled_at"], TRUE_UTC)
    put([_rel(RelationshipName.ENROLLED_IN)], ["target_completion"], LAPTOP_STRING_AHEAD)
    for rel, props in (
        (RelationshipName.EXTRACTED_FROM, ["extracted_at"]),
        (RelationshipName.APPLIES_KNOWLEDGE, ["grounded_at"]),
        (RelationshipName.BOOKMARKED, ["bookmarked_at"]),
        (RelationshipName.MARKED_AS_READ, ["marked_at"]),
        (RelationshipName.IN_PROGRESS, ["started_at", "last_activity_at"]),
        (RelationshipName.VIEWED, ["first_viewed_at", "last_viewed_at"]),
        (RelationshipName.MASTERED, ["mastered_at"]),
        (RelationshipName.SPAWNED_FROM, ["spawned_at"]),
        (RelationshipName.ALIGNMENT_SNAPSHOT, ["recorded_at"]),
        (RelationshipName.ULTIMATE_PATH, ["alignment_updated_at"]),
        (RelationshipName.INTERESTED_IN, ["expressed_at"]),
    ):
        put([_rel(rel)], props, TRUE_UTC)
    put(
        [_rel(RelationshipName.ENGAGED_WITH)],
        ["since", "completed_at", "abandoned_at"],
        TRUE_UTC_STRING,
    )
    put([_rel(RelationshipName.ULTIMATE_PATH)], ["designated_at"], LAPTOP_STRING)
    put([_rel(RelationshipName.ASSIGNED_TO)], ["assigned_at"], LAPTOP_STRING)
    put([_rel(RelationshipName.MEMBER_OF)], ["joined_at"], MEMBER_OF_JOINED)
    put([_rel(RelationshipName.SHARES_WITH)], ["shared_at"], LAPTOP_NATIVE_OR_STRING)
    put(
        [
            _rel(RelationshipName.SHARED_WITH_GROUP),
            _rel(RelationshipName.SUBMITTED_TO_GROUP),
        ],
        ["shared_at", "submitted_at"],
        LAPTOP_NATIVE,
    )
    put([_rel(RelationshipName.ATTENDS)], ["joined_at"], LAPTOP_NATIVE)
    put([_rel(RelationshipName.EARNED_BADGE)], ["earned_at"], LAPTOP_NATIVE)
    return rules


RULES: dict[tuple[str, str], Rule] = _build_rules()

#: JSON properties that hold nested stamps. A path absent from both sets stops.
JSON_RULES: dict[tuple[str, str], JsonRule] = {
    (_node(NeoLabel.GOAL), "progress_history"): JsonRule(
        "goal progress history (the report counts its entries by date)",
        read={"$[].date": CLIENT_STRING},
    ),
    (_node(NeoLabel.GOAL), "metadata"): JsonRule(
        "goal metadata",
        read={"$.progress_notes[].date": CLIENT_STRING},
        diagnostic=frozenset({"$.archived_at"}),
    ),
    (_node(NeoLabel.ACTIVITY_REPORT), "metadata"): JsonRule(
        "activity report metadata (a copy of the period; no code compares it)",
        diagnostic=frozenset({"$.period_end", "$.data_cutoff", "$.review_date", "$.period_start"}),
    ),
    (_node(NeoLabel.TASK), "knowledge_inference_metadata"): JsonRule(
        "task inference metadata (written, never read)",
        diagnostic=frozenset({"$.inference_timestamp"}),
    ),
    (_node(NeoLabel.USER_ENTRY), "metadata"): JsonRule(
        "entry metadata (extraction timings, written, never read)",
        diagnostic=frozenset(
            {
                "$.activity_extraction.extraction_started_at",
                "$.activity_extraction.extraction_completed_at",
            }
        ),
    ),
}


@dataclass(frozen=True)
class Ruling:
    """Mike's ruling on one row no rule settles, keyed to its exact stored value."""

    owner: str
    prop: str
    key: tuple[str, ...]
    text: str
    verdict: Verdict
    reason: str


#: Rows ruled one by one (§ Migration contract, step 2: "stops the run for
#: Mike's ruling"). A changed value no longer matches and stops again.
RULINGS: tuple[Ruling, ...] = (
    Ruling(
        owner="(:EntryReport)",
        prop="updated_at",
        key=("key=er_e7ca22a9", "key_prop=uid", "match_label=Entity", "owner_label=EntryReport"),
        text="2026-08-01T17:10:51.959Z",
        verdict=Verdict.LEAVE,
        reason=(
            "true UTC — retitle_entry_reports.py's datetime(), run before #904 merged "
            "(2026-08-01 18:27Z); the row carries its 'Feedback on' title (ruled 2026-09-28)"
        ),
    ),
    Ruling(
        owner="[:MEMBER_OF]",
        prop="joined_at",
        key=(
            "end_label=Group",
            "end_uid=group_default_user_admin",
            "start_label=User",
            "start_uid=user_uxsmoke",
            "type=MEMBER_OF",
        ),
        text="2026-09-25T23:06:45.126Z",
        verdict=Verdict.LEAVE,
        reason=(
            "true UTC — the Submit & Share PR 6a live-case script's server stamp, 16:06 PDT, "
            "before that PR merged at 16:32 (ruled 2026-09-28)"
        ),
    ),
)


# =============================================================================
# THE CENSUS — read every stamp, classify it, build the manifest
# =============================================================================

# Every value that is, or may hold, a stamp: a temporal; a string that begins with
# a date and an hour, or is JSON; a list that holds either. Each type's test sits
# under its own CASE branch — Cypher does not promise to short-circuit AND, and a
# string function applied to a list raises.
_TEMPORAL_OR_STAMP_STRING = """
    CASE
      WHEN v IS :: STRING THEN
        v =~ '(?s)\\\\d{4}-\\\\d{2}-\\\\d{2}[T ]\\\\d{2}.*' OR left(v, 1) IN ['{', '[']
      WHEN v IS :: LIST<ANY> THEN
        any(x IN v WHERE CASE
          WHEN x IS :: STRING THEN x =~ '(?s)\\\\d{4}-\\\\d{2}-\\\\d{2}[T ]\\\\d{2}.*'
          ELSE x IS :: ZONED DATETIME OR x IS :: LOCAL DATETIME
        END)
      ELSE v IS :: ZONED DATETIME OR v IS :: LOCAL DATETIME OR v IS :: ZONED TIME
    END
"""

_VALUE_COLUMNS = """
       valueType(v) AS value_type,
       CASE
         WHEN v IS :: STRING THEN v
         WHEN v IS :: LIST<ANY> THEN 'a list of ' + toString(size(v)) + ' values'
         ELSE toString(v)
       END AS text,
       CASE WHEN v IS :: ZONED DATETIME THEN v.timezone END AS zone,
       CASE WHEN v IS :: ZONED DATETIME OR v IS :: LOCAL DATETIME THEN v.nanosecond END AS nanosecond
"""

# The migration's own record is its state, not part of the corpus it moves.
_NODE_STAMPS = f"""
MATCH (n) WHERE NOT n:{_RECORD}
UNWIND keys(n) AS prop
WITH n, prop, n[prop] AS v
WHERE {_TEMPORAL_OR_STAMP_STRING}
RETURN elementId(n) AS element, labels(n) AS labels, n.uid AS uid, n.user_uid AS user_uid,
       prop, {_VALUE_COLUMNS}
"""

_REL_STAMPS = f"""
MATCH (a)-[r]->(b)
UNWIND keys(r) AS prop
WITH a, r, b, prop, r[prop] AS v
WHERE {_TEMPORAL_OR_STAMP_STRING}
RETURN elementId(r) AS element, type(r) AS rel_type,
       a.uid AS start_uid, labels(a) AS start_labels,
       b.uid AS end_uid, labels(b) AS end_labels, prop, {_VALUE_COLUMNS}
"""

_RECORD_STATES = f"""
OPTIONAL MATCH (r:{_RECORD} {{name: $name}})
RETURN collect(r {{.state, .manifest_hash, .stamped}}) AS records
"""


@dataclass
class Stamp:
    """One stored value on one element, with what the census decided about it."""

    kind: Target
    element: str  # elementId — valid inside the census transaction only
    owner: str  # "(:Task)" or "[:OWNS]"
    prop: str
    value: Value
    key: ElementKey | None  # the durable key, None when the element has none
    labels: tuple[str, ...] = ()
    rule: str = ""
    verdict: Verdict = Verdict.STOP
    reason: str = ""
    new_text: str | None = None
    json_path: str | None = None
    # Relationship endpoints, for the MEMBER_OF pairing.
    end_uid: str | None = None
    start_uid: str | None = None


@dataclass
class Census:
    census_at: datetime
    laptop_now: datetime
    graph_uri: str
    stamps: list[Stamp] = field(default_factory=list)
    #: Whole-JSON manifest rows: one per containing property.
    json_rows: list[JsonRow] = field(default_factory=list)
    pairs: list[Pair] = field(default_factory=list)
    key_stops: list[str] = field(default_factory=list)

    @property
    def stops(self) -> list[Stamp]:
        return [s for s in self.stamps if s.verdict is Verdict.STOP]

    @property
    def shifts(self) -> list[Stamp]:
        return [s for s in self.stamps if s.verdict is Verdict.SHIFT and s.json_path is None]


def laptop_zone_for(digits: datetime) -> tzinfo | None:
    """The zone a laptop-clock stamp's digits are in, by their date; None on the change day."""
    day = digits.date()
    if day < ZONE_CHANGE_DAY:
        return PLUS_SEVEN
    if day == ZONE_CHANGE_DAY:
        return None
    return LAPTOP


def shift_digits(digits: datetime) -> tuple[datetime | None, str]:
    """A laptop-clock wall clock as naive UTC digits, or (None, why) when it cannot be read."""
    zone = laptop_zone_for(digits)
    if zone is None:
        return None, f"a laptop-clock stamp dated {ZONE_CHANGE_DAY} (the zone change day)"
    aware = digits.replace(tzinfo=zone)
    utc = aware.astimezone(UTC)
    if utc.astimezone(zone).replace(tzinfo=None) != digits:
        return None, "a wall clock that does not exist in the laptop's zone (a DST gap)"
    return utc.replace(tzinfo=None), ""


def native_text(digits: datetime) -> str:
    """A UTC native's text as Cypher ``toString`` prints it: the fraction without trailing zeros."""
    whole = digits.replace(microsecond=0).isoformat()
    fraction = f"{digits.microsecond:06d}".rstrip("0")
    return f"{whole}.{fraction}Z" if fraction else f"{whole}Z"


def shifted_text(value: Value, new_digits: datetime) -> str:
    """The shifted value in its own shape (R5): naive isoformat, or a native's ``toString`` text."""
    if value.cls in (ValueClass.STR_NAIVE_US, ValueClass.STR_NAIVE_S):
        return new_digits.isoformat()
    return native_text(new_digits)


def _owner_of(labels: Iterable[str], prop: str) -> tuple[str | None, str]:
    """The rule owner a node's labels give for ``prop`` — or (None, why)."""
    candidates = [
        _node(label)
        for label in labels
        if label != NeoLabel.ENTITY.value
        and ((_node(label), prop) in RULES or (_node(label), prop) in JSON_RULES)
    ]
    if len(candidates) == 1:
        return candidates[0], ""
    if not candidates:
        return None, "no rule for this label and property"
    return None, f"labels {sorted(candidates)} give more than one rule"


def _node_key(
    labels: Iterable[str], owner: str, uid: str | None, user_uid: str | None
) -> NodeKey | None:
    label = owner[2:-1]
    if uid:
        match_label = NeoLabel.ENTITY.value if NeoLabel.ENTITY.value in labels else label
        return {"match_label": match_label, "owner_label": label, "key_prop": "uid", "key": uid}
    if label == NeoLabel.PRODUCTIVITY_ANALYTICS.value and user_uid:
        # Its writer MERGEs on user_uid; it carries no uid.
        return {"match_label": label, "owner_label": label, "key_prop": "user_uid", "key": user_uid}
    return None


def _endpoint_label(labels: Iterable[str]) -> str:
    labels = list(labels)
    for preferred in (NeoLabel.USER.value, NeoLabel.ENTITY.value):
        if preferred in labels:
            return preferred
    return labels[0] if labels else ""


def _json_stamps(obj: Any, path: str = "$") -> list[tuple[str, str]]:  # boundary: decoded JSON
    """Every ISO-datetime string nested in a parsed JSON value, with its normalized path."""
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(_json_stamps(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_json_stamps(v, f"{path}[]"))
    elif isinstance(obj, str) and classify_stamp_string(obj) is not None:
        found.append((path, obj))
    return found


def _decide(stamp: Stamp, rule: Rule, laptop_now: datetime) -> None:
    """Fill in a stamp's verdict, reason and new value under ``rule``."""
    stamp.rule = rule.name
    verdict = rule.verdict(stamp.value.cls)
    if verdict is Verdict.STOP:
        stamp.verdict = Verdict.STOP
        stamp.reason = f"{stamp.value.cls} is not a shape this property's writers produce"
        return
    if verdict is Verdict.LEAVE:
        stamp.verdict = Verdict.LEAVE
        return
    digits = stamp.value.digits
    assert digits is not None
    if stamp.value.cls.name.startswith("NATIVE") and not stamp.value.offset_zone:
        stamp.verdict = Verdict.STOP
        stamp.reason = "a laptop-clock native carrying a zone id, not an offset"
        return
    new_digits, why = shift_digits(digits)
    if new_digits is None:
        stamp.verdict, stamp.reason = Verdict.STOP, why
        return
    if rule.stamped_now and digits > laptop_now:
        stamp.verdict = Verdict.STOP
        stamp.reason = (
            f"stamped 'now' with digits later than the laptop's wall clock ({laptop_now:%Y-%m-%dT%H:%M}) "
            "— a UTC-clock process wrote it"
        )
        return
    stamp.verdict = Verdict.SHIFT
    stamp.new_text = shifted_text(stamp.value, new_digits)


def _apply_ruling(stamp: Stamp) -> bool:
    key = tuple(sorted((stamp.key or {}).items()))
    flat = tuple(f"{k}={v}" for k, v in key)
    for ruling in RULINGS:
        if (ruling.owner, ruling.prop, ruling.key, ruling.text) == (
            stamp.owner,
            stamp.prop,
            flat,
            stamp.value.text,
        ):
            stamp.rule = f"Mike's ruling: {ruling.reason}"
            if ruling.verdict is Verdict.SHIFT:
                assert stamp.value.digits is not None
                new_digits, why = shift_digits(stamp.value.digits)
                if new_digits is None:
                    stamp.verdict, stamp.reason = Verdict.STOP, why
                    return True
                stamp.new_text = shifted_text(stamp.value, new_digits)
            stamp.verdict = ruling.verdict
            stamp.reason = ""
            return True
    return False


def _member_of_pairing(
    stamp: Stamp,
    group_created: Mapping[str, str],
    in_progress: Mapping[str, list[str]],
    laptop_now: datetime,
) -> None:
    """Settle ``MEMBER_OF.joined_at`` by provenance that does not depend on its clock.

    A non-default group is reached only by ``GroupService.add_member`` (naive, a
    laptop native). A default group is reached by both; a row there is the
    enrollment handler's (aware) only when a stamp the enrollment wrote in the
    same moment pairs with it — the group's ``created_at`` when the handler created
    the group, or the member's ``IN_PROGRESS`` stamp just before.
    """
    stamp.rule = MEMBER_OF_JOINED.name
    group = stamp.end_uid or ""
    if not group.startswith(DEFAULT_GROUP_UID_PREFIX):
        _decide(stamp, LAPTOP_NATIVE, laptop_now)
        stamp.rule = f"{MEMBER_OF_JOINED.name}: a non-default group (add_member)"
        return
    if stamp.value.cls is not ValueClass.NATIVE_US:
        stamp.verdict = Verdict.STOP
        stamp.reason = f"{stamp.value.cls} on a default group: neither writer's shape"
        return
    joined = stamp.value.digits
    assert joined is not None
    if group_created.get(group) == stamp.value.text:
        stamp.verdict = Verdict.LEAVE
        stamp.rule = f"{MEMBER_OF_JOINED.name}: paired with the group's created_at (handler)"
        return
    for started in in_progress.get(stamp.start_uid or "", []):
        other = _instant(started).replace(tzinfo=None)
        if timedelta(0) <= joined - other <= timedelta(seconds=5):
            stamp.verdict = Verdict.LEAVE
            stamp.rule = f"{MEMBER_OF_JOINED.name}: paired with an IN_PROGRESS stamp (handler)"
            return
    stamp.verdict = Verdict.STOP
    stamp.reason = "a default-group row no paired stamp settles (add_member or the handler)"


async def _fetch(
    tx: AsyncTransaction,
    query: str,
    **params: Any,  # boundary: query parameters — heterogeneous Neo4j values
) -> list[Row]:
    result = await tx.run(query, **params)
    return [dict(record) async for record in result]


async def read_record_states(tx: AsyncTransaction) -> list[RecordState]:
    rows = await _fetch(tx, _RECORD_STATES, name=UTC_INSTANTS_MIGRATION)
    return cast("list[RecordState]", list(rows[0]["records"])) if rows else []


def _state_refusal(
    records: list[RecordState], *, allowed: set[MigrationState | None]
) -> str | None:
    """Why the record's state refuses this run, or None. ``None`` in ``allowed`` is no record."""
    if len(records) > 1:
        return f"the graph holds {len(records)} {_RECORD} nodes named {UTC_INSTANTS_MIGRATION!r}"
    state: MigrationState | None = None
    if records:
        stored = records[0].get("state")
        state = MigrationState.from_stored(stored)
        if state is None:
            return f"the {_RECORD} {UTC_INSTANTS_MIGRATION!r} is in an unknown state {stored!r}"
    if state not in allowed:
        return f"the {_RECORD} {UTC_INSTANTS_MIGRATION!r} is in state {state.value if state else None!r}"
    return None


async def run_census(
    tx: AsyncTransaction, graph_uri: str, laptop_now: datetime | None = None
) -> Census:
    """Read and classify every stored stamp, in one read transaction."""
    census = Census(
        census_at=datetime.now(UTC),
        laptop_now=laptop_now or datetime.now(LAPTOP).replace(tzinfo=None),
        graph_uri=graph_uri,
    )
    group_created: dict[str, str] = {}
    in_progress: dict[str, list[str]] = defaultdict(list)
    member_rows: list[Stamp] = []

    for row in await _fetch(tx, _NODE_STAMPS):
        labels = tuple(row["labels"])
        prop = str(row["prop"])
        owner, why = _owner_of(labels, prop)
        text = str(row["text"])
        if row["value_type"].startswith("LIST"):
            value = Value(text, ValueClass.LIST_OF_STAMPS, None)
        elif row["value_type"].startswith("STRING"):
            found = classify_stamp_string(text)
            if found is None:
                if text[:1] in "[{":
                    _json_census(census, row, labels, owner, why)
                continue
            value = found
        else:
            value = classify_native(
                row["value_type"], text, row["zone"], int(row["nanosecond"] or 0)
            )
        if NeoLabel.GROUP.value in labels and prop == "created_at" and row["uid"]:
            group_created[str(row["uid"])] = text
        key = _node_key(labels, owner, row["uid"], row["user_uid"]) if owner else None
        stamp = Stamp(
            "node", str(row["element"]), owner or _node("|".join(labels)), prop, value, key, labels
        )
        census.stamps.append(stamp)
        if _apply_ruling(stamp):
            continue
        if owner is None:
            stamp.reason = why
            continue
        _decide(stamp, RULES[(owner, prop)], census.laptop_now)

    for row in await _fetch(tx, _REL_STAMPS):
        rel_type, prop, text = str(row["rel_type"]), str(row["prop"]), str(row["text"])
        owner = _rel(rel_type)
        if row["value_type"].startswith("LIST"):
            value = Value(text, ValueClass.LIST_OF_STAMPS, None)
        elif row["value_type"].startswith("STRING"):
            found = classify_stamp_string(text)
            if found is None:
                _rel_json_census(census, row, owner, prop, text)
                continue
            value = found
        else:
            value = classify_native(
                row["value_type"], text, row["zone"], int(row["nanosecond"] or 0)
            )
        if (
            rel_type == RelationshipName.IN_PROGRESS.value
            and row["start_uid"]
            and value.cls.name.startswith("NATIVE")
        ):
            in_progress[str(row["start_uid"])].append(text)
        rel_key: RelKey | None = None
        if row["start_uid"] and row["end_uid"]:
            rel_key = RelKey(
                type=rel_type,
                start_label=_endpoint_label(row["start_labels"]),
                start_uid=str(row["start_uid"]),
                end_label=_endpoint_label(row["end_labels"]),
                end_uid=str(row["end_uid"]),
            )
        stamp = Stamp(
            "rel",
            str(row["element"]),
            owner,
            prop,
            value,
            rel_key,
            start_uid=row["start_uid"],
            end_uid=row["end_uid"],
        )
        census.stamps.append(stamp)
        if _apply_ruling(stamp):
            continue
        rule = RULES.get((owner, prop))
        if rule is None:
            stamp.reason = "no rule for this relationship type and property"
            continue
        if rule.paired:
            member_rows.append(stamp)
            continue
        _decide(stamp, rule, census.laptop_now)

    for stamp in member_rows:
        _member_of_pairing(stamp, group_created, in_progress, census.laptop_now)

    await _check_keys(tx, census)
    _find_pairs(census)
    return census


def _rel_json_census(census: Census, row: Row, owner: str, prop: str, text: str) -> None:
    """A relationship's JSON property holding stamps stops the census: no rule classifies one."""
    if text[:1] not in "[{":
        return
    try:
        parsed = json.loads(text)
    except ValueError:
        return
    for path, stamp_text in _json_stamps(parsed):
        value = classify_stamp_string(stamp_text)
        assert value is not None
        stamp = Stamp("rel", str(row["element"]), owner, prop, value, None, json_path=path)
        stamp.reason = "a JSON property on a relationship holding stamps: no rule classifies it"
        census.stamps.append(stamp)


def _json_census(
    census: Census, row: Row, labels: tuple[str, ...], owner: str | None, why: str
) -> None:
    """Classify the stamps nested in one JSON property; add its manifest row when any moves."""
    text = str(row["text"])
    try:
        parsed = json.loads(text)
    except ValueError:
        return
    nested = _json_stamps(parsed)
    if not nested:
        return
    prop = str(row["prop"])
    json_rule = JSON_RULES.get((owner, prop)) if owner else None
    key = _node_key(labels, owner, row["uid"], row["user_uid"]) if owner else None
    moved: list[JsonChange] = []
    for path, stamp_text in nested:
        value = classify_stamp_string(stamp_text)
        assert value is not None
        stamp = Stamp(
            "node",
            str(row["element"]),
            owner or _node("|".join(labels)),
            prop,
            value,
            key,
            labels,
            json_path=path,
        )
        census.stamps.append(stamp)
        if json_rule is None:
            stamp.reason = (
                why if owner is None else "a JSON property holding stamps no rule classifies"
            )
            continue
        if path in json_rule.diagnostic:
            stamp.rule, stamp.verdict = f"{json_rule.name} (diagnostic)", Verdict.LEAVE
            continue
        inner = json_rule.read.get(path)
        if inner is None:
            stamp.reason = "a JSON-nested stamp classified neither read nor diagnostic"
            continue
        _decide(stamp, inner, census.laptop_now)
        stamp.rule = f"{json_rule.name}: {inner.name}"
        if stamp.verdict is Verdict.SHIFT and stamp.new_text is not None:
            moved.append({"path": path, "old": stamp_text, "new": stamp.new_text})
    if not moved or any(
        s.verdict is Verdict.STOP
        for s in census.stamps
        if s.element == str(row["element"]) and s.prop == prop
    ):
        return
    if json.dumps(parsed) != text:
        census.key_stops.append(
            f"{owner}.{prop} on {key}: its JSON does not re-serialize to the stored text, "
            "so its digits cannot be moved alone"
        )
        return
    if owner is None or key is None:
        return  # its moving stamps stop on the missing key (_check_keys)
    new_text = json.dumps(_replace_stamps(parsed, {(m["path"], m["old"]): m["new"] for m in moved}))
    census.json_rows.append(
        {
            "element": str(row["element"]),
            "owner": owner,
            "prop": prop,
            "key": key,
            "old": text,
            "new": new_text,
            "changes": moved,
        }
    )


def _replace_stamps(  # boundary: decoded JSON in, re-encodable JSON out
    obj: Any, moves: Mapping[tuple[str, str], str], path: str = "$"
) -> Any:
    """``obj`` with each stamp that moves replaced where it moves — by its path and text.

    The same text at another path (a diagnostic copy of a date the report reads,
    say) is left as it is: the census classified it there.
    """
    if isinstance(obj, dict):
        return {k: _replace_stamps(v, moves, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_stamps(v, moves, f"{path}[]") for v in obj]
    if isinstance(obj, str) and (path, obj) in moves:
        return moves[(path, obj)]
    return obj


_NODE_KEY_COUNT = """
UNWIND $keys AS k
CALL (k) {{
  MATCH (n:{label} {{{key_prop}: k.key}})
  RETURN collect(elementId(n)) AS elements
}}
RETURN k.key AS key, elements
"""

_REL_KEY_COUNT = """
UNWIND $keys AS k
CALL (k) {{
  MATCH (:{start} {{uid: k.start_uid}})-[r:{rel_type}]->(:{end} {{uid: k.end_uid}})
  RETURN collect(elementId(r)) AS elements
}}
RETURN k.start_uid AS start_uid, k.end_uid AS end_uid, elements
"""


def _safe(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"not a Cypher identifier: {name!r}")
    return name


def _elements_by_key() -> defaultdict[str, set[str]]:
    return defaultdict(set)


async def _check_keys(tx: AsyncTransaction, census: Census) -> None:
    """Every moving value's durable key names exactly the element the census read."""
    movers = [s for s in census.stamps if s.verdict is Verdict.SHIFT]
    for stamp in movers:
        if stamp.key is None:
            stamp.verdict = Verdict.STOP
            stamp.reason = "the element has no durable key (no uid, no merge key)"
    by_group: dict[tuple[str, ...], dict[str, set[str]]] = defaultdict(_elements_by_key)
    for stamp in movers:
        if stamp.key is None:
            continue
        group: tuple[str, ...]
        if stamp.kind == "node":
            node_key = cast("NodeKey", stamp.key)
            group = ("node", node_key["match_label"], node_key["key_prop"])
            by_group[group][node_key["key"]].add(stamp.element)
        else:
            rel_key = cast("RelKey", stamp.key)
            group = ("rel", rel_key["start_label"], rel_key["type"], rel_key["end_label"])
            by_group[group][f"{rel_key['start_uid']}\u0000{rel_key['end_uid']}"].add(stamp.element)
    for group, wanted in by_group.items():
        if group[0] == "node":
            query = _NODE_KEY_COUNT.format(label=_safe(group[1]), key_prop=_safe(group[2]))
            rows = await _fetch(tx, query, keys=[{"key": k} for k in wanted])
            found = {str(r["key"]): set(r["elements"]) for r in rows}
        else:
            query = _REL_KEY_COUNT.format(
                start=_safe(group[1]), rel_type=_safe(group[2]), end=_safe(group[3])
            )
            pairs = [
                dict(zip(("start_uid", "end_uid"), k.split("\u0000"), strict=True)) for k in wanted
            ]
            rows = await _fetch(tx, query, keys=pairs)
            found = {f"{r['start_uid']}\u0000{r['end_uid']}": set(r["elements"]) for r in rows}
        for key, elements in wanted.items():
            resolved = found.get(key, set())
            if len(resolved) != 1 or resolved != elements:
                census.key_stops.append(
                    f"{group}: key {key.replace(chr(0), ' -> ')} resolves to {len(resolved)} element(s)"
                )


def _find_pairs(census: Census) -> None:
    """The classification check's pairs: a moving ``created_at`` string and a server
    ``embedding_updated_at`` on the same node, written in the same moment (7 h apart
    on the laptop's summer clock)."""
    embeds = {
        s.element: s
        for s in census.stamps
        if s.prop == "embedding_updated_at"
        and s.value.cls in (ValueClass.NATIVE_MS, ValueClass.NATIVE_S)
    }
    for stamp in census.shifts:
        if stamp.prop != "created_at" or stamp.kind != "node" or stamp.element not in embeds:
            continue
        embed = embeds[stamp.element]
        assert stamp.value.digits is not None and embed.value.digits is not None
        assert stamp.new_text is not None
        if abs(embed.value.digits - stamp.value.digits - PAIR_OFFSET) <= PAIR_TOLERANCE:
            census.pairs.append(
                Pair(
                    key=cast("NodeKey", stamp.key),
                    created_at_old=stamp.value.text,
                    created_at_new=stamp.new_text,
                    embedding_updated_at=embed.value.text,
                )
            )


# =============================================================================
# THE MANIFEST — immutable, content-addressed, outside the tracked tree
# =============================================================================


def default_manifest_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "skuel" / UTC_INSTANTS_MIGRATION


def _row_order(row: ManifestRow) -> tuple[str, str, str, str]:
    return (row["owner"], row["property"], json.dumps(row["key"], sort_keys=True), row["old"])


def build_manifest(census: Census) -> Manifest:
    rows: list[ManifestRow] = []
    for stamp in census.shifts:
        assert stamp.key is not None and stamp.new_text is not None
        rows.append(
            {
                "id": 0,  # numbered once the rows are ordered
                "target": stamp.kind,
                "owner": stamp.owner,
                "key": stamp.key,
                "property": stamp.prop,
                "shape": "native" if stamp.value.cls.name.startswith("NATIVE") else "string",
                "old": stamp.value.text,
                "new": stamp.new_text,
                "rule": stamp.rule,
            }
        )
    rows.extend(
        {
            "id": 0,
            "target": "node",
            "owner": json_row["owner"],
            "key": json_row["key"],
            "property": json_row["prop"],
            "shape": "json",
            "old": json_row["old"],
            "new": json_row["new"],
            "rule": "JSON-nested stamps",
            "changes": json_row["changes"],
        }
        for json_row in census.json_rows
    )
    rows.sort(key=_row_order)
    for index, row in enumerate(rows):
        row["id"] = index
    counts = Counter(r["rule"] for r in rows)
    left = Counter(s.rule for s in census.stamps if s.verdict is Verdict.LEAVE)
    return {
        "migration": UTC_INSTANTS_MIGRATION,
        "format": MANIFEST_FORMAT,
        "graph_uri": census.graph_uri,
        "census_at": census.census_at.isoformat(),
        "laptop_wall_clock_at_census": census.laptop_now.isoformat(),
        "counts": dict(sorted(counts.items())),
        "left": dict(sorted(left.items())),
        "pairs": census.pairs,
        "rows": rows,
    }


def manifest_bytes(manifest: Manifest) -> bytes:
    return (json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def manifest_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_manifest(manifest: Manifest, directory: Path) -> tuple[Path, str]:
    data = manifest_bytes(manifest)
    digest = manifest_hash(data)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"manifest-{digest}.json"
    if not path.exists():
        path.write_bytes(data)
    return path, digest


class ManifestError(RuntimeError):
    """The manifest named cannot be applied: missing, altered, or not this migration's."""


def load_manifest(directory: Path, digest: str) -> Manifest:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ManifestError(f"not a manifest hash (64 hex digits): {digest!r}")
    path = directory / f"manifest-{digest}.json"
    if not path.exists():
        raise ManifestError(f"no manifest {path}")
    data = path.read_bytes()
    if manifest_hash(data) != digest:
        raise ManifestError(f"{path} does not hash to {digest}: the file was altered")
    # boundary: the file this script wrote, checked by its hash above
    manifest = cast("Manifest", json.loads(data))
    if (
        manifest.get("migration") != UTC_INSTANTS_MIGRATION
        or manifest.get("format") != MANIFEST_FORMAT
    ):
        raise ManifestError(
            f"{path} is not a format-{MANIFEST_FORMAT} {UTC_INSTANTS_MIGRATION} manifest"
        )
    return manifest


# =============================================================================
# APPLY, REVERT, VERIFY — compare-and-set over the manifest, one transaction
# =============================================================================


def _typed(shape: str, text: str) -> Any:  # boundary: a string or a driver-bound datetime
    """A manifest value as the parameter the driver binds: a string, or an aware UTC datetime."""
    if shape == "native":
        return datetime.fromisoformat(text.split("[", 1)[0]).astimezone(UTC)
    return text


def _cas(prop: str, shape: str, side: str) -> str:
    """The expression that holds when the element's property still equals ``row.<side>``."""
    if shape == "native":
        # toString only under the type test: Cypher does not promise to short-circuit AND.
        return (
            f"CASE WHEN n.{prop} IS :: ZONED DATETIME "
            f"THEN n.{prop} = row.{side} AND toString(n.{prop}) = row.{side}_text "
            f"ELSE false END"
        )
    return f"n.{prop} = row.{side}"


def _group_statement(group: tuple[str, ...], *, write: bool, expect: str) -> str:
    """One statement for one group of manifest rows: compare, and set when ``write``."""
    target, prop, shape = group[0], _safe(group[-2]), group[-1]
    if target == "node":
        _, match_label, owner_label, key_prop, *_ = group
        match = (
            f"OPTIONAL MATCH (n:{_safe(match_label)} {{{_safe(key_prop)}: row.key}}) "
            f"WHERE '{_safe(owner_label)}' IN labels(n)"
        )
    else:
        _, start, rel_type, end, *_ = group
        match = (
            f"OPTIONAL MATCH (:{_safe(start)} {{uid: row.start_uid}})"
            f"-[n:{_safe(rel_type)}]->(:{_safe(end)} {{uid: row.end_uid}})"
        )
    other = "new" if expect == "old" else "old"
    setter = (
        f"FOREACH (_ IN CASE WHEN ok THEN [1] ELSE [] END | SET n.{prop} = row.{other}) "
        if write
        else ""
    )
    return (
        f"UNWIND $rows AS row {match} "
        f"WITH row, n, (n IS NOT NULL AND {_cas(prop, shape, expect)}) AS ok "
        f"{setter}RETURN row.id AS id, ok"
    )


def _groups(rows: Iterable[ManifestRow]) -> dict[tuple[str, ...], list[Row]]:
    grouped: dict[tuple[str, ...], list[Row]] = defaultdict(list)
    for row in rows:
        key = row["key"]
        shape = "native" if row["shape"] == "native" else "string"
        params: Row = {
            "id": row["id"],
            "old": _typed(shape, row["old"]),
            "new": _typed(shape, row["new"]),
            "old_text": row["old"],
            "new_text": row["new"],
        }
        if row["target"] == "node":
            node_key = cast("NodeKey", key)
            group = (
                "node",
                node_key["match_label"],
                node_key["owner_label"],
                node_key["key_prop"],
                row["property"],
                shape,
            )
            params["key"] = node_key["key"]
        else:
            rel_key = cast("RelKey", key)
            group = (
                "rel",
                rel_key["start_label"],
                rel_key["type"],
                rel_key["end_label"],
                row["property"],
                shape,
            )
            params["start_uid"], params["end_uid"] = rel_key["start_uid"], rel_key["end_uid"]
        grouped[group].append(params)
    return grouped


async def compare_and_set(
    tx: AsyncTransaction, rows: list[ManifestRow], *, forward: bool
) -> list[int]:
    """Set every row old → new (``forward``) or new → old where it still holds the other; return the ids that did not."""
    expect = "old" if forward else "new"
    unmatched: list[int] = []
    for group, params in _groups(rows).items():
        statement = _group_statement(group, write=True, expect=expect)
        results = await _fetch(tx, statement, rows=params)
        unmatched.extend(int(result["id"]) for result in results if not result["ok"])
    return sorted(unmatched)


async def rows_not_at(tx: AsyncTransaction, rows: list[ManifestRow], side: str) -> list[int]:
    """The ids of manifest rows whose element does not hold the ``side`` value (read-only)."""
    missing: list[int] = []
    for group, params in _groups(rows).items():
        statement = _group_statement(group, write=False, expect=side)
        results = await _fetch(tx, statement, rows=params)
        missing.extend(int(result["id"]) for result in results if not result["ok"])
    return sorted(missing)


_RECORD_APPLIED = f"""
MERGE (r:{_RECORD} {{name: $name}})
SET r.state = $applied, r.manifest_hash = $hash, r.rows = $rows, r.counts = $counts,
    r.census_at = $census_at, r.applied_at = datetime()
REMOVE r.stamped
RETURN r.state AS state
"""

_RECORD_REVERTED = f"""
MATCH (r:{_RECORD} {{name: $name}})
WHERE r.state = $applied AND r.manifest_hash = $hash
SET r.state = $reverted, r.reverted_at = datetime()
RETURN count(r) AS n
"""


class RefusedError(RuntimeError):
    """The run is refused: the graph's state or the manifest does not allow it; nothing written."""


class ConflictError(RuntimeError):
    """A value changed since the census; the transaction was rolled back."""

    def __init__(self, ids: list[int]) -> None:
        super().__init__(f"{len(ids)} row(s) no longer hold the value the manifest expects")
        self.ids = ids


async def confirm(driver: AsyncDriver, manifest: Manifest, digest: str, graph_uri: str) -> None:
    """Apply the manifest in one transaction and record it ``applied``."""
    if manifest["graph_uri"] != graph_uri:
        raise RefusedError(f"the manifest was taken on {manifest['graph_uri']}, not {graph_uri}")
    await ensure_record_name_is_unique(driver)
    async with driver.session() as session:
        tx = await session.begin_transaction()
        try:
            refusal = _state_refusal(
                await read_record_states(tx), allowed={None, MigrationState.REVERTED}
            )
            if refusal:
                raise RefusedError(refusal)
            unmatched = await compare_and_set(tx, list(manifest["rows"]), forward=True)
            if unmatched:
                raise ConflictError(unmatched)
            await _fetch(
                tx,
                _RECORD_APPLIED,
                name=UTC_INSTANTS_MIGRATION,
                applied=MigrationState.APPLIED.value,
                hash=digest,
                rows=len(manifest["rows"]),
                counts=json.dumps(manifest["counts"], sort_keys=True),
                census_at=manifest["census_at"],
            )
            await tx.commit()
        finally:
            if not tx.closed():
                await tx.rollback()


async def revert(driver: AsyncDriver, directory: Path) -> Manifest:
    """Undo the applied manifest in one transaction and record it ``reverted``."""
    async with driver.session() as session:
        tx = await session.begin_transaction()
        try:
            records = await read_record_states(tx)
            refusal = _state_refusal(records, allowed={MigrationState.APPLIED})
            if refusal:
                raise RefusedError(refusal)
            digest = records[0].get("manifest_hash")
            if not digest:
                raise RefusedError(
                    f"the {_RECORD} was stamped on an empty graph: there is nothing to undo"
                )
            manifest = load_manifest(directory, str(digest))
            unmatched = await compare_and_set(tx, list(manifest["rows"]), forward=False)
            if unmatched:
                raise ConflictError(unmatched)
            done = await _fetch(
                tx,
                _RECORD_REVERTED,
                name=UTC_INSTANTS_MIGRATION,
                applied=MigrationState.APPLIED.value,
                reverted=MigrationState.REVERTED.value,
                hash=digest,
            )
            if not done or done[0]["n"] != 1:
                raise RefusedError("the record changed during the revert")
            await tx.commit()
            return manifest
        finally:
            if not tx.closed():
                await tx.rollback()


@dataclass
class Verification:
    manifest_hash: str
    rows: int
    not_at_new: list[int]
    pairs: int
    pairs_apart_before: int
    pairs_together_after: int

    @property
    def ok(self) -> bool:
        return (
            not self.not_at_new
            and self.pairs_apart_before == self.pairs
            and self.pairs_together_after == self.pairs
        )


_PAIR_READ = """
UNWIND $keys AS k
OPTIONAL MATCH (n:{label} {{uid: k}})
RETURN k AS uid, toString(n.created_at) AS created_at, toString(n.embedding_updated_at) AS embedding
"""


async def verify(driver: AsyncDriver, directory: Path) -> Verification:
    """Every manifest row at its new value, the record applied, and the pairs together.

    A pair was 7.00 h apart in the census's reading; after the move, its node's
    ``created_at`` and ``embedding_updated_at`` — both read from the graph now —
    are about 0 h apart.
    """
    async with driver.session() as session:
        tx = await session.begin_transaction()
        try:
            records = await read_record_states(tx)
            refusal = _state_refusal(records, allowed={MigrationState.APPLIED})
            if refusal:
                raise RefusedError(refusal)
            digest = records[0].get("manifest_hash")
            if not digest:
                raise RefusedError(
                    f"the {_RECORD} was stamped on an empty graph: there is no manifest"
                )
            manifest = load_manifest(directory, str(digest))
            not_at_new = await rows_not_at(tx, list(manifest["rows"]), "new")
            pairs = list(manifest["pairs"])
            apart = together = 0
            by_label: dict[str, list[Pair]] = defaultdict(list)
            for pair in pairs:
                by_label[pair["key"]["match_label"]].append(pair)
            for label, group in by_label.items():
                query = _PAIR_READ.format(label=_safe(label))
                live = {
                    r["uid"]: r
                    for r in await _fetch(tx, query, keys=[p["key"]["key"] for p in group])
                }
                for pair in group:
                    # Before: the two values as the census read them.
                    census_embed = _instant(pair["embedding_updated_at"])
                    if (
                        abs(census_embed - _instant(pair["created_at_old"]) - PAIR_OFFSET)
                        <= PAIR_TOLERANCE
                    ):
                        apart += 1
                    # After: both values as the graph holds them now.
                    now = live.get(pair["key"]["key"], {})
                    now_created, now_embed = now.get("created_at"), now.get("embedding")
                    if (
                        now_created
                        and now_embed
                        and abs(_instant(now_embed) - _instant(now_created)) <= PAIR_TOLERANCE
                    ):
                        together += 1
            return Verification(
                str(digest), len(manifest["rows"]), not_at_new, len(pairs), apart, together
            )
        finally:
            if not tx.closed():
                await tx.rollback()


def _instant(text: str) -> datetime:
    """A stored stamp's text as an aware instant — an offset-less one on the (UTC) stored clock."""
    parsed = datetime.fromisoformat(text.split("[", 1)[0])
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# =============================================================================
# REPORTING
# =============================================================================


def print_census(census: Census, out: Callable[[str], None] = print) -> None:
    by_rule: dict[tuple[Verdict, str], list[Stamp]] = defaultdict(list)
    for stamp in census.stamps:
        by_rule[(stamp.verdict, stamp.rule or "(no rule)")].append(stamp)
    out(f"Census at {census.census_at:%Y-%m-%dT%H:%M:%SZ} of {census.graph_uri}")
    out(f"Laptop wall clock: {census.laptop_now:%Y-%m-%dT%H:%M:%S} (America/Vancouver)")
    out(f"Values read: {len(census.stamps)}")
    for verdict in (Verdict.SHIFT, Verdict.LEAVE):
        rules = sorted((rule, stamps) for (v, rule), stamps in by_rule.items() if v is verdict)
        total = sum(len(stamps) for _, stamps in rules)
        out(f"\n{verdict.upper()}: {total}")
        for rule, stamps in rules:
            props = Counter(f"{s.owner}.{s.prop}{s.json_path or ''}" for s in stamps)
            out(f"  {len(stamps):>5}  {rule}")
            for prop, n in sorted(props.items()):
                out(f"         {n:>4}  {prop}")
            if verdict is Verdict.SHIFT:
                for sample in stamps[:3]:
                    out(f"         e.g. {sample.value.text} -> {sample.new_text}")
    if census.pairs:
        out(
            f"\nClassification check: {len(census.pairs)} nodes whose created_at and server "
            "embedding_updated_at were written together read 7.00 h apart; --verify expects ~0 h after."
        )
    stops = census.stops
    if stops or census.key_stops:
        out(f"\nSTOP: {len(stops) + len(census.key_stops)} value(s) no rule settles")
        for stamp in stops:
            where = json.dumps(stamp.key, sort_keys=True) if stamp.key else stamp.element
            out(
                f"  {stamp.owner}.{stamp.prop}{stamp.json_path or ''} = {stamp.value.text!r} "
                f"[{stamp.value.cls}] on {where}: {stamp.reason}"
            )
        for reason in census.key_stops:
            out(f"  {reason}")


# =============================================================================
# CLI
# =============================================================================


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate every stored instant to UTC (ADR-089)")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--confirm", metavar="HASH", help="apply the manifest with this hash")
    action.add_argument("--verify", action="store_true", help="check the applied manifest")
    action.add_argument("--revert", action="store_true", help="undo the applied manifest")
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=default_manifest_dir(),
        help=f"where manifests are kept (default {default_manifest_dir()})",
    )
    args = parser.parse_args(argv)

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    connection = Neo4jConnection(utc_instants_guard=False)
    driver = await connection.connect()
    try:
        if args.verify:
            result = await verify(driver, args.manifest_dir)
            print(f"Manifest {result.manifest_hash}: {result.rows} rows")
            print(
                f"  rows not at their new value: {len(result.not_at_new)} {result.not_at_new[:20]}"
            )
            print(f"  pairs read 7.00 h apart before: {result.pairs_apart_before}/{result.pairs}")
            print(f"  pairs read together now:        {result.pairs_together_after}/{result.pairs}")
            print("\nOK" if result.ok else "\nFAILED")
            return 0 if result.ok else 1
        if args.revert:
            manifest = await revert(driver, args.manifest_dir)
            print(
                f"Reverted {len(manifest['rows'])} value(s) in one transaction; the record is 'reverted'."
            )
            return 0
        if args.confirm:
            manifest = load_manifest(args.manifest_dir, args.confirm)
            await confirm(driver, manifest, args.confirm, connection.uri)
            print(
                f"Applied {len(manifest['rows'])} value(s) in one transaction; the record is 'applied'."
            )
            print("Next: --verify.")
            return 0

        async with driver.session(default_access_mode="READ") as session:
            tx = await session.begin_transaction()
            try:
                refusal = _state_refusal(
                    await read_record_states(tx), allowed={None, MigrationState.REVERTED}
                )
                if refusal:
                    print(f"REFUSED: {refusal}. Nothing written.")
                    return 1
                census = await run_census(tx, connection.uri)
            finally:
                await tx.rollback()
        print_census(census)
        if census.stops or census.key_stops:
            print(
                "\nREFUSED: no manifest written. Each row above waits on a rule or Mike's ruling."
            )
            return 2
        path, digest = write_manifest(build_manifest(census), args.manifest_dir)
        print(f"\nManifest: {path}")
        print(f"Hash:     {digest}")
        print(
            f"\nCENSUS ONLY: nothing written to the graph. With Mike's OK on the counts:\n"
            f"  --confirm {digest}"
        )
        return 0
    except (RefusedError, ManifestError) as refused:
        print(f"REFUSED: {refused}. Nothing written.")
        return 1
    except ConflictError as conflict:
        print(f"FAILED: {conflict}; the transaction was rolled back and nothing was written.")
        print(f"  manifest row ids: {conflict.ids[:50]}")
        return 1
    finally:
        await connection.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
