"""Unit tests for ``TodayOrchestrator`` — the day view's per-domain selection.

The orchestrator selects and sorts domain models for one day; it never
re-shapes them. Task membership is the shared predicates in
``ui/today/membership.py`` (pinned separately there); this module pins what
the orchestrator does WITH them — the overdue/tasks split, the live-day gate,
the other dated domains, and per-section degradation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.choice.choice import Choice
from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.task.task import Task
from core.utils.result_simplified import Errors, Result
from ui.today.orchestrator import (
    TodayOrchestrator,
    _date_label,
    _heading_label,
    choice_is_on_day,
)

USER = "user_today"
TODAY = date.today()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_date_label_shape() -> None:
    assert _date_label(date(2026, 3, 22)) == "Sunday · March 22"


def test_heading_label_uses_relative_words_near_today() -> None:
    today = date(2026, 7, 18)
    assert _heading_label(today, today) == "Today"
    assert _heading_label(today - timedelta(days=1), today) == "Yesterday"
    assert _heading_label(today + timedelta(days=1), today) == "Tomorrow"
    assert _heading_label(date(2026, 7, 19) + timedelta(days=1), today) == "Jul 20"


def test_choice_is_on_day_by_deadline_or_decision() -> None:
    day = date(2026, 9, 12)
    due = Choice(uid="c1", user_uid=USER, title="x", decision_deadline=datetime(2026, 9, 12, 9))
    decided = Choice(uid="c2", user_uid=USER, title="x", decided_at=datetime(2026, 9, 12, 21, 5))
    elsewhere = Choice(uid="c3", user_uid=USER, title="x", decision_deadline=datetime(2026, 9, 13))
    undated = Choice(uid="c4", user_uid=USER, title="x")
    assert choice_is_on_day(due, day)
    assert choice_is_on_day(decided, day)
    assert not choice_is_on_day(elsewhere, day)
    assert not choice_is_on_day(undated, day)


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------


def _task(
    uid: str,
    *,
    due: date | None = None,
    scheduled: date | None = None,
    status: EntityStatus = EntityStatus.ACTIVE,
    title: str = "t",
) -> Task:
    return Task(
        uid=uid, user_uid=USER, title=title, status=status, due_date=due, scheduled_date=scheduled
    )


def _range_read(tasks: list[Task]):  # type: ignore[no-untyped-def]  # boundary: mock side effect
    """A stand-in for the dated task read: the rows whose named date field(s)
    fall inside [start, end]; completed rows only when ``include_completed``
    asks for them, as the real read's status exclusion does."""

    async def read(
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: str | list[str] | None = None,
    ) -> Result[list[Task]]:
        fields = [date_field] if isinstance(date_field, str) else list(date_field or [])
        rows = [
            t
            for t in tasks
            if (include_completed or t.status is not EntityStatus.COMPLETED)
            and any(
                getattr(t, f) is not None and start_date <= getattr(t, f) <= end_date
                for f in fields
            )
        ]
        return Result.ok(rows)

    return read


def _build(
    *,
    tasks: list[Task] | None = None,
) -> tuple[TodayOrchestrator, dict[str, MagicMock]]:
    services: dict[str, MagicMock] = {
        key: MagicMock() for key in ("tasks", "events", "habits", "goals", "choices", "calendar")
    }
    services["tasks"].get_user_items_in_range = AsyncMock(side_effect=_range_read(tasks or []))
    services["events"].get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    services["calendar"].habit_items_for_day = AsyncMock(return_value=Result.ok([]))
    services["goals"].get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    services["choices"].get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    orch = TodayOrchestrator(
        tasks_service=services["tasks"],
        events_service=services["events"],
        habits_service=services["habits"],
        goals_service=services["goals"],
        choices_service=services["choices"],
        calendar_service=services["calendar"],
    )
    return orch, services


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_day_returns_the_full_shape() -> None:
    orch, _ = _build()

    result = await orch.build_context(USER)

    assert result.is_ok
    ctx = result.value
    assert ctx["today_iso"] == TODAY.isoformat()
    assert ctx["heading"] == "Today"
    assert ctx["is_today"] is True
    assert ctx["can_quick_add"] is True
    for key in ("overdue", "tasks", "events", "habits", "milestones", "choices"):
        assert ctx[key] == []  # type: ignore[literal-required]


@pytest.mark.asyncio
async def test_overdue_and_tasks_split_by_the_shared_predicates() -> None:
    """Overdue = due strictly before today; tasks = scheduled OR due today,
    minus the overdue — a task in both renders once, in Overdue."""
    yesterday = TODAY - timedelta(days=1)
    overdue = _task("late", due=yesterday)
    due_today = _task("due", due=TODAY)
    scheduled_today = _task("sched", scheduled=TODAY)
    both = _task("both", due=yesterday, scheduled=TODAY)
    done = _task("done", due=yesterday, status=EntityStatus.COMPLETED)
    unrelated = _task("far", due=TODAY + timedelta(days=3))
    orch, _ = _build(tasks=[overdue, due_today, scheduled_today, both, done, unrelated])

    ctx = (await orch.build_context(USER)).value

    assert {t.uid for t in ctx["overdue"]} == {"both", "late"}
    assert {t.uid for t in ctx["tasks"]} == {"due", "sched"}


@pytest.mark.asyncio
async def test_other_day_has_no_overdue_but_keeps_its_members() -> None:
    """Overdue is a present-tense surface: browsing another day shows that
    day's lens members and no overdue pile."""
    other = TODAY + timedelta(days=2)
    orch, _ = _build(tasks=[_task("late", due=TODAY - timedelta(days=1)), _task("on", due=other)])

    ctx = (await orch.build_context(USER, other)).value

    assert ctx["overdue"] == []
    assert [t.uid for t in ctx["tasks"]] == ["on"]
    assert ctx["is_today"] is False
    assert ctx["heading"] != "Today"


@pytest.mark.asyncio
async def test_can_quick_add_gates_on_past_days() -> None:
    orch, _ = _build()
    assert (await orch.build_context(USER, TODAY - timedelta(days=1))).value[
        "can_quick_add"
    ] is False
    assert (await orch.build_context(USER, TODAY + timedelta(days=1))).value[
        "can_quick_add"
    ] is True


@pytest.mark.asyncio
async def test_tasks_are_ordered_by_due_date_then_title() -> None:
    orch, _ = _build(
        tasks=[
            _task("b", scheduled=TODAY, title="Beta"),
            _task("a", scheduled=TODAY, title="Alpha"),
            _task("d", scheduled=TODAY, due=TODAY, title="Zed"),
        ]
    )
    ctx = (await orch.build_context(USER)).value
    assert [t.uid for t in ctx["tasks"]] == ["d", "a", "b"]


@pytest.mark.asyncio
async def test_other_domains_are_read_for_the_viewed_day() -> None:
    day = TODAY + timedelta(days=1)
    orch, services = _build()
    goal = Goal(uid="g1", user_uid=USER, title="Ship", target_date=day)
    services["goals"].get_user_items_in_range = AsyncMock(return_value=Result.ok([goal]))
    habit_item = MagicMock(name="habit-chip")
    services["calendar"].habit_items_for_day = AsyncMock(return_value=Result.ok([habit_item]))
    on_day = Choice(
        uid="c-on",
        user_uid=USER,
        title="Pick",
        decision_deadline=datetime.combine(day, datetime.min.time()),
    )
    off_day = Choice(uid="c-off", user_uid=USER, title="Skip", decided_at=datetime(2020, 1, 1))
    services["choices"].get_user_items_in_range = AsyncMock(
        return_value=Result.ok([off_day, on_day])
    )

    ctx = (await orch.build_context(USER, day)).value

    services["events"].get_user_items_in_range.assert_awaited_once_with(
        USER, day, day, include_completed=True
    )
    services["goals"].get_user_items_in_range.assert_awaited_once_with(
        USER, day, day, include_completed=True
    )
    services["calendar"].habit_items_for_day.assert_awaited_once_with(USER, day)
    assert ctx["milestones"] == [goal]
    assert ctx["habits"] == [habit_item]
    assert [c.uid for c in ctx["choices"]] == ["c-on"]
    # A dated read by either date field — never the capped "all choices" list.
    services["choices"].get_user_items_in_range.assert_awaited_once_with(
        USER,
        day,
        day,
        include_completed=True,
        date_field=["decision_deadline", "decided_at"],
    )


@pytest.mark.asyncio
async def test_a_failed_task_read_fails_the_page() -> None:
    orch, services = _build()
    services["tasks"].get_user_items_in_range = AsyncMock(
        return_value=Result.fail(Errors.database("get_user_items_in_range", "boom"))
    )
    result = await orch.build_context(USER)
    assert result.is_error


@pytest.mark.asyncio
async def test_task_reads_are_dated_never_the_whole_list() -> None:
    """The day's tasks and the overdue pile come from bounded range reads —
    a plain "all tasks" list is capped at the backend's page and would drop
    an old task due today or an old overdue one past that page."""
    orch, services = _build(tasks=[_task("t", scheduled=TODAY)])
    await orch.build_context(USER)

    calls = services["tasks"].get_user_items_in_range.await_args_list
    day_call = calls[0]
    assert day_call.args[1:] == (TODAY, TODAY)
    # Completed rows are excluded in the query — the lens's own exclusion set —
    # so completed past-due rows can never consume the read's page.
    assert day_call.kwargs == {
        "include_completed": False,
        "date_field": ["due_date", "scheduled_date"],
    }
    overdue_call = calls[1]
    assert overdue_call.args[2] == TODAY - timedelta(days=1)
    assert overdue_call.kwargs == {"include_completed": False, "date_field": "due_date"}
    assert not services["tasks"].get_user_tasks.called


@pytest.mark.asyncio
async def test_another_day_issues_no_overdue_read() -> None:
    orch, services = _build(tasks=[_task("t", scheduled=TODAY)])
    await orch.build_context(USER, TODAY + timedelta(days=2))
    assert services["tasks"].get_user_items_in_range.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "method"),
    [
        ("events", "get_user_items_in_range"),
        ("goals", "get_user_items_in_range"),
        ("calendar", "habit_items_for_day"),
        ("choices", "get_user_items_in_range"),
    ],
)
async def test_a_failed_section_read_degrades_to_an_empty_section(
    service: str, method: str
) -> None:
    orch, services = _build(tasks=[_task("t", scheduled=TODAY)])
    setattr(
        services[service], method, AsyncMock(return_value=Result.fail(Errors.database(method, "x")))
    )

    result = await orch.build_context(USER)

    assert result.is_ok
    assert [t.uid for t in result.value["tasks"]] == ["t"]
