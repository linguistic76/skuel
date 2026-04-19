"""
Task - Task Domain Model
============================

Frozen dataclass for task entities (EntityType.TASK).

Inherits common fields from UserOwnedEntity. Adds 25 task-specific fields:
- Scheduling (9): due_date, scheduled_date, completion_date, duration, recurrence
- Hierarchy (3): parent_uid, project, assignee
- Cross-domain links (4): goal, habit, path step/path references
- Progress impact (6): goal contribution, knowledge mastery, habit streak
- Knowledge intelligence (3): confidence scores, inference metadata, opportunities

Task-specific methods: impact_score, learning_alignment_score, is_overdue,
days_remaining, get_summary, category, parent_goal_uid.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.task.task_dto import TaskDTO

from core.models.enums.entity_enums import EntityType
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class Task(UserOwnedEntity):
    """
    Immutable domain model for tasks (EntityType.TASK).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 25 task-specific fields for scheduling, hierarchy, cross-domain
    links, progress impact, and knowledge intelligence.
    """

    def __post_init__(self) -> None:
        """Force entity_type=TASK, then delegate to UserOwnedEntity for defaults."""
        if self.entity_type != EntityType.TASK:
            object.__setattr__(self, "entity_type", EntityType.TASK)
        super().__post_init__()
        # Enforce deep immutability: wrap mutable dicts in read-only proxies
        if isinstance(self.knowledge_confidence_scores, dict):
            object.__setattr__(
                self,
                "knowledge_confidence_scores",
                MappingProxyType(self.knowledge_confidence_scores),
            )
        if isinstance(self.knowledge_inference_metadata, dict):
            object.__setattr__(
                self,
                "knowledge_inference_metadata",
                MappingProxyType(self.knowledge_inference_metadata),
            )

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    due_date: date | None = None  # Task deadline
    scheduled_date: date | None = None  # Planned date
    completion_date: date | None = None  # Actual completion
    duration_minutes: int | None = None  # Expected duration
    actual_minutes: int | None = None  # Actual time spent

    # Recurrence
    recurrence_pattern: str | None = None  # RecurrencePattern enum value
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None

    # Event link
    scheduled_event_uid: str | None = None  # Linked event

    # =========================================================================
    # HIERARCHY
    # =========================================================================
    parent_uid: str | None = None  # Parent task (not derivation chain)
    project: str | None = None  # Project grouping
    assignee: str | None = None  # Task assignee

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    fulfills_goal_uid: str | None = None  # TASK -> GOAL
    reinforces_habit_uid: str | None = None  # TASK -> HABIT
    source_path_step_uid: str | None = None  # TASK -> PS
    source_learning_path_uid: str | None = None  # TASK -> LP

    # =========================================================================
    # PROGRESS IMPACT
    # =========================================================================
    goal_progress_contribution: float = 0.0  # Contribution to GOAL (0.0-1.0)
    knowledge_mastery_check: bool = False  # Verify knowledge mastery on completion
    habit_streak_maintainer: bool = False  # Maintains habit streak
    completion_updates_goal: bool = False  # Completion updates GOAL progress
    curriculum_driven: bool = False  # Derived from curriculum
    curriculum_practice_type: str | None = None  # Curriculum connection type

    # =========================================================================
    # KNOWLEDGE INTELLIGENCE
    # =========================================================================
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    # =========================================================================
    # TASK-SPECIFIC METHODS
    # =========================================================================

    def impact_score(self) -> float:
        """Calculate task impact score based on priority and knowledge connections."""
        from contextlib import suppress

        from core.models.enums.activity_enums import Priority

        base = 0.5
        if self.priority:
            with suppress(ValueError, KeyError):
                base = Priority(self.priority).to_numeric() / 4.0
        if self.fulfills_goal_uid:
            base = min(1.0, base + 0.2)
        return base

    def learning_alignment_score(self) -> float:
        """Score for how well a task aligns with learning paths."""
        score = 0.0
        if self.source_path_step_uid:
            score += 0.5
        if self.source_learning_path_uid:
            score += 0.3
        if self.knowledge_mastery_check:
            score += 0.2
        return min(1.0, score)

    def is_overdue(self) -> bool:
        """Check if past due_date without completion."""
        if self.is_completed:
            return False
        if not self.due_date:
            return False
        return self.due_date < date.today()

    def get_days_remaining(self) -> int | None:
        """Days until due_date, or None if no deadline."""
        if not self.due_date:
            return None
        delta = self.due_date - date.today()
        return delta.days

    def days_remaining(self) -> int:
        """Days until due_date (0 if none set or past)."""
        result = self.get_days_remaining()
        return max(0, result) if result is not None else 0

    def is_past(self) -> bool:
        """Check if task deadline is in the past."""
        if self.due_date:
            return self.due_date < date.today()
        return False

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the task."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this task exists."""
        return self.description or self.summary or f"task: {self.title}"

    def validates_knowledge_mastery(self) -> bool:
        """Check if this task validates knowledge mastery."""
        return self.knowledge_mastery_check

    def get_combined_knowledge_uids(self) -> set[str]:
        """Get all knowledge UIDs related to this task (empty — knowledge UIDs are graph-native)."""
        return set()

    def get_all_knowledge_uids(self) -> set[str]:
        """Alias for get_combined_knowledge_uids."""
        return self.get_combined_knowledge_uids()

    def calculate_knowledge_complexity(self) -> float:
        """Calculate knowledge complexity (0.0-1.0).

        Derived from knowledge_confidence_scores (breadth x gap) and
        learning_opportunities_count. Returns 0.0 for bare tasks with no
        knowledge intelligence data.
        """
        score = 0.0
        if self.knowledge_confidence_scores:
            count = len(self.knowledge_confidence_scores)
            avg_confidence = sum(self.knowledge_confidence_scores.values()) / count
            score += min(0.5, count / 10.0)  # breadth: up to 0.5 for 10+ concepts
            score += (1.0 - avg_confidence) * 0.3  # gap: low confidence = harder
        if self.learning_opportunities_count > 0:
            score += min(0.2, self.learning_opportunities_count / 5.0)
        return min(1.0, score)

    def is_knowledge_bridge(self) -> bool:
        """Check if this entity bridges multiple knowledge domains.

        Tasks bridge domains via graph relationships, not semantic_links
        (which are a Curriculum concept). Always False for tasks.
        """
        return False

    def calculate_learning_impact(self) -> float:
        """Calculate learning impact score (0.0-1.0).

        Derived from curriculum linkage fields already present on the Task:
        path step / learning path references, mastery check flag, curriculum
        origin, and breadth of knowledge confidence scores.
        """
        score = 0.0
        if self.source_path_step_uid:
            score += 0.30
        if self.source_learning_path_uid:
            score += 0.20
        if self.knowledge_mastery_check:
            score += 0.20
        if self.curriculum_driven:
            score += 0.15
        if self.knowledge_confidence_scores:
            score += min(0.15, len(self.knowledge_confidence_scores) * 0.03)
        return min(1.0, score)

    @property
    def category(self) -> str | None:
        """Task category — uses domain field."""
        return self.domain.value if self.domain else None

    @property
    def parent_goal_uid(self) -> str | None:
        """Alias for fulfills_goal_uid."""
        return self.fulfills_goal_uid

    @property
    def is_from_path_step(self) -> bool:
        """Check if this task originated from a path step."""
        return self.source_path_step_uid is not None

    @property
    def fulfills_path_step(self) -> bool:
        """Check if this task fulfills a path step."""
        return self.source_path_step_uid is not None

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | TaskDTO") -> "Task":
        """Create Task from an EntityDTO or TaskDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "TaskDTO":  # type: ignore[override]
        """Convert Task to domain-specific TaskDTO."""

        from core.models.task.task_dto import TaskDTO

        from core.models.dto_helpers import domain_to_dto
        return domain_to_dto(self, TaskDTO)

    def __str__(self) -> str:
        return f"Task(uid={self.uid}, title='{self.title}', due={self.due_date})"

    def __repr__(self) -> str:
        return (
            f"Task(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, priority={self.priority}, "
            f"due_date={self.due_date}, user_uid={self.user_uid})"
        )
