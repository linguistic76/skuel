"""
Unified Ingestion Service - Orchestration Layer
================================================

**REFACTORED (January 2026):** Decomposed from 1,916 lines to ~250 lines.

This module orchestrates content ingestion by composing:
- config.py - Entity configurations and constants
- types.py - Data classes (IngestionStats, ValidationResult, etc.)
- parser.py - MD/YAML file parsing
- detector.py - Format and entity type detection
- preparer.py - Entity data preparation
- validator.py - Validation pipeline
- batch.py - Concurrent batch operations

Architecture:
- Orchestrator stays small (~250 lines), delegates everything
- Each module has ONE job (separation of concerns)
- Clear data flow: Parse → Detect → Validate → Prepare → Ingest

Key Design Decisions (ADR-014):
- Format Support: Both MD + YAML as first-class citizens
- Architecture: Single unified service (one path forward)
- UID Format: Dot notation (`ku.filename`) - normalized from colon format
- Performance: BulkIngestionEngine for batch operations (10-100x faster)

See: /docs/decisions/ADR-014-unified-ingestion.md
"""

__version__ = "2.0"

from pathlib import Path
from typing import Any, Literal

from neo4j import AsyncDriver

from core.ingestion.bulk_ingestion import BulkIngestionEngine
from core.models.enums import EntityType
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .batch import ProgressCallback, find_entity_file, ingest_bundle, ingest_directory, ingest_vault
from .config import DEFAULT_MAX_FILE_SIZE_BYTES, DEFAULT_USER_UID, ENTITY_CONFIGS
from .detector import detect_entity_type, detect_format
from .parser import check_file_size, parse_markdown, parse_yaml
from .preparer import generate_uid, normalize_uid, prepare_entity_data
from .types import BundleStats, DryRunPreview, IncrementalStats, IngestionStats
from .validator import (
    validate_directory,
    validate_entity_data,
    validate_file,
    validate_required_fields,
)

logger = get_logger("skuel.services.unified_ingestion")


class UnifiedIngestionService:
    """
    Unified service for ingesting content from both MD and YAML formats.

    Orchestrates capabilities from decomposed modules:
    - Auto-detects file format (MD vs YAML)
    - Routes to appropriate entity type (14 types)
    - Normalizes UIDs to dot notation
    - Uses BulkIngestionEngine for batch performance
    - Creates graph-native relationships

    Usage:
        service = UnifiedIngestionService(driver)

        # Single file
        result = await service.ingest_file(Path("ku.machine-learning.md"))

        # Directory
        result = await service.ingest_directory(Path("/docs"))

        # Vault
        result = await service.ingest_vault(Path("/vault"), subdirs=["docs", "notes"])

        # Bundle
        result = await service.ingest_bundle(Path("/bundles/mindfulness"))
    """

    def __init__(
        self,
        driver: AsyncDriver,
        default_user_uid: str | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        embeddings_service: Any | None = None,
        chunking_service: Any | None = None,
    ) -> None:
        """
        Initialize unified ingestion service.

        Args:
            driver: Neo4j async driver
            default_user_uid: Default user UID for entities without explicit user_uid.
                              If not provided, uses SKUEL_DEFAULT_USER_UID env var or "user:system".
            max_file_size_bytes: Maximum file size in bytes (default: 10 MB).
                                 Files larger than this will be rejected to prevent OOM.
            embeddings_service: Optional Neo4jGenAIEmbeddingsService for embedding generation.
                                If not provided, ingestion works without embeddings (graceful degradation).
            chunking_service: Optional KuChunkingService for automatic chunk generation.
                              If not provided, ingestion works without chunking (graceful degradation).
        """
        if not driver:
            raise ValueError("Neo4j driver is required")

        self.driver = driver
        self.default_user_uid = (
            default_user_uid if default_user_uid is not None else DEFAULT_USER_UID
        )
        self.max_file_size_bytes = max_file_size_bytes
        self.embeddings = embeddings_service  # Can be None - graceful degradation
        self.chunking = chunking_service  # Can be None - graceful degradation
        self.logger = logger

        # Log embedding availability
        if self.embeddings:
            self.logger.info(
                "✅ Embeddings service available - will generate embeddings during ingestion"
            )
        else:
            self.logger.warning(
                "⚠️ Embeddings service not available - ingestion will work without embeddings"
            )

        # Log chunking availability
        if self.chunking:
            self.logger.info(
                "✅ Chunking service available - will generate chunks during KU ingestion"
            )
        else:
            self.logger.warning(
                "⚠️ Chunking service not available - KU ingestion will work without chunks"
            )

        # Lazy-initialized engines per entity type (keyed by EntityType)
        self._engines: dict[EntityType, BulkIngestionEngine[Any]] = {}

    def _get_engine(self, entity_type: EntityType) -> BulkIngestionEngine[Any]:
        """Get or create a BulkIngestionEngine for the entity type."""
        if entity_type not in self._engines:
            config = ENTITY_CONFIGS.get(entity_type)
            if not config:
                raise ValueError(f"Unknown entity type: {entity_type}")

            # Create engine with placeholder type (BulkIngestionEngine uses dict internally)
            self._engines[entity_type] = BulkIngestionEngine(
                driver=self.driver,
                entity_type=dict,  # Engines work with dicts
                entity_label=config.entity_label,
            )
        return self._engines[entity_type]

    # ========================================================================
    # DELEGATED METHODS (for backward compatibility)
    # ========================================================================

    def normalize_uid(self, uid: str) -> str:
        """Normalize UID to dot notation. Delegates to preparer module."""
        return normalize_uid(uid)

    def generate_uid(self, entity_type: EntityType, file_path: Path) -> str:
        """Generate UID from entity type and file path. Delegates to preparer module."""
        return generate_uid(entity_type, file_path)

    def detect_format(self, file_path: Path) -> str:
        """Detect file format from extension. Delegates to detector module."""
        return detect_format(file_path)

    def detect_entity_type(self, data: dict[str, Any], file_path: Path) -> EntityType:
        """Detect entity type from file content. Delegates to detector module."""
        return detect_entity_type(data, file_path)

    def parse_markdown(self, file_path: Path) -> Result[tuple[dict[str, Any], str]]:
        """Parse markdown file. Delegates to parser module."""
        return parse_markdown(file_path, self.max_file_size_bytes)

    def validate_required_fields(
        self,
        entity_type: EntityType,
        data: dict[str, Any],
        file_path: Path,
    ) -> Result[None]:
        """Validate required fields before preparation. Delegates to validator module."""
        return validate_required_fields(entity_type, data, file_path)

    def validate_entity_data(
        self,
        entity_type: EntityType,
        entity_data: dict[str, Any],
        file_path: Path,
    ) -> Result[None]:
        """Validate entity data after preparation. Delegates to validator module."""
        return validate_entity_data(entity_type, entity_data, file_path)

    def prepare_entity_data(
        self,
        entity_type: EntityType,
        data: dict[str, Any],
        body: str | None,
        file_path: Path,
    ) -> dict[str, Any]:
        """Prepare entity data for ingestion. Delegates to preparer module."""
        return prepare_entity_data(entity_type, data, body, file_path, self.default_user_uid)

    def parse_yaml(self, file_path: Path) -> Result[dict[str, Any]]:
        """Parse YAML file. Delegates to parser module."""
        return parse_yaml(file_path, self.max_file_size_bytes)

    def check_file_size(self, file_path: Path) -> Result[None]:
        """Check if file size is within limits. Delegates to parser module."""
        return check_file_size(file_path, self.max_file_size_bytes)

    # ========================================================================
    # SINGLE FILE INGESTION
    # ========================================================================

    @with_error_handling("ingest_file", error_type="system")
    async def ingest_file(self, file_path: Path) -> Result[dict[str, Any]]:
        """
        Ingest a single file (MD or YAML) into Neo4j.

        Auto-detects format and entity type, normalizes UID,
        and persists using BulkIngestionEngine.

        Args:
            file_path: Path to file to ingest

        Returns:
            Result with ingestion details including uid, title, entity_type
        """
        if not file_path.exists():
            return Result.fail(Errors.not_found(f"File not found: {file_path}"))

        # Detect format
        file_format = detect_format(file_path)

        # Parse file
        if file_format == "markdown":
            parse_result = parse_markdown(file_path, self.max_file_size_bytes)
            if parse_result.is_error:
                return Result.fail(parse_result.expect_error())
            data, body = parse_result.value
        else:  # yaml
            parse_result = parse_yaml(file_path, self.max_file_size_bytes)
            if parse_result.is_error:
                return Result.fail(parse_result.expect_error())
            data = parse_result.value
            body = None

        # Detect entity type (returns EntityType enum - type-safe!)
        entity_type = detect_entity_type(data, file_path)
        config = ENTITY_CONFIGS.get(entity_type)
        if not config:
            return Result.fail(
                Errors.validation(
                    f"Unsupported entity type: {entity_type.value}",
                    field="type",
                )
            )

        # Validate required fields before preparation (early fail-fast)
        validation_result = validate_required_fields(entity_type, data, file_path)
        if validation_result.is_error:
            return Result.fail(validation_result.expect_error())

        # Prepare entity data
        entity_data = prepare_entity_data(entity_type, data, body, file_path, self.default_user_uid)

        # Validate entity data after preparation (ensures auto-generated fields present)
        validation_result = validate_entity_data(entity_type, entity_data, file_path)
        if validation_result.is_error:
            return Result.fail(validation_result.expect_error())

        # Get engine for this entity type
        engine = self._get_engine(entity_type)

        # Ensure constraints
        await engine.ensure_constraints()

        # Ingest with relationships
        rel_config = config.relationship_config or {}
        result = await engine.upsert_with_relationships(
            entities=[entity_data],
            relationship_config=rel_config,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        stats = result.value
        self.logger.info(f"Ingested {entity_type.value}: {entity_data['uid']}")

        # Phase 1: Automatic chunking for KU entities (January 2026)
        # Generate chunks immediately after successful KU ingestion for RAG-readiness
        chunks_generated = False
        if entity_type == EntityType.KU and self.chunking:
            content_body = entity_data.get("content", "")
            if content_body:
                chunk_result = await self.chunking.process_content_for_ingestion(
                    parent_uid=entity_data["uid"],
                    content_body=content_body,
                    format=file_format,
                    source_path=str(file_path),
                )

                if chunk_result.is_error:
                    # Log warning but don't fail ingestion - chunks can be regenerated later
                    self.logger.warning(
                        f"Failed to generate chunks for {entity_data['uid']}: "
                        f"{chunk_result.expect_error().message}"
                    )
                else:
                    content, metadata = chunk_result.value
                    chunks_generated = True
                    self.logger.info(
                        f"Generated {content.chunk_count} chunks for {entity_data['uid']} "
                        f"({content.word_count} words)"
                    )

        return Result.ok(
            {
                "uid": entity_data["uid"],
                "title": entity_data.get("title") or entity_data.get("name"),
                "entity_type": entity_type.value,  # Serialize as string for JSON
                "format": file_format,
                "success": True,
                "nodes_created": stats.nodes_created,
                "nodes_updated": stats.nodes_updated,
                "relationships_created": stats.relationships_created,
                "chunks_generated": chunks_generated,  # Track whether chunking succeeded
            }
        )

    # ========================================================================
    # BATCH OPERATIONS - Delegate to batch module
    # ========================================================================

    async def ingest_directory(
        self,
        directory: Path,
        pattern: str = "*",
        batch_size: int = 500,
        max_concurrent: int = 20,
        ingestion_mode: Literal["full", "incremental", "smart"] = "full",
        validate_targets: bool = False,
        progress_callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> Result[IngestionStats | IncrementalStats | DryRunPreview]:
        """
        Ingest all supported files in a directory.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for files (default: "*" for all supported)
            batch_size: Batch size for bulk operations
            max_concurrent: Maximum concurrent file parsing operations
            ingestion_mode: Ingestion strategy:
                - "full": Process all files (default, backward compatible)
                - "incremental": Skip files with unchanged content hash
                - "smart": Skip files with unchanged mtime (fast), verify with hash if changed
            validate_targets: If True, validate relationship targets exist before ingestion
            progress_callback: Optional callback for progress reporting (current, total, current_file)
            dry_run: If True, validates and previews changes without writing to Neo4j

        Returns:
            Result with IngestionStats (full mode), IncrementalStats (incremental/smart mode), or DryRunPreview (dry-run mode)

        Delegates to batch.ingest_directory.
        """
        return await ingest_directory(
            directory=directory,
            engines=self._engines,
            get_engine=self._get_engine,
            driver=self.driver,
            pattern=pattern,
            batch_size=batch_size,
            max_concurrent=max_concurrent,
            default_user_uid=self.default_user_uid,
            max_file_size_bytes=self.max_file_size_bytes,
            ingestion_mode=ingestion_mode,
            validate_targets=validate_targets,
            progress_callback=progress_callback,
            dry_run=dry_run,
        )

    async def ingest_vault(
        self,
        vault_path: Path,
        subdirs: list[str] | None = None,
    ) -> Result[IngestionStats]:
        """
        Ingest an entire Obsidian vault or specific subdirectories.

        Delegates to batch.ingest_vault.
        """
        return await ingest_vault(
            vault_path=vault_path,
            ingest_directory_fn=self.ingest_directory,
            subdirs=subdirs,
        )

    async def ingest_bundle(self, bundle_path: Path) -> Result[BundleStats]:
        """
        Ingest a domain bundle using manifest file.

        Delegates to batch.ingest_bundle.
        """

        def _find_entity_file_with_size(bp: Path, uid: str) -> Path | None:
            return find_entity_file(bp, uid, self.max_file_size_bytes)

        return await ingest_bundle(
            bundle_path=bundle_path,
            parse_yaml_fn=self.parse_yaml,
            ingest_file_fn=self.ingest_file,
            find_entity_file_fn=_find_entity_file_with_size,
        )

    # ========================================================================
    # VALIDATION - Delegate to validator module
    # ========================================================================

    async def validate_file(self, file_path: Path) -> Result[Any]:
        """
        Validate a file without persisting to Neo4j (dry-run mode).

        Delegates to validator.validate_file.
        """
        return await validate_file(
            file_path=file_path,
            default_user_uid=self.default_user_uid,
            max_file_size_bytes=self.max_file_size_bytes,
        )

    async def validate_directory(
        self,
        directory: Path,
        pattern: str = "*",
        max_concurrent: int = 20,
    ) -> Result[Any]:
        """
        Validate all files in a directory without persisting (dry-run mode).

        Delegates to validator.validate_directory.
        """
        return await validate_directory(
            directory=directory,
            pattern=pattern,
            max_concurrent=max_concurrent,
            default_user_uid=self.default_user_uid,
            max_file_size_bytes=self.max_file_size_bytes,
        )
