"""
PathStepDTO - Path Step-Specific DTO (Tier 2 - Transfer)
==================================================================

Extends CurriculumDTO with 9 path-step-specific fields matching the
PathStep frozen dataclass (Tier 3): intent, knowledge references,
path relationship, and mastery tracking.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── PathStepDTO(CurriculumDTO) +9 path-step-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.curriculum_dto import CurriculumDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.curriculum_enums import StepDifficulty
from core.models.enums.entity_enums import EntityType


@dataclass
class PathStepDTO(CurriculumDTO):
    """
    Mutable DTO for path steps (EntityType.PATH_STEP).

    Extends CurriculumDTO with 9 path-step-specific fields:
    - Intent (1): intent
    - NOUS membership (1): nous
    - Knowledge references (1): knowledge_uids
    - Path relationship (2): learning_path_uid, sequence
    - Mastery (4): mastery_threshold, current_mastery, estimated_hours, step_difficulty
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.PATH_STEP, kw_only=True)

    # =========================================================================
    # INTENT
    # =========================================================================
    intent: str | None = None

    # =========================================================================
    # NOUS TOPIC MEMBERSHIP
    # =========================================================================
    # Multi-topic; empty = deliberately unassigned (rawness principle)
    nous: list[str] = field(default_factory=list)
    # NOUS sub-topic membership (2nd taxonomy level — mirrors Ku + `nous`)
    nous_subtopic: list[str] = field(default_factory=list)

    # =========================================================================
    # KNOWLEDGE REFERENCES
    # =========================================================================
    knowledge_uids: list[str] = field(default_factory=list)

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
                "step_difficulty",
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
    def from_dict(cls, data: dict[str, Any]) -> PathStepDTO:
        """Create PathStepDTO from dictionary (from database)."""
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
                "step_difficulty",
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
                "knowledge_uids",
                "nous",
                "nous_subtopic",
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
                # PathStep-specific fields
                "intent",
                "nous",
                "nous_subtopic",
                "knowledge_uids",
                "learning_path_uid",
                "sequence",
                "mastery_threshold",
                "current_mastery",
                "estimated_hours",
                "step_difficulty",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
                "step_difficulty",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, PathStepDTO):
            return False
        return self.uid == other.uid
