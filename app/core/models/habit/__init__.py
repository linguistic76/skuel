"""
Habit Three-Tier Model Package
===============================

Exports all habit-related models following the three-tier architecture:
- Tier 1 (External): Request models for API validation
- Tier 2 (Transfer): DTOs for data manipulation
- Tier 3 (Core): Immutable domain models with business logic
"""

# Import three-tier habit completion models
from .completion import HabitCompletion
from .completion_dto import HabitCompletionDTO
from .habit import Habit, HabitCategory, HabitDifficulty, HabitPolarity, HabitStatus
from .habit_completion_request import (
    HabitCompletionCreateRequest,
    HabitCompletionFilterRequest,
    HabitCompletionUpdateRequest,
)
from .habit_dto import HabitDTO
from .habit_request import (
    HabitCompletionRequest,  # Legacy request model
    HabitCreateRequest,
    HabitFilterRequest,
    HabitSkipRequest,
    HabitStatsRequest,
    HabitUpdateRequest,
)

__all__ = [
    "EnergyLevel",
    "FailureReason",
    # Domain Models
    "Habit",
    "HabitCategory",
    "HabitCompletion",
    "HabitCompletionContext",
    # Request Models - Completion (Three-tier)
    "HabitCompletionCreateRequest",
    "HabitCompletionDTO",
    "HabitCompletionFilterRequest",
    # Request Models - Completion (Legacy)
    "HabitCompletionRequest",
    "HabitCompletionUpdateRequest",
    # Request Models - Habit
    "HabitCreateRequest",
    # DTOs
    "HabitDTO",
    "HabitDifficulty",
    "HabitFilterRequest",
    # Intelligence Models
    "HabitIntelligence",
    # Enums
    "HabitPolarity",
    "HabitSkipRequest",
    "HabitStatsRequest",
    "HabitStatus",
    "HabitUpdateRequest",
]

# Intelligence models
from .habit_intelligence import (
    EnergyLevel,
    FailureReason,
    HabitCompletionContext,
    HabitIntelligence,
)
