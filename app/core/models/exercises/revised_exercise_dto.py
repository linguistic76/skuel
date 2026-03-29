"""
RevisedExerciseDTO - Revised Exercise-Specific DTO (Tier 2 - Transfer)
========================================================================

Extends UserOwnedDTO with 12 revised-exercise-specific fields matching the
RevisedExercise frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── RevisedExerciseDTO(UserOwnedDTO) +12 fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

import json
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

    Extends UserOwnedDTO with 12 revised-exercise-specific fields:
    - revision_number: Which revision iteration
    - original_exercise_uid: UID of the original Exercise
    - report_uid: UID of the ExerciseReport this addresses
    - submission_uid: UID of the ExerciseSubmission that was evaluated
    - student_uid: Target student
    - instructions: Revision instructions
    - model: Which LLM to use
    - context_notes: Reference materials
    - feedback_points: Typed feedback points (list of {category, detail} dicts)
    - revision_rationale: Why this revision was created
    - expected_modality: What submission format to expect
    """

    # =========================================================================
    # REVISED EXERCISE-SPECIFIC FIELDS
    # =========================================================================
    revision_number: int = 1
    original_exercise_uid: str | None = None
    report_uid: str | None = None
    submission_uid: str | None = None
    student_uid: str | None = None
    instructions: str | None = None
    model: str = "claude-sonnet-4-6"
    context_notes: list[str] = field(default_factory=list)
    feedback_points: list[dict[str, str]] = field(default_factory=list)
    revision_rationale: str | None = None
    expected_modality: str | None = None

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
                "report_uid": self.report_uid,
                "submission_uid": self.submission_uid,
                "student_uid": self.student_uid,
                "instructions": self.instructions,
                "model": self.model,
                "context_notes": list(self.context_notes) if self.context_notes else [],
                "feedback_points": (
                    json.dumps(self.feedback_points) if self.feedback_points else "[]"
                ),
                "revision_rationale": self.revision_rationale,
                "expected_modality": self.expected_modality,
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
            ],
            dict_fields=["metadata"],
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
                "feedback_points",
                "revision_rationale",
                "expected_modality",
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
