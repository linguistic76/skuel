"""
Enum Field Registry
===================

THE single source of truth for "which node/frontmatter fields are enum-valued,
and which Enum canonicalizes them". SKUEL's naming discipline keeps field names
globally consistent across entity types (``status`` is always ``EntityStatus``,
``sel_category`` is always ``SELCategory``, ...), so one flat map serves every
consumer:

- DTO ``from_neo4j_data`` methods slice their per-class maps via
  ``enum_fields_for(...)`` instead of each repeating the field→enum
  association inline (``sel_category → SELCategory`` used to be spelled out
  in five separate DTO modules).
- Ingestion canonicalizes authored enum values against the full registry
  (``canonicalize_enum_values`` in ``core/services/ingestion/preparer.py``)
  so vault authors can type ``learning_level: BEGINNER``, a documented alias
  (``status: pending``), or the ``none`` absence marker and the graph still
  stores the canonical member value (or drops the property); what remains
  non-member is rejected by the ingestion validator's vocabulary gate.

Adding a NEW enum-valued field: register it here, then slice it into the
owning DTO's ``enum_fields_for(...)`` call. A field name may appear only once
— if two entity types ever need the same field name with different enums,
that is a naming-convention violation to fix, not a registry limitation.

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from enum import Enum

from core.models.enums import Domain, KuComplexity, LearningLevel, MasteryImpact, SELCategory
from core.models.enums.activity_enums import Confidence, EngagementState
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.curriculum_enums import LpType, StepDifficulty
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.event_enums import EventType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.interaction_enums import InteractionResult, InteractionType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline, ReportSource
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.enums.scheduling_enums import RecurrencePattern, TimeOfDay
from core.models.enums.user_entry_enums import ExerciseScope, SubmissionModality

ENUM_FIELD_TYPES: dict[str, type[Enum]] = {
    # Universal Entity fields
    "entity_type": EntityType,
    "status": EntityStatus,
    "domain": Domain,
    "visibility": Visibility,
    # Curriculum fields
    "confidence": Confidence,
    "complexity": KuComplexity,
    "learning_level": LearningLevel,
    "sel_category": SELCategory,
    "step_difficulty": StepDifficulty,
    "path_type": LpType,
    # Exercise fields
    "scope": ExerciseScope,
    "expected_modality": SubmissionModality,
    "mastery_impact": MasteryImpact,
    # UserEntry fields
    "pipeline": Pipeline,
    "modality": SubmissionModality,
    # Interaction fields
    "interaction_type": InteractionType,
    "result_status": InteractionResult,
    # Activity lifecycle + scheduling fields (instances and templates)
    "engagement_state": EngagementState,
    "recurrence_pattern": RecurrencePattern,
    "preferred_time": TimeOfDay,
    # Goal fields
    "goal_type": GoalType,
    "timeframe": GoalTimeframe,
    "measurement_type": MeasurementType,
    # Habit fields
    "polarity": HabitPolarity,
    "habit_category": HabitCategory,
    "habit_difficulty": HabitDifficulty,
    # Event fields
    "event_type": EventType,
    # Choice fields
    "choice_type": ChoiceType,
    # Principle fields
    "principle_category": PrincipleCategory,
    "principle_source": PrincipleSource,
    "strength": PrincipleStrength,
    "current_alignment": AlignmentLevel,
    # LifePath fields
    "alignment_level": AlignmentLevel,
    # Report fields
    "processor_type": ReportSource,
    "assessment_outcome": AssessmentOutcome,
}


def enum_fields_for(*field_names: str) -> dict[str, type[Enum]]:
    """
    Slice the registry into a DTO's ``enum_fields`` map.

    A KeyError here is a real bug — the field is enum-valued somewhere but was
    never registered, which would also leave its authored casing unnormalized
    at ingestion.
    """
    return {name: ENUM_FIELD_TYPES[name] for name in field_names}


__all__ = ["ENUM_FIELD_TYPES", "enum_fields_for"]
