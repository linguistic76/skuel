"""
Infrastructure Services Module
===============================

Shared infrastructure patterns for all service types.

Provides:
- SemanticRelationshipLinker[T, DTO]: Generic semantic relationship operations
- LearningAlignmentBridge[T]: Generic learning alignment operations
- PrerequisiteChecker: Unified prerequisite checking for planning/scheduling (January 2026)
- ProgressCalculator: Unified progress calculation for all domains (January 2026)
"""

from core.services.infrastructure.learning_alignment_bridge import LearningAlignmentBridge
from core.services.infrastructure.prerequisite_checker import (
    DEFAULT_MASTERY_THRESHOLD,
    PrerequisiteChecker,
    PrerequisiteResult,
)
from core.services.infrastructure.progress_calculator import (
    DEFAULT_PROGRESS_WEIGHTS,
    STREAK_NORMALIZATION_DAYS,
    HabitContributionResult,
    ProgressCalculator,
    ProgressContributions,
)
from core.services.infrastructure.semantic_relationship_linker import SemanticRelationshipLinker

__all__ = [
    "DEFAULT_MASTERY_THRESHOLD",
    "DEFAULT_PROGRESS_WEIGHTS",
    "HabitContributionResult",
    "LearningAlignmentBridge",
    "PrerequisiteChecker",
    "PrerequisiteResult",
    "ProgressCalculator",
    "ProgressContributions",
    "SemanticRelationshipLinker",
    "STREAK_NORMALIZATION_DAYS",
]
