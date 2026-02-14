"""
Habit Models - Preserved Types
==============================

Habit domain now uses the unified Ku model (core.models.ku).
This package preserves habit-specific types that have no Ku equivalent:
- habit_request.py - Habit API request/response models (Pydantic)
- habit_completion_request.py - Completion request models (Pydantic)
- habit_intelligence.py - Habit intelligence dataclasses
- completion.py - HabitCompletion domain model (separate entity, not a Ku)
- completion_dto.py - HabitCompletionDTO for data transfer
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
