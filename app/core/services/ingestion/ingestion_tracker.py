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
    tracker = IngestionTracker(backend)

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
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from core.constants import MASS_DELETION_MAX_FRACTION, MASS_DELETION_MIN_COUNT
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.services.ingestion.config import is_ingestible_path
from core.services.ingestion.types import DeletionReconciliation
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.ingestion_protocols import IngestionBackendOperations
    from core.services.ingestion.config import SyncAllowlist

logger = get_logger("skuel.services.ingestion.ingestion_tracker")

# Edge files are tracked in IngestionMetadata like entity files, with the
# relationship identity encoded in the entity_uid slot. The prefix tells
# reconciliation to delete a relationship instead of a node.
EDGE_UID_PREFIX = "edge:"
_EDGE_IDENTITY_SEP = "|"


def edge_identity(from_uid: str, rel_type: str, to_uid: str) -> str:
    """Encode an edge's identity for the IngestionMetadata entity_uid slot."""
    return f"{EDGE_UID_PREFIX}{from_uid}{_EDGE_IDENTITY_SEP}{rel_type}{_EDGE_IDENTITY_SEP}{to_uid}"


def parse_edge_identity(identity: str) -> tuple[str, str, str] | None:
    """Decode (from_uid, rel_type, to_uid) from an edge identity string."""
    if not identity.startswith(EDGE_UID_PREFIX):
        return None
    parts = identity[len(EDGE_UID_PREFIX) :].split(_EDGE_IDENTITY_SEP)
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def _matches_pattern(path_str: str, pattern: str) -> bool:
    """Mirror collect_files() pattern semantics for tracked-row filtering.

    Reconciliation must not delete outside the run's requested scope — a
    *.md-scoped run has no authority over tracked YAML files (and out-of-scope
    rows would dodge the mass-deletion valve).
    """
    if pattern in ("*", "**/*"):
        return True
    name = Path(path_str).name
    if pattern.endswith((".md", ".yaml", ".yml")):
        return fnmatch(name, pattern)
    return fnmatch(Path(path_str).stem, pattern)


@dataclass
class FileIngestionMetadata:
    """Ingestion state for a single file."""

    file_path: str
    content_hash: str  # SHA-256 of file content
    file_mtime: float  # File modification timestamp (Unix epoch)
    last_ingested_at: datetime
    entity_uid: EntityUID


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

    def __init__(self, backend: "IngestionBackendOperations") -> None:
        """
        Initialize ingestion tracker.

        Args:
            backend: Typed backend for ingestion persistence
        """
        self.backend = backend
        self.logger = logger

    @staticmethod
    def _canonical(file_path: Path) -> str:
        """Canonical absolute path string — THE key form for IngestionMetadata.

        Metadata written with relative paths (direct service calls with a
        relative directory) would be invisible to deletion reconciliation,
        which queries by absolute directory prefix. Resolving at the tracker
        boundary keeps storage, lookup, and reconciliation in one form.
        """
        return str(file_path.resolve())

    async def ensure_constraints(self) -> Result[None]:
        """
        Ensure Neo4j constraints exist for IngestionMetadata nodes.

        Creates unique constraint on file_path for fast lookups.
        """
        result = await self.backend.ensure_tracker_constraints()
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

        path_strings = [self._canonical(fp) for fp in file_paths]

        result = await self.backend.get_ingestion_metadata(path_strings)

        if result.is_error:
            self.logger.error(
                "Failed to fetch ingestion metadata",
                extra={
                    "file_count": len(file_paths),
                    "error_message": str(result.error),
                },
            )
            return Result.fail(str(result.error))

        result_map: dict[str, FileIngestionMetadata] = {}
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
        entity_uid: EntityUID,
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

        result = await self.backend.update_ingestion_metadata(
            {
                "file_path": self._canonical(file_path),
                "content_hash": content_hash,
                "file_mtime": file_mtime,
                "entity_uid": entity_uid,
            }
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

        items = []
        for file_path, entity_uid, content_hash in updates:
            try:
                file_mtime = file_path.stat().st_mtime
                items.append(
                    {
                        "file_path": self._canonical(file_path),
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

        result = await self.backend.update_ingestion_metadata_batch(items)

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

        result = await self.backend.delete_ingestion_metadata(
            [self._canonical(fp) for fp in file_paths]
        )

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

    async def reconcile_deletions(
        self,
        directory: Path,
        pattern: str = "*",
        *,
        allowlist: "SyncAllowlist | None" = None,
        owner_uid: UserUID | None = None,
    ) -> Result[DeletionReconciliation]:
        """
        Propagate vault deletions to the graph for one directory.

        A tracked file under `directory` matching `pattern` that would no longer
        be collected for ingestion — either it no longer exists on disk (author
        deleted it) OR it is now excluded by the vault wall (staging floor /
        fail-closed allowlist) — has its corresponding entity (and content subtree
        + tracking row) deleted from Neo4j. Purging walled-but-present files
        retracts previously-synced content that has since become private, so the
        fail-closed guarantee holds retroactively, not just for new ingestion.

        Five guards:
        - **Pattern scope**: only tracked files matching the run's pattern are
          DELETED — a *.md-scoped run never deletes tracked YAML entities.
        - **Moved/renamed files**: if the same entity_uid is still claimed by
          ANY tracked file that would still be collected (existing AND allowed),
          only the stale tracking row is removed — the entity survives.
        - **Mass-deletion safety valve (GLOBAL)**: an unmounted vault or sync
          wipe makes EVERY tracked file physically vanish — so the valve checks
          PHYSICAL existence of all tracked files (independent of the wall: a
          mounted vault whose files are merely walled is still mounted and we DO
          want to purge those rows). If none physically exist, deletion is refused
          and a warning logged. A real full-vault teardown is an explicit admin
          operation, not a watcher side effect.
        - **Mass-deletion safety valve (THRESHOLD)**: evaluated AFTER the
          moved/stale split so vault reorganizations (identities re-claimed by
          new paths) never trip it. Refuses when at least
          ``MASS_DELETION_MIN_COUNT`` entities/edges would be deleted AND they
          exceed ``MASS_DELETION_MAX_FRACTION`` of ALL tracked files under the
          directory — deleting all-but-one file must not wipe the graph in one
          sync. Refusals surface via ``refusal_warning``; escape hatch: delete
          explicitly via the ingestion dashboard, or sync in smaller batches.
        - **Wall symmetry**: "would be collected" uses ``is_ingestible_path`` —
          the exact predicate ``collect_files`` applies — so ingestion and
          retraction never disagree.
        - **Owner scope** (``owner_uid``, descriptor-governed syncs): a tracked
          user-owned node (:Entity ``user_uid``, :Group ``owner_uid``,
          :Expense ``user_uid`` — every shape the delete query removes) whose
          owner differs from the syncing vault's owner is never deleted — the
          row and node both survive and the mismatch is reported
          (``ownership_mismatches``). Path prefix alone decided deletion before
          per-user vault roots; this closes the cross-owner hole for legacy
          rows and misconfigured roots. SHARED curriculum (ownerless) and Edge
          YAMLs (relationships carry no owner) stay path-scoped.

        Backend: IngestionBackend.get_tracked_files_under / get_entity_owner_uids /
        delete_entities_with_metadata.
        """
        # Trailing separator so /vault/a never matches /vault/abc.
        prefix = str(directory.resolve()).rstrip("/") + "/"
        tracked_result = await self.backend.get_tracked_files_under(prefix)
        if tracked_result.is_error:
            return Result.fail(tracked_result)

        all_tracked = tracked_result.value or []
        tracked = [row for row in all_tracked if _matches_pattern(str(row["file_path"]), pattern)]
        if not tracked:
            return Result.ok(DeletionReconciliation())

        def _collectible(row: dict[str, EntityUID]) -> bool:
            # Survives iff collect_files would still collect it: on disk AND not
            # excluded by the vault wall (staging floor / allowlist).
            path = Path(str(row["file_path"]))
            return path.exists() and is_ingestible_path(path, allowlist)

        # "gone" = deleted from disk OR now walled — both are retracted.
        gone = [row for row in tracked if not _collectible(row)]
        if not gone:
            return Result.ok(DeletionReconciliation())

        # Mass-deletion valve is PHYSICAL-existence only (mount detection), so a
        # wall change that leaves files on disk still purges them.
        physically_present = [row for row in all_tracked if Path(str(row["file_path"])).exists()]
        if not physically_present:
            warning = (
                f"Deletion reconciliation refused: all {len(all_tracked)} tracked "
                f"files under {directory} are missing — looks like an unmounted "
                "vault or sync wipe, not authoring. Delete explicitly via the "
                "ingestion dashboard if intended."
            )
            self.logger.warning(warning)
            return Result.ok(
                DeletionReconciliation(mass_deletion_refused=True, refusal_warning=warning)
            )

        # Identities still claimed by a file that would still be collected =
        # moves/renames to an allowed location (covers duplicate edge files too).
        # Claims are checked against ALL tracked rows, not just the pattern scope —
        # an identity owned by an out-of-scope allowed file must survive.
        live_uids = {row["entity_uid"] for row in all_tracked if _collectible(row)}
        stale_rows = [row for row in gone if row["entity_uid"] in live_uids]
        delete_rows = [row for row in gone if row["entity_uid"] not in live_uids]

        # Threshold mass-deletion valve — targets actual data loss, so it runs
        # AFTER the moved/stale split (a vault reorganization re-claims every
        # identity at a new path and lands in stale_rows, never here). The
        # floor keeps small vaults / small cleanups friction-free; the fraction
        # catches a majority wipe (e.g. deleting all-but-one file, which slips
        # past the physical-existence valve above).
        if (
            len(delete_rows) >= MASS_DELETION_MIN_COUNT
            and len(delete_rows) / len(all_tracked) > MASS_DELETION_MAX_FRACTION
        ):
            warning = (
                f"Deletion reconciliation refused: {len(delete_rows)} of "
                f"{len(all_tracked)} tracked files under {directory} would be "
                "deleted in one sync — that majority wipe looks like data loss, "
                "not authoring. Delete explicitly via the ingestion dashboard, "
                "or sync in smaller batches."
            )
            self.logger.warning(warning)
            return Result.ok(
                DeletionReconciliation(mass_deletion_refused=True, refusal_warning=warning)
            )

        stale_removed = 0
        if stale_rows:
            stale_result = await self.delete_ingestion_metadata(
                [Path(str(row["file_path"])) for row in stale_rows]
            )
            if stale_result.is_error:
                # A swallowed failure here would leave the old path's row to be
                # rediscovered every run while the API reports a clean sync.
                return Result.fail(stale_result)
            stale_removed = stale_result.value

        entity_rows = [
            row for row in delete_rows if not str(row["entity_uid"]).startswith(EDGE_UID_PREFIX)
        ]
        edge_rows = [
            row for row in delete_rows if str(row["entity_uid"]).startswith(EDGE_UID_PREFIX)
        ]

        ownership_mismatches: list[str] = []
        if owner_uid is not None and entity_rows:
            owners_result = await self.backend.get_entity_owner_uids(
                [str(row["entity_uid"]) for row in entity_rows]
            )
            if owners_result.is_error:
                # Fail the run rather than fall through to an UNSCOPED delete —
                # the guard must fail closed.
                return Result.fail(owners_result)
            foreign_uids = {
                str(rec["uid"])
                for rec in owners_result.value or []
                if str(rec["user_uid"]) != str(owner_uid)
            }
            if foreign_uids:
                skipped = [row for row in entity_rows if str(row["entity_uid"]) in foreign_uids]
                entity_rows = [
                    row for row in entity_rows if str(row["entity_uid"]) not in foreign_uids
                ]
                for row in skipped:
                    ownership_mismatches.append(
                        f"deletion skipped for {row['file_path']}: entity "
                        f"{row['entity_uid']} belongs to a different user than this "
                        "vault's owner — resolve ownership before deleting"
                    )
                self.logger.warning(
                    "Deletion reconciliation: skipped %d entity deletion(s) under %s "
                    "owned by a different user than the vault owner %s",
                    len(skipped),
                    directory,
                    owner_uid,
                )

        entities_deleted = 0
        if entity_rows:
            items = [
                {"file_path": str(row["file_path"]), "entity_uid": str(row["entity_uid"])}
                for row in entity_rows
            ]
            delete_result = await self.backend.delete_entities_with_metadata(items)
            if delete_result.is_error:
                return Result.fail(delete_result)
            entities_deleted = len(delete_result.value or [])
            self.logger.info(
                "Deletion propagation: removed %d entities for vault-deleted files under %s",
                entities_deleted,
                directory,
            )

        edges_deleted = 0
        for row in edge_rows:
            parsed = parse_edge_identity(str(row["entity_uid"]))
            rel_type = RelationshipName.from_string(parsed[1]) if parsed else None
            if parsed is None or rel_type is None:
                # Unparseable identity — clean the tracking row, leave the graph.
                self.logger.warning(
                    "Edge deletion skipped (unparseable identity %r) for %s — "
                    "removing tracking row only",
                    row["entity_uid"],
                    row["file_path"],
                )
                cleanup_result = await self.delete_ingestion_metadata([Path(str(row["file_path"]))])
                if cleanup_result.is_error:
                    return Result.fail(cleanup_result)
                stale_removed += 1
                continue
            edge_result = await self.backend.delete_edge_with_metadata(
                str(row["file_path"]), parsed[0], parsed[2], rel_type
            )
            if edge_result.is_error:
                return Result.fail(edge_result)
            edges_deleted += 1
        if edges_deleted:
            self.logger.info(
                "Deletion propagation: removed %d relationships for vault-deleted "
                "edge files under %s",
                edges_deleted,
                directory,
            )

        return Result.ok(
            DeletionReconciliation(
                entities_deleted=entities_deleted,
                edges_deleted=edges_deleted,
                stale_metadata_removed=stale_removed,
                ownership_mismatches=ownership_mismatches,
            )
        )

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
            while chunk := f.read(8192):
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
            metadata = metadata_map.get(self._canonical(file_path))
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
