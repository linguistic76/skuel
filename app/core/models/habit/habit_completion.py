"""
Habit Completion Bridge
=======================

Bridge file for backward compatibility during three-tier migration.
Re-exports the new three-tier models with the old names.

MIGRATION COMPLETE: All models now use three-tier architecture.
"""

# Import the new three-tier models
from .completion import HabitCompletion
from .completion_converters import (
    completion_create_request_to_dto,
    completion_dict_to_dto,
    completion_domain_to_dto,
    completion_dto_to_dict,
    completion_dto_to_domain,
)
from .completion_dto import HabitCompletionDTO
from .habit_completion_request import (
    HabitCompletionCreateRequest,
    HabitCompletionFilterRequest,
    HabitCompletionUpdateRequest,
)

# No aliases needed - use HabitCompletion directly

__all__ = [
    # New three-tier models
    "HabitCompletion",
    "HabitCompletionCreateRequest",
    "HabitCompletionDTO",
    "HabitCompletionFilterRequest",
    "HabitCompletionUpdateRequest",
    # Converters
    "completion_create_request_to_dto",
    "completion_dict_to_dto",
    "completion_domain_to_dto",
    "completion_dto_to_dict",
    "completion_dto_to_domain",
]
