"""
Task - Task Domain Model
============================

Frozen dataclass for task entities (EntityType.TASK).

Inherits common fields from UserOwnedEntity. Adds task-specific fields:
- Scheduling (9): due_date, scheduled_date, completion_date, duration, recurrence
- Hierarchy (3): parent_uid, project, assignee
- Cross-domain links (3): goal, habit, path step references
- Progress impact (5): goal contribution, knowledge mastery, habit streak
- Knowledge intelligence (3): confidence scores, inference metadata, opportunities

Task-specific methods: learning_alignment_score, is_overdue,
days_remaining, get_summary, category, parent_goal_uid.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.task.task_dto import TaskDTO
    from core.models.task.task_request import TaskCreateRequest
    from core.models.type_hints import UserUID

from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityType
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class Task(UserOwnedEntity):
    """
    Immutable domain model for tasks (EntityType.TASK).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds task-specific fields for scheduling, hierarchy, cross-domain
    links, progress impact, and knowledge intelligence.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.TASK, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=TASK, then delegate to UserOwnedEntity for defaults."""
        if self.entity_type != EntityType.TASK:
            raise ValueError(
                f"Task constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
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
    recurrence_pattern: RecurrencePattern | None = None
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
    source_path_step_uid: str | None = None  # TASK -> PS
    # EDGE-BACKED, never a node property. The Task↔Habit link is the graph edge
    # (Task)-[:REINFORCES_HABIT]->(Habit), which is the single source of truth; the
    # mapper's RELATIONSHIP_SKIP_FIELDS keeps this field out of the node. On READ it is
    # derived — populated at fetch time (e.g. by the prioritization path) from the edge
    # so pure scorers can see it. On CREATE it is the edge's INPUT: both doors carry it
    # on the entity and TasksCoreService writes the edge from it.
    #
    # The DTO's silence is why this needed the skip-set. The old note here said the field
    # "is absent from TaskDTO so it is never written to Neo4j" — true of the DTO, false of
    # the entity door, which persists the ENTITY (#966). Absence from one serializer is not
    # a persistence guarantee.
    reinforces_habit_uid: str | None = None  # EDGE-BACKED — see note above

    # =========================================================================
    # PROGRESS IMPACT
    # =========================================================================
    goal_progress_contribution: float = 0.0  # Contribution to GOAL (0.0-1.0)
    knowledge_mastery_check: bool = False  # Verify knowledge mastery on completion
    habit_streak_maintainer: bool = False  # Maintains habit streak
    completion_updates_goal: bool = False  # Completion updates GOAL progress
    curriculum_practice_type: str | None = None  # Curriculum connection type

    # =========================================================================
    # KNOWLEDGE INTELLIGENCE
    # =========================================================================
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference to the spawning template lives in the graph as
    # (Task)-[:SPAWNED_FROM]->(TaskTemplate); no property on this node.
    engagement_state: EngagementState | None = None  # None = standalone instance

    # =========================================================================
    # TASK-SPECIFIC METHODS
    # =========================================================================

    def learning_alignment_score(self) -> float:
        """Score for how well a task aligns with learning paths.

        PS link is sufficient signal — LP is reachable via PS via
        (PS)-[:IS_STEP_OF]->(LP), so a separate LP weight is redundant.
        """
        score = 0.0
        if self.source_path_step_uid:
            score += 0.7
        if self.knowledge_mastery_check:
            score += 0.3
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

        Derived from curriculum linkage fields on the Task: path step
        reference, mastery check flag, template origin (curriculum-spawned),
        and breadth of knowledge confidence scores.
        """
        score = 0.0
        if self.source_path_step_uid:
            score += 0.40
        if self.knowledge_mastery_check:
            score += 0.20
        if self.engagement_state is not None:
            score += 0.20
        if self.knowledge_confidence_scores:
            score += min(0.20, len(self.knowledge_confidence_scores) * 0.04)
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

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | TaskDTO") -> "Task":
        """Create Task from an EntityDTO or TaskDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "TaskDTO":
        """Convert Task to domain-specific TaskDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.task.task_dto import TaskDTO

        return domain_to_dto(self, TaskDTO)

    @classmethod
    def from_request(cls, request: "TaskCreateRequest", *, user_uid: "UserUID") -> "Task":
        """Construct a frozen Task from a validated TaskCreateRequest.

        Relationship-typed request fields are written as graph edges by the service
        layer after construction, never as node properties. Two of them nonetheless
        ride on the Task — ``parent_uid`` and ``reinforces_habit_uid`` — because the
        ENTITY door (``service.create(entity)``, where the generated CRUD route entered
        before it was bound to ``create_task``) has no request, so a link the entity
        cannot carry is a link that door can never write. The mapper's
        RELATIONSHIP_SKIP_FIELDS keeps both out of the node; ``TasksCoreService.create``
        turns them into HAS_SUBTASK and REINFORCES_HABIT. The list-typed fields
        (``applies_knowledge_uids``, ``prerequisite_knowledge_uids``) reach no Task field
        and stay request-only.

        The result is handed to the backend as the ENTITY, not as
        ``self.to_dto().to_dict()``: ``create_task`` now persists through the shared
        ``TasksCoreService.create`` primitive so the entity door and the request door
        cannot diverge on events. This factory exists so the create path
        stays frozen-domain end-to-end up to the persistence boundary — inference
        enrichment is applied via ``dataclasses.replace`` on the result, not via DTO
        mutation.
        """
        from core.models.type_hints import EntityUID
        from core.utils.uid_generator import UIDGenerator

        return cls(
            uid=EntityUID(UIDGenerator.generate_random_uid("task")),
            entity_type=EntityType.TASK,
            user_uid=user_uid,
            title=request.title,
            description=request.description,
            priority=request.priority,
            status=request.status,
            due_date=request.due_date,
            scheduled_date=request.scheduled_date,
            completion_date=request.completion_date,
            duration_minutes=request.duration_minutes,
            project=request.project,
            assignee=request.assignee,
            tags=tuple(request.tags),
            parent_uid=request.parent_uid,
            recurrence_pattern=request.recurrence_pattern,
            recurrence_end_date=request.recurrence_end_date,
            fulfills_goal_uid=request.fulfills_goal_uid,
            reinforces_habit_uid=request.reinforces_habit_uid,
            goal_progress_contribution=request.goal_progress_contribution,
            knowledge_mastery_check=request.knowledge_mastery_check,
            habit_streak_maintainer=request.habit_streak_maintainer,
        )

    def __str__(self) -> str:
        return f"Task(uid={self.uid}, title='{self.title}', due={self.due_date})"

    def __repr__(self) -> str:
        return (
            f"Task(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, priority={self.priority}, "
            f"due_date={self.due_date}, user_uid={self.user_uid})"
        )


def get_task_urgency(task: Any) -> tuple[Any, Any]:
    """
    Sort key: (priority value, due date) for ordering tasks by urgency.

    Task-domain sorting policy (Dynamic Enum Pattern — the policy lives with
    its domain, not in a generic utils grab-bag). None due_dates sort last.

    Example:
        critical_tasks.sort(key=get_task_urgency)
    """
    from core.ports.base_protocols import HasPriority

    priority_value = getattr(task.priority, "value", 0) if isinstance(task, HasPriority) else 0
    due_date = getattr(task, "due_date", None) or date.max
    return (priority_value, due_date)
