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

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import backfill_task_creation_due_dates as migration  # type: ignore[import-not-found]

from adapters.persistence.neo4j.ingestion_write_backend import TASK_CREATION_DUE_DATE_CYPHER
from core.models.task.task import Task

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
    cannot drift. Its shape: ``completion_date < created_at`` → the completion
    day; otherwise the creation day — the branch order of
    ``Task.with_creation_due_date``."""
    assert migration.RULE_PROJECTION is TASK_CREATION_DUE_DATE_CYPHER
    assert migration.RULE_PROJECTION == (
        "CASE WHEN n.completion_date IS NOT NULL AND "
        "substring(toString(n.completion_date), 0, 10) < substring(toString(n.created_at), 0, 10) "
        "THEN substring(toString(n.completion_date), 0, 10) "
        "ELSE substring(toString(n.created_at), 0, 10) END"
    )


def test_census_preview_and_write_agree_on_who_qualifies():
    """The census counts, the preview lists and the write touches the same rows."""
    for query in (migration.PREVIEW_QUERY, migration.BACKFILL_QUERY):
        assert f"WHERE {migration.UNDATED} AND n.created_at IS NOT NULL" in query
    assert f"{migration.UNDATED} AND n.created_at IS NOT NULL" in migration.CENSUS_QUERY
