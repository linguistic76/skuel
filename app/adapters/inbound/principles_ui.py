"""Principles UI routes.

Provides the read-focused principle list view at /principles and detail view
at /principles/detail. Principles are a gravity well — they show incoming
relationships from tasks, habits, choices, events, and goals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.connection_fetcher import PRINCIPLE_CONNECTION_CONFIG, fetch_entity_connections
from core.utils.entity_filters import filter_principles
from core.utils.logging import get_logger
from ui.activities.filter_bar import ActivityFilterBar
from ui.activities.nav import render_activity_sidebar_page
from ui.activities.principles_views import (
    PRINCIPLE_FILTER_CONFIG,
    PrincipleDetailView,
    PrincipleList,
    PrincipleStatsBar,
)
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.principles_service import PrinciplesService

logger = get_logger("skuel.routes.principles_ui")


def create_principles_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
) -> list[Any]:
    """Register Principles UI routes."""
    routes: list[Any] = []

    @rt("/principles")
    async def principles_page(request: Request) -> Any:
        """Main principles page — lists all user principles with filters."""
        user_uid = require_authenticated_user(request)

        result = await principles_service.get_user_principles(user_uid)
        if result.is_error:
            error = result.expect_error()
            content = Div(
                PageHeader("Principles"),
                render_error_banner(error.user_message or error.message),
            )
            return await render_activity_sidebar_page(content, active="principles", request=request)

        all_principles = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "active")
        category_filter = request.query_params.get("category", "all")
        strength_filter = request.query_params.get("strength", "all")
        sort_by = request.query_params.get("sort_by", "strength")

        filtered = filter_principles(
            all_principles, status_filter, category_filter, strength_filter, sort_by
        )

        # Batch-fetch incoming connections
        principle_uids = [p.uid for p in filtered]
        connections_map = await fetch_entity_connections(
            principles_service.core.backend, PRINCIPLE_CONNECTION_CONFIG, principle_uids
        )

        principle_count = len(all_principles)
        subtitle = f"{principle_count} principle{'s' if principle_count != 1 else ''}"

        content = Div(
            PageHeader("Principles", subtitle=subtitle),
            PrincipleStatsBar(all_principles),
            ActivityFilterBar(
                PRINCIPLE_FILTER_CONFIG,
                {
                    "status": status_filter,
                    "category": category_filter,
                    "strength": strength_filter,
                    "sort_by": sort_by,
                },
            ),
            PrincipleList(filtered, connections_map),
        )

        return await render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/list-fragment")
    async def principles_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered principle list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await principles_service.get_user_principles(user_uid)
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        all_principles = result.value

        status_filter = request.query_params.get("status", "active")
        category_filter = request.query_params.get("category", "all")
        strength_filter = request.query_params.get("strength", "all")
        sort_by = request.query_params.get("sort_by", "strength")

        filtered = filter_principles(
            all_principles, status_filter, category_filter, strength_filter, sort_by
        )

        principle_uids = [p.uid for p in filtered]
        connections_map = await fetch_entity_connections(
            principles_service.core.backend, PRINCIPLE_CONNECTION_CONFIG, principle_uids
        )

        return PrincipleList(filtered, connections_map)

    @rt("/principles/detail")
    async def principle_detail_page(request: Request) -> Any:
        """Detail page for a single principle with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing principle UID")),
                active="principles",
                request=request,
            )

        principle_result = await principles_service.get_principle(uid)
        if principle_result.is_error:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Principle not found")),
                active="principles",
                request=request,
            )

        principle = principle_result.value
        if principle.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Principle not found")),
                active="principles",
                request=request,
            )

        # Fetch incoming connections (gravity well)
        connections_map = await fetch_entity_connections(
            principles_service.core.backend, PRINCIPLE_CONNECTION_CONFIG, [principle.uid]
        )
        connections = connections_map.get(principle.uid, [])

        content = PrincipleDetailView(principle, connections)

        return await render_activity_sidebar_page(content, active="principles", request=request)

    routes.extend([principles_page, principles_list_fragment, principle_detail_page])
    return routes
