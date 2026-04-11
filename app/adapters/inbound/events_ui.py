"""Events UI routes.

Provides the read-focused event list view at /events and detail view at /events/detail.
Events enter via YAML upload; this UI shows them with status controls,
scheduling info, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.connection_fetcher import EVENT_CONNECTION_CONFIG
from core.utils.entity_filters import filter_events
from ui.activities.events_views import EventDetailView, EventList, EventStatsBar
from ui.activities.filter_bar import FILTER_CONFIGS

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.events_service import EventsService


def create_events_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
) -> list[Any]:
    """Register Events UI routes."""
    config = ActivityUIConfig(
        domain_name="events",
        domain_singular="event",
        page_title="Events",
        filter_params=(("status", "upcoming"), ("sort_by", "date")),
        get_all=events_service.get_user_events,
        get_one=events_service.get_event,
        backend=events_service.core.backend,
        filter_fn=filter_events,
        connection_config=EVENT_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["events"],
        list_component=EventList,
        stats_component=EventStatsBar,
        detail_component=EventDetailView,
    )
    return create_activity_ui_routes(app, rt, config)
