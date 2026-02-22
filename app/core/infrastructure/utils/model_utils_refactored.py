"""
Model Utilities (Refactored)
============================

Imports and re-exports utilities from focused modules.

The utilities are now split into:
- uid_utils.py: UID generation and validation
- validation_utils.py: Model validation helpers
- time_utils.py: Time and timezone utilities
- Other domain-specific utilities remain here temporarily
"""

# Re-export from focused modules

# Keep domain-specific helpers here for now
from dataclasses import replace
from typing import Any, TypeVar

from core.models.enums import EntityStatus, Priority

T = TypeVar("T")


class UpdateHelper:
    """Helper for updating immutable models"""

    @staticmethod
    def update_entity(entity: T, **updates: Any) -> T:
        """
        Update an immutable entity by creating a new instance.

        Args:
            entity: Entity to update
            **updates: Fields to update

        Returns:
            New entity instance with updates
        """
        return replace(entity, **updates)


class ScoringHelper:
    """Scoring and progress calculation utilities"""

    @staticmethod
    def calculate_mastery_score(correct: int, total: int, time_bonus: float = 0.0) -> float:
        """
        Calculate mastery score.

        Args:
            correct: Number of correct answers,
            total: Total number of questions,
            time_bonus: Bonus for speed (0-0.2)

        Returns:
            Score between 0 and 1
        """
        if total == 0:
            return 0.0

        base_score = correct / total
        return min(1.0, base_score + time_bonus)

    @staticmethod
    def calculate_priority_weight(priority: Priority) -> float:
        """
        Convert priority to numerical weight.

        Args:
            priority: Priority enum

        Returns:
            Weight value (0.5-2.0)
        """
        weights = {
            Priority.LOW: 0.5,
            Priority.MEDIUM: 1.0,
            Priority.HIGH: 1.5,
            Priority.CRITICAL: 2.0,
        }
        return weights.get(priority, 1.0)

    @staticmethod
    def is_complete(status: EntityStatus) -> bool:
        """
        Check if status represents completion.

        Args:
            status: Activity status

        Returns:
            True if completed
        """
        return status in [
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        ]
