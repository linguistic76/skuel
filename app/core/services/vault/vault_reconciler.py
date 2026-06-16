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
``user.preferences.vault_write_consent``.  Returns ``Result.fail`` with
``reason="first_run_notice"`` on the first call; the route renders the
first-run consent modal.  After the user grants consent, a separate
``POST /api/vault/sync/consent`` endpoint sets the preference flag and
subsequent sync calls proceed normally.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

import hashlib
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
from core.ports.vault_bridge_protocol import TaskLineUpdate, VaultSyncStats
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.vault_bridge_protocol import VaultBridgePort
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
    from core.services.tasks_service import TasksService
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

logger = get_logger("skuel.services.vault.reconciler")

_BASE36 = string.ascii_lowercase + string.digits
_UNCHECKED_RE = re.compile(r"^[-*]\s*\[\s*\]")
_CHECKED_RE = re.compile(r"^[-*]\s*\[[xX]\]")
_VAULT_ID_RE = re.compile(r"🆔️?\s*([\w-]{1,20})")


def _mint_vault_id() -> str:
    """Mint a 6-character base-36 vault ID with ``sk_`` prefix (ADR-070 Decision 1)."""
    return "sk_" + "".join(secrets.choice(_BASE36) for _ in range(6))


def _normalized_hash(line: str) -> str:
    """Replicates the obsidian-tasks adapter hash for VaultWriter line lookup."""
    line = re.sub(r"^[-*]\s*\[[xX]\]\s*", "- [ ] ", line)
    line = re.sub(r"^[-*]\s*\[\s*\]\s*", "- [ ] ", line)
    line = _VAULT_ID_RE.sub("", line)
    return hashlib.sha256(" ".join(line.split()).encode("utf-8")).hexdigest()


def _find_line_by_hash(content: str, target_hash: str) -> int | None:
    """Return 0-based index of the checkbox line whose normalized hash matches."""
    for i, line in enumerate(content.splitlines()):
        if _UNCHECKED_RE.match(line) or _CHECKED_RE.match(line):
            if _normalized_hash(line) == target_hash:
                return i
    return None


class VaultReconciler:
    """Bidirectional vault sync orchestrator (ADR-070).

    Wires together the ingestion pipeline (inbound) and VaultBridgePort
    adapter (outbound) to implement the full sync loop.
    """

    def __init__(
        self,
        vault_bridge: VaultBridgePort,
        unified_ingestion: UnifiedIngestionService,
        user_entry_service: UserEntryService,
        tasks_service: TasksService,
        user_service: UserService,
    ) -> None:
        self._bridge = vault_bridge
        self._ingestion = unified_ingestion
        self._user_entry = user_entry_service
        self._tasks = tasks_service
        self._user_service = user_service

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def sync(self, user_uid: str, vault_path: str) -> Result[VaultSyncStats]:
        """Run a full bidirectional vault sync for the given user.

        1. Ingest the vault directory (incremental — only changed files).
        2. Check vault-write consent (ADR-070 Decision 6 first-run gate).
        3. For each vault-ingested UserEntry with EXTRACT_ACTIVITIES pipeline:
           a. Find extracted tasks without a 🆔 vault_id → inject IDs.
           b. Find extracted tasks with vault_id that are COMPLETED in SKUEL
              → write [x] + ✅ date back to vault file.
        """
        stats = VaultSyncStats()

        uid = UserUID(user_uid)

        # Step 1: ingest (inbound — smart mode skips unchanged files)
        ingest_result = await self._ingestion.ingest_directory(
            Path(vault_path),
            ingestion_mode="smart",
            user_uid=uid,
        )
        if ingest_result.is_error:
            return Result.fail(ingest_result)
        stats.entries_ingested = _count_ingested(ingest_result.value)

        # Step 2: first-run consent guard (ADR-070 Decision 6)
        user_result = await self._user_service.get_user(uid)
        if user_result.is_error:
            return Result.fail(user_result)
        user = user_result.value
        if user is None:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        if not user.preferences.vault_write_consent:
            return Result.fail(
                Errors.forbidden(
                    action="vault_write",
                    reason="first_run_notice",
                    required_role="vault_write_consent",
                )
            )

        # Step 3: outbound — ID injection + status round-trip
        await self._run_outbound(user_uid, stats)
        return Result.ok(stats)

    async def grant_consent(self, user_uid: str) -> Result[None]:
        """Record vault-write consent for the user (ADR-070 Decision 6 first-run gate)."""
        result = await self._user_service.update_preferences(
            UserUID(user_uid), {"vault_write_consent": True}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(None)

    # =========================================================================
    # OUTBOUND
    # =========================================================================

    async def _run_outbound(self, user_uid: str, stats: VaultSyncStats) -> None:
        """Inject IDs and write done-status for all vault-ingested UserEntries."""
        entries_result = await self._user_entry.list_for_user(
            user_uid=UserUID(user_uid),
            pipeline=Pipeline.EXTRACT_ACTIVITIES,
            limit=500,
        )
        if entries_result.is_error:
            stats.errors.append(f"list_for_user failed: {entries_result.expect_error()}")
            return

        for entry in entries_result.value or []:
            vault_file_path = (entry.metadata or {}).get("vault_file_path")
            if not vault_file_path:
                continue
            await self._process_entry_outbound(user_uid, entry, vault_file_path, stats)

    async def _process_entry_outbound(
        self,
        user_uid: str,
        entry: Any,
        vault_file_path: str,
        stats: VaultSyncStats,
    ) -> None:
        """Process one UserEntry: inject IDs for new tasks, mark done for completed."""
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
            snapshot = await self._bridge.read_note(user_uid, vault_file_path)
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
                # No 🆔 yet — inject one
                if not line_hash:
                    continue
                line_idx = _find_line_by_hash(snapshot.content, line_hash)
                if line_idx is None:
                    stats.errors.append(
                        f"ID injection: line not found in {vault_file_path} for entity {entity_uid}"
                    )
                    continue
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

        write_result = await self._bridge.write_task_updates(
            user_uid=user_uid,
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
            update_result = await self._user_entry.update_entry(
                entry.uid, UserUID(user_uid), update_req
            )
            if update_result.is_error:
                stats.errors.append(
                    f"vault_sync_hash update failed for {entry.uid}: {update_result.expect_error()}"
                )


# =========================================================================
# HELPERS
# =========================================================================


def _count_ingested(stats: Any) -> int:
    """Extract a meaningful node count from IngestionStats | IncrementalStats."""
    if hasattr(stats, "nodes_created"):
        return int(stats.nodes_created or 0) + int(stats.nodes_updated or 0)
    return 0
