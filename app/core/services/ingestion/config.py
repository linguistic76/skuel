"""
Ingestion Configuration - Entity Configs and Constants
=======================================================

Data-driven configuration for all entity types.
Defines required fields, relationship configs, and ingestion behavior.

Relationship configs are derived from the Relationship Registry
(core/models/relationship_registry.py) — the single source of truth
for all Neo4j edge definitions. See: ADR-026.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

import os
from dataclasses import dataclass
from typing import Any

from core.ingestion.bulk_ingestion import RelationshipConfig
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_registry import generate_ingestion_relationship_config

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

# Default user UID for entities without explicit user_uid
# Configurable via SKUEL_DEFAULT_USER_UID environment variable
DEFAULT_USER_UID = os.environ.get("SKUEL_DEFAULT_USER_UID", "user:system")


# ============================================================================
# ENTITY INGESTION CONFIGURATION
# ============================================================================


@dataclass
class EntityIngestionConfig:
    """Configuration for ingesting a specific entity type."""

    entity_label: str  # Neo4j label (e.g., "Entity", "Task")
    uid_prefix: str  # UID prefix (e.g., "ku", "task")
    relationship_config: dict[str, RelationshipConfig] | None = None
    required_fields: tuple[str, ...] = ()
    default_values: dict[str, Any] | None = None
    requires_user_uid: bool = False  # Whether this entity type needs user_uid for multi-tenancy


# ENTITY_CONFIGS — Ingestion Entity Configuration
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
    EntityType.KU: EntityIngestionConfig(
        entity_label="Entity",
        uid_prefix="ku",
        required_fields=("title", "content"),
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
        entity_label="Lp",
        uid_prefix="lp",
        required_fields=("name",),
        relationship_config=generate_ingestion_relationship_config(EntityType.LEARNING_PATH),
    ),
    EntityType.LEARNING_STEP: EntityIngestionConfig(
        entity_label="Ls",
        uid_prefix="ls",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.LEARNING_STEP),
    ),
    NonKuDomain.FINANCE: EntityIngestionConfig(
        entity_label="Expense",
        uid_prefix="expense",
        required_fields=("description", "amount"),
        requires_user_uid=True,
    ),
    # NOTE: Journal merged into Reports (February 2026).
    # Journal ingestion creates Entity nodes with ku_type="submission".
    # Kept as SUBMISSION entry — "journal" alias in TYPE_MAPPING resolves here.
    EntityType.SUBMISSION: EntityIngestionConfig(
        entity_label="Report",
        uid_prefix="report",
        required_fields=("title",),
        requires_user_uid=True,
    ),
    EntityType.LIFE_PATH: EntityIngestionConfig(
        entity_label="LifePath",
        uid_prefix="lifepath",
        required_fields=("user_uid",),
    ),
}


__all__ = [
    "DEFAULT_MAX_CONCURRENT_PARSING",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "DEFAULT_USER_UID",
    "ENTITY_CONFIGS",
    "EntityIngestionConfig",
]
