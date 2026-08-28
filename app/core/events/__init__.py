"""
SKUEL Domain Events
===================

Event-driven architecture for decoupling services.

This package provides type-safe domain events for all SKUEL operations.
Services publish events on state changes, subscribers react to events.

Benefits:
- Zero coupling between services
- Easy testing (mock event bus only)
- Full audit trail of all state changes
- Flexible feature toggles (subscribe/unsubscribe)

Usage:
------,

Publishing:
    from core.events import TaskCompleted
    event = TaskCompleted(task_uid="...", user_uid="...")
    await event_bus.publish_async(event)

Subscribing:
    from core.events import TaskCompleted

    async def handle_task_completed(event: TaskCompleted):
        await invalidate_context(event.user_uid)

    event_bus.subscribe(TaskCompleted, handle_task_completed)

Event Catalog:
-------------

There is no hand-written catalog here. ``EVENT_REGISTRY`` is derived from the
imported event classes (see below), so the live answer is::

    from core.events import list_event_types

    list_event_types()  # every {domain}.{action} string

Adding an event to a module that this package already imports registers it
automatically. A NEW event module must be imported here — that is the one gap a
comprehension cannot close, and tests/unit/test_event_registry_derivation.py
fails if a defined event never reaches the registry.

References:
----------
- Defining / publishing / subscribing: ``core/events/base.py``
- Subscription wiring: ``services_bootstrap/_event_wiring.py`` (most of it; components
  that own their handlers subscribe themselves — ``git grep '.subscribe('``)
- Event Bus: ``adapters/infrastructure/event_bus.py``
- Pattern doc: ``docs/patterns/event_driven_architecture.md``
"""

from collections.abc import Iterator

# Base classes and protocols
# Knowledge substance events (tracking real-world application)
from core.events.base import BaseEvent, DomainEvent, EventMetadata

# Calendar Event events
from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventDeleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
    EventAttendeeAdded,
    EventAttendeeRemoved,
)

# Choice events
from core.events.choice_events import (
    ChoiceCreated,
    ChoiceDeleted,
    ChoiceMade,
    ChoiceOutcomeRecorded,
    ChoiceUpdated,
)

# Chunk embedding events (async background generation for RAG)
from core.events.chunk_events import (
    ChunkEmbeddingRequested,
    ReferenceChunkEmbeddingRequested,
)

# Curriculum events (PS)
# NOTE: MOC events removed January 2026 - MOC is now KU-based
from core.events.curriculum_events import (
    PathStepCompleted,
    PathStepCreated,
    PathStepDeleted,
    PathStepEnrolled,
    PathStepUpdated,
)

# Embedding events (async background generation)
from core.events.embedding_events import (
    ChoiceEmbeddingRequested,
    EmbeddingRequested,
    EventEmbeddingRequested,
    ExerciseEmbeddingRequested,
    GoalEmbeddingRequested,
    HabitEmbeddingRequested,
    KuEmbeddingRequested,
    LearningPathEmbeddingRequested,
    PathStepEmbeddingRequested,
    PrincipleEmbeddingRequested,
    ResourceEmbeddingRequested,
    RevisedExerciseEmbeddingRequested,
    TaskEmbeddingRequested,
    UserEntryEmbeddingRequested,
)

# Exercise events (ADR-040 — ExerciseCreated is a STAGED hook, see the module docstring)
from core.events.exercise_events import ExerciseCreated

# Form events
from core.events.form_events import (
    FormSubmissionDeleted,
    FormSubmitted,
    FormTemplateCreated,
    FormTemplateDeleted,
    FormTemplateUpdated,
)

# Goal events
from core.events.goal_events import (
    GoalAbandoned,
    GoalAchieved,
    GoalCreated,
    GoalMilestoneReached,
    GoalProgressUpdated,
    GoalRecommendationsGenerated,
    GoalUpdated,
)

# Group events (NonKuDomain.GROUP — ADR-053)
from core.events.group_events import (
    GroupCreated,
    GroupMemberAdded,
    GroupMemberRemoved,
)

# Habit events
from core.events.habit_events import (
    AchievementEarned,
    HabitCompleted,
    HabitCompletionBulk,
    HabitCreated,
    HabitMissed,
    HabitStreakBroken,
    HabitStreakMilestone,
    HabitUpdated,
)
from core.events.knowledge_substance_events import (
    KnowledgeAppliedInTask,
    KnowledgeBuiltIntoHabit,
    KnowledgeBulkAppliedInTask,
    KnowledgeBulkBuiltIntoHabit,
    KnowledgeBulkInformedChoice,
    KnowledgeInformedChoice,
    KnowledgePracticed,
    KnowledgePracticedInEvent,
    KnowledgeReflectedInEntry,
)

# Learning events
from core.events.learning_events import (
    KnowledgeCreated,
    KnowledgeMastered,
    LearningPathCompleted,
    LearningPathProgressUpdated,
    LearningPathStarted,
    LearningRecommendationGenerated,
    PathStepProgressUpdated,
)

# Learning loop events (ADR-054 — relocated from submission_events.py)
from core.events.learning_loop_events import (
    ActivitySnapshotAccessed,
    EntryReportGenerated,
    ReportSubmitted,
    RevisedExerciseCreated,
    UserEntryApproved,
    UserEntryRevisionRequested,
)

# Principle events
from core.events.principle_events import (
    PrincipleAlignmentAssessed,
    PrincipleConflictRevealed,
    PrincipleCreated,
    PrincipleDeleted,
    PrincipleReflectionRecorded,
    PrincipleStrengthChanged,
    PrincipleUpdated,
)

# Search events (discovery analytics)
from core.events.search_events import SearchExecuted

# Task events
from core.events.task_events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskPriorityChanged,
    TaskReopened,
    TasksBulkCompleted,
    TaskUpdated,
)

# Transcription events
from core.events.transcription_events import (
    TranscriptionCompleted,
    TranscriptionCreated,
    TranscriptionFailed,
)

# UserEntry events (ADR-054)
from core.events.user_entry_events import (
    UserEntryCreated,
    UserEntryProcessingCompleted,
    UserEntryProcessingFailed,
    UserEntryProcessingStarted,
)

# User events
from core.events.user_events import (
    UserActivityRecorded,
    UserDeleted,
)

# Public API
#
# Flat and alphabetical, deliberately. The former comment-delimited groupings had
# drifted into fiction (Calendar split across two blocks, DomainEvent filed under
# Choices) and cost more than they explained. The live catalog is
# ``list_event_types()``; a grouping to browse is not this list's job.
# tests/unit/test_event_registry_derivation.py fails if an event is missing here.
__all__ = [
    "AchievementEarned",
    "ActivitySnapshotAccessed",
    "BaseEvent",
    "CalendarEventCompleted",
    "CalendarEventCreated",
    "CalendarEventDeleted",
    "CalendarEventRescheduled",
    "CalendarEventUpdated",
    "ChoiceCreated",
    "ChoiceDeleted",
    "ChoiceEmbeddingRequested",
    "ChoiceMade",
    "ChoiceOutcomeRecorded",
    "ChoiceUpdated",
    "ChunkEmbeddingRequested",
    "DomainEvent",
    "EmbeddingRequested",
    "EntryReportGenerated",
    "EventAttendeeAdded",
    "EventAttendeeRemoved",
    "EventEmbeddingRequested",
    "EventMetadata",
    "ExerciseCreated",
    "ExerciseEmbeddingRequested",
    "FormSubmissionDeleted",
    "FormSubmitted",
    "FormTemplateCreated",
    "FormTemplateDeleted",
    "FormTemplateUpdated",
    "GoalAbandoned",
    "GoalAchieved",
    "GoalCreated",
    "GoalEmbeddingRequested",
    "GoalMilestoneReached",
    "GoalProgressUpdated",
    "GoalRecommendationsGenerated",
    "GoalUpdated",
    "GroupCreated",
    "GroupMemberAdded",
    "GroupMemberRemoved",
    "HabitCompleted",
    "HabitCompletionBulk",
    "HabitCreated",
    "HabitEmbeddingRequested",
    "HabitMissed",
    "HabitStreakBroken",
    "HabitStreakMilestone",
    "HabitUpdated",
    "KnowledgeAppliedInTask",
    "KnowledgeBuiltIntoHabit",
    "KnowledgeBulkAppliedInTask",
    "KnowledgeBulkBuiltIntoHabit",
    "KnowledgeBulkInformedChoice",
    "KnowledgeCreated",
    "KnowledgeInformedChoice",
    "KnowledgeMastered",
    "KnowledgePracticed",
    "KnowledgePracticedInEvent",
    "KnowledgeReflectedInEntry",
    "KuEmbeddingRequested",
    "LearningPathCompleted",
    "LearningPathEmbeddingRequested",
    "LearningPathProgressUpdated",
    "LearningPathStarted",
    "LearningRecommendationGenerated",
    "PathStepCompleted",
    "PathStepCreated",
    "PathStepDeleted",
    "PathStepEmbeddingRequested",
    "PathStepEnrolled",
    "PathStepProgressUpdated",
    "PathStepUpdated",
    "PrincipleAlignmentAssessed",
    "PrincipleConflictRevealed",
    "PrincipleCreated",
    "PrincipleDeleted",
    "PrincipleEmbeddingRequested",
    "PrincipleReflectionRecorded",
    "PrincipleStrengthChanged",
    "PrincipleUpdated",
    "ReferenceChunkEmbeddingRequested",
    "ReportSubmitted",
    "ResourceEmbeddingRequested",
    "RevisedExerciseCreated",
    "RevisedExerciseEmbeddingRequested",
    "SearchExecuted",
    "TaskCompleted",
    "TaskCreated",
    "TaskDeleted",
    "TaskEmbeddingRequested",
    "TaskPriorityChanged",
    "TaskReopened",
    "TaskUpdated",
    "TasksBulkCompleted",
    "TranscriptionCompleted",
    "TranscriptionCreated",
    "TranscriptionFailed",
    "UserActivityRecorded",
    "UserDeleted",
    "UserEntryApproved",
    "UserEntryCreated",
    "UserEntryEmbeddingRequested",
    "UserEntryProcessingCompleted",
    "UserEntryProcessingFailed",
    "UserEntryProcessingStarted",
    "UserEntryRevisionRequested",
    "publish_event",
]


# ============================================================================
# EVENT REGISTRY
# ============================================================================


def _iter_event_classes(root: type[BaseEvent] = BaseEvent) -> Iterator[type[BaseEvent]]:
    """Every transitive subclass of ``BaseEvent``, depth-first.

    Transitive, not direct: 13 of the per-domain ``*EmbeddingRequested`` events
    descend from ``EmbeddingRequested``, which is itself a concrete registered
    event. Intermediate bases are yielded alongside their children, so both the
    base and its descendants land in the registry.
    """
    for subclass in root.__subclasses__():
        yield subclass
        yield from _iter_event_classes(subclass)


# DERIVED, never hand-maintained. ``event_type`` is a ClassVar (core/events/base.py),
# so the mapping is a fact about the imported classes rather than a list to keep in
# sync — the 10-entry drift this replaced (92 listed vs 102 defined, found by
# ``./dev bloat``) is now unrepresentable.
#
# The one thing a comprehension cannot see is a sibling event module this package
# never imports: that is exactly how exercise_events and group_events drifted out.
# tests/unit/test_event_registry_derivation.py walks core/events/*.py by AST and
# fails if any defined event is missing here.
EVENT_REGISTRY: dict[str, type[BaseEvent]] = {
    event_class.event_type: event_class for event_class in _iter_event_classes()
}


def get_event_class(event_type: str) -> type[BaseEvent] | None:
    """
    Get event class by event type string.

    Useful for deserialization and event replay.

    Args:
        event_type: Event type string (e.g., "task.completed"),

    Returns:
        Event class or None if not found
    """
    return EVENT_REGISTRY.get(event_type)


async def publish_event(event_bus, event: BaseEvent, logger=None) -> bool:
    """
    Publish an event with proper warning if event bus is not configured.

    This utility function replaces the common pattern:
        if self.event_bus:
            await self.event_bus.publish_async(event)

    With:
        await publish_event(self.event_bus, event, self.logger)

    Benefits:
    - Warns when events are dropped (fail-fast philosophy)
    - Consistent logging across all services
    - Easier debugging of bootstrap misconfiguration

    Args:
        event_bus: Event bus instance (may be None)
        event: Domain event to publish
        logger: Optional logger for warnings (uses module logger if not provided)

    Returns:
        True if event was published, False if event bus is not configured

    Example:
        from core.events import publish_event, TaskCompleted

        event = TaskCompleted(task_uid="...", user_uid="...")
        await publish_event(self.event_bus, event, self.logger)
    """
    if event_bus:
        await event_bus.publish_async(event)
        return True
    else:
        # Get event type for logging
        event_type = getattr(event, "event_type", type(event).__name__)

        # Use provided logger or module logger
        from core.utils.logging import get_logger

        log = logger or get_logger("skuel.events")
        log.warning(
            f"Event bus not configured - {event_type} event dropped. "
            "Check bootstrap configuration if this is unexpected."
        )
        return False


def list_event_types() -> list[str]:
    """
    Get list of all registered event types.

    Returns:
        List of event type strings
    """
    return list(EVENT_REGISTRY.keys())
