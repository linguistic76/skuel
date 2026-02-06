"""
Metrics Event Handler
=====================

Event subscriber that tracks domain activity metrics in Prometheus.

Subscribes to domain events (TaskCreated, GoalAchieved, etc.) and increments
Prometheus counters for entity creation/completion tracking.

This enables business-level observability:
- Which features are users engaging with?
- What's the completion rate for tasks/goals/habits?
- Which domains are most active?

Phase 3 - January 2026
"""

from typing import Any

from core.events.calendar_event_events import CalendarEventCreated
from core.events.choice_events import ChoiceCreated
from core.events.goal_events import GoalCreated
from core.events.habit_events import HabitCompleted, HabitCreated
from core.events.principle_events import PrincipleCreated
from core.events.task_events import TaskCompleted, TaskCreated, TasksBulkCompleted
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.logging import get_logger

logger = get_logger(__name__)


class MetricsEventHandler:
    """
    Event handler that tracks domain activity in Prometheus.

    Subscribes to entity creation/completion events and increments
    Prometheus counters for observability.
    """

    def __init__(self, event_bus: EventBusOperations, prometheus_metrics: Any) -> None:
        """
        Initialize metrics event handler.

        Args:
            event_bus: EventBusOperations to subscribe to
            prometheus_metrics: PrometheusMetrics instance
        """
        self.event_bus = event_bus
        self.prometheus_metrics = prometheus_metrics

        # Subscribe to creation events
        self._subscribe_to_creation_events()

        # Subscribe to completion events
        self._subscribe_to_completion_events()

        logger.info("MetricsEventHandler initialized and subscribed to domain events")

    def _subscribe_to_creation_events(self) -> None:
        """Subscribe to entity creation events across all domains."""
        # Activity domains (6)
        self.event_bus.subscribe(TaskCreated, self._on_task_created)
        self.event_bus.subscribe(GoalCreated, self._on_goal_created)
        self.event_bus.subscribe(HabitCreated, self._on_habit_created)
        self.event_bus.subscribe(CalendarEventCreated, self._on_event_created)
        self.event_bus.subscribe(ChoiceCreated, self._on_choice_created)
        self.event_bus.subscribe(PrincipleCreated, self._on_principle_created)

        # Finance domain (1)
        from core.events.finance_events import ExpenseCreated

        self.event_bus.subscribe(ExpenseCreated, self._on_expense_created)

        # Content/Processing domains (2)
        # NOTE: JournalCreated subscription REMOVED (February 2026) - Journal merged into Reports
        # Journal creation tracked via ReportSubmitted with report_type="journal"
        from core.events.transcription_events import TranscriptionCreated

        self.event_bus.subscribe(TranscriptionCreated, self._on_transcription_created)

        # Curriculum domains (3)
        from core.events.curriculum_events import LearningStepCreated
        from core.events.learning_events import KnowledgeCreated, LearningPathStarted

        self.event_bus.subscribe(KnowledgeCreated, self._on_knowledge_created)
        self.event_bus.subscribe(LearningStepCreated, self._on_ls_created)
        self.event_bus.subscribe(LearningPathStarted, self._on_lp_started)

        # Report domain (1)
        from core.events.report_events import ReportSubmitted

        self.event_bus.subscribe(ReportSubmitted, self._on_report_submitted)

    def _subscribe_to_completion_events(self) -> None:
        """Subscribe to entity completion events."""
        self.event_bus.subscribe(TaskCompleted, self._on_task_completed)
        self.event_bus.subscribe(TasksBulkCompleted, self._on_tasks_bulk_completed)
        self.event_bus.subscribe(HabitCompleted, self._on_habit_completed)
        # Note: GoalAchieved event not found, will use GoalProgressUpdated
        # Note: EventCompleted not found (events don't have completion status typically)

    # === Creation Event Handlers ===

    async def _on_task_created(self, event: TaskCreated) -> None:
        """Track task creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="task", user_uid=event.user_uid
        ).inc()

    async def _on_goal_created(self, event: GoalCreated) -> None:
        """Track goal creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="goal", user_uid=event.user_uid
        ).inc()

    async def _on_habit_created(self, event: HabitCreated) -> None:
        """Track habit creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="habit", user_uid=event.user_uid
        ).inc()

    async def _on_event_created(self, event: CalendarEventCreated) -> None:
        """Track calendar event creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="event", user_uid=event.user_uid
        ).inc()

    async def _on_choice_created(self, event: ChoiceCreated) -> None:
        """Track choice creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="choice", user_uid=event.user_uid
        ).inc()

    async def _on_principle_created(self, event: PrincipleCreated) -> None:
        """Track principle creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="principle", user_uid=event.user_uid
        ).inc()

    async def _on_expense_created(self, event) -> None:
        """Track expense creation."""

        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="expense", user_uid=event.user_uid
        ).inc()

    # NOTE: _on_journal_created REMOVED (February 2026) - Journal merged into Reports
    # Journal creation tracked via _on_report_submitted with report_type="journal"

    async def _on_transcription_created(self, event) -> None:
        """Track transcription creation."""

        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="transcription", user_uid=event.user_uid
        ).inc()

    async def _on_knowledge_created(self, event) -> None:
        """Track KU creation."""

        # KU is shared content - may not have user_uid, use "system" as fallback
        user_uid = getattr(event, "user_uid", None) or getattr(event, "created_by_user", "system")
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="ku", user_uid=user_uid
        ).inc()

    async def _on_ls_created(self, event) -> None:
        """Track LS creation."""

        # LS is shared content - may not have user_uid, use "system" as fallback
        user_uid = getattr(event, "user_uid", "system")
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="ls", user_uid=user_uid
        ).inc()

    async def _on_lp_started(self, event) -> None:
        """Track LP start (proxy for creation tracking)."""

        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="lp", user_uid=event.user_uid
        ).inc()

    async def _on_report_submitted(self, event) -> None:
        """Track report submission (proxy for creation)."""

        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="report", user_uid=event.user_uid
        ).inc()

    # === Completion Event Handlers ===

    async def _on_task_completed(self, event: TaskCompleted) -> None:
        """Track task completion."""
        self.prometheus_metrics.domains.entities_completed.labels(
            entity_type="task", user_uid=event.user_uid
        ).inc()

    async def _on_tasks_bulk_completed(self, event: TasksBulkCompleted) -> None:
        """Track bulk task completion."""
        # Increment by number of tasks completed
        task_uids = getattr(event, "task_uids", None)
        count = len(task_uids) if task_uids else 1
        self.prometheus_metrics.domains.entities_completed.labels(
            entity_type="task", user_uid=event.user_uid
        ).inc(count)

    async def _on_habit_completed(self, event: HabitCompleted) -> None:
        """Track habit completion."""
        self.prometheus_metrics.domains.entities_completed.labels(
            entity_type="habit", user_uid=event.user_uid
        ).inc()

    # Note: Additional completion events can be added as they're created
    # For now, focus on the core activity domains (Tasks, Habits)


__all__ = ["MetricsEventHandler"]
