"""
Activity Report Service
========================

Processor-neutral CRUD for ActivityReport entities. Owns all ActivityReport
persistence regardless of who authored it — human admin or AI.

Three creation paths all converge here:
    Admin-written:   submit_report() → ReportSource.HUMAN
    AI-generated:    persist() called by ProgressReportGenerator → ReportSource.LLM / AUTOMATIC
    Scheduled:       persist() called by ProgressReportWorker → ReportSource.AUTOMATIC

Review queue management (ReviewRequest nodes) lives in ReviewQueueService.

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from collections.abc import Mapping
from datetime import datetime
from itertools import islice
from typing import TYPE_CHECKING, Any, cast

from core.models.type_hints import Neo4jProperties, TypeConverter, UserUID
from core.ports.query_types import AnnotationResult, AnnotationState, PrivacySummary
from core.ports.report_protocols import ActivityReportBackendOperations

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.user.unified_user_context import UserContext
    from core.services.user.user_context_builder import UserContextBuilder

from core.events import publish_event
from core.events.learning_loop_events import ActivitySnapshotAccessed
from core.models.enums.pipeline import ReportSource
from core.models.report.activity_report import ActivityReport
from core.models.report.activity_report_dto import ActivityReportDTO
from core.services.report.period_eligibility import PeriodEligibility
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.report_periods import (
    UnknownReportPeriodError,
    as_naive_utc,
    resolve_report_period,
)
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.report.activity_report")


def _report_from_props(props: Neo4jProperties) -> ActivityReport:
    """A stored ActivityReport node's properties as the domain model — through
    the DTO's parse layer (``dto_from_dict``), the one place JSON blobs such as
    ``metadata`` and the temporal fields are decoded."""
    return ActivityReport.from_dto(ActivityReportDTO.from_dict(props))


class ActivityReportService:
    """
    Processor-neutral CRUD for ActivityReport entities.

    Owns all ActivityReport persistence — the processor_type field (HUMAN, LLM,
    AUTOMATIC) is data, not a service boundary. Both admin-written reports and
    AI-generated reports are stored via this service.

    ReviewRequest queue management lives in ReviewQueueService.
    """

    def __init__(
        self,
        backend: ActivityReportBackendOperations,
        context_builder: "UserContextBuilder",
        event_bus: "EventBusOperations",
    ) -> None:
        self.backend = backend
        self.context_builder = context_builder
        self.event_bus = event_bus

    async def persist(self, report: ActivityReport) -> Result[ActivityReport]:
        """
        Persist an already-constructed ActivityReport entity.

        Called by ProgressReportGenerator after report construction so that
        persistence is owned by this service, not the orchestration layer.

        Args:
            report: Fully-constructed ActivityReport (all fields set by caller)

        Returns:
            Result[ActivityReport] — the persisted entity
        """
        return await self.backend.create(report)

    async def create_snapshot(
        self,
        context: "UserContext",
        time_period: str = "7d",
        domains: list[str] | None = None,
        admin_uid: str = "",
    ) -> Result[dict[str, Any]]:
        """
        Build a structured snapshot from a pre-built UserContext for admin review.

        The admin reads this data, then calls submit_feedback() with their
        written assessment.

        IMPORTANT: This method reads private user content across all activity
        domains. It MUST only be called from routes gated by @require_admin.
        See ADR-042 (Privacy as First-Class Citizen).

        Args:
            context: UserContext built with build_rich(subject_uid, window=time_period)
            time_period: The report-period token (trailing ``7d`` … ``90d`` or a
                calendar ``2026-W37`` / ``2026-09``); counted up to its data cutoff
            domains: Domains to include (None = all activity domains)
            admin_uid: UID of the admin performing the snapshot (used for audit trail)

        Returns:
            Result[dict] — snapshot data with per-domain activity summaries
        """
        subject_uid = context.user_uid
        now = datetime.now()
        try:
            period = resolve_report_period(time_period, now)
        except UnknownReportPeriodError as e:
            return Result.fail(Errors.validation(message=str(e), field="time_period"))
        if not period.has_started(now):
            return Result.fail(
                Errors.validation(
                    message=f"{period.label} has not started yet", field="time_period"
                )
            )
        start_date, end_date = period.start, period.data_cutoff(now)

        # Publish audit event so the subject_uid can later see when their data was accessed.
        # This is the producer feeding the staged privacy-transparency surface
        # (get_privacy_summary, PLANNED tier per ADR-069 §3); a /privacy route + UI will
        # surface this admin access history to the subject user. See ADR-042.
        event = ActivitySnapshotAccessed(
            subject_uid=subject_uid,
            admin_uid=admin_uid,
            time_period=time_period,
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

        # The context is the CURRENT inventory plus what was touched since the
        # period's start, with no upper bound; the snapshot admits what the
        # period's report would — the generator's own predicates.
        eligible = PeriodEligibility.for_window(start_date, end_date, period.end)

        def _entity(item: Mapping[str, Any]) -> Mapping[str, Any]:
            return item.get("entity") or {}

        tasks = [item for item in activity.get("tasks", []) if eligible.task_in_play(_entity(item))]
        goals = [
            item for item in activity.get("goals", []) if eligible.existed_by_end(_entity(item))
        ]
        habits = [
            item for item in activity.get("habits", []) if eligible.existed_by_end(_entity(item))
        ]
        choices = [
            item for item in activity.get("choices", []) if eligible.existed_by_end(_entity(item))
        ]
        events = [
            item for item in activity.get("events", []) if eligible.event_in_window(_entity(item))
        ]
        principles = [
            item
            for item in activity.get("principles", [])
            if eligible.existed_by_end(_entity(item))
        ]
        streaks_are_current = not period.is_closed(now)

        if include_all or "tasks" in (domains or []):
            snapshot["domains"]["tasks"] = {
                "count": len(tasks),
                "completed": sum(eligible.completed_in_period(_entity(item)) for item in tasks),
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
                        "progress": item.get("entity", {}).get("progress_percentage"),
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
                        "streak": (
                            item.get("entity", {}).get("current_streak", 0)
                            if streaks_are_current
                            else None
                        ),
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
                            for ref in item.get("graph_context", {}).get("guiding_principles") or []
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
                        "is_milestone": bool(
                            item.get("entity", {}).get("is_milestone_event", False)
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
                        "alignment": item.get("entity", {}).get("current_alignment"),
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
                    for uid in islice(mastery_scores, 10)
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
                        "progress_pct": item.get("graph_context", {}).get(
                            "progress_percentage", 0.0
                        ),
                    }
                    for item in lp_items[:10]
                ],
            }

        # Curriculum track — active path steps
        if include_all or "path_steps" in (domains or []):
            ls_items = activity.get("path_steps", [])
            snapshot["domains"]["path_steps"] = {
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

    async def submit_report(
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

        Stores as EntityType.ACTIVITY_REPORT with ReportSource.HUMAN.
        The admin_uid becomes owner (user_uid), subject_uid tracks who was reviewed.

        IMPORTANT: This method writes to another user's activity record.
        It MUST only be called from routes gated by @require_admin.
        See ADR-042 (Privacy as First-Class Citizen).

        Args:
            admin_uid: Admin user creating the report
            subject_uid: User whose activity was reviewed
            feedback_text: Admin's written report
            time_period: The report-period token reviewed (trailing or calendar)
            domains: Domains covered in the review
            snapshot_context: Optional snapshot data to store in metadata

        Returns:
            Result[ActivityReport] — the created report entity
        """
        now = datetime.now()
        try:
            period = resolve_report_period(time_period, now)
        except UnknownReportPeriodError as e:
            return Result.fail(Errors.validation(message=str(e), field="time_period"))
        if not period.has_started(now):
            return Result.fail(
                Errors.validation(
                    message=f"{period.label} has not started yet", field="time_period"
                )
            )
        start_date, end_date = period.start, period.end
        # A human-authored report of a period still open is partial exactly as a
        # generated one: its cutoff is now, and the period door treats it alike.
        cutoff = period.data_cutoff(now)

        try:
            metadata: dict[str, Any] = {
                "reviewed_by": admin_uid,
                "time_period": time_period,
                "period_kind": period.kind.value,
                "period_end": end_date.isoformat(),
                "data_cutoff": cutoff.isoformat(),
                "is_partial": period.is_partial_at(cutoff),
                "review_date": now.isoformat(),
            }
            if snapshot_context:
                metadata["snapshot"] = snapshot_context

            feedback = ActivityReport.create(
                user_uid=TypeConverter.to_user_uid(admin_uid),
                subject_uid=subject_uid,
                content=feedback_text,
                processor_type=ReportSource.HUMAN,
                period_start=start_date,
                period_end=end_date,
                time_period=time_period,
                domains=domains,
                metadata=metadata,
                data_cutoff=cutoff,
            )

            create_result = await self.persist(feedback)
            if create_result.is_error:
                return Result.fail(create_result)

            logger.info(f"Activity review created: {feedback.uid} by {admin_uid} for {subject_uid}")
            return Result.ok(feedback)

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Database error submitting activity report: {e}")
            return Result.fail(
                Errors.database(
                    operation="submit_report", message=f"Failed to submit activity report: {e}"
                )
            )
        except DATA_CONVERSION_EXCEPTIONS as e:
            logger.error(f"Data conversion error submitting activity report: {e}")
            return Result.fail(Errors.system(f"Failed to submit activity report: {e}"))
        except Exception as e:  # safety-net: catch unexpected errors
            logger.error(f"Unexpected error submitting activity report: {e}")
            return Result.fail(Errors.system(f"Failed to submit activity report: {e}"))

    async def get_for_user(self, uid: str, user_uid: UserUID) -> Result[ActivityReport]:
        """
        Fetch a single ActivityReport by UID, scoped to the owning user.

        Args:
            uid: ActivityReport UID
            user_uid: Owning user UID (ownership check)

        Returns:
            Result[ActivityReport] — the report, or NotFound error
        """
        query_result = await self.backend.get_for_user(uid, user_uid)
        if query_result.is_error:
            return Result.fail(query_result)
        report = self._first_report(query_result.value or [])
        if report is None:
            return Result.fail(Errors.not_found("ActivityReport", uid))
        return Result.ok(report)

    async def get_latest_for_owner(self, user_uid: UserUID) -> Result[ActivityReport | None]:
        """The newest ActivityReport the user owns, or ``None`` when there is none.

        Owner-scoped (``user_uid``), not subject-scoped: a HUMAN report an admin
        authored about this user is a subject row the owner-scoped detail read
        refuses, so the "latest report" door must never select it.

        Backend: ``ActivityReportBackend.get_latest_for_owner``.
        """
        query_result = await self.backend.get_latest_for_owner(user_uid)
        if query_result.is_error:
            return Result.fail(query_result)
        return Result.ok(self._first_report(query_result.value or []))

    async def latest_for_period(
        self, user_uid: UserUID, subject_uid: str, time_period: str
    ) -> Result[ActivityReport | None]:
        """The newest report the user owns about ``subject_uid`` for one
        ``time_period`` token — partial or final — or ``None``.

        Backend: ``ActivityReportBackend.find_by_period`` (owner-scoped).
        """
        query_result = await self.backend.find_by_period(user_uid, subject_uid, time_period)
        if query_result.is_error:
            return Result.fail(query_result)
        return Result.ok(self._first_report(query_result.value or []))

    async def find_by_period(
        self, user_uid: UserUID, subject_uid: str, time_period: str
    ) -> Result[ActivityReport | None]:
        """The period's REUSABLE report, or ``None`` when the door should generate.

        The newest owned report for the token is reused while its period is
        still open (a partial report re-opens on every click) and, once the
        period has closed, only if it was counted up to the period's end. A
        report whose ``data_cutoff`` precedes ``period_end`` of a closed period
        is stale — treated as absent so the next open generates the final
        report that supersedes it. An unknown token is a validation failure.
        """
        now = datetime.now()
        try:
            period = resolve_report_period(time_period, now)
        except UnknownReportPeriodError as e:
            return Result.fail(Errors.validation(message=str(e), field="time_period"))
        latest = await self.latest_for_period(user_uid, subject_uid, time_period)
        if latest.is_error or latest.value is None:
            return latest
        report = latest.value
        cutoff = as_naive_utc(report.data_cutoff)
        if period.is_closed(now) and (cutoff is None or period.is_partial_at(cutoff)):
            return Result.ok(None)
        return Result.ok(report)

    @staticmethod
    def _first_report(records: list[Any]) -> ActivityReport | None:
        """The first row's node as a report, or ``None`` for no rows."""
        if not records:
            return None
        node = records[0]
        inner = node.get("n") if isinstance(node, dict) and "n" in node else node
        # Neo4j Node implements Mapping at runtime but isn't typed as such
        props = (
            cast("Neo4jProperties", inner)
            if isinstance(inner, dict)
            else cast("Neo4jProperties", dict(cast("Any", inner)))
        )
        return _report_from_props(props)

    async def get_history(
        self,
        subject_uid: str,
        limit: int = 20,
        ending_before: datetime | None = None,
    ) -> Result[list[ActivityReport]]:
        """
        Get all ActivityReport entities where subject_uid matches the user.

        Returns both LLM-generated (AUTOMATIC/LLM) and human-written (HUMAN)
        feedback for the given user, newest first.

        Args:
            subject_uid: User to retrieve reports for
            limit: Maximum number of results
            ending_before: Keep only reports whose period ended by this instant —
                the comparison's way to the period BEFORE a calendar period, past
                its own regenerations and past later periods generated earlier

        Returns:
            Result[list[ActivityReport]]
        """
        query_result = await self.backend.get_history(
            subject_uid,
            limit,
            ending_before=ending_before.isoformat() if ending_before is not None else None,
        )
        if query_result.is_error:
            return Result.fail(query_result)

        records = query_result.value or []
        feedbacks = []
        for record in records:
            node = record.get("n") if isinstance(record, dict) else record
            if node:
                # Neo4j Node implements Mapping at runtime but isn't typed as such
                if isinstance(node, dict):
                    props = node
                else:
                    props = cast("Neo4jProperties", dict(cast("Any", node)))
                feedbacks.append(_report_from_props(props))

        return Result.ok(feedbacks)

    async def annotate(
        self,
        uid: str,
        user_uid: UserUID,
        annotation_mode: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> Result[AnnotationResult]:
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
        now = datetime.now().isoformat()
        result = await self.backend.annotate(
            uid=uid,
            user_uid=user_uid,
            annotation_mode=annotation_mode,
            now=now,
            user_annotation=user_annotation,
            user_revision=user_revision,
        )
        if result.is_error:
            return Result.fail(result)
        # boundary: neo4j-rows — heterogeneous dict columns vary per query
        # (execute_query's own return type); viewed as dict[str, Any] so the typed
        # literal below builds without per-value casts.
        records: list[dict[str, Any]] = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(f"ActivityReport {uid} not found or not owned by {user_uid}")
            )
        record = records[0] if isinstance(records[0], dict) else dict(records[0])
        annotation: AnnotationResult = {
            "uid": record["uid"],
            "annotation_mode": record["annotation_mode"],
            "user_annotation": record.get("user_annotation"),
            "user_revision": record.get("user_revision"),
        }
        return Result.ok(annotation)

    async def get_annotation(self, uid: str, user_uid: UserUID) -> Result[AnnotationState]:
        """
        Get current annotation state for an owned ActivityReport.

        Args:
            uid: ActivityReport uid
            user_uid: Owner requesting the annotation (ownership enforced via query)

        Returns:
            Result[dict] — current annotation fields (may all be None if not yet annotated)
        """
        result = await self.backend.get_annotation(uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        # boundary: neo4j-rows — heterogeneous dict columns vary per query
        # (execute_query's own return type); viewed as dict[str, Any] so the typed
        # literal below builds without per-value casts.
        records: list[dict[str, Any]] = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(f"ActivityReport {uid} not found or not owned by {user_uid}")
            )
        record = records[0] if isinstance(records[0], dict) else dict(records[0])
        annotation_updated_at = record.get("annotation_updated_at")
        state: AnnotationState = {
            "uid": record["uid"],
            "annotation_mode": record.get("annotation_mode"),
            "user_annotation": record.get("user_annotation"),
            "user_revision": record.get("user_revision"),
            "annotation_updated_at": (
                str(annotation_updated_at) if annotation_updated_at else None
            ),
        }
        return Result.ok(state)

    async def get_privacy_summary(self, user_uid: UserUID) -> Result[PrivacySummary]:
        """
        Return a privacy-transparency summary for the authenticated user.

        Three data points:
            admin_snapshots  — ActivityReports written by admins about this user
                               (processor_type=human, subject_uid=user_uid)
            shares_granted   — Users who currently have SHARES_WITH access to
                               the user's entities
            report_schedule  — Current automatic report schedule + last generated

        Staged (PLANNED tier, ADR-069 §3): no route consumes this yet — wire a
        /privacy route + UI. User-facing — always scoped to the requesting
        user's own data. No admin privileges required.

        Args:
            user_uid: Authenticated user requesting their own privacy summary

        Returns:
            Result[dict] — privacy summary with admin_snapshots, shares_granted,
                           and report_schedule sections
        """
        # 1. Admin-written ActivityReports received by this user
        admin_snapshots_result = await self.backend.get_admin_snapshots(user_uid)
        admin_snapshots: list[dict[str, Any]] = []
        if admin_snapshots_result.is_ok:
            for record in admin_snapshots_result.value or []:
                admin_snapshots.append(
                    {
                        "accessed_at": (
                            str(record.get("accessed_at")) if record.get("accessed_at") else None
                        ),
                        "admin_uid": record.get("admin_uid", ""),
                        "time_period": record.get("time_period", ""),
                    }
                )

        # 2. Users with active SHARES_WITH access to this user's entities
        shares_result = await self.backend.get_shares_granted(user_uid)
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
                            str(record.get("shared_at")) if record.get("shared_at") else None
                        ),
                    }
                )

        # 3. Active report schedule + last generated report
        schedule_result = await self.backend.get_report_schedule(user_uid)
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

        summary: PrivacySummary = {
            "user_uid": user_uid,
            "admin_snapshots": admin_snapshots,
            "admin_snapshot_count": len(admin_snapshots),
            "shares_granted": shares_granted,
            "shares_granted_count": len(shares_granted),
            "report_schedule": report_schedule,
        }
        return Result.ok(summary)
