"""
Explore UI Routes — Discovery Page for Ku + PathStep
=====================================================

Unified exploration surface where Ku and PathStep entities intermingle
in a discovery-first bento card layout with search and filtering.

Routes:
- GET  /explore              — Discovery index with search + bento card grid
- GET  /api/explore/search   — HTMX fragment: filtered card grid
- GET  /api/explore/graph    — Hub learning universe graph (Vis.js JSON)
- GET  /explore/ku/{uid}     — Ku detail page with sidebar
- GET  /explore/ps/{uid}     — PathStep detail page with sidebar

Learning loop fragment routes (/learning-loop/ps/*) are in learning_loop_routes.py.
"""

from typing import Any

from fasthtml.common import (
    Div,
    Request,
)

from adapters.inbound.auth import get_current_user, is_authenticated, require_authenticated_user
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.explore.cards import render_explore_card, render_explore_search_panel
from ui.explore.filters import filter_items, sort_by_created_at
from ui.explore.ku_detail import render_ku_detail_content, render_ku_not_found
from ui.explore.nav import render_explore_sidebar_page
from ui.explore.ps_detail import render_ps_detail_content, render_ps_not_found
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
    """Create /explore UI routes.

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

    # -----------------------------------------------------------------
    # GET /explore/ku/{uid} — Ku detail page
    # -----------------------------------------------------------------

    @rt("/explore/ku/{uid}")
    async def explore_ku_detail(request: Request, uid: str) -> Any:
        """Ku detail page — shell renders immediately, content loads via HTMX."""
        user_uid = get_current_user(request)
        sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None
        content = content_loading_placeholder(f"/explore/ku/{uid}/content", "ku-detail-content")
        return await render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
            current_uid=uid,
            current_entity_type="ku",
        )

    @rt("/explore/ku/{uid}/content")
    async def explore_ku_content_fragment(request: Request, uid: str) -> Any:
        """HTMX fragment: Ku detail content with learning state and exercises."""
        user_uid: str | None = get_current_user(request)

        ku_result = await orchestrator.get_ku(uid)

        if not ku_result or ku_result.is_error or not ku_result.value:
            return render_ku_not_found(uid)

        ku = ku_result.value

        # Learning state
        learning_state: dict[str, bool] = {"is_studying": False, "is_understood": False}
        is_pinned = False
        if user_uid:
            state_result = await orchestrator.get_ku_learning_state(user_uid, uid)
            if state_result.is_ok:
                learning_state = state_result.value
            pins_result = await orchestrator.get_pinned_entities(user_uid)
            if pins_result.is_ok and pins_result.value:
                is_pinned = uid in set(pins_result.value)

        # Exercises
        exercises_result = await orchestrator.get_exercises_for_curriculum(uid)
        exercises_for_ku = exercises_result.value if exercises_result.is_ok else []

        # Render markdown
        content_html, toc_html = render_markdown_with_toc(ku.description or "")

        return render_ku_detail_content(
            ku=ku,
            uid=uid,
            content_html=content_html,
            toc_html=toc_html,
            learning_state=learning_state,
            is_pinned=is_pinned,
            user_uid=user_uid,
            exercises_for_ku=exercises_for_ku,
        )

    # -----------------------------------------------------------------
    # GET /explore/ps/{uid} — PathStep detail page
    # -----------------------------------------------------------------

    @rt("/explore/ps/{uid}")
    async def explore_ps_detail(request: Request, uid: str) -> Any:
        """PathStep detail page — shell renders immediately, content loads via HTMX."""
        user_uid = get_current_user(request)
        sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None
        content = content_loading_placeholder(f"/explore/ps/{uid}/content", "ps-detail-content")
        return await render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
            current_uid=uid,
            current_entity_type="ps",
        )

    @rt("/explore/ps/{uid}/content")
    async def explore_ps_content_fragment(request: Request, uid: str) -> Any:
        """HTMX fragment: PathStep detail content with learning state and learning loop."""
        user_uid: str | None = get_current_user(request)

        result = await orchestrator.get_ps_with_content(uid)
        if result.is_error:
            return render_ps_not_found(uid)

        step, content_body = result.value
        if not content_body and getattr(step, "content", None):
            content_body = str(step.content)

        # Learning state
        is_marked_read = False
        is_bookmarked = False
        is_in_progress = False
        is_mastered = False
        if user_uid:
            await orchestrator.record_ps_view(user_uid, uid)
            state_result = await orchestrator.get_ps_learning_state(user_uid, uid)
            is_marked_read = state_result.value.is_marked_as_read if state_result.is_ok else False
            is_bookmarked = state_result.value.is_bookmarked if state_result.is_ok else False
            is_in_progress = (
                state_result.value.state.value == "in_progress" if state_result.is_ok else False
            )
            is_mastered = (
                state_result.value.state.value == "mastered" if state_result.is_ok else False
            )

        # Exercises for unauthenticated users
        exercises: list[dict] = []
        if not user_uid:
            exercises_result = await orchestrator.get_exercises_for_path_step(uid)
            if exercises_result.is_ok and exercises_result.value:
                exercises = exercises_result.value

        # Render markdown
        content_html, toc_html = render_markdown_with_toc(content_body or "")

        return render_ps_detail_content(
            step=step,
            uid=uid,
            content_html=content_html,
            toc_html=toc_html,
            is_marked_read=is_marked_read,
            is_bookmarked=is_bookmarked,
            is_in_progress=is_in_progress,
            is_mastered=is_mastered,
            user_uid=user_uid,
            exercises=exercises,
        )

    logger.info(
        "Explore UI routes registered: /explore, /explore/ku/{uid}, /explore/ps/{uid} "
        "(shell-first with /content fragments)"
    )

    return []


__all__ = ["create_explore_api_routes", "create_explore_ui_routes"]
