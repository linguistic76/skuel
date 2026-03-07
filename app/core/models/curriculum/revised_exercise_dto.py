"""
RevisedExerciseDTO - Revised Exercise-Specific DTO (Tier 2 - Transfer)
========================================================================

Extends UserOwnedDTO with 9 revised-exercise-specific fields matching the
RevisedExercise frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── RevisedExerciseDTO(UserOwnedDTO) +9 fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class RevisedExerciseDTO(UserOwnedDTO):
    """
    Mutable DTO for revised exercises (EntityType.REVISED_EXERCISE).

    Extends UserOwnedDTO with 9 revised-exercise-specific fields:
    - revision_number: Which revision iteration
    - original_exercise_uid: UID of the original Exercise
    - feedback_uid: UID of the SubmissionFeedback this addresses
    - student_uid: Target student
    - instructions: Revision instructions
    - model: Which LLM to use
    - context_notes: Reference materials
    - feedback_points_addressed: Specific feedback points targeted
    - revision_rationale: Why this revision was created
    """

    # =========================================================================
    # REVISED EXERCISE-SPECIFIC FIELDS
    # =========================================================================
    revision_number: int = 1
    original_exercise_uid: str | None = None
    feedback_uid: str | None = None
    student_uid: str | None = None
    instructions: str | None = None
    model: str = "claude-sonnet-4-6"
    context_notes: list[str] = field(default_factory=list)
    feedback_points_addressed: list[str] = field(default_factory=list)
    revision_rationale: str | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including revised-exercise-specific fields."""
        data = super().to_dict()
        data.update(
            {
                "revision_number": self.revision_number,
                "original_exercise_uid": self.original_exercise_uid,
                "feedback_uid": self.feedback_uid,
                "student_uid": self.student_uid,
                "instructions": self.instructions,
                "model": self.model,
                "context_notes": list(self.context_notes) if self.context_notes else [],
                "feedback_points_addressed": (
                    list(self.feedback_points_addressed)
                    if self.feedback_points_addressed
                    else []
                ),
                "revision_rationale": self.revision_rationale,
            }
        )
        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RevisedExerciseDTO:
        """Create RevisedExerciseDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "tags",
                "context_notes",
                "feedback_points_addressed",
            ],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
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
                # RevisedExercise-specific fields
                "revision_number",
                "instructions",
                "model",
                "context_notes",
                "feedback_points_addressed",
                "revision_rationale",
            },
            enum_mappings={
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, RevisedExerciseDTO):
            return False
        return self.uid == other.uid
