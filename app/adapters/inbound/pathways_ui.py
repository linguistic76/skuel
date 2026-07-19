"""
Pathways UI Routes
==================

Route handlers for structured learning pathway browsing and progress.
Routes parse the request, call the orchestrator, and wrap the page trees from
``ui/pathways/pages.py`` in ``BasePage`` — all rendering lives in ``ui/``.
"""

from typing import Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.pathways import pages
from ui.pathways.components import path_to_display_dict
from ui.ui_types import ActivePathData, LearningStatsData

logger = get_logger("skuel.ui.pathways")


def create_pathways_ui_routes(
    _app: Any, rt: Any, _primary_service: Any, orchestrator: Any = None
) -> list[Any]:
    """Create UI routes for pathway browsing and progress tracking."""

    routes: list[Any] = []

    @rt("/pathways")
    def pathways_dashboard(request) -> Any:
        """Main pathways dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        return BasePage(
            content=pages.dashboard_shell(),
            title="Pathways Dashboard",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(pathways_dashboard)

    @rt("/pathways/content")
    async def pathways_dashboard_content(request) -> Any:
        """HTMX fragment: pathways dashboard body."""
        user_uid = require_authenticated_user(request)
        summary_result = await orchestrator.get_dashboard_summary(user_uid)
        if summary_result.is_error:
            return pages.dashboard_content_error(summary_result.expect_error().message)
        active_paths: list[ActivePathData] = []
        stats = LearningStatsData(
            total_hours=0.0,
            concepts_mastered=0,
            active_streak=0,
            completion_rate=0.0,
        )
        if summary_result.value:
            active_paths = summary_result.value["active_paths"]
            stats = summary_result.value["stats"]
        return pages.dashboard_content(active_paths, stats)

    routes.append(pathways_dashboard_content)

    @rt("/pathways/browse")
    def browse_learning_paths(request) -> Any:
        """Browse learning paths — shell only, content loads via HTMX."""
        return BasePage(
            content=pages.browse_shell(),
            title="Browse Learning Paths",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(browse_learning_paths)

    @rt("/pathways/browse/content")
    async def browse_learning_paths_content(request) -> Any:
        """HTMX fragment: browse learning paths body."""
        available_paths: list[dict[str, Any]] = []
        paths_result = await orchestrator.list_all_paths(limit=50)
        if not paths_result.is_error and paths_result.value:
            available_paths.extend(path_to_display_dict(path) for path in paths_result.value)
        return pages.browse_content(available_paths)

    routes.append(browse_learning_paths_content)

    @rt("/pathways/steps")
    async def browse_path_steps(request) -> Any:
        """Browse available path steps."""
        require_authenticated_user(request)

        steps_result = await orchestrator.list_steps(limit=50)
        steps = steps_result.value if not steps_result.is_error and steps_result.value else []

        return BasePage(
            content=pages.steps_browser_page(steps),
            title="Browse Learning Steps",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(browse_path_steps)

    @rt("/api/pathways/filter-paths", methods=["POST"])
    @csrf_protected
    async def filter_learning_paths(request) -> Any:
        """Filter learning paths by difficulty, domain, and duration."""
        form_data = await request.form()
        difficulty = form_data.get("difficulty", "all")
        domain = form_data.get("domain", "all")
        duration = form_data.get("duration", "all")

        filter_result = await orchestrator.filter_paths(
            difficulty=difficulty,
            domain=domain,
            duration=duration,
            limit=50,
        )
        paths = filter_result.value if not filter_result.is_error else []
        return pages.paths_grid(paths, empty_message="No learning paths match your filters.")

    routes.append(filter_learning_paths)

    @rt("/pathways/path/{path_uid}")
    def learning_path_detail(request, path_uid: str) -> Any:
        """Learning path detail — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        return BasePage(
            content=pages.path_detail_shell(path_uid),
            title="Learning Path",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(learning_path_detail)

    @rt("/pathways/path/{path_uid}/content")
    async def learning_path_detail_content(request, path_uid: str) -> Any:
        """HTMX fragment: learning path detail body."""
        user_uid = require_authenticated_user(request)
        detail_result = await orchestrator.get_path_detail_progress(path_uid, user_uid)
        if detail_result.is_error:
            return pages.path_detail_not_found(path_uid)
        return pages.path_detail_content(path_uid, detail_result.value)

    routes.append(learning_path_detail_content)

    @rt("/pathways/analytics")
    def learning_analytics(request) -> Any:
        """Learning analytics dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        return BasePage(
            content=pages.analytics_shell(),
            title="Learning Analytics",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(learning_analytics)

    @rt("/pathways/analytics/content")
    async def learning_analytics_content(request) -> Any:
        """HTMX fragment: learning analytics body."""
        user_uid = require_authenticated_user(request)
        analytics_result = await orchestrator.get_learning_analytics(user_uid)
        analytics = analytics_result.value if not analytics_result.is_error else {}
        return pages.analytics_content(analytics)

    routes.append(learning_analytics_content)

    @rt("/lp/{uid}")
    async def lp_detail_view(request, uid: str) -> Any:
        """Learning Path detail view with full context and relationships."""
        path_result = await orchestrator.get_learning_path(uid)
        path = path_result.value if not path_result.is_error and path_result.value else None

        return BasePage(
            content=pages.lp_detail_page(uid, path),
            title=f"LP: {uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(lp_detail_view)

    logger.info(f"Pathways UI routes registered: {len(routes)} endpoints")
    return routes
