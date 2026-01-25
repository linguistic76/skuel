"""
Events Three-View Components
============================

Three-view event management interface with Calendar, List, and Create views.
Events is calendar-first (Calendar is the primary/default view).

Usage:
    from components.events_views import EventsViewComponents

    # Main tabs (calendar-first)
    tabs = EventsViewComponents.render_view_tabs("calendar")

    # Individual views
    calendar_view = EventsViewComponents.render_calendar_view(events, today, "month")
    list_view = EventsViewComponents.render_list_view(events, filters, stats)
    create_view = EventsViewComponents.render_create_view()
"""

from datetime import date, timedelta
from typing import Any

from fasthtml.common import (
    H2,
    H3,
    Button,
    Div,
    Form,
    Input,
    Label,
    Option,
    P,
    Select,
    Span,
    Textarea,
)

from components.activity_views_base import (
    ActivityCalendarNav,
    ActivityViewSwitcher,
    ActivityViewTabs,
)
from components.calendar_components import (
    create_day_timeline,
    create_month_grid,
    create_reschedule_form,
    create_week_grid,
)
from components.calendar_converters import event_to_calendar_item
from core.models.event.calendar_models import (
    CalendarData,
    CalendarView,
)
from core.models.event.event import Event
from core.utils.logging import get_logger

logger = get_logger("skuel.components.events_views")


class EventsViewComponents:
    """
    Three-view event management interface (Calendar-first).

    Views:
    - Calendar: Month/Week/Day views (PRIMARY)
    - List: Event list with filters
    - Create: Event creation form
    """

    # ========================================================================
    # MAIN TAB NAVIGATION (Calendar-First)
    # ========================================================================

    @staticmethod
    def render_view_tabs(active_view: str = "calendar") -> Div:
        """
        Render the main view tabs (Calendar, List, Create).
        Calendar is first/default for events.

        Args:
            active_view: Currently active view ("calendar", "list", "create")

        Returns:
            Div containing the tab navigation
        """
        return ActivityViewTabs.calendar_list_create("events", active_view)

    # ========================================================================
    # CALENDAR VIEW (PRIMARY)
    # ========================================================================

    @staticmethod
    def render_calendar_view(
        events: list[Any],
        current_date: date | None = None,
        calendar_view: str = "month",
    ) -> Div:
        """
        Render the calendar view with Month/Week/Day sub-views.

        Args:
            events: List of events to display
            current_date: Current date for calendar (defaults to today)
            calendar_view: Which view to show ("month", "week", "day")

        Returns:
            Div containing the calendar view
        """
        current_date = current_date or date.today()

        # Convert events to CalendarItems
        calendar_items = []
        for event in events:
            try:
                calendar_items.append(event_to_calendar_item(event))
            except Exception as e:
                logger.warning(f"Failed to convert event to calendar item: {e}")
                continue

        # Calculate date range based on view
        if calendar_view == "day":
            start_date = current_date
            end_date = current_date
            view_type = CalendarView.DAY
        elif calendar_view == "week":
            days_since_monday = current_date.weekday()
            start_date = current_date - timedelta(days=days_since_monday)
            end_date = start_date + timedelta(days=6)
            view_type = CalendarView.WEEK
        else:  # month
            start_date = current_date.replace(day=1)
            if current_date.month == 12:
                end_date = current_date.replace(
                    year=current_date.year + 1, month=1, day=1
                ) - timedelta(days=1)
            else:
                end_date = current_date.replace(month=current_date.month + 1, day=1) - timedelta(
                    days=1
                )
            view_type = CalendarView.MONTH

        # Filter items to date range
        filtered_items = [
            item for item in calendar_items if start_date <= item.start_time.date() <= end_date
        ]

        # Create CalendarData
        calendar_data = CalendarData(
            items=filtered_items,
            occurrences={},
            view=view_type,
            start_date=start_date,
            end_date=end_date,
            metadata={},
        )

        # Navigation header
        nav_header = ActivityCalendarNav.render("events", current_date, calendar_view)

        # View switcher
        view_switcher = ActivityViewSwitcher.render("events", current_date, calendar_view)

        # Render the appropriate calendar grid
        if calendar_view == "day":
            grid = create_day_timeline(calendar_data)
        elif calendar_view == "week":
            grid = create_week_grid(calendar_data)
        else:
            grid = create_month_grid(calendar_data)

        return Div(
            Div(
                nav_header,
                view_switcher,
                cls="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-4",
            ),
            Div(
                grid,
                id="calendar-grid",
            ),
            create_reschedule_form(),
            id="calendar-view",
            **{"x-data": "calendarDrag()"},
        )

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        events: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
        user_uid: str | None = None,
    ) -> Div:
        """
        Render the event list with filters.

        Args:
            events: List of events to display
            filters: Current filter values
            stats: Event statistics
            user_uid: Current user UID

        Returns:
            Div containing the list view
        """
        filters = filters or {}
        stats = stats or {}

        # Stats bar
        stats_bar = Div(
            Div(
                Span("Total: ", cls="text-gray-500"),
                Span(str(stats.get("total", 0)), cls="font-bold"),
                cls="mr-4",
            ),
            Div(
                Span("Upcoming: ", cls="text-gray-500"),
                Span(str(stats.get("upcoming", 0)), cls="font-bold text-green-600"),
                cls="mr-4",
            ),
            Div(
                Span("Today: ", cls="text-gray-500"),
                Span(str(stats.get("today", 0)), cls="font-bold text-blue-600"),
            ),
            cls="flex items-center mb-4 text-sm",
        )

        # Filter bar
        filter_bar = Div(
            Div(
                Label("Type:", cls="mr-2 text-sm"),
                Select(
                    Option("All", value="all", selected=filters.get("type") == "all"),
                    Option("Meeting", value="meeting", selected=filters.get("type") == "meeting"),
                    Option(
                        "Personal", value="personal", selected=filters.get("type") == "personal"
                    ),
                    Option("Work", value="work", selected=filters.get("type") == "work"),
                    Option("Social", value="social", selected=filters.get("type") == "social"),
                    name="filter_type",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/events/list-fragment",
                        "hx-target": "#event-list",
                        "hx-include": "[name^='filter_'], [name='sort_by']",
                    },
                ),
                cls="mr-4",
            ),
            Div(
                Label("Sort:", cls="mr-2 text-sm"),
                Select(
                    Option("Date", value="date", selected=filters.get("sort_by", "date") == "date"),
                    Option(
                        "Created",
                        value="created_at",
                        selected=filters.get("sort_by") == "created_at",
                    ),
                    name="sort_by",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/events/list-fragment",
                        "hx-target": "#event-list",
                        "hx-include": "[name^='filter_']",
                    },
                ),
            ),
            cls="flex items-center mb-4",
        )

        # Event list
        event_items = [EventsViewComponents._render_event_item(event, user_uid) for event in events]

        event_list = Div(
            *event_items
            if event_items
            else [
                P(
                    "No events found. Create one to get started!",
                    cls="text-gray-500 text-center py-8",
                )
            ],
            id="event-list",
            cls="space-y-3",
        )

        return Div(
            stats_bar,
            filter_bar,
            event_list,
            id="list-view",
        )

    @staticmethod
    def _render_event_item(event: Event, user_uid: str | None = None) -> Div:
        """Render a single event item for the list."""
        uid = event.uid
        title = event.title
        description = event.description or ""
        event_date = event.event_date
        start_time = event.start_time or ""
        end_time = event.end_time or ""
        location = event.location or ""
        event_type = event.event_type or "personal"

        event_type_str = str(event_type).lower()

        return Div(
            Div(
                # Header row
                Div(
                    H3(title, cls="text-lg font-semibold"),
                    Span(event_type_str.title(), cls="badge badge-primary badge-sm ml-2"),
                    cls="flex items-center",
                ),
                # Description
                P(
                    description[:100] + "..."
                    if description and len(description) > 100
                    else description,
                    cls="text-gray-600 text-sm mt-1",
                )
                if description
                else "",
                # Date and time
                Div(
                    Span(f"📅 {event_date}", cls="text-sm text-gray-600 mr-4")
                    if event_date
                    else "",
                    Span(f"🕐 {start_time} - {end_time}", cls="text-sm text-gray-600 mr-4")
                    if start_time
                    else "",
                    Span(f"📍 {location}", cls="text-sm text-gray-500") if location else "",
                    cls="flex flex-wrap items-center mt-2",
                ),
                # Actions
                Div(
                    Button(
                        "View",
                        cls="btn btn-xs btn-outline",
                        **{"hx-get": f"/events/{uid}", "hx-target": "body"},
                    ),
                    Button(
                        "Edit",
                        cls="btn btn-xs btn-ghost",
                        **{"hx-get": f"/events/{uid}/edit", "hx-target": "#modal"},
                    ),
                    cls="flex gap-2 mt-3",
                ),
                cls="p-4",
            ),
            id=f"event-{uid}",
            cls="card bg-base-100 shadow-sm border border-base-200 hover:shadow-md transition-shadow",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        event_types: list[str] | None = None,
        user_uid: str | None = None,
    ) -> Div:
        """
        Render the event creation form.

        Args:
            event_types: List of event type names for dropdown
            user_uid: Current user UID

        Returns:
            Div containing the creation form
        """
        event_types = event_types or [
            "meeting",
            "personal",
            "work",
            "social",
            "learning",
            "deadline",
            "reminder",
        ]

        # Left column: Core fields
        left_column = Div(
            # Title (required)
            Div(
                Label("Event Title", cls="label font-semibold"),
                Input(
                    type="text",
                    name="title",
                    placeholder="What's the event?",
                    cls="input input-bordered w-full",
                    required=True,
                    autofocus=True,
                ),
                cls="mb-4",
            ),
            # Description
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(
                    name="description",
                    placeholder="Event details...",
                    rows="3",
                    cls="textarea textarea-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Event Type
            Div(
                Label("Event Type", cls="label font-semibold"),
                Select(
                    *[Option(t.title(), value=t) for t in event_types],
                    name="event_type",
                    cls="select select-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Location
            Div(
                Label("Location", cls="label font-semibold"),
                Input(
                    type="text",
                    name="location",
                    placeholder="Where is it?",
                    cls="input input-bordered w-full",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Right column: Scheduling
        right_column = Div(
            # Event Date (required)
            Div(
                Label("Date", cls="label font-semibold"),
                Input(
                    type="date",
                    name="event_date",
                    cls="input input-bordered w-full",
                    required=True,
                ),
                cls="mb-4",
            ),
            # Start Time (required)
            Div(
                Label("Start Time", cls="label font-semibold"),
                Input(
                    type="time",
                    name="start_time",
                    cls="input input-bordered w-full",
                    required=True,
                ),
                cls="mb-4",
            ),
            # End Time (required)
            Div(
                Label("End Time", cls="label font-semibold"),
                Input(
                    type="time",
                    name="end_time",
                    cls="input input-bordered w-full",
                    required=True,
                ),
                cls="mb-4",
            ),
            # Priority
            Div(
                Label("Priority", cls="label font-semibold"),
                Select(
                    Option("P1 - Critical", value="critical"),
                    Option("P2 - High", value="high"),
                    Option("P3 - Medium", value="medium", selected=True),
                    Option("P4 - Low", value="low"),
                    name="priority",
                    cls="select select-bordered w-full",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Submit buttons
        submit_section = Div(
            Button(
                "Create Event",
                type="submit",
                cls="btn btn-primary btn-lg",
            ),
            Button(
                "Create & Add Another",
                type="submit",
                name="add_another",
                value="true",
                cls="btn btn-outline btn-lg ml-2",
            ),
            cls="flex justify-end pt-6 border-t border-base-200",
        )

        return Div(
            H2("Create New Event", cls="text-2xl font-bold mb-6"),
            Form(
                Div(
                    left_column,
                    right_column,
                    cls="flex flex-col lg:flex-row gap-8",
                ),
                submit_section,
                **{
                    "hx-post": "/events/quick-add",
                    "hx-target": "#view-content",
                    "hx-swap": "innerHTML",
                },
                cls="card bg-base-100 shadow-lg p-6",
            ),
            id="create-view",
        )


__all__ = ["EventsViewComponents", "event_to_calendar_item"]
