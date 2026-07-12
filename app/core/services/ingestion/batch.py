# skuel-lint: disable-file=SKUEL005 -- batch pipeline reports per-file errors as dicts aggregated into the batch report (deliberate carrier shape); orchestrator-level failures raise
"""
Ingestion Batch Operations - Concurrent File Processing
========================================================

Handles concurrent file parsing and batch ingestion operations.
Contains thread-pool workers and async semaphore-controlled processing.

Key Features:
- Incremental ingestion support via IngestionTracker (skip unchanged files)
- Parallel file parsing with configurable concurrency
- Progress callback for large operations
- Relationship target validation before ingestion

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from core.ingestion.ingestion_types import RelationshipConfig
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.exception_types import (
    DATA_CONVERSION_EXCEPTIONS,
    FILE_IO_EXCEPTIONS,
    NEO4J_EXCEPTIONS,
    PARSING_EXCEPTIONS,
)
from core.utils.frontmatter import split_frontmatter
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .config import (
    DEFAULT_MAX_CONCURRENT_PARSING,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_USER_UID,
    ENTITY_CONFIGS,
    SyncAllowlist,
    collect_files,
    collect_files_detailed,
)
from .detector import detect_entity_type, detect_format, is_edge_type
from .ingestion_tracker import IngestionTracker, edge_identity
from .moc_links import frontmatter_organizes_targets
from .parser import check_file_size, parse_markdown, parse_yaml
from .preparer import normalize_uid, prepare_edge_data, prepare_entity_data
from .types import (
    BundleStats,
    ChunkSource,
    DryRunPreview,
    IncrementalStats,
    IngestionError,
    IngestionStats,
)
from .validator import (
    validate_edge_data,
    validate_entity_data,
    validate_relationship_targets,
    validate_required_fields,
    validate_uid_format,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from core.ports.ingestion_protocols import BulkUpsertOperations, IngestionWriteOperations

logger = get_logger("skuel.services.ingestion.batch")

# Type alias for progress callback
ProgressCallback = Callable[[int, int, str], None]  # (current, total, current_file)


def create_error(
    file_path: Path,
    error: str,
    stage: str,
    error_type: str = "unknown",
    entity_type: str | None = None,
    line_number: int | None = None,
    column: int | None = None,
    field: str | None = None,
    suggestion: str | None = None,
) -> IngestionError:
    """
    Create a rich IngestionError with full context.

    Args:
        file_path: Path to the file that caused the error
        error: Error message
        stage: Processing stage (format_detection, parsing, type_detection, etc.)
        error_type: Error category (validation, parse, format, system, exception)
        entity_type: Entity type if detected
        line_number: Line number if available
        column: Column number if available
        field: Field name for validation errors
        suggestion: Helpful hint for fixing

    Returns:
        IngestionError with full context
    """
    return IngestionError(
        file=str(file_path),
        error=error,
        stage=stage,
        error_type=error_type,
        entity_type=entity_type,
        line_number=line_number,
        column=column,
        field=field,
        suggestion=suggestion,
    )


async def check_existing_entities(
    write_backend: IngestionWriteOperations,
    uids: list[str],
) -> dict[str, bool]:
    """
    Check which UIDs already exist in Neo4j.

    Args:
        write_backend: Ingestion write backend (existence Cypher lives below the
            boundary, ADR-044)
        uids: List of UIDs to check

    Returns:
        Dictionary mapping uid -> exists (bool)
    """
    if not uids:
        return {}

    return await write_backend.check_existing_entities(uids)


def parse_file_sync(
    file_path: Path,
    default_user_uid: UserUID = DEFAULT_USER_UID,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    *,
    owner_is_authoritative: bool = False,
) -> tuple[EntityType | NonKuDomain, dict[str, Any], None] | tuple[None, None, dict[str, Any]]:
    """
    Synchronous file parsing for use in thread pool.

    Handles format detection, parsing, validation, and data preparation.
    Returns rich error context via IngestionError on failure.

    Intentional seam vs. ``UnifiedIngestionService.ingest_file``: both run the
    same parse → validate → prepare pipeline (identical contract, one preparer);
    the remaining divergence is the error channel only — this path reports
    per-file ``IngestionError`` dicts the batch aggregates (and runs inside a
    thread pool), where ``ingest_file`` returns ``Result``.

    Args:
        file_path: Path to file to parse
        default_user_uid: Default user UID for multi-tenant entities
        max_file_size_bytes: Maximum file size

    Returns:
        Tuple of (entity_type, entity_data, None) on success
        or (None, None, IngestionError.to_dict()) on failure
    """
    entity_type_str: str | None = None

    try:
        # Stage 1: Format detection
        file_format = detect_format(file_path)

        # Stage 2: Parsing
        if file_format == "markdown":
            parse_result = parse_markdown(file_path, max_file_size_bytes)
            if parse_result.is_error:
                err = parse_result.expect_error()
                error = create_error(
                    file_path=file_path,
                    error=err.display_message,
                    stage="parsing",
                    error_type="parse",
                    suggestion="Check YAML frontmatter syntax between --- markers.",
                )
                return (None, None, error.to_dict())
            data, body = parse_result.value
        else:
            yaml_result = parse_yaml(file_path, max_file_size_bytes)
            if yaml_result.is_error:
                err = yaml_result.expect_error()
                # Line number is now embedded in the error message
                # Extract it for structured error if present
                line_num = None
                col = None
                msg = err.message or ""
                if "at line " in msg:
                    line_match = re.search(r"at line (\d+)", msg)
                    if line_match:
                        line_num = int(line_match.group(1))
                    col_match = re.search(r"column (\d+)", msg)
                    if col_match:
                        col = int(col_match.group(1))
                error = create_error(
                    file_path=file_path,
                    error=err.display_message,
                    stage="parsing",
                    error_type="parse",
                    line_number=line_num,
                    column=col,
                    suggestion="Check YAML syntax: proper indentation, colons, and quotes.",
                )
                return (None, None, error.to_dict())
            data = yaml_result.value
            body = None

        # Stage 3a: Check for edge type (edges are NOT entities)
        if is_edge_type(data):
            validation = validate_edge_data(data)
            if validation.is_error:
                err = validation.expect_error()
                error = create_error(
                    file_path=file_path,
                    error=err.display_message,
                    stage="validation",
                    error_type="validation",
                    entity_type="edge",
                    suggestion="Check edge YAML: requires 'from', 'to', 'relationship' fields.",
                )
                return (None, None, error.to_dict())
            edge_data = prepare_edge_data(data, file_path)
            # Return with sentinel: entity_type=None but entity_data has "_edge" marker
            edge_data["_is_edge"] = True
            # Use a cast-compatible return: (None, edge_data, None) won't match
            # the entity_type check downstream, so we use a special convention:
            # Return (None, edge_data, None) — the caller checks _is_edge
            return (None, edge_data, None)  # type: ignore[return-value]

        # Stage 3b: Entity type detection
        try:
            entity_type = detect_entity_type(data, file_path)
            entity_type_str = entity_type.value
        except ValueError as e:
            error = create_error(
                file_path=file_path,
                error=str(e),
                stage="type_detection",
                error_type="validation",
                suggestion="Add 'type: <entity_type>' field (e.g., type: ku, type: task).",
            )
            return (None, None, error.to_dict())

        # Stage 4: Pre-preparation validation (same contract as the single-file
        # door — ingest_file validates UID prefix then required fields).
        # USER_ENTRY is exempt, mirroring ingest_file (its USER_ENTRY branch
        # returns before validate_uid_format): an authored UserEntry uid is an
        # opaque deterministic join key (e.g. ``moc:worldview``), never type
        # information (ADR-013 never-sniff) — the entity kind is whatever
        # ``type:`` says, and the service normalizes/persists the uid.
        if entity_type != EntityType.USER_ENTRY:
            uid_result = validate_uid_format(entity_type, data, file_path)
            if uid_result.is_error:
                err = uid_result.expect_error()
                error = create_error(
                    file_path=file_path,
                    error=err.display_message,
                    stage="validation",
                    error_type="validation",
                    entity_type=entity_type_str,
                    field="uid",
                    suggestion=f"Use the UID prefix for {entity_type_str} entities (see error).",
                )
                return (None, None, error.to_dict())

        validation_result = validate_required_fields(entity_type, data, file_path)
        if validation_result.is_error:
            err = validation_result.expect_error()
            error = create_error(
                file_path=file_path,
                error=err.display_message,
                stage="validation",
                error_type="validation",
                entity_type=entity_type_str,
                field=getattr(err, "field", None),
                suggestion=f"Add the missing required fields for {entity_type_str} entity.",
            )
            return (None, None, error.to_dict())

        # Stage 5: Data preparation
        try:
            entity_data = prepare_entity_data(
                entity_type,
                data,
                body,
                file_path,
                default_user_uid,
                owner_is_authoritative=owner_is_authoritative,
            )
        except DATA_CONVERSION_EXCEPTIONS as e:
            error = create_error(
                file_path=file_path,
                error=f"Failed to prepare entity data: {e}",
                stage="preparation",
                error_type="system",
                entity_type=entity_type_str,
                suggestion="Check field values and data types match expected format.",
            )
            return (None, None, error.to_dict())

        # Stage 6: Post-preparation validation
        validation_result = validate_entity_data(entity_type, entity_data, file_path)
        if validation_result.is_error:
            err = validation_result.expect_error()
            error = create_error(
                file_path=file_path,
                error=err.display_message,
                stage="validation",
                error_type="validation",
                entity_type=entity_type_str,
                field=getattr(err, "field", None),
                suggestion="Ensure content body is not empty for content-based entities.",
            )
            return (None, None, error.to_dict())

        return (entity_type, entity_data, None)

    except ValueError as e:
        error = create_error(
            file_path=file_path,
            error=str(e),
            stage="format_detection",
            error_type="format",
            entity_type=entity_type_str,
            suggestion="Use .md, .yaml, or .yml file extension.",
        )
        return (None, None, error.to_dict())
    except FILE_IO_EXCEPTIONS as e:
        error = create_error(
            file_path=file_path,
            error=str(e),
            stage="file_io",
            error_type="system",
            entity_type=entity_type_str,
            suggestion="Check file permissions and encoding (UTF-8).",
        )
        return (None, None, error.to_dict())
    except Exception as e:  # safety-net: catch unexpected errors
        error = create_error(
            file_path=file_path,
            error=str(e),
            stage="unknown",
            error_type="exception",
            entity_type=entity_type_str,
            suggestion="Unexpected error. Check file permissions and encoding (UTF-8).",
        )
        return (None, None, error.to_dict())


async def parse_file_for_batch(
    file_path: Path,
    semaphore: asyncio.Semaphore,
    default_user_uid: UserUID = DEFAULT_USER_UID,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    *,
    owner_is_authoritative: bool = False,
) -> tuple[EntityType | NonKuDomain, dict[str, Any], None] | tuple[None, None, dict[str, Any]]:
    """
    Parse and validate a single file for batch ingestion.

    Runs file I/O in thread pool for non-blocking operation.
    Returns either (entity_type, entity_data, None) on success,
    or (None, None, error_dict) on failure.

    Args:
        file_path: Path to file to parse
        semaphore: Concurrency limiter
        default_user_uid: Default user UID
        max_file_size_bytes: Maximum file size

    Returns:
        Tuple of (entity_type, entity_data, None) or (None, None, IngestionError.to_dict())
    """
    async with semaphore:
        try:
            # Run synchronous file parsing in thread pool
            return await asyncio.to_thread(
                parse_file_sync,
                file_path,
                default_user_uid,
                max_file_size_bytes,
                owner_is_authoritative=owner_is_authoritative,
            )
        except (OSError, RuntimeError) as e:
            error = create_error(
                file_path=file_path,
                error=str(e),
                stage="thread_dispatch",
                error_type="system",
                suggestion="Thread pool or file system error. Check file format and encoding.",
            )
            return (None, None, error.to_dict())
        except Exception as e:  # safety-net: catch unexpected errors
            error = create_error(
                file_path=file_path,
                error=str(e),
                stage="thread_dispatch",
                error_type="exception",
                suggestion="This is an unexpected error. Check the file format and encoding.",
            )
            return (None, None, error.to_dict())


async def _ingest_edge_batch(
    write_backend: IngestionWriteOperations,
    edge_files: list[dict[str, Any]],
) -> tuple[int, list[dict[str, str]], list[dict[str, str]]]:
    """
    Ingest a batch of prepared edge data into Neo4j.

    Args:
        write_backend: Ingestion write backend (edge Cypher lives below the
            boundary, ADR-044)
        edge_files: List of prepared edge dicts (from prepare_edge_data)

    Returns:
        Tuple of (edges_created_count, error_dicts, successes). Each success
        carries {source_file, from_uid, to_uid, rel_type} so the caller can
        record IngestionMetadata for the edge file — which is what makes
        edge-file deletion propagate (and unchanged edge files skip).
    """
    edges_created = 0
    errors: list[dict[str, str]] = []
    successes: list[dict[str, str]] = []

    for edge_data in edge_files:
        from_uid = edge_data["from_uid"]
        to_uid = edge_data["to_uid"]
        props = edge_data["properties"]

        # Convert the validated-but-stringly-typed dict value into a typed
        # RelationshipName at the boundary; the enum (not caller discipline) is what
        # makes the rel-type interpolation in IngestionWriteBackend injection-safe.
        rel_type = RelationshipName.from_string(edge_data["relationship"])
        if rel_type is None:
            errors.append(
                IngestionError(
                    file=props.get("source_file", "<edge>"),
                    error=f"Unknown relationship type: {edge_data['relationship']!r}",
                    stage="edge_ingestion",
                    error_type="validation",
                ).to_dict()
            )
            continue

        try:
            # Cypher lives in IngestionWriteBackend below the boundary (ADR-044).
            records = await write_backend.ingest_edge(from_uid, to_uid, rel_type, props)
            if records:
                edges_created += 1
                successes.append(
                    {
                        "source_file": props.get("source_file", ""),
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "rel_type": str(rel_type),
                    }
                )
            else:
                edge_error = IngestionError(
                    file=props.get("source_file", "<edge>"),
                    error=f"Entity not found: from={from_uid} or to={to_uid}",
                    stage="edge_ingestion",
                    error_type="not_found",
                )
                errors.append(edge_error.to_dict())
        except NEO4J_EXCEPTIONS as e:
            edge_error = IngestionError(
                file=props.get("source_file", "<edge>"),
                error=str(e),
                stage="edge_ingestion",
                error_type="database",
            )
            errors.append(edge_error.to_dict())

    return edges_created, errors, successes


async def ingest_directory(
    directory: Path,
    write_backend: IngestionWriteOperations | None = None,  # edges, existence checks (ADR-044)
    bulk_backend: BulkUpsertOperations | None = None,  # node upsert + constraints (ADR-044)
    ingestion_backend: Any = None,  # IngestionBackend for ingestion tracking
    pattern: str = "*",
    batch_size: int = 500,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT_PARSING,
    default_user_uid: UserUID = DEFAULT_USER_UID,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ingestion_mode: Literal["full", "incremental", "smart"] = "full",
    force: bool = False,
    validate_targets: bool = False,
    progress_callback: ProgressCallback | None = None,
    dry_run: bool = False,
    ingest_file_fn: Callable[[Path], Awaitable[Result[Any]]] | None = None,
    allowlist: SyncAllowlist | None = None,
    owner_is_authoritative: bool = False,
    post_persist_fn: Callable[
        [EntityType | NonKuDomain, list[dict[str, Any]], dict[str, ChunkSource]],
        Awaitable[None],
    ]
    | None = None,
    moc_pass_fn: Callable[[str, list[str], Path, list[str]], Awaitable[list[str]]] | None = None,
) -> Result[IngestionStats | IncrementalStats | DryRunPreview]:
    """
    Ingest all supported files in a directory.

    Processes both MD and YAML files in PARALLEL, batching by entity type
    for efficient bulk operations.

    Args:
        directory: Directory to scan
        write_backend: Ingestion write backend — edges + existence checks (required
            for dry-run preview and edge ingestion). Cypher lives below the
            hexagonal boundary (ADR-044).
        bulk_backend: Bulk upsert backend — node upsert + constraints (required for
            non-dry-run ingestion).
        ingestion_backend: IngestionBackend for incremental tracking (optional)
        pattern: Glob pattern for files (default: "*" for all supported)
        batch_size: Batch size for bulk operations
        max_concurrent: Maximum concurrent file parsing operations (default: 20)
        default_user_uid: Default user UID
        max_file_size_bytes: Maximum file size
        ingestion_mode: Ingestion strategy:
            - "full": Process all files (default, backward compatible)
            - "incremental": Skip files with unchanged content hash
            - "smart": Skip files with unchanged mtime (fast), verify with hash if changed
        force: Re-process every surviving file regardless of hash/mtime while
            KEEPING tracked-mode semantics — metadata rows are re-stamped and
            deletion reconciliation still runs. This is force ≠ full: full mode
            skips reconciliation (and would leak the vault wall), force does
            not. Requires a tracked mode (incremental/smart); a full-mode force
            is rejected because "re-process unchanged" only has meaning under
            tracking.
        validate_targets: If True, validate relationship targets exist before ingestion
        progress_callback: Optional callback for progress reporting (current, total, current_file)
        dry_run: If True, validates and previews changes without writing to Neo4j
        ingest_file_fn: Optional per-file ingest callback for entity types that
            require a service pipeline (e.g. ``EntityType.USER_ENTRY``). When
            supplied, USER_ENTRY files bypass the bulk upsert engine and are
            routed through this callback instead — ensuring the OWNS edge,
            audience resolution, and post-persist pipeline (EXTRACT_ACTIVITIES)
            all run. Callback signature: ``async (path) -> Result[Any]``.
        allowlist: Optional fail-closed folder allowlist (SyncAllowlist). When
            set, files under its governed vault root are ingested only if they
            also sit under an allowed dir; files outside the root are unaffected.
            Applied in ``collect_files`` so every caller inherits the same wall.
        post_persist_fn: Optional per-type-batch callback invoked AFTER a
            successful bulk upsert with the persisted entity dicts plus the
            ``chunks_body_content`` (PathStep, Ku) content the engine popped
            pre-upsert (keyed by uid; empty for every other type) — the batch
            door's half of the shared post-persist step (ADR-074:
            ``UnifiedIngestionService._ingest_post_persist``, embedding
            publishes + body chunking). Never called for failed batches
            or in dry-run mode.
        moc_pass_fn: Optional MOC edge-pass callback
            (``UnifiedIngestionService._apply_moc_links``). Files with
            ``moc: true`` have their body-link suffixes collected during the
            per-type loops and applied END of sync — after IngestionMetadata
            rows are stamped and deletion reconciliation ran — so link targets
            ingested in the SAME sync resolve. Signature:
            ``async (entity_uid, link_suffixes, file_path,
            protected_target_uids) -> warnings``;
            returned warnings merge into the sync stats (content-vault
            posture; personal vaults return none).

    Returns:
        Result with IngestionStats (full mode), IncrementalStats (incremental/smart mode), or DryRunPreview (dry-run mode)
    """
    start_time = datetime.now()

    if not directory.exists():
        return Result.fail(Errors.not_found(f"Directory not found: {directory}"))

    # Validate ingestion_backend is provided for incremental modes
    if ingestion_mode != "full" and ingestion_backend is None:
        return Result.fail(
            Errors.validation(
                "IngestionBackend required for incremental/smart ingestion mode",
                field="ingestion_backend",
            )
        )

    # Force is defined on top of tracked ingestion (see docstring) — the facade
    # coerces full → smart before delegating here, so this only fires on a
    # direct mis-call.
    if force and ingestion_mode == "full":
        return Result.fail(
            Errors.validation(
                "force re-ingestion requires a tracked mode (incremental/smart); "
                "full mode already processes every file but skips deletion "
                "reconciliation",
                field="force",
            )
        )

    if dry_run and write_backend is None:
        return Result.fail(
            Errors.validation(
                "Ingestion write backend required for dry-run mode (to check existing entities)",
                field="write_backend",
            )
        )

    # Owner scope for deletion reconciliation: when a vault registry governs
    # this scan (owner_is_authoritative), default_user_uid IS the descriptor-
    # resolved vault owner — entity deletions are then refused for anything
    # owned by a different user (cross-owner guard). Ungoverned scans (minimal
    # composes, no registry) keep legacy path-only scoping.
    deletion_owner_scope = default_user_uid if owner_is_authoritative else None

    # Collect all supported files using simplified pattern matching, with
    # skip-reason bookkeeping (G10): walled/unsupported files are reported in
    # the stats instead of silently vanishing from the totals.
    all_files, collection_skips = collect_files_detailed(directory, pattern, allowlist=allowlist)

    if not all_files:
        if ingestion_mode == "full":
            return Result.ok(
                IngestionStats(
                    total_files=0,
                    duration_seconds=0,
                    errors=[{"message": "No files found"}],
                )
            )
        # Deletion propagation must still run: deleting the last files matching
        # the pattern lands here with all_files empty. The mass-deletion valve
        # (inside reconcile_deletions) covers the everything-vanished case;
        # this covers e.g. all *.md deleted while tracked *.yaml files survive.
        empty_errors: list[dict[str, Any]] = [{"message": "No files found"}]
        empty_warnings: list[str] = list(collection_skips.warnings)
        entities_deleted = 0
        edges_deleted = 0
        stale_metadata_removed = 0
        if ingestion_backend is not None and not dry_run:
            empty_tracker = IngestionTracker(ingestion_backend)
            reconcile_result = await empty_tracker.reconcile_deletions(
                directory,
                pattern,
                allowlist=allowlist,
                owner_uid=deletion_owner_scope,
            )
            if reconcile_result.is_ok:
                entities_deleted = reconcile_result.value.entities_deleted
                edges_deleted = reconcile_result.value.edges_deleted
                stale_metadata_removed = reconcile_result.value.stale_metadata_removed
                empty_warnings.extend(reconcile_result.value.ownership_mismatches)
                if reconcile_result.value.refusal_warning:
                    empty_warnings.append(reconcile_result.value.refusal_warning)
            else:
                empty_errors.append(
                    {
                        "message": f"Deletion reconciliation failed: {reconcile_result.error}",
                        "operation": "reconcile_deletions",
                    }
                )
        return Result.ok(
            IncrementalStats(
                total_files=0,
                duration_seconds=0,
                entities_deleted=entities_deleted,
                edges_deleted=edges_deleted,
                stale_metadata_removed=stale_metadata_removed,
                files_walled=collection_skips.walled,
                files_unsupported=collection_skips.unsupported,
                warnings=empty_warnings,
                errors=empty_errors,
            )
        )

    # Initialize ingestion tracking for incremental modes
    files_to_process = all_files
    files_skipped = 0
    skipped_unchanged = 0
    skipped_hash_match = 0
    tracker: IngestionTracker | None = None

    if ingestion_mode != "full" and ingestion_backend is not None:
        tracker = IngestionTracker(ingestion_backend)
        await tracker.ensure_constraints()

        if force:
            # Force: bypass the hash/mtime skip filter — every surviving file
            # re-processes. The tracker stays live so metadata rows are
            # re-stamped below and deletion reconciliation still runs.
            logger.info(
                f"Force re-ingestion: processing all {len(all_files)} files "
                "regardless of hash/mtime"
            )
        else:
            # Get existing ingestion metadata
            metadata_result = await tracker.get_ingestion_metadata(all_files)
            metadata_map = metadata_result.value if metadata_result.is_ok else {}

            # Filter to only files needing ingestion
            files_to_process, decisions = tracker.filter_files_needing_ingestion(
                all_files, metadata_map
            )

            # Count skip reasons
            for decision in decisions:
                if not decision.needs_ingestion:
                    files_skipped += 1
                    if decision.reason == "unchanged":
                        if (
                            decision.existing_metadata
                            and decision.existing_metadata.file_mtime
                            == decision.file_path.stat().st_mtime
                        ):
                            skipped_unchanged += 1
                        else:
                            skipped_hash_match += 1

            logger.info(
                f"Incremental ingestion: {len(files_to_process)}/{len(all_files)} files need processing "
                f"({files_skipped} skipped: {skipped_unchanged} unchanged, {skipped_hash_match} hash match)"
            )

    if not files_to_process:
        # All surviving files are up to date — but a deletion-only vault change
        # lands exactly here (the deleted file is simply absent from all_files),
        # so deletion propagation must still run before returning.
        entities_deleted = 0
        edges_deleted = 0
        stale_metadata_removed = 0
        reconcile_errors: list[dict[str, Any]] = []
        reconcile_warnings: list[str] = list(collection_skips.warnings)
        if tracker is not None and not dry_run:
            reconcile_result = await tracker.reconcile_deletions(
                directory,
                pattern,
                allowlist=allowlist,
                owner_uid=deletion_owner_scope,
            )
            if reconcile_result.is_ok:
                entities_deleted = reconcile_result.value.entities_deleted
                edges_deleted = reconcile_result.value.edges_deleted
                stale_metadata_removed = reconcile_result.value.stale_metadata_removed
                reconcile_warnings.extend(reconcile_result.value.ownership_mismatches)
                if reconcile_result.value.refusal_warning:
                    reconcile_warnings.append(reconcile_result.value.refusal_warning)
            else:
                # Same error surface as the non-empty processing path — a
                # silently-skipped reconciliation would report a clean sync
                # while the deleted entity is still in the graph.
                reconcile_errors.append(
                    {
                        "message": f"Deletion reconciliation failed: {reconcile_result.error}",
                        "operation": "reconcile_deletions",
                    }
                )

        duration = (datetime.now() - start_time).total_seconds()
        return Result.ok(
            IncrementalStats(
                total_files=len(all_files),
                files_checked=len(all_files),
                files_skipped=files_skipped,
                files_ingested=0,
                duration_seconds=duration,
                skipped_unchanged=skipped_unchanged,
                skipped_hash_match=skipped_hash_match,
                entities_deleted=entities_deleted,
                edges_deleted=edges_deleted,
                stale_metadata_removed=stale_metadata_removed,
                files_walled=collection_skips.walled,
                files_unsupported=collection_skips.unsupported,
                warnings=reconcile_warnings,
                errors=reconcile_errors if reconcile_errors else None,
            )
        )

    # Content-hash move pre-pass (uid-less renames): rewrite old-path tracker
    # rows to the new path BEFORE the ingestion loop (so the path-keyed uid
    # resolution reuses the uid, #616) and BEFORE deletion reconciliation (so
    # the old path is never classified a deletion). Exact-hash only — a
    # rename + edit in one sync falls back to delete+create (Phase 2,
    # similarity matching). Failure degrades to today's delete+create rather
    # than failing the sync, surfaced as a warning.
    moves_detected = 0
    applied_moves: list[str] = []
    move_warnings: list[str] = []
    if tracker is not None and not dry_run:
        move_result = await tracker.detect_and_apply_moves(
            directory,
            files_to_process,
            pattern,
            allowlist=allowlist,
            owner_uid=deletion_owner_scope,
        )
        if move_result.is_ok:
            moves_detected = len(move_result.value.applied)
            applied_moves = [
                f"{move.display_old} → {move.display_new}" for move in move_result.value.applied
            ]
            if moves_detected:
                logger.info(
                    f"Move detection: {moves_detected} renamed file(s) preserved "
                    f"identity — {', '.join(applied_moves)}"
                )
        else:
            move_warnings.append(
                f"Move detection failed ({move_result.error}); renamed files "
                "may be treated as delete + create this sync"
            )

    logger.info(
        f"Processing {len(files_to_process)} files from {directory} (max_concurrent={max_concurrent})"
    )

    # PARALLEL PARSING: Process all files concurrently with semaphore limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    parse_tasks = [
        parse_file_for_batch(
            fp,
            semaphore,
            default_user_uid,
            max_file_size_bytes,
            owner_is_authoritative=owner_is_authoritative,
        )
        for fp in files_to_process
    ]
    parse_results = await asyncio.gather(*parse_tasks)

    # Group entities by type for batch processing (keyed by EntityType | NonKuDomain)
    entities_by_type: dict[EntityType | NonKuDomain, list[dict[str, Any]]] = {}
    edge_files: list[dict[str, Any]] = []  # Prepared edge data for separate processing
    file_entity_map: dict[
        str, tuple[EntityType | NonKuDomain, str]
    ] = {}  # file_path -> (entity_type, uid)
    errors: list[dict[str, str]] = []

    for i, (entity_type, entity_data, error) in enumerate(parse_results):
        if progress_callback:
            progress_callback(i + 1, len(files_to_process), str(files_to_process[i]))

        if error is not None:
            errors.append(error)
        elif entity_data is not None and entity_data.get("_is_edge"):
            # Edge file — processed separately after entity ingestion
            entity_data.pop("_is_edge", None)
            edge_files.append(entity_data)
        elif entity_type is not None and entity_data is not None:
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            # Embed the source file path so per-file routing can recover it
            # (e.g. USER_ENTRY entities handled by ingest_file_fn below).
            entity_data["_file_path"] = str(files_to_process[i])
            entities_by_type[entity_type].append(entity_data)
            # Track file -> entity mapping for ingestion metadata updates
            file_entity_map[str(files_to_process[i])] = (entity_type, entity_data.get("uid", ""))

    # Optional: Validate relationship targets before ingestion. Dangling
    # targets no-op inside the relationship Cypher (the MATCH miss drops the
    # UNWIND row), so this pre-check is the ONLY place a phantom UID becomes
    # visible — every missing (source, target) pair gets its own warning (G10),
    # not just the aggregate repeat-count summary.
    #
    # Payload-aware: a target that resolves to another entity in THIS sync is
    # valid even though it isn't in the graph yet — the two-phase ingest below
    # persists ALL nodes (Phase 1) before ANY relationships (Phase 2), so
    # same-sync forward references resolve on this pass. The map spans every type
    # batch (a PathStep's uses_kus target is a Ku in a different batch), so it is
    # built once across entities_by_type and passed to every per-type check.
    # Without it the pre-check false-alarms on any wave of new,
    # mutually-referencing entities ("edge not created") even though Phase 2
    # creates the edge — a cosmetic warning that historically prompted a needless
    # second --force pass. Only truly-missing targets (typos, cross-vault refs)
    # still warn.
    #
    # Keyed by label (not a flat set): each node is registered under its domain
    # label AND the base Entity label — the multi-label reality Phase 2's
    # MATCH (target:{target_label}) queries. A same-sync UID therefore validates
    # only under the label the edge will look for, so a mis-labelled reference
    # (uses_kus pointing at a same-sync PathStep) still warns rather than silently
    # dropping.
    # Seeded with per-file collection skips (je_pro consent gate) so the
    # "add pipeline: knowledge to promote" hint reaches the sync UI/API,
    # plus any move-detection degradation from the pre-pass above.
    validation_warnings: list[str] = list(collection_skips.warnings) + move_warnings
    if validate_targets and write_backend is not None:
        known_uids_by_label: dict[str, set[str]] = {}
        for etype, ents in entities_by_type.items():
            cfg = ENTITY_CONFIGS.get(etype)
            if not cfg:
                continue
            for ent in ents:
                uid = ent.get("uid")
                if not uid:
                    continue
                uid = str(uid)
                known_uids_by_label.setdefault(cfg.entity_label, set()).add(uid)
                if cfg.base_label is not None:
                    known_uids_by_label.setdefault(cfg.base_label, set()).add(uid)
        for entity_type, entities in entities_by_type.items():
            config = ENTITY_CONFIGS.get(entity_type)
            if config and config.relationship_config:
                validation_result = await validate_relationship_targets(
                    entities,
                    config.relationship_config,
                    write_backend,
                    known_uids_by_label=known_uids_by_label,
                )
                if validation_result.is_ok and not validation_result.value.valid:
                    for source_uid, targets in sorted(
                        validation_result.value.missing_by_entity.items()
                    ):
                        for target_uid in targets:
                            warning = (
                                f"{source_uid}: relationship target '{target_uid}' does not "
                                "exist — edge not created"
                            )
                            logger.warning(f"[{entity_type.value}] {warning}")
                            validation_warnings.append(warning)

    # DRY-RUN MODE: Preview changes without writing to Neo4j
    if dry_run and write_backend is not None:
        # Collect all UIDs to check existence
        all_uids: list[str] = []
        for entities in entities_by_type.values():
            all_uids.extend(entity.get("uid", "") for entity in entities if entity.get("uid"))

        # Check which entities already exist
        exists_map = await check_existing_entities(write_backend, all_uids)

        # Categorize files
        files_to_create: list[dict[str, Any]] = []
        files_to_update: list[dict[str, Any]] = []
        relationships_to_create: list[dict[str, Any]] = []

        for entity_type, entities in entities_by_type.items():
            config = ENTITY_CONFIGS.get(entity_type)
            if not config:
                continue

            for entity in entities:
                uid = entity.get("uid", "")
                title = entity.get("title") or entity.get("name", "")
                file_path = entity.get("_file_path", "")

                if exists_map.get(uid, False):
                    # Entity exists - would be updated
                    files_to_update.append(
                        {
                            "uid": uid,
                            "title": title,
                            "entity_type": entity_type.value,
                            "file_path": file_path,
                            "changes_summary": "Content would be updated",
                        }
                    )
                else:
                    # New entity - would be created
                    files_to_create.append(
                        {
                            "uid": uid,
                            "title": title,
                            "entity_type": entity_type.value,
                            "file_path": file_path,
                        }
                    )

                # Track relationships that would be created
                # rel_config maps source_field -> RelationshipConfig TypedDict
                rel_config = config.relationship_config or {}
                for source_field, rel_cfg in rel_config.items():
                    rel_type_name = (
                        rel_cfg["rel_type"] if isinstance(rel_cfg, dict) else str(rel_cfg)
                    )
                    target_uids = entity.get(source_field, [])
                    if isinstance(target_uids, str):
                        target_uids = [target_uids]
                    for target_uid in target_uids:
                        if target_uid:
                            relationships_to_create.append(
                                {
                                    "source": uid,
                                    "target": target_uid,
                                    "type": rel_type_name,
                                }
                            )

        # Build preview
        duration = (datetime.now() - start_time).total_seconds()
        preview = DryRunPreview(
            total_files=len(all_files),
            files_to_create=files_to_create,
            files_to_update=files_to_update,
            files_to_skip=[str(fp) for fp in all_files if str(fp) not in file_entity_map],
            relationships_to_create=relationships_to_create,
            validation_warnings=validation_warnings,
            validation_errors=[str(e) for e in errors],
        )

        logger.info(
            f"DRY-RUN: Would create {len(files_to_create)} entities, "
            f"update {len(files_to_update)} entities, "
            f"skip {len(preview.files_to_skip)} files"
        )

        return Result.ok(preview)

    total_nodes_created = 0
    total_nodes_updated = 0
    total_relationships_created = 0

    # MOC edge passes (``moc: true`` files) collected during the per-type loops
    # and applied END of sync — after metadata stamping + deletion
    # reconciliation — so same-sync link targets resolve via their
    # IngestionMetadata rows. (entity_uid, ordered link suffixes, source file,
    # frontmatter ``organizes:`` targets spared from the stale-edge refresh)
    moc_items: list[tuple[str, list[str], Path, list[str]]] = []

    # USER_ENTRY routing: bypass the bulk upsert engine.  UserEntry requires the
    # full UserEntryService pipeline (OWNS edge, audience resolution, extraction).
    # When ingest_file_fn is wired (from UnifiedIngestionService), call it for
    # each UserEntry file; otherwise warn and skip (no orphan nodes created).
    user_entry_entities = entities_by_type.pop(EntityType.USER_ENTRY, [])
    if user_entry_entities:
        if ingest_file_fn is not None:
            for ue_entity in user_entry_entities:
                ue_path = Path(ue_entity.get("_file_path", ""))
                if not ue_path.exists():
                    errors.append(
                        IngestionError(
                            file=str(ue_path),
                            error="UserEntry file not found for per-file routing",
                            stage="routing",
                            error_type="not_found",
                            entity_type=EntityType.USER_ENTRY.value,
                        ).to_dict()
                    )
                    continue
                ue_result = await ingest_file_fn(ue_path)
                if ue_result.is_error:
                    errors.append(
                        IngestionError(
                            file=str(ue_path),
                            error=str(ue_result.expect_error()),
                            stage="user_entry_pipeline",
                            error_type="service",
                            entity_type=EntityType.USER_ENTRY.value,
                        ).to_dict()
                    )
                    # Remove from file_entity_map so smart-mode does NOT record a
                    # success hash — the next sync will retry this file.
                    file_entity_map.pop(str(ue_path), None)
                else:
                    result_data = ue_result.value or {}
                    if result_data.get("extraction_error"):
                        # Persistence succeeded but post-persist extraction failed.
                        # Surface as an error and exclude from smart-mode tracking so
                        # the next incremental sync retries extraction.
                        errors.append(
                            IngestionError(
                                file=str(ue_path),
                                error=result_data["extraction_error"],
                                stage="extract_activities",
                                error_type="service",
                                entity_type=EntityType.USER_ENTRY.value,
                            ).to_dict()
                        )
                        file_entity_map.pop(str(ue_path), None)
                    else:
                        # Count the per-file write as one node created/updated
                        if result_data.get("nodes_created", 0):
                            total_nodes_created += result_data["nodes_created"]
                        else:
                            total_nodes_updated += result_data.get("nodes_updated", 0) or 1
                        # Record the REAL entry uid the service minted (e.g.
                        # ue:daily:{user}:{date}), not the parse-phase
                        # title-derived guess — the tracker row feeds deletion
                        # propagation, and a uid that matches no node makes
                        # file-deletion a silent no-op on the entity side (G10).
                        if result_data.get("uid"):
                            file_entity_map[str(ue_path)] = (
                                EntityType.USER_ENTRY,
                                str(result_data["uid"]),
                            )
                            # MOC user_entry (e.g. a knowledge-pipeline map):
                            # collect against the REAL service uid; the edge
                            # pass runs end-of-sync (ingest_file deferred it).
                            if ue_entity.get("moc") is True:
                                moc_items.append(
                                    (
                                        str(result_data["uid"]),
                                        list(ue_entity.get("_moc_links") or []),
                                        ue_path,
                                        frontmatter_organizes_targets(ue_entity),
                                    )
                                )
                        # Per-line extraction problems (parse/creation/link
                        # errors) that did not fail the file: surface as
                        # warnings (G10) — the entry persisted and stays
                        # tracked, but the user must see what was dropped.
                        for warning in result_data.get("extraction_warnings") or []:
                            validation_warnings.append(f"{ue_path.name}: {warning}")
        else:
            logger.warning(
                f"{len(user_entry_entities)} UserEntry file(s) found in directory ingest "
                "but ingest_file_fn is not wired — skipping (no OWNS edge or pipeline). "
                "Wire UnifiedIngestionService.user_entry_service to enable UserEntry routing."
            )

    # Batch ingest by entity type
    if entities_by_type and bulk_backend is None:
        return Result.fail(
            Errors.validation(
                "Bulk upsert backend required for ingestion",
                field="bulk_backend",
            )
        )

    # Two-phase ingest: ALL node batches land first, then ALL relationship
    # batches. Relationship Cypher MATCHes targets (no stub nodes), so an edge
    # to an entity persisted by a LATER type batch — or a later row of the same
    # batch — would silently drop. Under incremental sync the source file then
    # hashes as unchanged and the edge is never retried, so "linked on a later
    # re-ingest" never comes. Running edges strictly after every node exists
    # makes one sync produce the complete graph.
    relationship_passes: list[
        tuple[EntityType | NonKuDomain, list[dict[str, Any]], dict[str, RelationshipConfig]]
    ] = []
    for entity_type, entities in entities_by_type.items():
        config = ENTITY_CONFIGS.get(entity_type)
        if not config or bulk_backend is None:
            continue

        await bulk_backend.ensure_constraints(config.entity_label)

        # Strip the engine's private bookkeeping key before persistence — the
        # bulk backend stores every remaining key as a node property, so leaving
        # _file_path on would (and historically did) leak it into the graph.
        # chunks_body_content (PathStep, Ku) content is popped for the same
        # reason: it lives on the :Content node (chunked, post-upsert), never
        # the :Entity node — the same shape ingest_file produces. The popped
        # body is threaded to post_persist_fn keyed by uid so the shared
        # chunk step can run.
        chunk_sources: dict[str, ChunkSource] = {}
        batch_moc_items: list[tuple[str, list[str], Path, list[str]]] = []
        for entity in entities:
            source_path = entity.pop("_file_path", None)
            # MOC link suffixes are engine-private too — popped for every
            # entity (never a node property), collected for the end-of-sync
            # edge pass when the file carried ``moc: true``.
            moc_links = entity.pop("_moc_links", None)
            if moc_links is not None and source_path:
                batch_moc_items.append(
                    (
                        str(entity["uid"]),
                        list(moc_links),
                        Path(source_path),
                        frontmatter_organizes_targets(entity),
                    )
                )
            if config.chunks_body_content:
                # `or ""` — frontmatter `content:` with no value parses to None
                content_body = entity.pop("content", "") or ""
                # Unconditional on purpose: an emptied body must overwrite the
                # previous ingest's word_count (`n += props` never removes
                # omitted keys) and still reach the shared chunk step, whose
                # empty-body branch clears the stale :Content subtree
                # (ADR-074 clear path — same behavior as the single-file door).
                entity["word_count"] = len(content_body.split())
                chunk_sources[entity["uid"]] = ChunkSource(
                    content=content_body,
                    file_format=detect_format(Path(source_path)) if source_path else "markdown",
                    source_path=source_path or "",
                )

        rel_config = config.relationship_config or {}
        result = await bulk_backend.upsert_nodes(
            entity_label=config.entity_label,
            base_label=config.base_label,
            entities=entities,
            relationship_config=rel_config,
            batch_size=batch_size,
        )

        if result.is_ok:
            stats = result.value
            total_nodes_created += stats.nodes_created
            total_nodes_updated += stats.nodes_updated
            logger.info(f"Ingested {len(entities)} {entity_type.value} entities")
            if rel_config:
                relationship_passes.append((entity_type, entities, rel_config))
            if post_persist_fn is not None:
                await post_persist_fn(entity_type, entities, chunk_sources)
            # Only persisted entities get their MOC edge pass — a failed
            # batch would refresh edges against a node that never landed.
            moc_items.extend(batch_moc_items)
        else:
            batch_error = IngestionError(
                file=f"<batch:{entity_type.value}>",
                error=str(result.expect_error()),
                stage="ingestion",
                error_type="database",
                entity_type=entity_type.value,
                suggestion="Check Neo4j connection and database constraints.",
            )
            errors.append(batch_error.to_dict())

    # Phase 2: relationships for every successfully-upserted type batch.
    for entity_type, entities, rel_config in relationship_passes:
        config = ENTITY_CONFIGS.get(entity_type)
        if not config or bulk_backend is None:
            continue
        rel_result = await bulk_backend.create_relationships(
            entity_label=config.entity_label,
            base_label=config.base_label,
            entities=entities,
            relationship_config=rel_config,
            batch_size=batch_size,
        )
        if rel_result.is_ok:
            total_relationships_created += rel_result.value.relationships_created
        else:
            rel_error = IngestionError(
                file=f"<batch:{entity_type.value}>",
                error=str(rel_result.expect_error()),
                stage="relationships",
                error_type="database",
                entity_type=entity_type.value,
                suggestion="Check Neo4j connection and database constraints.",
            )
            errors.append(rel_error.to_dict())

    # Ingest edge files (after entities, so referenced nodes likely exist)
    total_edges_created = 0
    edge_successes: list[dict[str, str]] = []
    if edge_files and write_backend is not None:
        total_edges_created, edge_errors, edge_successes = await _ingest_edge_batch(
            write_backend, edge_files
        )
        errors.extend(edge_errors)
        if total_edges_created:
            logger.info(f"Ingested {total_edges_created} edges from {len(edge_files)} edge files")

    # Update ingestion metadata for successfully processed files
    if tracker is not None and ingestion_mode != "full":
        ingestion_updates: list[tuple[Path, str, str]] = []
        for file_path in files_to_process:
            file_str = str(file_path)
            if file_str in file_entity_map:
                _, uid = file_entity_map[file_str]
                content_hash = tracker.compute_file_hash(file_path)
                ingestion_updates.append((file_path, uid, content_hash))

        # Edge files: tracked with the relationship identity in the uid slot,
        # so unchanged edge files skip on later runs and deleting the file
        # propagates to the relationship.
        for success in edge_successes:
            if not success["source_file"]:
                continue
            edge_path = Path(success["source_file"])
            if not edge_path.exists():
                continue
            identity = edge_identity(success["from_uid"], success["rel_type"], success["to_uid"])
            ingestion_updates.append((edge_path, identity, tracker.compute_file_hash(edge_path)))

        if ingestion_updates:
            await tracker.update_ingestion_metadata_batch(ingestion_updates)
            logger.info(f"Updated ingestion metadata for {len(ingestion_updates)} files")

    # Deletion propagation: vault file deleted -> graph entity/edge deleted.
    # Runs after the metadata updates above so moved/renamed files (already
    # re-ingested under their new path) are recognized as moves, not deletions.
    entities_deleted = 0
    edges_deleted = 0
    stale_metadata_removed = 0
    if tracker is not None and ingestion_mode != "full" and not dry_run:
        reconcile_result = await tracker.reconcile_deletions(
            directory,
            pattern,
            allowlist=allowlist,
            owner_uid=deletion_owner_scope,
        )
        if reconcile_result.is_ok:
            entities_deleted = reconcile_result.value.entities_deleted
            edges_deleted = reconcile_result.value.edges_deleted
            stale_metadata_removed = reconcile_result.value.stale_metadata_removed
            validation_warnings.extend(reconcile_result.value.ownership_mismatches)
            if reconcile_result.value.refusal_warning:
                validation_warnings.append(reconcile_result.value.refusal_warning)
        else:
            errors.append(
                {
                    "message": f"Deletion reconciliation failed: {reconcile_result.error}",
                    "operation": "reconcile_deletions",
                }
            )

    # MOC edge passes — LAST, so every same-sync target has its
    # IngestionMetadata row (stamped above) and deleted files are already
    # retracted. Failure-isolated per MOC: the node persisted; the error is
    # surfaced AND the file's metadata row is dropped so the next sync
    # re-processes it (its hash would otherwise read as unchanged and the
    # edge pass would never retry).
    if moc_items and moc_pass_fn is not None:
        for moc_uid, moc_links, moc_path, moc_protected in moc_items:
            try:
                validation_warnings.extend(
                    await moc_pass_fn(moc_uid, moc_links, moc_path, moc_protected)
                )
            except NEO4J_EXCEPTIONS as e:
                errors.append(
                    IngestionError(
                        file=str(moc_path),
                        error=f"MOC edge pass failed for {moc_uid}: {e}",
                        stage="moc_edge_pass",
                        error_type="database",
                    ).to_dict()
                )
                if tracker is not None and ingestion_mode != "full":
                    await tracker.delete_ingestion_metadata([moc_path])

    duration = (datetime.now() - start_time).total_seconds()

    # Return appropriate stats type based on ingestion mode
    if ingestion_mode == "full":
        return Result.ok(
            IngestionStats(
                total_files=len(all_files),
                successful=len(files_to_process) - len(errors),
                failed=len(errors),
                nodes_created=total_nodes_created,
                nodes_updated=total_nodes_updated,
                relationships_created=total_relationships_created,
                edges_created=total_edges_created,
                duration_seconds=duration,
                files_walled=collection_skips.walled,
                files_unsupported=collection_skips.unsupported,
                warnings=validation_warnings,
                errors=errors if errors else None,
            )
        )
    else:
        return Result.ok(
            IncrementalStats(
                total_files=len(all_files),
                files_checked=len(all_files),
                files_skipped=files_skipped,
                files_ingested=len(files_to_process) - len(errors),
                files_failed=len(errors),
                nodes_created=total_nodes_created,
                nodes_updated=total_nodes_updated,
                relationships_created=total_relationships_created,
                duration_seconds=duration,
                skipped_unchanged=skipped_unchanged,
                skipped_hash_match=skipped_hash_match,
                entities_deleted=entities_deleted,
                edges_deleted=edges_deleted,
                stale_metadata_removed=stale_metadata_removed,
                moves_detected=moves_detected,
                moves=applied_moves,
                files_walled=collection_skips.walled,
                files_unsupported=collection_skips.unsupported,
                warnings=validation_warnings,
                errors=errors if errors else None,
            )
        )


async def ingest_vault(
    vault_path: Path,
    ingest_directory_fn: Any,  # Callable for directory ingestion
    subdirs: list[str] | None = None,
    user_uid: UserUID | None = None,
) -> Result[IngestionStats]:
    """
    Ingest an entire Obsidian vault or specific subdirectories.

    Args:
        vault_path: Root path of Obsidian vault
        ingest_directory_fn: Function to call for directory ingestion
        subdirs: Optional list of subdirectories to ingest

    Returns:
        Result with aggregated IngestionStats
    """
    if not vault_path.exists():
        return Result.fail(Errors.not_found(f"Vault not found: {vault_path}"))

    # Determine directories to ingest
    dirs_to_ingest = [vault_path / subdir for subdir in subdirs] if subdirs else [vault_path]

    # Aggregate stats
    aggregated = IngestionStats()
    all_errors: list[dict[str, str]] = []

    for directory in dirs_to_ingest:
        if not directory.exists():
            logger.warning(f"Directory does not exist: {directory}")
            continue

        result = await ingest_directory_fn(directory, user_uid=user_uid)
        if result.is_ok:
            stats = result.value
            aggregated.total_files += stats.total_files
            aggregated.successful += stats.successful
            aggregated.failed += stats.failed
            aggregated.nodes_created += stats.nodes_created
            aggregated.nodes_updated += stats.nodes_updated
            aggregated.relationships_created += stats.relationships_created
            aggregated.duration_seconds += stats.duration_seconds
            if stats.errors:
                all_errors.extend(stats.errors)

    aggregated.errors = all_errors if all_errors else None

    logger.info(
        f"Vault ingestion complete: {aggregated.total_files} files, "
        f"{aggregated.nodes_created} created, "
        f"{aggregated.nodes_updated} updated"
    )

    return Result.ok(aggregated)


async def ingest_bundle(
    bundle_path: Path,
    parse_yaml_fn: Any,  # Function for YAML parsing
    ingest_file_fn: Any,  # Function for single file ingestion
    find_entity_file_fn: Any,  # Function to find entity file
) -> Result[BundleStats]:
    """
    Ingest a domain bundle using manifest file.

    Bundles are directories with:
    - manifest.yaml: Import order and entity list
    - *.yaml/*.md: Entity definition files

    Args:
        bundle_path: Path to domain bundle directory
        parse_yaml_fn: Function for parsing YAML files
        ingest_file_fn: Function for single file ingestion
        find_entity_file_fn: Function to find entity file by UID

    Returns:
        Result with BundleStats
    """
    try:
        logger.info(f"Ingesting domain bundle: {bundle_path}")

        # Load manifest
        manifest_path = bundle_path / "manifest.yaml"
        if not manifest_path.exists():
            return Result.fail(Errors.not_found(f"No manifest.yaml in bundle: {bundle_path}"))

        manifest_result = parse_yaml_fn(manifest_path)
        if manifest_result.is_error:
            return Result.fail(manifest_result)

        manifest = manifest_result.value
        bundle_name = manifest.get("bundle_name", bundle_path.name)

        stats = BundleStats(bundle_name=bundle_name)

        # Process import order
        import_order = manifest.get("import_order", {})

        for phase_name, entity_uids in sorted(import_order.items()):
            logger.info(f"Processing phase: {phase_name}")

            for uid in entity_uids:
                stats.total_attempted += 1

                # Find file for this UID
                entity_file = find_entity_file_fn(bundle_path, uid)
                if not entity_file:
                    stats.total_failed += 1
                    not_found_error = IngestionError(
                        file=f"<bundle:{uid}>",
                        error=f"File not found for UID: {uid}",
                        stage="file_resolution",
                        error_type="not_found",
                        suggestion=f"Create file named '{uid}.yaml' or '{uid}.md' in bundle directory.",
                    )
                    stats.errors.append(not_found_error.to_dict())
                    continue

                # Ingest file
                result = await ingest_file_fn(entity_file)
                if result.is_ok:
                    stats.total_successful += 1
                    stats.entities_created.append(uid)
                else:
                    stats.total_failed += 1
                    ingest_error = IngestionError(
                        file=str(entity_file),
                        error=str(result.expect_error()),
                        stage="ingestion",
                        error_type="system",
                        suggestion="Check the file content and Neo4j connection.",
                    )
                    stats.errors.append(ingest_error.to_dict())

        logger.info(
            f"Bundle ingestion complete: {stats.total_successful}/{stats.total_attempted} succeeded"
        )

        return Result.ok(stats)

    except (*FILE_IO_EXCEPTIONS, *PARSING_EXCEPTIONS) as e:
        logger.error(
            "Failed to ingest bundle - returning error",
            extra={
                "bundle_path": str(bundle_path),
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        return Result.fail(
            Errors.system(
                f"Bundle ingestion failed: {e}",
                operation="ingest_bundle",
                details={"path": str(bundle_path)},
            )
        )
    except Exception as e:  # safety-net: catch unexpected errors
        logger.error(
            "Failed to ingest bundle - unexpected error",
            extra={
                "bundle_path": str(bundle_path),
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        return Result.fail(
            Errors.system(
                f"Bundle ingestion failed: {e}",
                operation="ingest_bundle",
                details={"path": str(bundle_path)},
            )
        )


def find_entity_file(
    bundle_path: Path,
    uid: str,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> Path | None:
    """
    Find file for given UID in bundle.

    Searches for:
    1. File named after UID (e.g., ku.machine-learning.yaml)
    2. File containing matching UID in content

    Args:
        bundle_path: Path to bundle directory
        uid: Entity UID to find
        max_file_size_bytes: Maximum file size to consider

    Returns:
        Path to file or None
    """
    # Normalize UID for filename matching
    normalized_uid = normalize_uid(uid)

    # Try direct filename match
    for ext in (".yaml", ".yml", ".md"):
        direct_path = bundle_path / f"{normalized_uid}{ext}"
        if direct_path.exists():
            return direct_path

    # Search files for UID (skip files exceeding size limit)
    for yaml_file in bundle_path.glob("*.yaml"):
        if yaml_file.name == "manifest.yaml":
            continue
        try:
            # Skip oversized files during search
            if check_file_size(yaml_file, max_file_size_bytes).is_error:
                continue
            content = yaml_file.read_text()
            data = yaml.safe_load(content)
            if data and normalize_uid(data.get("uid", "")) == normalized_uid:
                return yaml_file
        except (*FILE_IO_EXCEPTIONS, *PARSING_EXCEPTIONS) as e:
            # Log but continue searching - file may be malformed but others may match
            logger.debug(
                "Error reading YAML file during entity search",
                extra={
                    "file": str(yaml_file),
                    "uid": uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )

    for md_file in bundle_path.glob("*.md"):
        try:
            # Skip oversized files during search
            if check_file_size(md_file, max_file_size_bytes).is_error:
                continue
            content = md_file.read_text()
            raw_yaml, _ = split_frontmatter(content)
            if raw_yaml is not None:
                frontmatter = yaml.safe_load(raw_yaml)
                if frontmatter and normalize_uid(frontmatter.get("uid", "")) == normalized_uid:
                    return md_file
        except (*FILE_IO_EXCEPTIONS, *PARSING_EXCEPTIONS) as e:
            # Log but continue searching - file may be malformed but others may match
            logger.debug(
                "Error reading markdown file during entity search",
                extra={
                    "file": str(md_file),
                    "uid": uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )

    return None


__all__ = [
    "ProgressCallback",
    "collect_files",
    "create_error",
    "find_entity_file",
    "ingest_bundle",
    "ingest_directory",
    "ingest_vault",
    "parse_file_for_batch",
    "parse_file_sync",
]
