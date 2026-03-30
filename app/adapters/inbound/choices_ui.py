"""Choices UI routes.

Provides the read-focused choice list view at /choices and detail view at /choices/detail.
Choices enter via YAML upload; this UI shows them with status controls,
decision framework, options, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.activities.choices_views import (
    ChoiceDetailView,
    ChoiceFilterBar,
    ChoiceList,
    ChoiceStatsBar,
    filter_choices,
)
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from starlette.requests import Request

    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.choices_service import ChoicesService

logger = get_logger("skuel.routes.choices_ui")


async def _fetch_choice_connections(
    choices_service: ChoicesService,
    choice_uids: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch-fetch outbound cross-domain connections for a list of choices.

    Returns a map of choice_uid -> list of connection dicts with keys:
    rel_type, target_uid, title, target_type.
    """
    if not choice_uids:
        return {}

    query = """
    MATCH (c:Entity:Choice)
    WHERE c.uid IN $choice_uids
    OPTIONAL MATCH (c)-[r]->(target:Entity)
    WHERE type(r) IN [
        'INFORMS_GOAL_STRATEGY', 'ENABLES_HABIT', 'EXPRESSES_PRINCIPLE',
        'APPLIES_KNOWLEDGE', 'RELATED_TO'
    ]
    RETURN c.uid AS choice_uid,
           type(r) AS rel_type,
           target.uid AS target_uid,
           target.title AS title,
           target.entity_type AS target_type
    """
    try:
        result = await choices_service.core.backend.execute_query(
            query, {"choice_uids": choice_uids}
        )
    except Exception:  # safety-net: Neo4j query failure shouldn't break the page
        logger.warning("Failed to fetch choice connections", exc_info=True)
        return {}

    if result.is_error:
        return {}

    connections_map: dict[str, list[dict[str, str]]] = {}
    for record in result.value:
        choice_uid = record["choice_uid"]
        if record.get("rel_type") is None:
            continue
        if choice_uid not in connections_map:
            connections_map[choice_uid] = []
        connections_map[choice_uid].append(
            {
                "rel_type": record["rel_type"],
                "target_uid": record.get("target_uid", ""),
                "title": record.get("title", ""),
                "target_type": record.get("target_type", ""),
            }
        )
    return connections_map


def create_choices_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
) -> RouteList:
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
                cls="uk-container uk-container-small",
            )
            return await BasePage(
                content,
                title="Choices",
                request=request,
                active_page="choices",
            )

        all_choices = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "pending")
        sort_by = request.query_params.get("sort_by", "deadline")

        filtered = filter_choices(all_choices, status_filter, sort_by)

        # Batch-fetch connections
        choice_uids = [c.uid for c in filtered]
        connections_map = await _fetch_choice_connections(choices_service, choice_uids)

        choice_count = len(all_choices)
        subtitle = f"{choice_count} choice{'s' if choice_count != 1 else ''}"

        content = Div(
            PageHeader("Choices", subtitle=subtitle),
            ChoiceStatsBar(all_choices),
            ChoiceFilterBar(status_filter, sort_by),
            ChoiceList(filtered, connections_map),
            cls="uk-container uk-container-small",
        )

        return await BasePage(
            content,
            title="Choices",
            request=request,
            active_page="choices",
        )

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
        connections_map = await _fetch_choice_connections(choices_service, choice_uids)

        return ChoiceList(filtered, connections_map)

    @rt("/choices/detail")
    async def choice_detail_page(request: Request) -> Any:
        """Detail page for a single choice with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await BasePage(
                Div(
                    render_error_banner("Missing choice UID"), cls="uk-container uk-container-small"
                ),
                title="Choice Not Found",
                request=request,
                active_page="choices",
            )

        choice_result = await choices_service.get_choice(uid)
        if choice_result.is_error:
            return await BasePage(
                Div(render_error_banner("Choice not found"), cls="uk-container uk-container-small"),
                title="Choice Not Found",
                request=request,
                active_page="choices",
            )

        choice = choice_result.value
        if choice.user_uid != user_uid:
            return await BasePage(
                Div(render_error_banner("Choice not found"), cls="uk-container uk-container-small"),
                title="Choice Not Found",
                request=request,
                active_page="choices",
            )

        # Fetch connections
        connections_map = await _fetch_choice_connections(choices_service, [choice.uid])
        connections = connections_map.get(choice.uid, [])

        content = ChoiceDetailView(choice, connections)

        return await BasePage(
            content,
            title=choice.title or "Choice",
            request=request,
            active_page="choices",
        )

    routes.extend([choices_page, choices_list_fragment, choice_detail_page])
    return routes
