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

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import QueryExecutor

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.feedback.review_queue")


class ReviewQueueService:
    """
    Manages ReviewRequest nodes for the admin review queue.

    Users call request_review() to signal they want an admin to review their
    Activity Domain data. Admins call get_pending_reviews() to see the queue.
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        self.executor = executor

    async def request_review(
        self,
        user_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        message: str | None = None,
    ) -> Result[dict[str, Any]]:
        """
        User requests an activity review from an admin.

        Creates a lightweight review request node in Neo4j for admin queuing.

        Args:
            user_uid: User requesting the review
            time_period: Preferred time window for review
            domains: Preferred domains to review
            message: Optional context message from the user

        Returns:
            Result[dict] — the created review request with uid
        """
        try:
            request_uid = UIDGenerator.generate_uid("review_request")
            now = datetime.now().isoformat()

            result = await self.executor.execute_query(
                """
                MATCH (u:User {uid: $user_uid})
                CREATE (r:ReviewRequest {
                    uid: $uid,
                    user_uid: $user_uid,
                    time_period: $time_period,
                    domains: $domains,
                    message: $message,
                    status: 'pending',
                    created_at: datetime($now)
                })
                CREATE (u)-[:REQUESTED]->(r)
                RETURN r.uid AS uid, r.status AS status
                """,
                {
                    "user_uid": user_uid,
                    "uid": request_uid,
                    "time_period": time_period,
                    "domains": domains or [],
                    "message": message or "",
                    "now": now,
                },
            )

            if result.is_error:
                return Result.fail(result.expect_error())

            logger.info(f"Review request created: {request_uid} for {user_uid}")
            return Result.ok({"uid": request_uid, "status": "pending", "user_uid": user_uid})

        except Exception as e:
            logger.error(f"Failed to create review request for {user_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to request review: {e}"))

    async def get_pending_reviews(
        self,
        _admin_uid: str,
        limit: int = 20,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get pending review requests for admin to action.

        Args:
            _admin_uid: Admin user (placeholder — future: filter by assigned admin)
            limit: Maximum number of results

        Returns:
            Result[list[dict]] — pending review requests with user context
        """
        try:
            result = await self.executor.execute_query(
                """
                MATCH (u:User)-[:REQUESTED]->(r:ReviewRequest {status: 'pending'})
                RETURN r.uid AS uid, r.user_uid AS user_uid, r.time_period AS time_period,
                       r.domains AS domains, r.message AS message, r.created_at AS created_at,
                       u.username AS username
                ORDER BY r.created_at ASC
                LIMIT $limit
                """,
                {"limit": limit},
            )

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(result.value or [])

        except Exception as e:
            logger.error(f"Failed to get pending reviews: {e}")
            return Result.fail(Errors.system(f"Failed to retrieve pending reviews: {e}"))
