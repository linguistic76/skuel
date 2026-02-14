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

import asyncio
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from core.ingestion.bulk_ingestion import BulkIngestionEngine
from core.models.enums.entity_enums import NonKuDomain
from core.models.enums.ku_enums import KuType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .config import DEFAULT_MAX_CONCURRENT_PARSING, DEFAULT_MAX_FILE_SIZE_BYTES, ENTITY_CONFIGS
from .detector import detect_entity_type, detect_format
from .ingestion_tracker import IngestionTracker
from .parser import FRONTMATTER_PATTERN, check_file_size, parse_markdown, parse_yaml
from .preparer import normalize_uid, prepare_entity_data
from .types import BundleStats, DryRunPreview, IncrementalStats, IngestionError, IngestionStats
from .validator import validate_entity_data, validate_relationship_targets, validate_required_fields

logger = get_logger("skuel.services.ingestion.batch")

# Type alias for progress callback
ProgressCallback = Callable[[int, int, str], None]  # (current, total, current_file)


def _file_mtime(path: Path) -> float:
    """Get file modification time for sorting."""
    return path.stat().st_mtime


def collect_files(directory: Path, pattern: str = "*") -> list[Path]:
    """
    Collect all supported files (MD, YAML, YML) from a directory.

    Simplifies the confusing pattern matching logic by providing clear semantics:
    - "*" or "**/*" → all supported files recursively
    - "*.md" → only markdown files recursively
    - "specific-name" → files with that exact stem

    Args:
        directory: Directory to search
        pattern: Glob pattern (default "*" for all files)

    Returns:
        List of file paths sorted by modification time (newest first)
    """
    all_files: list[Path] = []

    # Determine search behavior based on pattern
    if pattern in ("*", "**/*"):
        # Match all supported file types
        all_files.extend(directory.glob("**/*.md"))
        all_files.extend(directory.glob("**/*.yaml"))
        all_files.extend(directory.glob("**/*.yml"))
    elif pattern.endswith(".md"):
        # Markdown files only
        all_files.extend(directory.glob(f"**/{pattern}"))
    elif pattern.endswith((".yaml", ".yml")):
        # YAML files only
        all_files.extend(directory.glob(f"**/{pattern}"))
    else:
        # Specific file name - try all extensions
        all_files.extend(directory.glob(f"**/{pattern}.md"))
        all_files.extend(directory.glob(f"**/{pattern}.yaml"))
        all_files.extend(directory.glob(f"**/{pattern}.yml"))

    # Sort by modification time (newest first) for better cache behavior
    return sorted(all_files, key=_file_mtime, reverse=True)


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
    driver: Any,
    uids: list[str],
) -> dict[str, bool]:
    """
    Check which UIDs already exist in Neo4j.

    Args:
        driver: Neo4j async driver
        uids: List of UIDs to check

    Returns:
        Dictionary mapping uid -> exists (bool)
    """
    if not uids:
        return {}

    query = """
    UNWIND $uids AS uid
    OPTIONAL MATCH (n {uid: uid})
    RETURN uid, n IS NOT NULL AS exists
    """

    result = await driver.execute_query(
        query,
        {"uids": uids},
        database_="neo4j",
    )

    return {record["uid"]: record["exists"] for record in result.records}


def parse_file_sync(
    file_path: Path,
    default_user_uid: str = "user:system",
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> tuple[KuType | NonKuDomain, dict[str, Any], None] | tuple[None, None, dict[str, Any]]:
    """
    Synchronous file parsing for use in thread pool.

    Handles format detection, parsing, validation, and data preparation.
    Returns rich error context via IngestionError on failure.

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
                    error=err.user_message or err.message,
                    stage="parsing",
                    error_type="parse",
                    suggestion="Check YAML frontmatter syntax between --- markers.",
                )
                return (None, None, error.to_dict())
            data, body = parse_result.value
        else:
            parse_result = parse_yaml(file_path, max_file_size_bytes)
            if parse_result.is_error:
                err = parse_result.expect_error()
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
                    error=err.user_message or err.message,
                    stage="parsing",
                    error_type="parse",
                    line_number=line_num,
                    column=col,
                    suggestion="Check YAML syntax: proper indentation, colons, and quotes.",
                )
                return (None, None, error.to_dict())
            data = parse_result.value
            body = None

        # Stage 3: Entity type detection
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

        # Stage 4: Pre-preparation validation
        validation_result = validate_required_fields(entity_type, data, file_path)
        if validation_result.is_error:
            err = validation_result.expect_error()
            error = create_error(
                file_path=file_path,
                error=err.user_message or err.message,
                stage="validation",
                error_type="validation",
                entity_type=entity_type_str,
                field=getattr(err, "field", None),
                suggestion=f"Add the missing required fields for {entity_type_str} entity.",
            )
            return (None, None, error.to_dict())

        # Stage 5: Data preparation
        try:
            entity_data = prepare_entity_data(entity_type, data, body, file_path, default_user_uid)
        except Exception as e:
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
                error=err.user_message or err.message,
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
    except Exception as e:
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
    default_user_uid: str = "user:system",
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> tuple[KuType | NonKuDomain, dict[str, Any], None] | tuple[None, None, dict[str, Any]]:
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
            )
        except Exception as e:
            error = create_error(
                file_path=file_path,
                error=str(e),
                stage="thread_dispatch",
                error_type="exception",
                suggestion="This is an unexpected error. Check the file format and encoding.",
            )
            return (None, None, error.to_dict())


async def ingest_directory(
    directory: Path,
    engines: dict[KuType | NonKuDomain, BulkIngestionEngine[Any]],  # noqa: ARG001 - Modified by get_engine
    get_engine: Any,  # Callable to get/create engine
    driver: Any = None,  # Neo4j driver for ingestion tracking
    pattern: str = "*",
    batch_size: int = 500,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT_PARSING,
    default_user_uid: str = "user:system",
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ingestion_mode: Literal["full", "incremental", "smart"] = "full",
    validate_targets: bool = False,
    progress_callback: ProgressCallback | None = None,
    dry_run: bool = False,
) -> Result[IngestionStats | IncrementalStats | DryRunPreview]:
    """
    Ingest all supported files in a directory.

    Processes both MD and YAML files in PARALLEL, batching by entity type
    for efficient bulk operations.

    Args:
        directory: Directory to scan
        engines: Engine cache (keyed by KuType | NonKuDomain) - populated by get_engine as side effect
        get_engine: Function to get/create engine for entity type (modifies engines dict)
        driver: Neo4j driver (required for ingestion_mode != "full")
        pattern: Glob pattern for files (default: "*" for all supported)
        batch_size: Batch size for bulk operations
        max_concurrent: Maximum concurrent file parsing operations (default: 20)
        default_user_uid: Default user UID
        max_file_size_bytes: Maximum file size
        ingestion_mode: Ingestion strategy:
            - "full": Process all files (default, backward compatible)
            - "incremental": Skip files with unchanged content hash
            - "smart": Skip files with unchanged mtime (fast), verify with hash if changed
        validate_targets: If True, validate relationship targets exist before ingestion
        progress_callback: Optional callback for progress reporting (current, total, current_file)
        dry_run: If True, validates and previews changes without writing to Neo4j

    Returns:
        Result with IngestionStats (full mode), IncrementalStats (incremental/smart mode), or DryRunPreview (dry-run mode)
    """
    start_time = datetime.now()

    if not directory.exists():
        return Result.fail(Errors.not_found(f"Directory not found: {directory}"))

    # Validate driver is provided for incremental modes and dry-run
    if ingestion_mode != "full" and driver is None:
        return Result.fail(
            Errors.validation(
                "Neo4j driver required for incremental/smart ingestion mode",
                field="driver",
            )
        )

    if dry_run and driver is None:
        return Result.fail(
            Errors.validation(
                "Neo4j driver required for dry-run mode (to check existing entities)",
                field="driver",
            )
        )

    # Collect all supported files using simplified pattern matching
    all_files = collect_files(directory, pattern)

    if not all_files:
        if ingestion_mode == "full":
            return Result.ok(
                IngestionStats(
                    total_files=0,
                    duration_seconds=0,
                    errors=[{"message": "No files found"}],
                )
            )
        else:
            return Result.ok(
                IncrementalStats(
                    total_files=0,
                    duration_seconds=0,
                    errors=[{"message": "No files found"}],
                )
            )

    # Initialize ingestion tracking for incremental modes
    files_to_process = all_files
    files_skipped = 0
    skipped_unchanged = 0
    skipped_hash_match = 0
    tracker: IngestionTracker | None = None

    if ingestion_mode != "full" and driver is not None:
        tracker = IngestionTracker(driver)
        await tracker.ensure_constraints()

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
        # All files are up to date
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
            )
        )

    logger.info(
        f"Processing {len(files_to_process)} files from {directory} (max_concurrent={max_concurrent})"
    )

    # PARALLEL PARSING: Process all files concurrently with semaphore limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    parse_tasks = [
        parse_file_for_batch(fp, semaphore, default_user_uid, max_file_size_bytes)
        for fp in files_to_process
    ]
    parse_results = await asyncio.gather(*parse_tasks)

    # Group entities by type for batch processing (keyed by KuType | NonKuDomain)
    entities_by_type: dict[KuType | NonKuDomain, list[dict[str, Any]]] = {}
    file_entity_map: dict[
        str, tuple[KuType | NonKuDomain, str]
    ] = {}  # file_path -> (entity_type, uid)
    errors: list[dict[str, str]] = []

    for i, (entity_type, entity_data, error) in enumerate(parse_results):
        if progress_callback:
            progress_callback(i + 1, len(files_to_process), str(files_to_process[i]))

        if error is not None:
            errors.append(error)
        elif entity_type is not None and entity_data is not None:
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            entities_by_type[entity_type].append(entity_data)
            # Track file -> entity mapping for ingestion metadata updates
            file_entity_map[str(files_to_process[i])] = (entity_type, entity_data.get("uid", ""))

    # Optional: Validate relationship targets before ingestion
    validation_warnings: list[str] = []
    if validate_targets and driver is not None:
        for entity_type, entities in entities_by_type.items():
            config = ENTITY_CONFIGS.get(entity_type)
            if config and config.relationship_config:
                validation_result = await validate_relationship_targets(
                    entities, config.relationship_config, driver
                )
                if validation_result.is_ok and not validation_result.value.valid:
                    for warning in validation_result.value.warnings:
                        logger.warning(f"[{entity_type.value}] {warning}")
                        validation_warnings.append(warning)

    # DRY-RUN MODE: Preview changes without writing to Neo4j
    if dry_run and driver is not None:
        # Collect all UIDs to check existence
        all_uids = []
        for entities in entities_by_type.values():
            all_uids.extend(entity.get("uid", "") for entity in entities if entity.get("uid"))

        # Check which entities already exist
        exists_map = await check_existing_entities(driver, all_uids)

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

    # Batch ingest by entity type
    total_nodes_created = 0
    total_nodes_updated = 0
    total_relationships_created = 0

    for entity_type, entities in entities_by_type.items():
        config = ENTITY_CONFIGS.get(entity_type)
        if not config:
            continue

        engine = get_engine(entity_type)
        await engine.ensure_constraints()

        rel_config = config.relationship_config or {}
        result = await engine.upsert_with_relationships(
            entities=entities,
            relationship_config=rel_config,
            batch_size=batch_size,
        )

        if result.is_ok:
            stats = result.value
            total_nodes_created += stats.nodes_created
            total_nodes_updated += stats.nodes_updated
            total_relationships_created += stats.relationships_created
            logger.info(f"Ingested {len(entities)} {entity_type.value} entities")
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

    # Update ingestion metadata for successfully processed files
    if tracker is not None and ingestion_mode != "full":
        ingestion_updates: list[tuple[Path, str, str]] = []
        for file_path in files_to_process:
            file_str = str(file_path)
            if file_str in file_entity_map:
                _, uid = file_entity_map[file_str]
                content_hash = tracker.compute_file_hash(file_path)
                ingestion_updates.append((file_path, uid, content_hash))

        if ingestion_updates:
            await tracker.update_ingestion_metadata_batch(ingestion_updates)
            logger.info(f"Updated ingestion metadata for {len(ingestion_updates)} files")

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
                duration_seconds=duration,
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
                errors=errors if errors else None,
            )
        )


async def ingest_vault(
    vault_path: Path,
    ingest_directory_fn: Any,  # Callable for directory ingestion
    subdirs: list[str] | None = None,
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

        result = await ingest_directory_fn(directory)
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
            return Result.fail(manifest_result.expect_error())

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

    except Exception as e:
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
        except Exception as e:
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
            match = FRONTMATTER_PATTERN.match(content)
            if match:
                frontmatter = yaml.safe_load(match.group(1))
                if frontmatter and normalize_uid(frontmatter.get("uid", "")) == normalized_uid:
                    return md_file
        except Exception as e:
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
