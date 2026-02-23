"""
TaskDTO - Task-Specific DTO (Tier 2 - Transfer)
=================================================

Extends UserOwnedDTO with 25 task-specific fields matching the Task
frozen dataclass (Tier 3): scheduling, hierarchy, cross-domain links,
progress impact, and knowledge intelligence.

This is the first per-domain DTO, proving the pattern for Phase 3
of the domain-first architecture migration.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── TaskDTO(UserOwnedDTO) +25 task-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.ku.user_owned_dto import UserOwnedDTO


@dataclass
class TaskDTO(UserOwnedDTO):
    """
    Mutable DTO for tasks (EntityType.TASK).

    Extends UserOwnedDTO with 25 task-specific fields:
    - Scheduling (9): due_date, scheduled_date, completion_date, duration, recurrence
    - Hierarchy (3): parent_uid, project, assignee
    - Cross-domain links (4): goal, habit, learning step/path references
    - Progress impact (6): goal contribution, knowledge mastery, habit streak
    - Knowledge intelligence (3): confidence scores, inference metadata, opportunities
    """

    # =========================================================================
    # SCHEDULING
    # =========================================================================
    due_date: date | None = None
    scheduled_date: date | None = None
    completion_date: date | None = None
    duration_minutes: int | None = None
    actual_minutes: int | None = None

    # Recurrence
    recurrence_pattern: str | None = None
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
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None
    source_learning_step_uid: str | None = None
    source_learning_path_uid: str | None = None

    # =========================================================================
    # PROGRESS IMPACT
    # =========================================================================
    goal_progress_contribution: float = 0.0
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False
    completion_updates_goal: bool = False
    curriculum_driven: bool = False
    curriculum_practice_type: str | None = None

    # =========================================================================
    # KNOWLEDGE INTELLIGENCE
    # =========================================================================
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_task(cls, user_uid: str, title: str, **kwargs: Any) -> TaskDTO:
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
            ku_type=EntityType.TASK,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including task-specific fields."""
        from core.models.dto_helpers import convert_dates_to_iso

        data = super().to_dict()

        # Task-specific fields
        data.update(
            {
                # Scheduling
                "due_date": self.due_date,
                "scheduled_date": self.scheduled_date,
                "completion_date": self.completion_date,
                "duration_minutes": self.duration_minutes,
                "actual_minutes": self.actual_minutes,
                "recurrence_pattern": self.recurrence_pattern,
                "recurrence_end_date": self.recurrence_end_date,
                "recurrence_parent_uid": self.recurrence_parent_uid,
                "scheduled_event_uid": self.scheduled_event_uid,
                # Hierarchy
                "parent_uid": self.parent_uid,
                "project": self.project,
                "assignee": self.assignee,
                # Cross-domain links
                "fulfills_goal_uid": self.fulfills_goal_uid,
                "reinforces_habit_uid": self.reinforces_habit_uid,
                "source_learning_step_uid": self.source_learning_step_uid,
                "source_learning_path_uid": self.source_learning_path_uid,
                # Progress impact
                "goal_progress_contribution": self.goal_progress_contribution,
                "knowledge_mastery_check": self.knowledge_mastery_check,
                "habit_streak_maintainer": self.habit_streak_maintainer,
                "completion_updates_goal": self.completion_updates_goal,
                "curriculum_driven": self.curriculum_driven,
                "curriculum_practice_type": self.curriculum_practice_type,
                # Knowledge intelligence
                "knowledge_confidence_scores": dict(self.knowledge_confidence_scores)
                if self.knowledge_confidence_scores
                else None,
                "knowledge_inference_metadata": dict(self.knowledge_inference_metadata)
                if self.knowledge_inference_metadata
                else None,
                "learning_opportunities_count": self.learning_opportunities_count,
            }
        )

        convert_dates_to_iso(
            data,
            [
                "due_date",
                "scheduled_date",
                "completion_date",
                "recurrence_end_date",
            ],
        )

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskDTO:
        """Create TaskDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
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
            deprecated_fields=[
                "prerequisites",
                "enables",
                "related_to",
                "name",
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
                "reinforces_habit_uid",
                "source_learning_step_uid",
                "source_learning_path_uid",
                "goal_progress_contribution",
                "knowledge_mastery_check",
                "habit_streak_maintainer",
                "completion_updates_goal",
                "curriculum_driven",
                "curriculum_practice_type",
                "knowledge_confidence_scores",
                "knowledge_inference_metadata",
                "learning_opportunities_count",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, TaskDTO):
            return False
        return self.uid == other.uid
