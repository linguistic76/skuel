"""
Ingestion Validator - Validation Pipeline
==========================================

Complete validation sub-system for ingestion operations.
Provides pre-preparation and post-preparation validation,
plus dry-run capabilities for previewing ingestion.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from neo4j import AsyncDriver

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .config import DEFAULT_MAX_CONCURRENT_PARSING, ENTITY_CONFIGS, collect_files
from .detector import detect_entity_type, detect_format
from .parser import parse_markdown, parse_yaml
from .preparer import prepare_entity_data
from .types import DirectoryValidationResult, RelationshipValidationResult, ValidationResult

logger = get_logger("skuel.services.ingestion.validator")


def _by_count_desc(item: tuple[str, int]) -> int:
    """Sort key for (uid, count) tuples - descending by count."""
    return -item[1]


def validate_required_fields(
    entity_type: EntityType | NonKuDomain,
    data: dict[str, Any],
    file_path: Path,
) -> Result[None]:
    """
    Validate that all required fields are present for the entity type.

    Fail-fast validation ensures clear errors before Neo4j operations.
    Called BEFORE prepare_entity_data.

    Args:
        entity_type: EntityType | NonKuDomain enum value
        data: Entity data dictionary to validate
        file_path: Source file path (for error context)

    Returns:
        Result[None] - Ok if valid, Fail with validation error if missing fields
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        return Result.fail(
            Errors.validation(
                f"Unknown entity type: {entity_type.value}",
                field="type",
                user_message=f"File {file_path.name} has unsupported type '{entity_type.value}'",
            )
        )

    if not config.required_fields:
        return Result.ok(None)

    missing_fields: list[str] = []
    for field in config.required_fields:
        # Check if field exists and has a truthy value
        # Special handling: 'content' can come from body, 'title' can be generated
        if field == "content":
            # Content will be populated from markdown body - skip validation here
            # It's validated after prepare_entity_data
            continue
        if field == "title" or field == "name":
            # Title/name can be auto-generated from filename - skip validation here
            continue

        if field not in data or data[field] is None or data[field] == "":
            missing_fields.append(field)

    if missing_fields:
        fields_str = ", ".join(f"'{f}'" for f in missing_fields)
        return Result.fail(
            Errors.validation(
                f"Missing required fields: {fields_str}",
                field=missing_fields[0],  # Primary field for error
                user_message=(
                    f"File {file_path.name} ({entity_type.value}) is missing required fields: {fields_str}. "
                    f"Please add these fields to the frontmatter or YAML content."
                ),
            )
        )

    return Result.ok(None)


def validate_entity_data(
    entity_type: EntityType | NonKuDomain,
    entity_data: dict[str, Any],
    file_path: Path,
) -> Result[None]:
    """
    Validate prepared entity data has all required fields populated.

    Called AFTER prepare_entity_data to ensure auto-generated fields are present.

    Args:
        entity_type: EntityType | NonKuDomain enum value
        entity_data: Prepared entity data (after defaults applied)
        file_path: Source file path (for error context)

    Returns:
        Result[None] - Ok if valid, Fail with validation error if missing
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config or not config.required_fields:
        return Result.ok(None)

    missing_fields: list[str] = []
    for field in config.required_fields:
        value = entity_data.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            missing_fields.append(field)

    if missing_fields:
        fields_str = ", ".join(f"'{f}'" for f in missing_fields)
        return Result.fail(
            Errors.validation(
                f"Entity missing required fields after preparation: {fields_str}",
                field=missing_fields[0],
                user_message=(
                    f"File {file_path.name} ({entity_type.value}) could not provide required fields: {fields_str}. "
                    f"For 'content', ensure the markdown body is not empty. "
                    f"For 'title'/'name', add it to frontmatter or ensure filename is valid."
                ),
            )
        )

    return Result.ok(None)


async def validate_file(
    file_path: Path,
    default_user_uid: str = "user:system",
    max_file_size_bytes: int | None = None,
) -> Result[ValidationResult]:
    """
    Validate a file without persisting to Neo4j (dry-run mode).

    Performs all parsing, type detection, and validation that would occur
    during ingestion, but stops before writing to the database. Use this
    to preview what would be ingested and catch errors early.

    Args:
        file_path: Path to file to validate
        default_user_uid: Default user UID for multi-tenant entities
        max_file_size_bytes: Maximum file size (optional, uses default if None)

    Returns:
        Result[ValidationResult] with validation details and prepared data preview
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        if not file_path.exists():
            return Result.ok(
                ValidationResult(
                    valid=False,
                    file_path=str(file_path),
                    entity_type="unknown",
                    uid="",
                    errors=[f"File not found: {file_path}"],
                )
            )

        # Detect format
        try:
            file_format = detect_format(file_path)
        except ValueError as e:
            return Result.ok(
                ValidationResult(
                    valid=False,
                    file_path=str(file_path),
                    entity_type="unknown",
                    uid="",
                    errors=[str(e)],
                )
            )

        # Parse file
        if file_format == "markdown":
            if max_file_size_bytes:
                parse_result = parse_markdown(file_path, max_file_size_bytes)
            else:
                parse_result = parse_markdown(file_path)
            if parse_result.is_error:
                return Result.ok(
                    ValidationResult(
                        valid=False,
                        file_path=str(file_path),
                        entity_type="unknown",
                        uid="",
                        format=file_format,
                        errors=[str(parse_result.expect_error())],
                    )
                )
            data, body = parse_result.value
        else:  # yaml
            if max_file_size_bytes:
                parse_result = parse_yaml(file_path, max_file_size_bytes)
            else:
                parse_result = parse_yaml(file_path)
            if parse_result.is_error:
                return Result.ok(
                    ValidationResult(
                        valid=False,
                        file_path=str(file_path),
                        entity_type="unknown",
                        uid="",
                        format=file_format,
                        errors=[str(parse_result.expect_error())],
                    )
                )
            data = parse_result.value
            body = None

        # Detect entity type
        try:
            entity_type = detect_entity_type(data, file_path)
        except ValueError as e:
            return Result.ok(
                ValidationResult(
                    valid=False,
                    file_path=str(file_path),
                    entity_type="unknown",
                    uid="",
                    format=file_format,
                    errors=[str(e)],
                )
            )

        config = ENTITY_CONFIGS.get(entity_type)
        if not config:
            return Result.ok(
                ValidationResult(
                    valid=False,
                    file_path=str(file_path),
                    entity_type=entity_type.value,
                    uid="",
                    format=file_format,
                    errors=[f"Unsupported entity type: {entity_type.value}"],
                )
            )

        # Validate required fields before preparation
        validation_result = validate_required_fields(entity_type, data, file_path)
        if validation_result.is_error:
            error = validation_result.expect_error()
            errors.append(error.user_message or error.message)

        # Prepare entity data (even if validation failed, to show what would be created)
        try:
            entity_data = prepare_entity_data(entity_type, data, body, file_path, default_user_uid)
        except Exception as e:
            errors.append(f"Failed to prepare entity data: {e}")
            return Result.ok(
                ValidationResult(
                    valid=False,
                    file_path=str(file_path),
                    entity_type=entity_type.value,
                    uid="",
                    format=file_format,
                    errors=errors,
                )
            )

        # Validate entity data after preparation
        validation_result = validate_entity_data(entity_type, entity_data, file_path)
        if validation_result.is_error:
            error = validation_result.expect_error()
            errors.append(error.user_message or error.message)

        # Extract relationship targets for preview
        relationship_targets: dict[str, list[str]] = {}
        if config.relationship_config:
            for key in config.relationship_config:
                if key in entity_data:
                    targets = entity_data[key]
                    if isinstance(targets, list):
                        relationship_targets[key] = targets
                    elif isinstance(targets, str):
                        relationship_targets[key] = [targets]

        # Add warnings for potential issues
        if not entity_data.get("title") and not entity_data.get("name"):
            warnings.append("No title or name - will use filename as fallback")

        if config.requires_user_uid and entity_data.get("user_uid") == "user:system":
            warnings.append("Using default system user_uid - consider specifying user_uid")

        return Result.ok(
            ValidationResult(
                valid=len(errors) == 0,
                file_path=str(file_path),
                entity_type=entity_type.value,
                uid=entity_data.get("uid", ""),
                title=entity_data.get("title") or entity_data.get("name"),
                format=file_format,
                warnings=warnings,
                errors=errors,
                prepared_data=entity_data,
                relationship_targets=relationship_targets,
            )
        )

    except Exception as e:
        logger.error(f"Validation failed for {file_path}: {e}", exc_info=True)
        return Result.ok(
            ValidationResult(
                valid=False,
                file_path=str(file_path),
                entity_type="unknown",
                uid="",
                errors=[f"Unexpected error: {e}"],
            )
        )


async def validate_directory(
    directory: Path,
    pattern: str = "*",
    max_concurrent: int = DEFAULT_MAX_CONCURRENT_PARSING,
    default_user_uid: str = "user:system",
    max_file_size_bytes: int | None = None,
) -> Result[DirectoryValidationResult]:
    """
    Validate all files in a directory without persisting (dry-run mode).

    Uses PARALLEL validation for faster processing of large directories.

    Args:
        directory: Directory to validate
        pattern: Glob pattern for file matching (default: all files)
        max_concurrent: Maximum concurrent validation operations (default: 20)
        default_user_uid: Default user UID for multi-tenant entities
        max_file_size_bytes: Maximum file size (optional)

    Returns:
        Result[DirectoryValidationResult] with validation results for all files
    """
    start_time = datetime.now()

    if not directory.exists():
        return Result.fail(Errors.not_found(f"Directory not found: {directory}"))

    # Collect files using shared logic from batch module
    all_files = collect_files(directory, pattern)

    if not all_files:
        return Result.ok(
            DirectoryValidationResult(
                total_files=0,
                valid_files=0,
                invalid_files=0,
                results=[],
                duration_seconds=0.0,
            )
        )

    logger.info(
        f"Validating {len(all_files)} files from {directory} (max_concurrent={max_concurrent})"
    )

    # PARALLEL VALIDATION: Process all files concurrently with semaphore limiting
    semaphore = asyncio.Semaphore(max_concurrent)

    async def validate_with_semaphore(file_path: Path) -> ValidationResult:
        async with semaphore:
            result = await validate_file(file_path, default_user_uid, max_file_size_bytes)
            if result.is_ok:
                return result.value
            else:
                return ValidationResult(
                    valid=False,
                    file_path=str(file_path),
                    entity_type="unknown",
                    uid="",
                    errors=[str(result.expect_error())],
                )

    validation_tasks = [validate_with_semaphore(fp) for fp in all_files]
    results: list[ValidationResult] = await asyncio.gather(*validation_tasks)

    valid_count = sum(1 for r in results if r.valid)
    invalid_count = len(results) - valid_count

    duration = (datetime.now() - start_time).total_seconds()

    return Result.ok(
        DirectoryValidationResult(
            total_files=len(all_files),
            valid_files=valid_count,
            invalid_files=invalid_count,
            results=results,
            duration_seconds=duration,
        )
    )


async def validate_relationship_targets(
    entities: list[dict[str, Any]],
    relationship_config: dict[str, Any],
    driver: AsyncDriver,
) -> Result[RelationshipValidationResult]:
    """
    Validate that all UIDs referenced in relationships actually exist in Neo4j.

    Call this before ingestion to catch missing targets early. Missing targets
    would otherwise create orphan edges or silently fail.

    Args:
        entities: List of prepared entity dicts (with connections.* keys)
        relationship_config: Relationship configuration from ENTITY_CONFIGS
        driver: Neo4j async driver

    Returns:
        Result[RelationshipValidationResult] with validation details

    Example:
        result = await validate_relationship_targets(
            entities=[{"uid": "ku.test", "connections.requires": ["ku.prereq"]}],
            relationship_config=ENTITY_CONFIGS[EntityType.LESSON].relationship_config,
            driver=driver,
        )
        if not result.value.valid:
            logger.warning(f"Missing targets: {result.value.missing_uids}")
    """
    validation = RelationshipValidationResult(valid=True)

    if not relationship_config or not entities:
        return Result.ok(validation)

    # Collect all referenced UIDs by their target label
    uids_by_label: dict[str, set[str]] = {}

    # Track which entity references which UIDs (for error reporting)
    references: list[tuple[str, str, str]] = []  # (source_uid, target_uid, target_label)

    for entity in entities:
        source_uid = entity.get("uid", "unknown")

        for field_name, config in relationship_config.items():
            targets = entity.get(field_name, [])
            if not targets:
                continue

            # Ensure targets is a list
            if isinstance(targets, str):
                targets = [targets]

            target_label = config.get("target_label", "Unknown")

            for target_uid in targets:
                validation.total_references += 1

                if target_label not in uids_by_label:
                    uids_by_label[target_label] = set()
                uids_by_label[target_label].add(target_uid)

                references.append((source_uid, target_uid, target_label))

    if not uids_by_label:
        return Result.ok(validation)

    # Query Neo4j to find which UIDs exist
    existing_uids: set[str] = set()

    # Use driver.execute_query which accepts dynamic strings
    # The label is derived from ENTITY_CONFIGS so it's trusted
    try:
        for label, uids in uids_by_label.items():
            records, _, _ = await driver.execute_query(
                f"UNWIND $uids AS uid MATCH (n:{label} {{uid: uid}}) RETURN n.uid AS uid",
                uids=list(uids),
            )
            existing_uids.update(r["uid"] for r in records)

    except Exception as e:
        logger.error(f"Failed to validate relationship targets: {e}")
        return Result.fail(
            Errors.database(
                operation="validate_relationship_targets",
                message=f"Failed to validate relationship targets: {e}",
            )
        )

    # Check each reference against existing UIDs
    for source_uid, target_uid, _target_label in references:
        if target_uid in existing_uids:
            validation.valid_references += 1
        else:
            validation.add_missing(source_uid, target_uid)
            validation.valid = False

    # Generate warnings for frequently referenced missing UIDs
    if validation.missing_uids:
        uid_counts: dict[str, int] = {}
        for targets in validation.missing_by_entity.values():
            for target in targets:
                uid_counts[target] = uid_counts.get(target, 0) + 1

        for uid, count in sorted(uid_counts.items(), key=_by_count_desc):
            if count > 1:
                validation.warnings.append(
                    f"'{uid}' referenced by {count} entities but does not exist"
                )

    return Result.ok(validation)


_VALID_POLARITIES = {-1, 0, 1}
_VALID_TEMPORALITIES = {"minutes", "hours", "days", "chronic"}
_VALID_SOURCES = {"self_observation", "research", "teacher", "clinical"}


def validate_edge_data(data: dict[str, Any]) -> Result[None]:
    """
    Validate that edge data has all required fields and valid values.

    Required: from, to, relationship
    Optional: confidence (0.0-1.0), polarity (-1/0/1),
              temporality (minutes/hours/days/chronic),
              source (self_observation/research/teacher/clinical)

    Args:
        data: Parsed edge YAML data

    Returns:
        Result[None] - Ok if valid, Fail with validation error
    """
    errors: list[str] = []

    # Required fields
    if not data.get("from"):
        errors.append("Missing required field: 'from'")
    if not data.get("to"):
        errors.append("Missing required field: 'to'")
    if not data.get("relationship"):
        errors.append("Missing required field: 'relationship'")
    elif not RelationshipName.is_valid(data["relationship"]):
        errors.append(f"Unknown relationship type: '{data['relationship']}'")

    # Optional field validation
    confidence = data.get("confidence")
    if confidence is not None:
        try:
            conf_val = float(confidence)
            if not 0.0 <= conf_val <= 1.0:
                errors.append(f"confidence must be 0.0-1.0, got {conf_val}")
        except (TypeError, ValueError):
            errors.append(f"confidence must be a number, got '{confidence}'")

    polarity = data.get("polarity")
    if polarity is not None:
        try:
            pol_val = int(polarity)
            if pol_val not in _VALID_POLARITIES:
                errors.append(f"polarity must be -1, 0, or 1, got {pol_val}")
        except (TypeError, ValueError):
            errors.append(f"polarity must be an integer, got '{polarity}'")

    temporality = data.get("temporality")
    if temporality is not None and temporality not in _VALID_TEMPORALITIES:
        errors.append(
            f"temporality must be one of {sorted(_VALID_TEMPORALITIES)}, got '{temporality}'"
        )

    source = data.get("source")
    if source is not None and source not in _VALID_SOURCES:
        errors.append(f"source must be one of {sorted(_VALID_SOURCES)}, got '{source}'")

    if errors:
        return Result.fail(
            Errors.validation(
                "; ".join(errors),
                field="edge",
                user_message=f"Edge validation failed: {'; '.join(errors)}",
            )
        )

    return Result.ok(None)


__all__ = [
    "validate_directory",
    "validate_edge_data",
    "validate_entity_data",
    "validate_file",
    "validate_relationship_targets",
    "validate_required_fields",
]
