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
from core.utils.logging import get_logger
from ui.activities.events_views import (
    EventDetailView,
    EventFilterBar,
    EventList,
    EventStatsBar,
    filter_events,
)
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.events_service import EventsService

logger = get_logger("skuel.routes.events_ui")


async def _fetch_event_connections(
    events_service: EventsService,
    event_uids: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch-fetch outbound cross-domain connections for a list of events.

    Returns a map of event_uid -> list of connection dicts with keys:
    rel_type, target_uid, title, target_type.
    """
    if not event_uids:
        return {}

    query = """
    MATCH (e:Entity:Event)
    WHERE e.uid IN $event_uids
    OPTIONAL MATCH (e)-[r]->(target:Entity)
    WHERE type(r) IN [
        'REINFORCES_HABIT', 'MILESTONE_CELEBRATION_FOR_GOAL',
        'PART_OF_PATH_STEP', 'PART_OF_LEARNING_PATH',
        'DEMONSTRATES_PRINCIPLE', 'APPLIES_KNOWLEDGE',
        'RELATED_TO'
    ]
    RETURN e.uid AS event_uid,
           type(r) AS rel_type,
           target.uid AS target_uid,
           target.title AS title,
           target.entity_type AS target_type
    """
    try:
        result = await events_service.core.backend.execute_query(query, {"event_uids": event_uids})
    except Exception:  # safety-net: Neo4j query failure shouldn't break the page
        logger.warning("Failed to fetch event connections", exc_info=True)
        return {}

    if result.is_error:
        return {}

    connections_map: dict[str, list[dict[str, str]]] = {}
    for record in result.value:
        event_uid = record["event_uid"]
        if record.get("rel_type") is None:
            continue
        if event_uid not in connections_map:
            connections_map[event_uid] = []
        connections_map[event_uid].append(
            {
                "rel_type": record["rel_type"],
                "target_uid": record.get("target_uid", ""),
                "title": record.get("title", ""),
                "target_type": record.get("target_type", ""),
            }
        )
    return connections_map


def create_events_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
) -> RouteList:
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
                cls="uk-container uk-container-small",
            )
            return await BasePage(
                content,
                title="Events",
                request=request,
                active_page="events",
            )

        all_events = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "upcoming")
        sort_by = request.query_params.get("sort_by", "date")

        filtered = filter_events(all_events, status_filter, sort_by)

        # Batch-fetch connections
        event_uids = [e.uid for e in filtered]
        connections_map = await _fetch_event_connections(events_service, event_uids)

        event_count = len(all_events)
        subtitle = f"{event_count} event{'s' if event_count != 1 else ''}"

        content = Div(
            PageHeader("Events", subtitle=subtitle),
            EventStatsBar(all_events),
            EventFilterBar(status_filter, sort_by),
            EventList(filtered, connections_map),
            cls="uk-container uk-container-small",
        )

        return await BasePage(
            content,
            title="Events",
            request=request,
            active_page="events",
        )

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
        connections_map = await _fetch_event_connections(events_service, event_uids)

        return EventList(filtered, connections_map)

    @rt("/events/detail")
    async def event_detail_page(request: Request) -> Any:
        """Detail page for a single event with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await BasePage(
                Div(
                    render_error_banner("Missing event UID"), cls="uk-container uk-container-small"
                ),
                title="Event Not Found",
                request=request,
                active_page="events",
            )

        event_result = await events_service.get_event(uid)
        if event_result.is_error:
            return await BasePage(
                Div(render_error_banner("Event not found"), cls="uk-container uk-container-small"),
                title="Event Not Found",
                request=request,
                active_page="events",
            )

        event = event_result.value
        if event.user_uid != user_uid:
            return await BasePage(
                Div(render_error_banner("Event not found"), cls="uk-container uk-container-small"),
                title="Event Not Found",
                request=request,
                active_page="events",
            )

        # Fetch connections
        connections_map = await _fetch_event_connections(events_service, [event.uid])
        connections = connections_map.get(event.uid, [])

        content = EventDetailView(event, connections)

        return await BasePage(
            content,
            title=event.title or "Event",
            request=request,
            active_page="events",
        )

    routes.extend([events_page, events_list_fragment, event_detail_page])
    return routes
