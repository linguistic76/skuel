"""
VaultReconciler — ADR-070 Stage 1
===================================

Orchestrates the bidirectional Obsidian ↔ SKUEL vault sync:

    Inbound  (vault → SKUEL):  ingest_directory → extract_activities → Tasks
    Outbound (SKUEL → vault):  inject 🆔 IDs, write [x] + ✅ done-dates

Triggered by the user's "Update from my vault" button
(``POST /api/vault/sync``).  Stage 1 uses ``FilesystemVaultAdapter`` for
outbound writes; Stage 2+ swaps in ``LocalAgentVaultAdapter`` without
changing any logic here.

**First-run notice** (ADR-070 Decision 6, amended 2026-07-05):
Before touching the vault AT ALL — inbound read included — a personal sync
checks ``user.preferences.vault_write_consent``.  Returns
``Result.ok(VaultSyncStats(first_run_notice=True))`` on the first call,
without ingesting anything, so the route can render the consent modal
without treating it as an error.  After the user grants consent,
``POST /api/vault/sync/consent`` sets the preference flag and subsequent
sync calls proceed normally.  The content vault is admin inbound-only and
stays consent-free.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import asyncio
import re
import secrets
import string
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryUpdateRequest
from core.ports.vault_bridge_protocol import (
    VAULT_ID_RE,
    TaskLineUpdate,
    VaultSyncStats,
    normalize_vault_line_hash,
)
from core.services.ingestion.config import collect_files
from core.services.ingestion.ingestion_tracker import IngestionTracker
from core.services.ingestion.types import DryRunPreview, IncrementalStats, IngestionStats
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.path_display import display_path, strip_root_prefix
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry
    from core.ports.embedding_coverage_protocols import EmbeddingCoverageOperations
    from core.services.embeddings.retrievability import EmbeddingCoverage
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
    from core.services.tasks_service import TasksService
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

logger = get_logger("skuel.services.vault.reconciler")

_BASE36 = string.ascii_lowercase + string.digits

# Which vault folders may be ingested is now decided by a fail-closed allowlist
# (``SyncAllowlist``, seeded from the code-defined ``_DEFAULT_SYNC_SUBDIRS``)
# applied inside
# ``UnifiedIngestionService.ingest_directory`` — the single chokepoint both this
# reconciler and the HTTP /api/ingest/* door share. Everything under the vault
# root that is not explicitly allowed (the je_* journal staging folders,
# templates, loose notes, …) is walled off by default, so this reconciler no
# longer maintains its own je_* denylist.
_UNCHECKED_RE = re.compile(r"^[-*]\s*\[\s*\]")
_CHECKED_RE = re.compile(r"^[-*]\s*\[[xX]\]")


@dataclass(frozen=True)
class VaultDescription:
    """Read-only, UI-safe summary of what a vault sync may touch.

    The data behind the sync page's "What SKUEL can see" panel and the consent
    form's folder list — the wall shown to the user comes from the live
    allowlist, never from hardcoded prose. Folder names are RELATIVE to the
    vault root (#525 policy: absolute host paths never leave the service
    layer). ``whole_vault_open`` marks the combined single-vault configuration
    where ``build_sync_allowlist`` opens the entire root (the ``je_*`` staging
    floor still applies). A user with no personal vault gets
    ``vault_configured=False`` — a normal state, not an error.
    """

    vault_configured: bool
    allowed_folders: tuple[str, ...] = ()
    whole_vault_open: bool = False


# How many example file names a preview lists per category — enough to see
# what a sync would touch without dumping a thousand-line vault inventory.
PREVIEW_EXAMPLE_LIMIT = 20


@dataclass(frozen=True)
class VaultSyncPreview:
    """Dry-run report of what a vault sync WOULD do — nothing is written.

    Built by :meth:`VaultReconciler.preview` from read-only machinery only
    (tracker metadata compare + ``IngestionTracker.plan_deletions``). Every
    path in this object is vault-RELATIVE (#525 sanitization policy — absolute
    host paths never leave the service layer). ``first_run_notice`` mirrors
    the sync consent gate: preview reads the vault (hashing/comparing files),
    so a not-yet-consented user gets the consent form, not a preview.

    Outbound preview (would-inject 🆔 IDs / would-mark-done) is deliberately
    deferred — this covers the inbound ingest + deletion halves only.
    """

    first_run_notice: bool = False
    would_ingest_count: int = 0
    would_ingest_new: int = 0
    would_ingest_changed: int = 0
    would_ingest_examples: tuple[str, ...] = ()
    would_delete_entities: int = 0
    would_delete_entity_examples: tuple[str, ...] = ()
    would_delete_edges: int = 0
    would_delete_edge_examples: tuple[str, ...] = ()
    stale_cleanup_count: int = 0
    ownership_mismatches: tuple[str, ...] = ()
    refusal_warning: str | None = None


def _rel_visit_order(
    rel: dict[str, Any],  # boundary: EXTRACTED_FROM row — heterogeneous by protocol
) -> str:
    """Stable visit order for one entry's ``EXTRACTED_FROM`` rows.

    The backend read is unordered; the reconciler correlates edges to vault
    lines while walking these, so the walk needs an order that does not depend
    on Neo4j traversal.
    """
    return str(rel.get("entity_uid", ""))


@dataclass(frozen=True)
class _PendingInjection:
    """One 🆔 to persist onto its ``EXTRACTED_FROM`` edge after the file write.

    ``update_index`` points at the queued ``TaskLineUpdate`` whose OWN outcome
    decides whether the 🆔 may be persisted (``WriteResult.was_applied``).
    ``None`` marks the recovery case — the vault line already carried the 🆔,
    so nothing was queued and there is no write to gate on.
    """

    entity_uid: str
    vault_id: str
    update_index: int | None


def _mint_vault_id() -> str:
    """Mint a 6-character base-36 vault ID with ``sk_`` prefix (ADR-070 Decision 1)."""
    return "sk_" + "".join(secrets.choice(_BASE36) for _ in range(6))


def _find_line_by_hash(content: str, target_hash: str, claimed: set[int]) -> int | None:
    """Return 0-based index of the first UNCLAIMED checkbox line matching the hash.

    ``claimed`` holds line indices already spoken for by another entity in the
    same pass. Two identical task lines in one note share a
    ``source_line_hash`` — the digest is content-based and 🆔-blind by design —
    so a bare first-match lookup hands the SAME line to both of their entities:
    they mint duplicate ids, or a recovery copies the first line's 🆔 onto the
    second entity's edge and its completion write-back lands on the wrong line.
    """
    for i, line in enumerate(content.splitlines()):
        if i in claimed:
            continue
        if _UNCHECKED_RE.match(line) or _CHECKED_RE.match(line):
            if normalize_vault_line_hash(line) == target_hash:
                return i
    return None


class VaultReconciler:
    """Bidirectional vault sync orchestrator (ADR-070).

    Wires together the ingestion pipeline (inbound) and VaultBridgePort
    adapter (outbound) to implement the full sync loop. Descriptor-driven: a
    single instance serves every vault (content + personal) — the per-vault
    root, owner, allowlist, and bridge adapter come from the
    :class:`VaultRegistry`, not from instance state.
    """

    def __init__(
        self,
        registry: VaultRegistry,
        unified_ingestion: UnifiedIngestionService,
        user_entry_service: UserEntryService,
        tasks_service: TasksService,
        user_service: UserService,
        embedding_coverage: EmbeddingCoverageOperations | None = None,
    ) -> None:
        self._registry = registry
        self._ingestion = unified_ingestion
        self._user_entry = user_entry_service
        self._tasks = tasks_service
        self._user_service = user_service
        # Optional retrievability gauge: when wired, sync() probes embedding
        # coverage before and after ingest so the stats can say how much of
        # this sync's content is not yet vector-searchable. None → the
        # retrievability fields stay at their defaults (no probe, no flag).
        self._embedding_coverage = embedding_coverage
        # Per-root concurrency locks, keyed by resolved vault root. Created
        # lazily; bounded by the number of distinct vault roots. Different
        # roots never serialize against each other.
        self._root_locks: dict[str, asyncio.Lock] = {}

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    @property
    def embedding_coverage(self) -> EmbeddingCoverageOperations | None:
        """The wired retrievability gauge, or ``None`` when not composed.

        Read-only door for one-shot script syncs (``vault_bridge_sync.py``)
        that drain the embedding worker AFTER ``sync()`` returns: the stats'
        retrievability figures describe the pre-drain graph, so the script
        re-probes through the same gauge to report post-drain coverage.
        """
        return self._embedding_coverage

    async def sync(
        self, kind: VaultKind, user_uid: UserUID, *, force: bool = False
    ) -> Result[VaultSyncStats]:
        """Run a full vault sync for ``kind``.

        ``user_uid`` is the acting user; for ``VaultKind.CONTENT`` it is ignored
        (the content vault's fixed admin owner wins). All per-vault specifics —
        root, ingest-owner, allowlist, outbound bridge, and whether the task
        round-trip runs — come from the resolved :class:`VaultDescriptor`.

        ``force=True`` re-processes unchanged files too (re-chunk/migration
        campaigns) while keeping smart-mode semantics — the wall, metadata
        re-stamping, and deletion reconciliation all stay active.

        1. For personal (task-round-trip) vaults, check vault sync consent on
           the owner (ADR-070 Decision 6 first-run gate) — BEFORE any read.
           Not yet consented → return ``first_run_notice`` without ingesting.
        2. For a ``local_agent``-transport vault (``descriptor.mirror_pull``
           set, ADR-075 Decision 4), refresh the server-side staging mirror
           from the user's agent — fetch changed/new allowed files, delete
           mirror files absent from the agent's listing. No connected agent →
           the sync fails fast with a clear integration error, mirror
           untouched. Everything downstream sees the mirror as the vault.
        3. Ingest the vault directory (smart mode — only changed files, unless
           ``force``), attributed to the descriptor's owner, walled by the
           descriptor's allowlist.
        4. If the vault supports the task round-trip, for each ingested
           UserEntry with the EXTRACT_ACTIVITIES pipeline:
           a. inject 🆔 IDs into ID-less task lines;
           b. write ``[x]`` + ``✅ date`` for SKUEL-completed tasks.
        """
        descriptor_result = self._resolve_guarded(kind, user_uid)
        if descriptor_result.is_error:
            return Result.fail(descriptor_result)
        descriptor = descriptor_result.value
        owner = descriptor.owner_uid

        async with self._root_lock(descriptor):
            # Step 1: first-run consent gate (ADR-070 Decision 6, amended
            # 2026-07-05) — on the vault owner, BEFORE the first inbound read.
            # Consent covers the whole sync: SKUEL reading the allowed doorway
            # folders as much as writing 🆔 IDs back. Only vaults that support
            # the task round-trip belong to a consenting user, so the gate
            # engages there; the content vault is admin inbound-only and stays
            # consent-free. Curriculum writeback, when built, will engage the
            # same gate without blocking inbound ingest meanwhile.
            consent_result = await self._needs_first_run_consent(descriptor)
            if consent_result.is_error:
                return Result.fail(consent_result)
            if consent_result.value:
                return Result.ok(VaultSyncStats(first_run_notice=True))

            stats = VaultSyncStats()

            # Retrievability before-probe: a snapshot of embedding coverage
            # BEFORE ingest, so the after-probe can report the delta — how many
            # items THIS sync added that are not yet vector-searchable.
            # Optional and fail-soft; see _apply_retrievability.
            coverage_before: EmbeddingCoverage | None = None
            if self._embedding_coverage is not None:
                coverage_before = await self._probe_coverage()

            # Step 2: mirror refresh (ADR-075 Decision 4) — local_agent
            # transport only. Runs INSIDE the per-root lock (a preview can
            # never race a half-refreshed mirror) and AFTER the consent gate
            # (consent covers the first list/read RPC as much as a local read).
            # Pull warnings survive into the sync stats (G10): a torn read or
            # walled row is a real "your sync did not cover this" signal.
            if descriptor.mirror_pull is not None:
                pull_result = await descriptor.mirror_pull.refresh(owner)
                if pull_result.is_error:
                    return Result.fail(pull_result)
                stats.warnings.extend(pull_result.value.warnings)

            # Step 3: ingest (inbound — smart mode skips unchanged files). The
            # descriptor's own fail-closed allowlist scopes which folders are
            # read; entries are attributed to the descriptor's owner. Passing
            # ``user_uid``/``allowlist`` explicitly is belt-and-suspenders: the
            # ingestion mechanism resolves the same owner and wall by path
            # (resolve_by_path), and the guard above enforces that by-kind and
            # by-path agree on this root.
            # ``validate_targets=True`` (G10): dangling relationship targets
            # no-op inside the relationship Cypher, so real syncs must run the
            # pre-check and surface every phantom UID as a warning — not a
            # silent row drop, not a hard failure.
            ingest_result = await self._ingestion.ingest_directory(
                descriptor.root,
                ingestion_mode="smart",
                force=force,
                validate_targets=True,
                user_uid=owner,
                allowlist=descriptor.allowlist,
            )
            if ingest_result.is_error:
                return Result.fail(ingest_result)
            _merge_ingest_stats(stats, ingest_result.value, descriptor.root)

            # Retrievability after-probe: fill the coverage fields now that
            # ingest has persisted — before the outbound half, so BOTH return
            # paths below carry them. Corpus-wide ABSOLUTES only for content
            # syncs (admin-only door): a personal sync's stats reach a
            # non-admin surface, which must not see corpus aggregates.
            if self._embedding_coverage is not None:
                await self._apply_retrievability(
                    stats,
                    coverage_before,
                    include_absolutes=descriptor.kind is VaultKind.CONTENT,
                )

            # Step 4: outbound. Only vaults that support the task round-trip
            # have anything to write back; curriculum vaults are inbound-only
            # today (structural no-op).
            if not descriptor.supports_task_round_trip:
                return Result.ok(stats)

            await self._run_outbound(descriptor, stats)
            return Result.ok(stats)

    async def preview(self, kind: VaultKind, user_uid: UserUID) -> Result[VaultSyncPreview]:
        """Dry-run: report what :meth:`sync` WOULD do without writing anything.

        Same descriptor resolution, surface-independence guards, per-root lock,
        and first-run consent gate as :meth:`sync` — consent covers READING
        (ADR-070 Decision 6 amendment), and preview hashes/compares vault
        files, which is a read; a not-yet-consented user gets
        ``first_run_notice`` so the routes render the same consent form.

        Inbound half: the tracker's read-only compare (``collect_files`` under
        the descriptor's allowlist → ``get_ingestion_metadata`` →
        ``filter_files_needing_ingestion``) — never the ingest path. Deletion
        half: ``IngestionTracker.plan_deletions`` with the descriptor's
        allowlist + owner (the same scope ``sync``'s ingest passes when the
        registry governs the root). Neither the graph nor the vault is
        touched; outbound preview (would-inject 🆔 IDs / would-mark-done) is
        deferred.

        A preview never dials the agent (ADR-075 Decision 4): for a
        ``local_agent``-transport vault it reports the MIRROR's state as of
        the last refresh — read-only against server-local files, like every
        other preview.
        """
        descriptor_result = self._resolve_guarded(kind, user_uid)
        if descriptor_result.is_error:
            return Result.fail(descriptor_result)
        descriptor = descriptor_result.value

        # Same per-root lock as sync(): a preview racing a live sync would
        # compare against a half-updated tracker state and report noise.
        async with self._root_lock(descriptor):
            consent_result = await self._needs_first_run_consent(descriptor)
            if consent_result.is_error:
                return Result.fail(consent_result)
            if consent_result.value:
                return Result.ok(VaultSyncPreview(first_run_notice=True))

            backend = self._ingestion.ingestion_backend
            if backend is None:
                return Result.fail(
                    Errors.system(
                        "vault sync preview requires the ingestion tracking backend, "
                        "which is not wired in this composition",
                        user_message="Preview is unavailable — sync tracking is not configured.",
                    )
                )
            tracker = IngestionTracker(backend)

            # Single-vault guard (Kody #527): sync() inherits this check from
            # ingest_directory, but preview scans the root itself — without it
            # a preview of a directory nesting ANOTHER owner's vault would
            # list that owner's filenames and plan deletions sync would
            # refuse. Same predicate, same refusal.
            conflicting = self._registry.conflicting_nested_roots(
                descriptor.root, descriptor.owner_uid
            )
            if conflicting:
                return Result.fail(
                    Errors.validation(
                        "Directory scan would sweep a nested vault with a different "
                        f"owner (nested vault root(s): {', '.join(str(r) for r in conflicting)}); "
                        "scan a single vault root instead.",
                        field="directory",
                    )
                )

            # Inbound: which collected files would smart-mode ingest (new or
            # changed)? Tracker-level compare only — no ingest engine, no writes.
            files = collect_files(descriptor.root, "*", allowlist=descriptor.allowlist)
            metadata_result = await tracker.get_ingestion_metadata(files)
            if metadata_result.is_error:
                return Result.fail(metadata_result)
            to_ingest, decisions = tracker.filter_files_needing_ingestion(
                files, metadata_result.value
            )
            new_count = sum(1 for d in decisions if d.needs_ingestion and d.reason == "new")
            ingest_examples = tuple(
                f"{display_path(d.file_path, descriptor.root)}"
                f" ({'new' if d.reason == 'new' else 'changed'})"
                for d in decisions
                if d.needs_ingestion
            )[:PREVIEW_EXAMPLE_LIMIT]

            # Deletions: the read-only planning half of reconciliation, with
            # the same owner scope a descriptor-governed sync applies.
            plan_result = await tracker.plan_deletions(
                descriptor.root,
                "*",
                allowlist=descriptor.allowlist,
                owner_uid=descriptor.owner_uid,
            )
            if plan_result.is_error:
                return Result.fail(plan_result)
            plan = plan_result.value

            return Result.ok(
                VaultSyncPreview(
                    would_ingest_count=len(to_ingest),
                    would_ingest_new=new_count,
                    would_ingest_changed=len(to_ingest) - new_count,
                    would_ingest_examples=ingest_examples,
                    would_delete_entities=len(plan.entity_deletions),
                    would_delete_entity_examples=tuple(
                        planned.display_path for planned in plan.entity_deletions
                    )[:PREVIEW_EXAMPLE_LIMIT],
                    would_delete_edges=len(plan.edge_deletions),
                    would_delete_edge_examples=tuple(
                        planned.display_path for planned in plan.edge_deletions
                    )[:PREVIEW_EXAMPLE_LIMIT],
                    stale_cleanup_count=len(plan.stale_file_paths)
                    + len(plan.unparseable_edge_file_paths),
                    ownership_mismatches=plan.ownership_mismatches,
                    refusal_warning=plan.refusal_warning,
                )
            )

    def _resolve_guarded(self, kind: VaultKind, user_uid: UserUID) -> Result[VaultDescriptor]:
        """Resolve the descriptor for ``(kind, user_uid)`` with the surface-independence guards.

        By-kind and by-path resolution must agree on the root, otherwise the
        ingestion mechanism (which resolves owner + wall by path) would
        attribute a different owner than this by-kind sync. Kind disagreement
        is the combined-root config (VAULT_ROOT == INGESTION_PATH), where the
        single vault resolves to PERSONAL by-path: there is no distinct
        content vault, so a CONTENT sync would stamp content_owner_uid onto
        the user's own files. Refuse it — the combined vault syncs as
        PERSONAL. Owner disagreement is a nested-roots misconfiguration (e.g.
        a member vault placed inside the primary personal root): by-path
        governance belongs to the enclosing vault's owner, so syncing it as
        anyone else would split attribution. Refuse that too.
        """
        descriptor_result = self._registry.resolve(kind, user_uid)
        if descriptor_result.is_error:
            return Result.fail(descriptor_result)
        descriptor = descriptor_result.value

        by_path = self._registry.resolve_by_path(descriptor.root, descriptor.owner_uid)
        if by_path.is_ok and by_path.value.kind is not kind:
            return Result.fail(
                Errors.validation(
                    f"{kind.value} vault sync is unavailable in a combined-root "
                    "configuration (VAULT_ROOT coincides with INGESTION_PATH); the "
                    f"single vault resolves as {by_path.value.kind.value} — sync it "
                    "under that kind instead.",
                    field="kind",
                )
            )
        if by_path.is_ok and by_path.value.owner_uid != descriptor.owner_uid:
            return Result.fail(
                Errors.validation(
                    "vault sync refused: this vault root is governed by another "
                    "vault's owner by path (nested vault roots misconfiguration) — "
                    "move the vault outside the enclosing vault root.",
                    field="kind",
                )
            )
        return Result.ok(descriptor)

    def _root_lock(self, descriptor: VaultDescriptor) -> asyncio.Lock:
        """Per-root concurrency guard, shared by sync and preview.

        Two concurrent syncs of the same root would interleave ingest and
        outbound writes (only the per-file SHA-256 stale-read guard protects
        individual writes). A second operation on the SAME root simply waits
        its turn — it serializes, it does not error. Keyed by resolved root so
        distinct vault roots never block each other.
        """
        return self._root_locks.setdefault(str(descriptor.root.resolve()), asyncio.Lock())

    async def _needs_first_run_consent(self, descriptor: VaultDescriptor) -> Result[bool]:
        """Whether the first-run consent gate blocks this vault operation.

        True iff the vault supports the task round-trip (i.e. belongs to a
        consenting user — the content vault is admin inbound-only and stays
        consent-free) and its owner has not granted ``vault_write_consent``.
        Post-2026-07-05 amendment, consent covers READING as much as writing,
        so both sync and preview check it BEFORE any vault read.
        """
        if not descriptor.supports_task_round_trip:
            return Result.ok(False)
        user_result = await self._user_service.get_user(descriptor.owner_uid)
        if user_result.is_error:
            return Result.fail(user_result)
        user = user_result.value
        if user is None:
            return Result.fail(
                Errors.not_found(resource="User", identifier=str(descriptor.owner_uid))
            )
        return Result.ok(not user.preferences.vault_write_consent)

    async def _probe_coverage(self) -> EmbeddingCoverage | None:
        """One fail-soft embedding-coverage probe — ``None`` on error, logged.

        Backend: EmbeddingCoverageBackend.measure_embedding_coverage (a count
        query; CORE-tier safe, no embedding client involved).
        """
        if self._embedding_coverage is None:
            return None
        result = await self._embedding_coverage.measure_embedding_coverage()
        if result.is_error:
            logger.warning("embedding-coverage probe failed: %s", result.expect_error())
            return None
        return result.value

    async def _apply_retrievability(
        self,
        stats: VaultSyncStats,
        before: EmbeddingCoverage | None,
        *,
        include_absolutes: bool,
    ) -> None:
        """Fill the retrievability fields from a post-ingest coverage probe.

        Fail-soft by ruling: a failed probe sets ``coverage_probe_failed`` and
        NOTHING else — never a warning, never an error — so an optional
        probe's outage can never flip ``is_clean`` or turn a perfect sync's
        banner red. Absolute counts come from the after-probe alone; the
        delta needs both probes. Both probes are corpus-wide (the gauge's
        design), so the delta is the gap's growth across this sync's window:
        in the common case exactly what this sync added, though a concurrent
        writer on another root lands in the same window — every counted item
        is genuinely not yet searchable either way. Clamped at zero because
        the FULL-tier worker may embed concurrently mid-sync, shrinking the
        missing count — never report a negative credit.

        ``include_absolutes`` gates the corpus-wide counts: only content-vault
        syncs (admin-only door) carry them. A personal sync's stats serialize
        through non-admin responses, and corpus aggregates over other users'
        entities are admin-surface data (the PR-gauge lives behind
        /admin/knowledge-health for the same reason) — a personal sync
        reports only its window delta and the probe flag.
        """
        after = await self._probe_coverage()
        if after is None or before is None:
            stats.coverage_probe_failed = True
        if after is None:
            return
        if include_absolutes:
            stats.chunks_awaiting_embedding = after.missing_chunks
            stats.entities_awaiting_embedding = after.missing_entities
        if before is not None:
            stats.retrievability_delta = max(0, after.missing - before.missing)

    async def grant_consent(self, user_uid: UserUID) -> Result[None]:
        """Record vault-write consent for the user (ADR-070 Decision 6 first-run gate)."""
        result = await self._user_service.update_preferences(
            user_uid, {"vault_write_consent": True}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(None)

    async def describe(self, kind: VaultKind, user_uid: UserUID) -> Result[VaultDescription]:
        """Describe the privacy wall of ``(kind, user_uid)``'s vault — read-only.

        The sanctioned read door for UI surfaces (sync page, consent form):
        routes never touch the registry directly. Reads nothing from the vault;
        it only reports what a sync WOULD be allowed to read, derived from the
        descriptor's fail-closed allowlist. No vault for this user →
        ``vault_configured=False`` (not an error — the page renders a
        "no vault configured" note).

        For a ``local_agent``-transport vault with a live agent, the wall is
        additionally sourced from the agent's ``describe_wall`` (ADR-075 B4):
        the shown folders are the INTERSECTION of server allowlist and
        agent-side wall — what a sync can actually reach. Folder names are the
        pre-consent maximum (ADR-075 Decision 5), so this read is
        consent-free; no connected agent → the server-side wall is shown
        unchanged.
        """
        descriptor_result = self._registry.resolve(kind, user_uid)
        if descriptor_result.is_error:
            return Result.ok(VaultDescription(vault_configured=False))

        descriptor = descriptor_result.value
        allowlist = descriptor.allowlist
        root = allowlist.governed_root
        folders: list[str] = []
        whole_vault_open = False
        for allowed in allowlist.allowed_dirs:
            if allowed == root:
                # build_sync_allowlist's single-vault case: the whole root is
                # open (only the je_* staging floor applies).
                whole_vault_open = True
            elif allowed.is_relative_to(root):
                folders.append(allowed.relative_to(root).as_posix())
            # An allowed dir outside the governed root cannot come out of
            # build_sync_allowlist (such entries are dropped there) — skip
            # defensively rather than leak an absolute path (#525).

        if descriptor.mirror_pull is not None:
            wall_result = await descriptor.mirror_pull.describe_wall(descriptor.owner_uid)
            if wall_result.is_ok:
                agent_folders = set(wall_result.value.allowed_folders)
                folders = sorted(
                    agent_folders if whole_vault_open else set(folders) & agent_folders
                )
                whole_vault_open = False

        return Result.ok(
            VaultDescription(
                vault_configured=True,
                allowed_folders=tuple(sorted(folders)),
                whole_vault_open=whole_vault_open,
            )
        )

    # =========================================================================
    # OUTBOUND
    # =========================================================================

    async def _run_outbound(self, descriptor: VaultDescriptor, stats: VaultSyncStats) -> None:
        """Inject IDs and write done-status for all of the owner's vault entries."""
        owner = descriptor.owner_uid
        page_size = 500
        offset = 0
        resolved_vault_root = descriptor.root.resolve()

        while True:
            entries_result = await self._user_entry.list_for_user(
                user_uid=owner,
                pipeline=Pipeline.EXTRACT_ACTIVITIES,
                limit=page_size,
                offset=offset,
            )
            if entries_result.is_error:
                stats.errors.append(f"list_for_user failed: {entries_result.expect_error()}")
                return

            entries = entries_result.value or []
            for entry in entries:
                vault_file_path = (entry.metadata or {}).get("vault_file_path")
                if not vault_file_path:
                    continue
                # Guard: resolve both paths so ".." segments cannot bypass the check,
                # and skip upload entries whose source path is outside this vault root.
                resolved_vfp = Path(vault_file_path).resolve()
                if not resolved_vfp.is_relative_to(resolved_vault_root):
                    continue
                await self._process_entry_outbound(descriptor, entry, str(resolved_vfp), stats)

            if len(entries) < page_size:
                break
            offset += page_size

    async def _process_entry_outbound(
        self,
        descriptor: VaultDescriptor,
        entry: UserEntry,
        vault_file_path: str,
        stats: VaultSyncStats,
    ) -> None:
        """Process one UserEntry: inject IDs for new tasks, mark done for completed.

        A minted 🆔 is persisted onto its ``EXTRACTED_FROM`` edge only when the
        write reports THAT injection as applied — never on file-level success
        alone (deferred-work § Phantom-🆔).
        """
        owner = descriptor.owner_uid
        rels_result = await self._user_entry.get_extracted_entities(entry.uid)
        if rels_result.is_error:
            stats.errors.append(
                f"get_extracted_entities failed for {entry.uid}: {rels_result.expect_error()}"
            )
            return

        rels = rels_result.value or []
        if not rels:
            return
        # The backend read carries no ORDER BY, so give the pass a stable order
        # of its own: which edge is visited first otherwise decides which line a
        # recovery adopts. This makes the outcome REPRODUCIBLE — it does not
        # recover a "true" edge→line mapping for byte-identical lines, because
        # none is recorded and none exists: the digest is position-free and
        # 🆔-blind by design (ADR-070 Decision 1), so two identical lines carry
        # the same text and the same state, and which one an entity adopts is
        # arbitrary and unobservable. A line that diverges from its twin also
        # diverges in the digest (the ✅ date is deliberately inside it) and
        # stops matching, which is the discriminator the design does have.
        rels.sort(key=_rel_visit_order)

        try:
            snapshot = await descriptor.bridge.read_note(owner, vault_file_path)
        except FILE_IO_EXCEPTIONS as exc:
            # Full absolute detail in the log; user-facing stats stay
            # vault-relative (stats reach the HTMX fragment / JSON API verbatim).
            logger.warning("read_note failed for %s: %s", vault_file_path, exc)
            stats.errors.append(
                f"read_note failed for {display_path(vault_file_path, descriptor.root)}: "
                f"{strip_root_prefix(str(exc), descriptor.root)}"
            )
            return

        updates: list[TaskLineUpdate] = []
        injections: list[_PendingInjection] = []
        # Hash lookups must be INJECTIVE across this entry (see
        # ``_find_line_by_hash``): a line whose 🆔 one of these edges already
        # owns is off the table before the loop starts, and every line a lookup
        # takes is off it afterwards.
        owned_ids = {rel.get("vault_id") for rel in rels if rel.get("vault_id")}
        claimed_lines = {
            i
            for i, line in enumerate(snapshot.content.splitlines())
            if (owner_match := VAULT_ID_RE.search(line)) and owner_match.group(1) in owned_ids
        }

        for rel in rels:
            entity_uid = rel.get("entity_uid", "")
            vault_id = rel.get("vault_id")
            line_hash = rel.get("source_line_hash", "")

            if not vault_id:
                # No 🆔 in Neo4j yet — check if the vault file already has one
                # (possible if a previous sync wrote the file but the DB update failed).
                if not line_hash:
                    continue
                line_idx = _find_line_by_hash(snapshot.content, line_hash, claimed_lines)
                if line_idx is None:
                    # Entity was extracted from non-checkbox content (LLM bridge
                    # augmentation, DSL prose, or Markwhen blocks).  Those lines
                    # have no physical counterpart in the vault file and can't
                    # participate in the 🆔 round-trip — skip silently.
                    logger.debug(
                        "ID injection: skipping %s — no matching checkbox line in %s"
                        " (bridge/DSL entity, not a vault checkbox line)",
                        entity_uid,
                        vault_file_path,
                    )
                    continue
                claimed_lines.add(line_idx)
                found_line = snapshot.content.splitlines()[line_idx]
                existing_id_match = VAULT_ID_RE.search(found_line)
                if existing_id_match:
                    # Recovery: vault already has this ID; sync it to Neo4j without
                    # touching the file.  Prevents a new mint from permanently
                    # diverging Neo4j from the vault after a partial-write failure.
                    injections.append(
                        _PendingInjection(
                            entity_uid=entity_uid,
                            vault_id=existing_id_match.group(1),
                            update_index=None,
                        )
                    )
                else:
                    new_vault_id = _mint_vault_id()
                    updates.append(
                        TaskLineUpdate(
                            vault_id=new_vault_id,
                            inject_vault_id=True,
                            source_line_hash=line_hash,
                        )
                    )
                    injections.append(
                        _PendingInjection(
                            entity_uid=entity_uid,
                            vault_id=new_vault_id,
                            update_index=len(updates) - 1,
                        )
                    )
            else:
                # Has 🆔 — check if COMPLETED in SKUEL
                task_result = await self._tasks.get_task(entity_uid)
                if task_result.is_error or task_result.value is None:
                    continue
                task = task_result.value
                if task.status == EntityStatus.COMPLETED:
                    # The obsidian-tasks ✅ date is the completion, so it reads
                    # the stamp — not the mutable updated_at, which would rewrite
                    # the vault line every time a long-done task is edited. Only
                    # a completion that predates the stamp (and the one-shot
                    # backfill) has none; today is the honest floor for those.
                    done_date = (
                        task.completion_date.isoformat()
                        if task.completion_date
                        else date.today().isoformat()
                    )
                    updates.append(
                        TaskLineUpdate(
                            vault_id=vault_id,
                            mark_done=True,
                            done_date=done_date,
                        )
                    )
                    stats.tasks_marked_done += 1

        if not updates and not injections:
            return

        # Every pass goes through the write door, INCLUDING one with nothing to
        # write. A recovery needs no mutation — the file already carries its 🆔
        # — but it adopts an id read from the snapshot, and both transports run
        # the SHA-256 stale-read guard on an EMPTY batch without touching the
        # file. So the empty call is the validation: without it a concurrent
        # edit that removed the 🆔 between ``read_note`` and here would be
        # persisted as a phantom, the state this whole change closes.
        # (Gating the tail on ``updates`` had also made the recovery arm
        # unreachable in its own defining case — the healing pass has nothing
        # left to write — so the divergence it exists to heal was permanent.)
        write_result = await descriptor.bridge.write_task_updates(
            user_uid=owner,
            path=vault_file_path,
            updates=updates,
            expected_sha256=snapshot.sha256,
        )
        if not write_result.success:
            logger.error(
                "write_task_updates failed for %s: %s", vault_file_path, write_result.error
            )
            stats.errors.append(
                f"write_task_updates failed for {display_path(vault_file_path, descriptor.root)}: "
                f"{strip_root_prefix(str(write_result.error), descriptor.root)}"
            )
            # The snapshot every recovery 🆔 was read from is stale by
            # definition here — nothing from this pass is trustworthy.
            return

        # Persist injected 🆔s onto their EXTRACTED_FROM edges — each gated on
        # ITS OWN update landing, never on file-level success. An update that
        # matched no line is a no-op inside a successful write; persisting its
        # 🆔 would strand the task with an id its file never received, and no
        # later sync could find the line to write its completion back
        # (deferred-work § Phantom-🆔). Withholding is recoverable, never
        # permanent: the edge keeps no vault_id, so the next sync either
        # re-mints (the line still has no 🆔) or adopts the 🆔 the file already
        # carries (the recovery arm above) — which is exactly why that arm has
        # to run, and to be guarded, on a pass with nothing to write.
        for pending in injections:
            if pending.update_index is not None:
                if not write_result.was_applied(pending.update_index):
                    logger.warning(
                        "🆔 injection no-oped for %s in %s — %s not persisted",
                        pending.entity_uid,
                        vault_file_path,
                        pending.vault_id,
                    )
                    stats.warnings.append(
                        f"🆔 injection found no line for {pending.entity_uid} in "
                        f"{display_path(vault_file_path, descriptor.root)} — "
                        "not persisted, retried next sync"
                    )
                    continue
                stats.ids_injected += 1
            upd_result = await self._user_entry.update_extracted_vault_id(
                entry.uid, pending.entity_uid, pending.vault_id
            )
            if upd_result.is_error:
                stats.errors.append(
                    f"update_extracted_vault_id failed ({pending.entity_uid}): "
                    f"{upd_result.expect_error()}"
                )

        # Update vault_sync_hash on UserEntry metadata
        if write_result.new_sha256:
            new_meta = dict(entry.metadata or {})
            new_meta["vault_sync_hash"] = write_result.new_sha256
            update_req = UserEntryUpdateRequest(metadata=new_meta)
            update_result = await self._user_entry.update_entry(entry.uid, owner, update_req)
            if update_result.is_error:
                stats.errors.append(
                    f"vault_sync_hash update failed for {entry.uid}: {update_result.expect_error()}"
                )


# =========================================================================
# HELPERS
# =========================================================================


# Ingestion stages caused by the FILE'S OWN CONTENT (broken frontmatter,
# missing/empty type:, empty uid:, invalid enum value). Failures at these
# stages are classified as ignored-with-reason — the sync did its job; the
# file opted out or needs author attention. Every other stage (ingestion =
# DB write, edge_ingestion, relationships, moc_edge_pass, file_io,
# user_entry_pipeline, unknown ...) is a system fault and stays an error.
_CONTENT_FAULT_STAGES: frozenset[str] = frozenset(
    {"parsing", "type_detection", "validation", "preparation"}
)


def _merge_ingest_stats(
    stats: VaultSyncStats,
    ingest: IngestionStats | IncrementalStats | DryRunPreview | None,
    vault_root: Path,
) -> None:
    """Carry the ingestion outcome into the sync stats — counts AND problems.

    Historically only the node counts survived (``_count_ingested``), so
    every sync door reported "Sync complete" over failed files, dropped
    edges, and dropped lines (G10). Errors are dict-shaped
    (``IngestionError.to_dict`` / ad-hoc ``{"message": ...}``) — flatten to
    readable strings for the UI/API surface. Ingest errors/warnings carry
    ABSOLUTE host paths; ``vault_root`` relativizes them before they land in
    the user-facing stats (the fragment/JSON render these verbatim).

    Classification (2026-07-23 ruling): errors tagged with a content-fault
    stage become ``ignored`` per-file reasons; ``errors``/``files_failed``
    keep only system-caused failures. A sync whose only findings are ignored
    files reports clean.
    """
    if not isinstance(ingest, (IngestionStats, IncrementalStats)):
        return
    stats.entries_ingested = int(ingest.nodes_created or 0) + int(ingest.nodes_updated or 0)
    stats.files_walled = int(ingest.files_walled or 0)
    stats.files_unsupported = int(ingest.files_unsupported or 0)
    stats.warnings.extend(strip_root_prefix(warning, vault_root) for warning in ingest.warnings)
    for error in ingest.errors or []:
        if error.get("stage") in _CONTENT_FAULT_STAGES:
            stats.ignored.append(_format_ignored_file(error, vault_root))
        else:
            stats.errors.append(_format_ingest_error(error, vault_root))
    stats.files_ignored = len(stats.ignored)
    # The engine counts every per-file problem in ``failed``; content-caused
    # ones just moved to the ignored bucket, so only the remainder are
    # genuine failures.
    stats.files_failed = max(0, int(ingest.failed or 0) - stats.files_ignored)
    if isinstance(ingest, IncrementalStats):
        stats.edges_created = int(ingest.edges_created or 0)
        stats.edges_updated = int(ingest.edges_updated or 0)
        stats.entities_deleted = int(ingest.entities_deleted or 0)
        stats.edges_deleted = int(ingest.edges_deleted or 0)
        stats.moves_detected = int(ingest.moves_detected or 0)
        stats.moves = [strip_root_prefix(move, vault_root) for move in ingest.moves]


def _format_ingest_error(error: dict[str, Any], vault_root: Path) -> str:
    """One readable line per ingestion error dict — vault-relative paths only.

    The ``file`` field is an absolute host path (``operation`` fallbacks are
    plain words and pass through :func:`display_path` unchanged); the message
    may embed paths too, so both are sanitized against ``vault_root``.
    """
    file = error.get("file") or error.get("operation") or ""
    message = error.get("error") or error.get("message") or str(error)
    stage = error.get("stage")
    prefix = f"{display_path(str(file), vault_root)}: " if file else ""
    suffix = f" [{stage}]" if stage else ""
    return f"{prefix}{strip_root_prefix(str(message), vault_root)}{suffix}"


def _format_ignored_file(error: dict[str, Any], vault_root: Path) -> str:
    """One vault-relative ``path — reason`` line per ignored file.

    Two flavors the reason text keeps distinct: a file with no ``type:`` at
    all (likely a deliberate non-entity note — the detector's message says
    so), and a file that DECLARED a type but has a malformed field — that
    author opted in and probably wants to fix it, so the declared type is
    called out up front.
    """
    file = error.get("file") or ""
    message = strip_root_prefix(
        str(error.get("error") or error.get("message") or str(error)), vault_root
    )
    path = display_path(str(file), vault_root) if file else "(unknown file)"
    entity_type = error.get("entity_type")
    if entity_type:
        return f"{path} — declared 'type: {entity_type}' but not ingested: {message}"
    return f"{path} — {message}"
