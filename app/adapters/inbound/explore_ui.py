"""
Explore UI Routes — Discovery Surface
=======================================

Discovery page where Ku and PathStep entities intermingle
in a bento card layout with search, filtering, and graph.

Routes:
- GET  /explore              — Discovery index with search + bento card grid
- GET  /explore/content      — HTMX fragment: card grid with search panel
- GET  /api/explore/search   — HTMX fragment: filtered card grid
- GET  /api/explore/graph    — Hub learning universe graph (Vis.js JSON)

Detail pages (/explore/ku/{uid}, /explore/ps/{uid}) and learning loop
fragments (/learning-loop/ps/*) are in learning_loop_routes.py.
"""

from typing import Any

from fasthtml.common import (
    Div,
    Request,
)

from adapters.inbound.auth import is_authenticated, require_authenticated_user
from core.utils.logging import get_logger
from ui.explore.cards import render_explore_card, render_explore_search_panel
from ui.explore.filters import filter_items, sort_by_created_at
from ui.explore.nav import render_explore_sidebar_page
from ui.patterns.empty_state import EmptyState
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.explore")


# =============================================================================
# API factory
# =============================================================================


def create_explore_api_routes(
    _app: Any,
    rt: Any,
    orchestrator: Any,
) -> list[Any]:
    """Register /api/explore/* JSON + HTMX API routes.

    Args:
        orchestrator: ExploreOrchestrator for unified data access.
    """
    if orchestrator is None:
        raise RuntimeError("ExploreOrchestrator is required — bootstrap misconfigured")

    @rt("/api/explore/search")
    async def explore_search(
        request: Request,
        q: str = "",
        type: str = "",
        tag: str = "",
        sort: str = "created_at",
    ) -> Any:
        """Return filtered card grid HTML fragment for HTMX swap."""
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None
        items, pinned_uids, learning_states = await orchestrator.load_explore_index(user_uid)

        filtered = filter_items(items, q.strip(), type, tag, sort)

        if not filtered:
            return EmptyState("No results match your search.")

        cards = [
            render_explore_card(
                item,
                entity_type=et,
                learning_state=learning_states.get(item.uid, ""),
                is_pinned=item.uid in pinned_uids,
            )
            for item, et in filtered
        ]

        return Div(
            *cards,
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        )

    @rt("/api/explore/graph")
    async def explore_graph(request: Request) -> Any:
        """Return the user's learning universe as Vis.js {nodes, edges} JSON.

        Shows studying Kus + in-progress PSes as nodes, with USES_KU
        edges between PathSteps and their composed Kus. Unauthenticated
        users get an empty graph.
        """
        from starlette.responses import JSONResponse

        if not is_authenticated(request):
            return JSONResponse({"nodes": [], "edges": []})

        user_uid = require_authenticated_user(request)
        graph_data = await orchestrator.generate_learning_graph(user_uid)
        return JSONResponse(graph_data)

    logger.info("Explore API routes registered: /api/explore/search, /api/explore/graph")
    return []


# =============================================================================
# UI factory
# =============================================================================


def create_explore_ui_routes(
    _app: Any,
    rt: Any,
    orchestrator: Any,
) -> list[Any]:
    """Create /explore discovery UI routes.

    Args:
        orchestrator: ExploreOrchestrator for unified data access.
    """
    if orchestrator is None:
        raise RuntimeError("ExploreOrchestrator is required — bootstrap misconfigured")

    # -----------------------------------------------------------------
    # GET /explore — Discovery index
    # -----------------------------------------------------------------

    @rt("/explore")
    async def explore_index(request: Request) -> Any:
        """Explore page — shell renders immediately, content loads via HTMX."""
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None
        sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None
        content = Div(
            PageHeader("Explore", subtitle="Discover knowledge units and path steps"),
            content_loading_placeholder("/explore/content", "explore-content"),
        )
        return await render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
        )

    @rt("/explore/content")
    async def explore_content_fragment(request: Request) -> Any:
        """HTMX fragment: explore card grid with search panel."""
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None
        items, pinned_uids, learning_states = await orchestrator.load_explore_index(user_uid)

        all_tags = sorted(
            {t for item, _ in items for t in (getattr(item, "tags", None) or ())} - {""}
        )
        items.sort(key=sort_by_created_at, reverse=True)

        cards = [
            render_explore_card(
                item,
                entity_type=et,
                learning_state=learning_states.get(item.uid, ""),
                is_pinned=item.uid in pinned_uids,
            )
            for item, et in items
        ]

        grid = (
            Div(
                *cards,
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                id="explore-grid",
            )
            if cards
            else EmptyState(
                "No content yet",
                description="Ingest Ku or PathStep YAML files to populate this page.",
                id="explore-grid",
            )
        )

        return Div(
            render_explore_search_panel(all_tags),
            grid,
            id="explore-content",
        )

    logger.info(
        "Explore UI routes registered: /explore, /explore/content"
    )

    return []


__all__ = ["create_explore_api_routes", "create_explore_ui_routes"]
