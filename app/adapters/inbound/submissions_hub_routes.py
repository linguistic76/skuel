"""Submissions Hub Routes — hub page, preview endpoints, and submission history.

The Submissions section is where users upload activity data, submit exercises,
and view their submission history.

Routes:
- GET /submissions — hub page (no sidebar)
- GET /api/submissions/upload/preview — HTMX preview for upload block
- GET /api/submissions/submit/preview — HTMX preview for submit block
- GET /api/submissions/history/preview — HTMX preview for history block
- GET /submissions/history — submission history page
- GET /submissions/history/list — HTMX fragment: refresh submissions list
- POST /submissions/history/delete — HTMX: delete a user-owned submission
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
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.submissions")


def create_submissions_hub_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> None:
    """Register Submissions hub, preview, and child routes."""

    orchestrator = services.submissions_orchestrator
    if orchestrator is None:
        raise RuntimeError("SubmissionsOrchestrator is required — check bootstrap wiring")

    # ========================================================================
    # HUB PAGE
    # ========================================================================

    @rt("/submissions")
    async def submissions_hub(request: Request) -> Any:
        """Submissions hub — tabbed hub with Submissions tab active."""
        require_authenticated_user(request)
        from ui.home_hub import HomeHub
        from ui.layouts.base_page import BasePage

        return await BasePage(
            content=HomeHub(active_tab="submissions"),
            title="Submissions",
            request=request,
            active_page="submissions",
        )

    # ========================================================================
    # HTMX PREVIEW ENDPOINTS
    # ========================================================================

    @rt("/api/submissions/upload/preview")
    async def upload_preview(request: Request) -> Any:
        """HTMX preview: upload form embedded directly in the hub block."""
        require_authenticated_user(request)
        from adapters.inbound.upload_ui import _results_area, _upload_form

        return Div(_upload_form(), _results_area())

    @rt("/api/submissions/submit/preview")
    async def submit_preview(request: Request) -> Any:
        """HTMX preview: pending exercises to submit."""
        require_authenticated_user(request)
        return HubPreviewEmpty("submissions")

    @rt("/api/submissions/history/preview")
    async def history_preview(request: Request) -> Any:
        """HTMX preview: 3 most recent submissions for hub preview."""
        user_uid = require_authenticated_user(request)
        result = await orchestrator.list_submissions(
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

    @rt("/submissions/history")
    async def submissions_history(request: Request) -> Any:
        """Submission history — list of user's exercise submissions with feedback status."""
        user_uid = require_authenticated_user(request)

        submissions_content: Any = EmptyState(
            title="No submissions yet",
            description="Submit your first exercise to see it here.",
        )
        result = await orchestrator.get_submissions_with_feedback_status(user_uid)
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
        return await render_submissions_sidebar_page(
            content=content,
            active="history",
            request=request,
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/history/list")
    async def history_list(request: Request) -> Any:
        """HTMX fragment: student's submissions with teacher review status."""
        try:
            user_uid = require_authenticated_user(request)
            result = await orchestrator.get_submissions_with_feedback_status(user_uid)
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

    @rt("/submissions/history/delete", methods=["POST"])
    async def delete_submission(request: Request, uid: str) -> Any:
        """Delete a user-owned submission (only if no feedback received)."""
        user_uid = require_authenticated_user(request)

        # Verify the submission exists and belongs to this user
        sub_result = await orchestrator.get_submission(uid)
        if sub_result.is_error or not sub_result.value:
            return render_error_banner("Submission not found")
        submission = sub_result.value
        if submission.user_uid != user_uid:
            return render_error_banner("Access denied")

        # Guard: don't delete submissions that already have feedback
        history_result = await orchestrator.get_report_history(uid)
        if not history_result.is_error and history_result.value:
            return render_error_banner("Cannot delete a submission that has received feedback")

        delete_result = await orchestrator.delete_submission_with_file(uid)
        if delete_result.is_error:
            return render_error_banner("Failed to delete submission", str(delete_result.error))

        # Return empty div — HTMX outerHTML swap removes the row
        return Div()

    logger.info("Submissions hub routes registered")


__all__ = ["create_submissions_hub_routes"]
