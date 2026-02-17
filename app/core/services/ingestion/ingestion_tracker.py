"""
Ingestion Tracker - Incremental Ingestion State Management
==========================================================

Tracks file ingestion state in Neo4j for incremental operations.
Enables delta ingestion by detecting changed files based on content hash and mtime.

Key Design Decisions:
- Content hash (SHA-256) for definitive change detection
- File mtime as fast pre-filter before hash computation
- IngestionMetadata nodes stored in Neo4j alongside entity nodes
- Supports both "incremental" and "smart" ingestion modes

Usage:
    tracker = IngestionTracker(executor)

    # Check which files need ingestion
    result = await tracker.get_ingestion_metadata(file_paths)
    metadata = result.value if result.is_ok else {}
    files_to_ingest = [f for f in files if tracker.needs_ingestion(f, metadata.get(str(f)))]

    # After successful ingestion, update metadata
    await tracker.update_ingestion_metadata(file_path, entity_uid, content_hash)
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.protocols import QueryExecutor

logger = get_logger("skuel.services.ingestion.ingestion_tracker")


@dataclass
class FileIngestionMetadata:
    """Ingestion state for a single file."""

    file_path: str
    content_hash: str  # SHA-256 of file content
    file_mtime: float  # File modification timestamp (Unix epoch)
    last_ingested_at: datetime
    entity_uid: str


@dataclass
class IngestionDecision:
    """Result of ingestion decision for a file."""

    file_path: Path
    needs_ingestion: bool
    reason: str  # "new", "modified", "hash_changed", "unchanged"
    existing_metadata: FileIngestionMetadata | None = None


class IngestionTracker:
    """
    Track ingestion state in Neo4j for incremental operations.

    Stores IngestionMetadata nodes with file path, content hash, and timestamps.
    Used by ingest_directory() to skip unchanged files.
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize ingestion tracker.

        Args:
            executor: Query executor for database operations
        """
        self.executor = executor
        self.logger = logger

    async def ensure_constraints(self) -> Result[None]:
        """
        Ensure Neo4j constraints exist for IngestionMetadata nodes.

        Creates unique constraint on file_path for fast lookups.
        """
        query = """
        CREATE CONSTRAINT ingestion_metadata_file_path IF NOT EXISTS
        FOR (s:IngestionMetadata) REQUIRE s.file_path IS UNIQUE
        """
        result = await self.executor.execute_query(query)
        if result.is_error:
            self.logger.error(
                "Failed to create IngestionMetadata constraint",
                extra={
                    "error_message": str(result.error),
                },
            )
            return Result.fail(str(result.error))
        return Result.ok(None)

    async def get_ingestion_metadata(
        self, file_paths: list[Path]
    ) -> Result[dict[str, FileIngestionMetadata]]:
        """
        Fetch existing ingestion metadata from Neo4j for given files.

        Args:
            file_paths: List of file paths to query

        Returns:
            Result containing dict mapping file path strings to FileIngestionMetadata
        """
        if not file_paths:
            return Result.ok({})

        path_strings = [str(fp) for fp in file_paths]

        query = """
        UNWIND $paths AS path
        MATCH (s:IngestionMetadata {file_path: path})
        RETURN s.file_path AS file_path,
               s.content_hash AS content_hash,
               s.file_mtime AS file_mtime,
               s.last_ingested_at AS last_ingested_at,
               s.entity_uid AS entity_uid
        """

        result_map: dict[str, FileIngestionMetadata] = {}

        result = await self.executor.execute_query(query, {"paths": path_strings})

        if result.is_error:
            self.logger.error(
                "Failed to fetch ingestion metadata",
                extra={
                    "file_count": len(file_paths),
                    "error_message": str(result.error),
                },
            )
            return Result.fail(str(result.error))

        for record in result.value:
            # Handle datetime - Neo4j returns neo4j.time.DateTime
            last_ingested = record["last_ingested_at"]
            if getattr(type(last_ingested), "__module__", "") == "neo4j.time":
                last_ingested = last_ingested.to_native()

            metadata = FileIngestionMetadata(
                file_path=record["file_path"],
                content_hash=record["content_hash"],
                file_mtime=record["file_mtime"],
                last_ingested_at=last_ingested,
                entity_uid=record["entity_uid"],
            )
            result_map[record["file_path"]] = metadata

        self.logger.debug(
            f"Retrieved ingestion metadata for {len(result_map)}/{len(file_paths)} files"
        )
        return Result.ok(result_map)

    async def update_ingestion_metadata(
        self,
        file_path: Path,
        entity_uid: str,
        content_hash: str,
    ) -> Result[None]:
        """
        Update ingestion metadata after successful ingestion.

        Uses MERGE for idempotent upsert.

        Args:
            file_path: Path to the ingested file
            entity_uid: UID of the entity created/updated
            content_hash: SHA-256 hash of file content
        """
        query = """
        MERGE (s:IngestionMetadata {file_path: $file_path})
        SET s.content_hash = $content_hash,
            s.file_mtime = $file_mtime,
            s.last_ingested_at = datetime(),
            s.entity_uid = $entity_uid
        """

        try:
            file_mtime = file_path.stat().st_mtime
        except OSError as e:
            self.logger.error(
                "Failed to stat file for ingestion metadata update",
                extra={
                    "file_path": str(file_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(str(e))

        result = await self.executor.execute_query(
            query,
            {
                "file_path": str(file_path),
                "content_hash": content_hash,
                "file_mtime": file_mtime,
                "entity_uid": entity_uid,
            },
        )

        if result.is_error:
            self.logger.error(
                "Failed to update ingestion metadata",
                extra={
                    "file_path": str(file_path),
                    "entity_uid": entity_uid,
                    "error_message": str(result.error),
                },
            )
            return Result.fail(str(result.error))

        return Result.ok(None)

    async def update_ingestion_metadata_batch(
        self,
        updates: list[tuple[Path, str, str]],  # (file_path, entity_uid, content_hash)
    ) -> Result[int]:
        """
        Batch update ingestion metadata for multiple files.

        More efficient than individual updates for large ingestion operations.

        Args:
            updates: List of (file_path, entity_uid, content_hash) tuples

        Returns:
            Result with count of updated records
        """
        if not updates:
            return Result.ok(0)

        query = """
        UNWIND $items AS item
        MERGE (s:IngestionMetadata {file_path: item.file_path})
        SET s.content_hash = item.content_hash,
            s.file_mtime = item.file_mtime,
            s.last_ingested_at = datetime(),
            s.entity_uid = item.entity_uid
        RETURN count(s) AS updated
        """

        items = []
        for file_path, entity_uid, content_hash in updates:
            try:
                file_mtime = file_path.stat().st_mtime
                items.append(
                    {
                        "file_path": str(file_path),
                        "entity_uid": entity_uid,
                        "content_hash": content_hash,
                        "file_mtime": file_mtime,
                    }
                )
            except OSError:
                # File may have been deleted/moved during ingestion
                continue

        if not items:
            return Result.ok(0)

        result = await self.executor.execute_query(query, {"items": items})

        if result.is_error:
            self.logger.error(
                "Failed to batch update ingestion metadata",
                extra={
                    "batch_size": len(items),
                    "error_message": str(result.error),
                },
            )
            return Result.fail(str(result.error))

        records = result.value
        updated_count = records[0]["updated"] if records else 0
        return Result.ok(updated_count)

    async def delete_ingestion_metadata(self, file_paths: list[Path]) -> Result[int]:
        """
        Delete ingestion metadata for removed files.

        Call this when files are deleted from the vault.

        Args:
            file_paths: List of file paths to delete metadata for

        Returns:
            Result with count of deleted records
        """
        if not file_paths:
            return Result.ok(0)

        query = """
        UNWIND $paths AS path
        MATCH (s:IngestionMetadata {file_path: path})
        DETACH DELETE s
        RETURN count(*) AS deleted
        """

        result = await self.executor.execute_query(query, {"paths": [str(fp) for fp in file_paths]})

        if result.is_error:
            self.logger.error(
                "Failed to delete ingestion metadata",
                extra={
                    "file_count": len(file_paths),
                    "error_message": str(result.error),
                },
            )
            return Result.fail(str(result.error))

        records = result.value
        deleted_count = records[0]["deleted"] if records else 0
        return Result.ok(deleted_count)

    def compute_file_hash(self, file_path: Path) -> str:
        """
        Compute SHA-256 hash of file content.

        Args:
            file_path: Path to file

        Returns:
            Hex-encoded SHA-256 hash string
        """
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            # Read in chunks for memory efficiency with large files
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def needs_ingestion(
        self,
        file_path: Path,
        metadata: FileIngestionMetadata | None,
    ) -> IngestionDecision:
        """
        Determine if file needs re-ingestion based on hash/mtime.

        Strategy:
        1. If no metadata exists -> needs ingestion (new file)
        2. If file mtime unchanged -> skip (fast path)
        3. If mtime changed, check content hash -> ingest only if hash differs

        Args:
            file_path: Path to check
            metadata: Existing ingestion metadata (or None if new)

        Returns:
            IngestionDecision with needs_ingestion flag and reason
        """
        # New file - always needs ingestion
        if metadata is None:
            return IngestionDecision(
                file_path=file_path,
                needs_ingestion=True,
                reason="new",
            )

        try:
            current_mtime = file_path.stat().st_mtime

            # Fast path: mtime unchanged means file hasn't been touched
            if current_mtime == metadata.file_mtime:
                return IngestionDecision(
                    file_path=file_path,
                    needs_ingestion=False,
                    reason="unchanged",
                    existing_metadata=metadata,
                )

            # Mtime changed - compute hash to verify actual content change
            # (handles cases where file was touched but content unchanged)
            current_hash = self.compute_file_hash(file_path)

            if current_hash == metadata.content_hash:
                # Content unchanged despite mtime change (e.g., file was touched)
                return IngestionDecision(
                    file_path=file_path,
                    needs_ingestion=False,
                    reason="unchanged",
                    existing_metadata=metadata,
                )

            # Content actually changed
            return IngestionDecision(
                file_path=file_path,
                needs_ingestion=True,
                reason="hash_changed",
                existing_metadata=metadata,
            )

        except OSError as e:
            # File may have been deleted - treat as needing removal
            self.logger.warning(
                "Cannot access file for ingestion check - treating as modified",
                extra={
                    "file_path": str(file_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return IngestionDecision(
                file_path=file_path,
                needs_ingestion=True,
                reason="modified",  # Will fail during ingestion, handled there
                existing_metadata=metadata,
            )

    def filter_files_needing_ingestion(
        self,
        file_paths: list[Path],
        metadata_map: dict[str, FileIngestionMetadata],
    ) -> tuple[list[Path], list[IngestionDecision]]:
        """
        Filter files to only those needing ingestion.

        Convenience method that applies needs_ingestion to all files.

        Args:
            file_paths: All file paths to consider
            metadata_map: Existing metadata keyed by file path string

        Returns:
            Tuple of (files_to_ingest, all_decisions)
        """
        files_to_ingest: list[Path] = []
        all_decisions: list[IngestionDecision] = []

        for file_path in file_paths:
            metadata = metadata_map.get(str(file_path))
            decision = self.needs_ingestion(file_path, metadata)
            all_decisions.append(decision)

            if decision.needs_ingestion:
                files_to_ingest.append(file_path)

        return files_to_ingest, all_decisions


__all__ = [
    "FileIngestionMetadata",
    "IngestionDecision",
    "IngestionTracker",
]
