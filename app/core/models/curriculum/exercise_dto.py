"""
ExerciseDTO - Exercise-Specific DTO (Tier 2 - Transfer)
=========================================================

Extends CurriculumDTO with 7 exercise-specific fields matching the
Exercise frozen dataclass (Tier 3): instruction templates for LLM feedback.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── ExerciseDTO(CurriculumDTO) +7 exercise-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date

from core.models.curriculum.curriculum_dto import CurriculumDTO
from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.reports_enums import ProjectScope
from core.ports import get_enum_value


@dataclass
class ExerciseDTO(CurriculumDTO):
    """
    Mutable DTO for exercises (EntityType.EXERCISE).

    Extends CurriculumDTO with 7 exercise-specific fields:
    - instructions: LLM prompt for processing
    - model: Which LLM to use
    - scope: PERSONAL or ASSIGNED
    - due_date: Due date for ASSIGNED scope
    - group_uid: Target group for ASSIGNED scope
    - enrichment_mode: Processing strategy
    - context_notes: Reference materials
    """

    # =========================================================================
    # EXERCISE-SPECIFIC FIELDS
    # =========================================================================
    instructions: str | None = None
    model: str = "claude-3-5-sonnet-20241022"
    scope: ProjectScope = ProjectScope.PERSONAL
    due_date: date | None = None
    group_uid: str | None = None
    enrichment_mode: str | None = None
    context_notes: list[str] = field(default_factory=list)

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including exercise-specific fields."""
        from core.models.dto_helpers import convert_dates_to_iso

        data = super().to_dict()

        data.update(
            {
                "instructions": self.instructions,
                "model": self.model,
                "scope": get_enum_value(self.scope),
                "due_date": self.due_date,
                "group_uid": self.group_uid,
                "enrichment_mode": self.enrichment_mode,
                "context_notes": list(self.context_notes) if self.context_notes else [],
            }
        )

        convert_dates_to_iso(data, ["due_date"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExerciseDTO:
        """Create ExerciseDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "complexity": KuComplexity,
                "learning_level": LearningLevel,
                "sel_category": SELCategory,
                "scope": ProjectScope,
            },
            date_fields=["due_date"],
            datetime_fields=[
                "created_at",
                "updated_at",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
            list_fields=[
                "tags",
                "semantic_links",
                "learning_objectives",
                "context_notes",
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
                # CurriculumDTO fields
                "complexity",
                "learning_level",
                "sel_category",
                "quality_score",
                "estimated_time_minutes",
                "difficulty_rating",
                "semantic_links",
                "target_age_range",
                "learning_objectives",
                # Exercise-specific fields
                "instructions",
                "model",
                "scope",
                "due_date",
                "group_uid",
                "enrichment_mode",
                "context_notes",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "complexity": KuComplexity,
                "learning_level": LearningLevel,
                "sel_category": SELCategory,
                "scope": ProjectScope,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ExerciseDTO):
            return False
        return self.uid == other.uid
