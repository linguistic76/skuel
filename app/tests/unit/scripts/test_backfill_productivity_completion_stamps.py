"""The productivity stamp backfill's DB-free contract.

``scripts/backfill_productivity_completion_stamps.py`` is a one-shot pass that
fills NULL ``first_completion_at`` / ``last_completion_at`` on
``ProductivityAnalytics`` from completed-task history and drops the retired
``tasks_completed`` property. The census classifies each user before anything
is written, and that classification is the operator's only preview of a
reconstruction — so it is pure and pinned here:

1. **Null-only.** A stamp that exists is never planned for a write.
2. **Unfillable is its own state.** A node with a null stamp and no stamped
   completed task is reported, not invented.
3. **No node is not "nothing to do".** The vault ``- [x]`` door leaves real
   completions with no node at all; that user gets a node.
4. **The retired count is dropped wherever it sits**, independent of stamps.

The Cypher — the null guard and the ordering guard especially — is exercised
against a real graph in
``tests/integration/test_backfill_productivity_completion_stamps.py``. These run
on every CI job; that one is path-filtered.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import backfill_productivity_completion_stamps as backfill  # type: ignore[import-not-found]

from core.models.enums.entity_enums import EntityStatus


def _row(
    user_uid: str = "user_x",
    *,
    has_node: bool,
    has_first: bool = False,
    has_last: bool = False,
    has_retired_count: bool = False,
    first_day: str | None = None,
    last_day: str | None = None,
) -> backfill.CensusRow:
    """One census row, in the shape ``_to_census_row`` projects from the RETURN aliases."""
    return {
        "user_uid": user_uid,
        "has_node": has_node,
        "has_first": has_first,
        "has_last": has_last,
        "has_retired_count": has_retired_count,
        "first_day": first_day,
        "last_day": last_day,
    }


def test_a_user_with_completions_and_no_node_gets_both_stamps_and_a_node():
    plan = backfill.StampPlan.from_row(
        _row(has_node=False, first_day="2026-03-01", last_day="2026-08-20")
    )

    assert plan.creates_node
    assert plan.fill_first == "2026-03-01"
    assert plan.fill_last == "2026-08-20"
    assert not plan.unfillable
    assert plan.writes_anything


def test_existing_stamps_are_never_planned_for_a_write():
    """Null-only: the handler's stamp is the real moment and wins outright."""
    plan = backfill.StampPlan.from_row(
        _row(
            has_node=True,
            has_first=True,
            has_last=True,
            first_day="2026-01-01",
            last_day="2026-08-20",
        )
    )

    assert plan.fill_first is None
    assert plan.fill_last is None
    assert not plan.writes_anything


def test_only_the_missing_half_is_filled():
    plan = backfill.StampPlan.from_row(
        _row(
            has_node=True,
            has_first=True,
            has_last=False,
            first_day="2026-01-01",
            last_day="2026-08-20",
        )
    )

    assert plan.fill_first is None
    assert plan.fill_last == "2026-08-20"


def test_a_node_with_null_stamps_and_no_stamped_completion_is_unfillable_not_invented():
    plan = backfill.StampPlan.from_row(_row(has_node=True))

    assert plan.unfillable
    assert plan.fill_first is None and plan.fill_last is None
    assert not plan.creates_node
    assert not plan.writes_anything, "nothing to derive from — left null, reported"


def test_the_retired_count_is_dropped_even_when_no_stamp_is_written():
    plan = backfill.StampPlan.from_row(
        _row(has_node=True, has_first=True, has_last=True, has_retired_count=True)
    )

    assert plan.drops_retired_count
    assert plan.writes_anything


def test_the_write_never_touches_the_retired_count_and_the_drop_only_removes_it():
    """The two concerns are two statements: the stamp fill must not SET or
    read ``tasks_completed`` (it is being retired, not maintained), and the
    drop must REMOVE and nothing else."""
    assert "tasks_completed" not in backfill.BACKFILL_QUERY
    assert "REMOVE a.tasks_completed" in backfill.DROP_RETIRED_COUNT_QUERY
    assert "SET" not in backfill.DROP_RETIRED_COUNT_QUERY


def test_the_fill_is_a_coalesce_on_both_stamps_with_the_status_parameterised():
    """The NULL guard is the whole non-destructiveness argument, and the status
    is a driver parameter rather than a literal (CYP003)."""
    assert backfill.BACKFILL_QUERY.count("coalesce(") == 2
    assert "$completed" in backfill.BACKFILL_QUERY
    assert EntityStatus.COMPLETED.value == backfill.COMPLETED
