"""
Calendar UI Components
======================

UI components for calendar views (month, week, day).
Extracted from calendar_routes.py for separation of concerns.

Usage:
    from ui.calendar.components import (
        create_month_grid,
        create_week_grid,
        create_day_timeline,
        create_quick_add_modal,
        error_response,
    )
"""

__version__ = "1.0"

from datetime import date, datetime, timedelta
from itertools import islice
from typing import Any

from fasthtml.common import H2, H3, H4, A, Div, Form, Option, P, Span
from monsterui.franken import Button, ButtonT, CardBody, CardHeader, CardTitle, UkIcon
from monsterui.franken import CardContainer as Card

from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
)
from ui.feedback import Badge, BadgeT
from ui.forms import Input, Label, Select
from ui.layout import Size
from ui.patterns.modal import AlpineModal
from ui.primitives import ButtonLink


def create_month_grid(calendar_data: CalendarData) -> Div:
    """
    Create the month view grid showing all days with their calendar items.

    Args:
        calendar_data: Calendar data containing items and date range

    Returns:
        Div containing the complete month grid with day headers and week rows
    """
    # Group items by date
    items_by_date: dict[date, list[CalendarItem]] = {}
    for item in calendar_data.items:
        item_date = item.start_time.date()
        if item_date not in items_by_date:
            items_by_date[item_date] = []
        items_by_date[item_date].append(item)

    # Get occurrences by date
    occurrences_by_date: dict[date, list[CalendarOccurrence]] = {}
    for occurrences in calendar_data.occurrences.values():
        for occ in occurrences:
            if occ.date not in occurrences_by_date:
                occurrences_by_date[occ.date] = []
            occurrences_by_date[occ.date].append(occ)

    # Calculate calendar grid starting point
    # Start from the first day of the month, then back up to the previous Monday
    first_day = calendar_data.start_date
    # weekday() returns 0=Monday, 6=Sunday
    days_to_monday = first_day.weekday()
    grid_start = first_day - timedelta(days=days_to_monday)

    # Create week rows
    weeks = []
    current_date = grid_start

    # Continue until we've covered the entire month
    while (
        current_date <= calendar_data.end_date
        or current_date.month == calendar_data.start_date.month
    ):
        # Each grid row starts on a Monday — same anchor ISO weeks use, so the
        # first cell's ISO week number labels the whole row.
        week_start_date = current_date
        iso_year, iso_week, _ = week_start_date.isocalendar()

        week_cells = []
        for _ in range(7):
            # Get items for this date
            date_items = items_by_date.get(current_date, [])
            date_occurrences = occurrences_by_date.get(current_date, [])

            # Create day cell
            week_cells.append(
                create_day_cell(
                    current_date,
                    date_items[:3],  # Show max 3 items
                    date_occurrences,
                    len(date_items) > 3,
                    is_current_month=(current_date.month == calendar_data.start_date.month),
                )
            )

            current_date += timedelta(days=1)

        # Week-number cell links to the Weekly Note (Obsidian Calendar-style).
        week_num_cell = A(
            str(iso_week),
            href=f"/journals/weekly/{iso_year}/{iso_week}",
            title=f"Weekly note — W{iso_week}, {iso_year}",
            cls=(
                "border-r border-b p-2 flex items-center justify-center text-xs"
                " text-muted-foreground hover:text-primary hover:bg-muted cursor-pointer"
            ),
        )
        weeks.append(Div(week_num_cell, *week_cells, cls="grid grid-cols-8 gap-0"))

        # Stop if we've gone past the end of the month
        if (
            current_date.month != calendar_data.start_date.month
            and current_date > calendar_data.end_date
        ):
            break

    return Div(
        # Day headers (leading "W" column for week numbers)
        Div(
            Div(
                "W",
                cls="text-center font-semibold py-2 border-b border-r text-xs text-muted-foreground",
            ),
            *[
                Div(day, cls="text-center font-semibold py-2 border-b")
                for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            ],
            cls="grid grid-cols-8 gap-0 mb-0",
        ),
        # Week rows
        *weeks,
        cls="border rounded-lg overflow-hidden",
    )


def create_day_cell(
    cell_date: date,
    items: list[CalendarItem],
    occurrences: list[CalendarOccurrence],
    has_more: bool,
    is_current_month: bool = True,
) -> Div:
    """
    Create a single day cell for month view.

    Args:
        cell_date: The date for this cell
        items: Calendar items for this date (max 3)
        occurrences: Habit occurrences for this date
        has_more: Whether there are more items than shown
        is_current_month: Whether this date is in the current month

    Returns:
        Div containing the day cell UI
    """
    is_today = cell_date == date.today()

    # Build item elements - using HTMX for modal loading
    item_elements = [
        Div(
            Span(item.icon, cls="mr-1"),
            Span(item.title[:15] + "..." if len(item.title) > 15 else item.title, cls="text-xs"),
            cls="calendar-item px-1 py-0.5 rounded text-white mb-1 cursor-pointer hover:opacity-80",
            style=f"background-color: {item.color}",
            data_item_id=item.uid,
            hx_get=f"/events/calendar/item-details/{item.uid}",
            hx_target="body",
            hx_swap="beforeend",
        )
        for item in items
    ]

    # Build occurrence indicators
    occurrence_elements = []
    for occ in occurrences:
        icon = occ.status.get_emoji()
        occurrence_elements.append(Span(icon, cls="text-xs mr-1", title=occ.notes or ""))

    # More indicator
    more_element = []
    if has_more:
        more_element.append(Div("+more", cls="text-xs text-muted-foreground mt-1"))

    # Date number links to the Daily Note (Obsidian Calendar-style).
    # hx-boost="false" opts out of HTMX boost so the 302 redirect from
    # /journals/daily/{date} triggers a full browser navigation instead of
    # being swapped into the current HTMX target.
    daily_href = f"/journals/daily/{cell_date.isoformat()}"
    if is_today:
        date_header = Div(
            A(
                str(cell_date.day),
                href=daily_href,
                title="Daily note",
                **{"hx-boost": "false"},
                cls="text-lg font-bold text-primary hover:opacity-70",
            ),
            Badge("Today", variant=BadgeT.primary, size=Size.sm, cls="ml-2"),
            cls="flex items-center mb-1",
        )
    else:
        date_header = A(
            str(cell_date.day),
            href=daily_href,
            title="Daily note",
            **{"hx-boost": "false"},
            cls=(
                "text-sm font-semibold mb-1 block hover:text-primary "
                f"{'text-foreground' if is_current_month else 'text-foreground/40'}"
            ),
        )

    # Cell styling - more prominent today indicator with ring
    cell_cls = "border-r border-b p-2 min-h-[100px] "
    if is_today:
        cell_cls += "bg-primary/10 ring-2 ring-primary ring-inset"
    elif is_current_month:
        cell_cls += "bg-background"
    else:
        cell_cls += "bg-muted"

    return Div(
        # Date number (with Today badge if applicable)
        date_header,
        # Items
        *item_elements,
        # Occurrences
        Div(*occurrence_elements, cls="flex") if occurrence_elements else None,
        # More indicator
        *more_element,
        cls=cell_cls,
    )


def create_week_grid(calendar_data: CalendarData) -> Div:
    """
    Create the week view grid with time slots.

    Args:
        calendar_data: Calendar data containing items and date range

    Returns:
        Div containing the complete week grid with time slots
    """
    # Group items by day and time
    items_by_datetime: dict[tuple[date, int], list[CalendarItem]] = {}
    for item in calendar_data.items:
        key = (item.start_time.date(), item.start_time.hour)
        if key not in items_by_datetime:
            items_by_datetime[key] = []
        items_by_datetime[key].append(item)

    # Create time slots (6am to 11pm)
    time_slots = []
    for hour in range(6, 24):
        time_label = f"{hour:02d}:00"

        # Create cells for each day of the week
        day_cells = []
        current_date = calendar_data.start_date

        for day_offset in range(7):
            day_date = current_date + timedelta(days=day_offset)
            slot_items = items_by_datetime.get((day_date, hour), [])
            # ISO datetime for this slot (used for drag-drop reschedule)
            slot_datetime = f"{day_date.isoformat()}T{hour:02d}:00:00"

            day_cells.append(
                Div(
                    *[create_week_item(item) for item in slot_items],
                    cls="border-r border-b p-1 h-16 relative",
                    # Alpine.js: click opens quick-add modal, drag-drop handlers
                    **{
                        "x-on:click": f"openQuickAdd('{day_date.isoformat()}', {hour})",
                        "x-on:dragover.prevent": "handleDragOver($event)",
                        "x-on:drop": f"handleDrop($event, '{slot_datetime}')",
                    },
                )
            )

        time_slots.append(
            Div(
                Div(time_label, cls="w-16 text-xs text-muted-foreground pr-2 text-right"),
                *day_cells,
                cls="grid grid-cols-8 gap-0",
            )
        )

    # Day headers
    days = []
    current_date = calendar_data.start_date
    for _ in range(7):
        days.append(current_date.strftime("%a %d"))
        current_date += timedelta(days=1)

    return Div(
        # Header row
        Div(
            Div("", cls="w-16"),  # Empty corner
            *[Div(day, cls="text-center font-semibold py-2 border-b border-r") for day in days],
            cls="grid grid-cols-8 gap-0",
        ),
        # Time slots
        *time_slots,
        cls="border rounded-lg overflow-hidden",
    )


def create_week_item(item: CalendarItem) -> Div:
    """
    Create a calendar item for week view.

    Args:
        item: The calendar item to render

    Returns:
        Div containing the week view item UI
    """
    return Div(
        Span(item.icon, cls="mr-1"),
        Span(
            item.title[:10] + "..." if len(item.title) > 10 else item.title,
            cls="text-xs text-white",
        ),
        id=f"calendar-item-{item.uid}",  # ID for potential OOB swap
        cls="px-1 py-0.5 rounded cursor-move",
        style=f"background-color: {item.color}",
        draggable="true",
        # Alpine.js: drag-and-drop handling
        **{"x-on:dragstart": f"handleDragStart($event, '{item.uid}')"},
        # Use HTMX for modal loading instead of JavaScript
        hx_get=f"/events/calendar/item-details/{item.uid}",
        hx_target="body",
        hx_swap="beforeend",
    )


def create_day_timeline(calendar_data: CalendarData) -> Div:
    """
    Create the day view timeline.

    Args:
        calendar_data: Calendar data containing items for the day

    Returns:
        Div containing the day timeline UI
    """
    # Group items by hour
    items_by_hour: dict[int, list[CalendarItem]] = {}
    for item in calendar_data.items:
        hour = item.start_time.hour
        if hour not in items_by_hour:
            items_by_hour[hour] = []
        items_by_hour[hour].append(item)

    # Create timeline (6am to 11pm)
    timeline_slots = []
    for hour in range(6, 24):
        time_label = f"{hour:02d}:00"
        slot_items = items_by_hour.get(hour, [])
        # ISO datetime for this slot (used for drag-drop reschedule)
        slot_datetime = f"{calendar_data.start_date.isoformat()}T{hour:02d}:00:00"

        timeline_slots.append(
            Div(
                # Time label
                Div(time_label, cls="w-20 text-sm text-muted-foreground pr-4 text-right"),
                # Items for this hour
                Div(
                    *[create_timeline_item(item) for item in slot_items],
                    cls="flex-1 border-l-2 border-border pl-4 min-h-[60px]",
                    # Alpine.js: click opens quick-add modal, drag-drop handlers
                    **{
                        "x-on:click": f"openQuickAdd('{calendar_data.start_date.isoformat()}', {hour})",
                        "x-on:dragover.prevent": "handleDragOver($event)",
                        "x-on:drop": f"handleDrop($event, '{slot_datetime}')",
                    },
                ),
                cls="flex mb-0 hover:bg-muted cursor-pointer",
            )
        )

    return Div(*timeline_slots, cls="bg-background rounded-lg border p-4")


def create_timeline_item(item: CalendarItem) -> Div:
    """
    Create a calendar item for day timeline.

    Args:
        item: The calendar item to render

    Returns:
        Card containing the timeline item UI
    """
    duration = (item.end_time - item.start_time).seconds // 60

    return Card(
        Div(
            Span(item.icon, cls="text-lg mr-2"),
            Span(item.title, cls="font-semibold"),
            cls="flex items-center mb-1",
        ),
        P(
            f"{item.start_time.strftime('%H:%M')} - {item.end_time.strftime('%H:%M')} ({duration} min)",
            cls="text-sm text-muted-foreground mb-1",
        ),
        P(
            item.description[:100] + "..." if len(item.description) > 100 else item.description,
            cls="text-sm text-muted-foreground",
        )
        if item.description
        else None,
        # Habit occurrence indicator
        create_habit_check_in(item) if item.item_type == CalendarItemType.HABIT else None,
        id=f"calendar-item-{item.uid}",  # ID for potential OOB swap
        cls="bg-background shadow-sm mb-2 p-3 cursor-move",
        style=f"border-left: 4px solid {item.color}",
        draggable="true",
        # Alpine.js: drag-and-drop handling + HTMX for modal loading
        **{"x-on:dragstart": f"handleDragStart($event, '{item.uid}')"},
        hx_get=f"/events/calendar/item-details/{item.uid}",
        hx_target="body",
        hx_swap="beforeend",
    )


def create_habit_check_in(item: CalendarItem) -> Div:
    """
    Create habit check-in UI for day view.

    Uses HTMX for recording habit occurrences.

    Args:
        item: The habit calendar item

    Returns:
        Div containing the habit check-in UI
    """
    habit_uid = item.source_uid
    note_input_id = f"habit-note-{habit_uid}"

    return Div(
        H4("Check in for today:", cls="text-sm font-semibold mt-3 mb-2"),
        # Status container for HTMX response
        Div(id=f"habit-status-{habit_uid}"),
        Div(
            Input(
                type="text",
                name="notes",
                placeholder="How did it go?",
                id=note_input_id,
                cls="flex-1 px-2 py-1 border rounded-l text-sm",
            ),
            # HTMX buttons - each posts to different endpoint with status
            Button(
                "✅",
                type="button",
                cls=(ButtonT.primary, ButtonT.sm),
                hx_post=f"/events/calendar/habit/{habit_uid}/record/done",
                hx_target=f"#habit-status-{habit_uid}",
                hx_swap="innerHTML",
                hx_include=f"#{note_input_id}",
            ),
            Button(
                "⏭️",
                type="button",
                cls=(ButtonT.secondary, ButtonT.sm),
                hx_post=f"/events/calendar/habit/{habit_uid}/record/skipped",
                hx_target=f"#habit-status-{habit_uid}",
                hx_swap="innerHTML",
                hx_include=f"#{note_input_id}",
            ),
            Button(
                "❌",
                type="button",
                cls=(ButtonT.destructive, ButtonT.sm),
                hx_post=f"/events/calendar/habit/{habit_uid}/record/missed",
                hx_target=f"#habit-status-{habit_uid}",
                hx_swap="innerHTML",
                hx_include=f"#{note_input_id}",
            ),
            cls="flex gap-1",
        ),
        cls="mt-3 p-2 bg-muted rounded",
    )


def create_quick_add_modal() -> Div:
    """
    Create the quick add modal for adding calendar items.

    Uses Alpine.js for modal state and HTMX for form submission.

    Returns:
        Div containing the quick add modal (Alpine.js controlled visibility)
    """
    return AlpineModal(
        Form(
            H3("Quick Add", cls="text-xl font-bold mb-4"),
            # Status container for HTMX response
            Div(id="quick-add-status"),
            # Item type selector
            Div(
                Label("Type", cls="block text-sm font-medium mb-1"),
                Select(
                    Option("Task", value="task"),
                    Option("Event", value="event"),
                    Option("Habit", value="habit"),
                    name="type",
                    id="quick-add-type",
                ),
                cls="mb-4",
            ),
            # Title input
            Div(
                Label("Title", cls="block text-sm font-medium mb-1"),
                Input(
                    type="text",
                    name="title",
                    id="quick-add-title",
                    placeholder="Enter title...",
                    required=True,
                ),
                cls="mb-4",
            ),
            # Date/time input - Alpine.js x-model for datetime binding
            Div(
                Label("Date & Time", cls="block text-sm font-medium mb-1"),
                Input(
                    type="datetime-local",
                    name="start_time",
                    id="quick-add-datetime",
                    required=True,
                    x_model="datetime",
                ),
                cls="mb-4",
            ),
            # Duration input
            Div(
                Label("Duration (minutes)", cls="block text-sm font-medium mb-1"),
                Input(
                    type="number",
                    name="duration",
                    id="quick-add-duration",
                    value="60",
                ),
                cls="mb-4",
            ),
            # Buttons - Alpine.js for cancel
            Div(
                Button(
                    "Cancel",
                    type="button",
                    cls=(ButtonT.ghost, "mr-2"),
                    **{"x-on:click": "closeQuickAdd()"},  # fasthtml dynamic-attr splat
                ),
                Button(
                    "Create",
                    type="submit",
                    cls=ButtonT.primary,
                ),
                cls="flex justify-end",
            ),
            # HTMX form submission
            hx_post="/events/calendar/quick-create",
            hx_target="#quick-add-status",
            hx_swap="innerHTML",
        ),
        show="open",
        close="closeQuickAdd()",
        id="quick-add-modal",
    )


def create_reschedule_form() -> Form:
    """
    Create hidden HTMX form for drag-drop reschedule.

    This form is triggered by Alpine.js when an item is dropped on a time slot.
    Uses HTMX to submit the reschedule request and refresh the calendar grid.

    Returns:
        Hidden form with HTMX attributes for reschedule submission
    """
    return Form(
        Input(type="hidden", name="uid", x_ref="rescheduleUid"),
        Input(type="hidden", name="new_start", x_ref="rescheduleTime"),
        id="reschedule-form",
        style="display: none;",
        **{
            "x-ref": "rescheduleForm",
            "hx-patch": "/api/calendar/reschedule",
            "hx-target": "#calendar-grid",
            "hx-swap": "innerHTML",
            "hx-trigger": "submit",
        },
    )


def create_view_switcher(current_view: str, target_date: date) -> Div:
    """
    Create the day/week/month view switcher using links.

    Args:
        current_view: Current active view ('day', 'week', or 'month')
        target_date: The date to use for navigation links

    Returns:
        Div containing the view switcher links
    """
    views = [
        ("Day", "day", f"/events/day/{target_date.isoformat()}"),
        ("Week", "week", f"/events/week/{target_date.isoformat()}"),
        ("Month", "month", f"/events/month/{target_date.year}/{target_date.month}"),
    ]

    buttons = []
    for label, view, url in views:
        is_active = view == current_view
        cls_extra = ""
        if view == "day":
            cls_extra = "rounded-l-lg rounded-r-none"
        elif view == "month":
            cls_extra = "rounded-r-lg rounded-l-none"
        else:
            cls_extra = "rounded-none"

        if is_active:
            # Active view - styled span (not clickable)
            buttons.append(
                Button(
                    label,
                    cls=(ButtonT.primary, ButtonT.sm, f"cursor-default {cls_extra}"),
                    disabled=True,
                )
            )
        else:
            # Inactive view - use link
            buttons.append(
                ButtonLink(
                    label,
                    href=url,
                    cls=(ButtonT.ghost, ButtonT.sm, cls_extra),
                )
            )

    return Div(*buttons, cls="inline-flex mb-4")


def create_quick_add_button() -> Div:
    """
    Create the floating quick add button.

    Uses Alpine.js to open the quick add modal.

    Returns:
        Div containing the quick add button
    """
    return Div(
        Button(
            "+ Add Item",
            cls=(ButtonT.primary, "fixed bottom-6 right-6 rounded-full shadow-lg"),
            **{"x-on:click": "openQuickAdd()"},  # fasthtml dynamic-attr splat
        ),
    )


def error_response(error_message: Any) -> Div:
    """
    Create an error response UI.

    Args:
        error_message: The error message to display

    Returns:
        Div with the error UI
    """
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


def calendar_item_to_dict(item: CalendarItem) -> dict[str, Any]:
    """
    Convert calendar item to dictionary for JSON response.

    Args:
        item: The calendar item to convert

    Returns:
        Dictionary representation of the calendar item
    """
    return {
        "uid": item.uid,
        "title": item.title,
        "start_time": item.start_time.isoformat(),
        "end_time": item.end_time.isoformat(),
        "color": item.color,
        "icon": item.icon,
        "type": item.item_type.value,
    }


def _format_datetime(dt: datetime) -> str:
    """Format datetime for display."""
    return dt.strftime("%b %d, %I:%M %p")


def create_item_details_modal(item: Any) -> Div:
    """
    Render calendar item details as an HTMX modal fragment.

    Returns server-rendered HTML instead of JSON for HTMX swap.
    """
    # Type badge
    type_badge = Span(
        item.item_type.value.replace("_", " ").upper(),
        cls="px-3 py-1 rounded-full text-xs font-medium",
        style=f"background-color: {item.color}20; color: {item.color}",
    )

    # Priority stars
    priority_stars = ""
    if item.priority:
        priority_stars = Span(
            "⭐" * item.priority,
            cls="text-sm text-muted-foreground ml-4",
        )

    # Schedule info
    schedule_text = (
        "All Day"
        if item.all_day
        else f"{_format_datetime(item.start_time)} - {_format_datetime(item.end_time)}"
    )

    recurrence_info = None
    if item.is_recurring:
        recurrence_info = P(
            f"🔁 Recurring: {item.recurrence_pattern}",
            cls="text-sm text-muted-foreground mt-1",
        )

    # Description section
    description_section = None
    if item.description:
        description_section = Div(
            P("Description", cls="text-sm font-semibold text-muted-foreground mb-2"),
            P(item.description, cls="text-muted-foreground"),
            cls="mb-4",
        )

    # Event-specific info (location, attendees)
    event_info = None
    if item.item_type == CalendarItemType.EVENT:
        event_details = []
        if item.location:
            event_details.append(
                P(
                    Span("📍 Location:", cls="font-semibold text-muted-foreground"),
                    Span(item.location, cls="text-muted-foreground ml-2"),
                    cls="text-sm mb-2",
                )
            )
        if item.is_online:
            event_details.append(
                P(
                    Span("💻 Format:", cls="font-semibold text-muted-foreground"),
                    Span("Online Meeting", cls="text-muted-foreground ml-2"),
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
            event_details.append(
                Div(
                    P(
                        f"👥 Attendees ({len(item.attendee_emails)}"
                        + (f"/{item.max_attendees})" if item.max_attendees else ")"),
                        cls="text-sm font-semibold text-muted-foreground mb-1",
                    ),
                    Div(*attendee_badges, cls="flex flex-wrap"),
                    cls="mt-2",
                )
            )
        if event_details:
            event_info = Div(*event_details, cls="bg-info/10 p-4 rounded-lg mb-4")

    # Habit streak info
    habit_info = None
    if item.item_type == CalendarItemType.HABIT and item.streak_count is not None:
        habit_info = Div(
            P(
                f"Current Streak: {item.streak_count} days 🔥",
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

    # Close expression: hide via Alpine, then remove wrapper after transition
    close_expr = (
        "open = false; $nextTick(() => document.getElementById('item-details-modal')?.remove())"
    )

    # Action buttons based on type
    action_buttons = [
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
            # Header with title and close button
            Div(
                H2(
                    Span(item.icon or "📅", cls="mr-2"),
                    item.title,
                    cls="text-2xl font-bold flex items-center",
                ),
                Button(
                    UkIcon("x", cls="w-6 h-6"),
                    cls=(
                        ButtonT.ghost,
                        ButtonT.sm,
                        "text-muted-foreground hover:text-muted-foreground",
                    ),
                    **{"x-on:click": close_expr},  # fasthtml dynamic-attr splat
                ),
                cls="flex justify-between items-start mb-4",
            ),
            # Type and priority
            Div(type_badge, priority_stars, cls="flex items-center space-x-4 mb-4"),
            # Schedule
            Div(
                P("Schedule", cls="text-sm font-semibold text-muted-foreground mb-2"),
                P(schedule_text, cls="text-sm text-muted-foreground"),
                recurrence_info,
                cls="bg-muted p-4 rounded-lg mb-4",
            ),
            # Description
            description_section,
            # Event info
            event_info,
            # Habit info
            habit_info,
            # Tags
            tags_section,
            # Actions
            Div(*action_buttons, cls="flex pt-4 border-t"),
            show="open",
            close=close_expr,
            max_width="max-w-2xl",
            scrollable=True,
        ),
        x_data="{ open: true }",
        id="item-details-modal",
    )
