"""
Knowledge Substance Tracking Events
====================================

Events for tracking how knowledge is applied in real life.
These events update substance metrics in KnowledgeUnit models.

Philosophical Foundation:
"Applied knowledge, not pure theory" - Knowledge gains substance through
real-world application, practice, reflection, and decision-making.

The classes below are the catalog (each ``*Bulk`` variant included).

Subscriber: PsService (increment substance metrics) — wired in
services_bootstrap/_event_wiring.py. Former docstrings here also named
LearningAnalyticsService and SpacedRepetitionService as subscribers; neither
class has ever existed (measured 2026-08-20) — de-fictioned 2026-08-21.

Grain: every ``knowledge_uid`` may name a Ku or a PathStep (grain-agnostic by
ruling 2026-08-21); the handler credits whatever the uid names and fans out to
composing PathSteps.
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

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
    - PsService (increment substance metric)

    Published by:
    - TasksService (when task created with applies_knowledge_uids)
    - TasksService (when task updated to add knowledge UIDs)
    """

    knowledge_uid: str
    task_uid: str
    user_uid: UserUID

    # Optional context
    task_title: str | None = None
    task_priority: str | None = None

    event_type: ClassVar[str] = "knowledge.applied_in_task"


@dataclass(frozen=True)
class KnowledgePracticedInEvent(BaseEvent):
    """
    Published when an event is created to practice knowledge.

    Increments: times_practiced_in_events
    Updates: last_practiced_date

    Subscribers:
    - PsService (increment substance metric)

    Published by:
    - EventsService (when event created with practices_knowledge_uids —
      published only; the request door writes no APPLIES_KNOWLEDGE edge)
    """

    knowledge_uid: str
    event_uid: str
    user_uid: UserUID

    # Optional context
    event_title: str | None = None
    duration_minutes: int | None = None

    event_type: ClassVar[str] = "knowledge.practiced_in_event"


@dataclass(frozen=True)
class KnowledgePracticed(BaseEvent):
    """
    Published after a practice count was incremented (notification, not mechanism).

    Fired by the event-completion path AFTER ``increment_practice_count`` has
    already written ``times_practiced_in_events`` — a subscriber cannot affect
    the counter.

    Subscribers: none today. Ruled 2026-08-21 (Mike): the event stays and is to
    EARN a subscriber — the review-scheduling consumer named in
    ``docs/roadmap/deferred-work.md`` § KnowledgePracticed Subscriber — rather
    than be deleted as fire-and-forget. Former docstrings named
    LearningAnalyticsService and SpacedRepetitionService here; neither class
    has ever existed.

    Published by:
    - PsPracticeService (when CalendarEventCompleted)
    """

    knowledge_uid: str
    user_uid: UserUID

    # Context information
    practice_context: str  # "event_completion", "study_session", etc.
    event_uid: str | None = None
    times_practiced: int = 0  # New total practice count

    event_type: ClassVar[str] = "knowledge.practiced"


@dataclass(frozen=True)
class KnowledgeBuiltIntoHabit(BaseEvent):
    """
    Published when a habit is created that builds on knowledge.

    Increments: times_built_into_habits
    Updates: last_built_into_habit_date

    This is the HIGHEST WEIGHT substance event (0.10 per habit)
    because habits represent lifestyle integration.

    Subscribers:
    - PsService (increment substance metric)

    Published by:
    - HabitsService (when habit created with builds_on_knowledge_uids)
    """

    knowledge_uid: str
    habit_uid: str
    user_uid: UserUID

    # Optional context
    habit_title: str | None = None
    frequency: str | None = None  # "daily", "weekly", etc.

    event_type: ClassVar[str] = "knowledge.built_into_habit"


@dataclass(frozen=True)
class KnowledgeReflectedInEntry(BaseEvent):
    """
    Published when a UserEntry reflects on / applies knowledge.

    Increments: times_reflected_in_entries
    Updates: last_reflected_date

    HIGH WEIGHT event (0.07 per entry) because written reflection is
    metacognition — the user is consciously processing the knowledge.

    Subscribers:
    - PsService (increment substance metric)

    Published by (two writers, one event — see CLAUDE.md § Knowledge Substance):
    - UserEntryProcessingService (EXTRACT_ACTIVITIES pipeline, after each
      NEW ``(entry)-[:APPLIES_KNOWLEDGE]->(ku)`` edge write — ADR-069)
    - EntryGroundingService (vector grounding, after each NEW inferred edge)
    """

    knowledge_uid: str
    entry_uid: str
    user_uid: UserUID

    event_type: ClassVar[str] = "knowledge.reflected_in_entry"


@dataclass(frozen=True)
class KnowledgeInformedChoice(BaseEvent):
    """
    Published when a choice/decision is informed by knowledge.

    Increments: choices_informed_count
    Updates: last_choice_informed_date

    HIGH WEIGHT event (0.07 per choice) because applying knowledge
    to real decisions demonstrates practical understanding.

    Subscribers:
    - PsService (increment substance metric)

    Published by:
    - ChoicesService (when choice created with informed_by_knowledge_uids)
    """

    knowledge_uid: str
    choice_uid: str
    user_uid: UserUID

    # Optional context
    choice_title: str | None = None
    choice_outcome: str | None = None  # For tracking effectiveness

    event_type: ClassVar[str] = "knowledge.informed_choice"


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
    - PsService (batch increment substance metrics)

    Published by:
    - TasksService (when task created with applies_knowledge_uids)
    """

    knowledge_uids: tuple[str, ...]
    task_uid: str
    user_uid: UserUID

    # Optional context
    task_title: str | None = None
    task_priority: str | None = None

    event_type: ClassVar[str] = "knowledge.bulk_applied_in_task"

    @property
    def count(self) -> int:
        return len(self.knowledge_uids)


@dataclass(frozen=True)
class KnowledgeBulkBuiltIntoHabit(BaseEvent):
    """
    Published when a habit builds on multiple knowledge units.

    More efficient than publishing N individual KnowledgeBuiltIntoHabit events.

    Subscribers:
    - PsService (batch increment substance metrics)

    Published by:
    - HabitsService (when habit created with builds_on_knowledge_uids)
    """

    knowledge_uids: tuple[str, ...]
    habit_uid: str
    user_uid: UserUID

    # Optional context
    habit_title: str | None = None
    frequency: str | None = None

    event_type: ClassVar[str] = "knowledge.bulk_built_into_habit"

    @property
    def count(self) -> int:
        return len(self.knowledge_uids)


@dataclass(frozen=True)
class KnowledgeBulkInformedChoice(BaseEvent):
    """
    Published when a choice is informed by multiple knowledge units.

    More efficient than publishing N individual KnowledgeInformedChoice events.

    Subscribers:
    - PsService (batch increment substance metrics)

    Published by:
    - ChoicesService (when choice created with informed_by_knowledge_uids)
    """

    knowledge_uids: tuple[str, ...]
    choice_uid: str
    user_uid: UserUID

    # Optional context
    choice_title: str | None = None

    event_type: ClassVar[str] = "knowledge.bulk_informed_choice"

    @property
    def count(self) -> int:
        return len(self.knowledge_uids)


# ============================================================================
# DISPATCH RULE
# ============================================================================

# Publishers choose single vs bulk based on count — never both for the same
# connection (that would double-increment substance metrics):
#
#   ku_uids = request.applies_knowledge_uids
#   if len(ku_uids) == 1:
#       event = KnowledgeAppliedInTask(knowledge_uid=ku_uids[0], ...)
#   else:
#       event = KnowledgeBulkAppliedInTask(knowledge_uids=tuple(ku_uids), ...)
#   await publish_event(self.event_bus, event, self.logger)
#
# Subscribers for all 8 events (4 channels x 2 forms) are wired in:
#   services_bootstrap/_event_wiring.py → PsService handlers
#
# See: /docs/architecture/knowledge_substance_philosophy.md
