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

- January 2026
"""

from typing import Any

from core.events.calendar_event_events import CalendarEventCreated
from core.events.choice_events import ChoiceCreated
from core.events.goal_events import GoalCreated
from core.events.habit_events import HabitCompleted, HabitCreated
from core.events.principle_events import PrincipleCreated
from core.events.task_events import TaskCompleted, TaskCreated, TasksBulkCompleted
from core.ports.infrastructure_protocols import EventBusOperations
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

        # Content/Processing domains
        # NOTE: JournalCreated subscription REMOVED (February 2026) - Journal merged into
        # Reports, then journals became UserEntry (ADR-054, pipeline JOURNAL) — counted
        # via UserEntryCreated as entity_type="user_entry", no separate journal series.
        from core.events.transcription_events import TranscriptionCreated

        self.event_bus.subscribe(TranscriptionCreated, self._on_transcription_created)

        # Curriculum domains (3)
        from core.events.curriculum_events import PathStepCreated
        from core.events.learning_events import KnowledgeCreated, LearningPathStarted

        self.event_bus.subscribe(KnowledgeCreated, self._on_knowledge_created)
        self.event_bus.subscribe(PathStepCreated, self._on_ls_created)
        self.event_bus.subscribe(LearningPathStarted, self._on_lp_started)

        # UserEntry domain (ADR-054 — replaces legacy SubmissionCreated)
        from core.events.user_entry_events import UserEntryCreated

        self.event_bus.subscribe(UserEntryCreated, self._on_user_entry_created)

    def _subscribe_to_completion_events(self) -> None:
        """Subscribe to entity completion events."""
        self.event_bus.subscribe(TaskCompleted, self._on_task_completed)
        self.event_bus.subscribe(TasksBulkCompleted, self._on_tasks_bulk_completed)
        self.event_bus.subscribe(HabitCompleted, self._on_habit_completed)
        # Note: GoalAchieved event not found, will use GoalProgressUpdated
        # Note: EventCompleted not found (events don't have completion status typically)

    # === Creation Event Handlers ===

    def _on_task_created(self, event: TaskCreated) -> None:
        """Track task creation."""
        self.prometheus_metrics.domains.entities_created.labels(entity_type="task").inc()

    def _on_goal_created(self, event: GoalCreated) -> None:
        """Track goal creation."""
        self.prometheus_metrics.domains.entities_created.labels(entity_type="goal").inc()

    def _on_habit_created(self, event: HabitCreated) -> None:
        """Track habit creation."""
        self.prometheus_metrics.domains.entities_created.labels(entity_type="habit").inc()

    def _on_event_created(self, event: CalendarEventCreated) -> None:
        """Track calendar event creation."""
        self.prometheus_metrics.domains.entities_created.labels(entity_type="event").inc()

    def _on_choice_created(self, event: ChoiceCreated) -> None:
        """Track choice creation."""
        self.prometheus_metrics.domains.entities_created.labels(entity_type="choice").inc()

    def _on_principle_created(self, event: PrincipleCreated) -> None:
        """Track principle creation."""
        self.prometheus_metrics.domains.entities_created.labels(entity_type="principle").inc()

    # NOTE: _on_journal_created REMOVED (February 2026) - Journal merged into Reports;
    # journals are now UserEntry (ADR-054) and count as entity_type="user_entry".

    def _on_transcription_created(self, event) -> None:
        """Track transcription creation."""

        self.prometheus_metrics.domains.entities_created.labels(entity_type="transcription").inc()

    def _on_knowledge_created(self, event) -> None:
        """Track KU creation."""

        self.prometheus_metrics.domains.entities_created.labels(entity_type="ku").inc()

    def _on_ls_created(self, event) -> None:
        """Track PS creation."""

        self.prometheus_metrics.domains.entities_created.labels(entity_type="ps").inc()

    def _on_lp_started(self, event) -> None:
        """Track LP start (proxy for creation tracking)."""

        self.prometheus_metrics.domains.entities_created.labels(entity_type="lp").inc()

    def _on_user_entry_created(self, event) -> None:
        """Track UserEntry creation (any pipeline)."""

        self.prometheus_metrics.domains.entities_created.labels(entity_type="user_entry").inc()

    # === Completion Event Handlers ===

    def _on_task_completed(self, event: TaskCompleted) -> None:
        """Track task completion.

        Skips a repeat complete: a Prometheus counter is monotonic, so this is
        the one subscriber that has no un-increment and can only be corrected
        at the source. See :class:`TaskCompleted` for the contract.
        """
        if event.is_repeat:
            return
        self.prometheus_metrics.domains.entities_completed.labels(entity_type="task").inc()

    def _on_tasks_bulk_completed(self, event: TasksBulkCompleted) -> None:
        """Track bulk task completion."""
        # Increment by number of tasks completed
        task_uids = getattr(event, "task_uids", None)
        count = len(task_uids) if task_uids else 1
        self.prometheus_metrics.domains.entities_completed.labels(entity_type="task").inc(count)

    def _on_habit_completed(self, event: HabitCompleted) -> None:
        """Track habit completion."""
        self.prometheus_metrics.domains.entities_completed.labels(entity_type="habit").inc()

    # Note: Additional completion events can be added as they're created
    # For now, focus on the core activity domains (Tasks, Habits)


__all__ = ["MetricsEventHandler"]
