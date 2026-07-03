"""
TaskDTO - Task-Specific DTO (Tier 2 - Transfer)
=================================================

Extends UserOwnedDTO with task-specific fields matching the Task
frozen dataclass (Tier 3): scheduling, hierarchy, cross-domain links,
progress impact, and knowledge intelligence.

This is the first per-domain DTO, proving the pattern for
of the domain-first architecture migration.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── TaskDTO(UserOwnedDTO) +task-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from datetime import date

from core.models.enums import Domain
from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class TaskDTO(UserOwnedDTO):
    """
    Mutable DTO for tasks (EntityType.TASK).

    Extends UserOwnedDTO with task-specific fields:
    - Scheduling (9): due_date, scheduled_date, completion_date, duration, recurrence
    - Hierarchy (3): parent_uid, project, assignee
    - Cross-domain links (3): goal, habit, path step references
    - Progress impact (5): goal contribution, knowledge mastery, habit streak
    - Knowledge intelligence (3): confidence scores, inference metadata, opportunities
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.TASK, kw_only=True)

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    due_date: date | None = None
    scheduled_date: date | None = None
    completion_date: date | None = None
    duration_minutes: int | None = None
    actual_minutes: int | None = None

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None
    recurrence_parent_uid: str | None = None

    # Event link
    scheduled_event_uid: str | None = None

    # =========================================================================
    # HIERARCHY
    # =========================================================================
    parent_uid: str | None = None
    project: str | None = None
    assignee: str | None = None

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    # Task↔Habit linkage is the (Task)-[:REINFORCES_HABIT]->(Habit) graph edge,
    # not a persisted property — so it is intentionally absent from this DTO.
    fulfills_goal_uid: str | None = None
    source_path_step_uid: str | None = None

    # =========================================================================
    # PROGRESS IMPACT
    # =========================================================================
    goal_progress_contribution: float = 0.0
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False
    completion_updates_goal: bool = False
    curriculum_practice_type: str | None = None

    # =========================================================================
    # KNOWLEDGE INTELLIGENCE
    # =========================================================================
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is the (Task)-[:SPAWNED_FROM]->(TaskTemplate) edge.
    engagement_state: EngagementState | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_task(cls, user_uid: UserUID, title: str, **kwargs: Any) -> TaskDTO:
        """Create a TaskDTO with generated UID and correct defaults.

        Requires user_uid. Status defaults to DRAFT.
        """
        from core.utils.uid_generator import UIDGenerator

        uid = kwargs.pop("uid", None)
        if not uid:
            if title:
                uid = UIDGenerator.generate_uid("task", title)
            else:
                uid = UIDGenerator.generate_random_uid("task")

        kwargs.setdefault("status", EntityStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PRIVATE)

        return cls(
            uid=uid,
            title=title,
            entity_type=EntityType.TASK,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "entity_type",
                "status",
                "domain",
                "visibility",
                "recurrence_pattern",
            ],
            date_fields=["due_date", "scheduled_date", "completion_date", "recurrence_end_date"],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskDTO:
        """Create TaskDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "recurrence_pattern": RecurrencePattern,
                "engagement_state": EngagementState,
            },
            date_fields=[
                "due_date",
                "scheduled_date",
                "completion_date",
                "recurrence_end_date",
            ],
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags"],
            dict_fields=[
                "metadata",
                "knowledge_confidence_scores",
                "knowledge_inference_metadata",
            ],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # EntityDTO fields
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # UserOwnedDTO fields
                "priority",
                "visibility",
                # Task-specific fields
                "due_date",
                "scheduled_date",
                "completion_date",
                "duration_minutes",
                "actual_minutes",
                "recurrence_pattern",
                "recurrence_end_date",
                "recurrence_parent_uid",
                "scheduled_event_uid",
                "parent_uid",
                "project",
                "assignee",
                "fulfills_goal_uid",
                "source_path_step_uid",
                "goal_progress_contribution",
                "knowledge_mastery_check",
                "habit_streak_maintainer",
                "completion_updates_goal",
                "curriculum_practice_type",
                "knowledge_confidence_scores",
                "knowledge_inference_metadata",
                "learning_opportunities_count",
                "engagement_state",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "engagement_state": EngagementState,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, TaskDTO):
            return False
        return self.uid == other.uid
