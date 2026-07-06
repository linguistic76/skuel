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

**First-run notice** (ADR-070 Decision 6):
Before performing any outbound vault write, checks
``user.preferences.vault_write_consent``.  Returns
``Result.ok(VaultSyncStats(first_run_notice=True))`` on the first call so
the route can render the consent modal without treating it as an error.
After the user grants consent, ``POST /api/vault/sync/consent`` sets the
preference flag and subsequent sync calls proceed normally.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import re
import secrets
import string
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
from core.services.ingestion.types import DryRunPreview, IncrementalStats, IngestionStats
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry
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


def _mint_vault_id() -> str:
    """Mint a 6-character base-36 vault ID with ``sk_`` prefix (ADR-070 Decision 1)."""
    return "sk_" + "".join(secrets.choice(_BASE36) for _ in range(6))


def _find_line_by_hash(content: str, target_hash: str) -> int | None:
    """Return 0-based index of the checkbox line whose normalized hash matches."""
    for i, line in enumerate(content.splitlines()):
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
    ) -> None:
        self._registry = registry
        self._ingestion = unified_ingestion
        self._user_entry = user_entry_service
        self._tasks = tasks_service
        self._user_service = user_service

    # =========================================================================
    # PUBLIC API
    # =========================================================================

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

        1. Ingest the vault directory (smart mode — only changed files, unless
           ``force``), attributed to the descriptor's owner, walled by the
           descriptor's allowlist.
        2. Check vault-write consent on the owner (ADR-070 Decision 6 first-run
           gate).
        3. If the vault supports the task round-trip, for each ingested
           UserEntry with the EXTRACT_ACTIVITIES pipeline:
           a. inject 🆔 IDs into ID-less task lines;
           b. write ``[x]`` + ``✅ date`` for SKUEL-completed tasks.
        """
        descriptor_result = self._registry.resolve(kind, user_uid)
        if descriptor_result.is_error:
            return Result.fail(descriptor_result)
        descriptor = descriptor_result.value
        owner = descriptor.owner_uid

        # Surface-independence invariant: by-kind and by-path resolution must agree
        # on this root, otherwise the ingestion mechanism (which resolves owner +
        # wall by path) would attribute a different owner than this by-kind sync.
        # Kind disagreement is the combined-root config (VAULT_ROOT == INGESTION_PATH),
        # where the single vault resolves to PERSONAL by-path: there is no distinct
        # content vault, so a CONTENT sync would stamp content_owner_uid onto the
        # user's own files. Refuse it — the combined vault syncs as PERSONAL.
        # Owner disagreement is a nested-roots misconfiguration (e.g. a member
        # vault placed inside the primary personal root): by-path governance
        # belongs to the enclosing vault's owner, so syncing it as anyone else
        # would split attribution. Refuse that too.
        by_path = self._registry.resolve_by_path(descriptor.root, owner)
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
        if by_path.is_ok and by_path.value.owner_uid != owner:
            return Result.fail(
                Errors.validation(
                    "vault sync refused: this vault root is governed by another "
                    "vault's owner by path (nested vault roots misconfiguration) — "
                    "move the vault outside the enclosing vault root.",
                    field="kind",
                )
            )

        stats = VaultSyncStats()

        # Step 1: ingest (inbound — smart mode skips unchanged files). The
        # descriptor's own fail-closed allowlist scopes which folders are read;
        # entries are attributed to the descriptor's owner. Passing ``user_uid``/
        # ``allowlist`` explicitly is belt-and-suspenders: the ingestion mechanism
        # resolves the same owner and wall by path (resolve_by_path), and the guard
        # above enforces that by-kind and by-path agree on this root.
        # ``validate_targets=True`` (G10): dangling relationship targets no-op
        # inside the relationship Cypher, so real syncs must run the pre-check
        # and surface every phantom UID as a warning — not a silent row drop,
        # not a hard failure.
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
        _merge_ingest_stats(stats, ingest_result.value)

        # Steps 2-3: consent gate + outbound. Only vaults that support the task
        # round-trip have anything to write back, so the consent gate engages
        # there. Curriculum vaults are inbound-only today (structural no-op) — the
        # uniform gate is ready to engage the moment curriculum writeback is built
        # (designed-for, deferred), without blocking inbound ingest meanwhile.
        if not descriptor.supports_task_round_trip:
            return Result.ok(stats)

        # First-run consent guard (ADR-070 Decision 6) — on the vault owner.
        user_result = await self._user_service.get_user(owner)
        if user_result.is_error:
            return Result.fail(user_result)
        user = user_result.value
        if user is None:
            return Result.fail(Errors.not_found(resource="User", identifier=str(owner)))
        if not user.preferences.vault_write_consent:
            return Result.ok(VaultSyncStats(first_run_notice=True))

        await self._run_outbound(descriptor, stats)
        return Result.ok(stats)

    async def grant_consent(self, user_uid: UserUID) -> Result[None]:
        """Record vault-write consent for the user (ADR-070 Decision 6 first-run gate)."""
        result = await self._user_service.update_preferences(
            user_uid, {"vault_write_consent": True}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(None)

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
        """Process one UserEntry: inject IDs for new tasks, mark done for completed."""
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

        try:
            snapshot = await descriptor.bridge.read_note(owner, vault_file_path)
        except FILE_IO_EXCEPTIONS as exc:
            stats.errors.append(f"read_note failed for {vault_file_path}: {exc}")
            return

        updates: list[TaskLineUpdate] = []
        inject_pairs: list[tuple[str, str]] = []  # (entity_uid, new_vault_id)

        for rel in rels:
            entity_uid = rel.get("entity_uid", "")
            vault_id = rel.get("vault_id")
            line_hash = rel.get("source_line_hash", "")

            if not vault_id:
                # No 🆔 in Neo4j yet — check if the vault file already has one
                # (possible if a previous sync wrote the file but the DB update failed).
                if not line_hash:
                    continue
                line_idx = _find_line_by_hash(snapshot.content, line_hash)
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
                found_line = snapshot.content.splitlines()[line_idx]
                existing_id_match = VAULT_ID_RE.search(found_line)
                if existing_id_match:
                    # Recovery: vault already has this ID; sync it to Neo4j without
                    # touching the file.  Prevents a new mint from permanently
                    # diverging Neo4j from the vault after a partial-write failure.
                    inject_pairs.append((entity_uid, existing_id_match.group(1)))
                else:
                    new_vault_id = _mint_vault_id()
                    updates.append(
                        TaskLineUpdate(
                            vault_id=new_vault_id,
                            inject_vault_id=True,
                            source_line_hash=line_hash,
                        )
                    )
                    inject_pairs.append((entity_uid, new_vault_id))
                    stats.ids_injected += 1
            else:
                # Has 🆔 — check if COMPLETED in SKUEL
                task_result = await self._tasks.get_task(entity_uid)
                if task_result.is_error or task_result.value is None:
                    continue
                task = task_result.value
                if task.status == EntityStatus.COMPLETED:
                    done_date = (
                        task.updated_at.strftime("%Y-%m-%d")
                        if task.updated_at
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

        if not updates:
            return

        write_result = await descriptor.bridge.write_task_updates(
            user_uid=owner,
            path=vault_file_path,
            updates=updates,
            expected_sha256=snapshot.sha256,
        )
        if not write_result.success:
            stats.errors.append(
                f"write_task_updates failed for {vault_file_path}: {write_result.error}"
            )
            return

        # Update EXTRACTED_FROM edges with injected vault_ids
        for entity_uid, new_vault_id in inject_pairs:
            upd_result = await self._user_entry.update_extracted_vault_id(
                entry.uid, entity_uid, new_vault_id
            )
            if upd_result.is_error:
                stats.errors.append(
                    f"update_extracted_vault_id failed ({entity_uid}): {upd_result.expect_error()}"
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


def _merge_ingest_stats(
    stats: VaultSyncStats,
    ingest: IngestionStats | IncrementalStats | DryRunPreview | None,
) -> None:
    """Carry the ingestion outcome into the sync stats — counts AND problems.

    Historically only the node counts survived (``_count_ingested``), so
    every sync door reported "Sync complete" over failed files, dropped
    edges, and dropped lines (G10). Errors are dict-shaped
    (``IngestionError.to_dict`` / ad-hoc ``{"message": ...}``) — flatten to
    readable strings for the UI/API surface.
    """
    if not isinstance(ingest, (IngestionStats, IncrementalStats)):
        return
    stats.entries_ingested = int(ingest.nodes_created or 0) + int(ingest.nodes_updated or 0)
    stats.files_failed = int(ingest.failed or 0)
    stats.files_walled = int(ingest.files_walled or 0)
    stats.files_unsupported = int(ingest.files_unsupported or 0)
    stats.warnings.extend(ingest.warnings)
    for error in ingest.errors or []:
        stats.errors.append(_format_ingest_error(error))
    if isinstance(ingest, IncrementalStats):
        stats.entities_deleted = int(ingest.entities_deleted or 0)
        stats.edges_deleted = int(ingest.edges_deleted or 0)


def _format_ingest_error(error: dict[str, Any]) -> str:
    """One readable line per ingestion error dict."""
    file = error.get("file") or error.get("operation") or ""
    message = error.get("error") or error.get("message") or str(error)
    stage = error.get("stage")
    prefix = f"{file}: " if file else ""
    suffix = f" [{stage}]" if stage else ""
    return f"{prefix}{message}{suffix}"
