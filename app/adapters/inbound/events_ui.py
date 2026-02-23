"""
Events UI Routes - Three-View Standalone Interface
==================================================

Three-view event management UI with Calendar, List, and Create views.
Calendar-first design (not sidebar) since events are inherently time-based.

Routes:
- GET /events - Main dashboard with three views (standalone, no drawer)
- GET /events/view/calendar - HTMX fragment for calendar view (default)
- GET /events/view/list - HTMX fragment for list view
- GET /events/view/create - HTMX fragment for create view
- GET /events/list-fragment - HTMX filtered list (for filter updates)
- POST /events/quick-add - Create event via form
"""

__version__ = "2.0"

import contextlib
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from fasthtml.common import H1, H2, Form, P
from starlette.responses import RedirectResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.route_factories import QuickAddConfig, QuickAddRouteFactory
from ui.patterns.error_banner import render_error_banner
from components.events_views import EventsViewComponents
from ui.patterns.entity_dashboard import SharedUIComponents
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.ports.facade_protocols import EventsFacadeProtocol
from core.ports.query_types import ActivityFilterSpec
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_lower
from ui.daisy_components import (
    Button,
    ButtonT,
    Card,
    Div,
    Input,
    Label,
    Option,
    Select,
    Span,
    Textarea,
)
from ui.events.layout import create_events_page
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.relationships import EntityRelationshipsSection

logger = get_logger("skuel.routes.events.ui")


# ============================================================================
# REUSABLE UI COMPONENTS
# ============================================================================


class EventUIComponents:
    """Reusable component library for events interface"""

    @staticmethod
    def render_events_content(events=None, stats=None) -> Any:
        """
        Events dashboard content (without page wrapper).

        Used by create_profile_page() for Profile Hub integration.
        """
        events = events or []
        stats = stats or {}

        # Transform stats to shared format
        stats_formatted = {
            "total": {
                "label": "Total Events",
                "value": stats.get("total_events", 0),
                "color": "blue",
            },
            "upcoming": {
                "label": "Upcoming",
                "value": stats.get("upcoming_events", 0),
                "color": "green",
            },
            "today": {
                "label": "Today",
                "value": stats.get("today_events", 0),
                "color": "orange",
            },
        }

        # Define quick actions
        quick_actions = [
            {"label": "New Event", "href": "/events?view=create", "class": "btn-primary"},
            {"label": "View Calendar", "href": "/events", "class": "btn-secondary"},
            {"label": "Upcoming", "href": "/events?view=upcoming", "class": "btn-outline"},
        ]

        # Render content
        return Div(
            H1("Events", cls="text-3xl font-bold mb-6"),
            SharedUIComponents.render_stats_cards(stats_formatted),
            SharedUIComponents.render_quick_actions(quick_actions),
            Div(
                *[EventUIComponents.render_event_card(event) for event in events],
                cls="space-y-3",
            )
            if events
            else P(
                "No events yet. Create one to get started!", cls="text-gray-500 text-center py-8"
            ),
        )

    @staticmethod
    def render_event_card(event) -> Any:
        """Individual event card component"""
        # Extract data from either dict or dataclass
        if isinstance(event, dict):
            title = event.get("title", "Untitled Event")
            description = event.get("description", "")
            start_time = event.get("start_time", "")
            end_time = event.get("end_time", "")
            location = event.get("location", "")
            status = event.get("status", "scheduled")
        else:
            title = event.title
            description = getattr(event, "description", "")
            start_time = getattr(event, "start_time", "")
            end_time = getattr(event, "end_time", "")
            location = getattr(event, "location", "")
            status = getattr(event, "status", "scheduled")

        return Card(
            Div(
                Div(
                    Span(title, cls="font-semibold text-lg"),
                    Span(str(status).title(), cls="badge badge-primary ml-2"),
                    cls="flex items-center mb-2",
                ),
                P(
                    description[:100] + "..." if len(description) > 100 else description,
                    cls="text-gray-600 mb-2",
                )
                if description
                else "",
                Div(
                    Span(f"Start: {start_time}", cls="text-sm text-gray-500 mr-4")
                    if start_time
                    else "",
                    Span(f"End: {end_time}", cls="text-sm text-gray-500 mr-4") if end_time else "",
                    Span(f"Location: {location}", cls="text-sm text-gray-500") if location else "",
                    cls="flex flex-wrap",
                ),
                cls="p-4",
            ),
            cls="border border-gray-200 rounded-lg hover:shadow-md transition-shadow",
        )


# ============================================================================
# UI ROUTES
# ============================================================================


def create_events_ui_routes(_app, rt, events_service: EventsFacadeProtocol):
    """
    Create three-view event UI routes (standalone, calendar-first).

    Views:
    - Calendar: Month/Week/Day views (DEFAULT for events)
    - List: Sortable, filterable event list
    - Create: Event creation form

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        events_service: Events service
    """

    logger.info("Registering three-view event routes (standalone, calendar-first)")

    # ========================================================================
    # QUERY PARAM TYPES
    # ========================================================================

    @dataclass
    class Filters:
        """Typed filters for event list queries."""

        status: str
        sort_by: str

    @dataclass
    class CalendarParams:
        """Typed params for calendar view."""

        calendar_view: str
        current_date: date

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def parse_filters(request) -> Filters:
        """Extract filter parameters from request query params."""
        return Filters(
            status=request.query_params.get("filter_status", "scheduled"),
            sort_by=request.query_params.get("sort_by", "start_time"),
        )

    def parse_calendar_params(request) -> CalendarParams:
        """Extract calendar view parameters from request query params."""
        calendar_view = request.query_params.get("calendar_view", "month")
        date_str = request.query_params.get("date", "")

        # Parse date or use today
        try:
            current_date = date.fromisoformat(date_str) if date_str else date.today()
        except ValueError:
            current_date = date.today()

        return CalendarParams(calendar_view=calendar_view, current_date=current_date)

    # Error rendering moved to components.error_components.ErrorComponents

    # ========================================================================
    # ERROR HANDLING
    # ========================================================================

    def render_safe_error_response(
        user_message: str,
        error_context: Any,
        logger_instance,
        log_extra: dict[str, Any],
        status_code: int = 500,
    ) -> Response:
        """
        Return sanitized error to client, log detailed error server-side.

        Args:
            user_message: Safe message for client (e.g., "Failed to update event")
            error_context: Detailed error (logged but NOT sent to client)
            logger_instance: Logger instance for structured logging
            log_extra: Additional context for logs (user_uid, entity_uid, etc.)
            status_code: HTTP status code

        Returns:
            Response with sanitized message
        """
        # Log detailed error server-side
        logger_instance.error(
            user_message,
            extra={
                **log_extra,
                "error_type": type(error_context).__name__,
                "error_detail": str(error_context),
            },
        )

        # Return safe message to client
        return Response(user_message, status_code=status_code)

    # ========================================================================
    # DATA FETCHING HELPERS
    # ========================================================================

    async def get_all_events(user_uid: str) -> Result[list[Any]]:
        """Get all events for user."""
        try:
            if events_service:
                result = await events_service.get_user_events(user_uid)
                if result.is_error:
                    logger.warning(f"Failed to fetch events: {result.error}")
                    return result  # Propagate the error
                return Result.ok(result.value or [])
            return Result.ok([])
        except Exception as e:
            logger.error(
                "Error fetching all events",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch events: {e}"))

    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)
    # ========================================================================

    def validate_event_form_data(form_data: dict[str, Any]) -> Result[None]:
        """Validate event form data early."""
        title = form_data.get("title", "").strip()
        if not title:
            return Result.fail(Errors.validation("Event title is required"))
        if len(title) > 200:
            return Result.fail(Errors.validation("Event title must be 200 characters or less"))
        return Result.ok(None)

    def get_status_value(event: Any) -> str:
        """Helper to get status value (handles both enum and string)."""
        status = getattr(event, "status", None)
        if status is None:
            return "scheduled"
        if isinstance(status, Enum):
            return str(status.value).lower()
        return str(status).lower()

    def compute_event_stats(events: list[Any]) -> dict[str, int]:
        """Calculate event statistics."""
        today = date.today()
        return {
            "total": len(events),
            "scheduled": sum(1 for e in events if get_status_value(e) == "scheduled"),
            "today": sum(
                1
                for e in events
                if getattr(e, "start_time", None)
                and getattr(e.start_time, "date", lambda: None)() == today
            ),
        }

    def apply_event_filters(events: list[Any], status_filter: str = "scheduled") -> list[Any]:
        """Apply filter criteria to event list."""
        if status_filter == "scheduled":
            return [e for e in events if get_status_value(e) == "scheduled"]
        elif status_filter == "completed":
            return [e for e in events if get_status_value(e) == "completed"]
        elif status_filter == "cancelled":
            return [e for e in events if get_status_value(e) == "cancelled"]
        return events

    def apply_event_sort(events: list[Any], sort_by: str = "start_time") -> list[Any]:
        """Sort events by specified field."""

        def get_sort_datetime(event: Any) -> datetime:
            event_date = getattr(event, "event_date", None) or date.today()
            if not isinstance(event_date, date) and getattr(event_date, "year", None) is not None:
                event_date = date(event_date.year, event_date.month, event_date.day)
            start_time_val = getattr(event, "start_time", None)
            if start_time_val is None:
                return datetime.combine(event_date, time(0, 0))
            if (
                not isinstance(start_time_val, time)
                and getattr(start_time_val, "hour", None) is not None
            ):
                start_time_val = time(
                    start_time_val.hour,
                    start_time_val.minute,
                    getattr(start_time_val, "second", 0) or 0,
                )
            elif isinstance(start_time_val, str):
                try:
                    start_time_val = datetime.strptime(start_time_val, "%H:%M:%S").time()
                except ValueError:
                    start_time_val = time(0, 0)
            return datetime.combine(event_date, start_time_val)

        if sort_by == "start_time":
            return sorted(events, key=get_sort_datetime)
        elif sort_by == "title":
            return sorted(events, key=get_title_lower)
        elif sort_by == "created_at":
            return sorted(events, key=get_created_at_attr, reverse=True)
        return sorted(events, key=get_sort_datetime)

    async def get_filtered_events(
        user_uid: str,
        status_filter: str = "scheduled",
        sort_by: str = "start_time",
    ) -> Result[tuple[list[Any], dict[str, int]]]:
        """Get filtered and sorted events with stats.

        Orchestrates: fetch (I/O) → stats → filter → sort.
        Pure computation delegated to testable helper functions.
        """
        try:
            # I/O: Fetch all events
            events_result = await get_all_events(user_uid)
            if events_result.is_error:
                return Result.fail(events_result.expect_error())

            events = events_result.value

            # Computation: Calculate stats BEFORE filtering
            stats = compute_event_stats(events)

            # Computation: Apply filters
            filtered_events = apply_event_filters(events, status_filter)

            # Computation: Apply sort
            sorted_events = apply_event_sort(filtered_events, sort_by)

            return Result.ok((sorted_events, stats))
        except Exception as e:
            logger.error(
                "Error filtering events",
                extra={
                    "user_uid": user_uid,
                    "status_filter": status_filter,
                    "sort_by": sort_by,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to filter events: {e}"))

    async def get_event_types() -> Result[list[str]]:
        """Get available event types."""
        return Result.ok(
            ["meeting", "appointment", "deadline", "reminder", "social", "personal", "work"]
        )

    # ========================================================================
    # MAIN DASHBOARD (Standalone Three-View, Calendar First)
    # ========================================================================

    @rt("/events")
    async def events_dashboard(request) -> Any:
        """Main events dashboard with three views (standalone, calendar-first)."""
        user_uid = require_authenticated_user(request)

        # Get view parameter (default to calendar for events)
        view = request.query_params.get("view", "calendar")

        # Parse using helpers
        filters = parse_filters(request)
        calendar_params = parse_calendar_params(request)

        # Get data with Result[T]
        filtered_result = await get_filtered_events(user_uid, filters.status, filters.sort_by)
        event_types_result = await get_event_types()

        # CHECK FOR ERRORS
        if filtered_result.is_error:
            error_content = Div(
                EventsViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load events"),
                cls="p-4 lg:p-8 max-w-7xl mx-auto",
            )
            return await create_events_page(error_content, request=request)

        if event_types_result.is_error:
            error_content = Div(
                EventsViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load event types"),
                cls="p-4 lg:p-8 max-w-7xl mx-auto",
            )
            return await create_events_page(error_content, request=request)

        # Extract values
        events, stats = filtered_result.value
        event_types = event_types_result.value

        # Render the appropriate view content
        if view == "list":
            view_content = EventsViewComponents.render_list_view(
                events=events,
                filters={
                    "status": filters.status,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
                user_uid=user_uid,
            )
        elif view == "create":
            view_content = EventsViewComponents.render_create_view(
                event_types=event_types,
                user_uid=user_uid,
            )
        else:  # calendar (default for events)
            all_events_result = await get_all_events(user_uid)

            # Check for errors
            if all_events_result.is_error:
                view_content = render_error_banner(
                    f"Failed to load calendar: {all_events_result.error}"
                )
            else:
                view_content = EventsViewComponents.render_calendar_view(
                    events=all_events_result.value,
                    current_date=calendar_params.current_date,
                    calendar_view=calendar_params.calendar_view,
                )

        # Build page with tabs + view content
        page_content = Div(
            EventsViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content", role="tabpanel"),
            cls="p-4 lg:p-8 max-w-7xl mx-auto",
        )

        return await create_events_page(page_content, request=request)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/events/view/calendar")
    async def events_view_calendar(request) -> Any:
        """HTMX fragment for calendar view (default for events)."""
        user_uid = require_authenticated_user(request)
        calendar_params = parse_calendar_params(request)

        events_result = await get_all_events(user_uid)

        # Handle errors
        if events_result.is_error:
            return render_error_banner("Failed to load calendar")

        return EventsViewComponents.render_calendar_view(
            events=events_result.value,
            current_date=calendar_params.current_date,
            calendar_view=calendar_params.calendar_view,
        )

    @rt("/events/view/list")
    async def events_view_list(request) -> Any:
        """HTMX fragment for list view."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await get_filtered_events(user_uid, filters.status, filters.sort_by)

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load events")

        events, stats = filtered_result.value

        filters_dict: ActivityFilterSpec = {"status": filters.status, "sort_by": filters.sort_by}
        return EventsViewComponents.render_list_view(
            events=events,
            filters=filters_dict,
            stats=stats,
            user_uid=user_uid,
        )

    @rt("/events/view/create")
    async def events_view_create(request) -> Any:
        """HTMX fragment for create view."""
        user_uid = require_authenticated_user(request)
        event_types_result = await get_event_types()

        # Handle errors
        if event_types_result.is_error:
            return render_error_banner("Failed to load event types")

        return EventsViewComponents.render_create_view(
            event_types=event_types_result.value,
            user_uid=user_uid,
        )

    # ========================================================================
    # LIST FRAGMENT (for filter updates)
    # ========================================================================

    @rt("/events/list-fragment")
    async def events_list_fragment(request) -> Any:
        """Return filtered event list for HTMX updates."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await get_filtered_events(user_uid, filters.status, filters.sort_by)

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load events")

        events, _stats = filtered_result.value

        # Return just the event items
        event_items = [EventsViewComponents._render_event_item(event, user_uid) for event in events]

        return Div(
            *event_items
            if event_items
            else [P("No events found.", cls="text-gray-500 text-center py-8")],
            id="event-list",
            cls="space-y-3",
        )

    # ========================================================================
    # QUICK ADD (via QuickAddRouteFactory)
    # ========================================================================

    async def create_event_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """
        Domain-specific event creation logic.

        Handles form parsing, DTO building, model conversion, and service call.
        """
        # Extract form data
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip() or None
        event_type = form_data.get("event_type", "meeting")
        location = form_data.get("location", "").strip() or None
        event_date_str = form_data.get("event_date", "")
        start_time_str = form_data.get("start_time", "")
        end_time_str = form_data.get("end_time", "")

        logger.info(
            f"Quick add event: title={title}, date={event_date_str}, "
            f"start={start_time_str}, end={end_time_str}"
        )

        # Parse event date
        event_date_val = None
        if event_date_str:
            try:
                event_date_val = date.fromisoformat(event_date_str)
            except ValueError:
                logger.warning(f"Could not parse event_date: {event_date_str}")

        # Parse times
        start_time_val = None
        end_time_val = None
        if start_time_str:
            try:
                start_time_val = time.fromisoformat(start_time_str)
            except ValueError:
                logger.warning(f"Could not parse start_time: {start_time_str}")
        if end_time_str:
            try:
                end_time_val = time.fromisoformat(end_time_str)
            except ValueError:
                logger.warning(f"Could not parse end_time: {end_time_str}")

        # Build DTO and convert to domain model
        event_dto = EventDTO.create_event(
            user_uid=user_uid,
            title=title,
            event_date=event_date_val or date.today(),
            start_time=start_time_val or time(9, 0),
            end_time=end_time_val or time(10, 0),
            event_type=event_type.upper(),
            description=description,
            location=location,
        )

        event = Event.from_dto(event_dto)
        return await events_service.core.create(event)

    async def render_event_success_view(_user_uid: str) -> Any:
        """Render calendar view after successful event creation."""
        events = await get_all_events(_user_uid)
        return EventsViewComponents.render_calendar_view(
            events=events,
            current_date=date.today(),
            calendar_view="month",
        )

    async def render_event_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        event_types = await get_event_types()
        return EventsViewComponents.render_create_view(event_types=event_types, user_uid=user_uid)

    # Register quick-add route via factory
    events_quick_add_config = QuickAddConfig(
        domain_name="events",
        required_field="title",
        create_entity=create_event_from_form,
        render_success_view=render_event_success_view,
        render_add_another_view=render_event_add_another_view,
    )
    QuickAddRouteFactory.register_route(rt, events_quick_add_config)

    # ========================================================================
    # EDIT EVENT
    # ========================================================================

    @rt("/events/{uid}/edit")
    async def edit_event(request, uid: str) -> Any:
        """Return edit form modal for an event."""
        user_uid = require_authenticated_user(request)

        # Get the event with ownership verification
        if not events_service or not events_service.core:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this event
        result = await events_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            return Response("Event not found", status_code=404)

        event = result.value
        event_types_result = await get_event_types()
        event_types = [] if event_types_result.is_error else event_types_result.value

        # Extract current values
        title = getattr(event, "title", "")
        description = getattr(event, "description", "") or ""
        event_type = str(getattr(event, "event_type", "meeting")).lower()
        location = getattr(event, "location", "") or ""
        event_date_val = getattr(event, "event_date", None)
        start_time_val = getattr(event, "start_time", None)
        end_time_val = getattr(event, "end_time", None)

        # Convert Neo4j Time to Python time if needed
        def to_python_time(t):
            if t is None:
                return None
            if isinstance(t, time):
                return t
            if getattr(t, "hour", None) is not None:  # Neo4j Time
                return time(t.hour, t.minute, getattr(t, "second", 0) or 0)
            return None

        # Convert Neo4j Date to Python date if needed
        def to_python_date(d):
            if d is None:
                return None
            if isinstance(d, date):
                return d
            if getattr(d, "year", None) is not None:  # Neo4j Date
                return date(d.year, d.month, d.day)
            return None

        start_time_py = to_python_time(start_time_val)
        end_time_py = to_python_time(end_time_val)
        event_date_py = to_python_date(event_date_val)

        # Format dates/times for input fields
        event_date_str = event_date_py.isoformat() if event_date_py else ""
        start_time_str = start_time_py.strftime("%H:%M") if start_time_py else ""
        end_time_str = end_time_py.strftime("%H:%M") if end_time_py else ""

        # Build edit form modal
        return Div(
            Div(
                H2("Edit Event", cls="text-xl font-bold mb-4"),
                Form(
                    # Title
                    Div(
                        Label("Event Title", cls="label font-semibold"),
                        Input(
                            type="text",
                            name="title",
                            value=title,
                            cls="input input-bordered w-full",
                            required=True,
                        ),
                        cls="mb-4",
                    ),
                    # Description
                    Div(
                        Label("Description", cls="label font-semibold"),
                        Textarea(
                            description,
                            name="description",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Event Type
                    Div(
                        Label("Event Type", cls="label font-semibold"),
                        Select(
                            *[
                                Option(t.title(), value=t, selected=(t == event_type))
                                for t in event_types
                            ],
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
                            value=location,
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Date
                    Div(
                        Label("Date", cls="label font-semibold"),
                        Input(
                            type="date",
                            name="event_date",
                            value=event_date_str,
                            cls="input input-bordered w-full",
                            required=True,
                        ),
                        cls="mb-4",
                    ),
                    # Start Time
                    Div(
                        Label("Start Time", cls="label font-semibold"),
                        Input(
                            type="time",
                            name="start_time",
                            value=start_time_str,
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # End Time
                    Div(
                        Label("End Time", cls="label font-semibold"),
                        Input(
                            type="time",
                            name="end_time",
                            value=end_time_str,
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Submit buttons
                    Div(
                        Button(
                            "Save Changes",
                            type="submit",
                            variant=ButtonT.primary,
                        ),
                        Button(
                            "Cancel",
                            type="button",
                            variant=ButtonT.ghost,
                            cls="ml-2",
                            **{
                                "hx-get": "/events",
                                "hx-target": "body",
                                "hx-swap": "innerHTML",
                            },
                        ),
                        cls="flex justify-end pt-4",
                    ),
                    **{
                        "hx-post": f"/events/{uid}/update",
                        "hx-target": "body",
                        "hx-swap": "innerHTML",
                    },
                ),
                cls="modal-box",
            ),
            Div(
                cls="modal-backdrop",
                **{
                    "hx-get": "/events",
                    "hx-target": "body",
                    "hx-swap": "innerHTML",
                },
            ),
            id="modal",
            cls="modal modal-open",
        )

    @rt("/events/{uid}/update", methods=["POST"])
    async def update_event(request, uid: str) -> Any:
        """Update an event via form submission."""
        user_uid = require_authenticated_user(request)

        if not events_service or not events_service.core:
            return Response("Service unavailable", status_code=503)

        # Ownership verification before mutation
        ownership_result = await events_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Response("Event not found", status_code=404)

        form = await request.form()

        # Extract and parse form data
        title = form.get("title", "").strip()
        if not title:
            return Response("Title is required", status_code=400)

        description = form.get("description", "").strip() or None
        event_type = form.get("event_type", "meeting")
        location = form.get("location", "").strip() or None
        event_date_str = form.get("event_date", "")
        start_time_str = form.get("start_time", "")
        end_time_str = form.get("end_time", "")

        # Parse event date
        event_date_val = None
        if event_date_str:
            with contextlib.suppress(ValueError):
                event_date_val = date.fromisoformat(event_date_str)

        # Parse times
        start_time_val = None
        end_time_val = None
        if start_time_str:
            with contextlib.suppress(ValueError):
                start_time_val = time.fromisoformat(start_time_str)
        if end_time_str:
            with contextlib.suppress(ValueError):
                end_time_val = time.fromisoformat(end_time_str)

        # Update event
        update_data = {
            "title": title,
            "description": description,
            "event_type": event_type,
            "location": location,
            "event_date": event_date_val,
            "start_time": start_time_val,
            "end_time": end_time_val,
        }

        try:
            update_result = await events_service.update(uid, update_data)

            if update_result.is_error:
                return render_safe_error_response(
                    user_message="Failed to update event",
                    error_context=update_result.error,
                    logger_instance=logger,
                    log_extra={"event_uid": uid, "user_uid": user_uid},
                    status_code=500,
                )

            logger.info(f"Event updated: {uid}")

            # Redirect to events page (HTMX will follow the redirect)
            return RedirectResponse("/events", status_code=303)

        except Exception as e:
            logger.error(f"Error updating event: {e}")
            return Response("Error updating event", status_code=500)

    # ========================================================================
    # EVENT DETAIL PAGE (Phase 5)
    # ========================================================================

    @rt("/events/{uid}")
    async def event_detail_view(request: Any, uid: str) -> Any:
        """
        Event detail view with full context and relationships.

        Phase 5: Shows event details plus lateral relationships visualization.
        """
        user_uid = require_authenticated_user(request)

        # Fetch event with ownership verification
        result = await events_service.get_for_user(uid, user_uid)

        if result.is_error:
            logger.error(f"Failed to get event {uid}: {result.error}")
            return await BasePage(
                content=Card(
                    H2("Event Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find event: {uid}", cls="text-base-content/70"),
                    Button(
                        "← Back to Events",
                        **{"hx-get": "/events", "hx-target": "body"},
                        variant=ButtonT.primary,
                        cls="mt-4",
                    ),
                    cls="p-6",
                ),
                title="Event Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="events",
            )

        event = result.value

        # Render detail page
        content = Div(
            # Header Card
            Card(
                H1(f"📅 {event.title}", cls="text-2xl font-bold mb-2"),
                P(event.description or "No description provided", cls="text-base-content/70 mb-4"),
                # Status and Type badges
                Div(
                    Span(f"Status: {event.status.value}", cls="badge badge-info mr-2"),
                    Span(
                        f"Type: {event.event_type if event.event_type else 'Not set'}",
                        cls="badge badge-success mr-2",
                    ),
                    Span(
                        f"Priority: {event.priority if event.priority else 'Not set'}",
                        cls="badge badge-warning",
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-6 mb-4",
            ),
            # Details Card
            Card(
                H2("📋 Event Details", cls="text-xl font-semibold mb-4"),
                Div(
                    # Start and End Time
                    Div(
                        P("When:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                        P(
                            f"{event.start_time} to {event.end_time}"
                            if event.start_time and event.end_time
                            else "Time not set",
                            cls="text-base-content mb-3",
                        ),
                        cls="mb-4",
                    ),
                    # Location
                    (
                        Div(
                            P("Location:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            P(event.location or "Not specified", cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if event.location
                        else Div()
                    ),
                    # Created Date
                    Div(
                        P("Created:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                        P(str(event.created_at)[:10], cls="text-base-content/60 text-sm"),
                    ),
                    cls="space-y-2",
                ),
                cls="p-6 mb-4",
            ),
            # Actions Card
            Card(
                Div(
                    Button(
                        "← Back to Events",
                        **{"hx-get": "/events", "hx-target": "body"},
                        variant=ButtonT.ghost,
                        cls="mr-2",
                    ),
                    Button(
                        "✏️ Edit Event",
                        **{"hx-get": f"/events/{event.uid}/edit", "hx-target": "#modal"},
                        variant=ButtonT.primary,
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Phase 5: Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=event.uid,
                entity_type="events",
            ),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return await BasePage(
            content=content,
            title=event.title,
            page_type=PageType.STANDARD,
            request=request,
            active_page="events",
        )

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["EventUIComponents", "create_events_ui_routes"]
