"""
Events Three-View Components
============================

Three-view event management interface with Calendar, List, and Create views.
Events is calendar-first (Calendar is the primary/default view).

Usage:
    from ui.events.views import EventsViewComponents

    # Main tabs (calendar-first)
    tabs = EventsViewComponents.render_view_tabs("calendar")

    # Individual views
    calendar_view = EventsViewComponents.render_calendar_view(events, today, "month")
    list_view = EventsViewComponents.render_list_view(events, filters, stats)
    create_view = EventsViewComponents.render_create_view()
"""

from datetime import date
from typing import Any

from fasthtml.common import Div, Option, P, Span

from core.models.event.event import Event
from ui.buttons import Button, ButtonT
from ui.calendar.converters import event_to_calendar_item
from ui.forms import Input, Label, Select, Textarea
from ui.layout import Size
from ui.patterns.activity_views_base import (
    ActivityCreateForm,
    ActivityListFilters,
    ActivityViewTabs,
    render_activity_calendar,
)
from ui.patterns.entity_card import EntityCard
from ui.patterns.stats_grid import StatsGrid


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
        """Render the main view tabs (Calendar, List, Create)."""
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
        """Render the calendar view with Month/Week/Day sub-views."""
        return render_activity_calendar(
            domain="events",
            entities=events,
            converter=event_to_calendar_item,
            current_date=current_date,
            calendar_view=calendar_view,
        )

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        events: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
    ) -> Div:
        """Render the event list with filters."""
        filters = filters or {}
        stats = stats or {}

        stats_bar = StatsGrid(
            [
                {"label": "Total", "value": stats.get("total", 0)},
                {"label": "Upcoming", "value": stats.get("upcoming", 0), "trend": "up" if stats.get("upcoming", 0) > 0 else "neutral"},
                {"label": "Today", "value": stats.get("today", 0)},
            ],
            cols=3,
        )

        filter_bar = ActivityListFilters.render(
            domain="events",
            status_options=[("all", "All"), ("meeting", "Meeting"), ("personal", "Personal"), ("work", "Work"), ("social", "Social")],
            sort_options=[("date", "Date"), ("created_at", "Created")],
            current_status=filters.get("type", "all"),
            current_sort=filters.get("sort_by", "date"),
            list_target="#event-list",
            filter_name="filter_type",
            filter_label="Type",
        )

        event_items = [EventsViewComponents._render_event_item(event) for event in events]

        event_list = Div(
            *event_items
            if event_items
            else [
                P(
                    "No events found. Create one to get started!",
                    cls="text-muted-foreground text-center py-8",
                )
            ],
            id="event-list",
            cls="space-y-3",
        )

        return Div(stats_bar, filter_bar, event_list, id="list-view")

    @staticmethod
    def _render_event_item(event: Event) -> Div:
        """Render a single event item for the list."""
        uid = event.uid
        event_date = event.event_date
        start_time = event.start_time or ""
        end_time = event.end_time or ""
        location = event.location or ""
        event_type = event.event_type or "personal"
        event_type_str = str(event_type).lower()

        metadata: list[Any] = []
        if event_date:
            metadata.append(Span(f"📅 {event_date}", cls="text-sm text-muted-foreground"))
        if start_time:
            metadata.append(Span(f"🕐 {start_time} - {end_time}", cls="text-sm text-muted-foreground"))
        if location:
            metadata.append(Span(f"📍 {location}", cls="text-sm text-muted-foreground"))

        actions = Div(
            Button("View", variant=ButtonT.outline, size=Size.xs, **{"hx-get": f"/events/{uid}", "hx-target": "body"}),
            Button("Edit", variant=ButtonT.ghost, size=Size.xs, **{"hx-get": f"/events/{uid}/edit", "hx-target": "#modal"}),
            cls="flex gap-2",
        )

        return EntityCard(
            title=event.title,
            description=event.description or "",
            status=event_type_str.title(),
            metadata=metadata,
            actions=actions,
            id=f"event-{uid}",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        event_types: list[str] | None = None,
    ) -> Div:
        """Render the event creation form."""
        event_types = event_types or [
            "meeting", "personal", "work", "social",
            "learning", "deadline", "reminder",
        ]

        left_column = Div(
            Div(
                Label("Event Title", cls="label font-semibold"),
                Input(type="text", name="title", placeholder="What's the event?", required=True, autofocus=True),
                cls="mb-4",
            ),
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(name="description", placeholder="Event details...", rows="3"),
                cls="mb-4",
            ),
            Div(
                Label("Event Type", cls="label font-semibold"),
                Select(*[Option(t.title(), value=t) for t in event_types], name="event_type"),
                cls="mb-4",
            ),
            Div(
                Label("Location", cls="label font-semibold"),
                Input(type="text", name="location", placeholder="Where is it?"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        right_column = Div(
            Div(
                Label("Date", cls="label font-semibold"),
                Input(type="date", name="event_date", required=True),
                cls="mb-4",
            ),
            Div(
                Label("Start Time", cls="label font-semibold"),
                Input(type="time", name="start_time", required=True),
                cls="mb-4",
            ),
            Div(
                Label("End Time", cls="label font-semibold"),
                Input(type="time", name="end_time", required=True),
                cls="mb-4",
            ),
            Div(
                Label("Priority", cls="label font-semibold"),
                Select(
                    Option("P1 - Critical", value="critical"),
                    Option("P2 - High", value="high"),
                    Option("P3 - Medium", value="medium", selected=True),
                    Option("P4 - Low", value="low"),
                    name="priority",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        return ActivityCreateForm("events", "Event", left_column, right_column)


__all__ = ["EventsViewComponents", "event_to_calendar_item"]
