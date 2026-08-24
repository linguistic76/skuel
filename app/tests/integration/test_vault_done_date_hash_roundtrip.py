"""SKUEL's own ``✅ date`` write-back must not re-create the task it just marked done.

The vault round-trip (ADR-070) is a loop: a ``- [ ]`` line in a periodic note
is extracted into a Task; SKUEL injects ``🆔 sk_…`` into the line; when the
task is completed in SKUEL, the outbound pass rewrites the line as ``- [x] …
🆔 sk_… ✅ YYYY-MM-DD``. Every one of those edits changes the file, and every
file change is re-ingested on the next sync. Re-ingestion is idempotent only
through the line-hash guard (Guard 2, ``EXTRACTED_FROM.source_line_hash``),
whose whole job is to recognise a line SKUEL has already extracted — so the
hash has to be stable across every edit SKUEL itself makes. It was stable
across ``[x]`` and 🆔. It was not stable across ``✅``: the done-date token
changed the digest, Guard 2 missed, and Guard 4 (the semantic twin guard)
could not catch it either because it deliberately ignores terminal twins —
the task had just been COMPLETED. Net effect on the primary personal-data
path: completing a task in SKUEL produced a second COMPLETED copy of it on
the following sync.

This file drives the REAL loop against the container and a real vault
directory — the reconciler, the smart-mode ingest door, the extraction
pipeline with both graph-read guards, the real Tasks service, and the
filesystem bridge — never a re-implementation of any guard:

1. **The repro.** Extract → complete in SKUEL → sync writes ``✅`` → sync
   again → exactly one task. (Two, both COMPLETED, before the fix.)
2. **The already-checked door still works.** A line ingested as ``- [x] …
   ✅ date`` (the #1123 create door) stores a hash the next re-ingest
   recognises.
3. **The stored-hash migration is load-bearing.** A hash written by the
   pre-fix normalisation — with the ``✅`` token inside the digest, exactly
   what every already-checked extraction on the live graph carries — is
   orphaned by the fix on its own: the next re-ingest of that file would
   duplicate the task. ``scripts/rehash_vault_line_hashes.py`` recomputes
   it; after the migration the same sync is a no-op.

The unit-level contract (which tokens the normalisation strips) is pinned
DB-free in ``tests/unit/test_obsidian_tasks_adapter.py``; this file is
path-filtered.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import rehash_vault_line_hashes as rehash  # type: ignore[import-not-found]

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

OWNER = UserUID("user_vault_done_hash")
NOTE = "periodic_notes/2026-08-23.md"
TITLE = "Water the plants"

# A daily periodic note: the deterministic ``ue:daily:…`` uid makes every
# re-sync upsert the same UserEntry, which is what puts Guard 2 on the path.
FRONTMATTER = (
    "---\n"
    "type: user_entry\n"
    "pipeline: extract_activities\n"
    "metadata:\n"
    "  entry_kind: daily\n"
    "date: 2026-08-23\n"
    "---\n\n"
)


@dataclass
class Rig:
    driver: Any
    vault: Path
    reconciler: VaultReconciler
    tasks: Any

    @property
    def note(self) -> Path:
        return self.vault / NOTE

    async def sync(self) -> VaultSyncStats:
        result = await self.reconciler.sync(VaultKind.PERSONAL, OWNER)
        assert result.is_ok, result
        stats = result.value
        assert not stats.errors, stats.errors
        assert not stats.first_run_notice, "consent gate engaged — owner fixture lost its consent"
        return stats

    async def owned_tasks(self) -> list[tuple[str, str]]:
        """``(uid, status)`` of every Task the owner holds — the vault has one line."""
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

    async def stored_hash(self, task_uid: str) -> str | None:
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Task {uid: $uid})-[r:EXTRACTED_FROM]->(:UserEntry)
                RETURN r.source_line_hash AS h
                """,
                uid=task_uid,
            )
            record = await result.single()
            return record["h"] if record else None

    async def overwrite_stored_hash(self, task_uid: str, line_hash: str) -> None:
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Task {uid: $uid})-[r:EXTRACTED_FROM]->(:UserEntry)
                SET r.source_line_hash = $h
                """,
                uid=task_uid,
                h=line_hash,
            )
            await result.consume()


@pytest_asyncio.fixture
async def rig(neo4j_driver, clean_neo4j, tasks_service, tmp_path: Path) -> Rig:
    """The production wiring of the personal-vault sync, over a temp vault.

    Everything on the loop is real: ``VaultReconciler`` → smart-mode
    ``ingest_directory`` (tracker-backed, so an edited file re-ingests) →
    ``UserEntryService`` → ``UserEntryProcessingService`` (both graph-read
    guards) → ``ActivityExtractorService`` → the real ``TasksCoreService`` →
    the outbound pass through ``FilesystemVaultAdapter``. The only double is
    the user lookup: a ``User`` who has granted vault-write consent, so the
    first-run gate lets the sync through — the gate is not under test.
    """
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


async def _complete_in_skuel(rig: Rig, task_uid: str) -> None:
    """The status-control door: stamps ``completion_date`` and cascades."""
    done = await rig.tasks.update_task(
        task_uid, TaskUpdateRequest(status=EntityStatus.COMPLETED).to_intent()
    )
    assert done.is_ok, done


@pytest.mark.asyncio
@pytest.mark.integration
class TestDoneDateWriteBackRoundTrip:
    async def test_completing_a_task_in_skuel_does_not_recreate_it_on_the_next_sync(
        self, rig: Rig
    ) -> None:
        """The repro. Three syncs, one task, the whole way."""
        rig.note.write_text(FRONTMATTER + f"- [ ] {TITLE}\n", encoding="utf-8")

        # Sync 1: the line becomes a Task and gets its 🆔 injected into the file.
        first = await rig.sync()
        assert first.ids_injected == 1, first
        tasks = await rig.owned_tasks()
        assert len(tasks) == 1, tasks
        (task_uid, status) = tasks[0]
        assert status != EntityStatus.COMPLETED.value
        assert "🆔 sk_" in rig.note.read_text(encoding="utf-8")

        await _complete_in_skuel(rig, task_uid)

        # Sync 2: the 🆔 edit re-ingests (hash stable across injection — the
        # existing guarantee), then the outbound pass writes [x] + ✅.
        second = await rig.sync()
        assert second.tasks_marked_done == 1, second
        line = rig.note.read_text(encoding="utf-8").splitlines()[-1]
        assert line.startswith("- [x]"), line
        assert "✅ " in line, line
        assert len(await rig.owned_tasks()) == 1

        # Sync 3: the ✅ edit re-ingests. The hash must still recognise the
        # line — nothing but SKUEL's own write-back changed it.
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert tasks == [(task_uid, EntityStatus.COMPLETED.value)], (
            f"the ✅ write-back re-created the task it marked done: {tasks}"
        )

    async def test_an_already_checked_line_is_recognised_on_re_ingest(self, rig: Rig) -> None:
        """The #1123 create door: ``- [x] … ✅ date`` ingests COMPLETED once, not twice."""
        rig.note.write_text(FRONTMATTER + f"- [x] {TITLE} ✅ 2026-08-20\n", encoding="utf-8")

        await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 1, tasks
        assert tasks[0][1] == EntityStatus.COMPLETED.value

        # A prose edit elsewhere in the note re-ingests the whole entry; the
        # task line is byte-identical and must be recognised.
        rig.note.write_text(
            FRONTMATTER + f"- [x] {TITLE} ✅ 2026-08-20\n\nA note about the day.\n",
            encoding="utf-8",
        )
        await rig.sync()
        assert await rig.owned_tasks() == tasks

    async def test_the_migration_reconnects_a_pre_fix_hash_before_the_next_sync(
        self, rig: Rig
    ) -> None:
        """A stored hash that has the ``✅`` inside its digest is what the live
        graph carries for every already-checked extraction. Left alone, the
        fixed normalisation no longer recognises it and the next re-ingest
        duplicates the task — the fix would trigger the bug it fixes. The
        migration recomputes it from the vault line; the sync after that is
        a no-op."""
        line = f"- [x] {TITLE} ✅ 2026-08-20"
        rig.note.write_text(FRONTMATTER + line + "\n", encoding="utf-8")
        await rig.sync()
        (task_uid, _) = (await rig.owned_tasks())[0]

        # The pre-fix digest of the very line the file holds (🆔 included now).
        injected_line = rig.note.read_text(encoding="utf-8").splitlines()[-1]
        legacy = rehash.legacy_normalize_vault_line_hash(injected_line)
        current = await rig.stored_hash(task_uid)
        assert current is not None and current != legacy, "the fix did not change this digest"
        await rig.overwrite_stored_hash(task_uid, legacy)

        # Census: exactly this row is classified as a rewrite, nothing written.
        plans = await rehash.census(rig.driver)
        mine = [p for p in plans if p.entity_uid == task_uid]
        assert [p.outcome for p in mine] == [rehash.Outcome.REWRITE], mine
        assert await rig.stored_hash(task_uid) == legacy

        assert await rehash.run_rehash(rig.driver, confirm=True) == 0
        assert await rig.stored_hash(task_uid) == current

        # The next re-ingest of the file recognises the line again.
        rig.note.write_text(FRONTMATTER + line + "\n\nLater.\n", encoding="utf-8")
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert tasks == [(task_uid, EntityStatus.COMPLETED.value)], tasks
