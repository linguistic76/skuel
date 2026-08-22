"""The completion-stamp backfill's DB-free invariants.

The one-shot migration in ``scripts/backfill_activity_completion_stamps.py``
freezes the mutable ``updated_at`` proxy onto each Activity domain's canonical
completion field. Two things about it can rot without any query running:

1. **Field names.** The script must fill the property the live chokepoint stamp
   writes. It reads them from ``COMPLETION_FIELDS`` rather than declaring its
   own, so the two cannot name different properties — pinned here.
2. **Domain coverage.** Adding a domain to the stamp helper without adding a
   spec here would leave that domain's history unfrozen with no error at all;
   ``spec_coverage_gap()`` turns that into a loud failure, and this test proves
   the gap is closed today.

The Cypher itself is exercised against a real graph in
``tests/integration/test_backfill_activity_completion_stamps.py``. These run on
every CI job; that one is path-filtered.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import backfill_activity_completion_stamps as migration  # type: ignore[import-not-found]

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.completion_stamp import COMPLETION_FIELDS


def test_every_stamping_domain_has_a_backfill_spec():
    assert migration.spec_coverage_gap() == set()


def test_specs_read_their_field_from_the_shared_mapping():
    """The script never hard-codes a property name."""
    assert {s.entity_type: s.field for s in migration.SPECS} == dict(COMPLETION_FIELDS)


def test_principle_has_no_spec():
    """COMPLETED is not a valid Principle status, so it records no moment."""
    assert EntityStatus.COMPLETED not in EntityType.PRINCIPLE.valid_statuses()
    assert EntityType.PRINCIPLE not in {s.entity_type for s in migration.SPECS}


def test_date_fields_truncate_and_datetime_fields_do_not():
    """The projection decides the stored shape; ``toString`` unifies the source.

    ``updated_at`` is a live mix of ISO strings and native ZONED DATETIME, so
    every projection goes through ``toString()`` first.
    """
    task = next(s for s in migration.SPECS if s.entity_type is EntityType.TASK)
    choice = next(s for s in migration.SPECS if s.entity_type is EntityType.CHOICE)

    assert task.projection == "substring(toString(n.updated_at), 0, 10)"
    assert choice.projection == "toString(n.updated_at)"


def test_backfill_query_only_touches_unstamped_completions():
    """The NULL guard is what makes the migration idempotent and non-destructive."""
    task = next(s for s in migration.SPECS if s.entity_type is EntityType.TASK)
    query = migration.backfill_query(task)

    assert "MATCH (n:Task {status: $completed})" in query
    assert "WHERE n.completion_date IS NULL AND n.updated_at IS NOT NULL" in query
    assert "SET n.completion_date = substring(toString(n.updated_at), 0, 10)" in query


def test_labels_come_from_the_neo_label_enum():
    """A mistyped label matches zero rows instead of erroring (SKUEL030's hazard)."""
    from core.models.enums.neo_labels import NeoLabel

    valid = {label.value for label in NeoLabel}
    assert {s.label for s in migration.SPECS} <= valid
