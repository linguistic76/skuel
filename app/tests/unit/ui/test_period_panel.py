"""Unit tests for the periodic-note read panel (periodic-notes arc S3).

The panel shows the period's existing entities in pair vocabulary
(Tasks + Events / Goals + Habits), each row dooring to its day's lens
(/today/{date}). Strictly read-only (ruling E2 — no app-side planning
affordances on the note); habits never render in v1; a due-only task keeps its
⏰ + red STATE cue (E1). ``planning_period`` resolves the weekly note to its
ISO week, the monthly note to its calendar month, the quarterly note to its
three months and the yearly note to Jan 1 through Dec 31; the daily note gets no
period. A period long enough to lose one's place in (quarterly, yearly)
sub-heads its rows by month. ``PeriodicNotePage`` grows a third column only
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
    quarterly_period_start,
    weekly_period_start,
    yearly_period_start,
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
    """The day lens IS the daily note's panel; an unknown kind never plans."""
    assert planning_period("daily", "2026-08-03") is None
    assert planning_period("fortnightly", "2026-08") is None
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


# ---------------------------------------------------------------------------
# quarterly_period_start / yearly_period_start — the two new key contracts
# ---------------------------------------------------------------------------

_FOREIGN_KEYS = ("2026-W32", "2026-08", "2026-08-03", "2026-Q3", "2026")


def test_quarterly_period_start_parses_the_contract_form() -> None:
    assert quarterly_period_start("2026-Q1") == date(2026, 1, 1)
    assert quarterly_period_start("2026-Q3") == date(2026, 7, 1)
    assert quarterly_period_start("2026-Q4") == date(2026, 10, 1)


def test_quarterly_period_start_rejects_an_out_of_range_quarter() -> None:
    """Q5 would wrap into month 13 — rejected, never coerced."""
    assert quarterly_period_start("2026-Q0") is None
    assert quarterly_period_start("2026-Q5") is None


def test_yearly_period_start_parses_the_contract_form() -> None:
    assert yearly_period_start("2026") == date(2026, 1, 1)
    assert yearly_period_start("2024") == date(2024, 1, 1)


def test_every_parser_rejects_every_foreign_key_form() -> None:
    """The four key forms overlap dangerously: ``2026-Q3`` and ``2026-W32``
    share a shape, and ``2026`` is a prefix of all three others. Each parser
    must answer None for every key that is not its own — a coerced key would
    silently plan the wrong range.
    """
    parsers = {
        "2026-W32": weekly_period_start,
        "2026-08": monthly_period_start,
        "2026-Q3": quarterly_period_start,
        "2026": yearly_period_start,
    }
    for own_key, parser in parsers.items():
        assert parser(own_key) is not None, own_key
        for foreign in _FOREIGN_KEYS:
            if foreign == own_key:
                continue
            assert parser(foreign) is None, f"{parser.__name__} accepted {foreign}"


# ---------------------------------------------------------------------------
# planning_period — the two new ranges
# ---------------------------------------------------------------------------


def test_quarterly_period_is_the_quarters_three_months() -> None:
    period = planning_period("quarterly", "2026-Q3")
    assert period is not None
    assert (period.start, period.end) == (date(2026, 7, 1), date(2026, 9, 30))
    assert period.heading == "This quarter"
    # The en dash is escaped so the assertion stays byte-exact against the
    # label the panel renders (ruff flags a literal one as confusable).
    assert period.range_label == "Q3 2026 \u00b7 Jul \u2013 Sep"
    assert period.empty_label == "Nothing this quarter"


def test_quarterly_period_covers_q1_and_q4_edges_and_leap_february() -> None:
    q1 = planning_period("quarterly", "2024-Q1")  # leap year
    assert q1 is not None and (q1.start, q1.end) == (date(2024, 1, 1), date(2024, 3, 31))
    assert q1.start <= date(2024, 2, 29) <= q1.end
    q4 = planning_period("quarterly", "2026-Q4")
    assert q4 is not None and (q4.start, q4.end) == (date(2026, 10, 1), date(2026, 12, 31))


def test_yearly_period_is_january_first_to_december_thirty_first() -> None:
    period = planning_period("yearly", "2026")
    assert period is not None
    assert (period.start, period.end) == (date(2026, 1, 1), date(2026, 12, 31))
    assert period.heading == "This year"
    assert period.range_label == "2026"
    assert period.empty_label == "Nothing this year"


def test_new_kinds_degrade_to_no_period_on_an_unparseable_key() -> None:
    assert planning_period("quarterly", "2026-W32") is None
    assert planning_period("yearly", "2026-08") is None


# ---------------------------------------------------------------------------
# Month sub-headings — long periods only
# ---------------------------------------------------------------------------


def _spanning_items() -> list[CalendarItem]:
    """Chronological items in three consecutive months (a Q3 spread)."""
    return [
        _item("task-task_jul", CalendarItemType.TASK, title="July work", day=date(2026, 7, 6)),
        _item("task-task_aug", CalendarItemType.TASK, title="August work", day=date(2026, 8, 3)),
        _item("task-task_sep", CalendarItemType.TASK, title="Sept work", day=date(2026, 9, 14)),
    ]


def test_quarterly_and_yearly_periods_group_by_month() -> None:
    for kind, key in (("quarterly", "2026-Q3"), ("yearly", "2026")):
        period = planning_period(kind, key)
        assert period is not None and period.groups_by_month, kind


def test_weekly_and_monthly_periods_do_not_group_by_month() -> None:
    """Parity is preserved: the two shipped panels render exactly as before."""
    assert not _week().groups_by_month
    assert not _month().groups_by_month


def test_cross_month_week_still_renders_flat() -> None:
    """A week CAN span two months (Jul 27 to Aug 2) but still reads as one run
    of days — the sub-heading is a long-period affordance, not a span test."""
    week = planning_period("weekly", "2026-W31")
    assert week is not None
    assert (week.start, week.end) == (date(2026, 7, 27), date(2026, 8, 2))
    assert not week.groups_by_month


def test_quarterly_panel_sub_heads_each_month_run() -> None:
    period = planning_period("quarterly", "2026-Q3")
    assert period is not None
    xml = _panel_xml(_spanning_items(), period)

    assert "July 2026" in xml and "August 2026" in xml and "September 2026" in xml
    # Sub-heads open each run in chronological order, above their own rows.
    assert xml.index("July 2026") < xml.index("July work") < xml.index("August 2026")
    assert xml.index("August 2026") < xml.index("August work") < xml.index("September 2026")


def test_weekly_panel_has_no_month_sub_heads() -> None:
    xml = _panel_xml(_spanning_items(), _week())

    assert "July work" in xml  # rows still render
    assert "July 2026" not in xml and "September 2026" not in xml


def test_monthly_panel_has_no_month_sub_heads() -> None:
    """The month's own name is the panel's range label — never a row sub-head."""
    xml = _panel_xml(_spanning_items(), _month())

    assert xml.count("August 2026") == 1  # the range label alone
    assert "July 2026" not in xml


def test_sub_headed_panel_stays_read_only() -> None:
    period = planning_period("yearly", "2026")
    assert period is not None
    xml = _panel_xml(_spanning_items(), period)

    assert "<form" not in xml
    assert "<button" not in xml
