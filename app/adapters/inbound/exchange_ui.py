"""
Exchange Thread UI Route (feedback-loop UX arc C5)
====================================================

GET /exchange?exercise={uid}[&student={uid}] — read-only chronological view
of one (student, root exercise) exchange: submissions, feedback reports, and
revision requests interleaved, each linking to its existing detail/action
surface. Query params over path params per FastHTML conventions.

Access: the viewer reads their own exchange; ``student`` requires the SAME
double gate as the report download — the live TEACHER role ("may you review
at all") plus a shared active owned group with that student ("this student").
Every denial serves the same rendered not-found page with a REAL 404 status
(404-not-403; a denied read must not reach a client or cache as a success).
"""

from typing import TYPE_CHECKING

from fasthtml.common import FT, to_xml
from starlette.responses import HTMLResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.auth.roles import UserRole
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory
from ui.layouts.base_page import BasePage
from ui.learning_loop.exchange_thread import (
    render_exchange_not_found,
    render_exchange_thread,
)
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator

logger = get_logger("skuel.routes.exchange")


def create_exchange_ui_routes(
    _app: FastHTMLApp, rt: RouteDecorator, orchestrator: "UserEntryOrchestrator"
) -> None:
    """Register the /exchange thread page."""

    @rt("/exchange")
    async def exchange_thread_page(
        request: Request, exercise: str = "", student: str = ""
    ) -> "FT | HTMLResponse":
        """The exchange thread for (viewer-or-student, exercise) — read-only."""
        user_uid = require_authenticated_user(request)

        def _not_found() -> HTMLResponse:
            """The one denial shape: the rendered page with a real 404 status."""
            return HTMLResponse(
                to_xml(
                    BasePage(
                        content=render_exchange_not_found(),
                        title="Exchange",
                        request=request,
                        active_page="gradebook",
                    )
                ),
                status_code=404,
            )

        def _unavailable() -> HTMLResponse:
            """The operational-failure shape: rendered error banner, real 500."""
            return HTMLResponse(
                to_xml(
                    BasePage(
                        content=render_error_banner(
                            "Could not load the exchange. Please try again."
                        ),
                        title="Exchange",
                        request=request,
                        active_page="gradebook",
                    )
                ),
                status_code=500,
            )

        if not exercise:
            return _not_found()

        if student and student != user_uid:
            # The report-download route's first gate, replicated: the role is
            # read live, so an ex-teacher who still OWNS groups cannot keep
            # reading students' work on a stale edge. The orchestrator's
            # shared-active-group check is the second gate. Both denials
            # render the same 404 page — but the user read keeps its Result
            # distinction: a failed lookup is an outage, never a denial.
            viewer_result = await orchestrator.user_service.get_user(user_uid)
            if viewer_result.is_error:
                logger.error(
                    "Failed to resolve viewer role for exchange %s: %s",
                    exercise,
                    viewer_result.expect_error().message,
                )
                return _unavailable()
            viewer = viewer_result.value
            if viewer is None or not viewer.has_permission(UserRole.TEACHER):
                return _not_found()

        result = await orchestrator.get_exchange_thread(
            viewer_uid=user_uid,
            exercise_uid=exercise,
            student_uid=student or None,
        )
        if result.is_error:
            # Only a genuine NOT_FOUND is the deliberately hidden class
            # (missing exercise / no entries / denied access — the
            # orchestrator already collapses denials into it). An operational
            # failure (Neo4j down, query error) must surface as an outage,
            # never masquerade as missing user data.
            error = result.expect_error()
            if error.category is not ErrorCategory.NOT_FOUND:
                logger.error("Failed to load exchange thread for %s: %s", exercise, error.message)
                return _unavailable()
            return _not_found()

        return BasePage(
            content=render_exchange_thread(result.value, viewer_uid=user_uid),
            title="Exchange",
            request=request,
            active_page="gradebook",
        )

    logger.info("Exchange thread route registered: /exchange")


__all__ = ["create_exchange_ui_routes"]
