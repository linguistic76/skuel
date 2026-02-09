"""
Event Domain Model (Tier 3 - Core)
===================================

Immutable domain model with business logic for events.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for scheduling and habit reinforcement
- Phase 3: GraphContext for cross-domain event intelligence
- Phase 4: QueryIntent selection for event-specific patterns
"""

__version__ = "2.1"  # Updated for Phase 1-4 integration


from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, ClassVar

from core.constants import GraphDepth
from core.models.enums import ActivityStatus, Priority, RecurrencePattern, Visibility

# Phase 1: Query Infrastructure
from core.models.event.event_dto import EventDTO
from core.models.mixins import StatusChecksMixin
from core.models.query import QueryIntent
from core.models.query.graph_traversal import build_graph_context_query


@dataclass(frozen=True)
class Event(StatusChecksMixin):
    """
    Immutable domain model representing a calendar event.

    Contains all business logic and rules for event management.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - event ownership
    title: str
    description: str | None = None

    # Timing (core business data)
    event_date: date = None  # type: ignore[assignment]
    start_time: time = None  # type: ignore[assignment]
    end_time: time = None  # type: ignore[assignment]

    # Type and status
    event_type: str = "PERSONAL"
    status: ActivityStatus = ActivityStatus.SCHEDULED
    visibility: Visibility = Visibility.PRIVATE
    priority: Priority = Priority.MEDIUM

    # Location
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # Organization (immutable)
    tags: tuple[str, ...] = ()

    # Attendees (immutable)
    attendee_emails: tuple[str, ...] = ()
    max_attendees: int | None = None

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None  # type: ignore[assignment]
    recurrence_parent_uid: str | None = None

    # Reminders
    reminder_minutes: int | None = None
    reminder_sent: bool = False

    # Conflicts - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (event)-[:CONFLICTS_WITH]->(other_event)

    # Learning Integration (NEW) - GRAPH-NATIVE
    reinforces_habit_uid: str | None = None
    # Graph relationship: (event)-[:PRACTICES_KNOWLEDGE]->(ku)
    milestone_celebration_for_goal: str | None = None

    # Task Execution (NEW) - GRAPH-NATIVE
    # Graph relationship: (event)-[:EXECUTES_TASK]->(task)

    # Curriculum Integration (NEW - for educational events)
    source_learning_step_uid: str | None = None  # ls: UID if event comes from curriculum
    source_learning_path_uid: str | None = None  # lp: UID for path-level events
    is_milestone_event: bool = False  # True for curriculum milestones
    milestone_type: str | None = None  # 'step_completion', 'path_checkpoint', 'path_completion'
    curriculum_week: int | None = None  # Week in curriculum sequence

    # Quality Tracking (NEW)
    habit_completion_quality: int | None = None  # 1-5
    knowledge_retention_check: bool = False

    # Recurrence (ENHANCED)
    recurrence_maintains_habit: bool = True
    skip_breaks_habit_streak: bool = True

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    # StatusChecksMixin configuration
    # Event uses ActivityStatus (same as Task)
    _completed_statuses: ClassVar[tuple[ActivityStatus, ...]] = (ActivityStatus.COMPLETED,)
    _cancelled_statuses: ClassVar[tuple[ActivityStatus, ...]] = (ActivityStatus.CANCELLED,)
    _terminal_statuses: ClassVar[tuple[ActivityStatus, ...]] = (
        ActivityStatus.COMPLETED,
        ActivityStatus.CANCELLED,
    )
    _active_statuses: ClassVar[tuple[ActivityStatus, ...]] = (ActivityStatus.SCHEDULED,)

    def __post_init__(self) -> None:
        """Set defaults for datetime and metadata fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # Event implements KnowledgeCarrier and ActivityCarrier.
    # Event PRACTICES knowledge - relevance based on learning integration.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Event relevance based on curriculum and learning integration.

        Returns:
            0.0-1.0 based on learning integration
        """
        score = 0.0

        # Curriculum milestone event (highest relevance)
        if self.is_milestone_event:
            score = 0.9

        # From learning step
        if self.source_learning_step_uid:
            score = max(score, 0.8)

        # From learning path
        if self.source_learning_path_uid:
            score = max(score, 0.7)

        # Habit reinforcement
        if self.reinforces_habit_uid:
            score = max(score, 0.5)

        # Goal milestone
        if self.milestone_celebration_for_goal:
            score = max(score, 0.4)

        # Knowledge retention check
        if self.knowledge_retention_check:
            score = max(score, 0.6)

        return score

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity practices.

        Event knowledge is stored as graph relationships.
        This is a GRAPH-NATIVE placeholder - actual data requires service layer.

        Use service.relationships.get_event_knowledge(event_uid) for real data.

        Returns:
            Empty tuple (placeholder - actual KU UIDs via graph query)
        """
        # GRAPH-NATIVE: Real implementation requires service layer query
        # Query: MATCH (event)-[:PRACTICES_KNOWLEDGE]->(ku) RETURN ku.uid
        return ()

    # ==========================================================================
    # TIMING AND SCHEDULING
    # ==========================================================================

    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        if not self.start_time or not self.end_time:
            return 0

        # Convert Neo4j Time to Python time if needed
        from datetime import time as python_time

        from neo4j.time import Time as Neo4jTime

        start_time = self.start_time
        end_time = self.end_time

        # Handle Neo4j Time objects - convert to Python time
        if isinstance(start_time, Neo4jTime):
            start_time = python_time(start_time.hour, start_time.minute, start_time.second)
        if isinstance(end_time, Neo4jTime):
            end_time = python_time(end_time.hour, end_time.minute, end_time.second)

        # Convert times to datetime for calculation
        start = datetime.combine(date.today(), start_time)
        end = datetime.combine(date.today(), end_time)

        # Handle events that cross midnight
        if end < start:
            end += timedelta(days=1)

        duration = end - start
        return int(duration.total_seconds() / 60)

    def start_datetime(self) -> datetime:
        """Get combined start datetime."""
        return datetime.combine(self.event_date, self.start_time)

    def end_datetime(self) -> datetime:
        """Get combined end datetime."""
        end = datetime.combine(self.event_date, self.end_time)
        # Handle events crossing midnight
        if self.end_time < self.start_time:
            end += timedelta(days=1)
        return end

    def is_past(self) -> bool:
        """Check if event is in the past."""
        return self.end_datetime() < datetime.now()

    def is_ongoing(self) -> bool:
        """Check if event is currently happening."""
        now = datetime.now()
        return self.start_datetime() <= now <= self.end_datetime()

    def is_upcoming(self) -> bool:
        """Check if event is in the future."""
        return self.start_datetime() > datetime.now()

    def is_today(self) -> bool:
        """Check if event is today."""
        return self.event_date == date.today()

    def is_tomorrow(self) -> bool:
        """Check if event is tomorrow."""
        return self.event_date == date.today() + timedelta(days=1)

    def is_this_week(self) -> bool:
        """Check if event is this week."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start <= self.event_date <= week_end

    def days_until(self) -> int:
        """Calculate days until event (negative if past)."""
        delta = self.event_date - date.today()
        return delta.days

    def hours_until(self) -> float:
        """Calculate hours until event starts."""
        delta = self.start_datetime() - datetime.now()
        return delta.total_seconds() / 3600

    def is_imminent(self, hours: int = 2) -> bool:
        """Check if event starts within specified hours."""
        hours_left = self.hours_until()
        return 0 <= hours_left <= hours

    # ==========================================================================
    # STATUS AND STATE
    # ==========================================================================
    # is_completed(), is_cancelled(), is_terminal() provided by StatusChecksMixin

    def is_scheduled(self) -> bool:
        """Check if event is scheduled."""
        return self.status == ActivityStatus.SCHEDULED

    def is_active(self) -> bool:
        """Check if event is active (not cancelled or completed)."""
        return not self.is_terminal()

    def needs_reminder(self) -> bool:
        """Check if reminder should be sent."""
        if not self.reminder_minutes or self.reminder_sent:
            return False

        if not self.is_upcoming():
            return False

        minutes_until = self.hours_until() * 60
        return minutes_until <= self.reminder_minutes

    # ==========================================================================
    # ATTENDEES AND CAPACITY
    # ==========================================================================

    def attendee_count(self) -> int:
        """Get number of attendees."""
        return len(self.attendee_emails)

    def is_full(self) -> bool:
        """Check if event is at capacity."""
        if not self.max_attendees:
            return False
        return self.attendee_count() >= self.max_attendees

    def has_capacity(self) -> bool:
        """Check if event has room for more attendees."""
        if not self.max_attendees:
            return True
        return self.attendee_count() < self.max_attendees

    def remaining_capacity(self) -> int | None:
        """Get remaining capacity."""
        if not self.max_attendees:
            return None
        return max(0, self.max_attendees - self.attendee_count())

    def has_attendee(self, email: str) -> bool:
        """Check if email is in attendees list."""
        return email.lower() in [e.lower() for e in self.attendee_emails]

    # ==========================================================================
    # RECURRENCE
    # ==========================================================================

    def is_recurring(self) -> bool:
        """Check if event has recurrence pattern."""
        return self.recurrence_pattern is not None

    def is_recurrence_instance(self) -> bool:
        """Check if event is instance of recurring event."""
        return self.recurrence_parent_uid is not None

    def is_recurrence_active(self) -> bool:
        """Check if recurrence is still active."""
        if not self.is_recurring():
            return False
        if not self.recurrence_end_date:
            return True
        return date.today() <= self.recurrence_end_date

    def next_recurrence_date(self) -> date | None:
        """Calculate next recurrence date."""
        if not self.is_recurring():
            return None

        base_date = self.event_date

        if self.recurrence_pattern == RecurrencePattern.DAILY:
            return base_date + timedelta(days=1)
        elif self.recurrence_pattern == RecurrencePattern.WEEKLY:
            return base_date + timedelta(weeks=1)
        elif self.recurrence_pattern == RecurrencePattern.BIWEEKLY:
            return base_date + timedelta(weeks=2)
        elif self.recurrence_pattern == RecurrencePattern.MONTHLY:
            # Simple approximation - same day next month
            if base_date.month == 12:
                return base_date.replace(year=base_date.year + 1, month=1)
            else:
                return base_date.replace(month=base_date.month + 1)

        return None

    # ==========================================================================
    # CONFLICTS AND OVERLAPS
    # ==========================================================================

    def has_conflicts(self) -> bool:
        """
        Check if event has conflicts.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "CONFLICTS_WITH", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def overlaps_with(self, other: "Event") -> bool:
        """Check if this event overlaps with another."""
        if self.event_date != other.event_date:
            return False

        # Check time overlap
        return not (
            self.end_datetime() <= other.start_datetime()
            or self.start_datetime() >= other.end_datetime()
        )

    # ==========================================================================
    # LEARNING INTEGRATION
    # ==========================================================================

    def is_habit_event(self) -> bool:
        """Check if event reinforces a habit."""
        return self.reinforces_habit_uid is not None or self.recurrence_maintains_habit

    def is_learning_event(self) -> bool:
        """
        Check if event is related to learning.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "PRACTICES_KNOWLEDGE", "outgoing") > 0
        """
        return (
            self.knowledge_retention_check or self.milestone_celebration_for_goal is not None
        )  # Partial check - missing PRACTICES_KNOWLEDGE relationship check

    def is_milestone_event_for_goal(self) -> bool:
        """Check if event celebrates a goal milestone."""
        return self.milestone_celebration_for_goal is not None

    def is_practice_event(self) -> bool:
        """
        Check if event is for knowledge practice.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "PRACTICES_KNOWLEDGE", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def has_tasks(self) -> bool:
        """
        Check if event executes specific tasks.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "EXECUTES_TASK", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def habit_quality_score(self) -> float:
        """
        Get normalized habit quality score (0.0-1.0).
        """
        if not self.habit_completion_quality:
            return 0.0
        return self.habit_completion_quality / 5.0

    # ==========================================================================
    # CURRICULUM INTEGRATION (Event ↔ ls ↔ lp bridge)
    # ==========================================================================

    def is_from_curriculum(self) -> bool:
        """Check if event originated from curriculum (learning step or path)."""
        return (
            self.source_learning_step_uid is not None or self.source_learning_path_uid is not None
        )

    def is_from_learning_step(self) -> bool:
        """Check if event originated from a learning step."""
        return self.source_learning_step_uid is not None

    def is_from_learning_path(self) -> bool:
        """Check if event is a path-level milestone."""
        return self.source_learning_path_uid is not None

    def is_curriculum_milestone(self) -> bool:
        """Check if event is a curriculum milestone (not just goal milestone)."""
        return self.is_milestone_event and self.milestone_type is not None

    def is_step_completion_event(self) -> bool:
        """Check if event celebrates step completion."""
        return self.milestone_type == "step_completion"

    def is_path_checkpoint_event(self) -> bool:
        """Check if event is a path checkpoint review."""
        return self.milestone_type == "path_checkpoint"

    def is_path_completion_event(self) -> bool:
        """Check if event celebrates path completion."""
        return self.milestone_type == "path_completion"

    def get_curriculum_context(self) -> dict:
        """
        Get complete curriculum context for this event.

        GRAPH-NATIVE: practices_knowledge and executes_tasks require service layer queries.
        Use: backend.get_related_uids(uid, "PRACTICES_KNOWLEDGE", "outgoing")
        Use: backend.get_related_uids(uid, "EXECUTES_TASK", "outgoing")

        Returns:
            Dictionary with curriculum linkage information (UID lists as empty placeholders)
        """
        return {
            "is_curriculum_event": self.is_from_curriculum(),
            "source_learning_step": self.source_learning_step_uid,
            "source_learning_path": self.source_learning_path_uid,
            "is_milestone": self.is_curriculum_milestone(),
            "milestone_type": self.milestone_type,
            "curriculum_week": self.curriculum_week,
            "practices_knowledge": [],  # GRAPH QUERY: get_related_uids(uid, "PRACTICES_KNOWLEDGE", "outgoing")
            "executes_tasks": [],  # GRAPH QUERY: get_related_uids(uid, "EXECUTES_TASK", "outgoing")
            "is_study_session": False,  # Requires graph query
            "learning_impact": 0.0,  # Requires graph query
        }

    def is_study_session(self) -> bool:
        """
        Check if event is a dedicated study session for curriculum.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "PRACTICES_KNOWLEDGE", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def learning_impact_score(self) -> float:
        """
        Calculate the learning impact of this event.

        GRAPH-NATIVE: Knowledge practice and task execution require service layer queries.
        Use: backend.count_related(uid, "PRACTICES_KNOWLEDGE", "outgoing")
        Use: backend.count_related(uid, "EXECUTES_TASK", "outgoing")

        Returns:
            Partial score from node properties only (0.0-0.6 range)
            Service layer must enrich with graph relationship counts for full 0.0-1.0 range
        """
        score = 0.0

        # Habit reinforcement (30%)
        if self.reinforces_habit_uid:
            score += 0.3
            # Add quality bonus
            score += self.habit_quality_score() * 0.1

        # Milestone celebration (20%)
        if self.milestone_celebration_for_goal:
            score += 0.2

        # Knowledge retention check (10%)
        if self.knowledge_retention_check:
            score += 0.1

        # NOTE: Knowledge practice (30%) and task execution (10%) require graph queries
        # Service layer must add these components using count_related()

        return min(score, 1.0)

    def completion_value(self) -> float:
        """
        Calculate the value of completing this event.

        Combines importance, learning impact, and habit maintenance.
        """
        importance = self.importance_score() / 10.0  # Normalize to 0-1
        learning = self.learning_impact_score()

        # Extra weight for habit-breaking risk
        habit_risk = 0.2 if (self.is_habit_event() and self.skip_breaks_habit_streak) else 0.0

        return min(importance * 0.4 + learning * 0.4 + habit_risk, 1.0)

    # ==========================================================================
    # TAGS AND ORGANIZATION
    # ==========================================================================

    def has_tag(self, tag: str) -> bool:
        """Check if event has specific tag."""
        return tag.lower() in [t.lower() for t in self.tags]

    def is_meeting(self) -> bool:
        """Check if event is a meeting type."""
        return self.event_type in ["MEETING", "CONFERENCE", "WORKSHOP"]

    def is_personal(self) -> bool:
        """Check if event is personal."""
        return self.event_type == "PERSONAL"

    def is_work(self) -> bool:
        """Check if event is work-related."""
        return self.event_type == "WORK"

    def is_public(self) -> bool:
        """Check if event is public."""
        return self.visibility == Visibility.PUBLIC

    def is_private(self) -> bool:
        """Check if event is private."""
        return self.visibility == Visibility.PRIVATE

    # ==========================================================================
    # PRIORITY AND IMPORTANCE
    # ==========================================================================

    def is_high_priority(self) -> bool:
        """Check if event is high or critical priority."""
        return self.priority in [Priority.HIGH, Priority.CRITICAL]

    def importance_score(self) -> int:
        """
        Calculate importance score (0-10).

        Factors:
        - Priority (0-4 points)
        - Meeting type (2 points)
        - Attendee count (1-2 points)
        - Imminent (2 points)
        """
        score = 0

        # Priority
        priority_scores = {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.CRITICAL: 4,
        }
        score += priority_scores.get(self.priority, 0)

        # Meeting importance
        if self.is_meeting():
            score += 2

        # Attendees
        if self.attendee_count() > 5:
            score += 2
        elif self.attendee_count() > 0:
            score += 1

        # Timing
        if self.is_imminent():
            score += 2

        return min(score, 10)

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: "EventDTO") -> "Event":
        """
        Create immutable Event from mutable DTO.

        GRAPH-NATIVE: UID list fields are NOT transferred from DTO to domain model.
        Relationships exist only as Neo4j edges, queried via service layer.
        """

        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            title=dto.title,
            description=dto.description,
            event_date=dto.event_date,
            start_time=dto.start_time,
            end_time=dto.end_time,
            event_type=dto.event_type,
            status=dto.status,
            visibility=dto.visibility,
            priority=dto.priority,
            location=dto.location,
            is_online=dto.is_online,
            meeting_url=dto.meeting_url,
            tags=tuple(dto.tags),
            attendee_emails=tuple(dto.attendee_emails),
            max_attendees=dto.max_attendees,
            recurrence_pattern=dto.recurrence_pattern,
            recurrence_end_date=dto.recurrence_end_date,
            recurrence_parent_uid=dto.recurrence_parent_uid,
            reminder_minutes=dto.reminder_minutes,
            reminder_sent=dto.reminder_sent,
            # UID list fields REMOVED - relationships stored as graph edges only:
            # conflicts_with REMOVED - use (event)-[:CONFLICTS_WITH]->(event)
            # practices_knowledge_uids REMOVED - use (event)-[:PRACTICES_KNOWLEDGE]->(ku)
            # executes_tasks REMOVED - use (event)-[:EXECUTES_TASK]->(task)
            reinforces_habit_uid=getattr(dto, "reinforces_habit_uid", None),
            milestone_celebration_for_goal=getattr(dto, "milestone_celebration_for_goal", None),
            source_learning_step_uid=getattr(dto, "source_learning_step_uid", None),
            source_learning_path_uid=getattr(dto, "source_learning_path_uid", None),
            is_milestone_event=getattr(dto, "is_milestone_event", False),
            milestone_type=getattr(dto, "milestone_type", None),
            curriculum_week=getattr(dto, "curriculum_week", None),
            habit_completion_quality=getattr(dto, "habit_completion_quality", None),
            knowledge_retention_check=getattr(dto, "knowledge_retention_check", False),
            recurrence_maintains_habit=getattr(dto, "recurrence_maintains_habit", True),
            skip_breaks_habit_streak=getattr(dto, "skip_breaks_habit_streak", True),
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            metadata=getattr(dto, "metadata", {})
            or {},  # Copy metadata from DTO (rich context storage)
        )

    def to_dto(self) -> "EventDTO":
        """
        Convert to mutable DTO.

        GRAPH-NATIVE: UID list fields set to empty lists.
        Service layer must populate from graph queries before API serialization.
        """
        return EventDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            title=self.title,
            description=self.description,
            event_date=self.event_date,
            start_time=self.start_time,
            end_time=self.end_time,
            event_type=self.event_type,
            status=self.status,
            visibility=self.visibility,
            priority=self.priority,
            location=self.location,
            is_online=self.is_online,
            meeting_url=self.meeting_url,
            tags=list(self.tags),
            attendee_emails=list(self.attendee_emails),
            max_attendees=self.max_attendees,
            recurrence_pattern=self.recurrence_pattern,
            recurrence_end_date=self.recurrence_end_date,
            recurrence_parent_uid=self.recurrence_parent_uid,
            reminder_minutes=self.reminder_minutes,
            reminder_sent=self.reminder_sent,
            # PHASE 3B: conflicts_with, practices_knowledge_uids, executes_tasks are graph relationships
            # Services query these separately via relationship services
            reinforces_habit_uid=self.reinforces_habit_uid,
            milestone_celebration_for_goal=self.milestone_celebration_for_goal,
            source_learning_step_uid=self.source_learning_step_uid,
            source_learning_path_uid=self.source_learning_path_uid,
            is_milestone_event=self.is_milestone_event,
            milestone_type=self.milestone_type,
            curriculum_week=self.curriculum_week,
            habit_completion_quality=self.habit_completion_quality,
            knowledge_retention_check=self.knowledge_retention_check,
            recurrence_maintains_habit=self.recurrence_maintains_habit,
            skip_breaks_habit_streak=self.skip_breaks_habit_streak,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata,  # Copy metadata to DTO (rich context storage)
        )

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_scheduling_context_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for scheduling context

        Finds conflicts, related events, and time-based patterns.

        Args:
            depth: Maximum relationship depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=depth
        )

    def build_habit_reinforcement_query(self) -> str:
        """
        Build pure Cypher query for habit reinforcement

        Finds habits this event reinforces and related practice patterns.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_task_execution_query(self) -> str:
        """
        Build pure Cypher query for task execution context

        Finds tasks to be executed during this event.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.SPECIFIC, depth=GraphDepth.DIRECT
        )

    def build_knowledge_practice_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for knowledge practice

        Finds knowledge units practiced during this event.

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=depth
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on event characteristics.

        Business rules (December 2025 - SCHEDULED_ACTION priority):
        - Milestone events → HIERARCHICAL (goal progress context)
        - Default → SCHEDULED_ACTION (events as scheduled task execution)

        The SCHEDULED_ACTION intent emphasizes:
        - Tasks being executed during this event
        - Knowledge being practiced
        - Habits being reinforced
        - Goals being advanced
        - Scheduling conflicts

        Returns:
            Recommended QueryIntent for this event
        """
        # Milestone events need hierarchical goal context
        if self.milestone_celebration_for_goal is not None:
            return QueryIntent.HIERARCHICAL

        # All other events are scheduled actions - task execution, practice, reinforcement
        return QueryIntent.SCHEDULED_ACTION

    # ==========================================================================
    # PHASE 2: GRAPHENTITY PROTOCOL IMPLEMENTATION
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this event exist? One-sentence reasoning.

        GRAPH-NATIVE: Relationship counts require service layer queries.
        Service should enrich this explanation with graph relationship data.

        Returns:
            Human-readable explanation of event's purpose and context (partial)
        """
        parts = [self.title]

        # Primary purpose indicators
        if self.reinforces_habit_uid:
            parts.append(f"Reinforces habit: {self.reinforces_habit_uid}")

        if self.milestone_celebration_for_goal:
            parts.append(f"Celebrates goal milestone: {self.milestone_celebration_for_goal}")

        # NOTE: Service should add:
        # - Task execution count via count_related(uid, "EXECUTES_TASK")
        # - Knowledge practice count via count_related(uid, "PRACTICES_KNOWLEDGE")

        # Learning path context
        if self.source_learning_step_uid:
            parts.append(f"From learning step: {self.source_learning_step_uid}")

        if self.is_milestone_event:
            parts.append(f"Curriculum milestone: {self.milestone_type}")

        # Recurrence pattern
        if self.recurrence_pattern:
            parts.append(f"Recurring: {self.recurrence_pattern.value}")

        # Scheduling context
        if self.event_date:
            parts.append(f"Scheduled: {self.event_date}")

        return ". ".join(parts)

    def get_upstream_influences(self) -> list[dict]:
        """
        WHAT shaped this event? Entities that influenced its creation.

        GRAPH-NATIVE: Task and knowledge relationships require service layer queries.
        Service should enrich this list with graph relationship data.

        Returns:
            List of dicts representing upstream influences (partial - from node properties only):
            - Habits that need reinforcement
            - Goals that require milestone events
            - Learning paths/steps that scheduled this event
            - Recurrence parent

        Service layer should add:
            - Tasks that need execution time (via EXECUTES_TASK relationships)
            - Knowledge that needs practice (via PRACTICES_KNOWLEDGE relationships)
        """
        influences = []

        # 1. Habit reinforcement (recurring events)
        if self.reinforces_habit_uid:
            influences.append(
                {
                    "uid": self.reinforces_habit_uid,
                    "entity_type": "habit",
                    "relationship_type": "reinforces",
                    "reasoning": "Event scheduled to maintain habit streak",
                    "strength": 1.0 if self.recurrence_maintains_habit else 0.7,
                }
            )

        # 2. Goal milestones (celebration events)
        if self.milestone_celebration_for_goal:
            influences.append(
                {
                    "uid": self.milestone_celebration_for_goal,
                    "entity_type": "goal",
                    "relationship_type": "celebrates",
                    "reasoning": "Event celebrates goal progress milestone",
                    "strength": 1.0,
                }
            )

        # 3. Learning step (curriculum-driven events)
        if self.source_learning_step_uid:
            influences.append(
                {
                    "uid": self.source_learning_step_uid,
                    "entity_type": "learning_step",
                    "relationship_type": "scheduled_by",
                    "reasoning": "Event scheduled by learning curriculum",
                    "strength": 0.9,
                    "milestone": self.is_milestone_event,
                    "milestone_type": self.milestone_type,
                }
            )

        # 4. Learning path (path-level events)
        if self.source_learning_path_uid:
            influences.append(
                {
                    "uid": self.source_learning_path_uid,
                    "entity_type": "learning_path",
                    "relationship_type": "part_of",
                    "reasoning": "Event is part of learning path sequence",
                    "strength": 0.8,
                    "curriculum_week": self.curriculum_week,
                }
            )

        # 5. Recurrence parent (for recurring event instances)
        if self.recurrence_parent_uid:
            influences.append(
                {
                    "uid": self.recurrence_parent_uid,
                    "entity_type": "event",
                    "relationship_type": "spawned_from",
                    "reasoning": "Event is recurring instance of parent event",
                    "strength": 1.0,
                }
            )

        # NOTE: Service layer should add:
        # - Tasks (via get_related_uids(uid, "EXECUTES_TASK", "outgoing"))
        # - Knowledge (via get_related_uids(uid, "PRACTICES_KNOWLEDGE", "outgoing"))

        return influences

    def get_downstream_impacts(self) -> list[dict]:
        """
        WHAT does this event shape? Entities influenced by this event.

        GRAPH-NATIVE: Task and knowledge relationships require service layer queries.
        Service should enrich this list with graph relationship data.

        Returns:
            List of dicts representing downstream impacts (partial - from node properties only):
            - Habit streaks maintained
            - Goals advanced through milestones
            - Learning path progression
            - Future recurring instances

        Service layer should add:
            - Tasks completed (via EXECUTES_TASK relationships)
            - Knowledge reinforced (via PRACTICES_KNOWLEDGE relationships)
        """
        impacts = []

        # 1. Habit streak maintenance
        if self.reinforces_habit_uid and self.status == ActivityStatus.COMPLETED:
            impacts.append(
                {
                    "uid": self.reinforces_habit_uid,
                    "entity_type": "habit",
                    "relationship_type": "maintains_streak",
                    "reasoning": "Completed event maintains habit streak",
                    "strength": 1.0 if self.recurrence_maintains_habit else 0.6,
                    "quality": self.habit_completion_quality,
                }
            )

        # 2. Goal progress through milestones
        if self.milestone_celebration_for_goal and self.status == ActivityStatus.COMPLETED:
            impacts.append(
                {
                    "uid": self.milestone_celebration_for_goal,
                    "entity_type": "goal",
                    "relationship_type": "advances",
                    "reasoning": "Milestone event marks goal progress",
                    "strength": 0.9,
                    "milestone_type": "celebration",
                }
            )

        # 3. Learning path progression
        if (
            self.source_learning_step_uid
            and self.is_milestone_event
            and self.status == ActivityStatus.COMPLETED
        ):
            impacts.append(
                {
                    "uid": self.source_learning_step_uid,
                    "entity_type": "learning_step",
                    "relationship_type": "completes",
                    "reasoning": f"Milestone event marks {self.milestone_type} completion",
                    "strength": 1.0,
                    "milestone_type": self.milestone_type,
                }
            )

        # 4. Future recurring instances (if this is a parent recurring event)
        if self.recurrence_pattern and not self.recurrence_parent_uid:
            impacts.append(
                {
                    "uid": f"{self.uid}:recurring",
                    "entity_type": "event_series",
                    "relationship_type": "spawns",
                    "reasoning": f"Parent event spawns {self.recurrence_pattern.value} instances",
                    "strength": 1.0,
                    "pattern": self.recurrence_pattern.value,
                    "end_date": self.recurrence_end_date,
                }
            )

        # NOTE: Service layer should add:
        # - Tasks (via get_related_uids(uid, "EXECUTES_TASK", "outgoing"))
        # - Knowledge (via get_related_uids(uid, "PRACTICES_KNOWLEDGE", "outgoing"))

        return impacts

    def get_relationship_summary(self) -> dict:
        """
        Get comprehensive relationship context for this event.

        GRAPH-NATIVE: Some metrics require service layer queries.
        Service should enrich metrics with graph relationship counts.

        Returns:
            Dict containing:
            - explanation: Why this event exists (partial)
            - upstream: What shaped it (partial)
            - downstream: What it shapes (partial)
            - upstream_count: Number of upstream influences (partial)
            - downstream_count: Number of downstream impacts (partial)
            - event_metrics: Scheduling, completion, and integration details (partial)
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
            "event_metrics": {
                "status": self.status.value,
                "priority": self.priority.value,
                "event_type": self.event_type,
                "is_recurring": self.recurrence_pattern is not None,
                "recurrence_pattern": self.recurrence_pattern.value
                if self.recurrence_pattern
                else None,
                "reinforces_habit": self.reinforces_habit_uid is not None,
                "executes_tasks": 0,  # GRAPH QUERY: count_related(uid, "EXECUTES_TASK")
                "practices_knowledge": 0,  # GRAPH QUERY: count_related(uid, "PRACTICES_KNOWLEDGE")
                "is_milestone": self.is_milestone_event,
                "milestone_type": self.milestone_type,
                "has_conflicts": False,  # GRAPH QUERY: count_related(uid, "CONFLICTS_WITH") > 0
                "quality_score": self.habit_completion_quality,
            },
        }

    def __str__(self) -> str:
        """String representation."""
        return f"Event(uid={self.uid}, title='{self.title}', date={self.event_date})"
