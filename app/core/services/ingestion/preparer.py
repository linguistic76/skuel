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

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.utils.embedding_text_builder import build_embedding_text
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


def generate_uid(entity_type: EntityType | NonKuDomain, file_path: Path) -> str:
    """
    Generate UID from entity type and file path.

    Pattern: {uid_prefix}.{file_stem}

    Uses uid_prefix from ENTITY_CONFIGS (e.g., "ku" for CURRICULUM, not "curriculum").
    This preserves stable UID formats regardless of enum value changes.

    Args:
        entity_type: EntityType | NonKuDomain enum value
        file_path: Path to the file

    Returns:
        Generated UID (e.g., "ku.machine-learning")
    """
    from core.services.ingestion.config import ENTITY_CONFIGS

    config = ENTITY_CONFIGS.get(entity_type)
    prefix = config.uid_prefix if config else entity_type.value
    return f"{prefix}.{file_path.stem}"


async def prepare_entity_data_async(
    entity_type: EntityType | NonKuDomain,
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
        entity_type: EntityType | NonKuDomain enum value
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
    if body is not None and entity_type in (EntityType.ARTICLE, EntityType.SUBMISSION):
        entity_data["content"] = body

    # Article: normalize USES_KU UIDs
    if entity_type == EntityType.ARTICLE:
        if "uses_kus" in entity_data and isinstance(entity_data["uses_kus"], list):
            entity_data["uses_kus"] = [normalize_uid(uid) for uid in entity_data["uses_kus"]]

    # Learning Step: normalize relationship fields
    if entity_type == EntityType.LEARNING_STEP:
        # Convert single learning_path_uid to list
        lp_uid = entity_data.pop("learning_path_uid", None)
        if lp_uid:
            entity_data["learning_path_uids"] = [normalize_uid(lp_uid)]

        # Merge knowledge_uid (single) into primary_knowledge_uids (list)
        knowledge_uid = entity_data.pop("knowledge_uid", None)
        if knowledge_uid:
            normalized = normalize_uid(knowledge_uid)
            existing = [normalize_uid(u) for u in entity_data.get("primary_knowledge_uids", [])]
            if normalized not in existing:
                entity_data.setdefault("primary_knowledge_uids", []).insert(0, normalized)

        # Normalize UIDs in all relationship list fields
        uid_list_fields = [
            "primary_knowledge_uids",
            "supporting_knowledge_uids",
            "trains_ku_uids",
            "prerequisite_step_uids",
            "prerequisite_knowledge_uids",
            "principle_uids",
            "choice_uids",
            "habit_uids",
            "task_uids",
            "event_template_uids",
            "learning_path_uids",
        ]
        for field in uid_list_fields:
            if field in entity_data and isinstance(entity_data[field], list):
                entity_data[field] = [normalize_uid(uid) for uid in entity_data[field]]

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

    # Flatten contains/recommends for organizing KUs
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
        embedding_text = build_embedding_text(entity_type, entity_data)

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


def _should_generate_embedding(entity_type: EntityType | NonKuDomain) -> bool:
    """
    Determine if entity type should have embeddings.

    Priority entities for semantic search:
    - Ku: Substantial content (learning material)
    - All 6 Activity Domains: Tasks, Goals, Habits, Events, Choices, Principles

    Updated January 2026 to include all activity domains for complete semantic search coverage.
    """
    activity_domains = [
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
    ]
    return entity_type in (EntityType.ARTICLE, EntityType.KU) or entity_type in activity_domains


def prepare_entity_data_sync(
    entity_type: EntityType | NonKuDomain,
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
    if body is not None and entity_type in (EntityType.ARTICLE, EntityType.SUBMISSION):
        entity_data["content"] = body

    # Article: normalize USES_KU UIDs
    if entity_type == EntityType.ARTICLE:
        if "uses_kus" in entity_data and isinstance(entity_data["uses_kus"], list):
            entity_data["uses_kus"] = [normalize_uid(uid) for uid in entity_data["uses_kus"]]

    # Learning Step: normalize relationship fields
    if entity_type == EntityType.LEARNING_STEP:
        # Convert single learning_path_uid to list
        lp_uid = entity_data.pop("learning_path_uid", None)
        if lp_uid:
            entity_data["learning_path_uids"] = [normalize_uid(lp_uid)]

        # Merge knowledge_uid (single) into primary_knowledge_uids (list)
        knowledge_uid = entity_data.pop("knowledge_uid", None)
        if knowledge_uid:
            normalized = normalize_uid(knowledge_uid)
            existing = [normalize_uid(u) for u in entity_data.get("primary_knowledge_uids", [])]
            if normalized not in existing:
                entity_data.setdefault("primary_knowledge_uids", []).insert(0, normalized)

        # Normalize UIDs in all relationship list fields
        uid_list_fields = [
            "primary_knowledge_uids",
            "supporting_knowledge_uids",
            "trains_ku_uids",
            "prerequisite_step_uids",
            "prerequisite_knowledge_uids",
            "principle_uids",
            "choice_uids",
            "habit_uids",
            "task_uids",
            "event_template_uids",
            "learning_path_uids",
        ]
        for field in uid_list_fields:
            if field in entity_data and isinstance(entity_data[field], list):
                entity_data[field] = [normalize_uid(uid) for uid in entity_data[field]]

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


def prepare_edge_data(
    data: dict[str, Any],
    file_path: Path | None = None,
) -> dict[str, Any]:
    """
    Prepare edge data for ingestion into Neo4j.

    Normalizes from/to UIDs and extracts evidence properties.

    Args:
        data: Parsed edge YAML data (already validated)
        file_path: Optional source file path for provenance

    Returns:
        Dict with from_uid, to_uid, relationship, and evidence properties
    """
    now = datetime.now().isoformat()

    edge_data: dict[str, Any] = {
        "from_uid": normalize_uid(data["from"]),
        "to_uid": normalize_uid(data["to"]),
        "relationship": data["relationship"],
    }

    # Evidence properties (stored on the relationship edge)
    props: dict[str, Any] = {
        "created_at": now,
        "updated_at": now,
    }

    # Optional evidence fields
    for field in ("evidence", "confidence", "polarity", "temporality", "source", "observed_at"):
        if field in data and data[field] is not None:
            props[field] = data[field]

    if "tags" in data and isinstance(data["tags"], list):
        props["tags"] = data["tags"]

    if file_path:
        props["source_file"] = str(file_path)

    edge_data["properties"] = props
    return edge_data


__all__ = [
    "generate_uid",
    "normalize_uid",
    "prepare_edge_data",
    "prepare_entity_data",
    "prepare_entity_data_sync",
    "prepare_entity_data_async",
]
