"""
Cypher Generator Helpers - Shared utility functions for Cypher query generation.

This module contains helper functions used across multiple Cypher generator modules.
"""

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


def convert_value_for_neo4j(value: Any) -> Any:
    """
    Convert Python value to Neo4j-compatible value during query parameter binding.

    This handles the persistence boundary (Python→Neo4j driver), which is distinct
    from the HTTP boundary (Pydantic validates incoming JSON). The Neo4j driver does
    NOT auto-serialize Python enums or date objects, so this conversion is required.

    Handles:
    - Enum → .value
    - date/datetime → ISO string
    - Other → passthrough

    Args:
        value: Python value to convert

    Returns:
        Neo4j-compatible value
    """
    if isinstance(value, Enum):
        return value.value
    elif isinstance(value, date | datetime):
        return value.isoformat()
    else:
        return value


def get_filterable_fields[T](entity_class: type[T]) -> list[str]:
    """
    Get list of field names that can be used for filtering.

    Args:
        entity_class: Domain model class (must be dataclass)

    Returns:
        List of field names

    Raises:
        ValueError: If entity_class is not a dataclass

    Example:
        fields = get_filterable_fields(TaskPure)
        # ['uid', 'title', 'priority', 'status', 'due_date', ...]
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    return [f.name for f in fields(entity_class)]


def get_supported_operators() -> list[str]:
    """
    Get list of supported filter operators.

    Returns:
        List of operator names that can be used in filter keys.

    Supported operators:
        - eq (default): Exact match
        - gt, lt, gte, lte: Comparisons
        - contains: String matching or list membership
        - in: List membership
    """
    return ["eq", "gt", "lt", "gte", "lte", "contains", "in"]


def validate_dataclass[T](entity_class: type[T], operation: str = "operation") -> None:
    """
    Guard clause: verify entity_class is a dataclass before field introspection.

    CypherGenerator uses ``dataclasses.fields()`` to auto-generate Cypher from model
    structure. Passing a non-dataclass (e.g., a Pydantic model or plain class) would
    produce a cryptic TypeError deep in field introspection. This check fails fast
    with a clear message instead. It is NOT schema validation — it's a precondition
    for the code that follows.

    Args:
        entity_class: Class to validate
        operation: Name of operation for error message

    Raises:
        ValueError: If entity_class is not a dataclass
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass for {operation}, got {entity_class}")


def get_field_names[T](entity_class: type[T]) -> set[str]:
    """
    Get set of field names from a dataclass.

    Args:
        entity_class: Dataclass to get fields from

    Returns:
        Set of field names
    """
    return {f.name for f in fields(entity_class)}


# Re-export for convenience
__all__ = [
    "convert_value_for_neo4j",
    "get_field_names",
    "get_filterable_fields",
    "get_supported_operators",
    "validate_dataclass",
]
