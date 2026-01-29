"""
Ingestion Preparer - Entity Data Preparation
=============================================

Handles UID generation, content extraction, default injection,
relationship data flattening, and embedding generation.

Extracted from unified_ingestion_service.py for separation of concerns.

NEO4J GENAI INTEGRATION (January 2026):
- Automatically generates embeddings for priority entities (Ku, Task, Goal, LpStep)
- Uses Neo4jGenAIEmbeddingsService if available
- Graceful degradation - ingestion works without embeddings
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from core.models.shared_enums import EntityType
from core.utils.logging import get_logger

from .config import ENTITY_CONFIGS

logger = get_logger("skuel.ingestion.preparer")


def normalize_uid(uid: str) -> str:
    """
    Normalize UID to dot notation.

    Converts colon notation to dot notation:
        "ku:machine-learning" → "ku.machine-learning"

    Args:
        uid: Raw UID from file

    Returns:
        Normalized UID with dot notation
    """
    return uid.replace(":", ".")


def generate_uid(entity_type: EntityType, file_path: Path) -> str:
    """
    Generate UID from entity type and file path.

    Pattern: {entity_type.value}.{file_stem}

    Args:
        entity_type: EntityType enum value
        file_path: Path to the file

    Returns:
        Generated UID (e.g., "ku.machine-learning")
    """
    return f"{entity_type.value}.{file_path.stem}"


async def prepare_entity_data_async(
    entity_type: EntityType,
    data: dict[str, Any],
    body: str | None,
    file_path: Path,
    default_user_uid: str = "user:system",
    embeddings_service: Any | None = None,
) -> dict[str, Any]:
    """
    Async version of prepare_entity_data with embedding generation.

    Handles:
    - UID generation/normalization
    - Content extraction (body for MD)
    - Default value injection
    - Relationship data flattening
    - Timestamp injection
    - Embedding generation (NEW - January 2026)

    Args:
        entity_type: EntityType enum value
        data: Parsed frontmatter/YAML data
        body: Body content (for markdown) or None
        file_path: Source file path
        default_user_uid: Default user UID for multi-tenant entities
        embeddings_service: Optional Neo4jGenAIEmbeddingsService for embedding generation

    Returns:
        Prepared entity data dict

    Raises:
        ValueError: If entity type is unknown
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        raise ValueError(f"Unknown entity type: {entity_type.value}")

    # Start with data copy
    entity_data = dict(data)

    # Remove YAML-only metadata fields
    for field in ("version", "type", "created_at", "updated_at"):
        entity_data.pop(field, None)

    # Handle UID
    if "uid" in entity_data:
        entity_data["uid"] = normalize_uid(entity_data["uid"])
    else:
        entity_data["uid"] = generate_uid(entity_type, file_path)

    # Handle content for markdown files (type-safe check)
    if body is not None and entity_type in (EntityType.KU, EntityType.JOURNAL):
        entity_data["content"] = body

    # Handle title fallback from filename
    if "title" not in entity_data and "name" not in entity_data:
        entity_data["title"] = file_path.stem.replace("-", " ").title()

    # Apply default values
    if config.default_values:
        for key, value in config.default_values.items():
            if key not in entity_data:
                entity_data[key] = value

    # Inject user_uid for multi-tenant entity types
    # Uses explicit user_uid from data if present, otherwise falls back to default
    if config.requires_user_uid and "user_uid" not in entity_data:
        entity_data["user_uid"] = default_user_uid

    # Flatten relationship data for BulkIngestionEngine
    # Format: "connections.requires" → flat key in metadata
    connections = entity_data.pop("connections", {})
    if connections:
        for key, value in connections.items():
            if value:
                entity_data[f"connections.{key}"] = value

    # Flatten contains/recommends for MOC
    contains = entity_data.pop("contains", {})
    if contains:
        for key, value in contains.items():
            if value:
                entity_data[f"contains.{key}"] = value

    recommends = entity_data.pop("recommends", {})
    if recommends:
        for key, value in recommends.items():
            if value:
                entity_data[f"recommends.{key}"] = value

    # Add timestamps
    now = datetime.now().isoformat()
    entity_data.setdefault("created_at", now)
    entity_data["updated_at"] = now

    # Generate embeddings (NEW - January 2026)
    # Priority entities: Ku, Task, Goal, LpStep - others don't need embeddings
    if embeddings_service and _should_generate_embedding(entity_type):
        embedding_text = _get_embedding_text(entity_type, entity_data)

        if embedding_text:
            try:
                embedding_result = await embeddings_service.create_embedding(
                    text=embedding_text,
                    metadata={"entity_type": entity_type.value, "uid": entity_data["uid"]},
                )

                if embedding_result.is_ok:
                    # Store as list for JSON compatibility (will be converted to tuple in domain model)
                    entity_data["embedding"] = embedding_result.value
                    entity_data["embedding_model"] = embeddings_service.model
                    entity_data["embedding_updated_at"] = now
                    logger.info(f"Generated embedding for {entity_data['uid']}")
                else:
                    logger.warning(
                        f"Failed to generate embedding for {entity_data['uid']}: "
                        f"{embedding_result.expect_error()}"
                    )
                    # Continue without embedding (graceful degradation)

            except Exception as e:
                logger.warning(f"Exception generating embedding for {entity_data['uid']}: {e}")
                # Continue without embedding (graceful degradation)

    return entity_data


def _should_generate_embedding(entity_type: EntityType) -> bool:
    """
    Determine if entity type should have embeddings.

    Priority entities for semantic search:
    - Ku: Substantial content (learning material)
    - All 6 Activity Domains: Tasks, Goals, Habits, Events, Choices, Principles

    Updated January 2026 to include all activity domains for complete semantic search coverage.
    """
    ACTIVITY_DOMAINS = [
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
    ]
    return entity_type == EntityType.KU or entity_type in ACTIVITY_DOMAINS


def _get_embedding_text(entity_type: EntityType, entity_data: dict[str, Any]) -> str:
    """
    Extract text for embedding generation.

    Combines relevant fields based on entity type to create
    a comprehensive representation for semantic search.

    Updated January 2026 to support all 6 activity domains.

    Args:
        entity_type: Type of entity
        entity_data: Entity data dict

    Returns:
        Combined text suitable for embedding
    """
    if entity_type == EntityType.KU:
        # Ku: title + content + summary
        parts = []
        if "title" in entity_data:
            parts.append(entity_data["title"])
        if "content" in entity_data:
            parts.append(entity_data["content"])
        if "summary" in entity_data:
            parts.append(entity_data["summary"])
        return "\n\n".join(parts).strip()

    elif entity_type in [EntityType.TASK, EntityType.GOAL]:
        # Task/Goal: title + description
        parts = []
        if "title" in entity_data:
            parts.append(entity_data["title"])
        if "description" in entity_data:
            parts.append(entity_data["description"])
        return "\n".join(parts).strip()

    elif entity_type == EntityType.HABIT:
        # Habit: title + description + trigger + reward
        parts = []
        for field in ["title", "description", "trigger", "reward"]:
            if field in entity_data and entity_data[field]:
                parts.append(str(entity_data[field]))
        return "\n".join(parts).strip()

    elif entity_type == EntityType.EVENT:
        # Event: title + description + location
        parts = []
        for field in ["title", "description", "location"]:
            if field in entity_data and entity_data[field]:
                parts.append(str(entity_data[field]))
        return "\n".join(parts).strip()

    elif entity_type == EntityType.CHOICE:
        # Choice: title + description + decision_context + outcome
        parts = []
        for field in ["title", "description", "decision_context", "outcome"]:
            if field in entity_data and entity_data[field]:
                parts.append(str(entity_data[field]))
        return "\n".join(parts).strip()

    elif entity_type == EntityType.PRINCIPLE:
        # Principle: name + statement + description
        parts = []
        for field in ["name", "statement", "description"]:
            if field in entity_data and entity_data[field]:
                parts.append(str(entity_data[field]))
        return "\n".join(parts).strip()

    return ""


def prepare_entity_data_sync(
    entity_type: EntityType,
    data: dict[str, Any],
    body: str | None,
    file_path: Path,
    default_user_uid: str = "user:system",
) -> dict[str, Any]:
    """
    Synchronous version of prepare_entity_data for batch operations.

    Does NOT generate embeddings - use async version for embedding generation.
    This version is used in thread pool operations where async is not available.

    See prepare_entity_data() for full documentation.
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        raise ValueError(f"Unknown entity type: {entity_type.value}")

    # Start with data copy
    entity_data = dict(data)

    # Remove YAML-only metadata fields
    for field in ("version", "type", "created_at", "updated_at"):
        entity_data.pop(field, None)

    # Handle UID
    if "uid" in entity_data:
        entity_data["uid"] = normalize_uid(entity_data["uid"])
    else:
        entity_data["uid"] = generate_uid(entity_type, file_path)

    # Handle content for markdown files
    if body is not None and entity_type in (EntityType.KU, EntityType.JOURNAL):
        entity_data["content"] = body

    # Handle title fallback from filename
    if "title" not in entity_data and "name" not in entity_data:
        entity_data["title"] = file_path.stem.replace("-", " ").title()

    # Apply default values
    if config.default_values:
        for key, value in config.default_values.items():
            if key not in entity_data:
                entity_data[key] = value

    # Inject user_uid for multi-tenant entity types
    if config.requires_user_uid and "user_uid" not in entity_data:
        entity_data["user_uid"] = default_user_uid

    # Flatten relationship data
    connections = entity_data.pop("connections", {})
    if connections:
        for key, value in connections.items():
            if value:
                entity_data[f"connections.{key}"] = value

    contains = entity_data.pop("contains", {})
    if contains:
        for key, value in contains.items():
            if value:
                entity_data[f"contains.{key}"] = value

    recommends = entity_data.pop("recommends", {})
    if recommends:
        for key, value in recommends.items():
            if value:
                entity_data[f"recommends.{key}"] = value

    # Add timestamps
    now = datetime.now().isoformat()
    entity_data.setdefault("created_at", now)
    entity_data["updated_at"] = now

    return entity_data


# Alias for backward compatibility with batch operations
prepare_entity_data = prepare_entity_data_sync


__all__ = [
    "generate_uid",
    "normalize_uid",
    "prepare_entity_data",
    "prepare_entity_data_sync",
    "prepare_entity_data_async",
]
