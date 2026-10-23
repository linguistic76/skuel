"""
Factory Functions for Model Defaults
====================================

Named factory functions to replace lambda expressions in model definitions.
Following clean code principle: no lambdas, only named functions.
"""

from datetime import UTC
from typing import Any

from core.models.enums import EnergyLevel, TimeOfDay


def create_default_search_fields() -> list[str]:
    """Create default search fields for knowledge units."""
    return ["title", "summary", "tags"]


def create_default_energy_pattern() -> dict[TimeOfDay, EnergyLevel]:
    """Create default energy pattern for user preferences."""
    return {
        TimeOfDay.MORNING: EnergyLevel.MEDIUM,
        TimeOfDay.AFTERNOON: EnergyLevel.HIGH,
        TimeOfDay.EVENING: EnergyLevel.LOW,
    }


def create_default_user_energy_pattern() -> dict[TimeOfDay, EnergyLevel]:
    """Create default energy pattern dictionary for user schemas."""
    from core.models.enums import EnergyLevel, TimeOfDay

    return {
        TimeOfDay.MORNING: EnergyLevel.HIGH,
        TimeOfDay.AFTERNOON: EnergyLevel.MEDIUM,
        TimeOfDay.EVENING: EnergyLevel.LOW,
    }


def create_current_timestamp() -> Any:
    """Create a current UTC timestamp."""
    from datetime import datetime

    return datetime.now(UTC)


def create_turn_id() -> str:
    """Create a unique identifier for a conversation turn."""
    from uuid import uuid4

    return str(uuid4())
