"""
Exchange Thread UI Route (feedback-loop UX arc C5)
====================================================

GET /exchange?exercise={uid}[&student={uid}] — read-only chronological view
of one (student, root exercise) exchange: submissions, feedback reports, and
revision requests interleaved, each linking to its existing detail/action
surface. Query params over path params per FastHTML conventions.

Access: the viewer reads their own exchange; ``student`` requires the viewer
to share an active owned group with that student (the report-download gate).
Every denial renders the same not-found page (404-not-403).
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.learning_loop.exchange_thread import (
    render_exchange_not_found,
    render_exchange_thread,
)

if TYPE_CHECKING:
    from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator

logger = get_logger("skuel.routes.exchange")


def create_exchange_ui_routes(
    _app: FastHTMLApp, rt: RouteDecorator, orchestrator: "UserEntryOrchestrator"
) -> None:
    """Register the /exchange thread page."""

    @rt("/exchange")
    async def exchange_thread_page(request: Request, exercise: str = "", student: str = "") -> Any:
        """The exchange thread for (viewer-or-student, exercise) — read-only."""
        user_uid = require_authenticated_user(request)

        def _not_found() -> Any:
            return BasePage(
                content=render_exchange_not_found(),
                title="Exchange",
                request=request,
                active_page="gradebook",
            )

        if not exercise:
            return _not_found()

        result = await orchestrator.get_exchange_thread(
            viewer_uid=user_uid,
            exercise_uid=exercise,
            student_uid=student or None,
        )
        if result.is_error:
            return _not_found()

        return BasePage(
            content=render_exchange_thread(result.value, viewer_uid=user_uid),
            title="Exchange",
            request=request,
            active_page="gradebook",
        )

    logger.info("Exchange thread route registered: /exchange")


__all__ = ["create_exchange_ui_routes"]
