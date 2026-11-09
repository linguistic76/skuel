"""Activity Review Orchestrator
===============================

Application orchestrator for the Activity Review admin hub. Consolidates
ActivityReportOperations, ReviewQueueOperations, UserService, and
UserContextBuilder into a single facade for activity_review_ui.py.

ActivityReportOperations and UserService are always required.
ReviewQueueOperations and UserContextBuilder are optional — methods that
require them return Result.fail when unavailable.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.zone_context import zone_scope

if TYPE_CHECKING:
    from core.models.report.activity_report import ActivityReport
    from core.ports.query_types import PendingReviewItem
    from core.ports.report_protocols import ActivityReportOperations, ReviewQueueOperations
    from core.services.user.unified_user_context import RichUserContext, UserContext
    from core.services.user.user_context_builder import UserContextBuilder
    from core.services.user_service import UserService

logger = get_logger("skuel.orchestrator.activity_review")


@dataclass(frozen=True)
class SubmittedReview:
    """A written review, and what became of the request it answered.

    ``request_closed`` is None when the review answered no request, False when the
    report was written but its request could not be closed (the admin is told).
    """

    report: ActivityReport
    request_closed: bool | None = None


class ActivityReviewOrchestrator:
    """Facade for the Activity Review admin UI layer.

    Abstracts cross-service reads so the UI routing layer depends only on this
    orchestrator. ActivityReportOperations and UserService are always required.
    ReviewQueueOperations and UserContextBuilder are optional — callers receive
    a graceful Result.fail when unavailable.
    """

    def __init__(
        self,
        activity_report: ActivityReportOperations,
        user_service: UserService,
        review_queue: ReviewQueueOperations | None = None,
        context_builder: UserContextBuilder | None = None,
    ) -> None:
        self._activity_report = activity_report
        self._user_service = user_service
        self._review_queue = review_queue
        self._context_builder = context_builder

    @property
    def user_service(self) -> UserService:
        """Expose user service for admin role checks."""
        return self._user_service

    # --- Review Queue ---

    async def get_pending_reviews(
        self, admin_uid: UserUID, limit: int = 20
    ) -> Result[list[PendingReviewItem]]:
        """Return pending review requests. Empty list when queue service unavailable."""
        if self._review_queue is None:
            return Result.ok([])
        return await self._review_queue.get_pending_reviews(_admin_uid=admin_uid, limit=limit)

    # --- Context ---

    async def build_rich_context(
        self, subject_uid: UserUID, window: str = "7d"
    ) -> Result[RichUserContext]:
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
        context: UserContext,
        admin_uid: UserUID,
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> Result[dict[str, Any]]:
        """Build activity snapshot from pre-built UserContext.

        The period is the subject's: its days are days in the subject's zone,
        not the reviewing admin's. ``admin_uid`` is recorded on the subject's
        access audit (``ActivitySnapshotAccessed``).
        """
        zone = await self._user_service.get_user_zone(context.user_uid)
        if zone.is_error:
            return Result.fail(zone)
        with zone_scope(zone.value):
            return await self._activity_report.create_snapshot(
                context=context,
                time_period=time_period,
                domains=domains,
                admin_uid=admin_uid,
            )

    async def submit_report(
        self,
        admin_uid: UserUID,
        subject_uid: UserUID,
        feedback_text: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        snapshot_context: dict[str, Any] | None = None,  # boundary: the snapshot JSON
        review_request_uid: str | None = None,
    ) -> Result[SubmittedReview]:
        """Create ActivityReport from admin-written assessment.

        The subject must be a user: the report is written as theirs (owner and
        bell — Submit & Share arc R10/R11), so a mistyped uid would file a report nobody
        can open. An unknown subject is a validation error on ``subject_uid``.

        ``snapshot_context`` (the snapshot the admin read) is stored with the report,
        and refused when it names another user. A review answering ``review_request_uid`` is refused unless that request is
        the subject's and still pending; once the report is written, the request is
        closed and linked to it.
        """
        subject = await self._user_service.get_user(subject_uid)
        if subject.is_error:
            return Result.fail(subject)
        if subject.value is None:
            return Result.fail(
                Errors.validation(
                    message=f"No user with uid {subject_uid!r}",
                    field="subject_uid",
                )
            )
        snapshot_subject = (snapshot_context or {}).get("subject_uid")
        if snapshot_subject is not None and snapshot_subject != subject_uid:
            return Result.fail(
                Errors.validation(
                    message="The snapshot is of another user; load this user's snapshot",
                    field="snapshot_context",
                )
            )
        if review_request_uid:
            if self._review_queue is None:
                return Result.fail(
                    Errors.system(message="Review queue not configured", service="review_queue")
                )
            pending = await self._review_queue.is_pending_for(review_request_uid, subject_uid)
            if pending.is_error:
                return Result.fail(pending)
            if not pending.value:
                return Result.fail(
                    Errors.validation(
                        message="That review request is no longer pending for this user",
                        field="review_request_uid",
                    )
                )
        # The reviewed period is the subject's, in the subject's zone.
        with zone_scope(subject.value.zone()):
            written = await self._activity_report.submit_report(
                admin_uid=admin_uid,
                subject_uid=subject_uid,
                feedback_text=feedback_text,
                time_period=time_period,
                domains=domains,
                snapshot_context=snapshot_context,
            )
        if written.is_error:
            return Result.fail(written)
        report = written.value
        if not review_request_uid or self._review_queue is None:
            return Result.ok(SubmittedReview(report))
        closed = await self._review_queue.answer_request(
            review_request_uid, subject_uid, report.uid
        )
        if closed.is_error:
            logger.error(
                f"Report {report.uid} written but request {review_request_uid} not closed: "
                f"{closed.expect_error().message}"
            )
            return Result.ok(SubmittedReview(report, request_closed=False))
        return Result.ok(SubmittedReview(report, request_closed=closed.value))
