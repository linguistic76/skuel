"""
ExerciseDTO - Exercise-Specific DTO (Tier 2 - Transfer)
=========================================================

Extends CurriculumDTO with 9 exercise-specific fields matching the
Exercise frozen dataclass (Tier 3): instruction templates for LLM feedback.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── ExerciseDTO(CurriculumDTO) +9 exercise-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date

from core.models.curriculum_dto import CurriculumDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums import MasteryImpact
from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope, SubmissionModality


@dataclass
class ExerciseDTO(CurriculumDTO):
    """
    Mutable DTO for exercises (EntityType.EXERCISE).

    Extends CurriculumDTO with 9 exercise-specific fields:
    - path_step_uid: PathStep anchor (required for PERSONAL scope)
    - instructions: LLM prompt for processing
    - model: Which LLM to use
    - scope: PERSONAL or ASSIGNED
    - due_date: Due date for ASSIGNED scope
    - group_uid: Target group for ASSIGNED scope
    - enrichment_mode: Processing strategy
    - context_notes: Reference materials
    - form_schema: Optional inline form definition
    - expected_modality: What submission format this exercise expects
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.EXERCISE, kw_only=True)

    # =========================================================================
    # EXERCISE-SPECIFIC FIELDS
    # =========================================================================
    path_step_uid: str | None = None  # PathStep anchor — required for PERSONAL scope
    owner_uid: str | None = None  # UID of the user who created this exercise
    exercise_number: int | None = None
    instructions: str | None = None
    model: str = "claude-sonnet-4-6"
    scope: ExerciseScope = ExerciseScope.PERSONAL
    due_date: date | None = None
    group_uid: str | None = None
    enrichment_mode: str | None = None
    context_notes: list[str] = field(default_factory=list)
    form_schema: list[dict[str, Any]] | None = None  # Inline form definition
    expected_modality: SubmissionModality | None = None
    mastery_impact: MasteryImpact | None = None
    scoring_rubric: list[dict[str, Any]] | None = None  # Assessment rubric
    pass_threshold: float | None = None  # Minimum score (0.0-1.0) to pass

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
                "scope",
                "expected_modality",
                "mastery_impact",
            ],
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
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExerciseDTO:
        """Create ExerciseDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        # Neo4j stores form_schema and scoring_rubric as JSON strings — parse before dto_from_dict
        raw_schema = data.get("form_schema")
        raw_rubric = data.get("scoring_rubric")
        if isinstance(raw_schema, str) or isinstance(raw_rubric, str):
            data = dict(data)  # Don't mutate caller's dict
            if isinstance(raw_schema, str):
                try:
                    data["form_schema"] = json.loads(raw_schema)
                except json.JSONDecodeError, TypeError:
                    data["form_schema"] = None
            if isinstance(raw_rubric, str):
                try:
                    data["scoring_rubric"] = json.loads(raw_rubric)
                except json.JSONDecodeError, TypeError:
                    data["scoring_rubric"] = None

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
                "scope",
                "expected_modality",
                "mastery_impact",
            ),
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
                # Exercise-specific fields
                "path_step_uid",
                "exercise_number",
                "instructions",
                "model",
                "scope",
                "due_date",
                "group_uid",
                "enrichment_mode",
                "context_notes",
                "form_schema",
                "expected_modality",
                "mastery_impact",
                "scoring_rubric",
                "pass_threshold",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "complexity",
                "learning_level",
                "sel_category",
                "publication_state",
                "scope",
                "expected_modality",
                "mastery_impact",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ExerciseDTO):
            return False
        return self.uid == other.uid
