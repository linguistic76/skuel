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
    create_item_details_modal,
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


def _task_item(item_type: CalendarItemType = CalendarItemType.TASK_WORK) -> CalendarItem:
    return CalendarItem(
        uid="task-task_1",
        source_uid="task_1",
        item_type=item_type,
        title="Write report",
        start_time=datetime(2026, 8, 14, 9, 0),
        end_time=datetime(2026, 8, 14, 10, 0),
        all_day=item_type == CalendarItemType.TASK_DEADLINE,
    )


def test_task_modal_offers_date_only_reschedule() -> None:
    html = to_xml(create_item_details_modal(_task_item()))
    assert 'hx-post="/cal/item/task-task_1/reschedule"' in html
    assert 'name="new_date"' in html
    assert 'value="2026-08-14"' in html  # prefilled with the current date
    assert 'name="new_time"' not in html  # tasks move by date only
    # The OOB target the reschedule POST flips on success.
    assert 'id="item-schedule-text"' in html


def test_deadline_task_modal_also_offers_reschedule() -> None:
    html = to_xml(create_item_details_modal(_task_item(CalendarItemType.TASK_DEADLINE)))
    assert 'hx-post="/cal/item/task-task_1/reschedule"' in html
    assert 'name="new_date"' in html


def test_event_modal_offers_date_and_time_reschedule() -> None:
    item = CalendarItem(
        uid="event-event_1",
        source_uid="event_1",
        item_type=CalendarItemType.EVENT,
        title="Standup",
        start_time=datetime(2026, 8, 14, 10, 30),
        end_time=datetime(2026, 8, 14, 11, 30),
    )
    html = to_xml(create_item_details_modal(item))
    assert 'hx-post="/cal/item/event-event_1/reschedule"' in html
    assert 'name="new_date"' in html
    assert 'name="new_time"' in html
    assert 'value="10:30"' in html  # prefilled with the current start time


def test_habit_modal_never_offers_reschedule() -> None:
    """Habits recur — they don't reschedule (C4 rejected design)."""
    for habit_modal in (
        create_item_details_modal(_habit_item()),
        create_item_details_modal(_stamped(date.today() - timedelta(days=1))),
    ):
        assert "/reschedule" not in to_xml(habit_modal)
