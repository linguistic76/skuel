"""Tests for the TodayOrchestrator.

Shape-first: these tests verify the orchestrator returns a correctly-typed
TodayPageContext and that mapper helpers produce the right view shapes.
Full wiring across all 7 services is exercised in integration tests.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import EntityStatus, Priority
from core.utils.result_simplified import Result
from ui.today.orchestrator import (
    TodayOrchestrator,
    _date_label,
    _due_label,
    _heading_label,
    _parse_hhmm,
    _priority_label,
    _task_to_triage,
    _task_to_view,
)

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


def test_heading_label_uses_relative_words_near_today() -> None:
    today = date(2026, 4, 22)
    assert _heading_label(today, today) == "Today"
    assert _heading_label(today - timedelta(days=1), today) == "Yesterday"
    assert _heading_label(today + timedelta(days=1), today) == "Tomorrow"
    # Further out falls back to a compact month + day (no relative word).
    assert _heading_label(date(2026, 4, 19), today) == "Apr 19"


def _fake_task(
    *,
    uid: str = "t1",
    title: str = "Ship it",
    description: str = "",
    due_date: date | None = None,
    scheduled_date: date | None = None,
    status: EntityStatus = EntityStatus.ACTIVE,
    priority: Priority = Priority.MEDIUM,
    duration_minutes: int = 30,
    fulfills_goal_uid: str | None = None,
    updated_at: datetime | None = None,
    created_at: datetime | None = None,
    completion_date: date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        uid=uid,
        title=title,
        description=description,
        due_date=due_date,
        scheduled_date=scheduled_date,
        status=status,
        priority=priority,
        duration_minutes=duration_minutes,
        fulfills_goal_uid=fulfills_goal_uid,
        updated_at=updated_at,
        created_at=created_at,
        completion_date=completion_date,
    )


def test_task_to_view_produces_flat_shape() -> None:
    today = date(2026, 4, 22)
    t = _fake_task(
        uid="t-adr",
        title="ADR-021 · Event Sourcing",
        description="draft awaiting decision",
        due_date=today,
        priority=Priority.HIGH,
        duration_minutes=45,
        fulfills_goal_uid="g-ship",
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
        "user_relationship_service": MagicMock(),
    }
    services["tasks_service"].get_user_tasks = AsyncMock(return_value=_ok([]))
    services["goals_service"].get_user_goals = AsyncMock(return_value=_ok([]))
    services["habits_service"].get_user_habits = AsyncMock(return_value=_ok([]))
    services["events_service"].get_user_events = AsyncMock(return_value=_ok([]))
    services["principles_service"].get_user_principles = AsyncMock(return_value=_ok([]))
    services["principles_service"].get_embodiment_rates_7d = AsyncMock(return_value=_ok({}))
    services["user_relationship_service"].get_today_pinned = AsyncMock(return_value=_ok(set()))

    # Graph-enrichment surfaces consumed by _first_principle_map.
    services["goals_service"].relationships = MagicMock()
    services["goals_service"].relationships.get_related_uids = AsyncMock(return_value=_ok([]))
    services["habits_service"].relationships = MagicMock()
    services["habits_service"].relationships.get_related_uids = AsyncMock(return_value=_ok([]))

    services["lifepath_service"].core = MagicMock()
    services["lifepath_service"].core.get_designation = AsyncMock(return_value=_ok(None))
    services["lifepath_service"].core.lp_service = None  # no LP fetch in default harness

    orch = TodayOrchestrator(
        tasks_service=services["tasks_service"],
        goals_service=services["goals_service"],
        habits_service=services["habits_service"],
        events_service=services["events_service"],
        principles_service=services["principles_service"],
        lifepath_service=services["lifepath_service"],
        user_relationship_service=services["user_relationship_service"],
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
        "today_iso",
        "date_label",
        "heading",
        "is_today",
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
    # Bare build → the live day: is_today True, today_iso anchored to today.
    assert ctx["is_today"] is True
    assert ctx["today_iso"] == today.isoformat()
    assert ctx["heading"] == "Today"


@pytest.mark.asyncio
async def test_build_context_day_lens_targets_other_day() -> None:
    """A ``view_date`` other than today is a pure day lens: tasks filter to that
    day, triage (overdue-now) is suppressed, and the NOW marker is disabled."""
    orch, services = _build()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok(
            [
                _fake_task(uid="t-today", due_date=today),
                _fake_task(uid="t-tomorrow", due_date=tomorrow),
                _fake_task(uid="t-late", due_date=today - timedelta(days=2)),
            ]
        )
    )
    result = await orch.build_context("u-mike", tomorrow)
    assert not result.is_error
    ctx = result.value
    # Only tomorrow's task; today's + the overdue one are not on this day.
    assert [t["id"] for t in ctx["tasks"]] == ["t-tomorrow"]
    # Triage is a present-tense bar — never shown while browsing another day.
    assert ctx["triage"] == []
    assert ctx["is_today"] is False
    assert ctx["today_iso"] == tomorrow.isoformat()
    assert ctx["heading"] == "Tomorrow"


@pytest.mark.asyncio
async def test_build_context_can_quick_add_gates_on_past() -> None:
    """C6: quick-add is offered on today and future days, never a past day."""
    orch, _ = _build()
    today = date.today()

    today_ctx = (await orch.build_context("u-mike")).value
    assert today_ctx["can_quick_add"] is True

    future_ctx = (await orch.build_context("u-mike", today + timedelta(days=3))).value
    assert future_ctx["can_quick_add"] is True

    past_ctx = (await orch.build_context("u-mike", today - timedelta(days=1))).value
    assert past_ctx["can_quick_add"] is False


@pytest.mark.asyncio
async def test_build_context_ribbon_admits_scheduled_only_task() -> None:
    """C7 membership widening: scheduled_date == view_date puts a task on the
    ribbon even with NO due_date — it must not be invisible to the very lens
    that acts on it (and that quick-add will create it from, PR 6)."""
    orch, services = _build()
    today = date.today()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok(
            [
                _fake_task(uid="t-work", scheduled_date=today),  # scheduled-only
                _fake_task(uid="t-elsewhere", scheduled_date=today + timedelta(days=2)),
                _fake_task(
                    uid="t-done-work",
                    scheduled_date=today,
                    status=EntityStatus.COMPLETED,
                ),
            ]
        )
    )
    result = await orch.build_context("u-mike")
    assert not result.is_error
    ctx = result.value
    assert [t["id"] for t in ctx["tasks"]] == ["t-work"]
    # No due_date → no due label; the card still renders.
    assert ctx["tasks"][0]["due_label"] == ""
    assert ctx["triage"] == []


@pytest.mark.asyncio
async def test_build_context_dual_membership_task_in_ribbon_and_triage() -> None:
    """Overdue AND scheduled today → one card per surface: the ribbon speaks
    work-plan language (scheduled match), triage speaks deadline language."""
    orch, services = _build()
    today = date.today()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok(
            [
                _fake_task(
                    uid="t-dual",
                    due_date=today - timedelta(days=3),
                    scheduled_date=today,
                ),
            ]
        )
    )
    result = await orch.build_context("u-mike")
    assert not result.is_error
    ctx = result.value
    assert [t["id"] for t in ctx["tasks"]] == ["t-dual"]
    assert [t["id"] for t in ctx["triage"]] == ["t-dual"]


@pytest.mark.asyncio
async def test_build_context_triage_stays_due_based_not_scheduled() -> None:
    """A past scheduled_date alone never puts a task in triage — triage is
    deadline language (due-based), per the contract."""
    orch, services = _build()
    today = date.today()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok([_fake_task(uid="t-old-plan", scheduled_date=today - timedelta(days=5))])
    )
    result = await orch.build_context("u-mike")
    assert not result.is_error
    assert result.value["triage"] == []
    assert result.value["tasks"] == []


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
async def test_build_context_ritual_sorts_by_time_parses_preferred_time() -> None:
    orch, services = _build()
    evening_habit = SimpleNamespace(
        uid="h-evening",
        title="Evening reflect",
        preferred_time="21:00",
        duration_minutes=10,
    )
    morning_habit = SimpleNamespace(
        uid="h-morning",
        title="Morning sit",
        preferred_time="7:30",  # short form — should still parse
        duration_minutes=20,
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


@pytest.mark.asyncio
async def test_build_context_skips_habits_without_parseable_preferred_time() -> None:
    orch, services = _build()
    no_time = SimpleNamespace(
        uid="h-untimed", title="Deep work", preferred_time=None, duration_minutes=45
    )
    bad_time = SimpleNamespace(
        uid="h-garbled", title="Evening walk", preferred_time="whenever", duration_minutes=20
    )
    services["habits_service"].get_user_habits = AsyncMock(return_value=_ok([no_time, bad_time]))
    result = await orch.build_context("u-mike")
    assert not result.is_error
    assert result.value["rituals"] == []


# ---------------------------------------------------------------------------
# Graph enrichment — Goal → Principle, Habit → Principle
# ---------------------------------------------------------------------------


def test_parse_hhmm_variants() -> None:
    assert _parse_hhmm("07:30") == "07:30"
    assert _parse_hhmm("7:30") == "07:30"
    assert _parse_hhmm("21:00:00") == "21:00"
    assert _parse_hhmm("") is None
    assert _parse_hhmm(None) is None
    assert _parse_hhmm("morning") is None
    assert _parse_hhmm("25:00") is None
    assert _parse_hhmm("12:61") is None


@pytest.mark.asyncio
async def test_goal_principle_id_comes_from_graph_lookup() -> None:
    orch, services = _build()
    goal = SimpleNamespace(
        uid="g-1",
        title="Ship Today",
        status=EntityStatus.ACTIVE,
        calculate_progress=lambda: 0.4,
    )
    services["goals_service"].get_user_goals = AsyncMock(return_value=_ok([goal]))
    services["goals_service"].relationships.get_related_uids = AsyncMock(
        return_value=_ok(["p-craftsmanship", "p-depth"])
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    goal_views = result.value["goals"]
    assert len(goal_views) == 1
    assert goal_views[0]["id"] == "g-1"
    assert goal_views[0]["principle_id"] == "p-craftsmanship"
    assert goal_views[0]["progress"] == 0.4
    # The graph call used the "principles" key (GUIDED_BY_PRINCIPLE under the hood).
    services["goals_service"].relationships.get_related_uids.assert_awaited_with(
        "principles", "g-1"
    )


@pytest.mark.asyncio
async def test_habit_ritual_principle_id_comes_from_graph_lookup() -> None:
    orch, services = _build()
    habit = SimpleNamespace(
        uid="h-sit",
        title="Morning sit",
        preferred_time="07:00",
        duration_minutes=20,
    )
    services["habits_service"].get_user_habits = AsyncMock(return_value=_ok([habit]))
    services["habits_service"].relationships.get_related_uids = AsyncMock(
        return_value=_ok(["p-reflect"])
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    rituals = result.value["rituals"]
    assert len(rituals) == 1
    assert rituals[0]["id"] == "h-sit"
    assert rituals[0]["principle_id"] == "p-reflect"
    services["habits_service"].relationships.get_related_uids.assert_awaited_with(
        "principles", "h-sit"
    )


@pytest.mark.asyncio
async def test_graph_lookup_failure_degrades_to_empty_principle() -> None:
    """A failed principle-edge fetch should not abort the page — we just
    render that goal/habit without a principle binding."""
    from core.utils.result_simplified import Errors

    orch, services = _build()
    goal = SimpleNamespace(
        uid="g-1",
        title="Ship Today",
        status=EntityStatus.ACTIVE,
        calculate_progress=lambda: 0.0,
    )
    services["goals_service"].get_user_goals = AsyncMock(return_value=_ok([goal]))
    services["goals_service"].relationships.get_related_uids = AsyncMock(
        return_value=Result.fail(Errors.database("get_related_uids", "boom"))
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    assert result.value["goals"][0]["principle_id"] == ""


# ---------------------------------------------------------------------------
# Principle embodiment rate — rolling 7d habit-completion aggregate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_principle_embodiment_rate_flows_from_principles_service() -> None:
    orch, services = _build()
    active = SimpleNamespace(
        uid="p-depth",
        title="Depth over breadth",
        status=EntityStatus.ACTIVE,
        strength=SimpleNamespace(value="core"),
    )
    archived = SimpleNamespace(
        uid="p-old",
        title="Old",
        status=EntityStatus.ARCHIVED,
        strength=SimpleNamespace(value="developing"),
    )
    services["principles_service"].get_user_principles = AsyncMock(
        return_value=_ok([active, archived])
    )
    services["principles_service"].get_embodiment_rates_7d = AsyncMock(
        return_value=_ok({"p-depth": 0.42})
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    principles = result.value["principles"]
    # Archived principles are filtered out.
    assert [p["id"] for p in principles] == ["p-depth"]
    assert principles[0]["embodiment_rate"] == 0.42
    # The batch call was made with only the active principle's UID.
    called = services["principles_service"].get_embodiment_rates_7d.await_args
    assert list(called.args[0]) == ["p-depth"]


@pytest.mark.asyncio
async def test_principle_embodiment_rate_degrades_to_zero_on_failure() -> None:
    from core.utils.result_simplified import Errors

    orch, services = _build()
    principle = SimpleNamespace(
        uid="p-depth",
        title="Depth over breadth",
        status=EntityStatus.ACTIVE,
        strength=SimpleNamespace(value="strong"),
    )
    services["principles_service"].get_user_principles = AsyncMock(return_value=_ok([principle]))
    services["principles_service"].get_embodiment_rates_7d = AsyncMock(
        return_value=Result.fail(Errors.database("get_embodiment_rates_7d", "boom"))
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    principles = result.value["principles"]
    assert len(principles) == 1
    assert principles[0]["embodiment_rate"] == 0.0


# ---------------------------------------------------------------------------
# Today-scoped pins — :PINNED_TODAY edge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ribbon_tasks_sort_pinned_first_with_stable_order() -> None:
    orch, services = _build()
    today = date.today()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok(
            [
                _fake_task(uid="t-a", due_date=today),
                _fake_task(uid="t-b-pinned", due_date=today),
                _fake_task(uid="t-c", due_date=today),
                _fake_task(uid="t-d-pinned", due_date=today),
            ]
        )
    )
    services["user_relationship_service"].get_today_pinned = AsyncMock(
        return_value=_ok({"t-b-pinned", "t-d-pinned"})
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    ordered = [t["id"] for t in result.value["tasks"]]
    # Pinned first (source-order within each group), then unpinned (source-order).
    assert ordered == ["t-b-pinned", "t-d-pinned", "t-a", "t-c"]
    pinned_flags = {t["id"]: t["pinned"] for t in result.value["tasks"]}
    assert pinned_flags == {
        "t-a": False,
        "t-b-pinned": True,
        "t-c": False,
        "t-d-pinned": True,
    }


@pytest.mark.asyncio
async def test_triage_carries_pinned_flag_but_stays_severity_ordered() -> None:
    orch, services = _build()
    today = date.today()
    # Two overdue tasks: the more-overdue one is unpinned; the less-overdue is pinned.
    # Ribbon would sort pinned-first, triage must NOT — keep severity order.
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok(
            [
                _fake_task(uid="t-late-7d", due_date=today - timedelta(days=7)),
                _fake_task(uid="t-late-2d-pinned", due_date=today - timedelta(days=2)),
            ]
        )
    )
    services["user_relationship_service"].get_today_pinned = AsyncMock(
        return_value=_ok({"t-late-2d-pinned"})
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    triage = result.value["triage"]
    assert [t["id"] for t in triage] == ["t-late-7d", "t-late-2d-pinned"]
    assert triage[0]["pinned"] is False
    assert triage[1]["pinned"] is True


@pytest.mark.asyncio
async def test_today_pinned_failure_degrades_to_unpinned() -> None:
    """A failed pin fetch should not abort the page — tasks render with
    ``pinned=False`` in source order."""
    from core.utils.result_simplified import Errors

    orch, services = _build()
    today = date.today()
    services["tasks_service"].get_user_tasks = AsyncMock(
        return_value=_ok([_fake_task(uid="t-a", due_date=today)])
    )
    services["user_relationship_service"].get_today_pinned = AsyncMock(
        return_value=Result.fail(Errors.database("get_today_pinned", "boom"))
    )

    result = await orch.build_context("u-mike")
    assert not result.is_error
    tasks = result.value["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["pinned"] is False
