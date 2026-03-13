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

from datetime import date, timedelta
from typing import Any

from fasthtml.common import H2, H3, H4, A, Div, Form, Option, P, Span

from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
)
from ui.buttons import Button
from ui.forms import Input, Label, Select
from ui.cards import Card


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

        weeks.append(Div(*week_cells, cls="grid grid-cols-7 gap-0"))

        # Stop if we've gone past the end of the month
        if (
            current_date.month != calendar_data.start_date.month
            and current_date > calendar_data.end_date
        ):
            break

    return Div(
        # Day headers
        Div(
            *[
                Div(day, cls="text-center font-semibold py-2 border-b")
                for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            ],
            cls="grid grid-cols-7 gap-0 mb-0",
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
            **{
                "hx-get": f"/events/calendar/item-details/{item.uid}",
                "hx-target": "body",
                "hx-swap": "beforeend",
            },
        )
        for item in items
    ]

    # Build occurrence indicators
    occurrence_elements = []
    for occ in occurrences:
        icon = "✅" if occ.status == "done" else "⏭️" if occ.status == "skipped" else "❌"
        occurrence_elements.append(Span(icon, cls="text-xs mr-1", title=occ.notes or ""))

    # More indicator
    more_element = []
    if has_more:
        more_element.append(Div("+more", cls="text-xs text-muted-foreground mt-1"))

    # Today's date header with badge for visibility
    if is_today:
        date_header = Div(
            Span(str(cell_date.day), cls="text-lg font-bold text-primary"),
            Span("Today", cls="ml-2 badge badge-primary badge-sm"),
            cls="flex items-center mb-1",
        )
    else:
        date_header = Div(
            str(cell_date.day),
            cls=f"text-sm font-semibold mb-1 {'text-foreground' if is_current_month else 'text-foreground/40'}",
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
        **{
            "x-on:dragstart": f"handleDragStart($event, '{item.uid}')",
            # Use HTMX for modal loading instead of JavaScript
            "hx-get": f"/events/calendar/item-details/{item.uid}",
            "hx-target": "body",
            "hx-swap": "beforeend",
        },
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
        **{
            "x-on:dragstart": f"handleDragStart($event, '{item.uid}')",
            "hx-get": f"/events/calendar/item-details/{item.uid}",
            "hx-target": "body",
            "hx-swap": "beforeend",
        },
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
                cls="btn btn-success btn-sm",
                **{
                    "hx-post": f"/events/calendar/habit/{habit_uid}/record/done",
                    "hx-target": f"#habit-status-{habit_uid}",
                    "hx-swap": "innerHTML",
                    "hx-include": f"#{note_input_id}",
                },
            ),
            Button(
                "⏭️",
                type="button",
                cls="btn btn-warning btn-sm",
                **{
                    "hx-post": f"/events/calendar/habit/{habit_uid}/record/skipped",
                    "hx-target": f"#habit-status-{habit_uid}",
                    "hx-swap": "innerHTML",
                    "hx-include": f"#{note_input_id}",
                },
            ),
            Button(
                "❌",
                type="button",
                cls="btn btn-error btn-sm",
                **{
                    "hx-post": f"/events/calendar/habit/{habit_uid}/record/missed",
                    "hx-target": f"#habit-status-{habit_uid}",
                    "hx-swap": "innerHTML",
                    "hx-include": f"#{note_input_id}",
                },
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
    return Div(
        Div(
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
                        cls="w-full px-3 py-2 border rounded",
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
                        cls="w-full px-3 py-2 border rounded",
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
                        cls="w-full px-3 py-2 border rounded",
                        **{"x-model": "datetime"},
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
                        cls="w-full px-3 py-2 border rounded",
                    ),
                    cls="mb-4",
                ),
                # Buttons - Alpine.js for cancel
                Div(
                    Button(
                        "Cancel",
                        type="button",
                        cls="btn btn-ghost mr-2",
                        **{"x-on:click": "closeQuickAdd()"},
                    ),
                    Button(
                        "Create",
                        type="submit",
                        cls="btn btn-primary",
                    ),
                    cls="flex justify-end",
                ),
                cls="bg-background rounded-lg p-6 max-w-md w-full",
                # HTMX form submission
                **{
                    "hx-post": "/events/calendar/quick-create",
                    "hx-target": "#quick-add-status",
                    "hx-swap": "innerHTML",
                    "x-on:click.stop": "",  # Prevent click from bubbling to backdrop
                },
            ),
            cls="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50",
            # Alpine.js: click backdrop to close, x-show for visibility
            **{
                "x-show": "open",
                "x-transition": "",
                "x-on:click": "closeQuickAdd()",
            },
        ),
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
        Input(type="hidden", name="uid", **{"x-ref": "rescheduleUid"}),
        Input(type="hidden", name="new_start", **{"x-ref": "rescheduleTime"}),
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
        cls_base = "btn btn-sm"
        if view == "day":
            cls_base += " rounded-l-lg rounded-r-none"
        elif view == "month":
            cls_base += " rounded-r-lg rounded-l-none"
        else:
            cls_base += " rounded-none"

        if is_active:
            # Active view - styled span (not clickable)
            buttons.append(Span(label, cls=f"{cls_base} btn-primary cursor-default"))
        else:
            # Inactive view - use link
            buttons.append(
                A(
                    label,
                    href=url,
                    cls=f"{cls_base} btn-ghost",
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
            cls="fixed bottom-6 right-6 btn btn-success rounded-full shadow-lg",
            **{"x-on:click": "openQuickAdd()"},
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
            H2("Error", cls="text-xl font-bold text-error mb-2"),
            P(str(error_message), cls="text-muted-foreground"),
            Button(
                "Go Back",
                cls="mt-4 btn btn-primary",
                onclick="window.history.back()",
            ),
            cls="bg-background shadow-md p-6",
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
