"""
Calendar UI Components
======================

UI components for the redesigned calendar views (month, week).

Both views share one visual language:
- large period title + a per-type legend (``create_calendar_header``)
- a Prev/Now/Next + periodic-note toolbar (``create_calendar_toolbar``) — lens
  switching lives in the activity sidebar (Today / Weekly / Monthly links), not
  in the page chrome
- per-type colored event chips (``_event_chip``) — a leading dot + accent bar in
  the item's type color, fill at ~10% alpha

Month is a bordered grid with an ISO-week rail; Week is 7 day-column agenda cards.
Colors come from ``CalendarItemType.get_color()`` so the legend stays truthful.
(The single-day agenda view was dropped — for the current day the Today surface
(/today) is the one path; the calendar keeps the Week/Month temporal lenses.)

See: docs/design-handoff/calendar-month/README.md — historical design record
(visual intent only; its route/surface inventory predates the two-view contract)
"""

__version__ = "2.0"

from dataclasses import replace
from datetime import date, datetime, timedelta
from itertools import islice
from typing import TYPE_CHECKING, Any

from fasthtml.common import H1, H2, A, Div, Form, P, Span
from fasthtml.common import Button as HtmlButton

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    habit_block_on,
)
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle, Icon, Input
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.modal import AlpineModal
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from fasthtml.common import FT

# Legend vocabulary — four kinds grouped by Activity-domain pair (periodic-notes
# arc R1/R2/E1): Tasks+Events dominate the grid; Goals+Habits are milestones +
# recurrence; Choices+Principles get no swatch — the compass lives in the
# periodic note, not on the grid. Within each pair, R1's linear domain order.
_LEGEND_PAIRS: tuple[tuple[str, tuple[CalendarItemType, ...]], ...] = (
    ("Tasks + Events", (CalendarItemType.TASK, CalendarItemType.EVENT)),
    ("Goals + Habits", (CalendarItemType.MILESTONE, CalendarItemType.HABIT)),
)

_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# 8-column track: a narrow ISO-week rail + 7 equal day columns.
_MONTH_GRID_COLS = "grid grid-cols-[46px_repeat(7,minmax(0,1fr))]"
# Force a full browser navigation (journal routes answer with a 302 redirect that
# HTMX boost would otherwise swap into the current target).
_NO_BOOST = {"hx-boost": "false"}


# ============================================================================
# SHARED CHROME
# ============================================================================


def _legend_swatch(item_type: CalendarItemType) -> HtmlButton:
    """One kind-swatch, styled as a visible control (bordered pill).

    The border + hover ring + tooltip make the long-standing filter/spotlight
    interactivity discoverable — the legend used to LOOK static (periodic-notes
    arc S1: affordance invisibility was the calendar's recurring disease).
    """
    label = item_type.get_label()
    return HtmlButton(
        Span(
            cls="w-[9px] h-[9px] rounded-[3px]",
            style=f"background-color: {item_type.get_color()}",
        ),
        Span(label, cls="text-11 font-medium text-muted-foreground"),
        type="button",
        title=f"Click to show/hide {label} items · hover to spotlight",
        aria_label=f"Show or hide {label} items",
        cls=(
            "flex items-center gap-1.5 cursor-pointer rounded-full px-2 py-0.5"
            " border border-border bg-card transition-all hover:bg-accent"
            " hover:border-muted-foreground/40"
            " focus:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
        ),
        **{
            "@click": f"toggleType('{item_type.value}')",
            "@mouseenter": f"spotlight = '{item_type.value}'",
            "@mouseleave": "spotlight = null",
            ":class": f"isHidden('{item_type.value}') && 'opacity-40'",
            ":aria-pressed": f"String(!isHidden('{item_type.value}'))",
        },
    )


def create_calendar_legend() -> Div:
    """Kind swatches doubling as filter controls, grouped by Activity pair.

    Two groups (``_LEGEND_PAIRS``): Tasks+Events and Goals+Habits, each a tiny
    pair label + bordered swatch buttons. Click hides/shows that kind on the
    grid, hover spotlights it (dims the others). State + CSS classes live on
    the ``calendarLegend`` Alpine component bound to the calendar shell
    (``_wrap_calendar_page``), so filters survive HTMX content swaps; the
    hiding itself is pure CSS (``calendar.css``) keyed off ``data-item-type``.
    """
    groups = [
        Div(
            Span(
                pair_label,
                cls=(
                    "text-10 uppercase tracking-[0.08em] font-semibold"
                    " text-muted-foreground/60 whitespace-nowrap"
                ),
            ),
            *[_legend_swatch(item_type) for item_type in pair_types],
            cls="flex items-center gap-1.5",
        )
        for pair_label, pair_types in _LEGEND_PAIRS
    ]
    return Div(*groups, cls="flex items-center gap-4 flex-wrap pb-1")


def create_calendar_header(title: str) -> Div:
    """Period title (left) and the type legend (right).

    The title steps down on phones — "Week of Jun 30 – Jul 6" at 40px is wider
    than a 375px viewport's content column.
    """
    return Div(
        H1(title, cls="text-[32px] sm:text-[40px] font-bold tracking-[-0.02em] leading-none"),
        create_calendar_legend(),
        cls="flex items-end justify-between gap-6 flex-wrap mb-5",
    )


def _nav_button(label: str, href: str, icon_name: str, *, trailing: bool = False) -> A:
    """A bordered nav pill with a leading (or trailing) Lucide chevron."""
    icon = Icon(icon_name, cls="w-[15px] h-[15px]")
    text = Span(label)
    content = (text, icon) if trailing else (icon, text)
    return A(
        *content,
        href=href,
        cls=(
            "inline-flex items-center gap-1.5 h-[34px] px-3 border border-border bg-card"
            " rounded-lg text-13 font-medium text-foreground hover:bg-muted"
        ),
    )


def _note_button(href: str, label: str) -> A:
    """A bordered periodic-note pill with a leading square-pen icon."""
    return A(
        Icon("square-pen", cls="w-[15px] h-[15px]"),
        Span(label),
        href=href,
        title=f"Open {label.lower()}",
        **_NO_BOOST,
        cls=(
            "inline-flex items-center gap-[7px] h-[34px] px-[13px] border border-border"
            " bg-card rounded-lg text-13 font-medium text-foreground hover:bg-muted"
            " whitespace-nowrap"
        ),
    )


def calendar_nav_cluster(
    prev_href: str,
    next_href: str,
    today_href: str,
    note_href: str,
    note_label: str,
    daily_note_href: str | None = None,
) -> Div:
    """Prev/Now/Next pills + periodic-note button(s), right-aligned (no margin).

    The recenter pill is labelled "Now" — the word "Today" belongs solely to the
    Today surface (sidebar link), keeping the two meanings distinct. ``note_label``
    names the view's own periodic note ("Weekly note" / "Monthly note" / "Daily
    note"). ``daily_note_href`` — when given — adds a second "Daily note" button
    (today's note) beside it, so the Week/Month toolbars complete the
    Daily/Weekly/Monthly note family (act-from arc C6). The Today day-lens header
    omits it: its single note button already IS the daily note.

    Shared by the calendar toolbar (Week/Month) and the Today day-lens header, so
    all three temporal lenses carry an identical navigation cluster (#665).
    """
    note_buttons = [_note_button(note_href, note_label)]
    if daily_note_href is not None:
        note_buttons.append(_note_button(daily_note_href, "Daily note"))
    return Div(
        _nav_button("Prev", prev_href, "chevron-left"),
        A(
            "Now",
            href=today_href,
            cls=(
                "inline-flex items-center h-[34px] px-4 bg-primary text-primary-foreground"
                " border border-primary rounded-lg text-13 font-semibold hover:opacity-90"
            ),
        ),
        _nav_button("Next", next_href, "chevron-right", trailing=True),
        Div(cls="w-px h-[22px] bg-border mx-1"),
        *note_buttons,
        # flex-wrap: on phones the full cluster is wider than the viewport —
        # without it the leading "Prev" pill clips off the left edge; wrapped,
        # the note button(s) drop to a second row instead.
        cls="flex items-center justify-end gap-2 flex-wrap",
    )


def create_calendar_toolbar(
    prev_href: str,
    next_href: str,
    today_href: str,
    note_href: str,
    note_label: str,
    daily_note_href: str | None = None,
) -> Div:
    """Right-aligned Prev/Now/Next + periodic-note toolbar row (Week/Month views).

    Thin margin wrapper around :func:`calendar_nav_cluster`; the Today surface
    embeds the bare cluster in its header column instead. ``daily_note_href``
    threads through to add the "Daily note" (today's note) button beside the
    view's own periodic-note button.
    """
    return Div(
        calendar_nav_cluster(
            prev_href, next_href, today_href, note_href, note_label, daily_note_href
        ),
        cls="flex items-center justify-end gap-4 flex-wrap mb-5",
    )


# ============================================================================
# EVENT CHIP (shared across views)
# ============================================================================


def _item_order(item: CalendarItem) -> tuple[datetime, str, str]:
    """Sort key: start time, then — for habits only — title then uid.

    Habits need a tiebreak because slots collide by design: MORNING and ANYTIME
    both resolve to 09:00 and three of the five live habits land there, while
    nothing upstream orders them — their fetch issues no ``ORDER BY``. On a bare
    start-time key the day's rhythm would reshuffle between renders, and month
    and week (separate requests) could disagree with each other.

    The uid is what makes the key TOTAL. Nothing enforces unique habit titles,
    and two same-named habits are exactly the pair a reader cannot tell apart by
    position — yet they carry different durations and open different ``?date=``
    modals, so leaving them to fetch order would swap live controls between
    renders.

    Every other kind keeps ``("", "")`` and therefore its insertion order under
    Python's stable sort — tasks, then events, then goals, each already ordered
    by its query. Widening the tiebreak to all kinds would silently re-sort
    them: `_task_to_calendar_item` stamps EVERY scheduled task 09:00 and every
    due-only task midnight, so they all tie, and they would flip from
    newest-first to alphabetical with milestones wedged in between.
    """
    if item.item_type != CalendarItemType.HABIT:
        return (item.start_time, "", "")
    return (item.start_time, item.title, item.source_uid)


def _items_by_date(calendar_data: CalendarData) -> dict[date, list[CalendarItem]]:
    """Group calendar items onto their days, expanding recurring habits.

    Non-habit items land on ``start_time.date()``. A habit is a single item
    carrying its block on a placeholder date, so it is expanded into one chip
    per generated occurrence — otherwise recurring habits would only show on
    that one date, and vanish entirely in months that don't include it.

    Each expanded chip is RE-DATED onto its occurrence day through
    ``habit_block_on``, so it keeps the habit's own time of day and duration
    (habit-rhythm arc S2). Stamping the expansion to midnight instead — as this
    did while habit times were fabricated — would have clustered every habit at
    day start no matter how truthful the base item became, because the chips the
    grid sorts are these, not the base.

    Each expanded habit chip is stamped with its occurrence day + status in
    ``occurrence_data`` — that day stamp is what lets the chip open a day-aware
    item-details modal (``?date=``) and render completed days distinctly.
    """
    habit_items = {
        item.source_uid: item
        for item in calendar_data.items
        if item.item_type == CalendarItemType.HABIT
    }
    by_date: dict[date, list[CalendarItem]] = {}
    for item in calendar_data.items:
        if item.item_type == CalendarItemType.HABIT:
            continue  # expanded from occurrences below (the base carries no real date)
        by_date.setdefault(item.start_time.date(), []).append(item)

    for occurrences in calendar_data.occurrences.values():
        for occ in occurrences:
            base = habit_items.get(occ.calendar_item_uid)
            if base is None:
                continue
            start_time, end_time = habit_block_on(base, occ.date)
            by_date.setdefault(occ.date, []).append(
                replace(
                    base,
                    all_day=False,
                    start_time=start_time,
                    end_time=end_time,
                    occurrence_data={
                        "date": occ.date.isoformat(),
                        "status": occ.status.value,
                    },
                )
            )
    return by_date


def _fmt_time(dt: datetime) -> str:
    """12-hour clock without a leading zero (e.g. ``9:30 AM``)."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _duration_label(minutes: int) -> str:
    """Compact block length — ``20m``, ``1h``, ``1h 30m``."""
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _habit_duration_label(item: CalendarItem) -> str | None:
    """A habit chip's block length (``20m``); ``None`` for every other kind.

    Duration is the load-bearing half of the habit vocabulary — "it is more
    about duration than time" (habit-rhythm arc M3) — so every habit surface
    states it: the week chip's own line, the month chip's tooltip, the modal.
    """
    if item.item_type != CalendarItemType.HABIT:
        return None
    minutes = int((item.end_time - item.start_time).total_seconds() // 60)
    return _duration_label(minutes) if minutes > 0 else None


def _habit_block_label(item: CalendarItem) -> str | None:
    """A habit chip's block in the habit's own words — ``Morning · 20m``.

    The slot WORD, never a clock time (M3 — slots only). ``start_time`` carries
    the slot's representative hour because the day's ordering needs a point in
    time, but that hour must not be shown: MORNING and ANYTIME both resolve to
    09:00, so "9:00 AM" would tell someone who chose *anytime* that they
    committed to nine o'clock — the fabricated-habit-time defect this arc
    exists to end.

    A habit that states no slot gets the duration alone. It is placed at
    ANYTIME's hour so the day still orders, but naming it "Anytime" would
    invent a preference the user never expressed — the same fabrication in
    smaller print, and it would contradict every other surface, which reads a
    null ``preferred_time`` as unstated. ``None`` for every non-habit kind.
    """
    duration = _habit_duration_label(item)
    if duration is None:
        return None
    if item.time_of_day is None:
        return duration
    return f"{item.time_of_day.get_label()} · {duration}"


def _time_range_label(item: CalendarItem) -> str:
    """``All day`` for markers, a habit's ``slot · length``, else ``start – end``.

    A habit holds a slot and a duration, never a start and an end (M3), so its
    label states exactly those two facts. A start–end range would read as a
    clock appointment the habit never made, and would print a next-day hour for
    a block that runs past midnight.
    """
    if item.all_day:
        return "All day"
    block = _habit_block_label(item)
    if block is not None:
        return block
    start = _fmt_time(item.start_time)
    end = _fmt_time(item.end_time)
    return f"{start} – {end}" if end != start else start


def _occurrence_date_iso(item: CalendarItem) -> str | None:
    """The occurrence-day stamp (ISO date) a habit chip carries, if any."""
    if item.occurrence_data is None:
        return None
    stamped = item.occurrence_data.get("date")
    return str(stamped) if stamped else None


def _is_completed_occurrence(item: CalendarItem) -> bool:
    """Whether a habit chip's stamped occurrence day has a recorded completion."""
    if item.occurrence_data is None:
        return False
    return bool(item.occurrence_data.get("status") == CompletionStatus.DONE.value)


def _opens_detail_modal(item: CalendarItem) -> bool:
    """Whether a chip should open the item-details modal on click.

    Habit chips open the modal only when stamped with their occurrence day
    (``occurrence_data``, set during ``_items_by_date`` expansion) — the modal
    shows THAT day, and must never reconstruct it from "today" (the exact bug
    that once made habit chips display-only). The raw now()-stamped habit stub
    has no stamp and stays display-only; every other type always opens.
    """
    if item.item_type == CalendarItemType.HABIT:
        return _occurrence_date_iso(item) is not None
    return True


def _event_chip(item: CalendarItem, *, large: bool = False) -> Div:
    """An event chip colored by item type.

    Fill = type color at ~10% alpha (8-digit hex ``1a``); a 3px left accent bar +
    leading dot in the full color. ``large`` (week/day) adds a mono time label.
    Chips open the item-details modal via the existing HTMX endpoint; day-stamped
    habit chips pass their occurrence day (``?date=``, query param per FastHTML
    convention) so the modal shows THAT day, and carry ``data-completed`` when
    the day has a recorded completion (calendar.css renders them ✓/dimmed).
    """
    color = item.color
    # Due-state cue (periodic-notes arc E1): a due-but-unscheduled task keeps
    # the Task kind color but swaps its dot for ⏰ (plus the red left accent
    # from calendar.css via data-due) — urgency is a state, not a kind.
    if item.is_due:
        dot = Span("⏰", cls="flex-none text-10 leading-none", aria_label="Due")
    else:
        dot = Span(cls="flex-none w-2 h-2 rounded-full", style=f"background-color: {color}")
    chip_style = f"background-color: {color}1a; border-left: 3px solid {color}"
    interactive: dict[str, str] = {}
    if _opens_detail_modal(item):
        detail_url = f"/cal/item-details/{item.uid}"
        occurrence_day = _occurrence_date_iso(item)
        if occurrence_day is not None:
            detail_url += f"?date={occurrence_day}"
        interactive = {
            "data_item_id": item.uid,
            "hx_get": detail_url,
            "hx_target": "body",
            "hx_swap": "beforeend",
        }
    cursor = " cursor-pointer" if interactive else ""
    state_attrs: dict[str, str] = {"data_item_type": item.item_type.value}
    if item.is_due:
        state_attrs["data_due"] = "true"
    if _is_completed_occurrence(item):
        state_attrs["data_completed"] = "true"

    if large:
        return Div(
            Div(
                dot,
                Span(
                    item.title,
                    cls=(
                        "calendar-item-title flex-1 min-w-0 truncate text-xs"
                        " font-semibold text-foreground"
                    ),
                ),
                cls="flex items-center gap-1.5",
            ),
            Div(
                _time_range_label(item),
                cls="text-11 text-muted-foreground font-mono mt-[3px]",
            ),
            cls=f"calendar-item px-2.5 py-2 rounded-lg{cursor}",
            style=chip_style,
            title=item.title,
            **state_attrs,
            **interactive,
        )

    # The month chip's block rides in the TOOLTIP, not beside the title. A
    # month day column is pinned at ~93px (the grid is min-w-[700px] over 7
    # columns and pans rather than shrinking), and an inline duration measured
    # at 375px cut the title box from 47px to 5px — the habit's NAME vanished,
    # and with it the C3 completion ✓, which calendar.css renders inside
    # .calendar-item-title::after. The week chip has its own line for the block;
    # the month grid answers "which habits, and did I do them".
    block = _habit_block_label(item)
    return Div(
        dot,
        Span(item.title, cls="calendar-item-title flex-1 min-w-0 truncate"),
        cls=(
            "calendar-item flex items-center gap-1.5 px-[7px] py-0.5 rounded-md"
            f" text-11 font-medium leading-normal text-foreground{cursor}"
        ),
        style=chip_style,
        title=f"{item.title} · {block}" if block is not None else item.title,
        **state_attrs,
        **interactive,
    )


# ============================================================================
# MONTH VIEW
# ============================================================================


def create_month_grid(calendar_data: CalendarData, year: int, month: int) -> Div:
    """Flat month grid: ISO-week rail + 7 day columns, one row per week.

    ``calendar_data`` spans the full visible grid (Monday on/before the 1st
    through the Sunday of the last rendered week — ``month_grid_bounds``), so
    lead-in/tail cells carry real data. ``year``/``month`` name the focus
    month explicitly: with a grid-wide fetch range it can no longer be
    inferred from ``start_date``.

    Fills the viewport below the page chrome (uniform rows on sparse months);
    the Monday-anchored ISO-week rail is load-bearing — each week number links
    to that week's Obsidian weekly note, so Sunday-start is off the table.
    """
    items_by_date = _items_by_date(calendar_data)

    # Monday snap is a no-op when the route passes month_grid_bounds; it keeps
    # rows week-aligned if a caller ever hands in an unaligned range.
    grid_start = calendar_data.start_date - timedelta(days=calendar_data.start_date.weekday())

    weeks = []
    current_date = grid_start
    while current_date <= calendar_data.end_date:
        iso_year, iso_week, _ = current_date.isocalendar()
        week_cells = []
        for weekday_index in range(7):
            day_items = sorted(items_by_date.get(current_date, []), key=_item_order)
            week_cells.append(
                create_day_cell(
                    current_date,
                    day_items,
                    is_current_month=(current_date.year, current_date.month) == (year, month),
                    is_weekend=weekday_index >= 5,
                )
            )
            current_date += timedelta(days=1)

        # Week-number rail → the Weekly Note (Obsidian Calendar-style).
        rail = A(
            str(iso_week),
            href=f"/journals/weekly/{iso_year}/{iso_week}",
            title=f"Weekly note — W{iso_week}, {iso_year}",
            **_NO_BOOST,
            cls=(
                "flex items-center justify-center font-mono text-11 text-muted-foreground"
                " bg-muted/25 border-r border-b border-border hover:text-primary hover:bg-muted/60"
            ),
        )
        # flex-1: week rows share the container's spare height equally (uniform
        # rows on sparse months); a busy row still grows to its content, so no
        # chip is ever clipped (the #623 all-chips-visible ruling).
        weeks.append(Div(rail, *week_cells, cls=f"{_MONTH_GRID_COLS} flex-1"))

    header = Div(
        Div(
            "Wk",
            cls=(
                "flex items-center justify-center py-[11px] text-10 font-bold uppercase"
                " tracking-[0.06em] text-muted-foreground border-b border-r border-border"
            ),
        ),
        *[
            Div(
                label,
                cls=(
                    "text-center py-[11px] text-xs font-semibold border-b border-border "
                    + ("text-muted-foreground" if i >= 5 else "text-foreground")
                ),
            )
            for i, label in enumerate(_WEEKDAY_LABELS)
        ],
        cls=f"{_MONTH_GRID_COLS} bg-muted/50",
    )

    # Flat grid (no rounded card/shadow) that fills the viewport below the
    # chrome: min-height (not height) so sparse months stretch rows evenly
    # while busy months simply scroll the page. min-w + overflow wrapper: a
    # 7-day grid can't compress below ~93px/column and stay readable, so on
    # phones the grid keeps that width and pans horizontally inside its own
    # scroll container instead of crushing chips to slivers.
    return Div(
        Div(
            header,
            *weeks,
            cls=(
                "border border-border bg-card flex flex-col"
                " min-h-[calc(100dvh-250px)] min-w-[700px]"
            ),
        ),
        cls="overflow-x-auto",
    )


def create_day_cell(
    cell_date: date,
    items: list[CalendarItem],
    *,
    is_current_month: bool,
    is_weekend: bool,
) -> Div:
    """A single month-grid day cell: date number/pill + one chip per item.

    ALL of the day's items render (no truncation): the legend type filters hide
    chips client-side, so a chip that isn't in the DOM could never reappear when
    the types occluding it are toggled off. Busy days stretch their grid row.
    """
    is_today = cell_date == date.today()
    daily_href = f"/journals/daily/{cell_date.isoformat()}"
    day_lens_href = f"/today/{cell_date.isoformat()}"

    if is_today:
        date_el = A(
            str(cell_date.day),
            href=daily_href,
            title="Daily note",
            **_NO_BOOST,
            cls=(
                "inline-flex items-center justify-center min-w-[24px] h-6 px-1.5 rounded-full"
                " bg-primary text-primary-foreground text-xs font-bold"
            ),
        )
    else:
        tone = "text-foreground" if is_current_month else "text-muted-foreground/60"
        date_el = A(
            str(cell_date.day),
            href=daily_href,
            title="Daily note",
            **_NO_BOOST,
            cls=f"text-13 font-semibold {tone} hover:text-primary",
        )

    chips = [_event_chip(item) for item in items]

    cell_cls = "border-r border-b border-border min-h-[120px] px-[7px] pt-1.5 pb-2.5 relative overflow-hidden "
    cell_style = None
    if is_today:
        cell_cls += "bg-primary/[0.07]"
        cell_style = "box-shadow: inset 0 0 0 2px hsl(var(--primary))"
    elif not is_current_month:
        cell_cls += "bg-muted/50"
    elif is_weekend:
        cell_cls += "bg-muted/30"
    else:
        cell_cls += "bg-background"

    # Act from the day: any click on the cell that isn't a chip (item modal) or a
    # link opens that day's lens (/today/{date}, the acting surface — act-from arc
    # C6), including past days (reviewing a past day is legitimate). closest() —
    # not target===this — because on busy days chips and their column wrapper cover
    # most of the cell, which shrank the click surface to the date number alone.
    # The date-number link (an <a>, matched by closest('a')) stays independently
    # clickable and keeps opening the daily note. Plain JS so it works in
    # HTMX-swapped content without an Alpine re-init.
    return Div(
        # Day number top-right (standard desktop-calendar convention).
        Div(date_el, cls="flex items-center justify-end min-h-[24px] mb-[5px]"),
        Div(*chips, cls="flex flex-col gap-[3px]"),
        cls=cell_cls + " cursor-pointer",
        style=cell_style,
        onclick=f"if(!event.target.closest('.calendar-item,a'))window.location.href='{day_lens_href}'",
    )


# ============================================================================
# WEEK VIEW (agenda — 7 day-column cards)
# ============================================================================


def create_week_grid(calendar_data: CalendarData) -> Div:
    """Seven day-column agenda cards (Mon–Sun), each listing its events as chips."""
    items_by_date = _items_by_date(calendar_data)

    cards = []
    for offset in range(7):
        day = calendar_data.start_date + timedelta(days=offset)
        is_today = day == date.today()
        day_items = sorted(items_by_date.get(day, []), key=_item_order)

        head_tone = (
            "bg-primary text-primary-foreground"
            if is_today
            else "bg-muted/50 text-foreground hover:bg-muted"
        )
        head = A(
            Span(
                _WEEKDAY_LABELS[offset],
                cls="text-10 font-bold uppercase tracking-[0.06em] opacity-75",
            ),
            Span(str(day.day), cls="text-lg font-bold leading-none"),
            href=f"/journals/daily/{day.isoformat()}",
            title="Daily note",
            **_NO_BOOST,
            cls=f"flex flex-col gap-1 px-3 py-2.5 border-b border-border {head_tone}",
        )

        if day_items:
            body_children: list[FT] = [_event_chip(item, large=True) for item in day_items]
        else:
            body_children = [Div("No events", cls="text-xs text-muted-foreground/60 p-1.5")]
        body = Div(*body_children, cls="p-2 flex flex-col gap-1.5 flex-1")

        # Same non-chip/non-link click-through as the month cells: the card's
        # empty space opens that day's lens (/today/{date}, the acting surface —
        # act-from arc C6), while the head link (an <a> to the daily note) and the
        # chips keep their own behavior.
        cards.append(
            Div(
                head,
                body,
                # Tall min-height only in column layout (md+): stacked phone
                # cards hug their content — 7 x 360px of mostly-empty cards
                # made the mobile week nearly 2600px of scrolling.
                cls=(
                    "border border-border rounded-[11px] overflow-hidden bg-card"
                    " min-h-[120px] md:min-h-[360px] flex flex-col cursor-pointer"
                ),
                onclick=(
                    "if(!event.target.closest('.calendar-item,a'))"
                    f"window.location.href='/today/{day.isoformat()}'"
                ),
            )
        )

    # Columns from md up — at sm (640px) seven columns are ~91px each, too
    # narrow for titled chips, so small screens keep the stacked-card layout.
    return Div(*cards, cls="grid grid-cols-1 md:grid-cols-7 gap-2.5")


# ============================================================================
# DAY VIEW (agenda list)
# ============================================================================


# ============================================================================
# SHARED HELPERS
# ============================================================================


def error_response(error_message: Any) -> Div:
    """Create an error response UI for a failed calendar fetch."""
    return Div(
        Card(
            CardHeader(CardTitle("Error", cls="text-error")),
            CardBody(
                P(str(error_message), cls="text-muted-foreground"),
                Button(
                    "Go Back",
                    cls=(ButtonT.primary, "mt-4"),
                    onclick="window.history.back()",
                ),
            ),
        ),
        cls="container max-w-md mx-auto mt-8",
    )


def _format_datetime(dt: datetime) -> str:
    """Format datetime for display."""
    return dt.strftime("%b %d, %I:%M %p")


# ============================================================================
# ITEM DETAILS MODAL
# ============================================================================


def habit_day_state_line(done: bool, *, oob: bool = False) -> P:
    """That-day completion state line in the habit modal (``#habit-day-state``).

    One render truth shared by the modal and the habit-complete POST response:
    on success the route returns this line with ``oob=True`` (an HTMX
    out-of-band swap by id), so the open modal flips to "Completed on this
    day ✓" instead of contradicting the recorded write.
    """
    tone = "text-success" if done else "text-muted-foreground"
    extra: dict[str, str] = {"hx_swap_oob": "true"} if oob else {}
    return P(
        Icon(
            "check-circle" if done else "circle",
            cls="w-4 h-4 inline-block mr-1.5 align-[-3px]",
        ),
        "Completed on this day ✓" if done else "Not completed on this day",
        cls=f"text-sm font-medium {tone} mt-1",
        id="habit-day-state",
        **extra,
    )


def _is_terminal_task(item: CalendarItem) -> bool:
    """Whether a task calendar item is in a terminal status (cancelled/failed/
    archived/completed).

    Reads the ``status`` value ``_task_to_calendar_item`` stamps into
    ``metadata``. TasksCoreService._validate_update refuses every change to a
    terminal task, so terminal chips must not offer actions that are
    guaranteed to fail. A missing/unknown status counts as actionable — the
    service policy is the backstop.
    """
    raw_status = str(item.metadata.get("status", ""))
    try:
        return EntityStatus(raw_status).is_terminal()
    except ValueError:
        return False


def item_schedule_line(item: CalendarItem, *, oob: bool = False) -> P:
    """The modal's schedule line for a task/event item (``#item-schedule-text``).

    One render truth shared by the modal and the reschedule POST response: on
    success the route returns this line with ``oob=True`` (an HTMX out-of-band
    swap by id), so the open modal's schedule flips to the new date instead of
    contradicting the recorded move. Day-stamped habit modals render their own
    occurrence-day line and never OOB-swap this one.

    A habit reaching this line is the UNSTAMPED stub (a hand-typed
    ``/cal/item-details/habit-X`` with no ``?date=``, or an off-schedule one).
    It states its block and no date: a habit recurs, so its ``start_time``'s
    date is a placeholder, and a clock range would name a next-day hour for a
    block that runs past midnight.
    """
    block = _habit_block_label(item)
    if block is not None:
        text = block
    elif item.all_day:
        text = "All Day"
    else:
        text = f"{_format_datetime(item.start_time)} - {_format_datetime(item.end_time)}"
    extra: dict[str, str] = {"hx_swap_oob": "true"} if oob else {}
    return P(text, cls="text-sm text-foreground", id="item-schedule-text", **extra)


def reschedule_form(
    item_id: str,
    *,
    with_time: bool,
    date_value: str,
    time_value: str = "",
    error: str | None = None,
) -> Form:
    """Inline reschedule control in the item-details modal (``#reschedule-form``).

    Posts form-encoded ``new_date`` (+ ``new_time`` for events) to
    ``POST /cal/item/{item_id}/reschedule`` and swaps itself: success replaces
    the form with a "Rescheduled ✓" confirmation plus an OOB
    ``item_schedule_line`` update; a retryable failure re-renders the form
    with an error line and the posted values intact. Only task/event modals
    get this form — habits recur, they don't reschedule.
    """
    fields: list[FT] = [
        Input(
            type="date",
            name="new_date",
            value=date_value,
            required=True,
            full_width=False,
            aria_label="New date",
        )
    ]
    if with_time:
        fields.append(
            Input(
                type="time",
                name="new_time",
                value=time_value,
                required=True,
                full_width=False,
                aria_label="New start time",
            )
        )
    fields.append(Button("Reschedule", type="submit", cls=ButtonT.secondary))
    error_line = P(error, cls="text-sm font-medium text-error mt-2") if error else None
    return Form(
        P(
            "Move to",
            cls="text-10 font-bold uppercase tracking-[0.08em] text-muted-foreground mb-1.5",
        ),
        Div(*fields, cls="flex items-center gap-2"),
        error_line,
        hx_post=f"/cal/item/{item_id}/reschedule",
        hx_swap="outerHTML",
        id="reschedule-form",
        cls="mt-3 pt-3 border-t border-border",
    )


def create_item_details_modal(item: Any) -> Div:
    """Render calendar item details as an HTMX modal fragment.

    Header = a type-colored dot + type pill + Lucide close; the body keeps the full
    schedule / description / event / habit / tags detail. Returns server-rendered
    HTML (not JSON) for a direct ``beforeend`` swap onto ``body``.

    A habit item stamped with an occurrence day (``occurrence_data``, via
    ``get_item(..., on_date=...)``) renders day-aware: the schedule names THAT
    day, the habit panel shows that day's completion state, and "Mark Complete"
    posts that day (form field ``on_date``) — already-done days show a disabled
    "Completed ✓", future days offer no completion. An unstamped habit item
    stays display-only: the day is never reconstructed from "today".

    Task and event modals carry a ``reschedule_form`` in the schedule panel
    (date input; events add a start-time input — duration is preserved
    in-service). Habit modals never do: habits recur, they don't reschedule.
    Terminal tasks and past events (immutable historical records) get no
    form either — their domain services refuse date changes, so the form
    would be guaranteed to fail.

    A milestone (goal) modal carries a "View Goal" link to the goal's detail
    page and no reschedule form — goal target dates move on the goals
    surface, not the calendar.
    """
    color = item.color

    # Habit day-awareness — the occurrence-day stamp set by the service.
    occurrence_day: date | None = None
    occurrence_done = False
    if item.item_type == CalendarItemType.HABIT and item.occurrence_data:
        raw_day = item.occurrence_data.get("date")
        if raw_day:
            try:
                occurrence_day = date.fromisoformat(str(raw_day))
            except ValueError:
                occurrence_day = None
        occurrence_done = item.occurrence_data.get("status") == CompletionStatus.DONE.value
    type_pill = Span(
        item.item_type.get_label(),
        cls=(
            "inline-flex items-center px-[9px] py-0.5 rounded-full text-10"
            " font-semibold uppercase tracking-[0.04em]"
        ),
        style=f"background-color: {color}1f; color: {color}",
    )
    type_dot = Span(cls="flex-none w-2.5 h-2.5 rounded-full", style=f"background-color: {color}")

    # Close: hide via Alpine, then remove the wrapper after the transition.
    close_expr = (
        "open = false; $nextTick(() => document.getElementById('item-details-modal')?.remove())"
    )

    # Schedule — a day-stamped habit names its occurrence day; otherwise the
    # item's own times (via item_schedule_line, the reschedule OOB target).
    if occurrence_day is not None:
        # The day names itself, then the block the habit actually states —
        # the same "Morning · 20m" the chip shows, off the same stamp, so
        # opening a chip never contradicts it.
        day_text = (
            f"{occurrence_day:%A}, {occurrence_day:%B} {occurrence_day.day}, {occurrence_day.year}"
        )
        schedule_display = P(
            f"{day_text} · {_time_range_label(item)}",
            cls="text-sm text-foreground",
        )
    else:
        schedule_display = item_schedule_line(item)

    # Reschedule — tasks move by date (overdue tasks included: moving them
    # forward is the point), events by date + start time (duration preserved
    # in-service). Habits recur; they never get this form. Two states get no
    # form because their domain services refuse every date change, so
    # offering it would guarantee failure (the service policies stay the
    # backstop for hand-crafted posts): terminal tasks
    # (TasksCoreService._validate_update) and past events — immutable
    # historical records (EventsCoreService._validate_update).
    resched_form = None
    if item.item_type == CalendarItemType.TASK and not _is_terminal_task(item):
        resched_form = reschedule_form(
            item.uid,
            with_time=False,
            date_value=item.start_time.date().isoformat(),
        )
    elif item.item_type == CalendarItemType.EVENT and item.start_time.date() >= date.today():
        resched_form = reschedule_form(
            item.uid,
            with_time=True,
            date_value=item.start_time.date().isoformat(),
            time_value=item.start_time.strftime("%H:%M"),
        )
    recurrence_info = None
    if item.is_recurring:
        recurrence_info = P(
            Icon("repeat", cls="w-3.5 h-3.5 inline-block mr-1.5 align-[-2px]"),
            f"Recurring: {item.recurrence_pattern}",
            cls="text-sm text-muted-foreground mt-1",
        )

    description_section = None
    if item.description:
        description_section = Div(
            P("Description", cls="text-sm font-semibold text-muted-foreground mb-2"),
            P(item.description, cls="text-muted-foreground"),
            cls="mb-4",
        )

    # Event-specific info (location, online, attendees)
    event_info = None
    if item.item_type == CalendarItemType.EVENT:
        event_details = []
        if item.location:
            event_details.append(
                P(
                    Icon(
                        "map-pin",
                        cls="w-4 h-4 inline-block mr-2 align-[-3px] text-muted-foreground",
                    ),
                    Span(item.location, cls="text-muted-foreground"),
                    cls="text-sm mb-2",
                )
            )
        if item.is_online:
            event_details.append(
                P(
                    Icon(
                        "video",
                        cls="w-4 h-4 inline-block mr-2 align-[-3px] text-muted-foreground",
                    ),
                    Span("Online meeting", cls="text-muted-foreground"),
                    cls="text-sm mb-2",
                )
            )
        if len(item.attendee_emails) > 0:
            attendee_badges = [
                Span(
                    email,
                    cls="px-2 py-1 bg-background border border-info/20 text-info rounded-sm text-xs mr-1 mb-1",
                )
                for email in islice(item.attendee_emails, 5)
            ]
            count_label = f"Attendees ({len(item.attendee_emails)}" + (
                f"/{item.max_attendees})" if item.max_attendees else ")"
            )
            event_details.append(
                Div(
                    P(
                        Icon("users", cls="w-4 h-4 inline-block mr-2 align-[-3px]"),
                        count_label,
                        cls="text-sm font-semibold text-muted-foreground mb-1",
                    ),
                    Div(*attendee_badges, cls="flex flex-wrap"),
                    cls="mt-2",
                )
            )
        if event_details:
            event_info = Div(*event_details, cls="bg-info/10 p-4 rounded-lg mb-4")

    # Habit streak + that-day completion state
    habit_info = None
    if item.item_type == CalendarItemType.HABIT and (
        item.streak_count is not None or occurrence_day is not None
    ):
        habit_lines: list[FT] = []
        if item.streak_count is not None:
            habit_lines.append(
                P(
                    Icon("flame", cls="w-4 h-4 inline-block mr-1.5 align-[-3px]"),
                    f"Current streak: {item.streak_count} days",
                    cls="text-sm font-semibold text-success",
                )
            )
        if occurrence_day is not None:
            habit_lines.append(habit_day_state_line(occurrence_done))
        habit_info = Div(*habit_lines, cls="bg-success/10 p-4 rounded-lg mb-4")

    # Tags
    tags_section = None
    if item.tags:
        tag_badges = [
            Badge(tag, variant=BadgeT.info, size=Size.sm, cls="mr-1") for tag in item.tags
        ]
        tags_section = Div(
            P("Tags", cls="text-sm font-semibold text-muted-foreground mb-2"),
            Div(*tag_badges, cls="flex flex-wrap"),
            cls="mb-4",
        )

    # Actions — Close + a type-appropriate edit/action
    action_buttons: list[FT] = [
        Button(
            "Close",
            cls=ButtonT.ghost,
            **{"x-on:click": close_expr},  # fasthtml dynamic-attr splat
        )
    ]
    if item.item_type == CalendarItemType.TASK:
        action_buttons.insert(
            0,
            ButtonLink(
                "Edit Task",
                href=f"/tasks/edit?uid={item.source_uid}",
                cls=(ButtonT.primary, "mr-2"),
            ),
        )
    elif item.item_type == CalendarItemType.EVENT:
        action_buttons.insert(
            0,
            ButtonLink(
                "Edit Event",
                href=f"/events/edit?uid={item.source_uid}",
                cls=(ButtonT.primary, "mr-2"),
            ),
        )
    elif item.item_type == CalendarItemType.MILESTONE:
        action_buttons.insert(
            0,
            ButtonLink(
                "View Goal",
                href=f"/goals/detail?uid={item.source_uid}",
                cls=(ButtonT.primary, "mr-2"),
            ),
        )
    elif item.item_type == CalendarItemType.HABIT and occurrence_day is not None:
        # Day-aware completion: post THAT day. Already-done days show a
        # disabled "Completed ✓"; future days offer no completion (the server
        # rejects them too); an unstamped habit modal offers no action at all.
        if occurrence_done:
            action_buttons.insert(
                0, Button("Completed ✓", disabled=True, cls=(ButtonT.secondary, "mr-2"))
            )
        elif occurrence_day <= date.today():
            action_buttons.insert(
                0,
                Button(
                    "Mark Complete",
                    cls=(ButtonT.secondary, "mr-2"),
                    hx_post=f"/cal/habit/{item.source_uid}/complete",
                    hx_vals=f'{{"on_date": "{occurrence_day.isoformat()}"}}',
                    hx_swap="outerHTML",
                ),
            )

    return Div(
        AlpineModal(
            # Header: type dot + pill (left), close (right)
            Div(
                Div(type_dot, type_pill, cls="flex items-center gap-2.5"),
                Button(
                    Icon("x", cls="w-5 h-5"),
                    cls=(ButtonT.ghost, "text-muted-foreground hover:text-foreground"),
                    size="sm",
                    **{"x-on:click": close_expr},  # fasthtml dynamic-attr splat
                ),
                cls="flex justify-between items-start gap-3 mb-3",
            ),
            H2(item.title, cls="text-2xl font-bold leading-tight mb-4"),
            # Schedule
            Div(
                P(
                    "Schedule",
                    cls="text-10 font-bold uppercase tracking-[0.08em] text-muted-foreground mb-1.5",
                ),
                schedule_display,
                recurrence_info,
                resched_form,
                cls="bg-muted/60 p-4 rounded-lg mb-4",
            ),
            description_section,
            event_info,
            habit_info,
            tags_section,
            Div(*action_buttons, cls="flex pt-4 border-t border-border"),
            show="open",
            close=close_expr,
            max_width="max-w-2xl",
            scrollable=True,
        ),
        x_data="{ open: true }",
        id="item-details-modal",
    )
