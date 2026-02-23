"""
Habit domain models — Habit, HabitDTO, requests, intelligence, completions.
"""

from .completion import HabitCompletion
from .completion_dto import HabitCompletionDTO
from .habit_completion_request import (
    HabitCompletionCreateRequest,
    HabitCompletionFilterRequest,
    HabitCompletionUpdateRequest,
)

# Intelligence models
from .habit_intelligence import (
    EnergyLevel,
    FailureReason,
    HabitCompletionContext,
    HabitCompletionIntelligence,
    HabitIntelligence,
)
from .habit_request import (
    HabitCompletionRequest,
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
    "HabitCompletion",
    "HabitCompletionContext",
    # Request Models - Completion (Three-tier)
    "HabitCompletionCreateRequest",
    "HabitCompletionDTO",
    "HabitCompletionFilterRequest",
    "HabitCompletionIntelligence",
    # Request Models - Completion (Legacy)
    "HabitCompletionRequest",
    "HabitCompletionUpdateRequest",
    # Request Models - Habit
    "HabitCreateRequest",
    "HabitFilterRequest",
    # Intelligence Models
    "HabitIntelligence",
    "HabitSkipRequest",
    "HabitStatsRequest",
    "HabitUpdateRequest",
]
