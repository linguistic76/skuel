"""
Knowledge Substance Tracking Events
====================================

Events for tracking how knowledge is applied in real life.
These events update substance metrics in KnowledgeUnit models.

Philosophical Foundation:
"Applied knowledge, not pure theory" - Knowledge gains substance through
real-world application, practice, reflection, and decision-making.

Event Catalog:
- knowledge.applied_in_task - Task applies knowledge
- knowledge.practiced_in_event - Event practices knowledge
- knowledge.built_into_habit - Habit builds on knowledge
- knowledge.reflected_in_journal - Journal reflects on knowledge
- knowledge.informed_choice - Choice informed by knowledge

Subscribers:
- KuService (increment substance metrics)
- LearningAnalyticsService (track application patterns)
- SpacedRepetitionService (schedule reviews)
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent

# ============================================================================
# KNOWLEDGE SUBSTANCE EVENTS
# ============================================================================


@dataclass(frozen=True)
class KnowledgeAppliedInTask(BaseEvent):
    """
    Published when a task is created/updated to apply knowledge.

    Increments: times_applied_in_tasks
    Updates: last_applied_date

    Subscribers:
    - KuService (increment substance metric)
    - LearningAnalyticsService (track application patterns)

    Published by:
    - TasksService (when task created with applies_knowledge_uids)
    - TasksService (when task updated to add knowledge UIDs)
    """

    knowledge_uid: str
    task_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    task_title: str | None = None
    task_priority: str | None = None

    @property
    def event_type(self) -> str:
        return "knowledge.applied_in_task"


@dataclass(frozen=True)
class KnowledgePracticedInEvent(BaseEvent):
    """
    Published when an event is created to practice knowledge.

    Increments: times_practiced_in_events
    Updates: last_practiced_date

    Subscribers:
    - KuService (increment substance metric)
    - SpacedRepetitionService (track practice frequency)

    Published by:
    - EventsService (when event created with practices_knowledge_uid)
    """

    knowledge_uid: str
    event_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    event_title: str | None = (None,)
    duration_minutes: int | None = None

    @property
    def event_type(self) -> str:
        return "knowledge.practiced_in_event"


@dataclass(frozen=True)
class KnowledgePracticed(BaseEvent):
    """
    Published when knowledge is practiced (generic practice event).

    This is a generic practice tracking event used for event-driven
    practice count updates from various sources (event completion,
    study sessions, etc.).

    Increments: times_practiced_in_events
    Updates: last_practiced_date

    Subscribers:
    - LearningAnalyticsService (track practice patterns)
    - SpacedRepetitionService (schedule reviews)

    Published by:
    - KuPracticeService (when CalendarEventCompleted)
    - Study session tracking
    """

    ku_uid: str
    user_uid: str
    occurred_at: datetime

    # Context information
    practice_context: str  # "event_completion", "study_session", etc.
    event_uid: str | None = None
    times_practiced: int = 0  # New total practice count

    @property
    def event_type(self) -> str:
        return "knowledge.practiced"


@dataclass(frozen=True)
class KnowledgeBuiltIntoHabit(BaseEvent):
    """
    Published when a habit is created that builds on knowledge.

    Increments: times_built_into_habits
    Updates: last_built_into_habit_date

    This is the HIGHEST WEIGHT substance event (0.10 per habit)
    because habits represent lifestyle integration.

    Subscribers:
    - KuService (increment substance metric)
    - LearningAnalyticsService (track habit formation patterns)

    Published by:
    - HabitsService (when habit created with builds_on_knowledge_uids)
    """

    knowledge_uid: str
    habit_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    habit_title: str | None = None
    frequency: str | None = None  # "daily", "weekly", etc.

    @property
    def event_type(self) -> str:
        return "knowledge.built_into_habit"


@dataclass(frozen=True)
class KnowledgeInformedChoice(BaseEvent):
    """
    Published when a choice/decision is informed by knowledge.

    Increments: choices_informed_count
    Updates: last_choice_informed_date

    HIGH WEIGHT event (0.07 per choice) because applying knowledge
    to real decisions demonstrates practical understanding.

    Subscribers:
    - KuService (increment substance metric)
    - LearningAnalyticsService (track decision-making patterns)

    Published by:
    - ChoiceService (when choice created with informed_by_knowledge_uids)
    """

    knowledge_uid: str
    choice_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    choice_title: str | None = None
    choice_outcome: str | None = None  # For tracking effectiveness

    @property
    def event_type(self) -> str:
        return "knowledge.informed_choice"


# ============================================================================
# BATCH KNOWLEDGE EVENTS (Performance Optimization)
# ============================================================================


@dataclass(frozen=True)
class KnowledgeBulkAppliedInTask(BaseEvent):
    """
    Published when a task applies multiple knowledge units.

    More efficient than publishing N individual KnowledgeAppliedInTask events.
    O(1) event publication overhead vs O(n).

    Subscribers:
    - KuService (batch increment substance metrics)
    - LearningAnalyticsService (batch track application patterns)

    Published by:
    - TasksService (when task created with applies_knowledge_uids)
    """

    knowledge_uids: tuple[str, ...]
    task_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    task_title: str | None = None
    task_priority: str | None = None

    @property
    def event_type(self) -> str:
        return "knowledge.bulk_applied_in_task"

    @property
    def count(self) -> int:
        return len(self.knowledge_uids)


@dataclass(frozen=True)
class KnowledgeBulkBuiltIntoHabit(BaseEvent):
    """
    Published when a habit builds on multiple knowledge units.

    More efficient than publishing N individual KnowledgeBuiltIntoHabit events.

    Subscribers:
    - KuService (batch increment substance metrics)
    - LearningAnalyticsService (batch track habit formation patterns)

    Published by:
    - HabitsService (when habit created with builds_on_knowledge_uids)
    """

    knowledge_uids: tuple[str, ...]
    habit_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    habit_title: str | None = None
    frequency: str | None = None

    @property
    def event_type(self) -> str:
        return "knowledge.bulk_built_into_habit"

    @property
    def count(self) -> int:
        return len(self.knowledge_uids)


@dataclass(frozen=True)
class KnowledgeBulkInformedChoice(BaseEvent):
    """
    Published when a choice is informed by multiple knowledge units.

    More efficient than publishing N individual KnowledgeInformedChoice events.

    Subscribers:
    - KuService (batch increment substance metrics)
    - LearningAnalyticsService (batch track decision-making patterns)

    Published by:
    - ChoicesService (when choice created with informed_by_knowledge_uids)
    """

    knowledge_uids: tuple[str, ...]
    choice_uid: str
    user_uid: str
    occurred_at: datetime

    # Optional context
    choice_title: str | None = None

    @property
    def event_type(self) -> str:
        return "knowledge.bulk_informed_choice"

    @property
    def count(self) -> int:
        return len(self.knowledge_uids)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing Knowledge Substance Events:
=======================================

# In TasksService.create()
async def create_task(self, task: Task) -> Result[Task]:
    result = await self.backend.create(task)

    if result.is_ok and self.event_bus and task.applies_knowledge_uids:
        # Publish substance event for each knowledge UID
        for knowledge_uid in task.applies_knowledge_uids:
            event = KnowledgeAppliedInTask(
                knowledge_uid=knowledge_uid,
                task_uid=task.uid,
                user_uid=task.user_uid,
                occurred_at=datetime.now(),
                task_title=task.title,
                task_priority=task.priority or "medium"
            )
            await self.event_bus.publish_async(event)
            self.logger.debug(f"Published {event.event_type} for {knowledge_uid}")

    return result


# In HabitsService.create()
async def create_habit(self, habit: Habit) -> Result[Habit]:
    result = await self.backend.create(habit)

    if result.is_ok and self.event_bus and habit.builds_on_knowledge_uids:
        for knowledge_uid in habit.builds_on_knowledge_uids:
            event = KnowledgeBuiltIntoHabit(
                knowledge_uid=knowledge_uid,
                habit_uid=habit.uid,
                user_uid=habit.user_uid,
                occurred_at=datetime.now(),
                habit_title=habit.title,
                frequency=habit.frequency.value
            )
            await self.event_bus.publish_async(event)
            # HIGH IMPACT - log at info level
            self.logger.info(f"Knowledge {knowledge_uid} built into habit (substance +0.10)")

    return result


Subscribing to Knowledge Substance Events:
===========================================

# In KuService
async def handle_knowledge_applied_in_task(self, event: KnowledgeAppliedInTask) -> None:
    '''Increment substance metric when knowledge applied in task.'''
    try:
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric='times_applied_in_tasks',
            timestamp_field='last_applied_date',
            timestamp=event.occurred_at
        )
        self.logger.debug(f"Substance updated for {event.knowledge_uid}")
    except Exception as e:
        self.logger.error(f"Error incrementing substance: {e}")


async def increment_substance_metric(
    self,
    ku_uid: str,
    metric: str,
    timestamp_field: str,
    timestamp: datetime
) -> None:
    '''Atomically increment a substance metric in Neo4j.'''
    query = f'''
    MATCH (ku:Entity {{uid: $ku_uid}})
    SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
        ku.{timestamp_field} = $timestamp,
        ku._substance_cache_timestamp = NULL  # Invalidate cache
    RETURN ku
    '''
    await self.backend.execute_query(query, {
        'ku_uid': ku_uid,
        'timestamp': timestamp.isoformat()
    })


# In Bootstrap (services_bootstrap.py)
# Wire up substance tracking event listeners
event_bus.subscribe(KnowledgeAppliedInTask, ku_service.handle_knowledge_applied_in_task)
event_bus.subscribe(KnowledgePracticedInEvent, ku_service.handle_knowledge_practiced_in_event)
event_bus.subscribe(KnowledgeBuiltIntoHabit, ku_service.handle_knowledge_built_into_habit)
event_bus.subscribe(KnowledgeInformedChoice, ku_service.handle_knowledge_informed_choice)
"""
