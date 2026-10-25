"""
Ingestion Package - Unified Content Ingestion for SKUEL
========================================================

The "hips" of SKUEL - stability through clarity.
Connects content (MD/YAML files) to the knowledge graph (Neo4j). Direction,
re-sync contract and the module map are stated once, in the
``unified_ingestion_service`` module docstring; authoring rules live in
``docs/patterns/UNIFIED_INGESTION_GUIDE.md``.

Usage:
    # The composition root builds the service over its two backends
    # (services_bootstrap/_backends.py: create_all_backends).
    service = UnifiedIngestionService(
        write_backend=backends["ingestion_write_backend"],
        bulk_backend=backends["bulk_upsert_backend"],
        default_user_uid=owner,
    )

    # Full ingestion (default, processes all files)
    result = await service.ingest_directory(Path("/vault"))

    # Incremental ingestion (skip unchanged files)
    result = await service.ingest_directory(
        Path("/vault"),
        ingestion_mode="incremental",  # or "smart" for mtime-first detection
        validate_targets=True,    # validate relationship UIDs exist
    )
"""

# Configuration
from .config import (
    DEFAULT_MAX_CONCURRENT_PARSING,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    ENTITY_CONFIGS,
    EntityIngestionConfig,
)

# Detector functions
from .detector import detect_entity_type, detect_format, is_edge_type

# Ingestion history
from .ingestion_history import IngestionHistoryEntry, IngestionHistoryService

# Ingestion tracking
from .ingestion_tracker import FileIngestionMetadata, IngestionDecision, IngestionTracker

# Parser functions (for direct use if needed)
from .parser import parse_markdown, parse_yaml

# Preparer functions
from .preparer import generate_uid, prepare_edge_data, prepare_entity_data

# Reference-book ingest door (canon journaling companion, Phase 2)
from .reference_ingestion import ReferenceIngestionService, ReferenceIngestReport

# Data types
from .types import (
    DirectoryValidationResult,
    IncrementalStats,
    IngestionError,
    IngestionStats,
    RelationshipValidationResult,
    ValidationResult,
)

# Primary service
from .unified_ingestion_service import UnifiedIngestionService

# Validator functions
from .validator import (
    validate_directory,
    validate_edge_data,
    validate_entity_data,
    validate_file,
    validate_relationship_targets,
    validate_required_fields,
)

__all__ = [
    # Configuration
    "DEFAULT_MAX_CONCURRENT_PARSING",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "ENTITY_CONFIGS",
    "EntityIngestionConfig",
    # Data types
    "DirectoryValidationResult",
    "IncrementalStats",
    "IngestionError",
    "IngestionStats",
    "RelationshipValidationResult",
    "ValidationResult",
    # Ingestion tracking
    "FileIngestionMetadata",
    "IngestionDecision",
    "IngestionTracker",
    # Ingestion history
    "IngestionHistoryEntry",
    "IngestionHistoryService",
    # Primary service
    "UnifiedIngestionService",
    # Reference-book ingest door
    "ReferenceIngestionService",
    "ReferenceIngestReport",
    # Detector
    "detect_entity_type",
    "detect_format",
    "is_edge_type",
    # Preparer
    "generate_uid",
    "prepare_edge_data",
    "prepare_entity_data",
    # Parser
    "parse_markdown",
    "parse_yaml",
    # Validator
    "validate_directory",
    "validate_edge_data",
    "validate_entity_data",
    "validate_file",
    "validate_relationship_targets",
    "validate_required_fields",
]
