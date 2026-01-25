"""
Infrastructure Services Module
===============================

Shared infrastructure patterns for all service types.

Provides:
- SemanticRelationshipHelper[T, DTO]: Generic semantic relationship operations (Phase 3)
- LearningAlignmentHelper[T, DTO, Request]: Generic learning alignment operations (Phase 4)
- RelationshipCreationHelper[T, DTO]: Generic cross-domain relationship creation (Phase 5)
- PrerequisiteHelper: Unified prerequisite checking for planning/scheduling (January 2026)
- ProgressCalculationHelper: Unified progress calculation for all domains (January 2026)

Version: 1.4.0 (January 2026: Added ProgressCalculationHelper)
Date: 2026-01-19
"""

from core.services.infrastructure.learning_alignment_helper import LearningAlignmentHelper
from core.services.infrastructure.prerequisite_helper import (
    DEFAULT_MASTERY_THRESHOLD,
    PrerequisiteHelper,
    PrerequisiteResult,
)
from core.services.infrastructure.progress_calculation_helper import (
    DEFAULT_PROGRESS_WEIGHTS,
    STREAK_NORMALIZATION_DAYS,
    HabitContributionResult,
    ProgressCalculationHelper,
    ProgressContributions,
)
from core.services.infrastructure.relationship_creation_helper import RelationshipCreationHelper
from core.services.infrastructure.semantic_relationship_helper import SemanticRelationshipHelper

__all__ = [
    "DEFAULT_MASTERY_THRESHOLD",
    "DEFAULT_PROGRESS_WEIGHTS",
    "HabitContributionResult",
    "LearningAlignmentHelper",
    "PrerequisiteHelper",
    "PrerequisiteResult",
    "ProgressCalculationHelper",
    "ProgressContributions",
    "RelationshipCreationHelper",
    "SemanticRelationshipHelper",
    "STREAK_NORMALIZATION_DAYS",
]
