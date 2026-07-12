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
from typing import TYPE_CHECKING, Any

from core.constants import MASS_DELETION_MAX_FRACTION, MASS_DELETION_MIN_COUNT
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.services.ingestion.config import is_ingestible_path
from core.services.ingestion.move_detection import (
    MoveCandidate,
    NewFileCandidate,
    match_moves_by_hash,
)
from core.services.ingestion.types import (
    AppliedMove,
    DeletionPlan,
    DeletionReconciliation,
    MovePlan,
    PlannedEdgeDeletion,
    PlannedEntityDeletion,
)
from core.utils.logging import get_logger
from core.utils.path_display import display_path
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


@dataclass(frozen=True)
class _GoneRowClassification:
    """Gone-row classification shared by ``plan_deletions`` and the move pre-pass.

    Pattern scope, collectible check, moved/stale split, and owner-scope
    filtering are applied here; the mass-deletion valves are NOT — they are
    deletion-only safety devices, applied by ``plan_deletions`` on top. The
    move pre-pass must see candidates even when a whole-folder rename makes
    every old path physically vanish (the case the physical-existence valve
    reads as "unmounted vault"; for MOVES the disambiguating evidence is the
    new files on disk, which an unmounted vault cannot produce).
    """

    all_tracked: list[dict[str, Any]]
    stale_rows: list[dict[str, Any]]
    # Owner-filtered entity delete candidates (edge rows split out).
    entity_rows: list[dict[str, Any]]
    edge_rows: list[dict[str, Any]]
    ownership_mismatches: list[str]


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

    async def _classify_gone_rows(
        self,
        directory: Path,
        pattern: str = "*",
        *,
        allowlist: "SyncAllowlist | None" = None,
        owner_uid: UserUID | None = None,
    ) -> Result[_GoneRowClassification | None]:
        """Shared gone-row classification — the valve-free half of ``plan_deletions``.

        Applies pattern scope, the collectible check (``is_ingestible_path`` —
        wall symmetry with ``collect_files``), the moved/stale split (uid still
        claimed by a collectible file → stale row, entity survives), the
        entity/edge split, and the owner-scope filter (fail-closed: an owner
        lookup error fails the run rather than falling through to an unscoped
        delete). Returns ``None`` when nothing is tracked in scope or nothing
        is gone.

        Deliberately does NOT apply the mass-deletion valves: those protect
        DELETION. The move pre-pass consumes this classification too, and must
        see candidates even when a whole-folder rename makes every old path
        vanish at once — the physical-existence valve reads that as an
        unmounted vault, but a real unmount produces no new files to match, so
        move detection stays inert there without the valve (Codex #617).

        Backend (reads only): IngestionBackend.get_tracked_files_under /
        get_entity_owner_uids.
        """
        # Trailing separator so /vault/a never matches /vault/abc.
        prefix = str(directory.resolve()).rstrip("/") + "/"
        tracked_result = await self.backend.get_tracked_files_under(prefix)
        if tracked_result.is_error:
            return Result.fail(tracked_result)

        all_tracked = tracked_result.value or []
        tracked = [row for row in all_tracked if _matches_pattern(str(row["file_path"]), pattern)]
        if not tracked:
            return Result.ok(None)

        def _collectible(row: dict[str, Any]) -> bool:
            # Survives iff collect_files would still collect it: on disk AND not
            # excluded by the vault wall (staging floor / allowlist).
            path = Path(str(row["file_path"]))
            return path.exists() and is_ingestible_path(path, allowlist)

        # "gone" = deleted from disk OR now walled — both are retracted.
        gone = [row for row in tracked if not _collectible(row)]
        if not gone:
            return Result.ok(None)

        # Identities still claimed by a file that would still be collected =
        # moves/renames to an allowed location (covers duplicate edge files too).
        # Claims are checked against ALL tracked rows, not just the pattern scope —
        # an identity owned by an out-of-scope allowed file must survive.
        live_uids = {row["entity_uid"] for row in all_tracked if _collectible(row)}
        stale_rows = [row for row in gone if row["entity_uid"] in live_uids]
        delete_rows = [row for row in gone if row["entity_uid"] not in live_uids]

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
                # Mismatch rows surface in the sync UI/API — render paths
                # relative to the sync root; the log below keeps absolutes.
                for row in skipped:
                    ownership_mismatches.append(
                        f"deletion skipped for {display_path(str(row['file_path']), directory)}: "
                        f"entity {row['entity_uid']} belongs to a different user than this "
                        "vault's owner — resolve ownership before deleting"
                    )
                self.logger.warning(
                    "Deletion reconciliation: skipped %d entity deletion(s) under %s "
                    "owned by a different user than the vault owner %s: %s",
                    len(skipped),
                    directory,
                    owner_uid,
                    ", ".join(str(row["file_path"]) for row in skipped),
                )

        return Result.ok(
            _GoneRowClassification(
                all_tracked=all_tracked,
                stale_rows=stale_rows,
                entity_rows=entity_rows,
                edge_rows=edge_rows,
                ownership_mismatches=ownership_mismatches,
            )
        )

    async def plan_deletions(
        self,
        directory: Path,
        pattern: str = "*",
        *,
        allowlist: "SyncAllowlist | None" = None,
        owner_uid: UserUID | None = None,
    ) -> Result[DeletionPlan]:
        """
        Classify what deletion reconciliation WOULD do — read-only.

        The planning half of ``reconcile_deletions``: performs the full
        classification (pattern scope, collectible check, moved/stale split,
        both mass-deletion valves, owner-scope filtering, edge parseability)
        and returns a :class:`DeletionPlan` without deleting anything. Reads
        only: tracked rows (``get_tracked_files_under``), on-disk existence,
        and — when ``owner_uid`` is set — entity owners
        (``get_entity_owner_uids``). Display paths in the plan are rendered
        vault-relative against ``directory`` (#525 sanitization policy).

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

        Backend (reads only): IngestionBackend.get_tracked_files_under /
        get_entity_owner_uids.
        """
        classification_result = await self._classify_gone_rows(
            directory, pattern, allowlist=allowlist, owner_uid=owner_uid
        )
        if classification_result.is_error:
            return Result.fail(classification_result)
        classification = classification_result.value
        if classification is None:
            return Result.ok(DeletionPlan())

        all_tracked = classification.all_tracked
        stale_rows = classification.stale_rows
        entity_rows = classification.entity_rows
        edge_rows = classification.edge_rows
        ownership_mismatches = list(classification.ownership_mismatches)

        # Mass-deletion valve is PHYSICAL-existence only (mount detection), so a
        # wall change that leaves files on disk still purges them.
        physically_present = [row for row in all_tracked if Path(str(row["file_path"])).exists()]
        if not physically_present:
            # Refusal warnings surface in the sync UI/API — say "this vault",
            # never the absolute directory (host-path leak). The log keeps it.
            warning = (
                f"Deletion reconciliation refused: all {len(all_tracked)} tracked "
                "files in this vault are missing — looks like an unmounted "
                "vault or sync wipe, not authoring. Delete explicitly via the "
                "ingestion dashboard if intended."
            )
            self.logger.warning("%s [vault root: %s]", warning, directory)
            return Result.ok(DeletionPlan(mass_deletion_refused=True, refusal_warning=warning))

        # Split edge rows by parseability up front: an unparseable identity only
        # ever gets its tracking row cleaned (metadata-only, no graph data), so
        # it is classified BEFORE the threshold valve and never counted by it.
        deletable_edges: list[PlannedEdgeDeletion] = []
        unparseable_edge_paths: list[str] = []
        for row in edge_rows:
            parsed = parse_edge_identity(str(row["entity_uid"]))
            rel_type = RelationshipName.from_string(parsed[1]) if parsed else None
            if parsed is None or rel_type is None:
                # Unparseable identity — plan a tracking-row-only cleanup.
                self.logger.warning(
                    "Edge deletion skipped (unparseable identity %r) for %s — "
                    "removing tracking row only",
                    row["entity_uid"],
                    row["file_path"],
                )
                unparseable_edge_paths.append(str(row["file_path"]))
                continue
            deletable_edges.append(
                PlannedEdgeDeletion(
                    file_path=str(row["file_path"]),
                    from_uid=parsed[0],
                    to_uid=parsed[2],
                    rel_type=rel_type,
                    display_path=display_path(str(row["file_path"]), directory),
                )
            )

        # Threshold mass-deletion valve (Kody #524: placed after every
        # metadata-only path). It counts ONLY rows that would actually delete
        # graph data — owner-filtered entity rows plus parseable edge rows —
        # so vault reorganizations (stale rows), foreign-owned skips, and
        # malformed edges never inflate the ratio, and a refusal still leaves
        # all metadata-only cleanup done. The floor keeps small vaults /
        # small cleanups friction-free; the fraction catches a majority wipe
        # (e.g. deleting all-but-one file, which slips past the
        # physical-existence valve above).
        refusal_warning: str | None = None
        graph_delete_count = len(entity_rows) + len(deletable_edges)
        if (
            graph_delete_count >= MASS_DELETION_MIN_COUNT
            and graph_delete_count / len(all_tracked) > MASS_DELETION_MAX_FRACTION
        ):
            refusal_warning = (
                f"Deletion reconciliation refused: {graph_delete_count} of "
                f"{len(all_tracked)} tracked files in this vault would be "
                "deleted in one sync — that majority wipe looks like data loss, "
                "not authoring. Delete explicitly via the ingestion dashboard, "
                "or sync in smaller batches."
            )
            self.logger.warning("%s [vault root: %s]", refusal_warning, directory)

        return Result.ok(
            DeletionPlan(
                entity_deletions=tuple(
                    PlannedEntityDeletion(
                        file_path=str(row["file_path"]),
                        entity_uid=str(row["entity_uid"]),
                        display_path=display_path(str(row["file_path"]), directory),
                        content_hash=(
                            str(row["content_hash"]) if row.get("content_hash") else None
                        ),
                    )
                    for row in entity_rows
                ),
                edge_deletions=tuple(deletable_edges),
                stale_file_paths=tuple(str(row["file_path"]) for row in stale_rows),
                unparseable_edge_file_paths=tuple(unparseable_edge_paths),
                ownership_mismatches=tuple(ownership_mismatches),
                mass_deletion_refused=refusal_warning is not None,
                refusal_warning=refusal_warning,
            )
        )

    async def detect_and_apply_moves(
        self,
        directory: Path,
        files_to_process: list[Path],
        pattern: str = "*",
        *,
        allowlist: "SyncAllowlist | None" = None,
        owner_uid: UserUID | None = None,
    ) -> Result[MovePlan]:
        """Content-hash move pre-pass: turn uid-less renames into row rewrites.

        A uid-less vault file's identity is path-keyed (#616), so a rename is
        a new path — without this pass the sync mints a fresh uid at the new
        path and deletion reconciliation deletes the old node, losing the
        uid, grounding edges, manual/MOC links, and ``created_at``. A pure
        rename preserves content, so the old row and the new file share a
        SHA-256: for each unambiguous 1:1 match this pass rewrites the
        tracker row (old path → new path, SAME uid), after which
        ``_resolve_prior_user_entry_uid`` reuses the uid (in-place upsert)
        and reconciliation sees no row for the old path (no deletion).

        MUST run after ``files_to_process`` is collected and BEFORE both the
        ingestion loop and deletion reconciliation — later, and the new path
        has already minted a fresh uid or the old node is already gone.

        Phase 1 is exact-hash only: a rename + edit in the same sync changes
        the hash and falls back to delete+create (the Phase 2 similarity
        follow-up consumes ``HashMatchResult``'s residual). Safety rails:
        - ambiguity (2+ gone rows or 2+ new files sharing a hash) → skip;
        - trivial content (empty / whitespace-only) → never matched;
        - only rows whose uid names a live node are rewritten (mirrors #616);
        - foreign-owned rows never qualify (shared owner-scope filter).

        Move-source candidates come from ``_classify_gone_rows`` — the same
        valve-free classification ``plan_deletions`` builds on — so a move can
        only ever REDUCE the delete set. The mass-deletion valves deliberately
        do NOT gate this pass (Codex #617): a whole-folder rename makes every
        old path vanish at once, which the physical-existence valve reads as
        an unmounted vault — but a real unmount produces no new files to
        match, so move detection is naturally inert there, while a genuine
        reorganization gets its identities preserved. Authored-uid files don't
        need this pass (the uid-based moved/stale split already preserves
        them) but pass through harmlessly: rewriting to the same authored uid
        is what ingestion would stamp anyway.

        The rewritten row carries pending markers (empty hash, mtime 0): the
        current run's ingest re-stamps it on success, and if that ingest
        fails the next sync re-processes the file instead of hash-skipping a
        node whose path metadata never updated.

        Backend: IngestionBackend.get_tracked_files_under (via the shared
        classification) / get_live_entity_uids / update_ingestion_metadata /
        delete_ingestion_metadata.
        """
        if not files_to_process:
            return Result.ok(MovePlan())

        classification_result = await self._classify_gone_rows(
            directory, pattern, allowlist=allowlist, owner_uid=owner_uid
        )
        if classification_result.is_error:
            return Result.fail(classification_result)
        classification = classification_result.value
        if classification is None:
            return Result.ok(MovePlan())

        candidates = [
            MoveCandidate(
                file_path=str(row["file_path"]),
                entity_uid=str(row["entity_uid"]),
                content_hash=str(row["content_hash"]),
            )
            for row in classification.entity_rows
            if row.get("content_hash")
        ]
        if not candidates:
            return Result.ok(MovePlan())

        # New files = files this sync will process that have NO tracker row
        # (identity unclaimed). Queried directly — not derived from the smart-
        # mode "changed" flags — so force runs classify identically.
        meta_result = await self.get_ingestion_metadata(files_to_process)
        if meta_result.is_error:
            return Result.fail(meta_result)
        tracked_paths = set(meta_result.value)

        new_files: list[NewFileCandidate] = []
        for file_path in files_to_process:
            canonical = self._canonical(file_path)
            if canonical in tracked_paths:
                continue
            try:
                data = file_path.read_bytes()
            except OSError:
                continue
            if not data.strip():
                # Trivial content: empty-note hash collisions are meaningless.
                continue
            new_files.append(
                NewFileCandidate(
                    file_path=canonical,
                    content_hash=hashlib.sha256(data).hexdigest(),
                )
            )
        if not new_files:
            return Result.ok(MovePlan())

        match = match_moves_by_hash(candidates, new_files)
        for message in match.ambiguous:
            self.logger.info("Move detection: %s", message)
        if not match.pairs:
            return Result.ok(MovePlan())

        # Live-node guard (mirrors #616): a stale row pointing at a deleted
        # node is not a move source.
        live_result = await self.backend.get_live_entity_uids(
            [pair.row.entity_uid for pair in match.pairs]
        )
        if live_result.is_error:
            return Result.fail(live_result)
        live_uids = {str(record["uid"]) for record in live_result.value or []}

        applied: list[AppliedMove] = []
        for pair in match.pairs:
            if pair.row.entity_uid not in live_uids:
                self.logger.info(
                    "Move detection: skipping %s → %s — entity %s no longer exists",
                    pair.row.file_path,
                    pair.new_file.file_path,
                    pair.row.entity_uid,
                )
                continue
            # Upsert the new-path row FIRST, then drop the old one — a crash
            # between the two leaves both rows claiming one uid, which the
            # uid-based moved/stale split resolves as a stale row, never a
            # node deletion.
            upsert_result = await self.backend.update_ingestion_metadata(
                {
                    "file_path": pair.new_file.file_path,
                    "content_hash": "",  # pending marker — see docstring
                    "file_mtime": 0.0,
                    "entity_uid": pair.row.entity_uid,
                }
            )
            if upsert_result.is_error:
                return Result.fail(upsert_result)
            delete_result = await self.backend.delete_ingestion_metadata([pair.row.file_path])
            if delete_result.is_error:
                return Result.fail(delete_result)
            self.logger.info(
                "Move detected (content hash): %s → %s (uid %s)",
                pair.row.file_path,
                pair.new_file.file_path,
                pair.row.entity_uid,
            )
            applied.append(
                AppliedMove(
                    old_path=pair.row.file_path,
                    new_path=pair.new_file.file_path,
                    entity_uid=pair.row.entity_uid,
                    display_old=display_path(pair.row.file_path, directory),
                    display_new=display_path(pair.new_file.file_path, directory),
                )
            )

        return Result.ok(MovePlan(applied=tuple(applied)))

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

        Plan/execute split: :meth:`plan_deletions` performs ALL classification
        (the five guards documented there) read-only; this method executes the
        resulting :class:`DeletionPlan`. A mass-deletion refusal still executes
        the metadata-only cleanup (stale rows, unparseable edge rows) — only
        graph-data deletion is refused.

        Backend: IngestionBackend.get_tracked_files_under / get_entity_owner_uids /
        delete_entities_with_metadata.
        """
        plan_result = await self.plan_deletions(
            directory, pattern, allowlist=allowlist, owner_uid=owner_uid
        )
        if plan_result.is_error:
            return Result.fail(plan_result)
        return await self._execute_deletion_plan(plan_result.value, directory)

    async def _execute_deletion_plan(
        self, plan: DeletionPlan, directory: Path
    ) -> Result[DeletionReconciliation]:
        """Execute a :class:`DeletionPlan`: metadata cleanup, then graph deletes."""
        stale_removed = 0
        if plan.stale_file_paths:
            stale_result = await self.delete_ingestion_metadata(
                [Path(p) for p in plan.stale_file_paths]
            )
            if stale_result.is_error:
                # A swallowed failure here would leave the old path's row to be
                # rediscovered every run while the API reports a clean sync.
                return Result.fail(stale_result)
            stale_removed = stale_result.value

        for path in plan.unparseable_edge_file_paths:
            cleanup_result = await self.delete_ingestion_metadata([Path(path)])
            if cleanup_result.is_error:
                return Result.fail(cleanup_result)
            stale_removed += 1

        if plan.mass_deletion_refused:
            # Metadata-only cleanup above still ran (Kody #524); graph-data
            # deletion is refused.
            return Result.ok(
                DeletionReconciliation(
                    mass_deletion_refused=True,
                    refusal_warning=plan.refusal_warning,
                    stale_metadata_removed=stale_removed,
                    ownership_mismatches=list(plan.ownership_mismatches),
                )
            )

        entities_deleted = 0
        if plan.entity_deletions:
            items = [
                {"file_path": planned.file_path, "entity_uid": planned.entity_uid}
                for planned in plan.entity_deletions
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
        for planned_edge in plan.edge_deletions:
            edge_result = await self.backend.delete_edge_with_metadata(
                planned_edge.file_path,
                planned_edge.from_uid,
                planned_edge.to_uid,
                planned_edge.rel_type,
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
                ownership_mismatches=list(plan.ownership_mismatches),
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
    "EDGE_UID_PREFIX",
    "FileIngestionMetadata",
    "IngestionDecision",
    "IngestionTracker",
    "edge_identity",
    "parse_edge_identity",
]
