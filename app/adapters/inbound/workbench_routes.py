"""Workbench Route Configuration — hub, preview endpoints, and submission history.

The Workbench is the user's hub for getting work into SKUEL:
upload activity data, submit exercises, and view submission history.

Routes:
- GET /workbench — hub page (no sidebar)
- GET /api/workbench/upload/preview — HTMX preview for upload block
- GET /api/workbench/submit/preview — HTMX preview for submit block
- GET /api/workbench/history/preview — HTMX preview for history block
- GET /workbench/history — submission history page
- GET /workbench/history/list — HTMX fragment: refresh submissions list
- POST /workbench/history/delete — HTMX: delete a user-owned submission
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.models.enums.entity_enums import EntityType
from core.utils.logging import get_logger
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.page_header import PageHeader
from ui.submissions.report import render_yours_list
from ui.workbench.nav import render_workbench_sidebar_page

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.workbench")


def create_workbench_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> None:
    """Register Workbench hub, preview, and child routes."""

    submissions_service = getattr(services, "submissions", None)
    submissions_search_service = getattr(services, "submissions_search", None)
    teacher_review_service = getattr(services, "teacher_review", None)

    # ========================================================================
    # HUB PAGE
    # ========================================================================

    @rt("/workbench")
    async def workbench_hub(request: Request) -> Any:
        """Workbench hub — entry point with domain blocks, no sidebar."""
        require_authenticated_user(request)
        from ui.layouts.base_page import BasePage
        from ui.workbench.hub import WorkbenchHub

        return await BasePage(
            content=WorkbenchHub(),
            title="Workbench",
            request=request,
            active_page="workbench",
        )

    # ========================================================================
    # HTMX PREVIEW ENDPOINTS
    # ========================================================================

    @rt("/api/workbench/upload/preview")
    async def upload_preview(request: Request) -> Any:
        """HTMX preview: recent uploads summary."""
        require_authenticated_user(request)
        return HubPreviewEmpty("uploads")

    @rt("/api/workbench/submit/preview")
    async def submit_preview(request: Request) -> Any:
        """HTMX preview: pending exercises to submit."""
        require_authenticated_user(request)
        return HubPreviewEmpty("submissions")

    @rt("/api/workbench/history/preview")
    async def history_preview(request: Request) -> Any:
        """HTMX preview: 3 most recent submissions for hub preview."""
        user_uid = require_authenticated_user(request)
        if not submissions_service:
            return HubPreviewEmpty("submissions")
        result = await submissions_service.list_submissions(
            user_uid, entity_type=EntityType.EXERCISE_SUBMISSION, limit=3
        )
        if result.is_error:
            return HubPreviewEmpty("submissions")
        subs = result.value or []
        if not subs:
            return HubPreviewEmpty("submissions")
        cards = []
        for sub in subs[:3]:
            uid = getattr(sub, "uid", "")
            title = getattr(sub, "title", "Untitled") or "Untitled"
            status = str(getattr(sub, "status", "")).replace("_", " ").title()
            badge = (
                Span(status, cls="text-[10px] font-medium text-muted-foreground")
                if status
                else None
            )
            cards.append(HubPreviewCard(title=title, href=f"/gradebook/{uid}", badge=badge))
        return HubPreviewGrid(cards)

    # ========================================================================
    # SUBMISSION HISTORY PAGE
    # ========================================================================

    @rt("/workbench/history")
    async def workbench_history(request: Request) -> Any:
        """Submission history — list of user's exercise submissions with feedback status."""
        user_uid = require_authenticated_user(request)

        submissions_content: Any = EmptyState(
            title="No submissions yet",
            description="Submit your first exercise to see it here.",
        )
        if submissions_search_service:
            result = await submissions_search_service.get_submissions_with_feedback_status(user_uid)
            if result.is_error:
                logger.error(f"Error loading submissions history: {result.error}")
                submissions_content = render_error_banner(
                    "Failed to load submissions", str(result.error)
                )
            else:
                submissions_content = render_yours_list(result.value or [])

        content = Div(
            PageHeader(
                "Submission History",
                subtitle="Your submitted exercises and feedback status",
            ),
            submissions_content,
        )
        return await render_workbench_sidebar_page(
            content=content,
            active="history",
            request=request,
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/workbench/history/list")
    async def history_list(request: Request) -> Any:
        """HTMX fragment: student's submissions with teacher review status."""
        try:
            user_uid = require_authenticated_user(request)
            if not submissions_search_service:
                return Div(
                    render_error_banner("Submissions service unavailable"),
                    id="submissions-yours-list",
                )
            result = await submissions_search_service.get_submissions_with_feedback_status(user_uid)
            if result.is_error:
                logger.error(f"Error loading submissions history: {result.error}")
                return Div(
                    render_error_banner("Failed to load submissions", str(result.error)),
                    id="submissions-yours-list",
                )
            return render_yours_list(result.value or [])
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submissions history: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading submissions", str(e)),
                id="submissions-yours-list",
            )

    @rt("/workbench/history/delete", methods=["POST"])
    async def delete_submission(request: Request, uid: str) -> Any:
        """Delete a user-owned submission (only if no feedback received)."""
        user_uid = require_authenticated_user(request)

        if not submissions_service:
            return render_error_banner("Submissions service unavailable")

        # Verify the submission exists and belongs to this user
        sub_result = await submissions_service.get_submission(uid)
        if sub_result.is_error or not sub_result.value:
            return render_error_banner("Submission not found")
        submission = sub_result.value
        if submission.user_uid != user_uid:
            return render_error_banner("Access denied")

        # Guard: don't delete submissions that already have feedback
        if teacher_review_service:
            history_result = await teacher_review_service.get_report_history(uid)
            if not history_result.is_error and history_result.value:
                return render_error_banner("Cannot delete a submission that has received feedback")

        delete_result = await submissions_service.delete_submission_with_file(uid)
        if delete_result.is_error:
            return render_error_banner("Failed to delete submission", str(delete_result.error))

        # Return empty div — HTMX outerHTML swap removes the row
        return Div()

    logger.info("Workbench routes registered")


__all__ = ["create_workbench_routes"]
