"""
Markdown Sync DTOs
==================

Data Transfer Objects for markdown synchronization (Tier 2 of three-tier architecture).
Mutable objects for transferring data between service layers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MarkdownFileDTO:
    """DTO for a markdown file being synced"""

    file_path: str
    content: str
    frontmatter: dict[str, Any]
    body: str

    # Metadata
    uid: str | None = (None,)
    title: str | None = (None,)
    content_hash: str | None = (None,)
    file_size: int | None = (None,)
    last_modified: datetime | None = None

    # Parsing results
    headings: list[str] = (field(default_factory=list),)
    links: list[str] = (field(default_factory=list),)
    tags: list[str] = field(default_factory=list)

    # Relationships
    connections: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SyncOperationDTO:
    """DTO for a sync operation"""

    operation_id: str
    operation_type: str  # 'file', 'directory', 'vault', 'bulk'
    status: str  # 'pending', 'in_progress', 'completed', 'failed'

    # Request details
    target_path: str
    options: dict[str, Any] = field(default_factory=dict)

    # Timing
    started_at: datetime | None = (None,)

    completed_at: datetime | None = (None,)

    duration_seconds: float | None = None

    # Progress
    total_files: int = 0

    processed_files: int = 0
    successful_files: int = 0

    failed_files: int = 0
    skipped_files: int = 0

    # Database operations
    nodes_created: int = 0

    nodes_updated: int = 0
    relationships_created: int = 0

    # Errors
    errors: list[dict[str, Any]] = field(default_factory=list)

    # User context
    user_id: str | None = None

    def to_response_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "operation_id": self.operation_id,
            "status": self.status,
            "total_files": self.total_files,
            "successful": self.successful_files,
            "failed": self.failed_files,
            "skipped": self.skipped_files,
            "nodes_created": self.nodes_created,
            "nodes_updated": self.nodes_updated,
            "relationships_created": self.relationships_created,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
        }


@dataclass
class SyncStatisticsDTO:
    """DTO for sync operation statistics"""

    # File counts
    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0

    # Database operations
    nodes_created: int = 0
    nodes_updated: int = 0
    nodes_deleted: int = 0
    relationships_created: int = 0
    relationships_deleted: int = 0

    # Performance metrics
    duration_ms: int = 0
    files_per_second: float = 0.0
    average_file_size_kb: float = 0.0

    # Detailed errors
    errors: list[dict[str, Any]] = field(default_factory=list)

    # File-level details
    file_results: list[dict[str, Any]] | None = None
