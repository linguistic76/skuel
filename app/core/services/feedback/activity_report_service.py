"""
Activity Report Service
========================

Processor-neutral CRUD for ActivityReport entities. Owns all ActivityReport
persistence regardless of who authored it — human admin or AI.

Three creation paths all converge here:
    Admin-written:   submit_feedback() → ProcessorType.HUMAN
    AI-generated:    persist() called by ProgressFeedbackGenerator → ProcessorType.LLM / AUTOMATIC
    Scheduled:       persist() called by ProgressFeedbackWorker → ProcessorType.AUTOMATIC

Review queue management (ReviewRequest nodes) lives in ReviewQueueService.

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import BackendOperations, QueryExecutor
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.user.user_context_builder import UserContextBuilder

from core.constants import FeedbackTimePeriod
from core.events import publish_event
from core.events.submission_events import ActivitySnapshotAccessed
from core.models.enums.entity_enums import ProcessorType
from core.models.feedback.activity_report import ActivityReport
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.feedback.activity_report")


class ActivityReportService:
    """
    Processor-neutral CRUD for ActivityReport entities.

    Owns all ActivityReport persistence — the processor_type field (HUMAN, LLM,
    AUTOMATIC) is data, not a service boundary. Both admin-written feedback and
    AI-generated reports are stored via this service.

    ReviewRequest queue management lives in ReviewQueueService.
    """

    def __init__(
        self,
        backend: "BackendOperations[ActivityReport]",
        context_builder: "UserContextBuilder",
        executor: "QueryExecutor",
        event_bus: "EventBusOperations | None" = None,
    ) -> None:
        self.backend = backend
        self.context_builder = context_builder
        self.executor = executor
        self.event_bus = event_bus

    async def persist(self, report: ActivityReport) -> Result[ActivityReport]:
        """
        Persist an already-constructed ActivityReport entity.

        Called by ProgressFeedbackGenerator after report construction so that
        persistence is owned by this service, not the orchestration layer.

        Args:
            report: Fully-constructed ActivityReport (all fields set by caller)

        Returns:
            Result[ActivityReport] — the persisted entity
        """
        return await self.backend.create(report)

    async def create_snapshot(
        self,
        subject_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        admin_uid: str = "",
    ) -> Result[dict[str, Any]]:
        """
        Query a user's activity data for a given time window.

        Produces a structured snapshot dict for admin review. The admin
        reads this data, then calls submit_feedback() with their
        written assessment.

        IMPORTANT: This method reads private user content across all activity
        domains. It MUST only be called from routes gated by @require_admin.
        See ADR-042 (Privacy as First-Class Citizen).

        Args:
            subject_uid: The user whose activity to snapshot
            time_period: Time window (7d, 14d, 30d, 90d)
            domains: Domains to include (None = all activity domains)
            admin_uid: UID of the admin performing the snapshot (used for audit trail)

        Returns:
            Result[dict] — snapshot data with per-domain activity summaries
        """
        days = FeedbackTimePeriod.DAYS.get(time_period, FeedbackTimePeriod.DEFAULT_DAYS)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        ctx_result = await self.context_builder.build_rich(subject_uid, window=time_period)
        if ctx_result.is_error:
            return Result.fail(ctx_result.expect_error())

        context = ctx_result.value

        # Publish audit event so the subject_uid can see when their data was accessed.
        # This enables the privacy audit endpoint (GET /api/privacy/audit) to surface
        # admin access history to the subject user. See ADR-042.
        event = ActivitySnapshotAccessed(
            subject_uid=subject_uid,
            admin_uid=admin_uid,
            time_period=time_period,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, logger)
        activity = context.entities_rich
        ku_rich = context.knowledge_units_rich
        mastery_scores = context.knowledge_mastery
        include_all = not domains
        snapshot: dict[str, Any] = {
            "subject_uid": subject_uid,
            "time_period": time_period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "domains": {},
        }

        tasks = activity.get("tasks", [])
        goals = activity.get("goals", [])
        habits = activity.get("habits", [])
        choices = activity.get("choices", [])
        events = activity.get("events", [])
        principles = activity.get("principles", [])

        if include_all or "tasks" in (domains or []):
            snapshot["domains"]["tasks"] = {
                "count": len(tasks),
                "completed": sum(
                    1 for item in tasks
                    if item.get("entity", {}).get("status") == "completed"
                ),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "status": item.get("entity", {}).get("status", ""),
                    }
                    for item in tasks[:10]
                ],
            }

        if include_all or "goals" in (domains or []):
            snapshot["domains"]["goals"] = {
                "count": len(goals),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "status": item.get("entity", {}).get("status", ""),
                        "progress": item.get("entity", {}).get("progress"),
                    }
                    for item in goals[:10]
                ],
            }

        if include_all or "habits" in (domains or []):
            snapshot["domains"]["habits"] = {
                "count": len(habits),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "status": item.get("entity", {}).get("status", ""),
                        "streak": item.get("entity", {}).get("streak", 0),
                    }
                    for item in habits[:10]
                ],
            }

        if include_all or "choices" in (domains or []):
            snapshot["domains"]["choices"] = {
                "count": len(choices),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "principles": [
                            ref.get("title", "")
                            for ref in item.get("graph_context", {}).get("principle_refs", [])
                            if ref.get("title")
                        ],
                    }
                    for item in choices[:10]
                ],
            }

        if include_all or "events" in (domains or []):
            snapshot["domains"]["events"] = {
                "count": len(events),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "status": item.get("entity", {}).get("status", ""),
                        "event_type": item.get("entity", {}).get("event_type", ""),
                        "is_milestone": item.get("graph_context", {}).get(
                            "is_milestone", False
                        ),
                    }
                    for item in events[:10]
                ],
            }

        if include_all or "principles" in (domains or []):
            snapshot["domains"]["principles"] = {
                "count": len(principles),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "status": item.get("entity", {}).get("status", ""),
                        "alignment": item.get("entity", {}).get("alignment"),
                    }
                    for item in principles[:10]
                ],
            }

        # Curriculum track — knowledge units
        if include_all or "knowledge" in (domains or []):
            mastered_uids = [uid for uid, score in mastery_scores.items() if score >= 0.8]
            in_progress_uids = [uid for uid, score in mastery_scores.items() if score < 0.8]
            snapshot["domains"]["knowledge"] = {
                "mastered_count": len(mastered_uids),
                "in_progress_count": len(in_progress_uids),
                "items": [
                    {
                        "title": ku_rich.get(uid, {}).get("ku", {}).get("title", uid),
                        "domain": ku_rich.get(uid, {}).get("ku", {}).get("domain", ""),
                        "score": mastery_scores[uid],
                    }
                    for uid in list(mastery_scores.keys())[:10]
                ],
            }

        # Curriculum track — learning paths
        if include_all or "learning_paths" in (domains or []):
            lp_items = activity.get("learning_paths", [])
            snapshot["domains"]["learning_paths"] = {
                "count": len(lp_items),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title")
                            or item.get("entity", {}).get("name", ""),
                        "total_steps": item.get("graph_context", {}).get("total_steps", 0),
                        "completed_steps": item.get("graph_context", {}).get("completed_steps", 0),
                        "progress_pct": item.get("graph_context", {}).get("progress_percentage", 0.0),
                    }
                    for item in lp_items[:10]
                ],
            }

        # Curriculum track — active learning steps
        if include_all or "learning_steps" in (domains or []):
            ls_items = activity.get("learning_steps", [])
            snapshot["domains"]["learning_steps"] = {
                "count": len(ls_items),
                "items": [
                    {
                        "title": item.get("entity", {}).get("title", ""),
                        "status": item.get("entity", {}).get("status", ""),
                        "learning_path": (
                            item.get("graph_context", {}).get("learning_path") or {}
                        ).get("name", ""),
                    }
                    for item in ls_items[:10]
                ],
            }

        return Result.ok(snapshot)

    async def submit_feedback(
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
        days = FeedbackTimePeriod.DAYS.get(time_period, FeedbackTimePeriod.DEFAULT_DAYS)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        try:
            metadata: dict[str, Any] = {
                "reviewed_by": admin_uid,
                "time_period": time_period,
                "review_date": datetime.now().isoformat(),
            }
            if snapshot_context:
                metadata["snapshot"] = snapshot_context

            feedback = ActivityReport.create(
                user_uid=admin_uid,
                subject_uid=subject_uid,
                content=feedback_text,
                processor_type=ProcessorType.HUMAN,
                period_start=start_date,
                period_end=end_date,
                time_period=time_period,
                domains=domains,
                metadata=metadata,
            )

            create_result = await self.persist(feedback)
            if create_result.is_error:
                return Result.fail(create_result.expect_error())

            logger.info(
                f"Activity review created: {feedback.uid} by {admin_uid} for {subject_uid}"
            )
            return Result.ok(feedback)

        except Exception as e:
            logger.error(f"Failed to submit activity feedback: {e}")
            return Result.fail(Errors.system(f"Failed to submit activity feedback: {e}"))

    async def get_history(
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
                    Errors.not_found(f"ActivityReport {uid} not found or not owned by {user_uid}")
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
                    Errors.not_found(f"ActivityReport {uid} not found or not owned by {user_uid}")
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

    async def get_privacy_summary(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Return a privacy-transparency summary for the authenticated user.

        Three data points:
            admin_snapshots  — ActivityReports written by admins about this user
                               (processor_type=human, subject_uid=user_uid)
            shares_granted   — Users who currently have SHARES_WITH access to
                               the user's entities
            report_schedule  — Current automatic report schedule + last generated

        Used by GET /api/privacy/audit. User-facing — always scoped to the
        requesting user's own data. No admin privileges required.

        Args:
            user_uid: Authenticated user requesting their own privacy summary

        Returns:
            Result[dict] — privacy summary with admin_snapshots, shares_granted,
                           and report_schedule sections
        """
        try:
            # 1. Admin-written ActivityReports received by this user
            admin_snapshots_result = await self.executor.execute_query(
                """
                MATCH (n:Entity {ku_type: 'activity_report', subject_uid: $user_uid})
                WHERE n.processor_type = 'human'
                RETURN n.created_at AS accessed_at,
                       n.user_uid AS admin_uid,
                       n.time_period AS time_period
                ORDER BY n.created_at DESC
                LIMIT 50
                """,
                {"user_uid": user_uid},
            )
            admin_snapshots: list[dict[str, Any]] = []
            if admin_snapshots_result.is_ok:
                for record in admin_snapshots_result.value or []:
                    admin_snapshots.append(
                        {
                            "accessed_at": (
                                str(record.get("accessed_at"))
                                if record.get("accessed_at")
                                else None
                            ),
                            "admin_uid": record.get("admin_uid", ""),
                            "time_period": record.get("time_period", ""),
                        }
                    )

            # 2. Users with active SHARES_WITH access to this user's entities
            shares_result = await self.executor.execute_query(
                """
                MATCH (accessor:User)-[sw:SHARES_WITH]->(e:Entity {user_uid: $user_uid})
                RETURN accessor.uid AS accessor_uid,
                       e.uid AS entity_uid,
                       e.title AS entity_title,
                       sw.role AS role,
                       sw.shared_at AS shared_at
                ORDER BY sw.shared_at DESC
                LIMIT 100
                """,
                {"user_uid": user_uid},
            )
            shares_granted: list[dict[str, Any]] = []
            if shares_result.is_ok:
                for record in shares_result.value or []:
                    shares_granted.append(
                        {
                            "accessor_uid": record.get("accessor_uid", ""),
                            "entity_uid": record.get("entity_uid", ""),
                            "entity_title": record.get("entity_title", ""),
                            "role": record.get("role", ""),
                            "shared_at": (
                                str(record.get("shared_at"))
                                if record.get("shared_at")
                                else None
                            ),
                        }
                    )

            # 3. Active report schedule + last generated report
            schedule_result = await self.executor.execute_query(
                """
                MATCH (u:User {uid: $user_uid})-[:HAS_SCHEDULE]->(s:KuSchedule)
                WHERE s.is_active = true
                RETURN s.schedule_type AS schedule_type,
                       s.day_of_week AS day_of_week,
                       s.next_due_at AS next_due_at,
                       s.last_generated_at AS last_generated_at
                LIMIT 1
                """,
                {"user_uid": user_uid},
            )
            report_schedule: dict[str, Any] = {"active": False}
            if schedule_result.is_ok and schedule_result.value:
                record = schedule_result.value[0]
                report_schedule = {
                    "active": True,
                    "schedule_type": record.get("schedule_type", ""),
                    "day_of_week": record.get("day_of_week"),
                    "next_due_at": (
                        str(record.get("next_due_at")) if record.get("next_due_at") else None
                    ),
                    "last_generated_at": (
                        str(record.get("last_generated_at"))
                        if record.get("last_generated_at")
                        else None
                    ),
                }

            return Result.ok(
                {
                    "user_uid": user_uid,
                    "admin_snapshots": admin_snapshots,
                    "admin_snapshot_count": len(admin_snapshots),
                    "shares_granted": shares_granted,
                    "shares_granted_count": len(shares_granted),
                    "report_schedule": report_schedule,
                }
            )

        except Exception as e:
            logger.error(f"Failed to get privacy summary for {user_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to retrieve privacy summary: {e}"))
