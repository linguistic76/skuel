"""
Pathways UI Routes
==================

Route handlers for structured learning pathway browsing and progress, and the
learning path detail page (``/lp/{uid}``). Routes parse the request, call the
orchestrator, and wrap the page trees from ``ui/pathways/pages.py`` and
``ui/curriculum/lp_detail.py`` in ``BasePage`` — all rendering lives in ``ui/``.
"""

from typing import Any

from adapters.inbound.auth import get_current_user, require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.route_factories import refuse, refuse_not_found
from core.utils.logging import get_logger
from ui.curriculum import lp_detail
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.pathways import pages
from ui.pathways.components import (
    path_to_display_dict,
    to_active_path_data,
    to_learning_stats,
)

logger = get_logger("skuel.ui.pathways")


def create_pathways_ui_routes(
    _app: Any, rt: Any, _primary_service: Any, orchestrator: Any = None
) -> None:
    """Create UI routes for pathway browsing and progress tracking."""

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

    @rt("/pathways/content")
    async def pathways_dashboard_content(request) -> Any:
        """HTMX fragment: pathways dashboard body."""
        user_uid = require_authenticated_user(request)
        summary_result = await orchestrator.get_dashboard_summary(user_uid)
        if summary_result.is_error:
            return pages.dashboard_content_error(summary_result.expect_error().message)
        summary = summary_result.value
        active_paths = [to_active_path_data(row) for row in summary["paths"]]
        return pages.dashboard_content(active_paths, to_learning_stats(summary))

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

    @rt("/pathways/browse/content")
    async def browse_learning_paths_content(request) -> Any:
        """HTMX fragment: browse learning paths body."""
        available_paths: list[dict[str, Any]] = []
        paths_result = await orchestrator.list_all_paths(limit=50)
        if not paths_result.is_error and paths_result.value:
            available_paths.extend(path_to_display_dict(path) for path in paths_result.value)
        return pages.browse_content(available_paths)

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

    @rt("/pathways/analytics/content")
    async def learning_analytics_content(request) -> Any:
        """HTMX fragment: learning analytics body."""
        user_uid = require_authenticated_user(request)
        analytics_result = await orchestrator.get_learning_analytics(user_uid)
        analytics = analytics_result.value if not analytics_result.is_error else {}
        return pages.analytics_content(analytics)

    @rt("/lp/{uid}")
    def lp_detail_view(request, uid: str) -> Any:
        """Learning path detail — shell only, the body loads via HTMX. Public:
        shared curriculum reads for every visitor."""
        return BasePage(
            content=lp_detail.lp_detail_shell(uid),
            title="Learning Path",
            page_type=PageType.STANDARD,
            request=request,
            active_page="learning-paths",
        )

    @rt("/lp/{uid}/content")
    async def lp_detail_content(request, uid: str) -> Any:
        """HTMX fragment: the path, the step tree, and — for a signed-in viewer —
        their progress or Enroll. A uid that names no learning path is the 404."""
        user_uid = get_current_user(request)
        if user_uid is None:
            path_result = await orchestrator.get_learning_path(uid)
            if path_result.is_error:
                return refuse(
                    path_result.expect_error(), lp_detail.lp_detail_refusal, "Learning path"
                )
            if path_result.value is None:
                return refuse_not_found(lp_detail.lp_detail_refusal("Learning path not found"))
            return lp_detail.lp_detail_content(path_result.value, signed_in=False)

        detail_result = await orchestrator.get_path_detail_progress(uid, user_uid)
        if detail_result.is_error:
            return refuse(
                detail_result.expect_error(), lp_detail.lp_detail_refusal, "Learning path"
            )
        detail = detail_result.value
        return lp_detail.lp_detail_content(
            detail["path"],
            signed_in=True,
            is_enrolled=detail["is_enrolled"],
            progress=detail["progress"],
            mastered_uids=detail["mastered_uids"],
        )

    logger.info("Pathways UI routes registered")
