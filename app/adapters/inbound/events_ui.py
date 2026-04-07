"""Events UI routes.

Provides the read-focused event list view at /events and detail view at /events/detail.
Events enter via YAML upload; this UI shows them with status controls,
scheduling info, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.connection_fetcher import EVENT_CONNECTION_CONFIG, fetch_entity_connections
from core.utils.entity_filters import filter_events
from core.utils.logging import get_logger
from ui.activities.events_views import (
    EVENT_FILTER_CONFIG,
    EventDetailView,
    EventList,
    EventStatsBar,
)
from ui.activities.filter_bar import ActivityFilterBar
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.events_service import EventsService

logger = get_logger("skuel.routes.events_ui")


def create_events_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
) -> list[Any]:
    """Register Events UI routes."""
    routes: list[Any] = []

    @rt("/events")
    async def events_page(request: Request) -> Any:
        """Main events page — lists all user events with filters."""
        user_uid = require_authenticated_user(request)

        result = await events_service.get_user_events(user_uid)
        if result.is_error:
            error = result.expect_error()
            content = Div(
                PageHeader("Events"),
                render_error_banner(error.user_message or error.message),
            )
            return await render_activity_sidebar_page(content, active="events", request=request)

        all_events = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "upcoming")
        sort_by = request.query_params.get("sort_by", "date")

        filtered = filter_events(all_events, status_filter, sort_by)

        # Batch-fetch connections
        event_uids = [e.uid for e in filtered]
        connections_map = await fetch_entity_connections(
            events_service.core.backend, EVENT_CONNECTION_CONFIG, event_uids
        )

        event_count = len(all_events)
        subtitle = f"{event_count} event{'s' if event_count != 1 else ''}"

        content = Div(
            PageHeader("Events", subtitle=subtitle),
            EventStatsBar(all_events),
            ActivityFilterBar(EVENT_FILTER_CONFIG, {"status": status_filter, "sort_by": sort_by}),
            EventList(filtered, connections_map),
        )

        return await render_activity_sidebar_page(content, active="events", request=request)

    @rt("/events/list-fragment")
    async def events_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered event list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await events_service.get_user_events(user_uid)
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        all_events = result.value

        status_filter = request.query_params.get("status", "upcoming")
        sort_by = request.query_params.get("sort_by", "date")

        filtered = filter_events(all_events, status_filter, sort_by)

        event_uids = [e.uid for e in filtered]
        connections_map = await fetch_entity_connections(
            events_service.core.backend, EVENT_CONNECTION_CONFIG, event_uids
        )

        return EventList(filtered, connections_map)

    @rt("/events/detail")
    async def event_detail_page(request: Request) -> Any:
        """Detail page for a single event with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing event UID")),
                active="events",
                request=request,
            )

        event_result = await events_service.get_event(uid)
        if event_result.is_error:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Event not found")),
                active="events",
                request=request,
            )

        event = event_result.value
        if event.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Event not found")),
                active="events",
                request=request,
            )

        # Fetch connections
        connections_map = await fetch_entity_connections(
            events_service.core.backend, EVENT_CONNECTION_CONFIG, [event.uid]
        )
        connections = connections_map.get(event.uid, [])

        content = EventDetailView(event, connections)

        return await render_activity_sidebar_page(content, active="events", request=request)

    routes.extend([events_page, events_list_fragment, event_detail_page])
    return routes
