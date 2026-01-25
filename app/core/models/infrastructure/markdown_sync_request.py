"""
Markdown Sync Request Models
=============================

Pydantic models for markdown synchronization API boundaries (Tier 1 of three-tier architecture).
Handles validation and serialization at the API layer for sync operations.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.utils.logging import get_logger

logger = get_logger(__name__)


def _default_exclude_dirs() -> Any:
    """Default directories to exclude from sync."""
    return [".obsidian", ".trash", "node_modules", ".git"]


class MarkdownSyncFileRequest(BaseModel):
    """Request model for syncing a single markdown file"""

    file_path: str = Field(min_length=1, description="Path to the markdown file to sync")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate that the file path exists and is a markdown file"""
        path = Path(v)

        # Check if path exists
        if not path.exists():
            raise ValueError(f"File does not exist: {v}")

        # Check if it's a file (not a directory)
        if not path.is_file():
            raise ValueError(f"Path is not a file: {v}")

        # Check if it's a markdown file
        if not v.lower().endswith(".md"):
            raise ValueError(f"Not a markdown file: {v}")

        return v


class MarkdownSyncDirectoryRequest(BaseModel):
    """Request model for syncing all markdown files in a directory"""

    directory: str = Field(min_length=1, description="Directory path containing markdown files")

    pattern: str = Field(default="*.md", description="Glob pattern for files to sync")

    batch_size: int = Field(
        default=500, gt=0, le=1000, description="Number of files to process per batch"
    )

    recursive: bool = Field(
        default=True, description="Whether to search subdirectories recursively"
    )

    @field_validator("directory")
    @classmethod
    def validate_directory(cls, v: str) -> str:
        """Validate that the directory exists"""
        path = Path(v)

        if not path.exists():
            raise ValueError(f"Directory does not exist: {v}")

        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {v}")

        return v

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate glob pattern"""
        # Basic validation - ensure it has markdown extension
        if not (".md" in v or "*" in v):
            raise ValueError(f"Pattern should match markdown files: {v}")
        return v


class MarkdownSyncVaultRequest(BaseModel):
    """Request model for syncing an entire Obsidian vault"""

    vault_path: str = Field(min_length=1, description="Root path of the Obsidian vault")

    subdirs: list[str] | None = Field(
        default=None, description="Specific subdirectories to sync (None means all)"
    )

    exclude_dirs: list[str] = Field(
        default_factory=_default_exclude_dirs, description="Directories to exclude from sync"
    )

    batch_size: int = Field(
        default=500, gt=0, le=1000, description="Number of files to process per batch"
    )

    dry_run: bool = Field(default=False, description="If true, only preview what would be synced")

    @field_validator("vault_path")
    @classmethod
    def validate_vault_path(cls, v: str) -> str:
        """Validate that the vault path exists and is a directory"""
        path = Path(v)

        if not path.exists():
            raise ValueError(f"Vault path does not exist: {v}")

        if not path.is_dir():
            raise ValueError(f"Vault path is not a directory: {v}")

        # Check if it looks like an Obsidian vault (has .obsidian folder or markdown files)
        obsidian_dir = path / ".obsidian"
        has_markdown = any(path.glob("**/*.md"))

        if not (obsidian_dir.exists() or has_markdown):
            raise ValueError(f"Path does not appear to be an Obsidian vault: {v}")

        return v

    @field_validator("subdirs")
    @classmethod
    def validate_subdirs(cls, v: list[str] | None, info) -> list[str] | None:
        """Validate that subdirectories exist within the vault"""
        if v is None:
            return v

        vault_path = info.data.get("vault_path")
        if not vault_path:
            return v

        vault = Path(vault_path)
        valid_subdirs = []

        for subdir in v:
            subdir_path = vault / subdir
            if not subdir_path.exists():
                # Warning, but don't fail - directory might be created later
                logger.warning("Subdirectory does not exist", subdir=subdir)
            else:
                valid_subdirs.append(subdir)

        return valid_subdirs if valid_subdirs else None


class MarkdownSyncBulkRequest(BaseModel):
    """Request model for bulk syncing multiple files"""

    file_paths: list[str] = Field(
        min_length=1, max_length=1000, description="List of file paths to sync"
    )

    batch_size: int = Field(
        default=100, gt=0, le=500, description="Number of files to process per batch"
    )

    continue_on_error: bool = Field(
        default=True, description="Continue syncing if individual files fail"
    )

    @field_validator("file_paths")
    @classmethod
    def validate_file_paths(cls, v: list[str]) -> list[str]:
        """Validate that all file paths are markdown files"""
        valid_paths = []

        for file_path in v:
            if not file_path.lower().endswith(".md"):
                raise ValueError(f"Not a markdown file: {file_path}")

            path = Path(file_path)
            if not path.exists():
                raise ValueError(f"File does not exist: {file_path}")

            valid_paths.append(file_path)

        return valid_paths


class MarkdownSyncStatusRequest(BaseModel):
    """Request model for checking sync status"""

    operation_id: str | None = Field(default=None, description="Specific operation ID to check")

    include_details: bool = Field(default=False, description="Include detailed sync information")


class MarkdownSyncResponse(BaseModel):
    """Response model for sync operations"""

    success: bool = Field(description="Whether the sync was successful")
    operation_id: str | None = Field(default=None, description="Operation ID for tracking")

    # Statistics
    total_files: int = Field(default=0, description="Total files processed")
    successful: int = Field(default=0, description="Successfully synced files")
    failed: int = Field(default=0, description="Failed sync files")
    skipped: int = Field(default=0, description="Skipped files")

    # Database operations
    nodes_created: int = Field(default=0, description="Neo4j nodes created")
    nodes_updated: int = Field(default=0, description="Neo4j nodes updated")
    relationships_created: int = Field(default=0, description="Neo4j relationships created")

    # Performance metrics
    duration_seconds: float = Field(default=0.0, description="Total duration in seconds")
    files_per_second: float = Field(default=0.0, description="Processing rate")

    # Errors
    errors: list[dict] = Field(default_factory=list, description="List of errors encountered")

    # Additional details for specific operations
    details: dict | None = Field(default=None, description="Operation-specific details")
