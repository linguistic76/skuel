"""
Review Queue Service
=====================

Manages ReviewRequest nodes — the lightweight queue mechanism that lets users
request a human activity review from an admin.

This is deliberately separate from ActivityReportService because ReviewRequest
is a different entity type with a different lifecycle:
    User creates ReviewRequest → admin sees it in queue → admin writes ActivityReport

ReviewRequest nodes are not ActivityReport entities. They are transient workflow
markers consumed when the admin completes the review.

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID
from core.ports.query_types import PendingReviewItem, ReviewRequestResult

if TYPE_CHECKING:
    from adapters.persistence.neo4j.backends.collab_backends import ReviewQueueBackend

from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.report.review_queue")


class ReviewQueueService:
    """
    Manages ReviewRequest nodes for the admin review queue.

    Users call request_review() to signal they want an admin to review their
    Activity Domain data. Admins call get_pending_reviews() to see the queue.
    """

    def __init__(self, backend: "ReviewQueueBackend") -> None:
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

        Creates a lightweight review request node in Neo4j for admin queuing.

        Args:
            user_uid: User requesting the review
            time_period: Preferred time window for review
            domains: Preferred domains to review
            message: Optional context message from the user

        Returns:
            Result[ReviewRequestResult] — the created review request with uid
        """
        try:
            request_uid = UIDGenerator.generate_uid("review_request")
            now = datetime.now().isoformat()

            result = await self.backend.create_review_request(
                user_uid=user_uid,
                uid=request_uid,
                time_period=time_period,
                domains=domains or [],
                message=message or "",
                now=now,
            )

            if result.is_error:
                return Result.fail(result)

            logger.info(f"Review request created: {request_uid} for {user_uid}")
            return Result.ok({"uid": request_uid, "status": "pending", "user_uid": user_uid})

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to create review request for {user_uid}: {e}")
            return Result.fail(
                Errors.database(
                    operation="request_review", message=f"Failed to request review: {e}"
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            logger.error(f"Unexpected error creating review request for {user_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to request review: {e}"))

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
        try:
            result = await self.backend.get_pending_reviews(limit=limit)

            if result.is_error:
                return Result.fail(result)

            return Result.ok(result.value or [])

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get pending reviews: {e}")
            return Result.fail(
                Errors.database(
                    operation="get_pending_reviews",
                    message=f"Failed to retrieve pending reviews: {e}",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            logger.error(f"Unexpected error getting pending reviews: {e}")
            return Result.fail(Errors.system(f"Failed to retrieve pending reviews: {e}"))
