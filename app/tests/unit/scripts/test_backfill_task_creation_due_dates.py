"""The task due-date backfill's DB-free invariants.

``scripts/backfill_task_creation_due_dates.py`` applies the creation rule
(``Task.with_creation_due_date``) to history in Cypher. Two things about it can
rot without a query running:

1. **Field names.** The script writes and guards on property names that must
   be real ``Task`` fields — a typo would match nothing and report a clean run.
2. **The rule.** The Cypher projection is the vault door's own expression,
   imported; the guard predicate must be the model's ("neither date"), and the
   projection must take the completion day only when it is earlier.

The Cypher itself runs against a real graph in
``tests/integration/test_backfill_task_creation_due_dates.py``.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import backfill_task_creation_due_dates as migration  # type: ignore[import-not-found]

from adapters.persistence.neo4j.ingestion_write_backend import task_creation_due_date_cypher
from core.models.enums.entity_enums import EntityStatus
from core.models.task.task import Task
from core.utils import timestamp_helpers
from core.utils.zone_context import default_zone

TASK_FIELDS = {f.name for f in dataclasses.fields(Task)}


def test_the_guarded_and_written_fields_are_task_fields():
    assert {migration.DUE_FIELD, migration.SCHEDULED_FIELD, "created_at", "completion_date"} <= (
        TASK_FIELDS
    )


def test_the_guard_is_neither_date_and_the_write_is_the_due_date():
    """Only a node with BOTH lens fields NULL is touched — the model's own
    predicate — and only ``due_date`` is written (deadline language, as the
    model method)."""
    assert migration.UNDATED == "n.due_date IS NULL AND n.scheduled_date IS NULL"
    assert migration.UNDATED in migration.BACKFILL_QUERY
    assert f"SET n.{migration.DUE_FIELD} = " in migration.BACKFILL_QUERY
    assert f"n.{migration.SCHEDULED_FIELD} =" not in migration.BACKFILL_QUERY


def test_the_projection_is_the_vault_doors_own():
    """One expression, imported — the backfill and the live vault-door rule
    cannot drift. Its shape: on a COMPLETED node, ``completion_date <
    created_at`` → the completion day; otherwise the creation day — the branch
    order of ``Task.with_creation_due_date``, status guard included. The stored
    clock is UTC, so an offset-less ``created_at`` holds UTC digits and every
    stamp's creation day is the day its instant falls on in ``$zone``."""
    assert task_creation_due_date_cypher() == migration.RULE_PROJECTION
    created_day = "toString(date(datetime({datetime: datetime(n.created_at), timezone: $zone})))"
    done_day = "substring(toString(n.completion_date), 0, 10)"
    assert (
        "CASE WHEN n.status = $completed_status AND n.completion_date IS NOT NULL AND "
        f"{done_day} < {created_day} THEN {done_day} ELSE {created_day} END"
    ) == migration.RULE_PROJECTION
    assert "substring(toString(n.created_at)" not in migration.RULE_PROJECTION


def test_on_the_host_clock_an_offset_less_stamp_keeps_its_digits_day(
    monkeypatch: pytest.MonkeyPatch,
):
    """On the host-zone stored clock an offset-less ``created_at`` holds the host's
    wall clock, so its creation day is its own digits' day; a stamp with an offset
    still names its instant, whose day is the zone's."""
    monkeypatch.setattr(timestamp_helpers, "STORED_INSTANT_CLOCK", None)
    rule = task_creation_due_date_cypher()
    assert "substring(toString(n.created_at), 0, 10)" in rule
    assert "valueType(n.created_at) STARTS WITH 'ZONED'" in rule
    assert "date(datetime({datetime: datetime(n.created_at), timezone: $zone}))" in rule


def test_the_rule_parameter_is_the_completed_status():
    """The expression reads ``$completed_status`` and ``$zone``; the script
    supplies exactly the enum value the app writes and the app default zone, on
    every query that embeds the rule."""
    assert {
        "completed_status": EntityStatus.COMPLETED.value,
        "zone": str(default_zone()),
    } == migration.RULE_PARAMS
    assert "$completed_status" in migration.BACKFILL_QUERY
    assert "$completed_status" in migration.PREVIEW_QUERY


def test_census_preview_and_write_agree_on_who_qualifies():
    """The census counts, the preview lists and the write touches the same rows."""
    for query in (migration.PREVIEW_QUERY, migration.BACKFILL_QUERY):
        assert f"WHERE {migration.UNDATED} AND n.created_at IS NOT NULL" in query
    assert f"{migration.UNDATED} AND n.created_at IS NOT NULL" in migration.CENSUS_QUERY
