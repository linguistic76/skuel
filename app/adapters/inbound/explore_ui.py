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
from core.models.enums.entity_enums import EntityType
from core.models.search.filter_enums import SearchSortOrder
from core.models.search_request import SearchRequest
from core.utils.logging import get_logger
from ui.explore.cards import (
    LIBRARY_PAGE_SIZE,
    render_explore_card,
    render_explore_search_panel,
    render_load_more,
)
from ui.explore.graph import ExploreGraphView
from ui.explore.nav import render_explore_sidebar_page
from ui.explore.reading_plan import ExploreReadingView
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.explore")

# The library's sort dropdown values → SearchSortOrder (boundary mapping).
_LIBRARY_SORT_MAP = {
    "created_at": SearchSortOrder.CREATED_DESC,
    "title": SearchSortOrder.TITLE_ASC,
}


def _library_search_request(
    q: str,
    type_filter: str,
    tag: str,
    sort: str,
    offset: int,
) -> SearchRequest:
    """Map the library panel's form params onto THE canonical SearchRequest.

    Empty type = the whole catalog (Ku + PathStep); "ku"/"ps" resolve through
    EntityType.from_string (aliases are input-only). An active tag chip becomes
    an exact-match tags facet. Unknown sort values fall back to newest-first.
    """
    entity_type = EntityType.from_string(type_filter) if type_filter else None
    entity_types: list[Any] = (
        [entity_type] if entity_type else [EntityType.KU, EntityType.PATH_STEP]
    )
    return SearchRequest(
        query_text=q.strip() or None,
        entity_types=entity_types,
        tags_contain=[tag] if tag else None,
        sort_order=_LIBRARY_SORT_MAP.get(sort, SearchSortOrder.CREATED_DESC),
        limit=LIBRARY_PAGE_SIZE,
        offset=max(offset, 0),
    )


def _library_cards(
    records: list[dict[str, Any]],
    pinned_uids: set[str],
    learning_states: dict[str, str],
    offset: int,
) -> list[Any]:
    """Bare cards + Load-more sentinel for one library page.

    Bare (no grid wrapper) because every consumer swaps innerHTML into — or
    appends within — the ``#explore-grid`` container; a wrapped response would
    nest grid-in-grid. The sentinel is omitted on a short page (no next page).
    """
    cards: list[Any] = [
        render_explore_card(
            record,
            learning_state=learning_states.get(str(record.get("uid", "")), ""),
            is_pinned=str(record.get("uid", "")) in pinned_uids,
        )
        for record in records
    ]
    if len(records) == LIBRARY_PAGE_SIZE:
        cards.append(render_load_more(offset + LIBRARY_PAGE_SIZE))
    return cards


# =============================================================================
# API factory
# =============================================================================


def create_explore_api_routes(
    _app: Any,
    rt: Any,
    orchestrator: Any,
    search_router: Any,
) -> list[Any]:
    """Register /api/explore/* JSON + HTMX API routes."""
    if orchestrator is None:
        raise RuntimeError("ExploreOrchestrator is required — bootstrap misconfigured")
    if search_router is None:
        raise RuntimeError("SearchRouter is required — bootstrap misconfigured")

    @rt("/api/explore/search")
    async def explore_search(
        request: Request,
        q: str = "",
        type: str = "",
        tag: str = "",
        sort: str = "created_at",
        offset: int = 0,
    ) -> Any:
        """One library page of bare cards (+ Load-more sentinel) for HTMX swap.

        The catalog query runs through SearchRouter.faceted_search (One Path
        Forward) — Neo4j-side text/tag/type filtering, sort, and pagination.
        Anonymous browse is supported (Ku/PS are PUBLIC-visibility domains).
        """
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None

        search_request = _library_search_request(q, type, tag, sort, offset)
        result = await search_router.faceted_search(search_request, user_uid)
        if result.is_error:
            logger.error(f"Library search failed: {result.error}")
            return EmptyState("Search is unavailable right now. Please try again.")

        records = result.value.results
        if not records:
            # Page-two-and-beyond emptiness just ends the pagination quietly.
            return EmptyState("No results match your search.") if offset == 0 else Div()

        pinned_uids, learning_states = await orchestrator.load_card_decorations(user_uid)
        return tuple(_library_cards(records, pinned_uids, learning_states, offset))

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
    search_router: Any,
) -> list[Any]:
    """Create /explore discovery UI routes."""
    if orchestrator is None:
        raise RuntimeError("ExploreOrchestrator is required — bootstrap misconfigured")
    if search_router is None:
        raise RuntimeError("SearchRouter is required — bootstrap misconfigured")

    # -----------------------------------------------------------------
    # GET /explore — Reading-first shell (shell-first pattern)
    # -----------------------------------------------------------------

    @rt("/explore")
    def explore_index(request: Request) -> Any:
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
        return BasePage(
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
    def explore_read_ku(request: Request, uid: str) -> Any:
        """KU reader — forwards to the Ku detail page."""
        return RedirectResponse(url=f"/explore/ku/{uid}", status_code=302)

    # -----------------------------------------------------------------
    # GET /explore/graph — Dedicated full-page learning graph
    # -----------------------------------------------------------------

    @rt("/explore/graph")
    def explore_graph_page(request: Request) -> Any:
        """Full-page learning graph — the user's knowledge universe."""
        content = Div(
            Div(
                Div(
                    P(
                        "Your knowledge universe — every idea you're studying, every path in progress.",
                        cls="text-sm text-muted-foreground",
                    ),
                    Div(
                        A(
                            "← Reading",
                            href="/explore",
                            cls="text-sm text-muted-foreground hover:text-foreground transition-colors",
                        ),
                        A(
                            "Browse library →",
                            href="/explore/library",
                            cls="text-sm text-muted-foreground hover:text-foreground transition-colors",
                        ),
                        cls="flex items-center gap-6",
                    ),
                    cls="flex items-center justify-between mb-4",
                ),
                ExploreGraphView(mode="hub", height="calc(100vh - 220px)"),
                cls="w-full",
            ),
        )
        return BasePage(
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
        return render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
        )

    @rt("/explore/library/content")
    async def explore_library_content(request: Request, tag: str = "") -> Any:
        """HTMX fragment: bento card grid with search panel.

        First page via SearchRouter.faceted_search (same path as
        /api/explore/search); the tag-chip vocabulary comes from the graph
        via SearchRouter.tag_frequencies — never derived from the loaded
        page — ranked most-used first so the visible chip row surfaces the
        densest facets instead of an alphabetical A-C slice.
        """
        user_uid = require_authenticated_user(request) if is_authenticated(request) else None

        search_request = _library_search_request("", "", tag, "created_at", 0)
        result = await search_router.faceted_search(search_request, user_uid)
        if result.is_error:
            logger.error(f"Library content load failed: {result.error}")
            records = []
        else:
            records = result.value.results

        tags_result = await search_router.tag_frequencies()
        all_tags = (
            [item["tag"] for item in tags_result.value]
            if tags_result.is_ok and tags_result.value
            else []
        )

        pinned_uids, learning_states = await orchestrator.load_card_decorations(user_uid)
        cards = _library_cards(records, pinned_uids, learning_states, offset=0)

        grid = (
            Div(
                *cards,
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                id="explore-grid",
            )
            if records
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
