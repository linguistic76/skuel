"""
Cypher Generator Helpers - Shared utility functions for Cypher query generation.

This module contains helper functions used across multiple Cypher generator modules.
"""

import re
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

# =============================================================================
# Shared Edge Alternations
# =============================================================================

CURRICULUM_COMPOSITION_EDGES: str = "|".join(
    (
        RelationshipName.USES_KU.value,
        RelationshipName.CONTAINS_KNOWLEDGE.value,
        RelationshipName.TRAINS_KU.value,
    )
)
"""The canonical PathStep→Ku composition triple, as a Cypher type alternation.

ONE definition, because every reader of it must agree with the substance write
fan-out: a step's per-user substance is the mean over the Kus it composes, so a
reader matching a narrower set credits the learner for fewer Kus than the step
itself claims — which reads as "you never applied this" on knowledge they did
apply. That asymmetry has already been shipped twice (the MEGA-QUERY rollups
listed two of the three until 2026-08-12), and a hand-copied literal in each
query is how it recurs.

Built from ``RelationshipName`` rather than spelled out, so a renamed or
normalised edge moves every site at once instead of silently matching nothing.
"""

# =============================================================================
# Cypher Injection Guards
# =============================================================================

_VALID_NEO4J_LABELS: frozenset[str] = frozenset(v.value for v in NeoLabel)
_VALID_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_label(label: NeoLabel) -> None:
    """Raise ValueError if label is not a known NeoLabel value."""
    if label not in _VALID_NEO4J_LABELS:
        raise ValueError(f"Invalid Neo4j label: {label!r}")


def validate_identifier(name: str, context: str = "field") -> None:
    """Raise ValueError if name contains characters unsafe for Cypher interpolation."""
    if not _VALID_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {context} name: {name!r}")


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
        fields = get_filterable_fields(Task)
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


# Re-export for convenience
__all__ = [
    "convert_value_for_neo4j",
    "get_filterable_fields",
    "get_supported_operators",
    "validate_identifier",
    "validate_label",
]
