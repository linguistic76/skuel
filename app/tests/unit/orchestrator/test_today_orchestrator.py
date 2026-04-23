"""Tests for the TodayOrchestrator.

Shape-first: these tests verify the orchestrator returns a correctly-typed
TodayPageContext and that mapper helpers produce the right view shapes.
Full wiring across all 7 services is exercised in integration tests.
"""

from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import EntityStatus, Priority
from core.orchestrator.today_orchestrator import (
    TodayOrchestrator,
    _date_label,
    _due_label,
    _priority_label,
    _task_to_triage,
    _task_to_view,
)
from core.utils.result_simplified import Result

# ---------------------------------------------------------------------------
# Mapper helpers
# ---------------------------------------------------------------------------


def test_priority_label_collapses_critical_to_high() -> None:
    assert _priority_label(Priority.CRITICAL) == "high"
    assert _priority_label(Priority.HIGH) == "high"
    assert _priority_label(Priority.MEDIUM) == "medium"
    assert _priority_label(Priority.LOW) == "low"


def test_priority_label_accepts_strings() -> None:
    assert _priority_label("high") == "high"
    assert _priority_label("medium") == "medium"
    assert _priority_label("bogus") == "low"


def test_due_label_handles_today_future_and_overdue() -> None:
    today = date(2026, 4, 22)
    assert _due_label(None, today) == ""
    assert _due_label(today, today) == "Today"
    assert _due_label(today + timedelta(days=1), today) == "Tomorrow"
    assert _due_label(today + timedelta(days=3), today) == "In 3d"
    assert _due_label(today - timedelta(days=2), today) == "Overdue · 2d"


def test_date_label_shape() -> None:
    # "Saturday · April 22" style
    label = _date_label(date(2026, 4, 22))
    assert " · " in label
    assert "22" in label


def _fake_task(
    *,
    uid: str = "t1",
    title: str = "Ship it",
    description: str = "",
    due_date: date | None = None,
    status: EntityStatus = EntityStatus.ACTIVE,
    priority: Priority = Priority.MEDIUM,
    estimated_minutes: int = 30,
    goal_uid: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        uid=uid,
        title=title,
        description=description,
        due_date=due_date,
        status=status,
        priority=priority,
        estimated_minutes=estimated_minutes,
        goal_uid=goal_uid,
    )


def test_task_to_view_produces_flat_shape() -> None:
    today = date(2026, 4, 22)
    t = _fake_task(
        uid="t-adr",
        title="ADR-021 · Event Sourcing",
        description="draft awaiting decision",
        due_date=today,
        priority=Priority.HIGH,
        estimated_minutes=45,
        goal_uid="g-ship",
    )
    view = _task_to_view(t, lifepath_id="lp-mike", today=today)
    assert view["id"] == "t-adr"
    assert view["label"] == "ADR-021 · Event Sourcing"
    assert view["lifepath_id"] == "lp-mike"
    assert view["goal_id"] == "g-ship"
    assert view["priority"] == "high"
    assert view["est_min"] == 45
    assert view["due_label"] == "Today"


def test_task_to_triage_adds_severity_and_reason() -> None:
    today = date(2026, 4, 22)
    t = _fake_task(
        uid="t-late",
        title="Late ADR re-review",
        due_date=today - timedelta(days=3),
        priority=Priority.HIGH,
    )
    view = _task_to_triage(t, lifepath_id="lp-mike", today=today)
    assert view["severity"] == "overdue"
    assert "Overdue" in view["reason"]
    assert view["id"] == "t-late"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _ok(value: object) -> Result:  # type: ignore[type-arg]
    return Result.ok(value)


def _build() -> tuple[TodayOrchestrator, dict[str, MagicMock]]:
    services: dict[str, MagicMock] = {
        "tasks_service": MagicMock(),
        "goals_service": MagicMock(),
        "habits_service": MagicMock(),
        "events_service": MagicMock(),
        "principles_service": MagicMock(),
        "lifepath_service": MagicMock(),
        "user_context_service": MagicMock(),
    }
    services["tasks_service"].get_user_tasks = AsyncMock(return_value=_ok([]))
    services["goals_service"].get_user_goals = AsyncMock(return_value=_ok([]))
    services["habits_service"].get_user_habits = AsyncMock(return_value=_ok([]))
    services["events_service"].get_user_events = AsyncMock(return_value=_ok([]))
    services["principles_service"].get_user_principles = AsyncMock(return_value=_ok([]))
    services["lifepath_service"].core = MagicMock()
    services["lifepath_service"].core.get_designation = AsyncMock(return_value=_ok(None))
    orch = TodayOrchestrator(
        tasks_service=services["tasks_service"],
        goals_service=services["goals_service"],
        habits_service=services["habits_service"],
        events_service=services["events_service"],
        principles_service=services["principles_service"],
        lifepath_service=services["lifepath_service"],
        user_context_service=services["user_context_service"],
    )
    return orch, services


@pytest.mark.asyncio
async def test_build_context_empty_day_returns_valid_shape() -> None:
    orch, _ = _build()
    result = await orch.build_context("u-mike")
    assert not result.is_error
    ctx = result.value
    # required keys present
    for key in (
        "date_label",
        "now_hhmm",
        "stats",
        "triage",
        "lifepaths",
        "principles",
        "goals",
        "tasks",
        "rituals",
        "kinds",
    ):
        assert key in ctx
    assert ctx["tasks"] == []
    assert ctx["triage"] == []
    assert ctx["stats"]["nodes"] == 0
    assert ctx["stats"]["committed_min"] == 0
    assert len(ctx["lifepaths"]) == 1
    # no activity at all → ribbon renders dormant
    assert ctx["lifepaths"][0]["dormant"] is True
    # canonical kind metadata present
    assert set(ctx["kinds"].keys()) == {
        "submission",
        "path-step",
        "askesis",
        "journal",
        "ku",
        "resource",
    }


@pytest.mark.asyncio
async def test_build_context_splits_today_tasks_and_triage() -> None:
    orch, services = _build()
    today = date.today()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok(
            [
                _fake_task(uid="t-today", due_date=today, priority=Priority.HIGH),
                _fake_task(
                    uid="t-late",
                    due_date=today - timedelta(days=2),
                    priority=Priority.CRITICAL,
                ),
                _fake_task(uid="t-future", due_date=today + timedelta(days=3)),
            ]
        )
    )
    result = await orch.build_context("u-mike")
    assert not result.is_error
    ctx = result.value
    assert [t["id"] for t in ctx["tasks"]] == ["t-today"]
    assert [t["id"] for t in ctx["triage"]] == ["t-late"]
    assert ctx["triage"][0]["severity"] == "overdue"
    assert ctx["triage"][0]["priority"] == "high"  # CRITICAL collapses to high


@pytest.mark.asyncio
async def test_build_context_propagates_tasks_service_failure() -> None:
    from core.utils.result_simplified import Errors

    orch, services = _build()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=Result.fail(Errors.database("get_user_tasks", "tasks query failed"))
    )
    result = await orch.build_context("u-mike")
    assert result.is_error


@pytest.mark.asyncio
async def test_build_context_ritual_sorts_by_time() -> None:
    orch, services = _build()
    evening_habit = SimpleNamespace(
        uid="h-evening",
        title="Evening reflect",
        scheduled_time=time(21, 0),
        estimated_minutes=10,
        principle_uid="p-reflect",
    )
    morning_habit = SimpleNamespace(
        uid="h-morning",
        title="Morning sit",
        scheduled_time=time(7, 30),
        estimated_minutes=20,
        principle_uid="p-reflect",
    )
    services["habits_service"].get_user_habits = AsyncMock(
        return_value=_ok([evening_habit, morning_habit])
    )
    result = await orch.build_context("u-mike")
    assert not result.is_error
    rituals = result.value["rituals"]
    assert [r["id"] for r in rituals] == ["h-morning", "h-evening"]
    assert rituals[0]["time"] == "07:30"
    assert rituals[1]["time"] == "21:00"
