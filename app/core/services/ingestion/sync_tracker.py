"""
Sync Tracker - Incremental Sync State Management
=================================================

Tracks file sync state in Neo4j for incremental operations.
Enables delta sync by detecting changed files based on content hash and mtime.

Key Design Decisions:
- Content hash (SHA-256) for definitive change detection
- File mtime as fast pre-filter before hash computation
- SyncMetadata nodes stored in Neo4j alongside entity nodes
- Supports both "incremental" and "smart" sync modes

Usage:
    tracker = SyncTracker(driver)

    # Check which files need sync
    result = await tracker.get_sync_metadata(file_paths)
    metadata = result.value if result.is_ok else {}
    files_to_sync = [f for f in files if tracker.needs_sync(f, metadata.get(str(f)))]

    # After successful ingestion, update metadata
    await tracker.update_sync_metadata(file_path, entity_uid, content_hash)
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from neo4j import AsyncDriver
from neo4j.time import DateTime as Neo4jDateTime

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.ingestion.sync_tracker")


@dataclass
class FileSyncMetadata:
    """Sync state for a single file."""

    file_path: str
    content_hash: str  # SHA-256 of file content
    file_mtime: float  # File modification timestamp (Unix epoch)
    last_synced_at: datetime
    entity_uid: str


@dataclass
class SyncDecision:
    """Result of sync decision for a file."""

    file_path: Path
    needs_sync: bool
    reason: str  # "new", "modified", "hash_changed", "unchanged"
    existing_metadata: FileSyncMetadata | None = None


class SyncTracker:
    """
    Track sync state in Neo4j for incremental operations.

    Stores SyncMetadata nodes with file path, content hash, and timestamps.
    Used by ingest_directory() to skip unchanged files.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize sync tracker.

        Args:
            driver: Neo4j async driver
        """
        self.driver = driver
        self.logger = logger

    async def ensure_constraints(self) -> Result[None]:
        """
        Ensure Neo4j constraints exist for SyncMetadata nodes.

        Creates unique constraint on file_path for fast lookups.
        """
        query = """
        CREATE CONSTRAINT sync_metadata_file_path IF NOT EXISTS
        FOR (s:SyncMetadata) REQUIRE s.file_path IS UNIQUE
        """
        try:
            async with self.driver.session() as session:
                await session.run(query)
            return Result.ok(None)
        except Exception as e:
            self.logger.error(
                "Failed to create SyncMetadata constraint",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(str(e))

    async def get_sync_metadata(
        self, file_paths: list[Path]
    ) -> Result[dict[str, FileSyncMetadata]]:
        """
        Fetch existing sync metadata from Neo4j for given files.

        Args:
            file_paths: List of file paths to query

        Returns:
            Result containing dict mapping file path strings to FileSyncMetadata
        """
        if not file_paths:
            return Result.ok({})

        path_strings = [str(fp) for fp in file_paths]

        query = """
        UNWIND $paths AS path
        MATCH (s:SyncMetadata {file_path: path})
        RETURN s.file_path AS file_path,
               s.content_hash AS content_hash,
               s.file_mtime AS file_mtime,
               s.last_synced_at AS last_synced_at,
               s.entity_uid AS entity_uid
        """

        result_map: dict[str, FileSyncMetadata] = {}

        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"paths": path_strings})
                records = await result.data()

                for record in records:
                    # Handle datetime - Neo4j returns neo4j.time.DateTime
                    last_synced = record["last_synced_at"]
                    if isinstance(last_synced, Neo4jDateTime):
                        last_synced = last_synced.to_native()

                    metadata = FileSyncMetadata(
                        file_path=record["file_path"],
                        content_hash=record["content_hash"],
                        file_mtime=record["file_mtime"],
                        last_synced_at=last_synced,
                        entity_uid=record["entity_uid"],
                    )
                    result_map[record["file_path"]] = metadata

            self.logger.debug(
                f"Retrieved sync metadata for {len(result_map)}/{len(file_paths)} files"
            )
            return Result.ok(result_map)

        except Exception as e:
            self.logger.error(
                "Failed to fetch sync metadata",
                extra={
                    "file_count": len(file_paths),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(str(e))

    async def update_sync_metadata(
        self,
        file_path: Path,
        entity_uid: str,
        content_hash: str,
    ) -> Result[None]:
        """
        Update sync metadata after successful ingestion.

        Uses MERGE for idempotent upsert.

        Args:
            file_path: Path to the synced file
            entity_uid: UID of the entity created/updated
            content_hash: SHA-256 hash of file content
        """
        query = """
        MERGE (s:SyncMetadata {file_path: $file_path})
        SET s.content_hash = $content_hash,
            s.file_mtime = $file_mtime,
            s.last_synced_at = datetime(),
            s.entity_uid = $entity_uid
        """

        try:
            file_mtime = file_path.stat().st_mtime
            async with self.driver.session() as session:
                await session.run(
                    query,
                    {
                        "file_path": str(file_path),
                        "content_hash": content_hash,
                        "file_mtime": file_mtime,
                        "entity_uid": entity_uid,
                    },
                )
            return Result.ok(None)
        except Exception as e:
            self.logger.error(
                "Failed to update sync metadata",
                extra={
                    "file_path": str(file_path),
                    "entity_uid": entity_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(str(e))

    async def update_sync_metadata_batch(
        self,
        updates: list[tuple[Path, str, str]],  # (file_path, entity_uid, content_hash)
    ) -> Result[int]:
        """
        Batch update sync metadata for multiple files.

        More efficient than individual updates for large syncs.

        Args:
            updates: List of (file_path, entity_uid, content_hash) tuples

        Returns:
            Result with count of updated records
        """
        if not updates:
            return Result.ok(0)

        query = """
        UNWIND $items AS item
        MERGE (s:SyncMetadata {file_path: item.file_path})
        SET s.content_hash = item.content_hash,
            s.file_mtime = item.file_mtime,
            s.last_synced_at = datetime(),
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
                # File may have been deleted/moved during sync
                continue

        if not items:
            return Result.ok(0)

        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"items": items})
                record = await result.single()
                updated_count = record["updated"] if record else 0
            return Result.ok(updated_count)
        except Exception as e:
            self.logger.error(
                "Failed to batch update sync metadata",
                extra={
                    "batch_size": len(items),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(str(e))

    async def delete_sync_metadata(self, file_paths: list[Path]) -> Result[int]:
        """
        Delete sync metadata for removed files.

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
        MATCH (s:SyncMetadata {file_path: path})
        DETACH DELETE s
        RETURN count(*) AS deleted
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"paths": [str(fp) for fp in file_paths]})
                record = await result.single()
                deleted_count = record["deleted"] if record else 0
            return Result.ok(deleted_count)
        except Exception as e:
            self.logger.error(
                "Failed to delete sync metadata",
                extra={
                    "file_count": len(file_paths),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(str(e))

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

    def needs_sync(
        self,
        file_path: Path,
        metadata: FileSyncMetadata | None,
    ) -> SyncDecision:
        """
        Determine if file needs re-sync based on hash/mtime.

        Strategy:
        1. If no metadata exists → needs sync (new file)
        2. If file mtime unchanged → skip (fast path)
        3. If mtime changed, check content hash → sync only if hash differs

        Args:
            file_path: Path to check
            metadata: Existing sync metadata (or None if new)

        Returns:
            SyncDecision with needs_sync flag and reason
        """
        # New file - always needs sync
        if metadata is None:
            return SyncDecision(
                file_path=file_path,
                needs_sync=True,
                reason="new",
            )

        try:
            current_mtime = file_path.stat().st_mtime

            # Fast path: mtime unchanged means file hasn't been touched
            if current_mtime == metadata.file_mtime:
                return SyncDecision(
                    file_path=file_path,
                    needs_sync=False,
                    reason="unchanged",
                    existing_metadata=metadata,
                )

            # Mtime changed - compute hash to verify actual content change
            # (handles cases where file was touched but content unchanged)
            current_hash = self.compute_file_hash(file_path)

            if current_hash == metadata.content_hash:
                # Content unchanged despite mtime change (e.g., file was touched)
                return SyncDecision(
                    file_path=file_path,
                    needs_sync=False,
                    reason="unchanged",
                    existing_metadata=metadata,
                )

            # Content actually changed
            return SyncDecision(
                file_path=file_path,
                needs_sync=True,
                reason="hash_changed",
                existing_metadata=metadata,
            )

        except OSError as e:
            # File may have been deleted - treat as needing removal
            self.logger.warning(
                "Cannot access file for sync check - treating as modified",
                extra={
                    "file_path": str(file_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return SyncDecision(
                file_path=file_path,
                needs_sync=True,
                reason="modified",  # Will fail during ingestion, handled there
                existing_metadata=metadata,
            )

    def filter_files_needing_sync(
        self,
        file_paths: list[Path],
        metadata_map: dict[str, FileSyncMetadata],
    ) -> tuple[list[Path], list[SyncDecision]]:
        """
        Filter files to only those needing sync.

        Convenience method that applies needs_sync to all files.

        Args:
            file_paths: All file paths to consider
            metadata_map: Existing metadata keyed by file path string

        Returns:
            Tuple of (files_to_sync, all_decisions)
        """
        files_to_sync: list[Path] = []
        all_decisions: list[SyncDecision] = []

        for file_path in file_paths:
            metadata = metadata_map.get(str(file_path))
            decision = self.needs_sync(file_path, metadata)
            all_decisions.append(decision)

            if decision.needs_sync:
                files_to_sync.append(file_path)

        return files_to_sync, all_decisions


__all__ = [
    "FileSyncMetadata",
    "SyncDecision",
    "SyncTracker",
]
