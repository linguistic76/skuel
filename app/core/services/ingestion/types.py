"""
Ingestion Types - Data Classes for Ingestion Operations
========================================================

Pure data carriers for ingestion statistics, validation results, and errors.
No logic, no dependencies on service implementations.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IngestionStats:
    """Statistics from an ingestion operation."""

    total_files: int = 0
    successful: int = 0
    failed: int = 0
    nodes_created: int = 0
    nodes_updated: int = 0
    relationships_created: int = 0
    duration_seconds: float = 0.0
    errors: list[dict[str, Any]] | None = field(default_factory=list)

    @property
    def files_per_second(self) -> float:
        """Calculate files processed per second."""
        if self.duration_seconds == 0:
            return 0.0
        return self.total_files / self.duration_seconds


@dataclass
class BundleStats:
    """Statistics from a domain bundle ingestion."""

    bundle_name: str
    total_attempted: int = 0
    total_successful: int = 0
    total_failed: int = 0
    entities_created: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationResult:
    """
    Result from dry-run validation of a file or directory.

    Allows previewing what would be ingested without writing to Neo4j.
    Use validate_file() or validate_directory() for dry-run validation.
    """

    valid: bool
    file_path: str
    entity_type: str  # EntityType/NonKuDomain value for JSON serialization
    uid: str
    title: str | None = None
    format: str = "unknown"  # "markdown" or "yaml"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Preview of prepared data (without actually ingesting)
    prepared_data: dict[str, Any] | None = None
    # Relationship targets that would be created
    relationship_targets: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class DirectoryValidationResult:
    """Result from validating a directory of files."""

    total_files: int = 0
    valid_files: int = 0
    invalid_files: int = 0
    results: list[ValidationResult] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def all_valid(self) -> bool:
        """Check if all files are valid."""
        return self.invalid_files == 0 and self.total_files > 0


@dataclass
class RelationshipValidationResult:
    """
    Result from validating relationship targets.

    Checks that all UIDs referenced in connections actually exist in Neo4j.
    Use validate_relationship_targets() before ingestion to catch missing targets.
    """

    valid: bool
    total_references: int = 0
    valid_references: int = 0
    missing_references: int = 0
    # Missing targets grouped by source entity UID
    missing_by_entity: dict[str, list[str]] = field(default_factory=dict)
    # All missing UIDs (unique)
    missing_uids: set[str] = field(default_factory=set)
    # Warnings (e.g., "ku.prereq referenced by 3 entities but does not exist")
    warnings: list[str] = field(default_factory=list)

    def add_missing(self, source_uid: str, missing_target: str) -> None:
        """Add a missing relationship target."""
        if source_uid not in self.missing_by_entity:
            self.missing_by_entity[source_uid] = []
        self.missing_by_entity[source_uid].append(missing_target)
        self.missing_uids.add(missing_target)
        self.missing_references += 1


@dataclass
class IncrementalStats:
    """
    Statistics from an incremental ingestion operation.

    Extends IngestionStats with incremental-ingestion-specific metrics.
    """

    total_files: int = 0
    files_checked: int = 0
    files_skipped: int = 0  # Unchanged files
    files_ingested: int = 0  # Actually processed
    files_failed: int = 0
    nodes_created: int = 0
    nodes_updated: int = 0
    relationships_created: int = 0
    duration_seconds: float = 0.0
    # Breakdown by skip reason
    skipped_unchanged: int = 0
    skipped_hash_match: int = 0
    errors: list[dict[str, Any]] | None = field(default_factory=list)

    @property
    def skip_efficiency(self) -> float:
        """Calculate efficiency (what % of files were skipped)."""
        if self.total_files == 0:
            return 0.0
        return (self.files_skipped / self.total_files) * 100

    # Compatibility properties to match IngestionStats interface
    @property
    def successful(self) -> int:
        """Alias for files_ingested - matches IngestionStats interface."""
        return self.files_ingested

    @property
    def failed(self) -> int:
        """Alias for files_failed - matches IngestionStats interface."""
        return self.files_failed

    @property
    def files_per_second(self) -> float:
        """Calculate files processed per second."""
        if self.duration_seconds == 0:
            return 0.0
        return self.total_files / self.duration_seconds


@dataclass
class DryRunPreview:
    """Preview of what would change during ingestion."""

    total_files: int = 0
    files_to_create: list[dict[str, Any]] = field(
        default_factory=list
    )  # [{uid, title, entity_type, file_path}]
    files_to_update: list[dict[str, Any]] = field(
        default_factory=list
    )  # [{uid, title, changes_summary}]
    files_to_skip: list[str] = field(default_factory=list)
    relationships_to_create: list[dict[str, Any]] = field(
        default_factory=list
    )  # [{source, target, type}]
    validation_warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class IngestionError:
    """
    Rich error context for debugging ingestion failures.

    Provides detailed information about what went wrong, where, and how to fix it.
    """

    file: str
    error: str
    stage: str  # format_detection, parsing, type_detection, validation, preparation, ingestion
    error_type: str = "unknown"  # validation, parse, format, system, exception
    entity_type: str | None = None  # If we got far enough to detect it
    line_number: int | None = None  # For YAML/markdown parse errors
    column: int | None = None  # For YAML parse errors
    field: str | None = None  # For validation errors (which field failed)
    suggestion: str | None = None  # Helpful hint for fixing

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "file": self.file,
            "error": self.error,
            "stage": self.stage,
            "error_type": self.error_type,
        }
        if self.entity_type:
            result["entity_type"] = self.entity_type
        if self.line_number is not None:
            result["line_number"] = self.line_number
        if self.column is not None:
            result["column"] = self.column
        if self.field:
            result["field"] = self.field
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result

    def __str__(self) -> str:
        """Human-readable error string."""
        parts = [f"{self.file}: {self.error}"]
        if self.line_number:
            parts.append(f"(line {self.line_number})")
        if self.entity_type:
            parts.append(f"[{self.entity_type}]")
        parts.append(f"@ {self.stage}")
        return " ".join(parts)


__all__ = [
    "BundleStats",
    "DirectoryValidationResult",
    "DryRunPreview",
    "IngestionError",
    "IngestionStats",
    "RelationshipValidationResult",
    "IncrementalStats",
    "ValidationResult",
]
