"""The personal-vault sync rig — the production loop over a temp vault and the container.

Shared by ``test_vault_done_date_hash_roundtrip.py`` (the ✅ write-back /
Guard 2b arc) and ``test_vault_inbound_propagation.py`` (the R4 arc). Everything
on the loop is real: ``VaultReconciler`` → smart-mode ``ingest_directory``
(tracker-backed, so an edited file re-ingests) → ``UserEntryService`` →
``UserEntryProcessingService`` (every graph-read guard) →
``ActivityExtractorService`` → the real ``TasksCoreService`` → the outbound pass
through ``FilesystemVaultAdapter``. The only double is the user lookup: a
``User`` who has granted vault-write consent, so the first-run gate lets the
sync through — the gate is not under test.

Two traps the rig's users have met, so they are stated once here:

- **A byte-identical rewrite of a note is a tracker SKIP.** Smart mode
  fingerprints the file; a note written back to the exact bytes it held at
  its last ingest is not re-ingested (removing an injected 🆔 restores the
  pre-injection bytes). A scenario that "deletes a line" must change another
  byte, or the pre-pass never runs.
- **Files ingest newest-mtime first**, one at a time. A scenario that needs
  note A ingested before note B sets their mtimes (``Rig.order``) rather than
  relying on write order.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest_asyncio

from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.vault.filesystem_adapter import FilesystemVaultAdapter
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.neo_labels import NeoLabel
from core.models.task.task_request import TaskUpdateRequest
from core.models.type_hints import UserUID
from core.models.user.user import User, UserPreferences
from core.services.dsl.activity_extractor import ActivityExtractorService
from core.services.ingestion.config import build_sync_allowlist
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_processing_service import UserEntryProcessingService
from core.services.user_entry.user_entry_service import UserEntryService
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, VaultSyncStats
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.tasks.tasks_core_service import TasksCoreService

OWNER = UserUID("user_vault_done_hash")
NOTE = "periodic_notes/2026-08-23.md"
TITLE = "Water the plants"

# A daily periodic note: the deterministic ``ue:daily:…`` uid makes every
# re-sync upsert the same UserEntry, which is what puts the guards on the path.
FRONTMATTER = (
    "---\n"
    "type: user_entry\n"
    "pipeline: extract_activities\n"
    "metadata:\n"
    "  entry_kind: daily\n"
    "date: 2026-08-23\n"
    "---\n\n"
)


def daily_frontmatter(day: str) -> str:
    """The frontmatter of a daily note for ``day`` (``YYYY-MM-DD``)."""
    return FRONTMATTER.replace("date: 2026-08-23", f"date: {day}")


@dataclass(frozen=True)
class Stamp:
    """The R4 grace record as it stands on one Task node."""

    uid: str
    retired_vault_id: str | None
    retired_source_line: str | None
    retired_at: datetime | None


@dataclass
class Rig:
    driver: AsyncDriver
    vault: Path
    reconciler: VaultReconciler
    tasks: TasksCoreService

    @property
    def note(self) -> Path:
        return self.vault / NOTE

    def note_at(self, relative: str) -> Path:
        return self.vault / relative

    @staticmethod
    def order(*newest_first: Path) -> None:
        """Force the ingest order: the batch walks files newest-mtime first."""
        base = 1_800_000_000
        for offset, path in enumerate(newest_first):
            stamp = base - offset * 60
            os.utime(path, (stamp, stamp))

    async def sync(self, *, force: bool = False) -> VaultSyncStats:
        result = await self.reconciler.sync(VaultKind.PERSONAL, OWNER, force=force)
        assert result.is_ok, result
        stats = result.value
        assert not stats.errors, stats.errors
        assert not stats.first_run_notice, "consent gate engaged — owner fixture lost its consent"
        return stats

    async def extracted_edges(self) -> list[tuple[str, str | None]]:
        """``(task uid, vault_id)`` of every EXTRACTED_FROM edge into the owner's entries."""
        return [(uid, vault_id) for uid, vault_id, _entry, _line in await self.edges()]

    async def edges(self) -> list[tuple[str, str | None, str, str | None]]:
        """``(task uid, vault_id, entry uid, source_line)`` of every EXTRACTED_FROM edge."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Task)-[r:EXTRACTED_FROM]->(e:UserEntry {user_uid: $owner})
                RETURN t.uid AS uid, r.vault_id AS vault_id, e.uid AS entry,
                       r.source_line AS source_line
                ORDER BY t.uid, e.uid
                """,
                owner=OWNER,
            )
            return [
                (row["uid"], row["vault_id"], row["entry"], row["source_line"])
                async for row in result
            ]

    async def owned_tasks(self) -> list[tuple[str, str]]:
        """``(uid, status)`` of every Task the owner holds."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {uid: $owner})-[:OWNS]->(t:Task)
                RETURN t.uid AS uid, t.status AS status
                ORDER BY t.uid
                """,
                owner=OWNER,
            )
            return [(row["uid"], row["status"]) async for row in result]

    async def stamps(self) -> list[Stamp]:
        """The retirement stamps on every owned Task that carries one."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {uid: $owner})-[:OWNS]->(t:Task)
                WHERE t.retired_vault_id IS NOT NULL
                   OR t.retired_source_line IS NOT NULL
                   OR t.vault_line_retired_at IS NOT NULL
                RETURN t.uid AS uid, t.retired_vault_id AS vault_id,
                       t.retired_source_line AS line, t.vault_line_retired_at AS at
                ORDER BY t.uid
                """,
                owner=OWNER,
            )
            return [
                Stamp(
                    uid=row["uid"],
                    retired_vault_id=row["vault_id"],
                    retired_source_line=row["line"],
                    retired_at=row["at"].to_native() if row["at"] is not None else None,
                )
                async for row in result
            ]


@pytest_asyncio.fixture
async def rig(neo4j_driver, clean_neo4j, tasks_service, tmp_path: Path) -> Rig:
    """The production wiring of the personal-vault sync, over a temp vault."""
    vault = tmp_path / "vault"
    (vault / "periodic_notes").mkdir(parents=True)
    content_root = tmp_path / "content"  # distinct → the doorway-folder wall applies
    content_root.mkdir()

    executor = Neo4jQueryExecutor(neo4j_driver)
    sharing = UnifiedSharingService(
        backend=SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity),
    )
    user_entry_service = UserEntryService(
        backend=UserEntryBackend(neo4j_driver),  # type: ignore[arg-type]
        sharing_service=sharing,
    )

    consenting_owner = User(
        uid=OWNER, title=OWNER, preferences=UserPreferences(vault_write_consent=True)
    )
    user_service = Mock()
    user_service.get_user = AsyncMock(return_value=Result.ok(consenting_owner))

    processor = UserEntryProcessingService(
        entry_service=user_entry_service,
        activity_extractor=ActivityExtractorService(tasks_service=tasks_service),
        user_service=user_service,
    )
    ingestion = make_unified_ingestion_service(
        driver=neo4j_driver,
        default_user_uid=OWNER,
        ingestion_backend=IngestionBackend(executor=executor),
        user_entry_service=user_entry_service,
        user_service=user_service,
        user_entry_processor=processor,
    )
    allowlist = build_sync_allowlist(vault, content_root=content_root)
    personal = VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=vault,
        owner_uid=OWNER,
        allowlist=allowlist,
        bridge=FilesystemVaultAdapter(allowed_root=vault),
        supports_task_round_trip=True,
    )
    registry = VaultRegistry(content=None, personal=personal)
    ingestion.vault_registry = registry
    ingestion.sync_allowlist = allowlist

    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=user_entry_service,
        tasks_service=tasks_service,
        user_service=user_service,
    )
    return Rig(driver=neo4j_driver, vault=vault, reconciler=reconciler, tasks=tasks_service)


async def complete_in_skuel(rig: Rig, task_uid: str) -> None:
    """The status-control door: stamps ``completion_date`` and cascades."""
    done = await rig.tasks.update_task(
        task_uid, TaskUpdateRequest(status=EntityStatus.COMPLETED).to_intent()
    )
    assert done.is_ok, done


async def reopen_in_skuel(rig: Rig, task_uid: str) -> None:
    """The same status-control door, back out of ``completed`` (ADR-087).

    The guarded write returns the prior status, so the reopen is detected
    exactly — and consumed by the write that produced it. Nothing here
    subscribes to ``TaskReopened``: the vault surface is driven by the
    outbound pass's STATE predicate instead, which is why it survives this
    call returning and can be re-evaluated on any later sync.
    """
    reopened = await rig.tasks.update_task(
        task_uid, TaskUpdateRequest(status=EntityStatus.ACTIVE).to_intent()
    )
    assert reopened.is_ok, reopened


async def cancel_in_skuel(rig: Rig, task_uid: str) -> None:
    cancelled = await rig.tasks.update_task(
        task_uid, TaskUpdateRequest(status=EntityStatus.CANCELLED).to_intent()
    )
    assert cancelled.is_ok, cancelled
