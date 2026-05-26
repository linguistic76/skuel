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
- Performance: BulkUpsertBackend for batch operations (10-100x faster)

See: /docs/decisions/ADR-014-unified-ingestion.md
"""

from __future__ import annotations

__version__ = "2.0"

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from neo4j import AsyncDriver

    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .batch import ProgressCallback, find_entity_file, ingest_bundle, ingest_directory, ingest_vault
from .config import DEFAULT_MAX_FILE_SIZE_BYTES, DEFAULT_USER_UID, ENTITY_CONFIGS
from .detector import detect_entity_type, detect_format, is_edge_type
from .parser import check_file_size, parse_markdown, parse_yaml
from .preparer import (
    generate_uid,
    normalize_uid,
    prepare_edge_data,
    prepare_entity_data,
    prepare_entity_data_async,
)
from .types import (
    BundleStats,
    DirectoryValidationResult,
    DryRunPreview,
    IncrementalStats,
    IngestionStats,
    ValidationResult,
)
from .user_entry_ingestion import ingest_user_entry
from .validator import (
    validate_directory,
    validate_edge_data,
    validate_entity_data,
    validate_file,
    validate_required_fields,
    validate_uid_format,
)

logger = get_logger("skuel.services.unified_ingestion")


class UnifiedIngestionService:
    """
    Unified service for ingesting content from both MD and YAML formats.

    Orchestrates capabilities from decomposed modules:
    - Auto-detects file format (MD vs YAML)
    - Routes to appropriate entity type (20 entity types)
    - Normalizes UIDs to dot notation
    - Uses BulkUpsertBackend for batch performance
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
        default_user_uid: UserUID | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        embeddings_service: Any | None = None,
        chunking_service: Any | None = None,
        content_adapter: Any | None = None,
        event_bus: Any | None = None,
        ingestion_backend: Any | None = None,
        user_entry_service: UserEntryService | None = None,
        user_service: UserService | None = None,
    ) -> None:
        """
        Initialize unified ingestion service.

        Args:
            driver: Neo4j async driver. Used only to construct the ingestion
                    write + bulk-upsert backends (ADR-044); the service does not
                    author Cypher or open sessions itself.
            default_user_uid: Default user UID for entities without explicit user_uid.
                              If not provided, uses SKUEL_DEFAULT_USER_UID env var or "user:system".
            max_file_size_bytes: Maximum file size in bytes (default: 10 MB).
                                 Files larger than this will be rejected to prevent OOM.
            embeddings_service: Optional HuggingFaceEmbeddingsService for embedding generation.
                                If not provided, ingestion works without embeddings (graceful degradation).
            chunking_service: Optional EntityChunkingService for automatic chunk generation.
                              If not provided, ingestion works without chunking (graceful degradation).
            content_adapter: Neo4jContentAdapter for persisting :Content and :ContentChunk nodes
                             after chunk generation. Required in production for RAG retrieval;
                             when omitted, chunks remain in-memory only.
            event_bus: EventBusOperations for publishing ChunkEmbeddingRequested events to the
                       background embedding worker. Required in production for chunk embeddings.
            ingestion_backend: IngestionBackend for ingestion tracking (optional).
            user_entry_service: UserEntryService for routing UserEntry YAMLs through
                                the same create_entry() pipeline as /submit. Required
                                when ingesting ``type: user_entry`` files.
            user_service: UserService for role lookup during UserEntry ingestion
                          (gates ``audience: public`` on TEACHER role). When not
                          wired, ``audience: public`` uploads are rejected as
                          forbidden.
        """
        if not driver:
            raise ValueError("Neo4j driver is required")

        from adapters.persistence.neo4j.bulk_upsert_backend import BulkUpsertBackend
        from adapters.persistence.neo4j.ingestion_write_backend import IngestionWriteBackend

        self.driver = driver
        # All ingestion Cypher lives below the boundary (ADR-044): edge/existence
        # writes in IngestionWriteBackend, node upsert + constraints + delete in
        # BulkUpsertBackend. The service orchestrates and calls these backends; it
        # no longer authors Cypher or opens sessions itself.
        self._write_backend = IngestionWriteBackend(driver)
        self._bulk_backend = BulkUpsertBackend(driver)
        self.ingestion_backend = ingestion_backend
        self.default_user_uid = (
            default_user_uid if default_user_uid is not None else DEFAULT_USER_UID
        )
        self.max_file_size_bytes = max_file_size_bytes
        self.embeddings = embeddings_service  # Can be None - graceful degradation
        self.chunking = chunking_service  # Can be None - graceful degradation
        self.content_adapter = content_adapter  # Can be None - graceful degradation
        self.event_bus = event_bus  # Can be None - graceful degradation
        self.user_entry_service = user_entry_service
        self.user_service = user_service
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
                "✅ Chunking service available - will generate chunks during PathStep ingestion"
            )
        else:
            self.logger.warning(
                "⚠️ Chunking service not available - PathStep ingestion will work without chunks"
            )

        # Chunks reach Neo4j only when both the chunker and the content adapter are wired.
        # In tests, omitting either keeps the path entirely in-memory; in production
        # both are wired in compose.py so the full ingest → persist → embed chain runs.
        if self.chunking and not self.content_adapter:
            self.logger.warning(
                "⚠️ Chunking enabled but content_adapter missing — chunks will not be persisted to Neo4j"
            )
        if self.content_adapter and not self.event_bus:
            self.logger.warning(
                "⚠️ Content adapter wired but event_bus missing — chunk embeddings will not be generated"
            )

        # Track which entity types have had constraints ensured (avoid per-file
        # round-trip). The Cypher lives in BulkUpsertBackend; this set is the
        # orchestration bookkeeping that stays in the service.
        self._constraints_ensured: set[EntityType | NonKuDomain] = set()

    async def _ensure_constraints(self, entity_type: EntityType | NonKuDomain) -> None:
        """Ensure constraints once per entity type per service lifetime."""
        if entity_type in self._constraints_ensured:
            return
        config = ENTITY_CONFIGS.get(entity_type)
        if not config:
            raise ValueError(f"Unknown entity type: {entity_type}")
        await self._bulk_backend.ensure_constraints(config.entity_label)
        self._constraints_ensured.add(entity_type)

    # ========================================================================
    # DELEGATED METHODS (for backward compatibility)
    # ========================================================================

    def normalize_uid(self, uid: str) -> str:
        """Normalize UID to dot notation. Delegates to preparer module."""
        return normalize_uid(uid)

    def generate_uid(self, entity_type: EntityType | NonKuDomain, file_path: Path) -> str:
        """Generate UID from entity type and file path. Delegates to preparer module."""
        return generate_uid(entity_type, file_path)

    def detect_format(self, file_path: Path) -> str:
        """Detect file format from extension. Delegates to detector module."""
        return detect_format(file_path)

    def detect_entity_type(self, data: dict[str, Any], file_path: Path) -> EntityType | NonKuDomain:
        """Detect entity type from file content. Delegates to detector module."""
        return detect_entity_type(data, file_path)

    def parse_markdown(self, file_path: Path) -> Result[tuple[dict[str, Any], str]]:
        """Parse markdown file. Delegates to parser module."""
        return parse_markdown(file_path, self.max_file_size_bytes)

    def validate_required_fields(
        self,
        entity_type: EntityType | NonKuDomain,
        data: dict[str, Any],
        file_path: Path,
    ) -> Result[None]:
        """Validate required fields before preparation. Delegates to validator module."""
        return validate_required_fields(entity_type, data, file_path)

    def validate_entity_data(
        self,
        entity_type: EntityType | NonKuDomain,
        entity_data: dict[str, Any],
        file_path: Path,
    ) -> Result[None]:
        """Validate entity data after preparation. Delegates to validator module."""
        return validate_entity_data(entity_type, entity_data, file_path)

    def prepare_entity_data(
        self,
        entity_type: EntityType | NonKuDomain,
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
    # EDGE INGESTION
    # ========================================================================

    @with_error_handling("ingest_edge", error_type="system")
    async def ingest_edge(self, edge_data: dict[str, Any]) -> Result[dict[str, Any]]:
        """
        Ingest a standalone edge (relationship) into Neo4j.

        Uses the edge-write backend (not the bulk node upsert) since edges create
        relationships, not nodes.

        Args:
            edge_data: Prepared edge data from prepare_edge_data()

        Returns:
            Result with edge details (from_uid, to_uid, relationship, created)
        """
        from_uid = edge_data["from_uid"]
        to_uid = edge_data["to_uid"]
        props = edge_data["properties"]

        # Convert the validated-but-stringly-typed dict value into a typed
        # RelationshipName at the boundary — this is where the value re-enters the
        # typed world, so the enum (not "validated by caller" discipline) is what
        # guarantees the rel-type interpolation in IngestionWriteBackend is safe.
        rel_type = RelationshipName.from_string(edge_data["relationship"])
        if rel_type is None:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship type: {edge_data['relationship']!r}",
                    field="relationship",
                )
            )

        try:
            # The Cypher lives in IngestionWriteBackend below the boundary (ADR-044).
            records = await self._write_backend.ingest_edge(from_uid, to_uid, rel_type, props)

            if not records:
                # One or both entities not found
                missing: list[str] = []
                for uid, label in [(from_uid, "from"), (to_uid, "to")]:
                    if not await self._write_backend.entity_exists(uid):
                        missing.append(f"{label}={uid}")
                return Result.fail(
                    Errors.not_found(
                        resource="Entity",
                        identifier=", ".join(missing),
                    )
                )

            record = records[0]
            was_created = record["created"]
            self.logger.info(
                f"{'Created' if was_created else 'Updated'} edge: "
                f"({from_uid})-[:{rel_type}]->({to_uid})"
            )

            return Result.ok(
                {
                    "from_uid": from_uid,
                    "to_uid": to_uid,
                    "relationship": rel_type,
                    "created": was_created,
                    "success": True,
                }
            )

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to ingest edge ({from_uid})-[:{rel_type}]->({to_uid}): {e}")
            return Result.fail(
                Errors.database(
                    operation="ingest_edge",
                    message=f"Edge ingestion failed: {e}",
                )
            )

    # ========================================================================
    # SINGLE FILE INGESTION
    # ========================================================================

    @with_error_handling("ingest_file", error_type="system")
    async def ingest_file(
        self, file_path: Path, *, user_uid: UserUID | None = None
    ) -> Result[dict[str, Any]]:
        """
        Ingest a single file (MD or YAML) into Neo4j.

        Auto-detects format and entity type, normalizes UID,
        and persists using BulkUpsertBackend. If the file declares
        type: Edge, it is ingested as a relationship instead of a node.

        Args:
            file_path: Path to file to ingest
            user_uid: Override user UID for multi-tenant entities.
                      If not provided, uses self.default_user_uid.

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
                return Result.fail(parse_result)
            data, body = parse_result.value
        else:  # yaml
            yaml_result = parse_yaml(file_path, self.max_file_size_bytes)
            if yaml_result.is_error:
                return Result.fail(yaml_result)
            data = yaml_result.value
            body = None

        # Check for edge type BEFORE entity type detection
        if is_edge_type(data):
            validation = validate_edge_data(data)
            if validation.is_error:
                return Result.fail(validation)
            prepared = prepare_edge_data(data, file_path)
            return await self.ingest_edge(prepared)

        # Detect domain type (returns EntityType/NonKuDomain enum - type-safe!)
        entity_type = detect_entity_type(data, file_path)
        config = ENTITY_CONFIGS.get(entity_type)
        if not config:
            return Result.fail(
                Errors.validation(
                    f"Unsupported entity type: {entity_type.value}",
                    field="type",
                )
            )

        # UserEntry has its own creation pipeline (audience resolution,
        # Interaction audit, TRANSFORMS edges, compensation delete) that the
        # bulk engine cannot replicate. Route through UserEntryService so
        # /upload and /submit share every downstream step.
        if entity_type == EntityType.USER_ENTRY:
            if self.user_entry_service is None:
                return Result.fail(
                    Errors.system(
                        "UserEntry ingestion requires user_entry_service "
                        "to be wired into UnifiedIngestionService.",
                        operation="ingest_user_entry",
                    )
                )
            effective_user_uid = user_uid or self.default_user_uid
            return await ingest_user_entry(
                data=data,
                file_path=file_path,
                user_uid=effective_user_uid,
                user_entry_service=self.user_entry_service,
                user_service=self.user_service,
            )

        # Validate UID format before preparation (early fail-fast)
        uid_result = validate_uid_format(entity_type, data, file_path)
        if uid_result.is_error:
            return Result.fail(uid_result)

        # Validate required fields before preparation (early fail-fast)
        validation_result = validate_required_fields(entity_type, data, file_path)
        if validation_result.is_error:
            return Result.fail(validation_result)

        # Prepare entity data (async path generates embeddings if service available)
        effective_user_uid = user_uid or self.default_user_uid
        entity_data = await prepare_entity_data_async(
            entity_type,
            data,
            body,
            file_path,
            effective_user_uid,
            embeddings_service=self.embeddings,
        )

        # Validate entity data after preparation (ensures auto-generated fields present)
        validation_result = validate_entity_data(entity_type, entity_data, file_path)
        if validation_result.is_error:
            return Result.fail(validation_result)

        # For PathStep: pop content before Neo4j storage — content lives on :Content node, not :Entity node
        ku_content_body = ""
        if entity_type == EntityType.PATH_STEP:
            ku_content_body = entity_data.pop("content", "")
            if ku_content_body:
                entity_data["word_count"] = len(ku_content_body.split())

        # Ensure constraints once per entity type, not per file.
        await self._ensure_constraints(entity_type)

        # Ingest with relationships (node upsert + edge creation below the boundary)
        rel_config = config.relationship_config or {}
        result = await self._bulk_backend.upsert_with_relationships(
            entity_label=config.entity_label,
            base_label=config.base_label,
            entities=[entity_data],
            relationship_config=rel_config,
        )

        if result.is_error:
            return Result.fail(result)

        stats = result.value
        self.logger.info(f"Ingested {entity_type.value}: {entity_data['uid']}")

        # Groups need an OWNS edge from the teacher to the group (ADR-053).
        # The engine created only the :Group node; wire ownership here.
        if entity_type == NonKuDomain.GROUP:
            owner_uid = entity_data.get("owner_uid")
            if owner_uid:
                try:
                    await self._write_backend.create_group_ownership(owner_uid, entity_data["uid"])
                except NEO4J_EXCEPTIONS as e:
                    self.logger.warning(
                        f"Failed to create OWNS edge for group {entity_data['uid']}: {e}"
                    )

        # Automatic chunking for PathStep entities
        # Generate chunks immediately after successful PathStep ingestion for RAG-readiness
        chunks_generated = False
        if entity_type == EntityType.PATH_STEP and self.chunking:
            content_body = ku_content_body  # Already popped above
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
                    content, _metadata = chunk_result.value
                    self.logger.info(
                        f"Generated {content.chunk_count} chunks for {entity_data['uid']} "
                        f"({content.word_count} words)"
                    )

                    # Persist chunks to Neo4j so retrieval can target them
                    if self.content_adapter:
                        stored = await self.content_adapter.store_content_with_chunks(
                            entity_data["uid"], content
                        )
                        if not stored:
                            self.logger.warning(
                                f"Chunk persistence failed for {entity_data['uid']}"
                            )
                        chunks_generated = stored

                        # Request async embedding generation for the persisted chunks
                        if stored and self.event_bus and content.chunks:
                            from datetime import datetime

                            from core.events import ChunkEmbeddingRequested, publish_event

                            await publish_event(
                                self.event_bus,
                                ChunkEmbeddingRequested(
                                    parent_uid=entity_data["uid"],
                                    chunk_uids=tuple(c.chunk_id for c in content.chunks),
                                    chunk_texts=tuple(c.context_window for c in content.chunks),
                                    requested_at=datetime.now(),
                                    user_uid=user_uid if user_uid else None,
                                ),
                                self.logger,
                            )
                    else:
                        # Chunks generated in-memory but not persisted — flag for the caller.
                        chunks_generated = True

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
        *,
        user_uid: UserUID | None = None,
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
            write_backend=self._write_backend,
            bulk_backend=self._bulk_backend,
            ingestion_backend=self.ingestion_backend,
            pattern=pattern,
            batch_size=batch_size,
            max_concurrent=max_concurrent,
            default_user_uid=user_uid or self.default_user_uid,
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

    async def validate_file(self, file_path: Path) -> Result[ValidationResult]:
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
    ) -> Result[DirectoryValidationResult]:
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
