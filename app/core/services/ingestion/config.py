"""
Ingestion Configuration - Entity Configs and Constants
=======================================================

Data-driven configuration for all entity types.
Defines required fields, relationship configs, and ingestion behavior.

Relationship configs are derived from the Relationship Registry
(core/models/relationship_registry.py) — the single source of truth
for all Neo4j edge definitions. See: ADR-026.

The ``generate_ingestion_relationship_config`` translation function lives
here (not in the registry) to keep the model layer free of ingestion concerns.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.constants import SYSTEM_USER_UID
from core.ingestion.bulk_ingestion import RelationshipConfig
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_registry import (
    ENTITY_TYPE_TO_LABEL,
    LABEL_CONFIGS,
    LABEL_TO_DEFAULT_ENTITY_TYPE,
)
from core.models.type_hints import UserUID

# ============================================================================
# FILE SIZE LIMITS
# ============================================================================

# Default maximum file size: 10 MB
# Prevents OOM on very large files
DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# ============================================================================
# CONCURRENCY LIMITS
# ============================================================================

# Default max concurrent file parsing operations
# Balances parallelism with resource usage (file handles, memory)
DEFAULT_MAX_CONCURRENT_PARSING = 20

# ============================================================================
# USER CONFIGURATION
# ============================================================================

# Default user UID for entities without explicit user_uid.
# Configurable via SKUEL_DEFAULT_USER_UID; defaults to the canonical SYSTEM_USER_UID
# (`user_system`). Must stay canonical (`user_<name>`) — the ingestion boundary rejects
# non-canonical owners. See core.constants.SYSTEM_USER_UID.
DEFAULT_USER_UID: UserUID = UserUID(os.environ.get("SKUEL_DEFAULT_USER_UID", SYSTEM_USER_UID))


# ============================================================================
# INGESTION RELATIONSHIP CONFIG GENERATION
# ============================================================================


def generate_ingestion_relationship_config(
    entity_type: EntityType,
) -> dict[str, RelationshipConfig] | None:
    """
    Generate ingestion relationship config from the registry (single source of truth).

    Extracts UnifiedRelationshipDefinitions that have yaml_field_path set,
    filtered by entity_type for disambiguation when multiple EntityTypes share a label.

    Args:
        entity_type: The EntityType to generate config for

    Returns:
        Dict mapping yaml_field_path -> RelationshipConfig, or None if no relationships.
        Each value is a TypedDict with rel_type, target_label, direction.

    See: /docs/decisions/ADR-026-unified-relationship-registry.md
    """
    entity_label = ENTITY_TYPE_TO_LABEL.get(entity_type)
    if not entity_label:
        return None

    config = LABEL_CONFIGS.get(entity_label)
    if not config:
        return None

    default_type = LABEL_TO_DEFAULT_ENTITY_TYPE.get(entity_label)
    result: dict[str, RelationshipConfig] = {}

    for rel in config.relationships:
        if rel.yaml_field_path is None:
            continue

        # Filter by ingestion_entity_type:
        # - If set, only include for that specific EntityType
        # - If None, only include for the default EntityType for the label
        if rel.ingestion_entity_type is not None:
            if rel.ingestion_entity_type != entity_type:
                continue
        elif entity_type != default_type:
            continue

        result[rel.yaml_field_path] = RelationshipConfig(
            rel_type=rel.relationship.value,
            target_label=rel.target_label,
            direction=rel.direction,  # type: ignore[typeddict-item]  # str validated at definition
        )

    return result if result else None


# ============================================================================
# ENTITY INGESTION CONFIGURATION
# ============================================================================


@dataclass
class EntityIngestionConfig:
    """Configuration for ingesting a specific entity type."""

    entity_label: str  # Neo4j domain label (e.g., "PathStep", "Task")
    uid_prefix: str  # UID prefix (e.g., "ku", "task")
    relationship_config: dict[str, RelationshipConfig] | None = None
    required_fields: tuple[str, ...] = ()
    default_values: dict[str, Any] | None = None
    requires_user_uid: bool = False  # Whether this entity type needs user_uid for multi-tenancy
    base_label: str | None = (
        "Entity"  # Multi-label base (e.g., :Entity:Task). None for non-Entity types.
    )


# ENTITY_CONFIGS — Ingestion Entity Configuration
#
# 12 of 20 entity types are file-ingestible. The following are excluded:
#   - REVISED_EXERCISE: Created via API as part of the feedback loop
#   - RESOURCE: Created via API with curated metadata
#   - FORM_TEMPLATE: Created via API by admins
#   - FORM_SUBMISSION: Created via API by users
#   - USER_ENTRY: Ingestible; legacy ``je_input``/``exercise_submission``
#     type strings alias to USER_ENTRY with pipeline inferred (ADR-054).
#   - EXERCISE_REPORT/ACTIVITY_REPORT: Created via report generation pipeline
#
# Relationship configs are derived from the Relationship Registry via
# generate_ingestion_relationship_config(). Only entries with yaml_field_path
# set in the registry generate ingestion relationships.
#
# Note: generate_ingestion_relationship_config() takes EntityType.
# NonKuDomain entries (FINANCE, GROUP) have no relationship configs.
#
# See: core/models/relationship_registry.py (single source of truth)
# See: /docs/decisions/ADR-026-unified-relationship-registry.md
ENTITY_CONFIGS: dict[EntityType | NonKuDomain, EntityIngestionConfig] = {
    EntityType.EXERCISE: EntityIngestionConfig(
        entity_label="Exercise",
        uid_prefix="ex",
        required_fields=("title", "instructions"),
        relationship_config=generate_ingestion_relationship_config(EntityType.EXERCISE),
    ),
    EntityType.KU: EntityIngestionConfig(
        entity_label="Ku",
        uid_prefix="ku",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.KU),
    ),
    EntityType.TASK: EntityIngestionConfig(
        entity_label="Task",
        uid_prefix="task",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.TASK),
    ),
    EntityType.GOAL: EntityIngestionConfig(
        entity_label="Goal",
        uid_prefix="goal",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.GOAL),
    ),
    EntityType.HABIT: EntityIngestionConfig(
        entity_label="Habit",
        uid_prefix="habit",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.HABIT),
    ),
    EntityType.EVENT: EntityIngestionConfig(
        entity_label="Event",
        uid_prefix="event",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.EVENT),
    ),
    EntityType.CHOICE: EntityIngestionConfig(
        entity_label="Choice",
        uid_prefix="choice",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.CHOICE),
    ),
    EntityType.PRINCIPLE: EntityIngestionConfig(
        entity_label="Principle",
        uid_prefix="principle",
        required_fields=("name", "statement"),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.PRINCIPLE),
    ),
    EntityType.LEARNING_PATH: EntityIngestionConfig(
        entity_label="LearningPath",
        uid_prefix="lp",
        required_fields=("name",),
        relationship_config=generate_ingestion_relationship_config(EntityType.LEARNING_PATH),
    ),
    EntityType.PATH_STEP: EntityIngestionConfig(
        entity_label="PathStep",
        uid_prefix="ps",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.PATH_STEP),
    ),
    NonKuDomain.FINANCE: EntityIngestionConfig(
        entity_label="Expense",
        uid_prefix="expense",
        required_fields=("description", "amount"),
        requires_user_uid=True,
        base_label=None,  # Expense is not an Entity type
    ),
    NonKuDomain.GROUP: EntityIngestionConfig(
        entity_label="Group",
        uid_prefix="group",
        required_fields=("name",),
        requires_user_uid=True,  # Upload user becomes owner_uid (see preparer)
        base_label=None,  # Group is not an Entity type
    ),
    EntityType.USER_ENTRY: EntityIngestionConfig(
        entity_label="UserEntry",
        uid_prefix="ue",
        required_fields=("title",),
        requires_user_uid=True,
    ),
    EntityType.INTERACTION: EntityIngestionConfig(
        entity_label="Interaction",
        uid_prefix="ia",
        required_fields=("interaction_type", "target_uid"),
        requires_user_uid=True,
        # No YAML-driven relationships — context relationships are created
        # programmatically by InteractionService.create_interaction().
    ),
    EntityType.LIFE_PATH: EntityIngestionConfig(
        entity_label="LifePath",
        uid_prefix="lifepath",
        required_fields=("user_uid",),
    ),
}


# ============================================================================
# FILE COLLECTION
# ============================================================================


def _file_mtime(path: Path) -> float:
    """Get file modification time for sorting."""
    return path.stat().st_mtime


def collect_files(directory: Path, pattern: str = "*") -> list[Path]:
    """
    Collect all supported files (MD, YAML, YML) from a directory.

    Simplifies pattern matching with clear semantics:
    - "*" or "**/*" -> all supported files recursively
    - "*.md" -> only markdown files recursively
    - "specific-name" -> files with that exact stem

    Args:
        directory: Directory to search
        pattern: Glob pattern (default "*" for all files)

    Returns:
        List of file paths sorted by modification time (newest first)
    """
    all_files: list[Path] = []

    if pattern in ("*", "**/*"):
        all_files.extend(directory.glob("**/*.md"))
        all_files.extend(directory.glob("**/*.yaml"))
        all_files.extend(directory.glob("**/*.yml"))
    elif pattern.endswith(".md") or pattern.endswith((".yaml", ".yml")):
        all_files.extend(directory.glob(f"**/{pattern}"))
    else:
        all_files.extend(directory.glob(f"**/{pattern}.md"))
        all_files.extend(directory.glob(f"**/{pattern}.yaml"))
        all_files.extend(directory.glob(f"**/{pattern}.yml"))

    return sorted(all_files, key=_file_mtime, reverse=True)


__all__ = [
    "DEFAULT_MAX_CONCURRENT_PARSING",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "DEFAULT_USER_UID",
    "ENTITY_CONFIGS",
    "EntityIngestionConfig",
    "collect_files",
    "generate_ingestion_relationship_config",
]
