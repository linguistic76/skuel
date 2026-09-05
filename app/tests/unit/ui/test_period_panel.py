"""Unit tests for the periodic-note read panel (periodic-notes arc S3).

The panel shows the period's existing entities in pair vocabulary
(Tasks + Events / Goals + Habits), each row dooring to its day's lens
(/today/{date}). Strictly read-only (ruling E2 — no app-side planning
affordances on the note); habits never render in v1; a due-only task keeps its
⏰ + red STATE cue (E1). ``planning_period`` resolves the weekly note to its
ISO week and the monthly note to its calendar month;
the daily note gets no period. ``PeriodicNotePage`` grows a third column only
when a panel is passed.
"""

from __future__ import annotations

from datetime import date, datetime

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.event.calendar_models import CalendarItem, CalendarItemType
from ui.journals.period_panel import (
    PlanningPanel,
    PlanningPeriod,
    monthly_period_start,
    planning_period,
    weekly_period_start,
)

_WEEK_START = date(2026, 8, 3)  # Monday of ISO week 2026-W32


def _week() -> PlanningPeriod:
    period = planning_period("weekly", "2026-W32")
    assert period is not None
    return period


def _month() -> PlanningPeriod:
    period = planning_period("monthly", "2026-08")
    assert period is not None
    return period


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


def _panel_xml(items: list[CalendarItem], period: PlanningPeriod | None = None) -> str:
    return to_xml(PlanningPanel(items, period if period is not None else _week()))


# ---------------------------------------------------------------------------
# weekly_period_start / monthly_period_start — the period-key contracts
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


def test_monthly_period_start_parses_the_contract_form() -> None:
    assert monthly_period_start("2026-08") == date(2026, 8, 1)
    assert monthly_period_start("2026-12") == date(2026, 12, 1)


def test_monthly_period_start_rejects_non_monthly_keys() -> None:
    assert monthly_period_start("2026-08-03") is None  # a daily key — never truncated
    assert monthly_period_start("2026-W32") is None  # a weekly key
    assert monthly_period_start("2026") is None
    assert monthly_period_start("junk") is None
    assert monthly_period_start("2026-13") is None  # no such month


# ---------------------------------------------------------------------------
# planning_period — which notes plan, and against what range
# ---------------------------------------------------------------------------


def test_weekly_period_is_the_iso_week() -> None:
    period = _week()
    assert (period.start, period.end) == (date(2026, 8, 3), date(2026, 8, 9))
    assert period.heading == "This week"
    assert period.empty_label == "Nothing this week"


def test_monthly_period_is_the_calendar_month() -> None:
    period = _month()
    assert (period.start, period.end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert period.heading == "This month"
    assert period.range_label == "August 2026"
    assert period.empty_label == "Nothing this month"


def test_monthly_period_end_respects_short_months() -> None:
    feb = planning_period("monthly", "2028-02")  # leap year
    assert feb is not None and feb.end == date(2028, 2, 29)
    apr = planning_period("monthly", "2026-04")
    assert apr is not None and apr.end == date(2026, 4, 30)


def test_daily_and_unknown_kinds_get_no_period() -> None:
    """The day lens IS the daily note's panel; nothing else plans."""
    assert planning_period("daily", "2026-08-03") is None
    assert planning_period("quarterly", "2026-Q3") is None
    assert planning_period("", "2026-08") is None


def test_unparseable_key_degrades_to_no_period() -> None:
    assert planning_period("weekly", "2026-08") is None
    assert planning_period("monthly", "2026-W32") is None


# ---------------------------------------------------------------------------
# PlanningPanel — pair vocabulary, day-lens doors, read-only
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


def test_monthly_panel_speaks_the_month() -> None:
    """Parity: the same panel, headed by the month, rows still door to days."""
    xml = _panel_xml(
        [
            _item("task-task_1", CalendarItemType.TASK, title="Write draft", day=date(2026, 8, 20)),
        ],
        _month(),
    )

    assert "This month" in xml and "August 2026" in xml
    assert "This week" not in xml
    assert xml.count("Nothing this month") == 1  # the Goals + Habits group
    assert 'href="/today/2026-08-20"' in xml


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

    panel = PlanningPanel([], _month())
    xml = to_xml(
        PeriodicNotePage(
            entry=_entry("monthly", "2026-08"),
            initial_workspace=Div("workspace"),
            planning_panel=panel,
        )
    )

    assert 'id="planning-panel"' in xml
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

    assert 'id="planning-panel"' not in xml
    assert "Tasks + Events" not in xml
