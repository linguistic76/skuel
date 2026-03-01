"""
Activity Review Service
========================

Enables admin-written activity feedback for users. Admin reviews a user's
Activity Domain data (a "snapshot") and writes structured feedback stored
as EntityType.ACTIVITY_REPORT with ProcessorType.HUMAN.

Two trigger paths:
    Admin-initiated: Admin views a user's snapshot → writes feedback
    User-initiated:  User requests a review → appears in admin queue

This is the "human" counterpart to ProgressFeedbackGenerator (which uses
ProcessorType.AUTOMATIC or LLM). Both produce ActivityReport entities.

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import BackendOperations, QueryExecutor

from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.feedback.activity_report import ActivityReport
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.feedback.activity_review")

TIME_PERIOD_DAYS = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
}


class ActivityReviewService:
    """
    Admin-facing service for human activity domain feedback.

    Creates ActivityReport entities with ProcessorType.HUMAN — the admin reads
    a user's activity snapshot and writes qualitative feedback.

    Complements ProgressFeedbackGenerator (automated/LLM path) with the
    human-review path for the same ActivityReport entity type.
    """

    def __init__(
        self,
        executor: "QueryExecutor",
        ai_feedback_backend: "BackendOperations[ActivityReport]",
    ) -> None:
        self.executor = executor
        self.ai_feedback_backend = ai_feedback_backend

    async def create_activity_snapshot(
        self,
        subject_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Query a user's activity data for a given time window.

        Produces a structured snapshot dict for admin review. The admin
        reads this data, then calls submit_activity_feedback() with their
        written assessment.

        IMPORTANT: This method reads private user content across all activity
        domains. It MUST only be called from routes gated by @require_admin.
        See ADR-042 (Privacy as First-Class Citizen).

        Args:
            subject_uid: The user whose activity to snapshot
            time_period: Time window (7d, 14d, 30d, 90d)
            domains: Domains to include (None = all activity domains)

        Returns:
            Result[dict] — snapshot data with per-domain activity summaries
        """
        days = TIME_PERIOD_DAYS.get(time_period, 7)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        try:
            snapshot: dict[str, Any] = {
                "subject_uid": subject_uid,
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "domains": {},
            }

            include_all = not domains

            if include_all or "tasks" in (domains or []):
                tasks_result = await self.executor.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
                    WHERE t.updated_at >= datetime($start) AND t.updated_at <= datetime($end)
                    RETURN t.uid AS uid, t.title AS title, t.status AS status,
                           t.priority AS priority
                    ORDER BY t.updated_at DESC LIMIT 20
                    """,
                    {
                        "user_uid": subject_uid,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                )
                if tasks_result.is_ok:
                    records = tasks_result.value or []
                    snapshot["domains"]["tasks"] = {
                        "count": len(records),
                        "completed": len([r for r in records if r.get("status") == "completed"]),
                        "items": [
                            {"title": r.get("title", ""), "status": r.get("status", "")}
                            for r in records[:10]
                        ],
                    }

            if include_all or "goals" in (domains or []):
                goals_result = await self.executor.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(g:Goal)
                    WHERE g.updated_at >= datetime($start) AND g.updated_at <= datetime($end)
                    RETURN g.uid AS uid, g.title AS title, g.status AS status,
                           g.progress AS progress
                    ORDER BY g.updated_at DESC LIMIT 10
                    """,
                    {
                        "user_uid": subject_uid,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                )
                if goals_result.is_ok:
                    records = goals_result.value or []
                    snapshot["domains"]["goals"] = {
                        "count": len(records),
                        "items": [
                            {
                                "title": r.get("title", ""),
                                "status": r.get("status", ""),
                                "progress": r.get("progress"),
                            }
                            for r in records[:10]
                        ],
                    }

            if include_all or "habits" in (domains or []):
                habits_result = await self.executor.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(h:Habit)
                    WHERE h.updated_at >= datetime($start) AND h.updated_at <= datetime($end)
                    RETURN h.uid AS uid, h.title AS title, h.status AS status,
                           h.streak_count AS streak
                    ORDER BY h.updated_at DESC LIMIT 10
                    """,
                    {
                        "user_uid": subject_uid,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                )
                if habits_result.is_ok:
                    records = habits_result.value or []
                    snapshot["domains"]["habits"] = {
                        "count": len(records),
                        "items": [
                            {
                                "title": r.get("title", ""),
                                "status": r.get("status", ""),
                                "streak": r.get("streak", 0),
                            }
                            for r in records[:10]
                        ],
                    }

            if include_all or "choices" in (domains or []):
                choices_result = await self.executor.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Choice)
                    WHERE c.created_at >= datetime($start) AND c.created_at <= datetime($end)
                    OPTIONAL MATCH (c)-[:INFORMED_BY_PRINCIPLE]->(p:Principle)
                    RETURN c.uid AS uid, c.title AS title,
                           collect(DISTINCT p.title) AS principles
                    ORDER BY c.created_at DESC LIMIT 10
                    """,
                    {
                        "user_uid": subject_uid,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                )
                if choices_result.is_ok:
                    records = choices_result.value or []
                    snapshot["domains"]["choices"] = {
                        "count": len(records),
                        "items": [
                            {
                                "title": r.get("title", ""),
                                "principles": [p for p in r.get("principles", []) if p],
                            }
                            for r in records[:10]
                        ],
                    }

            return Result.ok(snapshot)

        except Exception as e:
            logger.error(f"Failed to create activity snapshot for {subject_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to create activity snapshot: {e}"))

    async def submit_activity_feedback(
        self,
        admin_uid: str,
        subject_uid: str,
        feedback_text: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        snapshot_context: dict[str, Any] | None = None,
    ) -> Result[ActivityReport]:
        """
        Create an ActivityReport entity from admin-written activity assessment.

        Stores as EntityType.ACTIVITY_REPORT with ProcessorType.HUMAN.
        The admin_uid becomes owner (user_uid), subject_uid tracks who was reviewed.

        IMPORTANT: This method writes to another user's activity record.
        It MUST only be called from routes gated by @require_admin.
        See ADR-042 (Privacy as First-Class Citizen).

        Args:
            admin_uid: Admin user creating the feedback
            subject_uid: User whose activity was reviewed
            feedback_text: Admin's written assessment
            time_period: Time window reviewed (7d, 14d, 30d, 90d)
            domains: Domains covered in the review
            snapshot_context: Optional snapshot data to store in metadata

        Returns:
            Result[ActivityReport] — the created feedback entity
        """
        days = TIME_PERIOD_DAYS.get(time_period, 7)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        try:
            uid = UIDGenerator.generate_uid("ku")
            title = (
                f"Activity Review — {subject_uid} "
                f"({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
            )
            metadata: dict[str, Any] = {
                "reviewed_by": admin_uid,
                "time_period": time_period,
                "review_date": datetime.now().isoformat(),
            }
            if snapshot_context:
                metadata["snapshot"] = snapshot_context

            feedback = ActivityReport(
                uid=uid,
                title=title,
                ku_type=EntityType.ACTIVITY_REPORT,
                user_uid=admin_uid,
                status=EntityStatus.COMPLETED,
                processor_type=ProcessorType.HUMAN,
                processed_content=feedback_text,
                subject_uid=subject_uid,
                time_period=time_period,
                period_start=start_date,
                period_end=end_date,
                domains_covered=tuple(domains) if domains else (),
                depth="standard",
                metadata=metadata,
            )

            create_result = await self.ai_feedback_backend.create(feedback)
            if create_result.is_error:
                return Result.fail(create_result.expect_error())

            logger.info(f"Activity review created: {uid} by {admin_uid} for {subject_uid}")
            return Result.ok(feedback)

        except Exception as e:
            logger.error(f"Failed to submit activity feedback: {e}")
            return Result.fail(Errors.system(f"Failed to submit activity feedback: {e}"))

    async def get_activity_reviews_for_user(
        self,
        subject_uid: str,
        limit: int = 20,
    ) -> Result[list[ActivityReport]]:
        """
        Get all ActivityReport entities where subject_uid matches the user.

        Returns both LLM-generated (AUTOMATIC/LLM) and human-written (HUMAN)
        feedback for the given user.

        Args:
            subject_uid: User to retrieve feedback for
            limit: Maximum number of results

        Returns:
            Result[list[ActivityReport]]
        """
        try:
            query_result = await self.executor.execute_query(
                """
                MATCH (n:Entity {ku_type: 'activity_report', subject_uid: $subject_uid})
                RETURN n
                ORDER BY n.created_at DESC
                LIMIT $limit
                """,
                {"subject_uid": subject_uid, "limit": limit},
            )

            if query_result.is_error:
                return Result.fail(query_result.expect_error())

            records = query_result.value or []
            feedbacks = []
            for record in records:
                node = record.get("n") if isinstance(record, dict) else record
                if node:
                    props = dict(node) if not isinstance(node, dict) else node
                    feedbacks.append(ActivityReport._from_dict(props))  # type: ignore[attr-defined]

            return Result.ok(feedbacks)

        except Exception as e:
            logger.error(f"Failed to get activity reviews for {subject_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to retrieve activity reviews: {e}"))

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

    async def annotate(
        self,
        uid: str,
        user_uid: str,
        annotation_mode: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Save user annotation or revision to an owned ActivityReport.

        Two modes:
            additive — user_annotation is stored alongside processed_content (original preserved)
            revision — user_revision replaces processed_content when sharing

        Args:
            uid: ActivityReport uid to annotate
            user_uid: Owner making the annotation (ownership enforced via query)
            annotation_mode: "additive" | "revision"
            user_annotation: Commentary text (required for additive mode)
            user_revision: Replacement text (required for revision mode)

        Returns:
            Result[dict] — saved annotation fields
        """
        if annotation_mode not in ("additive", "revision"):
            return Result.fail(
                Errors.validation(
                    "annotation_mode must be 'additive' or 'revision'",
                    field="annotation_mode",
                )
            )
        if annotation_mode == "additive" and not user_annotation:
            return Result.fail(
                Errors.validation(
                    "user_annotation required for additive mode",
                    field="user_annotation",
                )
            )
        if annotation_mode == "revision" and not user_revision:
            return Result.fail(
                Errors.validation(
                    "user_revision required for revision mode",
                    field="user_revision",
                )
            )
        try:
            now = datetime.now().isoformat()
            result = await self.executor.execute_query(
                """
                MATCH (n:Entity {uid: $uid, user_uid: $user_uid, ku_type: 'activity_report'})
                SET n.annotation_mode = $annotation_mode,
                    n.annotation_updated_at = datetime($now),
                    n.user_annotation = $user_annotation,
                    n.user_revision = $user_revision
                RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                       n.user_annotation AS user_annotation, n.user_revision AS user_revision
                """,
                {
                    "uid": uid,
                    "user_uid": user_uid,
                    "annotation_mode": annotation_mode,
                    "now": now,
                    "user_annotation": user_annotation,
                    "user_revision": user_revision,
                },
            )
            if result.is_error:
                return Result.fail(result.expect_error())
            records = result.value or []
            if not records:
                return Result.fail(
                    Errors.not_found(
                        f"ActivityReport {uid} not found or not owned by {user_uid}"
                    )
                )
            record = records[0] if isinstance(records[0], dict) else dict(records[0])
            return Result.ok(
                {
                    "uid": record.get("uid"),
                    "annotation_mode": record.get("annotation_mode"),
                    "user_annotation": record.get("user_annotation"),
                    "user_revision": record.get("user_revision"),
                }
            )
        except Exception as e:
            logger.error(f"Failed to annotate ActivityReport {uid}: {e}")
            return Result.fail(Errors.system(f"Failed to save annotation: {e}"))

    async def get_annotation(self, uid: str, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get current annotation state for an owned ActivityReport.

        Args:
            uid: ActivityReport uid
            user_uid: Owner requesting the annotation (ownership enforced via query)

        Returns:
            Result[dict] — current annotation fields (may all be None if not yet annotated)
        """
        try:
            result = await self.executor.execute_query(
                """
                MATCH (n:Entity {uid: $uid, user_uid: $user_uid, ku_type: 'activity_report'})
                RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                       n.user_annotation AS user_annotation, n.user_revision AS user_revision,
                       n.annotation_updated_at AS annotation_updated_at
                """,
                {"uid": uid, "user_uid": user_uid},
            )
            if result.is_error:
                return Result.fail(result.expect_error())
            records = result.value or []
            if not records:
                return Result.fail(
                    Errors.not_found(
                        f"ActivityReport {uid} not found or not owned by {user_uid}"
                    )
                )
            record = records[0] if isinstance(records[0], dict) else dict(records[0])
            annotation_updated_at = record.get("annotation_updated_at")
            return Result.ok(
                {
                    "uid": record.get("uid"),
                    "annotation_mode": record.get("annotation_mode"),
                    "user_annotation": record.get("user_annotation"),
                    "user_revision": record.get("user_revision"),
                    "annotation_updated_at": (
                        str(annotation_updated_at) if annotation_updated_at else None
                    ),
                }
            )
        except Exception as e:
            logger.error(f"Failed to get annotation for ActivityReport {uid}: {e}")
            return Result.fail(Errors.system(f"Failed to retrieve annotation: {e}"))

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
