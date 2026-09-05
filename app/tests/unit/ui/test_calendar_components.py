"""Unit tests for calendar UI components — day-aware habit chips + modal (C3).

The act-from arc's heart: habit chips are stamped with their occurrence day
during ``_items_by_date`` expansion, open a day-aware item-details modal
(``?date=``), and render completed days distinctly; the modal's Mark Complete
posts THAT day and never offers completion on future or already-done days.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
    CalendarView,
)
from core.models.type_hints import EntityUID
from ui.calendar.components import (
    _event_chip,
    _items_by_date,
    _opens_detail_modal,
    calendar_nav_cluster,
    create_calendar_legend,
    create_calendar_toolbar,
    create_day_cell,
    create_item_details_modal,
    create_week_grid,
)


def _habit_item(occurrence_data: dict[str, str] | None = None) -> CalendarItem:
    now = datetime(2026, 8, 1, 12, 0)
    return CalendarItem(
        uid="habit-habit_1",
        source_uid="habit_1",
        item_type=CalendarItemType.HABIT,
        title="Meditate",
        start_time=now,
        end_time=now,
        streak_count=4,
        occurrence_data=occurrence_data,
    )


def _stamped(day: date, status: CompletionStatus = CompletionStatus.PENDING) -> CalendarItem:
    return _habit_item({"date": day.isoformat(), "status": status.value})


# ---------------------------------------------------------------------------
# _items_by_date — habit chips know their day
# ---------------------------------------------------------------------------


def test_items_by_date_stamps_habit_chips_with_day_and_status() -> None:
    habit = _habit_item()
    data = CalendarData(
        items=[habit],
        occurrences={
            EntityUID("habit_1"): [
                CalendarOccurrence(
                    calendar_item_uid="habit_1",
                    date=date(2026, 8, 1),
                    status=CompletionStatus.DONE,
                ),
                CalendarOccurrence(
                    calendar_item_uid="habit_1",
                    date=date(2026, 8, 2),
                    status=CompletionStatus.PENDING,
                ),
            ]
        },
        view=CalendarView.WEEK,
        start_date=date(2026, 7, 27),
        end_date=date(2026, 8, 2),
        metadata={},
    )
    by_date = _items_by_date(data)
    done_chip = by_date[date(2026, 8, 1)][0]
    pending_chip = by_date[date(2026, 8, 2)][0]
    assert done_chip.occurrence_data == {"date": "2026-08-01", "status": "done"}
    assert pending_chip.occurrence_data == {"date": "2026-08-02", "status": "pending"}


# ---------------------------------------------------------------------------
# _event_chip — day-aware interactivity + completed styling hook
# ---------------------------------------------------------------------------


def test_day_stamped_habit_chip_opens_day_aware_modal() -> None:
    chip = to_xml(_event_chip(_stamped(date(2026, 8, 1))))
    assert 'hx-get="/cal/item-details/habit-habit_1?date=2026-08-01"' in chip
    assert "data-completed" not in chip


def test_completed_habit_chip_carries_data_completed() -> None:
    chip = to_xml(_event_chip(_stamped(date(2026, 8, 1), CompletionStatus.DONE), large=True))
    assert 'data-completed="true"' in chip
    assert "calendar-item-title" in chip  # the CSS ✓ hook


def test_unstamped_habit_stub_stays_display_only() -> None:
    """The raw now()-stamped habit stub has no day — it must not open a modal
    that would reconstruct the day from 'today' (the original defect)."""
    assert _opens_detail_modal(_habit_item()) is False
    chip = to_xml(_event_chip(_habit_item()))
    assert "hx-get" not in chip


def test_non_habit_chip_still_opens_modal_without_date_param() -> None:
    item = CalendarItem(
        uid="event-event_1",
        source_uid="event_1",
        item_type=CalendarItemType.EVENT,
        title="Standup",
        start_time=datetime(2026, 8, 1, 10, 0),
        end_time=datetime(2026, 8, 1, 11, 0),
    )
    chip = to_xml(_event_chip(item))
    assert 'hx-get="/cal/item-details/event-event_1"' in chip


# ---------------------------------------------------------------------------
# create_item_details_modal — the modal shows THAT day
# ---------------------------------------------------------------------------


def test_modal_names_the_occurrence_day_and_offers_mark_complete() -> None:
    day = date.today() - timedelta(days=1)
    html = to_xml(create_item_details_modal(_stamped(day)))
    assert f"{day:%A}" in html  # the day is named, not reconstructed
    assert "Mark Complete" in html
    assert f'"on_date": "{day.isoformat()}"' in html
    assert 'hx-post="/cal/habit/habit_1/complete"' in html
    assert "Not completed on this day" in html
    # The OOB target the habit-complete POST flips on success.
    assert 'id="habit-day-state"' in html


def test_modal_shows_completed_state_for_done_day() -> None:
    day = date.today() - timedelta(days=1)
    html = to_xml(create_item_details_modal(_stamped(day, CompletionStatus.DONE)))
    assert "Completed ✓" in html
    assert "Completed on this day ✓" in html
    assert "Mark Complete" not in html
    assert "hx-post" not in html


def test_modal_offers_no_completion_on_future_day() -> None:
    day = date.today() + timedelta(days=1)
    html = to_xml(create_item_details_modal(_stamped(day)))
    assert "Mark Complete" not in html
    assert "hx-post" not in html


def test_modal_offers_no_completion_without_day_stamp() -> None:
    html = to_xml(create_item_details_modal(_habit_item()))
    assert "Mark Complete" not in html
    assert "hx-post" not in html


# ---------------------------------------------------------------------------
# create_item_details_modal — reschedule form (act-from arc C4)
# ---------------------------------------------------------------------------


def _task_item(
    is_due: bool = False,
    status: str = "active",
) -> CalendarItem:
    return CalendarItem(
        uid="task-task_1",
        source_uid="task_1",
        item_type=CalendarItemType.TASK,
        title="Write report",
        start_time=datetime(2026, 8, 14, 9, 0),
        end_time=datetime(2026, 8, 14, 10, 0),
        all_day=is_due,
        is_due=is_due,
        metadata={"status": status},
    )


def test_task_modal_offers_date_only_reschedule() -> None:
    html = to_xml(create_item_details_modal(_task_item()))
    assert 'hx-post="/cal/item/task-task_1/reschedule"' in html
    assert 'name="new_date"' in html
    assert 'value="2026-08-14"' in html  # prefilled with the current date
    assert 'name="new_time"' not in html  # tasks move by date only
    # The OOB target the reschedule POST flips on success.
    assert 'id="item-schedule-text"' in html


def test_due_state_task_modal_also_offers_reschedule() -> None:
    html = to_xml(create_item_details_modal(_task_item(is_due=True)))
    assert 'hx-post="/cal/item/task-task_1/reschedule"' in html
    assert 'name="new_date"' in html


def test_terminal_task_modal_offers_no_reschedule() -> None:
    """A finished task has no work left to move, so the modal offers no
    reschedule form. A UI judgement, not a service refusal — ``update_task``
    would accept the date change (Tasks has no terminal-state rule)."""
    for status in ("cancelled", "failed", "archived", "completed"):
        html = to_xml(create_item_details_modal(_task_item(status=status)))
        assert "/reschedule" not in html, f"terminal status {status} must hide the form"


def test_unknown_task_status_still_offers_reschedule() -> None:
    """A missing/unknown status counts as actionable — the reschedule route's
    own guards stay the backstop, and their refusal renders in the form."""
    html = to_xml(create_item_details_modal(_task_item(status="")))
    assert 'hx-post="/cal/item/task-task_1/reschedule"' in html


def _event_item(day: date) -> CalendarItem:
    return CalendarItem(
        uid="event-event_1",
        source_uid="event_1",
        item_type=CalendarItemType.EVENT,
        title="Standup",
        start_time=datetime.combine(day, datetime.min.time().replace(hour=10, minute=30)),
        end_time=datetime.combine(day, datetime.min.time().replace(hour=11, minute=30)),
    )


def test_event_modal_offers_date_and_time_reschedule() -> None:
    html = to_xml(create_item_details_modal(_event_item(date.today() + timedelta(days=7))))
    assert 'hx-post="/cal/item/event-event_1/reschedule"' in html
    assert 'name="new_date"' in html
    assert 'name="new_time"' in html
    assert 'value="10:30"' in html  # prefilled with the current start time


def test_todays_event_modal_still_offers_reschedule() -> None:
    """event_date == today is mutable — only strictly-past events are frozen."""
    html = to_xml(create_item_details_modal(_event_item(date.today())))
    assert 'hx-post="/cal/item/event-event_1/reschedule"' in html


def test_past_event_modal_offers_no_reschedule() -> None:
    """Past events are immutable historical records — the events service
    refuses date/time changes, so the modal must not offer a form that is
    guaranteed to fail."""
    html = to_xml(create_item_details_modal(_event_item(date.today() - timedelta(days=1))))
    assert "/reschedule" not in html
    assert 'name="new_date"' not in html


def test_habit_modal_never_offers_reschedule() -> None:
    """Habits recur — they don't reschedule (C4 rejected design)."""
    for habit_modal in (
        create_item_details_modal(_habit_item()),
        create_item_details_modal(_stamped(date.today() - timedelta(days=1))),
    ):
        assert "/reschedule" not in to_xml(habit_modal)


# ---------------------------------------------------------------------------
# create_item_details_modal — goal milestones (act-from arc C5)
# ---------------------------------------------------------------------------


def _milestone_item() -> CalendarItem:
    day = date(2026, 8, 21)
    return CalendarItem(
        uid="goal-goal_1",
        source_uid="goal_1",
        item_type=CalendarItemType.MILESTONE,
        title="Focus on Van",
        start_time=datetime.combine(day, datetime.min.time()),
        end_time=datetime.combine(day, datetime.max.time()),
        all_day=True,
    )


def test_milestone_chip_opens_detail_modal() -> None:
    """Milestone chips are clickable the moment they exist (#911 gotcha) —
    the chip must point at the item-details endpoint."""
    assert _opens_detail_modal(_milestone_item()) is True
    chip = to_xml(_event_chip(_milestone_item()))
    assert 'hx-get="/cal/item-details/goal-goal_1"' in chip
    assert 'data-item-type="milestone"' in chip


def test_milestone_modal_offers_view_goal_link() -> None:
    html = to_xml(create_item_details_modal(_milestone_item()))
    assert "View Goal" in html
    assert 'href="/goals/detail?uid=goal_1"' in html


def test_milestone_modal_never_offers_reschedule() -> None:
    """Goal target dates move on the goals surface, not the calendar (C5)."""
    html = to_xml(create_item_details_modal(_milestone_item()))
    assert "/reschedule" not in html
    assert 'name="new_date"' not in html


# ---------------------------------------------------------------------------
# Day-click acts: cell/card body opens the day lens; date number stays the
# daily-note door (act-from arc C6)
# ---------------------------------------------------------------------------


def test_month_day_cell_click_opens_day_lens_number_keeps_daily_note() -> None:
    cell = to_xml(create_day_cell(date(2026, 8, 20), [], is_current_month=True, is_weekend=False))
    # Cell body click → the day lens (the acting surface).
    assert "window.location.href='/today/2026-08-20'" in cell
    # Guarded so chips and the date-number link stay independently clickable.
    assert "closest('.calendar-item,a')" in cell
    # The date-number link still opens that day's daily note.
    assert 'href="/journals/daily/2026-08-20"' in cell


def test_month_past_day_cell_still_navigates_to_its_lens() -> None:
    """Reviewing a past day is legitimate — the cell always opens its lens."""
    cell = to_xml(create_day_cell(date(2020, 1, 1), [], is_current_month=True, is_weekend=False))
    assert "window.location.href='/today/2020-01-01'" in cell


def test_week_card_click_opens_day_lens_head_keeps_daily_note() -> None:
    data = CalendarData(
        items=[],
        occurrences={},
        view=CalendarView.WEEK,
        start_date=date(2026, 8, 17),  # Monday
        end_date=date(2026, 8, 23),
        metadata={},
    )
    grid = to_xml(create_week_grid(data))
    # Each day card body opens that day's lens; the head link keeps the daily note.
    assert "window.location.href='/today/2026-08-20'" in grid
    assert 'href="/journals/daily/2026-08-20"' in grid


# ---------------------------------------------------------------------------
# Toolbar: Prev/Now/Next only. The "Notes" picker moved to the navbar
# (tests/unit/ui/test_navbar_period_notes.py).
# ---------------------------------------------------------------------------


def test_toolbar_carries_the_three_nav_pills_and_no_notes_door() -> None:
    toolbar = to_xml(
        create_calendar_toolbar(
            prev_href="/cal/month/2026/7",
            next_href="/cal/month/2026/9",
            today_href="/cal",
        )
    )
    assert 'href="/cal/month/2026/7"' in toolbar
    assert 'href="/cal/month/2026/9"' in toolbar
    assert 'href="/cal"' in toolbar
    # The periodic-note door is the navbar's now — two doors would drift apart.
    assert "period-note-menu" not in toolbar
    assert "/journals/" not in toolbar


def test_day_lens_cluster_is_the_same_three_pills() -> None:
    """The Today header embeds the bare cluster, so all three temporal lenses
    carry an identical navigation cluster (#665)."""
    cluster = to_xml(
        calendar_nav_cluster(
            prev_href="/today/2026-08-01",
            next_href="/today/2026-08-03",
            today_href="/today",
        )
    )
    assert 'href="/today/2026-08-01"' in cluster
    assert 'href="/today/2026-08-03"' in cluster
    assert "period-note-menu" not in cluster


# ---------------------------------------------------------------------------
# create_calendar_legend — pair-grouped, one Task kind, visible affordance
# (periodic-notes arc S1/E1)
# ---------------------------------------------------------------------------


def test_legend_groups_four_kinds_by_activity_pair() -> None:
    html = to_xml(create_calendar_legend())
    assert "Tasks + Events" in html
    assert "Goals + Habits" in html
    # Four kind-swatches, one per legend word — Deadline is dead as a kind.
    for label in ("Task", "Event", "Milestone", "Habit"):
        assert f">{label}</span>" in html
    assert "Deadline" not in html
    assert html.count("toggleType(") == 4
    # Choices/Principles never appear (R2 — the compass lives in the note).
    assert "Choice" not in html
    assert "Principle" not in html


def test_legend_swatches_read_as_controls() -> None:
    """The filter/spotlight interactivity must be discoverable: real buttons,
    a border (control styling), and a tooltip naming both behaviors."""
    html = to_xml(create_calendar_legend())
    assert html.count("<button") == 4
    assert "border-border" in html
    assert html.count("Click to show/hide") == 4
    assert "hover to spotlight" in html


def test_due_state_task_chip_carries_cue_and_task_type() -> None:
    """A due-but-unscheduled task chip keeps the ONE Task kind for filtering
    but visibly carries the due state: data-due + ⏰ (E1)."""
    chip = to_xml(_event_chip(_task_item(is_due=True)))
    assert 'data-item-type="task"' in chip
    assert 'data-due="true"' in chip
    assert "⏰" in chip


def test_scheduled_task_chip_has_no_due_cue() -> None:
    chip = to_xml(_event_chip(_task_item()))
    assert 'data-item-type="task"' in chip
    assert "data-due" not in chip
    assert "⏰" not in chip
