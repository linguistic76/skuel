"""
CurriculumDTO - Curriculum-Specific DTO (Tier 2 - Transfer)
=============================================================

Extends EntityDTO (NOT UserOwnedDTO) with 21 curriculum-specific fields
matching the Curriculum frozen dataclass (Tier 3): learning metadata and
substance tracking. Curriculum types are shared content, not user-owned.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        ├── LearningStepDTO(CurriculumDTO) +9
        ├── LearningPathDTO(CurriculumDTO) +4
        └── ExerciseDTO(CurriculumDTO) +7

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.entity_dto import EntityDTO
from core.ports import get_enum_value


@dataclass
class CurriculumDTO(EntityDTO):
    """
    Mutable DTO for curriculum entities (EntityType.CURRICULUM).

    Extends EntityDTO (NOT UserOwnedDTO) with 21 curriculum-specific fields:
    - Learning metadata (9): complexity, learning_level, sel_category, quality_score,
      estimated_time_minutes, difficulty_rating, semantic_links, target_age_range, learning_objectives
    - Substance tracking (10): 5 counters + 5 last-dates
    """

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

    # =========================================================================
    # SUBSTANCE TRACKING
    # =========================================================================
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
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
        """Convert to dictionary, including curriculum-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = super().to_dict()

        data.update(
            {
                # Learning metadata
                "complexity": get_enum_value(self.complexity),
                "learning_level": get_enum_value(self.learning_level),
                "sel_category": get_enum_value(self.sel_category),
                "quality_score": self.quality_score,
                "estimated_time_minutes": self.estimated_time_minutes,
                "difficulty_rating": self.difficulty_rating,
                "semantic_links": list(self.semantic_links) if self.semantic_links else [],
                "target_age_range": list(self.target_age_range)
                if self.target_age_range
                else None,
                "learning_objectives": list(self.learning_objectives)
                if self.learning_objectives
                else [],
                # Substance tracking
                "times_applied_in_tasks": self.times_applied_in_tasks,
                "times_practiced_in_events": self.times_practiced_in_events,
                "times_built_into_habits": self.times_built_into_habits,
                "journal_reflections_count": self.journal_reflections_count,
                "choices_informed_count": self.choices_informed_count,
                "last_applied_date": self.last_applied_date,
                "last_practiced_date": self.last_practiced_date,
                "last_built_into_habit_date": self.last_built_into_habit_date,
                "last_reflected_date": self.last_reflected_date,
                "last_choice_informed_date": self.last_choice_informed_date,
            }
        )

        convert_datetimes_to_iso(
            data,
            [
                "last_applied_date",
                "last_practiced_date",
                "last_built_into_habit_date",
                "last_reflected_date",
                "last_choice_informed_date",
            ],
        )

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CurriculumDTO:
        """Create CurriculumDTO from dictionary (from database)."""
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
            },
            datetime_fields=[
                "created_at", "updated_at",
                "last_applied_date", "last_practiced_date",
                "last_built_into_habit_date", "last_reflected_date",
                "last_choice_informed_date",
            ],
            list_fields=[
                "tags", "semantic_links", "learning_objectives",
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
                "title", "content", "summary", "description", "word_count",
                "domain", "status", "tags", "metadata",
                # Curriculum-specific fields
                "complexity", "learning_level", "sel_category",
                "quality_score", "estimated_time_minutes", "difficulty_rating",
                "semantic_links", "target_age_range", "learning_objectives",
                "times_applied_in_tasks", "times_practiced_in_events",
                "times_built_into_habits", "journal_reflections_count",
                "choices_informed_count",
                "last_applied_date", "last_practiced_date",
                "last_built_into_habit_date", "last_reflected_date",
                "last_choice_informed_date",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "complexity": KuComplexity,
                "learning_level": LearningLevel,
                "sel_category": SELCategory,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, CurriculumDTO):
            return False
        return self.uid == other.uid
