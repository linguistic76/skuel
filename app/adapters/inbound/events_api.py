"""
Events API - Status, Analytics, and Domain-Specific Routes
============================================================

CRUD, Query, and Intelligence factories are now registered via config in
events_routes.py.  This file contains only factories and routes that require
runtime closures or domain-specific handler logic:
- StatusRouteFactory (start/complete/cancel transitions)
- AnalyticsRouteFactory (custom async handlers)
- Manual domain routes (calendar, conflicts, recurrence, attendees)
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.boundary import boundary_handler
from core.auth import require_ownership_query
from core.infrastructure.routes import (
    StatusRouteFactory,
    StatusTransition,
)
from core.infrastructure.routes.analytics_route_factory import AnalyticsRouteFactory
from core.models.enums import ContentScope
from core.models.event.event_request import (
    EventStatusUpdateRequest,
    GetRecurringEventsRequest,
)
from core.services.protocols.facade_protocols import EventsFacadeProtocol
from core.utils.result_simplified import Result


def create_events_api_routes(
    app: Any,
    rt: Any,
    events_service: EventsFacadeProtocol,
    **_kwargs: Any,
) -> list[Any]:
    """
    Create event API routes that require runtime closures or domain-specific logic.

    CRUD, Query, and Intelligence routes are registered by register_domain_routes
    before this function is called (see events_routes.py → EVENTS_CONFIG).

    Args:
        app: FastHTML application instance
        rt: Route decorator
        events_service: EventsService instance (primary service)
        **_kwargs: Absorbs related services passed by register_domain_routes
    """

    # Service getter for ownership decorator (SKUEL012: named function, not lambda)
    def get_events_service():
        return events_service

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================
    # SECURITY: All UID-based routes verify user owns the event before operating

    # Event Status Operations
    # -----------------------

    @rt("/api/events/status")
    @require_ownership_query(get_events_service)
    @boundary_handler()
    async def update_event_status_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Update event status (requires ownership)."""
        body = await request.json()
        typed_request = EventStatusUpdateRequest(
            event_uid=entity.uid,
            status=body.get("status"),
            notes=body.get("notes"),
            cancellation_reason=body.get("cancellation_reason"),
        )
        return await events_service.update_event_status(typed_request)

    # ========================================================================
    # STATUS ROUTES (Factory-Generated)
    # ========================================================================
    # BEFORE: 3 manual routes (~44 lines) with manual ownership verification
    # AFTER: 1 factory config with AUTOMATIC ownership verification

    status_factory = StatusRouteFactory(
        service=events_service,
        domain_name="events",
        transitions={
            "start": StatusTransition(
                target_status="in_progress",
                method_name="start_event",
            ),
            "complete": StatusTransition(
                target_status="completed",
                method_name="complete_event",
            ),
            "cancel": StatusTransition(
                target_status="cancelled",
                requires_body=True,
                body_fields=["reason"],
                method_name="cancel_event",
            ),
        },
        scope=ContentScope.USER_OWNED,
    )
    status_factory.register_routes(app, rt)

    # Calendar Operations
    # -------------------

    @rt("/api/events/calendar")
    @boundary_handler()
    async def get_calendar_events_route(request: Request) -> Result[Any]:
        """Get events for calendar view."""
        params = dict(request.query_params)
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        view = params.get("view", "month")

        return await events_service.get_calendar_events(start_date, end_date, view)

    @rt("/api/events/conflicts")
    @require_ownership_query(get_events_service)
    @boundary_handler()
    async def check_conflicts_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Check for scheduling conflicts (requires ownership)."""
        # Use facade protocol signature: (start_time, end_time, user_uid)
        return await events_service.check_conflicts(
            start_time=entity.start_time,
            end_time=entity.end_time,
            user_uid=user_uid,
        )

    # Search and Analytics
    # --------------------

    @rt("/api/events/search")
    @boundary_handler()
    async def search_events_route(request: Request) -> Result[Any]:
        """Search events."""
        params = dict(request.query_params)
        query = params.get("q", "")
        limit = int(params.get("limit", 50))

        return await events_service.search_events(query, limit)

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    # Analytics handler functions
    async def handle_time_usage_analytics(service, params):
        """Handle time usage analytics request."""
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        period = params.get("period", "week")
        return await service.get_time_usage_analytics(start_date, end_date, period)

    async def handle_scheduling_patterns(service, params):
        """Handle scheduling patterns analytics request."""
        time_range = params.get("time_range", "30d")
        return await service.get_scheduling_patterns(time_range)

    async def handle_calendar_insights(service, params):
        """Handle calendar insights analytics request."""
        time_range = params.get("time_range", "30d")
        return await service.get_calendar_insights(time_range)

    # Create analytics factory
    analytics_factory = AnalyticsRouteFactory(
        service=events_service,
        domain_name="events",
        analytics_config={
            "time_usage": {
                "path": "/api/events/analytics/time-usage",
                "handler": handle_time_usage_analytics,
                "description": "Get time usage analytics for events",
                "methods": ["GET"],
            },
            "patterns": {
                "path": "/api/events/analytics/patterns",
                "handler": handle_scheduling_patterns,
                "description": "Get scheduling pattern analytics",
                "methods": ["GET"],
            },
            "calendar_insights": {
                "path": "/api/events/intelligence/insights",
                "handler": handle_calendar_insights,
                "description": "Get AI-powered calendar insights",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

    # Recurrence Operations
    # ---------------------

    @rt("/api/events/recurrence")
    @require_ownership_query(get_events_service)
    @boundary_handler()
    async def create_recurring_instances_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Create recurring event instances (requires ownership)."""
        body = await request.json()
        # Use facade protocol signature: (event_uid, recurrence_data)
        recurrence_data = {
            "count": body.get("count", 10),
        }
        return await events_service.create_recurring_instances(
            event_uid=entity.uid,
            recurrence_data=recurrence_data,
        )

    @rt("/api/events/recurring")
    @boundary_handler()
    async def get_recurring_events_route(request: Request) -> Result[Any]:
        """Get recurring events using typed request object."""
        params = dict(request.query_params)
        typed_request = GetRecurringEventsRequest(
            user_uid=params.get("user_uid", ""),
            limit=int(params.get("limit", "100")),
        )
        return await events_service.get_recurring_events(typed_request)

    # Attendee Operations
    # -------------------
    # SECURITY: All routes verify user owns the event before operating

    @rt("/api/events/attendees", methods=["POST"])
    @require_ownership_query(get_events_service)
    @boundary_handler()
    async def add_attendee_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Add attendee to event (requires ownership)."""
        body = await request.json()
        # Use facade protocol signature: (event_uid, attendee_data)
        attendee_data = {
            "user_uid": body.get("attendee_uid", body.get("user_uid", "")),
            "role": body.get("role", "attendee"),
            "send_notification": body.get("send_notification", True),
        }
        return await events_service.add_attendee(event_uid=entity.uid, attendee_data=attendee_data)

    @rt("/api/events/attendees", methods=["DELETE"])
    @require_ownership_query(get_events_service)
    @boundary_handler()
    async def remove_attendee_route(
        request: Request, user_uid: str, entity: Any, attendee_uid: str
    ) -> Result[Any]:
        """Remove attendee from event (requires ownership)."""
        # Use facade protocol signature: (event_uid, attendee_uid)
        return await events_service.remove_attendee(
            event_uid=entity.uid,
            attendee_uid=attendee_uid,
        )

    @rt("/api/events/attendees", methods=["GET"])
    @require_ownership_query(get_events_service)
    @boundary_handler()
    async def get_event_attendees_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get event attendees (requires ownership)."""
        return await events_service.get_event_attendees(entity.uid)

    return []  # Routes registered via @rt() decorators (no objects returned)
