"""
LearningPathDTO - Learning Path-Specific DTO (Tier 2 - Transfer)
==================================================================

Extends CurriculumDTO with 4 learning-path-specific fields matching the
LearningPath frozen dataclass (Tier 3): path configuration.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── LearningPathDTO(CurriculumDTO) +4 learning-path-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.curriculum_dto import CurriculumDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.curriculum_enums import LpType
from core.models.enums.entity_enums import EntityType


@dataclass
class LearningPathDTO(CurriculumDTO):
    """
    Mutable DTO for learning paths (EntityType.LEARNING_PATH).

    Extends CurriculumDTO with 4 learning-path-specific fields:
    - Path configuration (4): path_type, outcomes, checkpoint_week_intervals, estimated_hours
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.LEARNING_PATH, kw_only=True)

    # =========================================================================
    # PATH CONFIGURATION
    # =========================================================================
    path_type: LpType | None = None
    outcomes: list[str] = field(default_factory=list)
    checkpoint_week_intervals: list[int] = field(default_factory=list)
    estimated_hours: float | None = None

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
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
                "path_type",
            ],
            datetime_fields=[
                "created_at",
                "updated_at",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningPathDTO:
        """Create LearningPathDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
                "path_type",
            ),
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
                "outcomes",
                "checkpoint_week_intervals",
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
                # CurriculumDTO fields
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
                "quality_score",
                "estimated_time_minutes",
                "difficulty_rating",
                "semantic_links",
                "target_age_range",
                "learning_objectives",
                # LearningPath-specific fields
                "path_type",
                "outcomes",
                "checkpoint_week_intervals",
                "estimated_hours",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
                "path_type",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, LearningPathDTO):
            return False
        return self.uid == other.uid
