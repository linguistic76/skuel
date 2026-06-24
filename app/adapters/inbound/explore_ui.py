"""
Explore UI Routes — Reading-First Discovery Surface
====================================================

Routes:
- GET  /explore                  — Reading-first index (reading plan, shell-first)
- GET  /explore/content          — HTMX fragment: reading plan content
- GET  /explore/read/{uid}       — KU reader (alias → /explore/ku/{uid})
- GET  /explore/graph            — Dedicated full-page learning graph
- GET  /explore/library          — Full catalog shell (bento card grid)
- GET  /explore/library/content  — HTMX fragment: bento card grid with search
- GET  /api/explore/search       — HTMX fragment: filtered card grid
- GET  /api/explore/graph        — Hub learning universe graph (Vis.js JSON)

Detail pages (/explore/ku/{uid}, /explore/ps/{uid}) and learning loop
fragments (/learning-loop/ps/*) are in learning_loop_routes.py.
"""

from typing import Any

from fasthtml.common import (
    A,
    Div,
    P,
    Request,
    Script,
)
from starlette.responses import RedirectResponse

from adapters.inbound.auth import is_authenticated, require_authenticated_user
from core.utils.logging import get_logger
from ui.explore.cards import render_explore_card, render_explore_search_panel
from ui.explore.filters import filter_items, sort_by_created_at
from ui.explore.graph import ExploreGraphView
from ui.explore.nav import render_explore_sidebar_page
from ui.explore.reading_plan import ExploreReadingView
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
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
    """Register /api/explore/* JSON + HTMX API routes."""
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
        """Return the user's learning universe as Vis.js {nodes, edges} JSON."""
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
    """Create /explore discovery UI routes."""
    if orchestrator is None:
        raise RuntimeError("ExploreOrchestrator is required — bootstrap misconfigured")

    # -----------------------------------------------------------------
    # GET /explore — Reading-first shell (shell-first pattern)
    # -----------------------------------------------------------------

    @rt("/explore")
    async def explore_index(request: Request) -> Any:
        """Explore reading surface — shell renders immediately, plan loads via HTMX.

        exploreReading.js is loaded here (in the full-page shell, before Alpine's
        deferred bundle fires alpine:init) so the factory is registered before
        htmx:load calls Alpine.initTree() on the swapped fragment.
        """
        content = Div(
            # No defer — must execute before Alpine's deferred bundle fires alpine:init
            Script(src="/static/js/explore-reading.js"),
            content_loading_placeholder("/explore/content", "explore-reading-content"),
        )
        return await BasePage(
            content,
            title="Explore",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="explore",
        )

    @rt("/explore/content")
    async def explore_reading_content(request: Request) -> Any:
        """HTMX fragment: reading plan content for /explore."""
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None
        plan = await orchestrator.get_reading_plan(user_uid)
        return Div(
            ExploreReadingView(plan),
            id="explore-reading-content",
        )

    # -----------------------------------------------------------------
    # GET /explore/read/{uid} — KU reader alias
    # -----------------------------------------------------------------

    @rt("/explore/read/{uid}")
    async def explore_read_ku(request: Request, uid: str) -> Any:
        """KU reader — forwards to the Ku detail page."""
        return RedirectResponse(url=f"/explore/ku/{uid}", status_code=302)

    # -----------------------------------------------------------------
    # GET /explore/graph — Dedicated full-page learning graph
    # -----------------------------------------------------------------

    @rt("/explore/graph")
    async def explore_graph_page(request: Request) -> Any:
        """Full-page learning graph — the user's knowledge universe."""
        content = Div(
            Div(
                Div(
                    P(
                        "Your knowledge universe — every idea you're studying, every path in progress.",
                        cls="text-sm text-muted-foreground",
                    ),
                    Div(
                        A("← Reading", href="/explore", cls="text-sm text-muted-foreground hover:text-foreground transition-colors"),
                        A("Browse library →", href="/explore/library", cls="text-sm text-muted-foreground hover:text-foreground transition-colors"),
                        cls="flex items-center gap-6",
                    ),
                    cls="flex items-center justify-between mb-4",
                ),
                ExploreGraphView(mode="hub", height="calc(100vh - 220px)"),
                cls="w-full",
            ),
        )
        return await BasePage(
            content,
            title="Learning Graph",
            request=request,
            active_page="explore",
        )

    # -----------------------------------------------------------------
    # GET /explore/library — Demoted bento-grid catalog
    # -----------------------------------------------------------------

    @rt("/explore/library")
    async def explore_library(request: Request, tag: str = "") -> Any:
        """Full knowledge catalog — bento card grid with search."""
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None
        sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None

        fragment_url = "/explore/library/content"
        if tag:
            fragment_url += f"?tag={tag}"

        content = Div(
            PageHeader("Library", subtitle="Explore all knowledge units and path steps"),
            content_loading_placeholder(fragment_url, "explore-library-content"),
        )
        return await render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
        )

    @rt("/explore/library/content")
    async def explore_library_content(request: Request, tag: str = "") -> Any:
        """HTMX fragment: bento card grid with search panel."""
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None
        items, pinned_uids, learning_states = await orchestrator.load_explore_index(user_uid)

        all_tags = sorted(
            {t for item, _ in items for t in (getattr(item, "tags", None) or ())} - {""}
        )
        items.sort(key=sort_by_created_at, reverse=True)

        if tag:
            items = [(item, et) for item, et in items if tag in (getattr(item, "tags", None) or [])]

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
            render_explore_search_panel(all_tags, active_tag=tag),
            grid,
            id="explore-library-content",
        )

    logger.info(
        "Explore UI routes registered: /explore, /explore/content, "
        "/explore/read/{uid}, /explore/graph, /explore/library, /explore/library/content"
    )

    return []


__all__ = ["create_explore_api_routes", "create_explore_ui_routes"]
