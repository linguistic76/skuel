"""Render tests for the day view (``ui/today/page.py``).

Server-rendered, so everything is asserted on the markup: the sections and
their ``data-item-type`` containers (the shared legend filter's hook), the
defer controls and their source language, the calendar chips for habits, the
read-only rows, the quick-add gate, and the Prev/Next hrefs — which must
survive arbitrary ISO dates the ``/today/{date_str}`` route accepts.
"""

from __future__ import annotations

from datetime import date, datetime

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.choice.choice import Choice
from core.models.enums import EntityStatus
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.task.task import Task
from ui.today.page import TodayPage, _step_day

USER = "user_page"


def _ctx(today_iso: str, *, heading: str = "Today", can_quick_add: bool = True, **sections) -> dict:  # type: ignore[no-untyped-def]  # boundary: test context bag
    base = {
        "today_iso": today_iso,
        "date_label": "Saturday · March 22",
        "heading": heading,
        "is_today": True,
        "can_quick_add": can_quick_add,
        "overdue": [],
        "tasks": [],
        "events": [],
        "habits": [],
        "milestones": [],
        "choices": [],
    }
    base.update(sections)
    return base


def _task(uid: str, **fields) -> Task:  # type: ignore[no-untyped-def]  # boundary: dto-kwargs
    return Task(uid=uid, user_uid=USER, title=f"Task {uid}", status=EntityStatus.ACTIVE, **fields)


def _render(ctx: dict) -> str:  # type: ignore[type-arg]
    return to_xml(TodayPage(ctx))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Header + navigation
# ---------------------------------------------------------------------------


def test_step_day_steps_within_range() -> None:
    assert _step_day(date(2026, 7, 21), 1) == date(2026, 7, 22)
    assert _step_day(date(2026, 7, 21), -1) == date(2026, 7, 20)


def test_step_day_clamps_at_boundaries() -> None:
    assert _step_day(date.min, -1) == date.min
    assert _step_day(date.max, 1) == date.max


def test_today_page_renders_at_date_boundaries() -> None:
    for iso in ("0001-01-01", "9999-12-31"):
        html = _render(_ctx(iso))
        assert f'href="/today/{iso}"' in html  # the clamped arrow self-links


def test_header_binds_the_shared_legend_with_the_day_swatch_set() -> None:
    html = _render(_ctx("2026-09-12"))
    assert 'x-data="calendarLegend"' in html
    assert 'href="/today/2026-09-11"' in html and 'href="/today/2026-09-13"' in html
    for label in ("Task", "Event", "Habit", "Milestone", "Choice"):
        assert f">{label}</span>" in html
    assert html.count("toggleType(") == 5


# ---------------------------------------------------------------------------
# Quick-add gate + empty day
# ---------------------------------------------------------------------------


def test_quick_add_present_on_actable_day_anchored_to_view_date() -> None:
    html = _render(_ctx("2027-04-23"))
    assert 'hx-post="/today/tasks/quick-add"' in html
    assert 'name="view_date" value="2027-04-23"' in html


def test_quick_add_absent_on_past_day() -> None:
    html = _render(_ctx("2020-01-01", heading="Jan 1", can_quick_add=False))
    assert "/today/tasks/quick-add" not in html


def test_empty_day_shows_caught_up_and_no_sections() -> None:
    html = _render(_ctx("2026-09-12"))
    assert "You're caught up." in html
    assert "data-item-type=" not in html


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def test_overdue_and_tasks_render_cards_with_defer_controls() -> None:
    late = _task("late", due_date=date(2026, 9, 10))
    planned = _task("plan", scheduled_date=date(2026, 9, 12))
    html = _render(_ctx("2026-09-12", overdue=[late], tasks=[planned]))
    assert 'data-item-type="task"' in html
    assert ">Overdue</h2>" in html and ">Tasks</h2>" in html
    # The cards are the domain list's TaskCard — status toggles through the one door.
    assert 'hx-post="/api/tasks/late/status"' in html
    assert 'hx-post="/api/tasks/plan/status"' in html
    # Each card carries its defer control, speaking its surface's language.
    assert 'hx-post="/today/tasks/late/defer"' in html
    assert 'hx-post="/today/tasks/plan/defer"' in html
    assert 'name="source" value="triage"' in html
    assert 'name="source" value="day"' in html
    assert html.count('name="view_date" value="2026-09-12"') >= 3  # quick-add + two defers
    # A refused defer shows the server's reason beside the buttons; a completed
    # card reloads the day so membership decides what stays.
    assert html.count('role="status" data-defer-note') == 2
    assert html.count("hx-on::response-error") == 2
    assert html.count("hx-on::after-request") == 2
    assert "window.location.reload()" in html


def test_tasks_section_has_its_own_empty_state_when_other_sections_render() -> None:
    event = Event(
        uid="ev1",
        user_uid=USER,
        title="Standup",
        status=EntityStatus.SCHEDULED,
        event_date=date(2026, 9, 12),
    )
    html = _render(_ctx("2026-09-12", events=[event]))
    assert "No tasks on this day" in html
    assert 'data-item-type="event"' in html
    assert "Standup" in html
    assert "You're caught up." not in html


def test_habits_render_as_day_stamped_calendar_chips() -> None:
    chip = CalendarItem(
        uid="habit-h1",
        source_uid="h1",
        item_type=CalendarItemType.HABIT,
        title="Meditate",
        start_time=datetime(2026, 9, 12, 9, 0),
        end_time=datetime(2026, 9, 12, 9, 20),
        occurrence_data={"date": "2026-09-12", "status": "pending"},
    )
    html = _render(_ctx("2026-09-12", habits=[chip]))
    assert 'data-item-type="habit"' in html
    assert "Meditate" in html
    # The chip opens the day-aware modal — the per-day complete door lives there.
    assert "/cal/item-details/habit-h1?date=2026-09-12" in html


def test_milestones_and_choices_render_read_only_rows() -> None:
    goal = Goal(uid="g1", user_uid=USER, title="Ship it", target_date=date(2026, 9, 12))
    due = Choice(
        uid="c1", user_uid=USER, title="Pick a stack", decision_deadline=datetime(2026, 9, 12, 8)
    )
    decided = Choice(uid="c2", user_uid=USER, title="Chose", decided_at=datetime(2026, 9, 12, 20))
    html = _render(_ctx("2026-09-12", milestones=[goal], choices=[due, decided]))
    assert 'data-item-type="milestone"' in html
    assert 'href="/goals/detail?uid=g1"' in html
    assert 'data-item-type="choice"' in html
    assert 'href="/choices/detail?uid=c1"' in html
    assert "Decide by this day" in html
    assert ">Decided<" in html
    # Read-only: no status doors for these rows.
    assert "/api/goals/" not in html and "/api/choices/" not in html
