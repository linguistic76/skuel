"""
Review Queue Service
=====================

Manages ReviewRequest nodes — the lightweight queue mechanism that lets users
request a human activity review from an admin.

This is deliberately separate from ActivityReportService because ReviewRequest
is a different entity type with a different lifecycle:
    User creates ReviewRequest → admin sees it in queue → admin writes ActivityReport

ReviewRequest nodes are not ActivityReport entities. They are workflow markers:
pending until the admin's review is written, then answered and linked to that
report (ANSWERED_BY).

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import PendingReviewItem, ReviewRequestResult

if TYPE_CHECKING:
    from core.ports.report_protocols import ReviewQueueBackendOperations

from core.utils.logging import get_logger
from core.utils.neo4j_props import neo4j_str, neo4j_str_list
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.report.review_queue")


class ReviewQueueService:
    """
    Manages ReviewRequest nodes for the admin review queue.

    A learner calls request_review() to ask an admin to review their Activity
    Domain data, and holds one pending request at a time. Admins read the queue
    with get_pending_reviews(); writing the review closes the request it answers
    (answer_request).
    """

    def __init__(self, backend: ReviewQueueBackendOperations) -> None:
        self.backend = backend

    async def request_review(
        self,
        user_uid: UserUID,
        time_period: str = "7d",
        domains: list[str] | None = None,
        message: str | None = None,
    ) -> Result[ReviewRequestResult]:
        """
        User requests an activity review from an admin.

        A learner who already holds a pending request gets that one back
        (``created`` false) and nothing new is queued. An unknown user is a
        not-found failure.

        Args:
            user_uid: User requesting the review
            time_period: The report-period token to review
            domains: Activity domains to review (none = all)
            message: Optional context message from the user

        Returns:
            Result[ReviewRequestResult] — the learner's pending request
        """
        request_uid = UIDGenerator.generate_random_uid("rr")
        result = await self.backend.create_review_request(
            user_uid=user_uid,
            uid=request_uid,
            time_period=time_period,
            domains=domains or [],
            message=message or "",
            now=datetime.now().isoformat(),
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows:
            return Result.fail(Errors.not_found("User", user_uid))

        request = _request_from_row(rows[0])
        request["created"] = bool(rows[0].get("created"))
        if request["created"]:
            logger.info(f"Review request created: {request['uid']} for {user_uid}")
        return Result.ok(request)

    async def get_pending_request(self, user_uid: UserUID) -> Result[ReviewRequestResult | None]:
        """The learner's pending request, or None when they hold none."""
        result = await self.backend.get_pending_request(user_uid)
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        return Result.ok(_request_from_row(rows[0]) if rows else None)

    async def get_pending_reviews(
        self,
        _admin_uid: str,
        limit: int = 20,
    ) -> Result[list[PendingReviewItem]]:
        """
        Get pending review requests for admin to action.

        Args:
            _admin_uid: Admin user (placeholder — future: filter by assigned admin)
            limit: Maximum number of results

        Returns:
            Result[list[PendingReviewItem]] — pending review requests with user context
        """
        result = await self.backend.get_pending_reviews(limit=limit)
        if result.is_error:
            return Result.fail(result)

        items: list[PendingReviewItem] = [
            PendingReviewItem(
                uid=neo4j_str(row, "uid", ""),
                user_uid=neo4j_str(row, "user_uid", ""),
                time_period=neo4j_str(row, "time_period", ""),
                domains=neo4j_str_list(row, "domains"),
                message=neo4j_str(row, "message", ""),
                created_at=neo4j_str(row, "created_at", ""),
                username=neo4j_str(row, "username", ""),
            )
            for row in (result.value or [])
        ]
        return Result.ok(items)

    async def is_pending_for(self, request_uid: str, subject_uid: UserUID) -> Result[bool]:
        """Whether ``request_uid`` is a pending request that ``subject_uid`` made."""
        return await self.backend.is_pending_for(request_uid, subject_uid)

    async def answer_request(
        self, request_uid: str, subject_uid: UserUID, report_uid: str
    ) -> Result[bool]:
        """Close the subject's pending request: answered, linked to the report.

        False when it was not pending (answered by another review meanwhile, or
        not the subject's); nothing changes then.
        """
        return await self.backend.answer_review_request(
            request_uid, subject_uid, report_uid, datetime.now().isoformat()
        )


def _request_from_row(row: Neo4jProperties) -> ReviewRequestResult:
    """A request row as the typed result (``created`` is the writer's to add)."""
    return ReviewRequestResult(
        uid=neo4j_str(row, "uid", ""),
        status=neo4j_str(row, "status", ""),
        user_uid=neo4j_str(row, "user_uid", ""),
        time_period=neo4j_str(row, "time_period", ""),
        domains=neo4j_str_list(row, "domains"),
        message=neo4j_str(row, "message", ""),
        created_at=neo4j_str(row, "created_at", ""),
    )
