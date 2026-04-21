"""Activity Review Orchestrator
===============================

Application orchestrator for the Activity Review admin hub. Consolidates
ActivityReportOperations, ReviewQueueOperations, UserService, and
UserContextBuilder into a single facade for activity_review_ui.py.

ActivityReportOperations and UserService are always required.
ReviewQueueOperations and UserContextBuilder are optional — methods that
require them return Result.fail when unavailable.
"""

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.report.activity_report import ActivityReport
    from core.ports.report_protocols import ActivityReportOperations, ReviewQueueOperations
    from core.services.user.unified_user_context import RichUserContext, UserContext
    from core.services.user.user_context_builder import UserContextBuilder
    from core.services.user_service import UserService


class ActivityReviewOrchestrator:
    """Facade for the Activity Review admin UI layer.

    Abstracts cross-service reads so the UI routing layer depends only on this
    orchestrator. ActivityReportOperations and UserService are always required.
    ReviewQueueOperations and UserContextBuilder are optional — callers receive
    a graceful Result.fail when unavailable.
    """

    def __init__(
        self,
        activity_report: "ActivityReportOperations",
        user_service: "UserService",
        review_queue: "ReviewQueueOperations | None" = None,
        context_builder: "UserContextBuilder | None" = None,
    ) -> None:
        self._activity_report = activity_report
        self._user_service = user_service
        self._review_queue = review_queue
        self._context_builder = context_builder

    @property
    def user_service(self) -> "UserService":
        """Expose user service for admin role checks."""
        return self._user_service

    # --- Review Queue ---

    async def get_pending_reviews(self, admin_uid: str, limit: int = 20) -> "Result[list[Any]]":
        """Return pending review requests. Empty list when queue service unavailable."""
        if self._review_queue is None:
            return Result.ok([])
        return await self._review_queue.get_pending_reviews(_admin_uid=admin_uid, limit=limit)

    # --- Context ---

    async def build_rich_context(
        self, subject_uid: str, window: str = "7d"
    ) -> "Result[RichUserContext]":
        """Build rich UserContext for a subject user. Fails when builder unavailable."""
        if self._context_builder is None:
            return Result.fail(
                Errors.system(
                    message="Context builder not configured",
                    service="context_builder",
                )
            )
        return await self._context_builder.build_rich(subject_uid, window=window)

    # --- Activity Report ---

    async def create_snapshot(
        self,
        context: "UserContext",
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> "Result[dict[str, Any]]":
        """Build activity snapshot from pre-built UserContext."""
        return await self._activity_report.create_snapshot(
            context=context,
            time_period=time_period,
            domains=domains,
        )

    async def submit_report(
        self,
        admin_uid: str,
        subject_uid: str,
        feedback_text: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> "Result[ActivityReport]":
        """Create ActivityReport from admin-written assessment."""
        return await self._activity_report.submit_report(
            admin_uid=admin_uid,
            subject_uid=subject_uid,
            feedback_text=feedback_text,
            time_period=time_period,
            domains=domains,
        )
