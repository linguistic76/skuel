"""Principles UI routes.

Provides the read-focused principle list view at /principles and detail view
at /principles/detail. Principles are a gravity well — they show incoming
relationships from tasks, habits, choices, events, and goals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.connection_fetcher import PRINCIPLE_CONNECTION_CONFIG
from core.utils.entity_filters import filter_principles
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.principles_views import PrincipleDetailView, PrincipleList, PrincipleStatsBar

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.principles_service import PrinciplesService


def create_principles_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
) -> list[Any]:
    """Register Principles UI routes."""
    config = ActivityUIConfig(
        domain_name="principles",
        domain_singular="principle",
        page_title="Principles",
        filter_params=(
            ("status", "active"),
            ("category", "all"),
            ("strength", "all"),
            ("sort_by", "strength"),
        ),
        get_all=principles_service.get_user_principles,
        get_one=principles_service.get_principle,
        backend=principles_service.core.backend,
        filter_fn=filter_principles,
        connection_config=PRINCIPLE_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["principles"],
        list_component=PrincipleList,
        stats_component=PrincipleStatsBar,
        detail_component=PrincipleDetailView,
    )
    return create_activity_ui_routes(app, rt, config)
