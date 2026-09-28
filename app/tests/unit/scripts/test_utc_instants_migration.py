"""The UTC instants migration's classifier, shifts, rules and manifest — no graph.

``scripts/migrations/utc_instants_2026_10.py`` decides every stored value by its
(label or type, property) rule, its shape and its precision, reads a laptop-clock
stamp in the zone its date gives, and keeps each value's shape. These tests pin
each rule's verdicts, each stop case and the manifest's integrity; the
integration test (tests/integration/migrations/test_utc_instants_migration.py)
runs the whole census → confirm → verify → revert on a real graph.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "migrations" / "utc_instants_2026_10.py"
_spec = importlib.util.spec_from_file_location("utc_instants_2026_10", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration
_spec.loader.exec_module(migration)

VC = migration.ValueClass
S, L, X = migration.Verdict.SHIFT, migration.Verdict.LEAVE, migration.Verdict.STOP
LAPTOP_NOW = datetime(2026, 9, 28, 8, 0)


# ---------------------------------------------------------------------------
# Value classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cls"),
    [
        ("2026-09-20T09:00:00.123456", VC.STR_NAIVE_US),
        ("2026-09-04T00:00:00", VC.STR_NAIVE_S),
        ("2026-07-05T19:15:00.372", VC.STR_NAIVE_MS),
        ("2026-07-05T19:15:00.37", VC.STR_NAIVE_MS),
        ("2026-09-27T17:00", VC.STR_NAIVE_OTHER),
        ("2026-09-27T17:00:00.1234", VC.STR_NAIVE_OTHER),
        ("2026-09-06T01:39:05.423Z", VC.STR_OFFSET),
        ("2026-03-06T10:30:00+07:00", VC.STR_OFFSET),
        ("2026-06-07T12:51:25.257911+00:00", VC.STR_OFFSET),
    ],
)
def test_a_stamp_strings_class_is_its_shape_and_precision(text: str, cls: object) -> None:
    value = migration.classify_string(text)
    assert value is not None and value.cls is cls


@pytest.mark.parametrize("text", ["2026-09-28", "Form Response (2026-06-17 10:16)", "hello", "{}"])
def test_a_string_that_is_not_a_stamp_is_not_classified(text: str) -> None:
    assert migration.classify_string(text) is None


@pytest.mark.parametrize(
    ("value_type", "text", "zone", "nanos", "cls", "offset_zone"),
    [
        (
            "ZONED DATETIME NOT NULL",
            "2026-07-04T12:42:38.288833Z",
            "Z",
            288_833_000,
            VC.NATIVE_US,
            True,
        ),
        (
            "ZONED DATETIME NOT NULL",
            "2026-09-04T20:55:29.923Z",
            "Z",
            923_000_000,
            VC.NATIVE_MS,
            True,
        ),
        ("ZONED DATETIME NOT NULL", "2026-03-29T00:00:00Z", "Z", 0, VC.NATIVE_S, True),
        (
            "ZONED DATETIME NOT NULL",
            "2026-07-02T21:47:48.665Z[UTC]",
            "UTC",
            665_000_000,
            VC.NATIVE_MS,
            False,
        ),
        (
            "ZONED DATETIME NOT NULL",
            "2026-03-06T10:30:00+07:00",
            "+07:00",
            0,
            VC.NATIVE_OTHER,
            False,
        ),
        (
            "ZONED DATETIME NOT NULL",
            "2026-07-04T12:42:38.288833001Z",
            "Z",
            288_833_001,
            VC.NATIVE_OTHER,
            True,
        ),
        (
            "LOCAL DATETIME NOT NULL",
            "2026-07-04T12:42:38.288833",
            None,
            288_833_000,
            VC.NATIVE_UNZONED,
            True,
        ),
    ],
)
def test_a_natives_class_is_its_precision_and_zone(
    value_type: str, text: str, zone: str | None, nanos: int, cls: object, offset_zone: bool
) -> None:
    value = migration.classify_native(value_type, text, zone, nanos)
    assert value.cls is cls
    assert value.offset_zone is offset_zone


# ---------------------------------------------------------------------------
# The shift: the zone a laptop-clock stamp's date gives, and its shape kept
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("digits", "utc"),
    [
        # America/Vancouver in summer (PDT, UTC-7).
        (datetime(2026, 9, 20, 9, 0, 0, 123456), datetime(2026, 9, 20, 16, 0, 0, 123456)),
        # A date-only path's local midnight keeps its day.
        (datetime(2026, 9, 4), datetime(2026, 9, 4, 7, 0)),
        # UTC+7 before the zone change.
        (datetime(2026, 2, 1, 18, 12, 42, 404457), datetime(2026, 2, 1, 11, 12, 42, 404457)),
    ],
)
def test_a_laptop_stamp_is_read_in_the_zone_its_date_gives(digits: datetime, utc: datetime) -> None:
    assert migration.shift_digits(digits) == (utc, "")


def test_a_laptop_stamp_on_the_zone_change_day_stops() -> None:
    moved, why = migration.shift_digits(datetime(2026, 3, 27, 13, 0))
    assert moved is None and "zone change day" in why


def test_a_wall_clock_in_a_spring_gap_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wall clock the zone skips names no instant. America/Vancouver has no gap after
    the laptop's zone change (permanent UTC-7 from 2026-11-01), so the check is shown on
    a zone with one: 02:30 on 2026-03-29 never happened in Berlin."""
    monkeypatch.setattr(migration, "LAPTOP", ZoneInfo("Europe/Berlin"))
    moved, why = migration.shift_digits(datetime(2026, 3, 29, 2, 30))
    assert moved is None and "DST gap" in why


def test_a_natives_new_text_is_cypher_tostring() -> None:
    assert (
        migration.native_text(datetime(2026, 9, 28, 0, 41, 0, 750000)) == "2026-09-28T00:41:00.75Z"
    )
    assert (
        migration.native_text(datetime(2026, 9, 28, 0, 41, 0, 750123))
        == "2026-09-28T00:41:00.750123Z"
    )
    assert migration.native_text(datetime(2026, 9, 28, 0, 41)) == "2026-09-28T00:41:00Z"


def test_the_shift_keeps_each_values_shape() -> None:
    naive = migration.classify_string("2026-09-20T09:00:00.123456")
    whole = migration.classify_string("2026-09-04T00:00:00")
    native = migration.classify_native(
        "ZONED DATETIME", "2026-09-27T17:41:00.750123Z", "Z", 750_123_000
    )
    moved = datetime(2026, 9, 28, 0, 41, 0, 750123)
    assert (
        migration.shifted_text(naive, datetime(2026, 9, 20, 16, 0, 0, 123456))
        == "2026-09-20T16:00:00.123456"
    )
    assert migration.shifted_text(whole, datetime(2026, 9, 4, 7, 0)) == "2026-09-04T07:00:00"
    assert migration.shifted_text(native, moved) == "2026-09-28T00:41:00.750123Z"


# ---------------------------------------------------------------------------
# Every rule's verdicts
# ---------------------------------------------------------------------------

ALL = tuple(VC)


def _matrix(rule: object) -> dict[object, object]:
    return {cls: rule.verdict(cls) for cls in ALL}  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("rule", "shift", "leave"),
    [
        (
            "LAPTOP_STRING",
            {VC.STR_NAIVE_US, VC.STR_NAIVE_S},
            {VC.STR_OFFSET, VC.NATIVE_MS, VC.NATIVE_S},
        ),
        (
            "LAPTOP_STRING_AHEAD",
            {VC.STR_NAIVE_US, VC.STR_NAIVE_S},
            {VC.STR_OFFSET, VC.NATIVE_MS, VC.NATIVE_S},
        ),
        ("CLIENT_STRING", {VC.STR_NAIVE_US, VC.STR_NAIVE_S}, {VC.STR_OFFSET}),
        ("CLIENT_STRING_AHEAD", {VC.STR_NAIVE_US, VC.STR_NAIVE_S}, {VC.STR_OFFSET}),
        # Both writers are the laptop's: an offset string or a millisecond native is neither.
        ("LAPTOP_STRING_OR_NATIVE", {VC.STR_NAIVE_US, VC.STR_NAIVE_S, VC.NATIVE_US}, set()),
        ("LAPTOP_NATIVE", {VC.NATIVE_US}, set()),
        ("LAPTOP_NATIVE_OR_STRING", {VC.NATIVE_US, VC.STR_NAIVE_US, VC.STR_NAIVE_S}, set()),
        ("LAPTOP_NATIVE_OR_MIDNIGHT", {VC.NATIVE_US, VC.NATIVE_S}, set()),
        ("PERIOD_BOUND", {VC.STR_NAIVE_US, VC.STR_NAIVE_S}, set()),
        ("PERIOD_CUTOFF", {VC.STR_NAIVE_US, VC.STR_NAIVE_S}, set()),
        ("TRUE_UTC", set(), {VC.NATIVE_US, VC.NATIVE_MS, VC.NATIVE_S, VC.STR_OFFSET}),
        ("TRUE_UTC_STRING", set(), {VC.STR_OFFSET}),
        ("AUTHORED_OFFSET", set(), {VC.STR_OFFSET}),
        # A whole-second offset-less OWNS string is a Python stamp or the backfill's: it stops.
        ("OWNS_STAMP", {VC.STR_NAIVE_US}, {VC.STR_NAIVE_MS, VC.STR_OFFSET}),
        (
            "GROUP_CREATED",
            {VC.STR_NAIVE_US, VC.STR_NAIVE_S},
            {VC.NATIVE_US, VC.NATIVE_MS, VC.NATIVE_S},
        ),
        # A whole-second native is the backfill's UTC midnight or a completion's local one.
        ("PRODUCTIVITY_STAMP", {VC.NATIVE_US}, set()),
        ("INSIGHT_EXPIRY", set(), set()),
    ],
)
def test_each_rule_shifts_and_leaves_exactly_its_writers_shapes(
    rule: str, shift: set[object], leave: set[object]
) -> None:
    matrix = _matrix(getattr(migration, rule))
    assert {cls for cls, v in matrix.items() if v is S} == shift
    assert {cls for cls, v in matrix.items() if v is L} == leave
    # Everything else stops — the unclassifiable precisions always do.
    for cls in (VC.STR_NAIVE_OTHER, VC.NATIVE_OTHER, VC.NATIVE_UNZONED):
        assert matrix[cls] is X


def test_every_label_and_relationship_has_a_created_and_updated_rule() -> None:
    for label in NeoLabel:
        for prop in ("created_at", "updated_at"):
            assert (f"(:{label})", prop) in migration.RULES
    for rel in RelationshipName:
        for prop in ("created_at", "updated_at"):
            assert (f"[:{rel}]", prop) in migration.RULES


@pytest.mark.parametrize(
    ("owner", "prop", "rule"),
    [
        ("[:OWNS]", "created_at", "OWNS_STAMP"),
        ("[:SHARED_WITH_GROUP]", "shared_at", "LAPTOP_NATIVE"),
        ("[:SUBMITTED_TO_GROUP]", "submitted_at", "LAPTOP_NATIVE"),
        ("[:SHARES_WITH]", "shared_at", "LAPTOP_NATIVE_OR_STRING"),
        ("[:MEMBER_OF]", "joined_at", "MEMBER_OF_JOINED"),
        ("(:EntryReport)", "updated_at", "LAPTOP_STRING_OR_NATIVE"),
        ("(:UserEntry)", "updated_at", "LAPTOP_STRING_OR_NATIVE"),
        ("(:UserEntry)", "created_at", "LAPTOP_STRING"),
        ("(:Notification)", "created_at", "LAPTOP_NATIVE"),
        ("(:Session)", "created_at", "TRUE_UTC"),
        ("(:Content)", "updated_at", "TRUE_UTC"),
        ("(:Ku)", "embedding_updated_at", "TRUE_UTC"),
        ("(:Ku)", "last_reflected_date", "LAPTOP_NATIVE_OR_MIDNIGHT"),
        ("(:ActivityReport)", "period_end", "PERIOD_BOUND"),
        ("(:Choice)", "decision_deadline", "CLIENT_STRING_AHEAD"),
        ("(:Event)", "rescheduled_at", "TRUE_UTC_STRING"),
        ("(:Insight)", "expires_at", "INSIGHT_EXPIRY"),
        ("[:EXACERBATED_BY]", "observed_at", "AUTHORED_OFFSET"),
    ],
)
def test_the_table_names_each_propertys_rule(owner: str, prop: str, rule: str) -> None:
    assert migration.RULES[(owner, prop)] is getattr(migration, rule)


def _stamp(owner: str, prop: str, value: Any) -> Any:
    return migration.Stamp(
        "node",
        "e1",
        owner,
        prop,
        value,
        {"match_label": "Entity", "owner_label": owner[2:-1], "key_prop": "uid", "key": "x"},
    )


def test_a_now_stamp_ahead_of_the_laptops_wall_clock_stops() -> None:
    value = migration.classify_string("2026-09-28T14:00:00.000001")  # a UTC process, just now
    stamp = _stamp("(:Task)", "created_at", value)
    migration._decide(stamp, migration.LAPTOP_STRING, LAPTOP_NOW)
    assert stamp.verdict is X and "UTC-clock process" in stamp.reason


def test_a_deadline_ahead_of_the_laptops_wall_clock_moves() -> None:
    value = migration.classify_string("2026-10-15T17:00:00.000001")
    stamp = _stamp("(:Choice)", "decision_deadline", value)
    migration._decide(stamp, migration.CLIENT_STRING_AHEAD, LAPTOP_NOW)
    assert stamp.verdict is S and stamp.new_text == "2026-10-16T00:00:00.000001"


def test_a_laptop_native_carrying_a_zone_id_stops() -> None:
    value = migration.classify_native(
        "ZONED DATETIME", "2026-09-20T09:00:00.123456Z[UTC]", "UTC", 123_456_000
    )
    stamp = _stamp("(:Notification)", "created_at", value)
    migration._decide(stamp, migration.LAPTOP_NATIVE, LAPTOP_NOW)
    assert stamp.verdict is X and "zone id" in stamp.reason


def test_a_shape_the_writers_do_not_produce_stops() -> None:
    value = migration.classify_native(
        "ZONED DATETIME", "2026-08-01T17:10:51.959Z", "Z", 959_000_000
    )
    stamp = _stamp("(:EntryReport)", "updated_at", value)
    migration._decide(stamp, migration.LAPTOP_STRING_OR_NATIVE, LAPTOP_NOW)
    assert stamp.verdict is X


def test_a_labels_owner_is_the_one_label_with_a_rule() -> None:
    assert migration._owner_of(("Entity", "Task"), "created_at") == ("(:Task)", "")
    owner, why = migration._owner_of(("Entity", "Task"), "odd_at")
    assert owner is None and "no rule" in why
    owner, why = migration._owner_of(("Task", "Goal"), "created_at")
    assert owner is None and "more than one rule" in why


# ---------------------------------------------------------------------------
# MEMBER_OF: settled by provenance, never by the value's clock
# ---------------------------------------------------------------------------


def _member(group: str, text: str, nanos: int, user: str = "user_s") -> Any:
    value = migration.classify_native("ZONED DATETIME", text, "Z", nanos)
    return migration.Stamp(
        "rel",
        "r1",
        "[:MEMBER_OF]",
        "joined_at",
        value,
        {"type": "MEMBER_OF"},
        start_uid=user,
        end_uid=group,
    )


def test_a_non_default_group_membership_is_add_members_and_moves() -> None:
    stamp = _member("group.class", "2026-09-20T09:00:00.123456Z", 123_456_000)
    migration._member_of_pairing(stamp, {}, {}, LAPTOP_NOW)
    assert stamp.verdict is S and stamp.new_text == "2026-09-20T16:00:00.123456Z"


def test_a_default_group_membership_paired_with_the_groups_creation_stays() -> None:
    text = "2026-07-04T19:39:43.827681Z"
    stamp = _member("group_default_user_admin", text, 827_681_000)
    migration._member_of_pairing(stamp, {"group_default_user_admin": text}, {}, LAPTOP_NOW)
    assert stamp.verdict is L


def test_a_default_group_membership_paired_with_its_in_progress_stamp_stays() -> None:
    stamp = _member("group_default_user_admin", "2026-07-04T19:39:43.827681Z", 827_681_000)
    in_progress = {"user_s": ["2026-07-04T19:39:43.777678Z"]}
    migration._member_of_pairing(stamp, {}, in_progress, LAPTOP_NOW)
    assert stamp.verdict is L


def test_an_unpaired_default_group_membership_stops() -> None:
    stamp = _member("group_default_user_admin", "2026-09-20T09:00:00.123456Z", 123_456_000)
    in_progress = {"user_s": ["2026-09-20T16:00:00.1Z"]}  # seven hours off: no pair
    migration._member_of_pairing(stamp, {}, in_progress, LAPTOP_NOW)
    assert stamp.verdict is X and "no paired stamp" in stamp.reason


def test_a_millisecond_default_group_membership_stops() -> None:
    stamp = _member("group_default_user_admin", "2026-09-25T23:06:45.126Z", 126_000_000)
    migration._member_of_pairing(stamp, {}, {}, LAPTOP_NOW)
    assert stamp.verdict is X


# ---------------------------------------------------------------------------
# Rulings, JSON paths, the record's state
# ---------------------------------------------------------------------------


def test_a_ruling_settles_exactly_its_row_and_value(monkeypatch: pytest.MonkeyPatch) -> None:
    ruling = migration.Ruling(
        owner="[:MEMBER_OF]",
        prop="joined_at",
        key=("type=MEMBER_OF",),
        text="2026-09-25T23:06:45.126Z",
        verdict=L,
        reason="true UTC (the ruled row)",
    )
    monkeypatch.setattr(migration, "RULINGS", (ruling,))
    stamp = _member("group_default_user_admin", "2026-09-25T23:06:45.126Z", 126_000_000)
    assert migration._apply_ruling(stamp) and stamp.verdict is L
    changed = _member("group_default_user_admin", "2026-09-25T23:06:45.127Z", 127_000_000)
    assert not migration._apply_ruling(changed)


def test_json_stamps_are_found_by_normalized_path() -> None:
    parsed = {
        "activity_extraction": {"extraction_started_at": "2026-09-15T12:50:06.419335", "n": 1},
        "list": [{"date": "2026-09-20T09:00:00.123456"}, {"date": "2026-09-21"}],
    }
    assert migration._json_stamps(parsed) == [
        ("$.activity_extraction.extraction_started_at", "2026-09-15T12:50:06.419335"),
        ("$.list[].date", "2026-09-20T09:00:00.123456"),
    ]


def test_the_records_state_refuses_the_wrong_run() -> None:
    applied = [{"state": "applied", "manifest_hash": "h"}]
    assert migration._state_refusal([], allowed={None, "reverted"}) is None
    assert "applied" in migration._state_refusal(applied, allowed={None, "reverted"})
    assert migration._state_refusal(applied, allowed={"applied"}) is None
    assert "2 MigrationRecord" in migration._state_refusal(applied * 2, allowed={"applied"})


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def _manifest() -> dict[str, object]:
    return {
        "migration": migration.UTC_INSTANTS_MIGRATION,
        "format": migration.MANIFEST_FORMAT,
        "graph_uri": "bolt://x",
        "census_at": "2026-09-28T15:00:00+00:00",
        "laptop_wall_clock_at_census": "2026-09-28T08:00:00",
        "counts": {},
        "left": {},
        "pairs": [],
        "rows": [],
    }


def test_the_manifest_is_content_addressed_and_loads_by_its_hash(tmp_path: Path) -> None:
    path, digest = migration.write_manifest(_manifest(), tmp_path)
    assert path.name == f"manifest-{digest}.json"
    assert migration.load_manifest(tmp_path, digest) == json.loads(path.read_bytes())


def test_an_altered_manifest_is_refused(tmp_path: Path) -> None:
    path, digest = migration.write_manifest(_manifest(), tmp_path)
    path.write_text(path.read_text().replace("bolt://x", "bolt://y"))
    with pytest.raises(migration.ManifestError, match="altered"):
        migration.load_manifest(tmp_path, digest)


@pytest.mark.parametrize("digest", ["abc", "g" * 64])
def test_a_malformed_hash_is_refused(tmp_path: Path, digest: str) -> None:
    with pytest.raises(migration.ManifestError, match="not a manifest hash"):
        migration.load_manifest(tmp_path, digest)


def test_another_migrations_manifest_is_refused(tmp_path: Path) -> None:
    other = {**_manifest(), "migration": "something_else"}
    _, digest = migration.write_manifest(other, tmp_path)
    with pytest.raises(migration.ManifestError, match="not a format-1"):
        migration.load_manifest(tmp_path, digest)


def test_the_manifests_rows_are_ordered_and_numbered() -> None:
    census = migration.Census(
        census_at=datetime(2026, 9, 28, 15, 0, tzinfo=migration.UTC),
        laptop_now=LAPTOP_NOW,
        graph_uri="bolt://x",
    )
    for uid, text in (("b", "2026-09-20T09:00:00.000002"), ("a", "2026-09-20T09:00:00.000001")):
        value = migration.classify_string(text)
        stamp = migration.Stamp(
            "node",
            uid,
            "(:Task)",
            "created_at",
            value,
            {"match_label": "Entity", "owner_label": "Task", "key_prop": "uid", "key": uid},
        )
        migration._decide(stamp, migration.LAPTOP_STRING, LAPTOP_NOW)
        census.stamps.append(stamp)
    rows = migration.build_manifest(census)["rows"]
    assert [row["key"]["key"] for row in rows] == ["a", "b"]
    assert [row["id"] for row in rows] == [0, 1]
    assert rows[0]["new"] == "2026-09-20T16:00:00.000001" and rows[0]["shape"] == "string"


def test_a_json_stamp_moves_only_at_the_path_it_was_classified_at() -> None:
    """The same text at a read path and a diagnostic path: only the read one moves."""
    stamp = "2026-09-20T09:00:00.123456"
    text = json.dumps({"progress_notes": [{"date": stamp, "notes": "n"}], "archived_at": stamp})
    census = migration.Census(
        census_at=datetime(2026, 9, 28, 15, 0, tzinfo=migration.UTC),
        laptop_now=LAPTOP_NOW,
        graph_uri="bolt://x",
    )
    row = {"element": "e1", "prop": "metadata", "text": text, "uid": "goal.x", "user_uid": None}
    migration._json_census(census, row, ("Entity", "Goal"), "(:Goal)", "")
    assert not census.stops
    [json_row] = census.json_rows
    moved = json.loads(json_row["new"])
    assert moved["progress_notes"][0]["date"] == "2026-09-20T16:00:00.123456"
    assert moved["archived_at"] == stamp
    assert json_row["changes"] == [
        {"path": "$.progress_notes[].date", "old": stamp, "new": "2026-09-20T16:00:00.123456"}
    ]
