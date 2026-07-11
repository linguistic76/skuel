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

Tasks:
    TaskCreated, TaskCompleted, TaskUpdated, TaskDeleted, TaskPriorityChanged,

Goals:
    GoalCreated, GoalAchieved, GoalProgressUpdated, GoalAbandoned

Habits:
    HabitCreated, HabitCompleted, HabitStreakBroken, HabitMissed,

Principles:
    PrincipleCreated, PrincipleUpdated, PrincipleDeleted, PrincipleStrengthChanged, PrincipleAlignmentAssessed

Choices:
    ChoiceCreated, ChoiceUpdated, ChoiceDeleted, ChoiceMade, ChoiceOutcomeRecorded

Calendar Events:
    CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, CalendarEventDeleted, CalendarEventRescheduled

Forms:
    FormTemplateCreated, FormTemplateUpdated, FormTemplateDeleted, FormSubmitted, FormSubmissionDeleted

User:
    UserDeleted,

Learning:
    KnowledgeMastered, LearningPathStarted, LearningPathCompleted,
    PathStepProgressUpdated

References:
----------
- Migration Guide: /home/mike/0bsidian/skuel/docs/guides/EVENT_DRIVEN_MIGRATION_GUIDE.md
- Quick Reference: /home/mike/skuel/app/core/events/README.md
- Event Bus: /home/mike/skuel/app/adapters/infrastructure/event_bus.py
"""

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
    GoalUpdated,
)

# Habit events
from core.events.habit_events import (
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
    AssessmentCreated,
    ReportSubmitted,
    RevisedExerciseCreated,
    UserEntryApproved,
    UserEntryRevisionRequested,
)

# Principle events
from core.events.principle_events import (
    PrincipleAlignmentAssessed,
    PrincipleCreated,
    PrincipleDeleted,
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
__all__ = [
    # Learning loop events
    "ActivitySnapshotAccessed",
    "AssessmentCreated",
    "ReportSubmitted",
    "RevisedExerciseCreated",
    "UserEntryApproved",
    "UserEntryRevisionRequested",
    # Base
    "BaseEvent",
    # Calendar Events
    "CalendarEventCompleted",
    # Chunk embedding events (async background generation for RAG)
    "ChunkEmbeddingRequested",
    "ReferenceChunkEmbeddingRequested",
    # Embedding events (async background generation)
    "ChoiceEmbeddingRequested",
    "EmbeddingRequested",
    "EventEmbeddingRequested",
    "ExerciseEmbeddingRequested",
    "GoalEmbeddingRequested",
    "HabitEmbeddingRequested",
    "KuEmbeddingRequested",
    "LearningPathEmbeddingRequested",
    "PathStepEmbeddingRequested",
    "PrincipleEmbeddingRequested",
    "ResourceEmbeddingRequested",
    "RevisedExerciseEmbeddingRequested",
    "TaskEmbeddingRequested",
    "UserEntryEmbeddingRequested",
    # Calendar Events
    "CalendarEventCreated",
    "CalendarEventDeleted",
    "CalendarEventRescheduled",
    "CalendarEventUpdated",
    # Choices
    "ChoiceCreated",
    "ChoiceDeleted",
    "ChoiceMade",
    "ChoiceOutcomeRecorded",
    "ChoiceUpdated",
    "DomainEvent",
    "EventMetadata",
    # Forms
    "FormSubmissionDeleted",
    "FormSubmitted",
    "FormTemplateCreated",
    "FormTemplateDeleted",
    "FormTemplateUpdated",
    "GoalAbandoned",
    "GoalAchieved",
    # Goals
    "GoalCreated",
    "GoalMilestoneReached",
    "GoalProgressUpdated",
    "GoalUpdated",
    "HabitCompleted",
    "HabitCompletionBulk",
    # Habits
    "HabitCreated",
    "HabitMissed",
    "HabitStreakBroken",
    "HabitStreakMilestone",
    "HabitUpdated",
    # Knowledge substance events
    "KnowledgeAppliedInTask",
    "KnowledgeBulkAppliedInTask",
    "KnowledgeBulkBuiltIntoHabit",
    "KnowledgeBulkInformedChoice",
    "KnowledgeBuiltIntoHabit",
    "KnowledgeCreated",
    "KnowledgeInformedChoice",
    "KnowledgeReflectedInEntry",
    # Learning
    "KnowledgeMastered",
    "KnowledgePracticed",
    "KnowledgePracticedInEvent",
    "LearningPathCompleted",
    "LearningPathProgressUpdated",
    "LearningPathStarted",
    "LearningRecommendationGenerated",
    "PathStepProgressUpdated",
    # Curriculum (PS)
    # NOTE: MOC events removed January 2026 - MOC is now KU-based
    "PathStepCompleted",
    "PathStepCreated",
    "PathStepDeleted",
    "PathStepEnrolled",
    "PathStepUpdated",
    "PrincipleAlignmentAssessed",
    # Principles
    "PrincipleCreated",
    "PrincipleDeleted",
    "PrincipleStrengthChanged",
    "PrincipleUpdated",
    # Search
    "SearchExecuted",
    "TaskCompleted",
    # Tasks
    "TaskCreated",
    "TaskDeleted",
    "TaskPriorityChanged",
    "TaskUpdated",
    "TasksBulkCompleted",
    # Transcription events
    "TranscriptionCompleted",
    "TranscriptionCreated",
    "TranscriptionFailed",
    "UserActivityRecorded",
    # User
    "UserDeleted",
    # UserEntry (ADR-054)
    "UserEntryCreated",
    "UserEntryProcessingCompleted",
    "UserEntryProcessingFailed",
    "UserEntryProcessingStarted",
    # Utilities
    "publish_event",
]


# ============================================================================
# EVENT REGISTRY
# ============================================================================

# Map event type strings to event classes for deserialization
EVENT_REGISTRY: dict[str, type[BaseEvent]] = {
    # Learning loop
    "submission.report_submitted": ReportSubmitted,
    "user_entry.approved": UserEntryApproved,
    "user_entry.revision_requested": UserEntryRevisionRequested,
    "assessment.created": AssessmentCreated,
    "activity.snapshot_accessed": ActivitySnapshotAccessed,
    "revised_exercise.created": RevisedExerciseCreated,
    # Chunk embedding events (async background generation for RAG)
    "chunk.embedding_requested": ChunkEmbeddingRequested,
    "reference_chunk.embedding_requested": ReferenceChunkEmbeddingRequested,
    # Embedding events (async background generation)
    "embedding.requested": EmbeddingRequested,
    "task.embedding_requested": TaskEmbeddingRequested,
    "goal.embedding_requested": GoalEmbeddingRequested,
    "habit.embedding_requested": HabitEmbeddingRequested,
    "event.embedding_requested": EventEmbeddingRequested,
    "choice.embedding_requested": ChoiceEmbeddingRequested,
    "principle.embedding_requested": PrincipleEmbeddingRequested,
    "ku.embedding_requested": KuEmbeddingRequested,
    "resource.embedding_requested": ResourceEmbeddingRequested,
    "exercise.embedding_requested": ExerciseEmbeddingRequested,
    "path_step.embedding_requested": PathStepEmbeddingRequested,
    "learning_path.embedding_requested": LearningPathEmbeddingRequested,
    "revised_exercise.embedding_requested": RevisedExerciseEmbeddingRequested,
    "user_entry.embedding_requested": UserEntryEmbeddingRequested,
    # Tasks
    "task.created": TaskCreated,
    "task.completed": TaskCompleted,
    "task.updated": TaskUpdated,
    "task.deleted": TaskDeleted,
    "task.priority_changed": TaskPriorityChanged,
    "tasks.bulk_completed": TasksBulkCompleted,
    # Goals
    "goal.created": GoalCreated,
    "goal.updated": GoalUpdated,
    "goal.achieved": GoalAchieved,
    "goal.progress_updated": GoalProgressUpdated,
    "goal.abandoned": GoalAbandoned,
    "goal.milestone_reached": GoalMilestoneReached,
    # Habits
    "habit.created": HabitCreated,
    "habit.updated": HabitUpdated,
    "habit.completed": HabitCompleted,
    "habits.bulk_completed": HabitCompletionBulk,
    "habit.streak_broken": HabitStreakBroken,
    "habit.missed": HabitMissed,
    "habit.streak_milestone": HabitStreakMilestone,
    # User
    "user.activity_recorded": UserActivityRecorded,
    "user.deleted": UserDeleted,
    # Learning
    "knowledge.mastered": KnowledgeMastered,
    "knowledge.created": KnowledgeCreated,
    # Knowledge substance events
    "knowledge.applied_in_task": KnowledgeAppliedInTask,
    "knowledge.practiced_in_event": KnowledgePracticedInEvent,
    "knowledge.practiced": KnowledgePracticed,
    "knowledge.built_into_habit": KnowledgeBuiltIntoHabit,
    "knowledge.reflected_in_entry": KnowledgeReflectedInEntry,
    "knowledge.informed_choice": KnowledgeInformedChoice,
    "knowledge.bulk_applied_in_task": KnowledgeBulkAppliedInTask,
    "knowledge.bulk_built_into_habit": KnowledgeBulkBuiltIntoHabit,
    "knowledge.bulk_informed_choice": KnowledgeBulkInformedChoice,
    "path_step.progress_updated": PathStepProgressUpdated,
    "learning_path.started": LearningPathStarted,
    "learning_path.completed": LearningPathCompleted,
    "learning_path.progress_updated": LearningPathProgressUpdated,
    "learning.recommendation_generated": LearningRecommendationGenerated,
    # Path Steps (PS)
    "path_step.created": PathStepCreated,
    "path_step.updated": PathStepUpdated,
    "path_step.deleted": PathStepDeleted,
    "path_step.enrolled": PathStepEnrolled,
    "path_step.completed": PathStepCompleted,
    # Maps of Content (MOC) - removed January 2026
    # MOC is now KU-based - use KU events instead
    # Principles
    "principle.created": PrincipleCreated,
    "principle.updated": PrincipleUpdated,
    "principle.deleted": PrincipleDeleted,
    "principle.strength_changed": PrincipleStrengthChanged,
    "principle.alignment_assessed": PrincipleAlignmentAssessed,
    # Choices
    "choice.created": ChoiceCreated,
    "choice.updated": ChoiceUpdated,
    "choice.deleted": ChoiceDeleted,
    "choice.made": ChoiceMade,
    "choice.outcome_recorded": ChoiceOutcomeRecorded,
    # Calendar Events
    "calendar_event.created": CalendarEventCreated,
    "calendar_event.updated": CalendarEventUpdated,
    "calendar_event.completed": CalendarEventCompleted,
    "calendar_event.deleted": CalendarEventDeleted,
    "calendar_event.rescheduled": CalendarEventRescheduled,
    # Forms
    "form_template.created": FormTemplateCreated,
    "form_template.updated": FormTemplateUpdated,
    "form_template.deleted": FormTemplateDeleted,
    "form.submitted": FormSubmitted,
    "form_submission.deleted": FormSubmissionDeleted,
    # UserEntry (ADR-054)
    "user_entry.created": UserEntryCreated,
    "user_entry.processing_started": UserEntryProcessingStarted,
    "user_entry.processing_completed": UserEntryProcessingCompleted,
    "user_entry.processing_failed": UserEntryProcessingFailed,
    # Transcriptions
    "transcription.created": TranscriptionCreated,
    "transcription.completed": TranscriptionCompleted,
    "transcription.failed": TranscriptionFailed,
    # Search (discovery analytics)
    "search.executed": SearchExecuted,
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


# ============================================================================
# EVENT GROUPS
# ============================================================================

LEARNING_LOOP_EVENTS = [
    ReportSubmitted,
    UserEntryApproved,
    AssessmentCreated,
    ActivitySnapshotAccessed,
    UserEntryRevisionRequested,
    RevisedExerciseCreated,
]

TASK_EVENTS = [
    TaskCreated,
    TaskCompleted,
    TaskUpdated,
    TaskDeleted,
    TaskPriorityChanged,
    TasksBulkCompleted,
]

GOAL_EVENTS = [
    GoalCreated,
    GoalUpdated,
    GoalAchieved,
    GoalProgressUpdated,
    GoalAbandoned,
    GoalMilestoneReached,
]

HABIT_EVENTS = [
    HabitCreated,
    HabitUpdated,
    HabitCompleted,
    HabitCompletionBulk,
    HabitStreakBroken,
    HabitMissed,
    HabitStreakMilestone,
]

USER_EVENTS = [
    UserActivityRecorded,
    UserDeleted,
]

LEARNING_EVENTS = [
    KnowledgeMastered,
    KnowledgeCreated,
    LearningPathStarted,
    LearningPathCompleted,
    LearningPathProgressUpdated,
    PathStepProgressUpdated,
    LearningRecommendationGenerated,
]

KNOWLEDGE_SUBSTANCE_EVENTS = [
    KnowledgeAppliedInTask,
    KnowledgePracticedInEvent,
    KnowledgePracticed,
    KnowledgeBuiltIntoHabit,
    KnowledgeReflectedInEntry,
    KnowledgeInformedChoice,
    KnowledgeBulkAppliedInTask,
    KnowledgeBulkBuiltIntoHabit,
    KnowledgeBulkInformedChoice,
]

PS_EVENTS = [
    PathStepCreated,
    PathStepUpdated,
    PathStepDeleted,
    PathStepEnrolled,
    PathStepCompleted,
]


PRINCIPLE_EVENTS = [
    PrincipleCreated,
    PrincipleUpdated,
    PrincipleDeleted,
    PrincipleStrengthChanged,
    PrincipleAlignmentAssessed,
]

CHOICE_EVENTS = [
    ChoiceCreated,
    ChoiceUpdated,
    ChoiceDeleted,
    ChoiceMade,
    ChoiceOutcomeRecorded,
]

CALENDAR_EVENT_EVENTS = [
    CalendarEventCreated,
    CalendarEventUpdated,
    CalendarEventCompleted,
    CalendarEventDeleted,
    CalendarEventRescheduled,
]

FORM_EVENTS = [
    FormTemplateCreated,
    FormTemplateUpdated,
    FormTemplateDeleted,
    FormSubmitted,
    FormSubmissionDeleted,
]

USER_ENTRY_EVENTS = [
    UserEntryCreated,
    UserEntryProcessingStarted,
    UserEntryProcessingCompleted,
    UserEntryProcessingFailed,
]

TRANSCRIPTION_EVENTS = [
    TranscriptionCreated,
    TranscriptionCompleted,
    TranscriptionFailed,
]

SEARCH_EVENTS = [
    SearchExecuted,
]

# All events
ALL_EVENTS = (
    LEARNING_LOOP_EVENTS
    + TASK_EVENTS
    + GOAL_EVENTS
    + HABIT_EVENTS
    + USER_EVENTS
    + LEARNING_EVENTS
    + KNOWLEDGE_SUBSTANCE_EVENTS
    + PS_EVENTS
    + PRINCIPLE_EVENTS
    + CHOICE_EVENTS
    + CALENDAR_EVENT_EVENTS
    + FORM_EVENTS
    + USER_ENTRY_EVENTS
    + TRANSCRIPTION_EVENTS
    + SEARCH_EVENTS
)


# ============================================================================
# QUICK REFERENCE
# ============================================================================

"""
Quick Reference - Common Patterns
==================================

1. Publishing an event:
    event = TaskCompleted(
        task_uid="task-123",
        user_uid="user-456",
    )
    await event_bus.publish_async(event)

2. Subscribing to an event:
    async def handle_task_completed(event: TaskCompleted):
        await invalidate_context(event.user_uid)

    event_bus.subscribe(TaskCompleted, handle_task_completed)

3. Bootstrap wiring:
    def _wire_event_subscribers(event_bus, services):
        event_bus.subscribe(TaskCompleted, services.user.handle_task_completed)
        event_bus.subscribe(GoalAchieved, services.user.handle_goal_achieved)

4. Testing:
    mock_bus = Mock()
    mock_bus.publish_async = AsyncMock()

    service = TasksService(backend, event_bus=mock_bus)
    await service.complete_task("task-123")

    mock_bus.publish_async.assert_called_once()
    event = mock_bus.publish_async.call_args[0][0]
    assert event.event_type == "task.completed"

For complete documentation, see:
- Migration Guide: /home/mike/0bsidian/skuel/docs/guides/EVENT_DRIVEN_MIGRATION_GUIDE.md
- Quick Reference: /home/mike/skuel/app/core/events/README.md
"""
