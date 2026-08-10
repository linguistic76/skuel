"""
CurriculumDTO - Curriculum-Specific DTO (Tier 2 - Transfer)
=============================================================

Extends EntityDTO (NOT UserOwnedDTO) with ~22 curriculum-specific fields
matching the Curriculum frozen dataclass (Tier 3): confidence, learning
metadata, and substance tracking. Curriculum types are shared content,
not user-owned.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +22 curriculum-specific fields
        ├── PathStepDTO(CurriculumDTO) +9
        ├── LearningPathDTO(CurriculumDTO) +4
        └── ExerciseDTO(CurriculumDTO) +7

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums import KuComplexity, LearningLevel, SELCategory
from core.models.enums.activity_enums import Confidence


@dataclass
class CurriculumDTO(EntityDTO):
    """
    Mutable DTO for curriculum entities.

    Extends EntityDTO (NOT UserOwnedDTO) with ~22 curriculum-specific fields:
    - Confidence (1): admin-assessed content certainty
    - Learning metadata (10): complexity, learning_level, sel_category, quality_score,
      estimated_time_minutes, difficulty_rating, semantic_links, target_age_range,
      learning_objectives, structured_learning_objectives
    - Substance tracking (10): 5 counters + 5 last-dates
    """

    # =========================================================================
    # CONFIDENCE (admin-assessed certainty about this curriculum content)
    # =========================================================================
    confidence: Confidence | None = None

    # =========================================================================
    # LEARNING METADATA
    # =========================================================================
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5
    semantic_links: list[str] = field(default_factory=list)
    target_age_range: list[int] | None = None
    learning_objectives: list[str] = field(default_factory=list)
    structured_learning_objectives: list[Any] = field(default_factory=list)

    # =========================================================================
    # SUBSTANCE TRACKING
    # =========================================================================
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    times_reflected_in_entries: int = 0
    choices_informed_count: int = 0

    last_applied_date: datetime | None = None
    last_practiced_date: datetime | None = None
    last_built_into_habit_date: datetime | None = None
    last_reflected_date: datetime | None = None
    last_choice_informed_date: datetime | None = None

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
                "confidence",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
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
    def from_dict(cls, data: dict[str, Any]) -> CurriculumDTO:
        """Create CurriculumDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "confidence",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
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
                "structured_learning_objectives",
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
                # Curriculum-specific fields
                "confidence",
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
                "structured_learning_objectives",
                "times_applied_in_tasks",
                "times_practiced_in_events",
                "times_built_into_habits",
                "times_reflected_in_entries",
                "choices_informed_count",
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "confidence",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, CurriculumDTO):
            return False
        return self.uid == other.uid
