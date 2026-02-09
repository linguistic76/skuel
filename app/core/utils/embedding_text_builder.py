"""
Embedding Text Builder Utility

Single source of truth for extracting embeddable text from entities.

Usage:
    # From dict (ingestion):
    text = build_embedding_text(EntityType.TASK, {"title": "Fix bug", "description": "Fix login"})

    # From model (background worker):
    text = build_embedding_text(EntityType.TASK, task_model)

See: /docs/patterns/EMBEDDING_ARCHITECTURE.md
"""

from typing import Any, Protocol, overload

from core.models.enums import EntityType


class HasAttributes(Protocol):
    """Protocol for objects with getattr support (domain models)."""

    def __getattribute__(self, name: str) -> Any: ...


# Single source of truth for embedding field mappings
EMBEDDING_FIELD_MAPS: dict[EntityType, tuple[str, ...]] = {
    EntityType.KU: ("title", "content", "summary"),
    EntityType.TASK: ("title", "description"),
    EntityType.GOAL: ("title", "description", "vision_statement"),
    EntityType.HABIT: ("name", "title", "description", "cue", "reward"),
    EntityType.EVENT: ("title", "description", "location"),
    EntityType.CHOICE: ("title", "description", "decision_context", "outcome"),
    EntityType.PRINCIPLE: ("name", "statement", "description"),
}


@overload
def build_embedding_text(entity_type: EntityType, source: dict[str, Any]) -> str: ...


@overload
def build_embedding_text(entity_type: EntityType, source: HasAttributes) -> str: ...


def build_embedding_text(
    entity_type: EntityType,
    source: dict[str, Any] | HasAttributes,
) -> str:
    """
    Build embedding text from entity data.

    Handles both dict (ingestion) and domain model (background worker) inputs.
    Returns empty string if no embeddable content found.

    Args:
        entity_type: Type of entity (determines field mapping)
        source: Either dict (from ingestion) or domain model (from worker)

    Returns:
        Concatenated text from configured fields, or empty string if no content.

    Examples:
        >>> # From dict (ingestion)
        >>> data = {"title": "Learn Python", "description": "Master the basics"}
        >>> build_embedding_text(EntityType.TASK, data)
        'Learn Python\nMaster the basics'

        >>> # From model (background worker)
        >>> task = Task(title="Learn Python", description="Master the basics")
        >>> build_embedding_text(EntityType.TASK, task)
        'Learn Python\nMaster the basics'

        >>> # KU uses double newlines
        >>> ku_data = {
        ...     "title": "Python",
        ...     "content": "A programming language",
        ...     "summary": "High-level",
        ... }
        >>> build_embedding_text(EntityType.KU, ku_data)
        'Python\n\nA programming language\n\nHigh-level'

        >>> # Missing fields handled gracefully
        >>> data = {"title": "Task without description"}
        >>> build_embedding_text(EntityType.TASK, data)
        'Task without description'

        >>> # Empty dict returns empty string
        >>> build_embedding_text(EntityType.TASK, {})
        ''
    """
    # Get field mapping for this entity type
    fields = EMBEDDING_FIELD_MAPS.get(entity_type)
    if not fields:
        return ""

    # Extract field values
    parts: list[str] = []
    for field in fields:
        value = _get_field_value(source, field)
        if value:
            parts.append(str(value).strip())

    if not parts:
        return ""

    # KU uses double newlines for better semantic separation
    # (title, content blocks, summary are distinct concepts)
    separator = "\n\n" if entity_type == EntityType.KU else "\n"
    return separator.join(parts)


def _get_field_value(source: dict[str, Any] | HasAttributes, field: str) -> Any:
    """
    Extract field value from dict or object.

    Uses duck typing with sentinel pattern to avoid hasattr() (SKUEL011).

    Args:
        source: Dict or object with attributes
        field: Field name to extract

    Returns:
        Field value or None if not found/empty
    """
    # Sentinel for missing attributes (SKUEL011 compliant)
    _not_found = object()

    if isinstance(source, dict):
        value = source.get(field)
    else:
        # Use sentinel pattern instead of hasattr() (SKUEL011)
        value = getattr(source, field, _not_found)
        if value is _not_found:
            return None

    # Treat empty strings/whitespace as None
    if isinstance(value, str) and not value.strip():
        return None

    return value
