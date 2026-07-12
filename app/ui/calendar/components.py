"""
Calendar UI Components
======================

UI components for the redesigned calendar views (month, week, day).

All three views share one visual language:
- eyebrow + large title + a per-type legend (``create_calendar_header``)
- a segmented Day/Week/Month switcher + Prev/Today/Next + Monthly-note toolbar
  (``create_view_switcher`` / ``create_calendar_toolbar``)
- per-type colored event chips (``_event_chip``) — a leading dot + accent bar in
  the item's type color, fill at ~10% alpha

Month is a bordered grid with an ISO-week rail; Week is 7 day-column agenda cards;
Day is a vertical agenda list. Colors come from ``CalendarItemType.get_color()`` so
the legend stays truthful.

See: plans/design_handoff_calendar_month/README.md
"""

__version__ = "2.0"

from dataclasses import replace
from datetime import date, datetime, timedelta
from itertools import islice
from typing import Any

from fasthtml.common import H1, H2, A, Div, P, Span

from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
)
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle, Icon
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.modal import AlpineModal
from ui.primitives import ButtonLink

# Legend / switcher vocabulary — the calendar's five item types, in display order.
_LEGEND_TYPES: tuple[CalendarItemType, ...] = (
    CalendarItemType.EVENT,
    CalendarItemType.TASK_WORK,
    CalendarItemType.TASK_DEADLINE,
    CalendarItemType.HABIT,
    CalendarItemType.MILESTONE,
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


def create_calendar_legend() -> Div:
    """Five type swatches (color square + label), read from the enum palette."""
    swatches = [
        Div(
            Span(
                cls="w-[9px] h-[9px] rounded-[3px]",
                style=f"background-color: {item_type.get_color()}",
            ),
            Span(item_type.get_label(), cls="text-[11px] font-medium text-muted-foreground"),
            cls="flex items-center gap-1.5",
        )
        for item_type in _LEGEND_TYPES
    ]
    return Div(*swatches, cls="flex items-center gap-3.5 flex-wrap pb-1")


def create_calendar_header(title: str) -> Div:
    """Eyebrow + period title (left) and the type legend (right)."""
    return Div(
        Div(
            Div(
                "Calendar",
                cls="text-[11px] font-bold uppercase tracking-[0.1em] text-muted-foreground",
            ),
            H1(title, cls="text-[40px] font-bold tracking-[-0.02em] leading-none mt-1.5"),
        ),
        create_calendar_legend(),
        cls="flex items-end justify-between gap-6 flex-wrap mb-5",
    )


def create_view_switcher(current_view: str, target_date: date) -> Div:
    """Segmented Day/Week/Month control. Active segment is a non-navigating span."""
    views = (
        ("Day", "day", f"/events/day/{target_date.isoformat()}"),
        ("Week", "week", f"/events/week/{target_date.isoformat()}"),
        ("Month", "month", f"/events/month/{target_date.year}/{target_date.month}"),
    )
    seg_base = "inline-flex items-center h-7 px-4 rounded-md text-[13px] font-semibold"
    segments = []
    for label, view, url in views:
        if view == current_view:
            segments.append(
                Span(
                    label,
                    cls=f"{seg_base} bg-card text-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08)]",
                )
            )
        else:
            segments.append(
                A(
                    label,
                    href=url,
                    cls=f"{seg_base} bg-transparent text-muted-foreground hover:text-foreground",
                )
            )
    return Div(*segments, cls="inline-flex p-[3px] bg-muted border border-border rounded-[9px]")


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
            " rounded-lg text-[13px] font-medium text-foreground hover:bg-muted"
        ),
    )


def create_calendar_toolbar(
    current_view: str,
    target_date: date,
    prev_href: str,
    next_href: str,
    today_href: str,
    monthly_note_href: str,
) -> Div:
    """Segmented switcher (left) + Prev/Today/Next and Monthly-note cluster (right)."""
    nav = Div(
        _nav_button("Prev", prev_href, "chevron-left"),
        A(
            "Today",
            href=today_href,
            cls=(
                "inline-flex items-center h-[34px] px-4 bg-primary text-primary-foreground"
                " border border-primary rounded-lg text-[13px] font-semibold hover:opacity-90"
            ),
        ),
        _nav_button("Next", next_href, "chevron-right", trailing=True),
        Div(cls="w-px h-[22px] bg-border mx-1"),
        A(
            Icon("square-pen", cls="w-[15px] h-[15px]"),
            Span("Monthly note"),
            href=monthly_note_href,
            title="Open monthly note",
            **_NO_BOOST,
            cls=(
                "inline-flex items-center gap-[7px] h-[34px] px-[13px] border border-border"
                " bg-card rounded-lg text-[13px] font-medium text-foreground hover:bg-muted"
                " whitespace-nowrap"
            ),
        ),
        cls="flex items-center gap-2",
    )
    return Div(
        create_view_switcher(current_view, target_date),
        nav,
        cls="flex items-center justify-between gap-4 flex-wrap mb-5",
    )


# ============================================================================
# EVENT CHIP (shared across views)
# ============================================================================


def _item_start(item: CalendarItem) -> datetime:
    """Sort key: an item's start time (chronological ordering within a day)."""
    return item.start_time


def _items_by_date(calendar_data: CalendarData) -> dict[date, list[CalendarItem]]:
    """Group calendar items onto their days, expanding recurring habits.

    Non-habit items land on ``start_time.date()``. A habit is a single item stamped
    at ``now()``, so it is expanded into one all-day chip per generated occurrence
    (title/color reused from the habit item) — otherwise recurring habits would only
    show on today, and vanish entirely in months that don't include today.
    """
    habit_items = {
        item.source_uid: item
        for item in calendar_data.items
        if item.item_type == CalendarItemType.HABIT
    }
    by_date: dict[date, list[CalendarItem]] = {}
    for item in calendar_data.items:
        if item.item_type == CalendarItemType.HABIT:
            continue  # expanded from occurrences below (the raw item is a now() stub)
        by_date.setdefault(item.start_time.date(), []).append(item)

    midnight = datetime.min.time()
    for occurrences in calendar_data.occurrences.values():
        for occ in occurrences:
            base = habit_items.get(occ.calendar_item_uid)
            if base is None:
                continue
            day_start = datetime.combine(occ.date, midnight)
            by_date.setdefault(occ.date, []).append(
                replace(base, all_day=True, start_time=day_start, end_time=day_start)
            )
    return by_date


def _fmt_time(dt: datetime) -> str:
    """12-hour clock without a leading zero (e.g. ``9:30 AM``)."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _time_range_label(item: CalendarItem) -> str:
    """``All day`` for markers, else ``start – end`` (collapsed if equal)."""
    if item.all_day:
        return "All day"
    start = _fmt_time(item.start_time)
    end = _fmt_time(item.end_time)
    return f"{start} – {end}" if end != start else start


def _event_chip(item: CalendarItem, *, large: bool = False) -> Div:
    """A clickable event chip colored by item type.

    Fill = type color at ~10% alpha (8-digit hex ``1a``); a 3px left accent bar +
    leading dot in the full color. ``large`` (week/day) adds a mono time label.
    Click opens the item-details modal via the existing HTMX endpoint.
    """
    color = item.color
    dot = Span(cls="flex-none w-2 h-2 rounded-full", style=f"background-color: {color}")
    htmx = {
        "data_item_id": item.uid,
        "hx_get": f"/events/calendar/item-details/{item.uid}",
        "hx_target": "body",
        "hx_swap": "beforeend",
    }
    chip_style = f"background-color: {color}1a; border-left: 3px solid {color}"

    if large:
        return Div(
            Div(
                dot,
                Span(
                    item.title,
                    cls="flex-1 min-w-0 truncate text-[12.5px] font-semibold text-foreground",
                ),
                cls="flex items-center gap-1.5",
            ),
            Div(
                _time_range_label(item),
                cls="text-[11px] text-muted-foreground font-mono mt-[3px]",
            ),
            cls="calendar-item px-2.5 py-2 rounded-lg cursor-pointer",
            style=chip_style,
            title=item.title,
            **htmx,
        )

    return Div(
        dot,
        Span(item.title, cls="flex-1 min-w-0 truncate"),
        cls=(
            "calendar-item flex items-center gap-1.5 px-[7px] py-0.5 rounded-md"
            " text-[11.5px] font-medium leading-[1.5] text-foreground cursor-pointer"
        ),
        style=chip_style,
        title=item.title,
        **htmx,
    )


# ============================================================================
# MONTH VIEW
# ============================================================================


def create_month_grid(calendar_data: CalendarData) -> Div:
    """Bordered month grid: ISO-week rail + 7 day columns, one row per week."""
    items_by_date = _items_by_date(calendar_data)

    # Grid starts on the Monday on/just before the 1st of the month.
    first_day = calendar_data.start_date
    grid_start = first_day - timedelta(days=first_day.weekday())

    weeks = []
    current_date = grid_start
    while current_date <= calendar_data.end_date or current_date.month == first_day.month:
        iso_year, iso_week, _ = current_date.isocalendar()
        week_cells = []
        for weekday_index in range(7):
            day_items = sorted(items_by_date.get(current_date, []), key=_item_start)
            week_cells.append(
                create_day_cell(
                    current_date,
                    day_items[:3],
                    more_count=max(0, len(day_items) - 3),
                    is_current_month=current_date.month == first_day.month,
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
                "flex items-center justify-center font-mono text-[11px] text-muted-foreground"
                " bg-muted/25 border-r border-b border-border hover:text-primary hover:bg-muted/60"
            ),
        )
        weeks.append(Div(rail, *week_cells, cls=_MONTH_GRID_COLS))

        if current_date.month != first_day.month and current_date > calendar_data.end_date:
            break

    header = Div(
        Div(
            "Wk",
            cls=(
                "flex items-center justify-center py-[11px] text-[10px] font-bold uppercase"
                " tracking-[0.06em] text-muted-foreground border-b border-r border-border"
            ),
        ),
        *[
            Div(
                label,
                cls=(
                    "text-center py-[11px] text-[12px] font-semibold border-b border-border "
                    + ("text-muted-foreground" if i >= 5 else "text-foreground")
                ),
            )
            for i, label in enumerate(_WEEKDAY_LABELS)
        ],
        cls=f"{_MONTH_GRID_COLS} bg-muted/50",
    )

    return Div(
        header,
        *weeks,
        cls="border border-border rounded-xl overflow-hidden bg-card shadow-[0_1px_3px_rgba(0,0,0,0.04)]",
    )


def create_day_cell(
    cell_date: date,
    items: list[CalendarItem],
    *,
    more_count: int,
    is_current_month: bool,
    is_weekend: bool,
) -> Div:
    """A single month-grid day cell: date number/pill + up to 3 chips + overflow."""
    is_today = cell_date == date.today()
    daily_href = f"/journals/daily/{cell_date.isoformat()}"

    if is_today:
        date_el = A(
            str(cell_date.day),
            href=daily_href,
            title="Daily note",
            **_NO_BOOST,
            cls=(
                "inline-flex items-center justify-center min-w-[24px] h-6 px-1.5 rounded-full"
                " bg-primary text-primary-foreground text-[12px] font-bold"
            ),
        )
    else:
        tone = "text-foreground" if is_current_month else "text-muted-foreground/60"
        date_el = A(
            str(cell_date.day),
            href=daily_href,
            title="Daily note",
            **_NO_BOOST,
            cls=f"text-[13px] font-semibold {tone} hover:text-primary",
        )

    chips = [_event_chip(item) for item in items]
    more_el = (
        Div(f"+{more_count} more", cls="text-[11px] font-medium text-muted-foreground px-1.5 pt-px")
        if more_count > 0
        else None
    )

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

    # event.target===this replicates Alpine's .self modifier — navigate to the daily
    # note only when the cell background (not a chip) is clicked. Plain JS so it works
    # in HTMX-swapped content without an Alpine re-init.
    return Div(
        Div(date_el, cls="flex items-center min-h-[24px] mb-[5px]"),
        Div(*chips, more_el, cls="flex flex-col gap-[3px]"),
        cls=cell_cls,
        style=cell_style,
        onclick=f"if(event.target===this)window.location.href='{daily_href}'",
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
        day_items = sorted(items_by_date.get(day, []), key=_item_start)

        head_tone = (
            "bg-primary text-primary-foreground"
            if is_today
            else "bg-muted/50 text-foreground hover:bg-muted"
        )
        head = A(
            Span(
                _WEEKDAY_LABELS[offset],
                cls="text-[10px] font-bold uppercase tracking-[0.06em] opacity-75",
            ),
            Span(str(day.day), cls="text-[18px] font-bold leading-none"),
            href=f"/journals/daily/{day.isoformat()}",
            title="Daily note",
            **_NO_BOOST,
            cls=f"flex flex-col gap-1 px-3 py-2.5 border-b border-border {head_tone}",
        )

        if day_items:
            body_children: list[Any] = [_event_chip(item, large=True) for item in day_items]
        else:
            body_children = [Div("No events", cls="text-[12px] text-muted-foreground/60 p-1.5")]
        body = Div(*body_children, cls="p-2 flex flex-col gap-1.5 flex-1")

        cards.append(
            Div(
                head,
                body,
                cls="border border-border rounded-[11px] overflow-hidden bg-card min-h-[360px] flex flex-col",
            )
        )

    return Div(*cards, cls="grid grid-cols-1 sm:grid-cols-7 gap-2.5")


# ============================================================================
# DAY VIEW (agenda list)
# ============================================================================


def create_day_timeline(calendar_data: CalendarData) -> Div:
    """Vertical agenda: a mono time gutter + a type-accented card per event."""
    items = sorted(_items_by_date(calendar_data).get(calendar_data.start_date, []), key=_item_start)
    if not items:
        return Div(
            Div("Nothing scheduled", cls="text-[16px] font-semibold text-foreground mb-1.5"),
            Div("This day is clear.", cls="text-[13px] text-muted-foreground"),
            cls="text-center py-16 px-6",
        )

    rows = []
    for item in items:
        color = item.color
        start_label = "All day" if item.all_day else _fmt_time(item.start_time)
        pill = Span(
            item.item_type.get_label(),
            cls=(
                "inline-flex items-center px-[9px] py-0.5 rounded-full text-[10.5px]"
                " font-semibold uppercase tracking-[0.04em]"
            ),
            style=f"background-color: {color}1f; color: {color}",
        )
        dot = Span(cls="flex-none w-2 h-2 rounded-full", style=f"background-color: {color}")
        card = Div(
            Div(
                dot,
                Span(item.title, cls="text-[15px] font-semibold text-foreground"),
                pill,
                cls="flex items-center gap-2 flex-wrap",
            ),
            Div(
                _time_range_label(item),
                cls="text-[12.5px] text-muted-foreground font-mono mt-1",
            ),
            Div(item.description, cls="text-[13px] text-muted-foreground mt-1.5 leading-[1.5]")
            if item.description
            else None,
            cls="calendar-item flex-1 bg-card border border-border rounded-[10px] px-4 py-3.5 cursor-pointer",
            style=f"border-left: 4px solid {color}",
            data_item_id=item.uid,
            hx_get=f"/events/calendar/item-details/{item.uid}",
            hx_target="body",
            hx_swap="beforeend",
        )
        gutter = Div(
            start_label,
            cls="w-[72px] flex-none text-right pt-3.5 font-mono text-[12px] text-muted-foreground",
        )
        rows.append(Div(gutter, card, cls="flex gap-4 items-stretch"))

    return Div(*rows, cls="flex flex-col gap-2.5")


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


def create_item_details_modal(item: Any) -> Div:
    """Render calendar item details as an HTMX modal fragment.

    Header = a type-colored dot + type pill + Lucide close; the body keeps the full
    schedule / description / event / habit / tags detail. Returns server-rendered
    HTML (not JSON) for a direct ``beforeend`` swap onto ``body``.
    """
    color = item.color
    type_pill = Span(
        item.item_type.get_label(),
        cls=(
            "inline-flex items-center px-[9px] py-0.5 rounded-full text-[10.5px]"
            " font-semibold uppercase tracking-[0.04em]"
        ),
        style=f"background-color: {color}1f; color: {color}",
    )
    type_dot = Span(cls="flex-none w-2.5 h-2.5 rounded-full", style=f"background-color: {color}")

    # Close: hide via Alpine, then remove the wrapper after the transition.
    close_expr = (
        "open = false; $nextTick(() => document.getElementById('item-details-modal')?.remove())"
    )

    # Schedule
    schedule_text = (
        "All Day"
        if item.all_day
        else f"{_format_datetime(item.start_time)} - {_format_datetime(item.end_time)}"
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
                    cls="px-2 py-1 bg-background border border-info/20 text-info rounded text-xs mr-1 mb-1",
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

    # Habit streak
    habit_info = None
    if item.item_type == CalendarItemType.HABIT and item.streak_count is not None:
        habit_info = Div(
            P(
                Icon("flame", cls="w-4 h-4 inline-block mr-1.5 align-[-3px]"),
                f"Current streak: {item.streak_count} days",
                cls="text-sm font-semibold text-success",
            ),
            cls="bg-success/10 p-4 rounded-lg mb-4",
        )

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
    action_buttons: list[Any] = [
        Button(
            "Close",
            cls=ButtonT.ghost,
            **{"x-on:click": close_expr},  # fasthtml dynamic-attr splat
        )
    ]
    if item.item_type in (CalendarItemType.TASK_WORK, CalendarItemType.TASK_DEADLINE):
        action_buttons.insert(
            0,
            ButtonLink(
                "Edit Task",
                href=f"/tasks/{item.source_uid}/edit",
                cls=(ButtonT.primary, "mr-2"),
            ),
        )
    elif item.item_type == CalendarItemType.EVENT:
        action_buttons.insert(
            0,
            ButtonLink(
                "Edit Event",
                href=f"/events/{item.source_uid}/edit",
                cls=(ButtonT.primary, "mr-2"),
            ),
        )
    elif item.item_type == CalendarItemType.HABIT:
        action_buttons.insert(
            0,
            Button(
                "Mark Complete",
                cls=(ButtonT.secondary, "mr-2"),
                hx_post=f"/events/calendar/habit/{item.source_uid}/complete",
                hx_swap="none",
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
                    cls="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground mb-1.5",
                ),
                P(schedule_text, cls="text-sm text-foreground"),
                recurrence_info,
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
