"""Tests for the shared day-lens membership predicates (C7).

``ui/today/membership.py`` is THE definition of ribbon/triage membership:
``TodayOrchestrator.build_context()`` renders by it and the defer guard in
``adapters/inbound/today_routes.py`` validates by it. The identity tests here
unit-assert the contract's "guard and render share ONE predicate function —
no independent status list" clause.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

from core.models.enums import EntityStatus
from ui.today.membership import (
    DUE_FIELD,
    LENS_EXCLUDED_STATUSES,
    SCHEDULED_FIELD,
    is_ribbon_member,
    is_triage_member,
    ribbon_date_fields,
    status_renders_on_lens,
)

VIEW = date(2026, 8, 2)


def _task(
    *,
    due_date: date | None = None,
    scheduled_date: date | None = None,
    status: EntityStatus = EntityStatus.ACTIVE,
) -> Any:
    return SimpleNamespace(due_date=due_date, scheduled_date=scheduled_date, status=status)


# ---------------------------------------------------------------------------
# Ribbon membership — scheduled OR due == view_date, plus the status rule
# ---------------------------------------------------------------------------


def test_ribbon_scheduled_only_match() -> None:
    t = _task(scheduled_date=VIEW)
    assert ribbon_date_fields(t, VIEW) == (SCHEDULED_FIELD,)
    assert is_ribbon_member(t, VIEW) is True


def test_ribbon_due_only_match() -> None:
    t = _task(due_date=VIEW)
    assert ribbon_date_fields(t, VIEW) == (DUE_FIELD,)
    assert is_ribbon_member(t, VIEW) is True


def test_ribbon_dual_field_match_returns_both() -> None:
    t = _task(due_date=VIEW, scheduled_date=VIEW)
    assert ribbon_date_fields(t, VIEW) == (SCHEDULED_FIELD, DUE_FIELD)
    assert is_ribbon_member(t, VIEW) is True


def test_ribbon_no_field_match() -> None:
    t = _task(due_date=VIEW + timedelta(days=1), scheduled_date=VIEW - timedelta(days=1))
    assert ribbon_date_fields(t, VIEW) == ()
    assert is_ribbon_member(t, VIEW) is False
    assert is_ribbon_member(_task(), VIEW) is False  # both fields None


def test_ribbon_completed_task_is_not_a_member_even_with_date_match() -> None:
    # A completed task's dates still pass the date checks — the status rule
    # must refuse it (contract round 9: completed-after-load defers are 400).
    t = _task(scheduled_date=VIEW, status=EntityStatus.COMPLETED)
    assert ribbon_date_fields(t, VIEW) == (SCHEDULED_FIELD,)  # date-only helper
    assert is_ribbon_member(t, VIEW) is False


def test_ribbon_cancelled_and_failed_still_render_today() -> None:
    # C7 scope line: today the exclusion is exactly COMPLETED — dated
    # CANCELLED/FAILED tasks render and therefore remain deferrable.
    assert is_ribbon_member(_task(due_date=VIEW, status=EntityStatus.CANCELLED), VIEW) is True
    assert is_ribbon_member(_task(due_date=VIEW, status=EntityStatus.FAILED), VIEW) is True


# ---------------------------------------------------------------------------
# Triage membership — actually overdue, plus the SAME status rule
# ---------------------------------------------------------------------------


def test_triage_requires_actual_overdue() -> None:
    today = VIEW
    assert is_triage_member(_task(due_date=today - timedelta(days=7)), today) is True
    assert is_triage_member(_task(due_date=today), today) is False  # due today ≠ overdue
    assert is_triage_member(_task(due_date=today + timedelta(days=1)), today) is False
    assert is_triage_member(_task(due_date=None), today) is False


def test_triage_ignores_scheduled_date() -> None:
    # Triage is deadline language — a stale work-plan date alone never
    # qualifies (the contract keeps the triage bar due-based).
    t = _task(scheduled_date=VIEW - timedelta(days=5))
    assert is_triage_member(t, VIEW) is False


def test_triage_completed_task_is_not_a_member() -> None:
    t = _task(due_date=VIEW - timedelta(days=7), status=EntityStatus.COMPLETED)
    assert is_triage_member(t, VIEW) is False


# ---------------------------------------------------------------------------
# ONE predicate function — render and guard share the same objects
# ---------------------------------------------------------------------------


def test_orchestrator_renders_by_the_shared_predicates() -> None:
    import ui.today.membership as membership
    import ui.today.orchestrator as orchestrator

    assert orchestrator.is_ribbon_member is membership.is_ribbon_member
    assert orchestrator.is_triage_member is membership.is_triage_member


def test_defer_guard_validates_by_the_shared_predicates() -> None:
    import adapters.inbound.today_routes as today_routes
    import ui.today.membership as membership

    assert today_routes.is_ribbon_member is membership.is_ribbon_member
    assert today_routes.is_triage_member is membership.is_triage_member
    assert today_routes.ribbon_date_fields is membership.ribbon_date_fields


def test_single_status_exclusion_list() -> None:
    """The status rule lives in exactly one place, and today it excludes
    exactly COMPLETED (whether CANCELLED/FAILED should render is lens-status
    truth, out of C7's scope — see the contract)."""
    assert frozenset({EntityStatus.COMPLETED}) == LENS_EXCLUDED_STATUSES
    assert status_renders_on_lens(_task(status=EntityStatus.ACTIVE)) is True
    assert status_renders_on_lens(_task(status=EntityStatus.COMPLETED)) is False
