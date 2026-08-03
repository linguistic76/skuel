"""Unit tests for the weekly-note read panel (periodic-notes arc S3).

The panel shows the ISO week's existing entities in pair vocabulary
(Tasks + Events / Goals + Habits), each row dooring to its day's lens
(/today/{date}). Strictly read-only (ruling E2 — no app-side planning
affordances on the weekly note); habits never render in v1; a due-only task
keeps its ⏰ + red STATE cue (E1). ``PeriodicNotePage`` grows a third column
only when a panel is passed — daily/monthly stay two-column.
"""

from __future__ import annotations

from datetime import date, datetime

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.event.calendar_models import CalendarItem, CalendarItemType
from ui.journals.week_panel import WeeklyPlanningPanel, weekly_period_start

_WEEK_START = date(2026, 8, 3)  # Monday of ISO week 2026-W32


def _item(
    uid: str,
    item_type: CalendarItemType,
    *,
    title: str,
    day: date,
    is_due: bool = False,
) -> CalendarItem:
    start = datetime.combine(day, datetime.min.time().replace(hour=9))
    return CalendarItem(
        uid=uid,
        source_uid=uid.split("-", 1)[1],
        item_type=item_type,
        title=title,
        start_time=start,
        end_time=start,
        is_due=is_due,
        color=item_type.get_color(),
        icon="⏰" if is_due else item_type.get_icon(),
    )


def _panel_xml(items: list[CalendarItem]) -> str:
    return to_xml(WeeklyPlanningPanel(items, week_start=_WEEK_START))


# ---------------------------------------------------------------------------
# weekly_period_start — the period-key contract
# ---------------------------------------------------------------------------


def test_weekly_period_start_parses_the_contract_form() -> None:
    monday = weekly_period_start("2026-W32")
    assert monday == date(2026, 8, 3)
    assert monday is not None and monday.weekday() == 0  # Monday-start, permanent


def test_weekly_period_start_rejects_non_weekly_keys() -> None:
    assert weekly_period_start("2026-08-03") is None  # a daily key
    assert weekly_period_start("2026-08") is None  # a monthly key
    assert weekly_period_start("junk") is None
    assert weekly_period_start("2026-W99") is None  # no such ISO week


# ---------------------------------------------------------------------------
# WeeklyPlanningPanel — pair vocabulary, day-lens doors, read-only
# ---------------------------------------------------------------------------


def test_panel_groups_in_pair_vocabulary() -> None:
    xml = _panel_xml(
        [
            _item("task-task_1", CalendarItemType.TASK, title="Write draft", day=_WEEK_START),
            _item("event-event_1", CalendarItemType.EVENT, title="Team sync", day=date(2026, 8, 5)),
            _item("goal-goal_1", CalendarItemType.MILESTONE, title="Ship v1", day=date(2026, 8, 9)),
        ]
    )

    assert "Tasks + Events" in xml
    assert "Goals + Habits" in xml
    assert "Write draft" in xml and "Team sync" in xml and "Ship v1" in xml


def test_rows_door_to_the_day_lens() -> None:
    xml = _panel_xml(
        [
            _item("task-task_1", CalendarItemType.TASK, title="Write draft", day=date(2026, 8, 4)),
            _item("event-event_1", CalendarItemType.EVENT, title="Team sync", day=date(2026, 8, 5)),
        ]
    )

    assert 'href="/today/2026-08-04"' in xml
    assert 'href="/today/2026-08-05"' in xml


def test_due_only_task_keeps_the_due_state_cue() -> None:
    """E1: due-ness is chip state (⏰ + red), never a kind or a legend word."""
    xml = _panel_xml(
        [
            _item(
                "task-task_due",
                CalendarItemType.TASK,
                title="Pay invoice",
                day=date(2026, 8, 7),
                is_due=True,
            )
        ]
    )

    assert "⏰" in xml
    assert "text-red-600" in xml
    assert "Deadline" not in xml  # the kind died in E1


def test_habits_never_render_in_v1() -> None:
    """A habit item passed defensively simply does not render (v1 exclusion)."""
    xml = _panel_xml(
        [
            _item("habit-habit_1", CalendarItemType.HABIT, title="Meditate", day=_WEEK_START),
            _item("task-task_1", CalendarItemType.TASK, title="Write draft", day=_WEEK_START),
        ]
    )

    assert "Meditate" not in xml
    assert "Write draft" in xml


def test_panel_is_read_only() -> None:
    """No forms, no buttons, no HTMX mutations — rows are navigation only (E2)."""
    xml = _panel_xml(
        [
            _item("task-task_1", CalendarItemType.TASK, title="Write draft", day=_WEEK_START),
            _item("goal-goal_1", CalendarItemType.MILESTONE, title="Ship v1", day=date(2026, 8, 9)),
        ]
    )

    assert "<form" not in xml
    assert "<button" not in xml
    assert "hx-post" not in xml and "hx-put" not in xml and "hx-delete" not in xml


def test_empty_groups_render_a_muted_empty_state() -> None:
    xml = _panel_xml([])

    assert xml.count("Nothing this week") == 2
    assert "Tasks + Events" in xml and "Goals + Habits" in xml


def test_panel_header_names_the_week_range() -> None:
    xml = _panel_xml([])

    assert "This week" in xml
    # The range label joins the endpoints with an en dash (deliberate UI copy;
    # RUF001 would flag the literal here, so assert via the escape).
    assert "Aug 3 \u2013 9" in xml


# ---------------------------------------------------------------------------
# PeriodicNotePage — the panel column appears only when passed
# ---------------------------------------------------------------------------


def _entry(kind: str, period_key: str) -> object:
    from core.models.enums.entity_enums import EntityStatus
    from core.models.user_entry.user_entry import UserEntry

    created = datetime(2026, 8, 1, 8, 0)
    return UserEntry(
        uid=f"ue:{kind}:user_test:{period_key}",
        user_uid="user_test",
        title=f"{kind.title()} Note",
        content="",
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        metadata={"entry_kind": kind, "period_key": period_key},
    )


def test_periodic_note_page_includes_panel_when_passed() -> None:
    from fasthtml.common import Div

    from ui.journals.chat_page import PeriodicNotePage

    panel = WeeklyPlanningPanel([], week_start=_WEEK_START)
    xml = to_xml(
        PeriodicNotePage(
            entry=_entry("weekly", "2026-W32"),
            initial_workspace=Div("workspace"),
            week_panel=panel,
        )
    )

    assert 'id="week-panel"' in xml
    assert "Tasks + Events" in xml


def test_periodic_note_page_stays_two_column_without_panel() -> None:
    from fasthtml.common import Div

    from ui.journals.chat_page import PeriodicNotePage

    xml = to_xml(
        PeriodicNotePage(
            entry=_entry("daily", "2026-08-03"),
            initial_workspace=Div("workspace"),
        )
    )

    assert 'id="week-panel"' not in xml
    assert "Tasks + Events" not in xml
