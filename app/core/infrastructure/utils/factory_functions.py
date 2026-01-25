"""
Factory Functions for Model Defaults
====================================

Named factory functions to replace lambda expressions in model definitions.
Following clean code principle: no lambdas, only named functions.
"""

from datetime import UTC
from typing import Any
from uuid import uuid4

from core.models.shared_enums import EnergyLevel, TimeOfDay


def create_step_uid() -> str:
    """Create a unique identifier for a learning path step."""
    return f"step_{uuid4().hex[:8]}"


def create_path_uid() -> str:
    """Create a unique identifier for a learning path."""
    return f"path_{uuid4().hex[:8]}"


def create_session_uid() -> str:
    """Create a unique identifier for a learning session."""
    return f"session_{uuid4().hex[:8]}"


def create_insight_uid() -> str:
    """Create a unique identifier for a learning insight."""
    return f"insight_{uuid4().hex[:8]}"


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
    from core.models.shared_enums import EnergyLevel, TimeOfDay

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
