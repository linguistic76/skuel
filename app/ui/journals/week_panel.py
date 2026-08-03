"""Weekly-note read panel — the week the note plans against (periodic-notes arc S3).

Template-led planning (ruling E2): forward planning happens through checkbox/DSL
lines in the vault weekly note; the app SHOWS the week's existing entities for
planning-against and accountability (R4). This panel is strictly read-only — no
mutations, no quick-add. Every row doors to its day's lens (``/today/{date}``),
where acting happens (act-from arc C6/C7).

Vocabulary is the calendar's pair grouping (R1/R2, matching the legend's
``_LEGEND_PAIRS``): Tasks + Events, then Goals + Habits. The Goals + Habits
group holds Milestones only — habits are deliberately absent from v1 (daily
recurrence is calendar texture, not weekly planning matter). Choices/Principles
never appear: the compass lives in the writing, not in chips (R2). A due-only
task keeps its ⏰ + red state cue — a STATE of a Task, never a kind (E1).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from fasthtml.common import A, Div, P, Span

from core.models.event.calendar_models import CalendarItemType

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.event.calendar_models import CalendarItem


def weekly_period_start(period_key: str) -> date | None:
    """Monday of the ISO week a weekly period key names (``2026-W32``).

    The key format is the ``ensure_periodic_note`` persistence contract
    (``{year}-W{week:02d}``); vault-derived weekly notes carry the same form as
    their UID's last colon segment (``week_of`` frontmatter — the join
    contract). Returns ``None`` when the key doesn't parse — callers degrade to
    "no panel" rather than guessing a week.
    """
    year_str, sep, week_str = period_key.partition("-W")
    if not sep:
        return None
    try:
        return date.fromisocalendar(int(year_str), int(week_str), 1)
    except ValueError:
        return None


# Pair labels mirror the calendar legend (``ui/calendar/components.py``
# ``_LEGEND_PAIRS``) so the two surfaces speak one vocabulary. Membership
# differs deliberately: no HABIT here (v1 exclusion). Anything outside these
# tuples — a habit item passed defensively — simply doesn't render.
_PANEL_PAIRS: tuple[tuple[str, tuple[CalendarItemType, ...]], ...] = (
    ("Tasks + Events", (CalendarItemType.TASK, CalendarItemType.EVENT)),
    ("Goals + Habits", (CalendarItemType.MILESTONE,)),
)


def WeeklyPlanningPanel(items: "list[CalendarItem]", week_start: date) -> Div:
    """Read-only panel of the ISO week's existing entities, pair-grouped.

    ``items`` come from ``CalendarService.get_planning_items`` (tasks due OR
    scheduled in-week + events + goal Milestones), already chronological.
    """
    week_end = week_start + timedelta(days=6)
    return Div(
        Div(
            P("This week", cls="text-[15px] font-bold text-foreground"),
            P(_range_label(week_start, week_end), cls="text-[12px] text-muted-foreground"),
            cls="mb-3",
        ),
        *[
            _panel_group(label, [i for i in items if i.item_type in member_types])
            for label, member_types in _PANEL_PAIRS
        ],
        id="week-panel",
    )


def _range_label(start: date, end: date) -> str:
    """``"Aug 3 – 9"``, or ``"Jul 28 – Aug 3"`` when the week crosses a month."""
    if start.month == end.month:
        return f"{start.strftime('%b')} {start.day} – {end.day}"
    return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}"


def _panel_group(label: str, items: "list[CalendarItem]") -> Div:
    """One pair group: legend-styled label + rows (or a muted empty state)."""
    rows: list[FT] = (
        [_panel_row(item) for item in items]
        if items
        else [P("Nothing this week", cls="text-[12px] text-muted-foreground italic px-2 py-1")]
    )
    return Div(
        Span(
            label,
            cls=("text-[10px] uppercase tracking-[0.08em] font-semibold text-muted-foreground/60"),
        ),
        Div(*rows, cls="mt-1 flex flex-col gap-0.5"),
        cls="mb-4",
    )


def _panel_row(item: "CalendarItem") -> A:
    """One entity row — a link to its day's lens. Reading here, acting there.

    Kind travels as the color dot (the legend's color-communicates-kind rule);
    due-only tasks add the ⏰ + red STATE cue on the day label (E1).
    """
    day = item.start_time.date()
    day_label = day.strftime("%a %-d")
    return A(
        Span(
            cls="w-2 h-2 rounded-full flex-shrink-0",
            style=f"background-color: {item.color};",
        ),
        Span(item.title, cls="flex-1 min-w-0 truncate text-[13px] text-foreground"),
        Span(
            f"⏰ {day_label}" if item.is_due else day_label,
            cls=(
                "text-[11px] whitespace-nowrap "
                + ("text-red-600 font-medium" if item.is_due else "text-muted-foreground")
            ),
        ),
        href=f"/today/{day.isoformat()}",
        title=f"Open the {day.strftime('%A')} day lens",
        cls="flex items-center gap-2 px-2 py-1.5 rounded-[8px] hover:bg-slate-100 no-underline",
    )


__all__ = ["WeeklyPlanningPanel", "weekly_period_start"]
