"""
Ingestion Configuration - Entity Configs and Constants
=======================================================

Data-driven configuration for all 14 entity types.
Defines required fields, relationship configs, and ingestion behavior.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

import os
from dataclasses import dataclass
from typing import Any

from core.ingestion.bulk_ingestion import RelationshipConfig
from core.models.relationship_names import RelationshipName
from core.models.shared_enums import EntityType

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

    entity_label: str  # Neo4j label (e.g., "Ku", "Task")
    uid_prefix: str  # UID prefix (e.g., "ku", "task")
    relationship_config: dict[str, RelationshipConfig] | None = None
    required_fields: tuple[str, ...] = ()
    default_values: dict[str, Any] | None = None
    requires_user_uid: bool = False  # Whether this entity type needs user_uid for multi-tenancy


# Entity configurations for all supported types
# Uses EntityType enum for type-safe keys
#
# NOTE: relationship_config uses dict literals that satisfy RelationshipConfig TypedDict
# via structural typing. Each inner dict must have: rel_type, target_label, direction
# See: core/ingestion/bulk_ingestion.py::RelationshipConfig for TypedDict definition
ENTITY_CONFIGS: dict[EntityType, EntityIngestionConfig] = {
    EntityType.KU: EntityIngestionConfig(
        entity_label="Ku",
        uid_prefix="ku",
        required_fields=("title", "content"),
        relationship_config={
            "connections.requires": RelationshipConfig(
                rel_type=RelationshipName.PREREQUISITE.value,
                target_label="Ku",
                direction="incoming",
            ),
            "connections.enables": RelationshipConfig(
                rel_type=RelationshipName.ENABLES.value,
                target_label="Ku",
                direction="outgoing",
            ),
            "connections.related": RelationshipConfig(
                rel_type="RELATED_TO",
                target_label="Ku",
                direction="outgoing",
            ),
        },
    ),
    EntityType.MOC: EntityIngestionConfig(
        entity_label="Moc",
        uid_prefix="moc",
        required_fields=("title",),
        relationship_config={
            "contains.knowledge": RelationshipConfig(
                rel_type="CONTAINS_KNOWLEDGE",
                target_label="Ku",
                direction="outgoing",
            ),
            "contains.paths": RelationshipConfig(
                rel_type="CONTAINS_PATH",
                target_label="Lp",
                direction="outgoing",
            ),
            "contains.principles": RelationshipConfig(
                rel_type="CONTAINS_PRINCIPLE",
                target_label="Principle",
                direction="outgoing",
            ),
            "related_mocs": RelationshipConfig(
                rel_type="RELATED_TO_MOC",
                target_label="Moc",
                direction="outgoing",
            ),
        },
    ),
    EntityType.TASK: EntityIngestionConfig(
        entity_label="Task",
        uid_prefix="task",
        required_fields=("title",),
        requires_user_uid=True,  # Activity domain - user-owned
        relationship_config={
            "connections.depends_on": RelationshipConfig(
                rel_type=RelationshipName.DEPENDS_ON.value,
                target_label="Task",
                direction="outgoing",
            ),
            "connections.applies_knowledge": RelationshipConfig(
                rel_type=RelationshipName.APPLIES_KNOWLEDGE.value,
                target_label="Ku",
                direction="outgoing",
            ),
            "connections.fulfills_goal": RelationshipConfig(
                rel_type=RelationshipName.FULFILLS_GOAL.value,
                target_label="Goal",
                direction="outgoing",
            ),
        },
    ),
    EntityType.GOAL: EntityIngestionConfig(
        entity_label="Goal",
        uid_prefix="goal",
        required_fields=("title",),
        requires_user_uid=True,  # Activity domain - user-owned
        relationship_config={
            "connections.requires_knowledge": RelationshipConfig(
                rel_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
                target_label="Ku",
                direction="outgoing",
            ),
            "connections.aligned_with_principle": RelationshipConfig(
                rel_type=RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                target_label="Principle",
                direction="outgoing",
            ),
        },
    ),
    EntityType.HABIT: EntityIngestionConfig(
        entity_label="Habit",
        uid_prefix="habit",
        required_fields=("title",),
        requires_user_uid=True,  # Activity domain - user-owned
        relationship_config={
            "connections.reinforces_knowledge": RelationshipConfig(
                rel_type=RelationshipName.REINFORCES_KNOWLEDGE.value,
                target_label="Ku",
                direction="outgoing",
            ),
            "connections.supports_goal": RelationshipConfig(
                rel_type=RelationshipName.SUPPORTS_GOAL.value,
                target_label="Goal",
                direction="outgoing",
            ),
        },
    ),
    EntityType.EVENT: EntityIngestionConfig(
        entity_label="Event",
        uid_prefix="event",
        required_fields=("title",),
        requires_user_uid=True,  # Activity domain - user-owned
        relationship_config={
            "connections.applies_knowledge": RelationshipConfig(
                rel_type=RelationshipName.APPLIES_KNOWLEDGE.value,
                target_label="Ku",
                direction="outgoing",
            ),
        },
    ),
    EntityType.CHOICE: EntityIngestionConfig(
        entity_label="Choice",
        uid_prefix="choice",
        required_fields=("title",),
        requires_user_uid=True,  # Activity domain - user-owned
        relationship_config={
            "connections.guided_by_principle": RelationshipConfig(
                rel_type="GUIDED_BY_PRINCIPLE",
                target_label="Principle",
                direction="outgoing",
            ),
        },
    ),
    EntityType.PRINCIPLE: EntityIngestionConfig(
        entity_label="Principle",
        uid_prefix="principle",
        required_fields=("name", "statement"),
        requires_user_uid=True,  # Activity domain - user-owned
        relationship_config={
            "connections.guides_goal": RelationshipConfig(
                rel_type=RelationshipName.GUIDES_GOAL.value,
                target_label="Goal",
                direction="outgoing",
            ),
            "connections.inspires_habit": RelationshipConfig(
                rel_type="INSPIRES_HABIT",
                target_label="Habit",
                direction="outgoing",
            ),
        },
    ),
    EntityType.LP: EntityIngestionConfig(
        entity_label="Lp",
        uid_prefix="lp",
        required_fields=("name",),
        relationship_config={
            "connections.contains_steps": RelationshipConfig(
                rel_type="CONTAINS_STEP",
                target_label="Ls",
                direction="outgoing",
            ),
        },
    ),
    EntityType.LS: EntityIngestionConfig(
        entity_label="Ls",
        uid_prefix="ls",
        required_fields=("title",),
        relationship_config={
            "connections.teaches_knowledge": RelationshipConfig(
                rel_type="TEACHES_KNOWLEDGE",
                target_label="Ku",
                direction="outgoing",
            ),
        },
    ),
    EntityType.FINANCE: EntityIngestionConfig(
        entity_label="Expense",
        uid_prefix="expense",
        required_fields=("description", "amount"),
        requires_user_uid=True,  # Finance domain - user-owned
    ),
    # NOTE: EntityType.JOURNAL maps to REPORT via get_canonical() (February 2026)
    # Journal ingestion creates Report nodes with report_type="journal"
    EntityType.JOURNAL: EntityIngestionConfig(
        entity_label="Report",
        uid_prefix="report",
        required_fields=("content",),
        requires_user_uid=True,  # Content/Processing domain - user-owned
    ),
    EntityType.REPORT: EntityIngestionConfig(
        entity_label="Report",
        uid_prefix="report",
        required_fields=("title",),
        requires_user_uid=True,  # Content/Processing domain - user-owned
    ),
    EntityType.LIFEPATH: EntityIngestionConfig(
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
