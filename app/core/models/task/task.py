"""
Task Domain Model (Tier 3 - Core)
==================================

Immutable domain model with business logic for tasks.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for task dependencies and impact
- Phase 3: GraphContext for cross-domain task intelligence
- Phase 4: QueryIntent selection for task-specific patterns
"""

from __future__ import annotations

__version__ = "2.1"  # Updated for Phase 1-4 integration


from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# Phase 1: Query Infrastructure
from typing import TYPE_CHECKING, Any, ClassVar

from core.constants import GraphDepth
from core.models.mixins import StatusChecksMixin
from core.models.query import QueryIntent
from core.models.query.graph_traversal import build_graph_context_query
from core.models.shared_enums import ActivityStatus, Priority, RecurrencePattern

if TYPE_CHECKING:
    from core.models.task.task_dto import TaskDTO
    from core.models.task.task_relationships import TaskRelationships


@dataclass(frozen=True)
class Task(StatusChecksMixin):
    """
    Immutable domain model representing a task.

    Contains all business logic and rules for task management.

    ## Graph Access Patterns (See /docs/GRAPH_ACCESS_PATTERNS.md)

    This model implements BOTH graph access patterns:

    **Pattern 1 (Graph-Aware Models)**: Direct relationship UIDs
    - Fields: parent_uid, subtask_uids, prerequisite_task_uids, applies_knowledge_uids
    - Methods: is_learning_task(), has_prerequisites(), is_parent() [marked with [P1]]
    - Use for: Instant checks, validation, simple queries

    **Pattern 2 (Graph-Native Queries)**: Graph intelligence queries
    - Methods: build_dependency_query(), build_completion_impact_query() [marked with [P2]]
    - Use for: Multi-hop traversal, cross-domain analysis, Askesis context

    **Example - Using Both Patterns Together**:
    ```python
    # Pattern 1: Quick validation
    if task.has_prerequisites():  # Instant
        print(f"Task has {len(task.prerequisite_task_uids)} prerequisites")

    # Pattern 2: Deep analysis
    if task.is_learning_task():  # Pattern 1 informs Pattern 2
        query = task.build_knowledge_context_query(GraphDepth.NEIGHBORHOOD)
        context = await graph_service.execute_graph_query(query)
    ```

    Index Strategy:
    - uid: Unique index (primary lookup)
    - priority, status: Regular indexes (common filters)
    - due_date, scheduled_date: Regular indexes (date-based queries)
    """

    # Identity
    uid: str = field(metadata={"index": True, "unique": True})
    user_uid: str = field(metadata={"index": True})  # REQUIRED - task ownership
    title: str
    description: str | None = None

    # Scheduling
    due_date: date | None = field(default=None, metadata={"index": True})
    scheduled_date: date | None = field(default=None, metadata={"index": True})
    completion_date: date | None = None  # type: ignore[assignment]

    # Time tracking
    duration_minutes: int = 30
    actual_minutes: int | None = None

    # Status and priority
    status: ActivityStatus = field(default=ActivityStatus.DRAFT, metadata={"index": True})
    priority: Priority = field(default=Priority.MEDIUM, metadata={"index": True})

    # Organization
    project: str | None = None
    assignee: str | None = None
    tags: tuple[str, ...] = ()

    # Hierarchy (immutable)
    parent_uid: str | None = None
    # GRAPH-NATIVE: subtask_uids removed - query via service.relationships.get_task_subtasks()

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None  # type: ignore[assignment]
    recurrence_parent_uid: str | None = None

    # Learning Integration (NEW)
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None
    # GRAPH-NATIVE: applies_knowledge_uids removed - query via service.relationships.get_task_knowledge()
    # GRAPH-NATIVE: aligned_principle_uids removed - query via service.relationships.get_task_principles()
    source_learning_step_uid: str | None = None  # ls: UID if task comes from learning step

    # Progress Impact (NEW)
    goal_progress_contribution: float = 0.0  # 0-1
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False

    # Dependencies (ENHANCED)
    # GRAPH-NATIVE: prerequisite_knowledge_uids removed - query via service.relationships.get_task_prerequisite_knowledge()
    # GRAPH-NATIVE: prerequisite_task_uids removed - query via service.relationships.get_task_prerequisite_tasks()
    # GRAPH-NATIVE: enables_task_uids removed - query via service.relationships.get_task_enables()

    # Scheduling (enhanced)
    scheduled_event_uid: str | None = None  # Link to Event

    # Completion (ENHANCED)
    completion_updates_goal: bool = True
    # GRAPH-NATIVE: completion_triggers_tasks removed - query via service.relationships.get_task_triggers()
    # GRAPH-NATIVE: completion_unlocks_knowledge removed - query via service.relationships.get_task_unlocks_knowledge()

    # Knowledge Intelligence (Enhanced - Phase 1 Week 2)
    # GRAPH-NATIVE: inferred_knowledge_uids removed - query via service.relationships.get_task_inferred_knowledge()
    knowledge_confidence_scores: dict[str, float] = None  # type: ignore[assignment]
    knowledge_inference_metadata: dict[str, Any] = None  # type: ignore[assignment]
    learning_opportunities_count: int = 0
    # knowledge_patterns_detected: Computed from knowledge relationships, not stored

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    # StatusChecksMixin configuration
    _completed_statuses: ClassVar[tuple[ActivityStatus, ...]] = (ActivityStatus.COMPLETED,)
    _cancelled_statuses: ClassVar[tuple[ActivityStatus, ...]] = (ActivityStatus.CANCELLED,)
    _terminal_statuses: ClassVar[tuple[ActivityStatus, ...]] = (
        ActivityStatus.COMPLETED,
        ActivityStatus.CANCELLED,
    )
    _active_statuses: ClassVar[tuple[ActivityStatus, ...]] = (
        ActivityStatus.DRAFT,
        ActivityStatus.SCHEDULED,
        ActivityStatus.IN_PROGRESS,
        ActivityStatus.PAUSED,
        ActivityStatus.BLOCKED,
    )

    def __post_init__(self) -> None:
        """Set defaults for datetime and dict fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.knowledge_confidence_scores is None:
            object.__setattr__(self, "knowledge_confidence_scores", {})
        if self.knowledge_inference_metadata is None:
            object.__setattr__(self, "knowledge_inference_metadata", {})
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # Task implements KnowledgeCarrier and ActivityCarrier.
    # Task APPLIES knowledge - relevance based on learning integration.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Task relevance based on learning integration fields.
        Uses learning_alignment_score() for partial score, with bonuses
        for direct curriculum connection.

        Returns:
            0.0-1.0 based on learning integration
        """
        score = 0.0

        # Direct curriculum connection (highest relevance)
        if self.source_learning_step_uid:
            score = 0.8

        # Goal alignment
        if self.fulfills_goal_uid:
            score = max(score, 0.5)

        # Habit integration
        if self.reinforces_habit_uid:
            score = max(score, 0.4)

        # Knowledge mastery check
        if self.knowledge_mastery_check:
            score = max(score, 0.6)

        return score

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity applies.

        Task knowledge is stored as graph relationships.
        This is a GRAPH-NATIVE placeholder - actual data requires service layer.

        Use service.relationships.get_task_knowledge(task_uid) for real data.

        Returns:
            Empty tuple (placeholder - actual KU UIDs via graph query)
        """
        # GRAPH-NATIVE: Real implementation requires service layer query
        # Query: MATCH (task)-[:APPLIES_KNOWLEDGE]->(ku) RETURN ku.uid
        return ()

    def learning_impact_score(self) -> float:
        """
        Calculate learning impact when this task completes.

        Used by event-driven updates to increment KU substance counters.

        Returns:
            Impact score 0.0-1.0
        """
        score = 0.0

        # From learning step (highest impact)
        if self.source_learning_step_uid:
            score += 0.4

        # Goal contribution
        score += self.goal_progress_contribution * 0.3

        # Mastery check
        if self.knowledge_mastery_check:
            score += 0.2

        # Habit streak
        if self.habit_streak_maintainer:
            score += 0.1

        return min(1.0, score)

    # ==========================================================================
    # STATUS CHECKS
    # ==========================================================================
    # is_completed(), is_cancelled(), is_terminal() provided by StatusChecksMixin

    def is_blocked(self) -> bool:
        """Check if task is blocked."""
        return self.status == ActivityStatus.BLOCKED

    def is_in_progress(self) -> bool:
        """Check if task is in progress."""
        return self.status == ActivityStatus.IN_PROGRESS

    def is_scheduled(self) -> bool:
        """Check if task is scheduled."""
        return self.status == ActivityStatus.SCHEDULED

    def is_draft(self) -> bool:
        """Check if task is in draft status."""
        return self.status == ActivityStatus.DRAFT

    def is_active(self) -> bool:
        """Check if task is active (not completed or cancelled)."""
        return not self.is_terminal()

    # ==========================================================================
    # TIME AND SCHEDULING
    # ==========================================================================

    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if not self.due_date or not self.is_active():
            return False
        return date.today() > self.due_date

    def days_until_due(self) -> int | None:
        """Calculate days until due date."""
        if not self.due_date:
            return None
        delta = self.due_date - date.today()
        return delta.days

    def is_due_soon(self, days: int = 3) -> bool:
        """Check if task is due within specified days."""
        days_left = self.days_until_due()
        if days_left is None:
            return False
        return 0 <= days_left <= days

    def is_due_today(self) -> bool:
        """Check if task is due today."""
        return self.due_date == date.today() if self.due_date else False

    def is_scheduled_today(self) -> bool:
        """Check if task is scheduled for today."""
        return self.scheduled_date == date.today() if self.scheduled_date else False

    def estimated_end_time(self) -> datetime | None:
        """Calculate estimated end time if scheduled."""
        if not self.scheduled_date:
            return None
        # Assume 9 AM start if no specific time
        start = datetime.combine(self.scheduled_date, datetime.min.time().replace(hour=9))
        return start + timedelta(minutes=self.duration_minutes)

    # ==========================================================================
    # HIERARCHY AND RELATIONSHIPS
    # ==========================================================================

    def is_parent(self) -> bool:
        """
        Check if task has subtasks.

        GRAPH-NATIVE (October 26, 2025): Service layer must query graph relationships.
        Use: backend.count_related(uid, "HAS_CHILD", "outgoing") > 0

        Returns:
            True (placeholder - actual value from service layer graph query)
        """
        # Query required: (task)-[:HAS_CHILD]->(subtask)
        return True  # Placeholder - service queries backend.count_related()

    def is_subtask(self) -> bool:
        """
        Check if task is a subtask of another.

        Direct property check - no graph query needed.
        """
        return self.parent_uid is not None

    def is_standalone(self) -> bool:
        """Check if task has no parent or children."""
        return not self.is_parent() and not self.is_subtask()

    # ==========================================================================
    # RECURRENCE
    # ==========================================================================

    def is_recurring(self) -> bool:
        """Check if task has recurrence pattern."""
        return self.recurrence_pattern is not None

    def is_recurrence_instance(self) -> bool:
        """Check if task is an instance of a recurring task."""
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
        if not self.is_recurring() or not self.due_date:
            return None

        base_date = self.completion_date or self.due_date

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
    # PRIORITY AND URGENCY
    # ==========================================================================

    def is_high_priority(self) -> bool:
        """Check if task is high or critical priority."""
        return self.priority in [Priority.HIGH, Priority.CRITICAL]

    def is_urgent(self) -> bool:
        """
        Check if task is urgent.

        Urgent = high priority OR overdue OR due today
        """
        return self.is_high_priority() or self.is_overdue() or self.is_due_today()

    def urgency_score(self) -> int:
        """
        Calculate urgency score (0-10).

        Factors:
        - Priority (0-4 points)
        - Days until due (0-3 points)
        - Overdue (3 points)
        """
        score = 0

        # Priority score
        priority_scores = {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.CRITICAL: 4,
        }
        score += priority_scores.get(self.priority, 0)

        # Due date score
        if self.is_overdue() or self.is_due_today():
            score += 3
        elif self.is_due_soon(days=3):
            score += 2
        elif self.is_due_soon(days=7):
            score += 1

        return min(score, 10)

    # ==========================================================================
    # PROGRESS AND METRICS
    # ==========================================================================

    def progress_percentage(self) -> float:
        """
        Calculate progress percentage.

        - Draft: 0%
        - Scheduled: 10%
        - In Progress: 50%
        - Blocked: 50%
        - Completed: 100%
        - Cancelled: 0%
        """
        progress_map = {
            ActivityStatus.DRAFT: 0.0,
            ActivityStatus.SCHEDULED: 10.0,
            ActivityStatus.IN_PROGRESS: 50.0,
            ActivityStatus.BLOCKED: 50.0,
            ActivityStatus.COMPLETED: 100.0,
            ActivityStatus.CANCELLED: 0.0,
        }
        return progress_map.get(self.status, 0.0)

    def efficiency_ratio(self) -> float | None:
        """
        Calculate efficiency ratio (actual vs estimated time).

        Returns None if not completed or no actual time recorded.
        """
        if not self.is_completed() or not self.actual_minutes:
            return None
        if self.duration_minutes == 0:
            return 1.0
        return self.duration_minutes / self.actual_minutes

    def was_on_time(self) -> bool | None:
        """
        Check if task was completed on time.

        Returns None if not completed.
        """
        if not self.is_completed() or not self.due_date or not self.completion_date:
            return None
        return self.completion_date <= self.due_date

    # ==========================================================================
    # LEARNING INTEGRATION
    # ==========================================================================

    def is_learning_task(self) -> bool:
        """
        Check if task is related to learning.

        GRAPH-NATIVE (October 26, 2025): Service layer must query graph relationships.
        Use: backend.count_related(uid, "APPLIES_KNOWLEDGE") > 0

        Returns True if task has learning relationships (goal, knowledge, mastery check).
        """
        # Query required: (task)-[:APPLIES_KNOWLEDGE]->(ku)
        return (
            self.fulfills_goal_uid is not None or self.knowledge_mastery_check
            # applies_knowledge_uids removed - query via backend
        )

    def is_habit_task(self) -> bool:
        """Check if task reinforces a habit."""
        return self.reinforces_habit_uid is not None or self.habit_streak_maintainer

    def is_milestone_task(self) -> bool:
        """
        Check if task is a major milestone.

        GRAPH-NATIVE (October 26, 2025): Some checks require graph queries.
        Use: backend.count_related(uid, "UNLOCKS_KNOWLEDGE") > 0 for unlock check
        """
        # Query required: (task)-[:UNLOCKS_KNOWLEDGE]->(ku)
        return (
            self.goal_progress_contribution >= 0.2  # 20% or more of goal
            or self.knowledge_mastery_check
            # completion_unlocks_knowledge removed - query via backend
        )

    def has_prerequisites(self) -> bool:
        """
        Check if task has prerequisites.

        GRAPH-NATIVE (October 26, 2025): Service layer must query graph relationships.
        Use: backend.count_related(uid, "REQUIRES_PREREQUISITE") > 0 or
             backend.count_related(uid, "REQUIRES_KNOWLEDGE") > 0
        """
        # Query required:
        # - (task)-[:REQUIRES_PREREQUISITE]->(prereq_task)
        # - (task)-[:REQUIRES_KNOWLEDGE]->(ku)
        return False  # Placeholder - service queries backend

    def is_blocked_by_knowledge(self) -> bool:
        """
        Check if task is blocked by missing knowledge.

        GRAPH-NATIVE (October 26, 2025): Service layer must query graph relationships.
        Use: backend.count_related(uid, "REQUIRES_KNOWLEDGE") > 0 and status==BLOCKED
        """
        # Query required: (task)-[:REQUIRES_KNOWLEDGE]->(ku)
        return self.is_blocked()  # Partial check - full check requires backend query

    def can_start(self, rels: TaskRelationships) -> bool:
        """
        Determine if this task can be started based on dependencies.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        A task can start if:
        1. It's not already completed or cancelled
        2. It has no incomplete prerequisite tasks
        3. It has no blocking knowledge requirements (if knowledge-gated)

        Args:
            rels: Graph relationship data containing prerequisite information

        Returns:
            True if task is ready to be started

        Example:
            rels = await TaskRelationships.fetch(task.uid, service.relationships)
            if task.can_start(rels):
                await service.update_status(task.uid, ActivityStatus.IN_PROGRESS)
        """
        # Cannot start if already terminal
        if self.is_completed() or self.is_cancelled():
            return False

        # Cannot start if has incomplete prerequisites
        if rels.prerequisite_task_uids:
            return False

        # Cannot start if explicitly blocked
        return not self.is_blocked()

    def learning_alignment_score(self) -> float:
        """
        Calculate how well-aligned this task is with learning goals.

        GRAPH-NATIVE (October 26, 2025): Partial score only.
        For complete score, service layer must query:
        - backend.count_related(uid, "APPLIES_KNOWLEDGE") > 0 for knowledge (25%)
        - backend.count_related(uid, "ALIGNED_WITH_PRINCIPLE") > 0 for principles (15%)

        Returns:
            Partial score from 0.0 to 0.6 (40% of total - needs graph queries for full score)
        """
        score = 0.0

        # Goal alignment (30%)
        if self.fulfills_goal_uid:
            score += 0.3

        # Knowledge application (25%) - REQUIRES GRAPH QUERY
        # Service must query: (task)-[:APPLIES_KNOWLEDGE]->(ku)
        # if backend.count_related(uid, "APPLIES_KNOWLEDGE") > 0:
        #     score += 0.25

        # Habit reinforcement (20%)
        if self.reinforces_habit_uid:
            score += 0.2

        # Principle alignment (15%) - REQUIRES GRAPH QUERY
        # Service must query: (task)-[:ALIGNED_WITH_PRINCIPLE]->(principle)
        # if backend.count_related(uid, "ALIGNED_WITH_PRINCIPLE") > 0:
        #     score += 0.15

        # Progress contribution (10%)
        score += min(self.goal_progress_contribution * 0.1, 0.1)

        return min(score, 1.0)  # Partial score - full score requires graph queries

    def impact_score(self) -> float:
        """
        Calculate the overall impact of completing this task.

        Combines urgency, learning alignment, and progress contribution.
        """
        urgency = self.urgency_score() / 10.0  # Normalize to 0-1
        learning = self.learning_alignment_score()
        progress = self.goal_progress_contribution

        # Weighted combination
        return urgency * 0.4 + learning * 0.4 + progress * 0.2

    # ==========================================================================
    # TAGS AND ORGANIZATION
    # ==========================================================================

    def has_tag(self, tag: str) -> bool:
        """Check if task has specific tag."""
        return tag.lower() in [t.lower() for t in self.tags]

    def has_project(self) -> bool:
        """Check if task is associated with a project."""
        return self.project is not None

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: TaskDTO) -> Task:
        """
        Create immutable Task from mutable DTO.

        GRAPH-NATIVE (October 26, 2025): UID list fields removed from Task model.
        Relationships are stored ONLY as Neo4j graph edges, not in domain model properties.

        DTOs still contain UID lists for API serialization (populated from graph queries).
        Those lists are NOT transferred to the Task model - they exist only in DTOs.
        """

        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            title=dto.title,
            description=dto.description,
            due_date=dto.due_date,
            scheduled_date=dto.scheduled_date,
            completion_date=dto.completion_date,
            duration_minutes=dto.duration_minutes,
            actual_minutes=dto.actual_minutes,
            status=dto.status,
            priority=dto.priority,
            project=dto.project,
            assignee=dto.assignee,
            tags=tuple(dto.tags),
            parent_uid=dto.parent_uid,
            # subtask_uids: REMOVED - stored as graph relationships only
            recurrence_pattern=dto.recurrence_pattern,
            recurrence_end_date=dto.recurrence_end_date,
            recurrence_parent_uid=dto.recurrence_parent_uid,
            fulfills_goal_uid=getattr(dto, "fulfills_goal_uid", None),
            reinforces_habit_uid=getattr(dto, "reinforces_habit_uid", None),
            # applies_knowledge_uids: REMOVED - stored as graph relationships only
            # aligned_principle_uids: REMOVED - stored as graph relationships only
            source_learning_step_uid=getattr(dto, "source_learning_step_uid", None),
            goal_progress_contribution=getattr(dto, "goal_progress_contribution", 0.0),
            knowledge_mastery_check=getattr(dto, "knowledge_mastery_check", False),
            habit_streak_maintainer=getattr(dto, "habit_streak_maintainer", False),
            # prerequisite_knowledge_uids: REMOVED - stored as graph relationships only
            # prerequisite_task_uids: REMOVED - stored as graph relationships only
            # enables_task_uids: REMOVED - stored as graph relationships only
            scheduled_event_uid=getattr(dto, "scheduled_event_uid", None),
            completion_updates_goal=getattr(dto, "completion_updates_goal", True),
            # completion_triggers_tasks: REMOVED - stored as graph relationships only
            # completion_unlocks_knowledge: REMOVED - stored as graph relationships only
            # Knowledge Intelligence (Enhanced - Phase 1 Week 2)
            # inferred_knowledge_uids: REMOVED - stored as graph relationships only
            knowledge_confidence_scores=getattr(dto, "knowledge_confidence_scores", {}) or {},
            knowledge_inference_metadata=getattr(dto, "knowledge_inference_metadata", {}) or {},
            learning_opportunities_count=getattr(dto, "learning_opportunities_count", 0),
            # knowledge_patterns_detected: REMOVED - computed from relationships
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            metadata=getattr(dto, "metadata", {})
            or {},  # Copy metadata from DTO (rich context storage)
        )

    def to_dto(self) -> TaskDTO:
        """
        Convert to mutable DTO.

        GRAPH-NATIVE (October 26, 2025): UID list fields set to empty lists.
        Service layer is responsible for populating relationship UIDs from graph queries.

        Example service-layer population:
            dto = task.to_dto()
            dto.applies_knowledge_uids = await backend.get_related_uids(
                task.uid,
                "APPLIES_KNOWLEDGE",
                direction="outgoing"
            ).value
        """
        from .task_dto import TaskDTO

        # NOTE: TaskDTO no longer has relationship fields (Phase 2 migration)
        # Task model still has them (Phase 3A temporary) but doesn't pass to DTO
        # Relationships queried dynamically via TasksRelationshipService
        return TaskDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            title=self.title,
            description=self.description,
            due_date=self.due_date,
            scheduled_date=self.scheduled_date,
            completion_date=self.completion_date,
            duration_minutes=self.duration_minutes,
            actual_minutes=self.actual_minutes,
            status=self.status,
            priority=self.priority,
            project=self.project,
            tags=list(self.tags),
            parent_uid=self.parent_uid,
            recurrence_pattern=self.recurrence_pattern,
            recurrence_end_date=self.recurrence_end_date,
            recurrence_parent_uid=self.recurrence_parent_uid,
            fulfills_goal_uid=self.fulfills_goal_uid,
            reinforces_habit_uid=self.reinforces_habit_uid,
            source_learning_step_uid=self.source_learning_step_uid,
            goal_progress_contribution=self.goal_progress_contribution,
            knowledge_mastery_check=self.knowledge_mastery_check,
            habit_streak_maintainer=self.habit_streak_maintainer,
            scheduled_event_uid=self.scheduled_event_uid,
            completion_updates_goal=self.completion_updates_goal,
            knowledge_confidence_scores=self.knowledge_confidence_scores.copy()
            if isinstance(self.knowledge_confidence_scores, dict)
            else {},
            knowledge_inference_metadata=self.knowledge_inference_metadata.copy()
            if isinstance(self.knowledge_inference_metadata, dict)
            else {},
            learning_opportunities_count=self.learning_opportunities_count,
            knowledge_patterns_detected=[],  # COMPUTED from relationships, not stored
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata,  # Copy metadata to DTO (rich context storage)
        )

    # ==========================================================================
    # UNIFIED KNOWLEDGE INTEGRATION METHODS (Phase 1 Week 2)
    # ==========================================================================

    def get_all_knowledge_connections(self, rels: TaskRelationships) -> list[dict]:
        """
        Get unified view of all knowledge connections (explicit + inferred).

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            List of knowledge connection dictionaries with type, confidence, source
        """
        connections = []

        # Explicit knowledge connections (high confidence)
        connections.extend(
            [
                {
                    "knowledge_uid": uid,
                    "connection_type": "applies",
                    "confidence": 0.95,
                    "source": "explicit",
                }
                for uid in rels.applies_knowledge_uids
            ]
        )

        connections.extend(
            [
                {
                    "knowledge_uid": uid,
                    "connection_type": "requires",
                    "confidence": 0.95,
                    "source": "explicit",
                }
                for uid in rels.prerequisite_knowledge_uids
            ]
        )

        # Inferred knowledge connections (variable confidence)
        for uid in rels.inferred_knowledge_uids:
            confidence = self.knowledge_confidence_scores.get(uid, 0.5)
            connections.append(
                {
                    "knowledge_uid": uid,
                    "connection_type": "applies",
                    "confidence": confidence,
                    "source": "inferred",
                }
            )

        return connections

    def get_knowledge_enhancement_summary(self, rels: TaskRelationships) -> dict:
        """
        Get comprehensive summary of knowledge enhancement data.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            Dictionary with all knowledge integration metrics
        """
        all_connections = self.get_all_knowledge_connections(rels)

        # Compute knowledge patterns from relationships
        patterns = []
        if rels.prerequisite_knowledge_uids and rels.applies_knowledge_uids:
            patterns.append("knowledge_bridge")
        if len(rels.applies_knowledge_uids) > 2:
            patterns.append("knowledge_integration")

        return {
            "explicit_knowledge_count": len(rels.applies_knowledge_uids)
            + len(rels.prerequisite_knowledge_uids),
            "inferred_knowledge_count": len(rels.inferred_knowledge_uids),
            "total_knowledge_connections": len(all_connections),
            "avg_confidence_score": self._calculate_average_confidence(all_connections),
            "learning_opportunities_count": self.learning_opportunities_count,
            "knowledge_patterns_detected": patterns,  # Computed from relationships
            "knowledge_complexity_score": self.calculate_knowledge_complexity(rels),
            "learning_impact_score": self.calculate_learning_impact(rels),
            "knowledge_bridge_status": self.is_knowledge_bridge(rels),
            "mastery_validation_task": self.validates_knowledge_mastery(),
            "knowledge_integration_level": self._determine_integration_level(rels),
        }

    def has_knowledge_enhancement(self, rels: TaskRelationships) -> bool:
        """
        Check if task has any knowledge enhancement (explicit or inferred).

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            True if task has any knowledge connections
        """
        return (
            len(rels.applies_knowledge_uids) > 0
            or len(rels.prerequisite_knowledge_uids) > 0
            or len(rels.inferred_knowledge_uids) > 0
            or self.learning_opportunities_count > 0
        )

    def get_combined_knowledge_uids(self, rels: TaskRelationships) -> list[str]:
        """
        Get all knowledge UIDs (explicit + inferred) as a unified list.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            List of all unique knowledge UIDs
        """
        all_uids = set()
        all_uids.update(rels.applies_knowledge_uids)
        all_uids.update(rels.prerequisite_knowledge_uids)
        all_uids.update(rels.inferred_knowledge_uids)
        return list(all_uids)

    def _calculate_average_confidence(self, connections: list[dict]) -> float:
        """Calculate average confidence score across all connections."""
        if not connections:
            return 0.0
        return sum(conn["confidence"] for conn in connections) / len(connections)

    def _determine_integration_level(self, rels: TaskRelationships) -> str:
        """
        Determine the level of knowledge integration.

        Args:
            rels: Task relationship data from graph

        Returns:
            Integration level (none/basic/moderate/advanced/expert)
        """
        total_connections = len(self.get_all_knowledge_connections(rels))

        if total_connections == 0:
            return "none"
        elif total_connections <= 2:
            return "basic"
        elif total_connections <= 4:
            return "moderate"
        elif total_connections <= 6:
            return "advanced"
        else:
            return "expert"

    def calculate_knowledge_complexity(self, rels: TaskRelationships) -> float:
        """
        Calculate knowledge complexity score based on connections and types.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            Complexity score (0.0-1.0)
        """
        total_connections = (
            len(rels.applies_knowledge_uids)
            + len(rels.prerequisite_knowledge_uids)
            + len(rels.inferred_knowledge_uids)
        )

        # Base score from number of connections
        complexity_score = total_connections * 0.2

        # Bonus for prerequisites (indicating foundational knowledge needed)
        complexity_score += len(rels.prerequisite_knowledge_uids) * 0.1

        # Bonus for confidence scores (higher confidence = more complex integration)
        if self.knowledge_confidence_scores:
            avg_confidence = sum(self.knowledge_confidence_scores.values()) / len(
                self.knowledge_confidence_scores
            )
            complexity_score += avg_confidence * 0.3

        # Bonus for pattern detection (computed from relationships)
        pattern_count = 0
        if rels.prerequisite_knowledge_uids and rels.applies_knowledge_uids:
            pattern_count += 1  # knowledge_bridge pattern
        if len(rels.applies_knowledge_uids) > 2:
            pattern_count += 1  # knowledge_integration pattern
        complexity_score += pattern_count * 0.1

        return round(min(complexity_score, 1.0), 2)  # Cap at 1.0

    def calculate_learning_impact(self, rels: TaskRelationships) -> float:
        """
        Calculate learning impact score.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            Impact score (0.0-1.0)
        """
        impact_score = 0.0

        # Base impact from knowledge application
        impact_score += len(rels.applies_knowledge_uids) * 0.15

        # Higher impact for bridging knowledge
        if rels.prerequisite_knowledge_uids and rels.applies_knowledge_uids:
            impact_score += 0.3  # Knowledge bridging bonus

        # Impact from learning opportunities
        impact_score += self.learning_opportunities_count * 0.1

        # Impact from goal contribution
        impact_score += self.goal_progress_contribution * 0.2

        # Mastery validation adds significant impact
        if self.knowledge_mastery_check:
            impact_score += 0.2

        return round(min(impact_score, 1.0), 2)  # Cap at 1.0

    def is_knowledge_bridge(self, rels: TaskRelationships) -> bool:
        """
        Check if task bridges existing knowledge to new knowledge.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            True if task requires prerequisites and applies knowledge
        """
        return len(rels.prerequisite_knowledge_uids) > 0 and len(rels.applies_knowledge_uids) > 0

    def validates_knowledge_mastery(self) -> bool:
        """Check if task validates knowledge mastery."""
        return self.knowledge_mastery_check

    # ==========================================================================
    # LEARNING STEP INTEGRATION (Task ↔ ls bridge)
    # ==========================================================================

    def fulfills_learning_step(self, step_uid: str) -> bool:
        """
        Check if task is linked to specific learning step.

        Args:
            step_uid: LearningStep UID to check

        Returns:
            True if task originated from or fulfills this learning step
        """
        return self.source_learning_step_uid == step_uid

    def is_from_learning_step(self) -> bool:
        """Check if task originated from a learning step."""
        return self.source_learning_step_uid is not None

    def get_learning_context(self, rels: TaskRelationships) -> dict:
        """
        Get complete learning step context for this task.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            Dictionary with all learning-related information
        """
        return {
            "source_learning_step": self.source_learning_step_uid,
            "knowledge_applied": list(rels.applies_knowledge_uids),
            "knowledge_prerequisites": list(rels.prerequisite_knowledge_uids),
            "knowledge_unlocked": list(rels.completion_unlocks_knowledge),
            "inferred_knowledge": list(rels.inferred_knowledge_uids),
            "mastery_check": self.knowledge_mastery_check,
            "learning_impact": self.calculate_learning_impact(rels),
            "is_knowledge_bridge": self.is_knowledge_bridge(rels),
            "total_knowledge_connections": len(self.get_combined_knowledge_uids(rels)),
        }

    def supports_knowledge_from_step(
        self, step_knowledge_uids: list[str], applies_knowledge_uids: list[str]
    ) -> bool:
        """
        Check if task applies knowledge from a learning step.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch applies_knowledge_uids via: service.relationships.get_task_knowledge(task.uid)

        Args:
            step_knowledge_uids: Knowledge UIDs from a LearningStep
            applies_knowledge_uids: Knowledge UIDs applied by this task (from graph)

        Returns:
            True if task applies any of the step's knowledge
        """
        task_knowledge = set(applies_knowledge_uids)
        step_knowledge = set(step_knowledge_uids)
        return bool(task_knowledge & step_knowledge)

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_dependency_query(self, depth: int = 2) -> str:
        """
        [P2] Build pure Cypher query for task dependencies.

        Pattern 2 (Graph-Native Queries): Multi-hop prerequisite traversal.

        Finds prerequisite tasks and prerequisite knowledge across multiple levels.
        Use this for deep dependency analysis (e.g., Askesis context, impact analysis).

        For direct prerequisite checks, use Pattern 1:
            if task.prerequisite_task_uids:  # Instant, no DB query

        Args:
            depth: Maximum dependency depth

        Returns:
            Pure Cypher query string

        Example:
            # Get full dependency tree (2 levels deep)
            query = task.build_dependency_query(GraphDepth.NEIGHBORHOOD)
            deps = await graph_service.execute_graph_query(query)
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def build_completion_impact_query(self) -> str:
        """
        [P2] Build pure Cypher query for completion impact.

        Pattern 2 (Graph-Native Queries): Cross-domain impact analysis.

        Finds goals updated, tasks triggered, and knowledge unlocked
        when this task completes. Traverses across multiple domains.

        For direct impact checks, use Pattern 1:
            if task.completion_updates_goal:  # Instant
            triggered = list(task.completion_triggers_tasks)  # Instant

        Returns:
            Pure Cypher query string

        Example:
            # Analyze what happens when task completes
            query = task.build_completion_impact_query()
            impact = await graph_service.execute_graph_query(query)
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_knowledge_context_query(self, depth: int = 2) -> str:
        """
        [P2] Build pure Cypher query for knowledge context.

        Pattern 2 (Graph-Native Queries): Semantic knowledge traversal.

        Finds all knowledge (explicit + inferred) related to this task,
        including hidden connections and relationship patterns.

        For direct knowledge access, use Pattern 1:
            knowledge_uids = list(task.applies_knowledge_uids)  # Instant

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string

        Example:
            # Get rich knowledge context (including inferred relationships)
            query = task.build_knowledge_context_query(GraphDepth.NEIGHBORHOOD)
            context = await graph_service.execute_graph_query(query)
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=depth
        )

    def build_practice_opportunities_query(self) -> str:
        """
        [P2] Build pure Cypher query for practice opportunities.

        Pattern 2 (Graph-Native Queries): Semantic practice discovery.

        Finds knowledge that can be practiced through this task,
        using semantic relationships (PRACTICES_VIA_HABIT, etc).

        For direct practice checks, use Pattern 1:
            if task.knowledge_mastery_check:  # Instant
            practice_count = len(task.applies_knowledge_uids)  # Instant

        Returns:
            Pure Cypher query string

        Example:
            # Find practice opportunities for knowledge mastery
            query = task.build_practice_opportunities_query()
            opportunities = await graph_service.execute_graph_query(query)
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=GraphDepth.DIRECT
        )

    def get_suggested_query_intent(self, rels: TaskRelationships) -> QueryIntent:
        """
        Get suggested QueryIntent based on task characteristics.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Business rules:
        - Tasks with prerequisites → PREREQUISITE (understand dependencies)
        - Tasks that unlock knowledge → HIERARCHICAL (see impact)
        - Tasks for knowledge mastery → PRACTICE (find related practice)
        - High-priority tasks → SPECIFIC (focused context)
        - Default → RELATIONSHIP (explore connections)

        Args:
            rels: Task relationship data from graph

        Returns:
            Recommended QueryIntent for this task
        """
        if len(rels.prerequisite_task_uids) > 0 or len(rels.prerequisite_knowledge_uids) > 0:
            return QueryIntent.PREREQUISITE

        if len(rels.completion_unlocks_knowledge) > 0 or self.completion_updates_goal:
            return QueryIntent.HIERARCHICAL

        if self.knowledge_mastery_check or len(rels.applies_knowledge_uids) > 0:
            return QueryIntent.PRACTICE

        # Use is_urgent() helper method which combines priority + time factors
        if self.is_urgent():
            return QueryIntent.SPECIFIC

        return QueryIntent.RELATIONSHIP

    # ==========================================================================
    # GRAPHENTITY PROTOCOL IMPLEMENTATION (Phase 2)
    # ==========================================================================

    def explain_existence(self, rels: TaskRelationships) -> str:
        """
        WHY does this task exist? One-sentence reasoning.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            str: Explanation of task's existence and purpose
        """
        parts = [self.title]

        # Add goal connection
        if self.fulfills_goal_uid:
            parts.append(f"Advances goal: {self.fulfills_goal_uid}")

        # Add habit connection
        if self.reinforces_habit_uid:
            parts.append(f"Reinforces habit: {self.reinforces_habit_uid}")

        # Add knowledge application
        if rels.applies_knowledge_uids:
            parts.append(f"Applies {len(rels.applies_knowledge_uids)} knowledge area(s)")

        # Add knowledge unlocking
        if rels.completion_unlocks_knowledge:
            parts.append(f"Unlocks {len(rels.completion_unlocks_knowledge)} new knowledge area(s)")

        # Add priority if high/urgent (using is_urgent() helper method)
        if self.is_urgent():
            parts.append(f"Priority: {self.priority.value}")

        return ". ".join(parts)

    def get_upstream_influences(self, rels: TaskRelationships) -> list[dict]:
        """
        WHAT shaped this task? Entities that influenced its creation.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            List of upstream entities (goals, habits, knowledge, parent tasks)
        """
        influences = []

        # 1. Goal this task advances
        if self.fulfills_goal_uid:
            influences.append(
                {
                    "uid": self.fulfills_goal_uid,
                    "entity_type": "goal",
                    "relationship_type": "created_for",
                    "reasoning": "Task created to advance goal progress",
                    "strength": None,
                }
            )

        # 2. Habit this task reinforces
        if self.reinforces_habit_uid:
            influences.append(
                {
                    "uid": self.reinforces_habit_uid,
                    "entity_type": "habit",
                    "relationship_type": "reinforces",
                    "reasoning": "Task completion reinforces habit",
                    "strength": None,
                }
            )

        # 3. Knowledge this task applies
        influences.extend(
            [
                {
                    "uid": knowledge_uid,
                    "entity_type": "knowledge",
                    "relationship_type": "applies",
                    "reasoning": "Task requires and applies this knowledge",
                    "strength": None,
                }
                for knowledge_uid in rels.applies_knowledge_uids
            ]
        )

        # 4. Required knowledge (from graph relationships)
        influences.extend(
            [
                {
                    "uid": knowledge_uid,
                    "entity_type": "knowledge",
                    "relationship_type": "requires",
                    "reasoning": "Prerequisite knowledge needed",
                    "strength": None,
                }
                for knowledge_uid in rels.prerequisite_knowledge_uids
            ]
        )

        # 5. Parent task (if subtask)
        if self.parent_uid:
            influences.append(
                {
                    "uid": self.parent_uid,
                    "entity_type": "task",
                    "relationship_type": "spawned_by",
                    "reasoning": "Subtask of parent task",
                    "strength": None,
                }
            )

        # 6. Prerequisite tasks
        influences.extend(
            [
                {
                    "uid": task_uid,
                    "entity_type": "task",
                    "relationship_type": "depends_on",
                    "reasoning": "Must complete prerequisite first",
                    "strength": None,
                }
                for task_uid in rels.prerequisite_task_uids
            ]
        )

        # Note: Future enhancement - add Choice derivation for tasks
        # Note: Future enhancement - add Principle guidances

        return influences

    def get_downstream_impacts(self, rels: TaskRelationships) -> list[dict]:
        """
        WHAT does this task shape? Entities influenced by this task.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            List of downstream entities (goals, knowledge, dependent tasks)
        """
        impacts = []

        # 1. Goal progress update
        if self.completion_updates_goal and self.fulfills_goal_uid:
            impacts.append(
                {
                    "uid": self.fulfills_goal_uid,
                    "entity_type": "goal",
                    "relationship_type": "advances",
                    "reasoning": "Completion advances goal progress",
                    "strength": self.goal_progress_contribution,
                }
            )

        # 2. Knowledge unlocking
        impacts.extend(
            [
                {
                    "uid": knowledge_uid,
                    "entity_type": "knowledge",
                    "relationship_type": "unlocks",
                    "reasoning": "Completion unlocks new knowledge",
                    "strength": None,
                }
                for knowledge_uid in rels.completion_unlocks_knowledge
            ]
        )

        # 3. Subtasks
        impacts.extend(
            [
                {
                    "uid": subtask_uid,
                    "entity_type": "task",
                    "relationship_type": "spawns",
                    "reasoning": "Subtask created from this task",
                    "strength": None,
                }
                for subtask_uid in rels.subtask_uids
            ]
        )

        # 4. Dependent tasks (tasks that depend on this)
        # Note: This would require reverse lookup in the graph
        # Future enhancement: Track dependent_task_uids

        return impacts

    def get_relationship_summary(self, rels: TaskRelationships) -> dict:
        """
        Get comprehensive relationship context for this task.

        GRAPH-NATIVE: Relationship data passed as parameter.
        Fetch via: TaskRelationships.fetch(task.uid, service.relationships)

        Args:
            rels: Task relationship data from graph

        Returns:
            Dict with explanation, upstream influences, and downstream impacts
        """
        return {
            "explanation": self.explain_existence(rels),
            "upstream": self.get_upstream_influences(rels),
            "downstream": self.get_downstream_impacts(rels),
            "upstream_count": len(self.get_upstream_influences(rels)),
            "downstream_count": len(self.get_downstream_impacts(rels)),
        }

    def __str__(self) -> str:
        """String representation."""
        return f"Task(uid={self.uid}, title='{self.title}', status={self.status.value})"
