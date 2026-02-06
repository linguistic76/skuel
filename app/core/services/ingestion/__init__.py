"""
Ingestion Package - Unified Content Ingestion for SKUEL
========================================================

The "hips" of SKUEL - stability through clarity.
Connects content (MD/YAML files) to the knowledge graph (Neo4j).

Architecture (January 2026):
- unified_ingestion_service.py - Orchestration (~250 lines)
- config.py - Entity configs and constants (~280 lines)
- types.py - Data classes (~200 lines)
- parser.py - MD/YAML parsing (~150 lines)
- detector.py - Format/type detection (~100 lines)
- preparer.py - Data preparation (~100 lines)
- validator.py - Validation pipeline (~550 lines)
- batch.py - Concurrent operations (~800 lines)
- sync_tracker.py - Incremental sync state (~300 lines)

Total: ~2,700 lines across 9 focused modules

Key Features (2026):
- Incremental sync: Skip unchanged files using content hash/mtime
- Relationship validation: Verify target UIDs exist before ingestion
- Progress reporting: Callback-based progress for large operations
- Configurable user UID: Via SKUEL_DEFAULT_USER_UID env var

Usage:
    from core.services.ingestion import UnifiedIngestionService

    service = UnifiedIngestionService(driver)

    # Full sync (default, processes all files)
    result = await service.ingest_directory(Path("/vault"))

    # Incremental sync (skip unchanged files)
    result = await service.ingest_directory(
        Path("/vault"),
        sync_mode="incremental",  # or "smart" for mtime-first detection
        validate_targets=True,    # validate relationship UIDs exist
    )
"""

# Configuration
from .config import (
    DEFAULT_MAX_CONCURRENT_PARSING,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_USER_UID,
    ENTITY_CONFIGS,
    EntityIngestionConfig,
)

# Detector functions
from .detector import detect_entity_type, detect_format

# Parser functions (for direct use if needed)
from .parser import parse_markdown, parse_yaml

# Preparer functions
from .preparer import generate_uid, normalize_uid, prepare_entity_data

# Progress tracking
from .progress_tracker import ProgressTracker

# Sync tracking
from .sync_history import SyncHistoryEntry, SyncHistoryService
from .sync_tracker import FileSyncMetadata, SyncDecision, SyncTracker

# Data types
from .types import (
    BundleStats,
    DirectoryValidationResult,
    DryRunPreview,
    IngestionError,
    IngestionStats,
    RelationshipValidationResult,
    SyncStats,
    ValidationResult,
)

# Primary service
from .unified_ingestion_service import UnifiedIngestionService

# Validator functions
from .validator import (
    validate_directory,
    validate_entity_data,
    validate_file,
    validate_relationship_targets,
    validate_required_fields,
)

__all__ = [
    # Configuration
    "DEFAULT_MAX_CONCURRENT_PARSING",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "DEFAULT_USER_UID",
    "ENTITY_CONFIGS",
    "EntityIngestionConfig",
    # Data types
    "BundleStats",
    "DirectoryValidationResult",
    "DryRunPreview",
    "IngestionError",
    "IngestionStats",
    "RelationshipValidationResult",
    "SyncStats",
    "ValidationResult",
    # Progress tracking
    "ProgressTracker",
    # Sync tracking
    "FileSyncMetadata",
    "SyncDecision",
    "SyncTracker",
    # Sync history
    "SyncHistoryEntry",
    "SyncHistoryService",
    # Primary service
    "UnifiedIngestionService",
    # Detector
    "detect_entity_type",
    "detect_format",
    # Preparer
    "generate_uid",
    "normalize_uid",
    "prepare_entity_data",
    # Parser
    "parse_markdown",
    "parse_yaml",
    # Validator
    "validate_directory",
    "validate_entity_data",
    "validate_file",
    "validate_relationship_targets",
    "validate_required_fields",
]
