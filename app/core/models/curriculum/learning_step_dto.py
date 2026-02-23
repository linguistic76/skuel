"""
LearningStepDTO - Learning Step-Specific DTO (Tier 2 - Transfer)
==================================================================

Extends CurriculumDTO with 9 learning-step-specific fields matching the
LearningStep frozen dataclass (Tier 3): intent, knowledge references,
path relationship, and mastery tracking.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── LearningStepDTO(CurriculumDTO) +9 learning-step-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory
from core.models.enums.ku_enums import EntityStatus, EntityType, StepDifficulty
from core.models.curriculum.curriculum_dto import CurriculumDTO
from core.ports import get_enum_value


@dataclass
class LearningStepDTO(CurriculumDTO):
    """
    Mutable DTO for learning steps (EntityType.LEARNING_STEP).

    Extends CurriculumDTO with 9 learning-step-specific fields:
    - Intent (1): intent
    - Knowledge references (2): primary_knowledge_uids, supporting_knowledge_uids
    - Path relationship (2): learning_path_uid, sequence
    - Mastery (4): mastery_threshold, current_mastery, estimated_hours, step_difficulty
    """

    # =========================================================================
    # INTENT
    # =========================================================================
    intent: str | None = None

    # =========================================================================
    # KNOWLEDGE REFERENCES
    # =========================================================================
    primary_knowledge_uids: list[str] = field(default_factory=list)
    supporting_knowledge_uids: list[str] = field(default_factory=list)

    # =========================================================================
    # PATH RELATIONSHIP
    # =========================================================================
    learning_path_uid: str | None = None
    sequence: int | None = None

    # =========================================================================
    # MASTERY
    # =========================================================================
    mastery_threshold: float = 0.7
    current_mastery: float = 0.0
    estimated_hours: float | None = None
    step_difficulty: StepDifficulty | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including learning-step-specific fields."""
        data = super().to_dict()

        data.update(
            {
                "intent": self.intent,
                "primary_knowledge_uids": list(self.primary_knowledge_uids)
                if self.primary_knowledge_uids
                else [],
                "supporting_knowledge_uids": list(self.supporting_knowledge_uids)
                if self.supporting_knowledge_uids
                else [],
                "learning_path_uid": self.learning_path_uid,
                "sequence": self.sequence,
                "mastery_threshold": self.mastery_threshold,
                "current_mastery": self.current_mastery,
                "estimated_hours": self.estimated_hours,
                "step_difficulty": get_enum_value(self.step_difficulty),
            }
        )

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningStepDTO:
        """Create LearningStepDTO from dictionary (from database)."""
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
                "step_difficulty": StepDifficulty,
            },
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
                "primary_knowledge_uids",
                "supporting_knowledge_uids",
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
                # LearningStep-specific fields
                "intent",
                "primary_knowledge_uids",
                "supporting_knowledge_uids",
                "learning_path_uid",
                "sequence",
                "mastery_threshold",
                "current_mastery",
                "estimated_hours",
                "step_difficulty",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "complexity": KuComplexity,
                "learning_level": LearningLevel,
                "sel_category": SELCategory,
                "step_difficulty": StepDifficulty,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, LearningStepDTO):
            return False
        return self.uid == other.uid
