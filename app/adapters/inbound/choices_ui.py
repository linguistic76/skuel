"""Choices UI routes.

Provides the read-focused choice list view at /choices and detail view at /choices/detail.
Choices enter via YAML upload; this UI shows them with status controls,
decision framework, options, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.connection_fetcher import CHOICE_CONNECTION_CONFIG, fetch_entity_connections
from core.utils.logging import get_logger
from core.utils.entity_filters import filter_choices
from ui.activities.choices_views import (
    CHOICE_FILTER_CONFIG,
    ChoiceDetailView,
    ChoiceList,
    ChoiceStatsBar,
)
from ui.activities.filter_bar import ActivityFilterBar
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.choices_service import ChoicesService

logger = get_logger("skuel.routes.choices_ui")


def create_choices_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
) -> list[Any]:
    """Register Choices UI routes."""
    routes: list[Any] = []

    @rt("/choices")
    async def choices_page(request: Request) -> Any:
        """Main choices page — lists all user choices with filters."""
        user_uid = require_authenticated_user(request)

        result = await choices_service.get_user_choices(user_uid)
        if result.is_error:
            error = result.expect_error()
            content = Div(
                PageHeader("Choices"),
                render_error_banner(error.user_message or error.message),
            )
            return await render_activity_sidebar_page(content, active="choices", request=request)

        all_choices = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "pending")
        sort_by = request.query_params.get("sort_by", "deadline")

        filtered = filter_choices(all_choices, status_filter, sort_by)

        # Batch-fetch connections
        choice_uids = [c.uid for c in filtered]
        connections_map = await fetch_entity_connections(
            choices_service.core.backend, CHOICE_CONNECTION_CONFIG, choice_uids
        )

        choice_count = len(all_choices)
        subtitle = f"{choice_count} choice{'s' if choice_count != 1 else ''}"

        content = Div(
            PageHeader("Choices", subtitle=subtitle),
            ChoiceStatsBar(all_choices),
            ActivityFilterBar(CHOICE_FILTER_CONFIG, {"status": status_filter, "sort_by": sort_by}),
            ChoiceList(filtered, connections_map),
        )

        return await render_activity_sidebar_page(content, active="choices", request=request)

    @rt("/choices/list-fragment")
    async def choices_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered choice list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await choices_service.get_user_choices(user_uid)
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        all_choices = result.value

        status_filter = request.query_params.get("status", "pending")
        sort_by = request.query_params.get("sort_by", "deadline")

        filtered = filter_choices(all_choices, status_filter, sort_by)

        choice_uids = [c.uid for c in filtered]
        connections_map = await fetch_entity_connections(
            choices_service.core.backend, CHOICE_CONNECTION_CONFIG, choice_uids
        )

        return ChoiceList(filtered, connections_map)

    @rt("/choices/detail")
    async def choice_detail_page(request: Request) -> Any:
        """Detail page for a single choice with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing choice UID")),
                active="choices",
                request=request,
            )

        choice_result = await choices_service.get_choice(uid)
        if choice_result.is_error:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Choice not found")),
                active="choices",
                request=request,
            )

        choice = choice_result.value
        if choice.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Choice not found")),
                active="choices",
                request=request,
            )

        # Fetch connections
        connections_map = await fetch_entity_connections(
            choices_service.core.backend, CHOICE_CONNECTION_CONFIG, [choice.uid]
        )
        connections = connections_map.get(choice.uid, [])

        content = ChoiceDetailView(choice, connections)

        return await render_activity_sidebar_page(content, active="choices", request=request)

    routes.extend([choices_page, choices_list_fragment, choice_detail_page])
    return routes
