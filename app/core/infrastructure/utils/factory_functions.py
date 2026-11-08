"""
Factory Functions for Model Defaults
====================================

Named factory functions to replace lambda expressions in model definitions.
Following clean code principle: no lambdas, only named functions.
"""

from datetime import UTC, datetime
from uuid import uuid4


def create_current_timestamp() -> datetime:
    """Create a current UTC timestamp."""
    return datetime.now(UTC)


def create_turn_id() -> str:
    """Create a unique identifier for a conversation turn."""
    return str(uuid4())
