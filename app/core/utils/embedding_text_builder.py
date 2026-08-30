"""
Embedding Text Builder Utility

Single source of truth for extracting embeddable text from entities.

Usage:
    # From dict (ingestion):
    text = build_embedding_text(EntityType.TASK, {"title": "Fix bug", "description": "Fix login"})

    # From model (background worker):
    text = build_embedding_text(EntityType.TASK, task_model)

See: /docs/decisions/ADR-074-post-persist-embedding-events.md
"""

import hashlib
from typing import Any, overload

from core.models.enums.entity_enums import EntityType

# Single source of truth for embedding field mappings — the keys ARE the list
# of content-bearing entity types; no prose count elsewhere is authoritative.
# A map declares WHAT would be embedded, not that anything is: a type is
# embedded only through an event class in EMBEDDING_EVENT_TYPES
# (core/events/embedding_publisher.py). A map with no event class is HOLLOW —
# nothing builds text for it — and must be registered in
# PLANNED_EMBEDDING_MAPS (scripts/detect_bloat.py), which audits the derived
# hollow set on every run; an unregistered hollow map fails --check.
# PATH_STEP deliberately excludes "content": the entity vector covers
# frontmatter fields only — body-content semantics live in CHUNK embeddings
# (ADR-074). Keeping it out makes that hold on every trigger path (ingest,
# in-app update, --stale backfill), even against a legacy node that still
# carries a content property.
EMBEDDING_FIELD_MAPS: dict[EntityType, tuple[str, ...]] = {
    EntityType.PATH_STEP: ("title", "intent", "description", "summary"),
    EntityType.KU: ("title", "summary", "description"),
    EntityType.RESOURCE: ("title", "author", "content", "summary"),
    EntityType.TASK: ("title", "description"),
    EntityType.GOAL: ("title", "description", "vision_statement"),
    # HABIT: "name" was a phantom — Habit has no such field (its name IS
    # ``title``), no vault file authors ``name:``, and the enrichment dicts that
    # carry ``"name": habit.title`` never reach this builder. Found by the
    # detector's advisory phantom-field check the day it landed; dropping it
    # changes no model-path text (the name never contributed).
    EntityType.HABIT: ("title", "description", "cue", "reward"),
    EntityType.EVENT: ("title", "description", "location"),
    # CHOICE: "outcome" was a phantom — the column is ``actual_outcome``, so the
    # map silently contributed nothing for it. ``decision_context`` was equally
    # phantom until it became a real column; both now name what Choice actually has.
    EntityType.CHOICE: ("title", "description", "decision_context", "actual_outcome"),
    # PRINCIPLE includes ``why_important``: before it became a column its text was
    # spliced into ``description``, so it was already part of what got embedded.
    # Dropping it from the map on promotion would have quietly shrunk the semantic
    # surface of every principle.
    EntityType.PRINCIPLE: ("title", "statement", "description", "why_important"),
    EntityType.REVISED_EXERCISE: ("title", "instructions", "revision_rationale"),
    EntityType.EXERCISE: ("title", "instructions", "description"),
    EntityType.LEARNING_PATH: ("title", "description", "outcomes"),
    # USER_ENTRY: knowledge entries hold their body in ``content``;
    # ``processed_content`` is pipeline-specific output. Filename is metadata,
    # not semantics — deliberately excluded.
    EntityType.USER_ENTRY: ("title", "content", "processed_content"),
    # The four maps below are HOLLOW (registered in PLANNED_EMBEDDING_MAPS,
    # ruled keep 2026-08-29): they name what the report-tier and forms vectors
    # WILL carry once ADR-074's event/label/publish/subscribe quartet exists.
    # ENTRY_REPORT: was ("title", "content", "summary") — ``content`` and
    # ``summary`` exist on the model (inherited from Entity) but both writers
    # in EntryReportService populate ``processed_content`` and leave them at
    # their defaults, so the old map would have embedded the title alone. The
    # writer decides the field, not the dataclass.
    EntityType.ENTRY_REPORT: ("title", "processed_content"),
    # ACTIVITY_REPORT: ``processing_error`` is not content. ``annotation_mode``
    # discriminates additive commentary (``user_annotation``) from a sharing
    # replacement (``user_revision``) and a flat tuple cannot branch, so every
    # populated content field concatenates — as USER_ENTRY already does for
    # its raw/pipeline pair; in practice at most one annotation field is set.
    EntityType.ACTIVITY_REPORT: (
        "title",
        "description",
        "processed_content",
        "user_annotation",
        "user_revision",
    ),
    EntityType.FORM_TEMPLATE: ("title", "instructions", "description"),
    EntityType.FORM_SUBMISSION: ("title", "processed_content", "description"),
}


@overload
def build_embedding_text(entity_type: EntityType, source: dict[str, Any]) -> str: ...


@overload
def build_embedding_text(entity_type: EntityType, source: object) -> str: ...


def build_embedding_text(
    entity_type: EntityType,
    source: dict[str, Any] | object,
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
        'Learn Python\\nMaster the basics'

        >>> # From model (background worker)
        >>> task = Task(title="Learn Python", description="Master the basics")
        >>> build_embedding_text(EntityType.TASK, task)
        'Learn Python\\nMaster the basics'

        >>> # CURRICULUM uses double newlines
        >>> ku_data = {
        ...     "title": "Python",
        ...     "content": "A programming language",
        ...     "summary": "High-level",
        ... }
        >>> build_embedding_text(EntityType.PATH_STEP, ku_data)
        'Python\\n\\nA programming language\\n\\nHigh-level'

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

    # Curriculum and Resource types use double newlines for better semantic separation
    # (title, content blocks, summary are distinct concepts)
    _curriculum_types = {
        EntityType.PATH_STEP,
        EntityType.KU,
        EntityType.RESOURCE,
        EntityType.EXERCISE,
        EntityType.LEARNING_PATH,
        EntityType.REVISED_EXERCISE,
    }
    separator = "\n\n" if entity_type in _curriculum_types else "\n"
    return separator.join(parts)


def hash_embedding_text(text: str) -> str:
    """
    THE hash recipe for embedding-text identity (sha256 hex digest).

    Stored as ``embedding_text_hash`` next to every entity embedding (one
    writer: ``EmbeddingsService.store_embedding_with_metadata``) and compared
    BEFORE generation so unchanged text is never re-embedded — force
    re-ingests bump ``updated_at`` without changing content, and the hash is
    the content-truth signal the timestamp can't provide. Consumers of the
    comparison: the background worker's batch pre-check and the ``--stale``
    backfill's fine filter, both via
    ``EmbeddingsService.verify_fresh_embeddings`` — no third recipe.

    Hashes the FULL ``build_embedding_text`` output, deliberately independent
    of any provider's truncation budget: an edit past the truncation point
    re-embeds to an identical vector (rare, cheap) but the hash stays
    provider-agnostic. Version outranks hash — an ``EMBEDDING_VERSION`` bump
    re-embeds regardless of text equality (model migrations are never
    skipped).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_field_value(source: dict[str, Any] | object, field: str) -> Any:
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
