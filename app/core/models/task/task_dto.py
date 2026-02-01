"""
Task DTO (Tier 2 - Transfer)
============================

Mutable data transfer object for task data movement between layers.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, ClassVar

from core.models.activity_dto_mixin import ActivityDTOMixin
from core.models.shared_enums import ActivityStatus, Priority, RecurrencePattern


@dataclass
class TaskDTO(ActivityDTOMixin):
    """
    Mutable data transfer object for tasks - PROPERTIES ONLY.

    ⚠️  WARNING: Relationship List Fields Do NOT Exist!
    ==================================================

    ❌ These fields were REMOVED and will cause AttributeError:
        - subtask_uids
        - applies_knowledge_uids
        - prerequisite_knowledge_uids
        - prerequisite_task_uids
        - enables_task_uids
        - aligned_principle_uids

    ✅ To access relationships, use TaskRelationships.fetch():
        ```python
        from core.models.task.task_relationships import TaskRelationships

        # Fetch all relationships in one call
        rels = await TaskRelationships.fetch(task.uid, tasks_service.relationships)

        # Access relationship data
        knowledge_uids = rels.applies_knowledge_uids
        subtask_uids = rels.subtask_uids
        ```

    Single UID Fields (Still Available):
    ------------------------------------
    ✅ fulfills_goal_uid: str | None
    ✅ reinforces_habit_uid: str | None
    ✅ parent_uid: str | None
    ✅ source_learning_step_uid: str | None

    Purpose:
    --------
    - Moving data between service and repository
    - Database operations
    - Inter-service communication

    Graph-Native Design (Phase 2 Migration - Oct 28, 2025):
    -------------------------------------------------------
    - Relationship LISTS removed → stored as Neo4j edges
    - Single UIDs kept → stored as node properties
    - Query relationships via: TaskRelationships.fetch()

    📖 Documentation:
    - Task-specific: /core/models/task/task_relationships.py
    - Domain pattern: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
    """

    # Class variable for UID generation (ActivityDTOMixin)
    _uid_prefix: ClassVar[str] = "task"

    # Identity
    uid: str
    user_uid: str  # REQUIRED - task ownership
    title: str
    description: str | None = None

    # Scheduling
    due_date: date | None = None
    scheduled_date: date | None = None
    completion_date: date | None = None

    # Time tracking
    duration_minutes: int = 30
    actual_minutes: int | None = None

    # Status and priority
    status: ActivityStatus = ActivityStatus.DRAFT
    priority: Priority = Priority.MEDIUM

    # Organization
    project: str | None = None
    assignee: str | None = None
    tags: list[str] = field(default_factory=list)

    # Hierarchy - Single parent UID is a property
    parent_uid: str | None = None

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None  # Original recurring task

    # Learning Integration - Single UIDs are properties
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None
    source_learning_step_uid: str | None = None  # ls: UID if task comes from learning step

    # Progress Impact (NEW)
    goal_progress_contribution: float = 0.0  # 0-1
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False

    # Scheduling (enhanced)
    scheduled_event_uid: str | None = None  # Link to Event

    # Completion
    completion_updates_goal: bool = True

    # Enhanced Knowledge Tracking - NON-UID metadata only
    # Transient field for inference processing (not persisted to graph as property)
    # After inference, create graph relationships via service.relationships.add_task_knowledge()
    inferred_knowledge_uids: list[str] = field(default_factory=list)
    knowledge_confidence_scores: dict[str, float] = field(default_factory=dict)
    knowledge_inference_metadata: dict[str, Any] = field(default_factory=dict)
    learning_opportunities_count: int = 0
    knowledge_patterns_detected: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Additional data
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        user_uid: str,
        title: str,
        priority: Priority = Priority.MEDIUM,
        due_date: date | None = None,
        duration_minutes: int = 30,
        project: str | None = None,
        tags: list[str] | None = None,
    ) -> "TaskDTO":
        """
        Factory method to create new TaskDTO with generated UID.

        Args:
            user_uid: User UID (REQUIRED - fail-fast philosophy),
            title: Task title,
            priority: Task priority,
            due_date: Due date,
            duration_minutes: Estimated duration,
            project: Project name,
            tags: List of tags

        Returns:
            TaskDTO with generated UID
        """
        return cls._create_activity_dto(
            user_uid=user_uid,
            title=title,
            priority=priority,
            due_date=due_date,
            duration_minutes=duration_minutes,
            project=project,
            tags=tags or [],
            status=ActivityStatus.DRAFT,
        )

    def update_from(self, updates: dict) -> None:
        """Update fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(self, updates)

    def complete(self, actual_minutes: int | None = None) -> None:
        """Mark task as completed."""
        self.status = ActivityStatus.COMPLETED
        self.completion_date = date.today()
        if actual_minutes:
            self.actual_minutes = actual_minutes
        self.updated_at = datetime.now()

    def cancel(self) -> None:
        """Mark task as cancelled."""
        self.status = ActivityStatus.CANCELLED
        self.updated_at = datetime.now()

    def copy(self) -> "TaskDTO":
        """Create a copy of this TaskDTO (properties only - relationships not copied)."""
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
            assignee=self.assignee,
            tags=self.tags.copy(),
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
            knowledge_confidence_scores=self.knowledge_confidence_scores.copy(),
            knowledge_inference_metadata=self.knowledge_inference_metadata.copy(),
            learning_opportunities_count=self.learning_opportunities_count,
            knowledge_patterns_detected=self.knowledge_patterns_detected.copy(),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata.copy(),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for database operations."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["status", "priority", "recurrence_pattern"],
            date_fields=["due_date", "scheduled_date", "completion_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "TaskDTO":
        """
        Create DTO from dictionary.

        Infrastructure fields (e.g., 'embedding', 'embedding_version') are
        automatically filtered out by dto_from_dict. Embeddings are search
        infrastructure stored in Neo4j for vector search, not domain data.

        See: /docs/patterns/three_tier_type_system.md
        """
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "status": ActivityStatus,
                "priority": Priority,
                "recurrence_pattern": RecurrencePattern,
            },
            date_fields=["due_date", "scheduled_date", "completion_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags", "knowledge_patterns_detected", "inferred_knowledge_uids"],
            dict_fields=["knowledge_confidence_scores", "knowledge_inference_metadata", "metadata"],
        )
