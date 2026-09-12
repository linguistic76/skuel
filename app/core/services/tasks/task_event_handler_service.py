"""
Task Event Handler Service
============================

Handles event-driven reactive logic for task domain events.

Fire-and-forget handlers that analyze completion patterns, detect
priority inflation, and classify batch operations.

Part of the TasksService decomposition — separates event handling from
graph analytics (TasksIntelligenceService).

Responsibilities:
- Dependent-task scheduling on completion (``TRIGGERS_ON_COMPLETION``) — its own
  subscriber with its own exception boundary
- Duration calibration from task completions (migrated from intelligence)
- Overdue pattern detection and principle alignment on completion
- Priority change categorization and inflation detection
- Batch completion pattern classification
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import LearningLoop
from core.events.task_events import (
    TaskCompleted,
    TaskPriorityChanged,
    TasksBulkCompleted,
)
from core.models.enums import EntityStatus, Priority
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.models.update_contracts import StatusWriteGuard
from core.services.insight import persist_principle_alignment_insight
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_float, coerce_int

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.services.insight.insight_generation_service import InsightGenerationService
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def _categorize_priority_change(old: str, new: str) -> str:
    """Categorize a priority change as escalation, de-escalation, or lateral.

    Args:
        old: Previous priority value (e.g., "low", "high")
        new: New priority value

    Returns:
        Change type: "escalation", "de-escalation", or "lateral"
    """
    try:
        old_rank = Priority(old.lower()).to_numeric()
        new_rank = Priority(new.lower()).to_numeric()
    except ValueError:
        return "lateral"

    if new_rank > old_rank:
        return "escalation"
    elif new_rank < old_rank:
        return "de-escalation"
    else:
        return "lateral"


def _detect_batch_pattern(count: int, occurred_at: datetime) -> str:
    """Classify a batch completion by count and time of day.

    Args:
        count: Number of tasks completed in the batch
        occurred_at: When the batch completion occurred

    Returns:
        Pattern name: "inbox_zero_sprint", "end_of_day_cleanup", or "routine_batch"
    """
    if count > 5:
        return "inbox_zero_sprint"
    elif occurred_at.hour >= 17:
        return "end_of_day_cleanup"
    else:
        return "routine_batch"


class TaskEventHandlerService:
    """Event-driven handlers for task domain events.

    Fire-and-forget handlers that analyze completion patterns, detect
    priority inflation, and classify batch operations.

    Handles:
    - TaskCompleted: dependent-task scheduling (``handle_dependent_scheduling``, subscribed on
      its own so an optional intelligence step cannot pre-empt it), then duration
      calibration, overdue detection, principle alignment (``handle_task_completed``)
    - TaskPriorityChanged: Change categorization, cascade impact, inflation detection
    - TasksBulkCompleted: Batch pattern classification
    """

    def __init__(
        self,
        backend: TasksOperations,
        relationship_service: UnifiedRelationshipService | None = None,
        insight_store: InsightStore | None = None,
        event_bus: Any = None,
        ku_generation_service: InsightGenerationService | None = None,
    ) -> None:
        """Initialize task event handler service.

        Args:
            backend: Backend for task operations
            relationship_service: For querying related entities (optional)
            insight_store: For persisting event-driven insights (optional)
            event_bus: Event bus (accepted for factory uniformity, not used)
            ku_generation_service: For automatic knowledge generation on task completion (optional)
        """
        self.backend = backend
        self.relationships = relationship_service
        self.insight_store = insight_store
        self.ku_generation_service = ku_generation_service
        self.logger = get_logger("skuel.services.tasks.event_handler")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_task_completed(self, event: TaskCompleted) -> None:
        """Handle task completion with duration calibration and pattern detection.

        Migrated from TasksIntelligenceService.learn_from_completion().

        The handler:
        1. Computes EMA of estimated vs actual duration, persisted on User node
        2. Detects overdue completion patterns
        3. Checks principle alignment for completed task

        Every publisher of ``TaskCompleted`` is transition-gated (see the
        event's docstring), so this handler runs exactly once per genuine
        completion and needs no repeat gate of its own.

        Args:
            event: TaskCompleted event with completion context

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # 1. Duration calibration (migrated from intelligence service)
            await self._calibrate_duration(event)

            # 2. Overdue pattern detection
            if event.was_overdue:
                self.logger.info(
                    "Overdue task completed",
                    extra={
                        "task_uid": event.task_uid,
                        "user_uid": event.user_uid,
                        "event_type": "task.overdue_completion",
                    },
                )

                # Persist overdue completion insight
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.COMPLETION_PATTERN, EntityUID(event.task_uid)
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.COMPLETION_PATTERN,
                        domain="tasks",
                        title="Overdue Task Completed",
                        description="A task was completed past its due date. Consider adjusting time estimates.",
                        confidence=0.85,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=EntityUID(event.task_uid),
                        supporting_data={
                            "was_overdue": True,
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist overdue insight: {create_result.error}"
                        )

            # 3. Principle alignment check
            if self.relationships:
                await self._check_principle_alignment(event)

            # 4. Knowledge generation (fire-and-forget — errors logged, not propagated)
            if self.ku_generation_service:
                await self._trigger_knowledge_generation(event.user_uid)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling task completion: {e}",
                extra={
                    "task_uid": event.task_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_dependent_scheduling(self, event: TaskCompleted) -> None:
        """Schedule the completed task's ``TRIGGERS_ON_COMPLETION`` dependents.

        The one graph write a task completion cascades into, and the reason it is
        its own subscriber rather than a step of :meth:`handle_task_completed`: that
        handler exits through one boundary when an optional intelligence step
        (duration calibration, principle alignment, knowledge generation) raises,
        and a dependent must not stay unscheduled behind a completion that reported
        success. The bus runs subscribers in isolation, so nothing this raises can
        reach another handler or the completing request.

        Recompute-shaped: every dependent is asked for on every completion, and the
        write's own terminal condition (:meth:`_schedule_dependent`) makes a second
        pass a no-op — no repeat gate is needed or wanted.

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            triggers = await self.backend.get_related_uids(
                event.task_uid, RelationshipName.TRIGGERS_ON_COMPLETION, direction="outgoing"
            )
            if triggers.is_error:
                self.logger.warning(
                    "Could not read TRIGGERS_ON_COMPLETION dependents of %s: %s",
                    event.task_uid,
                    triggers.expect_error(),
                )
                return
            for dependent_uid in triggers.value:
                await self._schedule_dependent(dependent_uid)
        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error scheduling dependents of completed task: {e}",
                extra={"task_uid": event.task_uid, "user_uid": event.user_uid, "error": str(e)},
            )

    async def _schedule_dependent(self, task_uid: str) -> None:
        """Schedule a dependent task, unless that task has already finished.

        A ``TRIGGERS_ON_COMPLETION`` dependent that is already in a terminal state is
        left exactly as it is — this cascade unblocks work, it never reopens work
        that is done.
        """
        # The terminal check is a CONDITION ON THE WRITE, not a read before it
        # (ADR-087). A blind ``status=scheduled`` on an already-COMPLETED dependent
        # would move it out of COMPLETED while LEAVING ``completion_date`` set —
        # breaking the invariant that the stamp is non-null exactly when the task
        # is completed. A dependent being completed concurrently is exactly the case
        # a read-then-write gate misses, because the status it read is already stale
        # by the time it writes.
        # The gate is ``terminal_values()``, not COMPLETED alone: FAILED / CANCELLED /
        # ARCHIVED dependents are equally not this cascade's to resurrect, and keying
        # on the enum's own predicate means a new terminal status is honoured here
        # without an edit. It is the only terminal-state protection anywhere in Tasks:
        # the domain's own update hook carries a single rule about overdue priority,
        # because refusing every change to a finished task would also refuse the
        # status re-post that reopens it.
        # No stamp guard is wanted here: the only prior a reopen clear would apply
        # to is COMPLETED, which this guard refuses outright.
        result = await self.backend.update_with_status_guard(
            task_uid,
            {"status": EntityStatus.SCHEDULED.value},
            StatusWriteGuard(refuse_if_prior_in=EntityStatus.terminal_values()),
        )
        if result.is_error:
            # Includes the not-found case — a TRIGGERS_ON_COMPLETION edge pointing
            # at nothing fails this write, never the cascade around it.
            self.logger.warning(
                f"Failed to schedule dependent task {task_uid}: {result.expect_error()}"
            )
            return
        outcome = result.value
        if not outcome.applied:
            self.logger.debug(
                "Skipped scheduling dependent task %s: already terminal (%s)",
                task_uid,
                outcome.prior_status,
            )
            return
        self.logger.debug(f"Scheduled dependent task {task_uid}")

    async def handle_task_priority_changed(self, event: TaskPriorityChanged) -> None:
        """Handle task priority changes with cascade analysis.

        The handler:
        1. Categorizes the change (escalation/de-escalation/lateral)
        2. Queries cascade impact on dependent tasks
        3. Detects priority inflation patterns

        Args:
            event: TaskPriorityChanged event with old/new priority

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # 1. Categorize the change
            change_type = _categorize_priority_change(event.old_priority, event.new_priority)

            self.logger.info(
                f"Task priority {change_type}: {event.old_priority} -> {event.new_priority}",
                extra={
                    "task_uid": event.task_uid,
                    "user_uid": event.user_uid,
                    "old_priority": event.old_priority,
                    "new_priority": event.new_priority,
                    "change_type": change_type,
                    "event_type": "task.priority.changed",
                },
            )

            # 2. Cascade impact — find tasks that depend on this one. Those are the tasks
            # with an INCOMING DEPENDS_ON edge ((dependent)-[:DEPENDS_ON]->(this)); read
            # the backend directly with the correct direction. (The previous service call
            # passed RelationshipName.DEPENDS_ON.value as a method_key — never matched, so
            # the cascade silently found nothing.)
            if self.relationships and change_type in ("escalation", "de-escalation"):
                depends_result = await self.backend.get_related_uids(
                    EntityUID(event.task_uid),
                    RelationshipName.DEPENDS_ON,
                    direction="incoming",
                )
                if depends_result.is_ok and depends_result.value:
                    affected_uids = depends_result.value
                    self.logger.info(
                        f"Priority {change_type} affects {len(affected_uids)} dependent tasks",
                        extra={
                            "task_uid": event.task_uid,
                            "affected_task_uids": affected_uids[:5],
                            "affected_count": len(affected_uids),
                            "event_type": "task.priority.cascade_impact",
                        },
                    )

            # 3. Priority inflation detection
            await self._detect_priority_inflation(event)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling task priority change: {e}",
                extra={
                    "task_uid": event.task_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    def handle_tasks_bulk_completed(self, event: TasksBulkCompleted) -> None:
        """Handle batch task completion with pattern detection.

        Classifies the batch by count and time of day:
        - "inbox_zero_sprint" (>5 tasks)
        - "end_of_day_cleanup" (after 17:00)
        - "routine_batch" (default)

        Args:
            event: TasksBulkCompleted event with batch context

        Note:
            Fire-and-forget — lightweight, no graph queries.
        """
        try:
            pattern = _detect_batch_pattern(event.count, event.occurred_at)

            self.logger.info(
                f"Batch completion detected: {pattern} ({event.count} tasks)",
                extra={
                    "user_uid": event.user_uid,
                    "task_count": event.count,
                    "pattern": pattern,
                    "occurred_at": event.occurred_at.isoformat(),
                    "event_type": "task.bulk_completed.pattern",
                },
            )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling bulk task completion: {e}",
                extra={
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    async def _calibrate_duration(self, event: TaskCompleted) -> None:
        """Compute EMA of estimated vs actual duration, persisted on User node.

        Migrated from TasksIntelligenceService.learn_from_completion().

        See: /docs/decisions/ADR-048
        """
        # 1. Get task to compare estimated vs actual duration
        task_result = await self.backend.get(event.task_uid)
        if task_result.is_error or not task_result.value:
            return

        task = task_result.value
        estimated = getattr(task, "duration_minutes", None)
        actual = getattr(task, "actual_minutes", None)

        if not estimated or not actual:
            return

        # 2. Calculate ratio, clamped to bounds
        ratio = actual / estimated
        ratio = max(LearningLoop.MIN_DURATION_RATIO, min(LearningLoop.MAX_DURATION_RATIO, ratio))

        # 3. Get current EMA state from User node
        state_result = await self.backend.get_user_learning_state(event.user_uid)
        if state_result.is_error:
            self.logger.warning(f"Failed to read learning state for {event.user_uid}")
            return

        state = state_result.value
        old_ratio = coerce_float(
            state.get("task_duration_ratio") or LearningLoop.DEFAULT_DURATION_RATIO
        )
        old_count = coerce_int(state.get("task_completion_count"))

        # 4. EMA update
        alpha = LearningLoop.EMA_ALPHA_TASK_DURATION
        new_ratio = alpha * ratio + (1 - alpha) * old_ratio
        new_count = old_count + 1

        # 5. Persist updated learning state on User node
        await self.backend.update_user_learning_state(
            event.user_uid,
            {
                "task_duration_ratio": round(new_ratio, 4),
                "task_completion_count": new_count,
                "task_duration_updated_at": datetime.now().isoformat(),
            },
        )

        # 6. Write predicted duration back to the completed task
        predicted = round(estimated * new_ratio)
        await self.backend.update(event.task_uid, {"predicted_duration_minutes": predicted})

        self.logger.info(
            f"Task duration learning: ratio={ratio:.2f} -> EMA={new_ratio:.4f} "
            f"(sample {new_count})",
            extra={
                "user_uid": event.user_uid,
                "task_uid": event.task_uid,
                "raw_ratio": round(ratio, 4),
                "ema_ratio": round(new_ratio, 4),
                "sample_count": new_count,
                "event_type": "task.duration.learned",
            },
        )

    async def _check_principle_alignment(self, event: TaskCompleted) -> None:
        """Check if completed task is aligned with any principles.

        Generates cross-domain insight when task contributes to principle alignment.
        """
        if not self.relationships:
            return

        # "principles" is the Task→Principle config key (ALIGNED_WITH_PRINCIPLE); the
        # service takes a method_key, not a raw RelationshipName.value (never matched).
        aligned_result = await self.relationships.get_related_uids(
            "principles", EntityUID(event.task_uid)
        )
        if aligned_result.is_ok and aligned_result.value:
            principle_uids = aligned_result.value
            self.logger.info(
                f"Completed task aligned with {len(principle_uids)} principle(s)",
                extra={
                    "task_uid": event.task_uid,
                    "user_uid": event.user_uid,
                    "principle_uids": principle_uids[:5],
                    "event_type": "task.completion.principle_alignment",
                },
            )

            await persist_principle_alignment_insight(
                self.insight_store,
                self.logger,
                user_uid=event.user_uid,
                entity_uid=EntityUID(event.task_uid),
                domain="tasks",
                title="Task Aligned with Principles",
                description=f"Completed task contributes to {len(principle_uids)} principle(s).",
                principle_uids=principle_uids,
            )

    async def _detect_priority_inflation(self, event: TaskPriorityChanged) -> None:
        """Detect if user has too many high-priority tasks.

        Warns if >60% of recent tasks are high priority.
        """
        tasks_result = await self.backend.find_by(user_uid=event.user_uid)
        if tasks_result.is_error:
            return

        tasks: list[Any] = tasks_result.value or []
        if len(tasks) < 3:
            return

        high_count = sum(1 for t in tasks if t.priority and Priority(t.priority).to_numeric() >= 3)
        inflation_ratio = high_count / len(tasks)

        if inflation_ratio > 0.6:
            self.logger.warning(
                f"Priority inflation detected: {inflation_ratio:.0%} of tasks are high priority",
                extra={
                    "user_uid": event.user_uid,
                    "high_priority_count": high_count,
                    "total_tasks": len(tasks),
                    "inflation_ratio": round(inflation_ratio, 2),
                    "event_type": "task.priority.inflation_warning",
                },
            )

            # Persist priority inflation insight
            if self.insight_store:
                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(
                        InsightType.IMBALANCE_DETECTED, EntityUID(event.task_uid)
                    ),
                    user_uid=event.user_uid,
                    insight_type=InsightType.IMBALANCE_DETECTED,
                    domain="tasks",
                    title="Priority Inflation Detected",
                    description=f"{inflation_ratio:.0%} of your tasks are high priority. Consider re-evaluating priorities.",
                    confidence=0.9,
                    impact=InsightImpact.HIGH,
                    entity_uid=EntityUID(event.task_uid),
                    recommended_actions=[
                        {
                            "action": "Review and re-prioritize tasks",
                            "rationale": "When most tasks are high priority, nothing is truly prioritized",
                        }
                    ],
                    supporting_data={
                        "high_priority_count": high_count,
                        "total_tasks": len(tasks),
                        "inflation_ratio": round(inflation_ratio, 2),
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist inflation insight: {create_result.error}"
                    )

    async def _trigger_knowledge_generation(self, user_uid: UserUID) -> None:
        """Extract and auto-publish knowledge from the user's recent completed tasks.

        Fire-and-forget — errors are logged, never propagated. Runs as part of
        handle_task_completed so knowledge generation is a named event consequence,
        not a hidden side effect inside the orchestration layer.
        """
        if not self.ku_generation_service:
            return

        try:
            knowledge_result = (
                await self.ku_generation_service.extract_knowledge_from_completed_tasks(
                    user_uid=user_uid, days_back=30, min_tasks=3
                )
            )

            if not (knowledge_result.is_ok and knowledge_result.value):
                return

            curation_result = self.ku_generation_service.curate_generated_knowledge(
                knowledge_result.value
            )

            if curation_result.is_ok:
                auto_published = curation_result.value.get("auto_publish", [])
                for knowledge_dto in auto_published:
                    if self.ku_generation_service.ku_service:
                        summary = (
                            (knowledge_dto.content or "")[:200] + "..."
                            if len(knowledge_dto.content or "") > 200
                            else (knowledge_dto.content or "")
                        )
                        await self.ku_generation_service.ku_service.create(
                            title=knowledge_dto.title,
                            body=knowledge_dto.content,
                            summary=summary,
                            tags=knowledge_dto.tags,
                            domain=str(knowledge_dto.domain.value),
                            **knowledge_dto.metadata,
                        )
        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.warning(f"Knowledge generation failed for user {user_uid}: {e}")
