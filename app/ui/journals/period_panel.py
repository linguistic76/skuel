"""Periodic-note read panel — the period the note plans against (periodic-notes arc S3).

Template-led planning (ruling E2): forward planning happens through checkbox/DSL
lines in the vault weekly/monthly note; the app SHOWS the period's existing
entities for planning-against and accountability (R4). This panel is strictly
read-only — no mutations, no quick-add. Every row doors to its day's lens
(``/today/{date}``), where acting happens (act-from arc C6/C7).

Four periods carry the panel: weekly (ISO week), monthly (calendar month;
ruling: ``docs/roadmap/done/monthly-note-panel-parity.md``), quarterly (three
calendar months) and yearly (Jan 1 – Dec 31; ruling:
``docs/roadmap/done/quarterly-yearly-periodic-notes.md``). The daily note never
does — its day lens IS the panel. ``planning_period`` is the one place that
knows which kinds plan, how their period keys parse, and which of them are long
enough to need month sub-headings; the period-key parsers it reads are the
shared contract in ``core/utils/period_keys.py`` (the reports speak the same
weekly and monthly keys).

Vocabulary is the calendar's pair grouping (R1/R2, matching the legend's
``_LEGEND_PAIRS``): Tasks + Events, then Goals + Habits. The Goals + Habits
group holds Milestones only — habits are deliberately absent from v1 (daily
recurrence is calendar texture, not planning matter). Choices/Principles
never appear: the compass lives in the writing, not in chips (R2). A due-only
task keeps its ⏰ + red state cue — a STATE of a Task, never a kind (E1).
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from fasthtml.common import A, Div, P, Span

from core.models.event.calendar_models import CalendarItemType
from core.utils.period_keys import (
    monthly_period_start,
    quarterly_period_start,
    weekly_period_start,
    yearly_period_start,
)

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.event.calendar_models import CalendarItem


@dataclass(frozen=True)
class PlanningPeriod:
    """The date range a periodic note plans against, plus its panel copy."""

    start: date
    end: date
    heading: str
    range_label: str
    empty_label: str
    # Sub-head each pair group's rows by month. Set by kind, not derived from
    # the range: a week that crosses a month boundary (Jul 28 to Aug 3) spans two
    # months but still reads as one run of days, so it stays flat. The
    # sub-heading earns its place only once a flat list is long enough to lose
    # its place in — quarterly and yearly.
    groups_by_month: bool = False


def planning_period(entry_kind: str, period_key: str) -> PlanningPeriod | None:
    """Resolve a periodic note's planning range — ``None`` means "no panel".

    Weekly → the ISO week (Monday–Sunday); monthly → the calendar month;
    quarterly → the quarter's three months; yearly → Jan 1 – Dec 31. Daily
    notes and unknown kinds get no period (the day lens is the daily surface),
    and an unparseable key degrades to no panel rather than a guessed range.
    """
    if entry_kind == "weekly":
        week_start = weekly_period_start(period_key)
        if week_start is None:
            return None
        week_end = week_start + timedelta(days=6)
        return PlanningPeriod(
            start=week_start,
            end=week_end,
            heading="This week",
            range_label=_week_range_label(week_start, week_end),
            empty_label="Nothing this week",
        )
    if entry_kind == "monthly":
        month_start = monthly_period_start(period_key)
        if month_start is None:
            return None
        last_day = monthrange(month_start.year, month_start.month)[1]
        return PlanningPeriod(
            start=month_start,
            end=month_start.replace(day=last_day),
            heading="This month",
            range_label=month_start.strftime("%B %Y"),
            empty_label="Nothing this month",
        )
    if entry_kind == "quarterly":
        quarter_start = quarterly_period_start(period_key)
        if quarter_start is None:
            return None
        end_month = quarter_start.month + 2
        last_day = monthrange(quarter_start.year, end_month)[1]
        quarter_end = date(quarter_start.year, end_month, last_day)
        quarter_number = (quarter_start.month - 1) // 3 + 1
        return PlanningPeriod(
            start=quarter_start,
            end=quarter_end,
            heading="This quarter",
            range_label=(
                f"Q{quarter_number} {quarter_start.year} · "
                f"{quarter_start.strftime('%b')} – {quarter_end.strftime('%b')}"
            ),
            empty_label="Nothing this quarter",
            groups_by_month=True,
        )
    if entry_kind == "yearly":
        year_start = yearly_period_start(period_key)
        if year_start is None:
            return None
        return PlanningPeriod(
            start=year_start,
            end=date(year_start.year, 12, 31),
            heading="This year",
            range_label=str(year_start.year),
            empty_label="Nothing this year",
            groups_by_month=True,
        )
    return None


# Pair labels mirror the calendar legend (``ui/calendar/components.py``
# ``_LEGEND_PAIRS``) so the two surfaces speak one vocabulary. Membership
# differs deliberately: no HABIT here (v1 exclusion). Anything outside these
# tuples — a habit item passed defensively — simply doesn't render.
_PANEL_PAIRS: tuple[tuple[str, tuple[CalendarItemType, ...]], ...] = (
    ("Tasks + Events", (CalendarItemType.TASK, CalendarItemType.EVENT)),
    ("Goals + Habits", (CalendarItemType.MILESTONE,)),
)


def PlanningPanel(items: "list[CalendarItem]", period: PlanningPeriod) -> Div:
    """Read-only panel of the period's existing entities, pair-grouped.

    ``items`` come from ``CalendarService.get_planning_items`` over
    ``period.start``–``period.end`` (tasks due OR scheduled in-period + events
    + goal Milestones), already chronological.
    """
    return Div(
        Div(
            P(period.heading, cls="text-15 font-bold text-foreground"),
            P(period.range_label, cls="text-xs text-muted-foreground"),
            cls="mb-3",
        ),
        *[
            _panel_group(label, [i for i in items if i.item_type in member_types], period)
            for label, member_types in _PANEL_PAIRS
        ],
        id="planning-panel",
    )


def _week_range_label(start: date, end: date) -> str:
    """``"Aug 3 – 9"``, or ``"Jul 28 – Aug 3"`` when the week crosses a month."""
    if start.month == end.month:
        return f"{start.strftime('%b')} {start.day} – {end.day}"
    return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}"


def _panel_group(label: str, items: "list[CalendarItem]", period: PlanningPeriod) -> Div:
    """One pair group: legend-styled label + rows (or a muted empty state).

    Over a long period (``period.groups_by_month``) the rows are sub-headed by
    month so a quarter's or a year's flat run stays navigable; weekly and
    monthly panels render the same flat list they always have.
    """
    rows: list[FT] = (
        (_month_subheaded_rows(items) if period.groups_by_month else [_panel_row(i) for i in items])
        if items
        else [P(period.empty_label, cls="text-xs text-muted-foreground italic px-2 py-1")]
    )
    return Div(
        Span(
            label,
            cls=("text-10 uppercase tracking-[0.08em] font-semibold text-muted-foreground/60"),
        ),
        Div(*rows, cls="mt-1 flex flex-col gap-0.5"),
        cls="mb-4",
    )


def _month_subheaded_rows(items: "list[CalendarItem]") -> "list[FT]":
    """Rows with a month sub-head opening each month's run.

    ``items`` arrive chronological, so a month change is simply the next row's
    month differing from the previous one — no re-sorting, no bucketing.
    """
    rows: list[FT] = []
    current: tuple[int, int] | None = None
    for item in items:
        day = item.start_time.date()
        month = (day.year, day.month)
        if month != current:
            current = month
            rows.append(
                Span(
                    day.strftime("%B %Y"),
                    cls=(
                        "block mt-2 first:mt-0 px-2 text-10 font-semibold uppercase"
                        " tracking-[0.06em] text-muted-foreground/80"
                    ),
                )
            )
        rows.append(_panel_row(item))
    return rows


def _panel_row(item: "CalendarItem") -> A:
    """One entity row — a link to its day's lens. Reading here, acting there.

    Kind travels as the color dot (the legend's color-communicates-kind rule);
    due-only tasks add the ⏰ + red STATE cue on the day label (E1).
    """
    day = item.start_time.date()
    day_label = day.strftime("%a %-d")
    return A(
        Span(
            cls="w-2 h-2 rounded-full shrink-0",
            style=f"background-color: {item.color};",
        ),
        Span(item.title, cls="flex-1 min-w-0 truncate text-13 text-foreground"),
        Span(
            f"⏰ {day_label}" if item.is_due else day_label,
            cls=(
                "text-11 whitespace-nowrap "
                + ("text-red-600 font-medium" if item.is_due else "text-muted-foreground")
            ),
        ),
        href=f"/today/{day.isoformat()}",
        title=f"Open the {day.strftime('%A')} day lens",
        cls="flex items-center gap-2 px-2 py-1.5 rounded-[8px] hover:bg-slate-100 no-underline",
    )


__all__ = [
    "PlanningPanel",
    "PlanningPeriod",
    "monthly_period_start",
    "planning_period",
    "quarterly_period_start",
    "weekly_period_start",
    "yearly_period_start",
]
