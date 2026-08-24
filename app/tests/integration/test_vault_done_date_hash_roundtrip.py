"""SKUEL's own ``✅ date`` write-back must not re-create the task it just marked done.

The vault round-trip (ADR-070) is a loop: a ``- [ ]`` line in a periodic note
is extracted into a Task; SKUEL injects ``🆔 sk_…`` into the line; when the
task is completed in SKUEL, the outbound pass rewrites the line as ``- [x] …
🆔 sk_… ✅ YYYY-MM-DD``. Every one of those edits changes the file, and every
file change is re-ingested on the next sync (the ingest door passes
``force=True``, so the completed-run guard never blocks). Re-ingestion is
idempotent only through the extraction guards. Guard 2 (``source_line_hash``)
is stable across ``[x]`` and 🆔 but not across ``✅`` — and it must not be:
the ✅ date is the only thing that tells two same-title completed occurrences
in one note apart. Guard 4 (the semantic twin guard) ignores terminal twins
by design, so a just-completed task had no guard at all. Net effect on the
primary personal-data path: completing a task in SKUEL produced a second
COMPLETED copy of it on the following sync.

The fix reads the 🆔 as identity at ingest (Guard 2b): a line whose 🆔
already carries an ``EXTRACTED_FROM`` edge to the entry is already extracted,
whatever its hash says — and, because that edge is the line's own, its hash
is refreshed to the current digest (the stale one retired from the exact-match
set before any line is checked against it). The digest itself is unchanged,
so no stored hash moved and the agent protocol did not change.

This file drives the REAL loop against the container and a real vault
directory — the reconciler, the smart-mode ingest door, the extraction
pipeline with all three graph-read guards, the real Tasks service, and the
filesystem bridge — never a re-implementation of any guard:

1. **The repro.** Extract → complete in SKUEL → sync writes ``✅`` → sync
   again → exactly one task. (Two, both COMPLETED, before the fix.)
2. **The already-checked door still works.** A line ingested as ``- [x] …
   ✅ date`` (the #1123 create door) is recognised on the next re-ingest.
3. **The ✅ date stays a discriminator.** A second same-title completed
   occurrence added a sync later becomes its own task — the shape a
   hash-blinding fix silently swallowed (Codex P1 on #1143, round 2).
4. **The edge's change signal moves with the line.** After the write-back, a
   fresh ``- [ ] Gym`` the user adds next week is a new task — it would have
   hashed into the edge's original unchecked digest (round 3).
5. **…even in the same ingest as the write-back.** The sibling appended before
   the write-back is re-ingested, placed above it, is a new task — the stale
   digest is retired before any line is checked against it (round 4).
6. **…and after the done line is gone.** The user clears the completed line
   from the note and writes a fresh ``- [ ] Gym``: nothing is left in the file
   to retire the old digest in memory, so it has to have been *persisted* on
   the edge by the earlier re-ingest (the refresh is what this pins).

The unit-level contracts — which tokens the digest normalises, and Guard 2b
at the extractor — are pinned DB-free in
``tests/unit/test_obsidian_tasks_adapter.py`` and
``tests/unit/test_dsl_integration.py``; this file is path-filtered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
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


@pytest_asyncio.fixture
async def rig(neo4j_driver, clean_neo4j, tasks_service, tmp_path: Path) -> Rig:
    """The production wiring of the personal-vault sync, over a temp vault.

    Everything on the loop is real: ``VaultReconciler`` → smart-mode
    ``ingest_directory`` (tracker-backed, so an edited file re-ingests) →
    ``UserEntryService`` → ``UserEntryProcessingService`` (all three graph-read
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

        # Sync 3: the ✅ edit re-ingests. The hash has moved (by design); the
        # 🆔 on the entry's own edge is what says the line is already SKUEL's.
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

    async def test_a_new_unchecked_occurrence_after_the_write_back_is_still_extracted(
        self, rig: Rig
    ) -> None:
        """After SKUEL writes ``[x]`` + ``✅`` into ``- [ ] Gym``, the edge's
        change signal must move with the line. If it kept the ORIGINAL unchecked
        digest, a fresh ``- [ ] Gym`` the user adds next week would hash into it
        and Guard 2 would drop the new task silently (Codex P1, round 3)."""
        rig.note.write_text(FRONTMATTER + "- [ ] Gym\n", encoding="utf-8")
        await rig.sync()
        ((task_uid, _),) = await rig.owned_tasks()
        await _complete_in_skuel(rig, task_uid)
        await rig.sync()  # 🆔 re-ingest + [x] ✅ write-back
        await rig.sync()  # the write-back re-ingests; Guard 2b recognises the line
        assert len(await rig.owned_tasks()) == 1
        written = rig.note.read_text(encoding="utf-8")
        assert "- [x] Gym" in written and "✅ " in written, written

        rig.note.write_text(written + "- [ ] Gym\n", encoding="utf-8")
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, f"the new unchecked occurrence was swallowed: {tasks}"
        assert sorted(status for _, status in tasks) == sorted(
            [EntityStatus.COMPLETED.value, EntityStatus.DRAFT.value]
        )

    async def test_a_sibling_added_before_the_write_back_re_ingests_is_still_extracted(
        self, rig: Rig
    ) -> None:
        """The same-ingest ordering (Codex P1, round 4): the user appends the next
        ``- [ ] Gym`` after SKUEL wrote ``[x]`` + ``✅`` into the old one but
        before that write-back has been re-ingested. Both lines arrive in ONE
        ingest whose exact-match set still holds the old unchecked digest; the
        stale digest must be retired before any line is checked against it, or
        the sibling is dropped and smart-mode checkpoints the file."""
        rig.note.write_text(FRONTMATTER + "- [ ] Gym\n", encoding="utf-8")
        await rig.sync()
        ((task_uid, _),) = await rig.owned_tasks()
        await _complete_in_skuel(rig, task_uid)
        await rig.sync()  # 🆔 re-ingest + [x] ✅ write-back — NOT re-ingested yet
        written = rig.note.read_text(encoding="utf-8")
        assert "- [x] Gym" in written, written

        # The sibling goes ABOVE the written-back line: retirement must not
        # depend on the completed line being seen first.
        rig.note.write_text(
            written.replace("- [x] Gym", "- [ ] Gym\n- [x] Gym", 1), encoding="utf-8"
        )
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, f"the sibling in the same ingest was swallowed: {tasks}"
        assert sorted(status for _, status in tasks) == sorted(
            [EntityStatus.COMPLETED.value, EntityStatus.DRAFT.value]
        )

    async def test_a_fresh_occurrence_after_the_done_line_is_removed_is_still_extracted(
        self, rig: Rig
    ) -> None:
        """The persisted refresh. Once the write-back has been re-ingested, the
        edge must hold the written-back line's digest, not the original one:
        when the user later clears the done line and writes a fresh ``- [ ]
        Gym``, no 🆔 line remains to retire the stale digest in memory."""
        rig.note.write_text(FRONTMATTER + "- [ ] Gym\n", encoding="utf-8")
        await rig.sync()
        ((task_uid, _),) = await rig.owned_tasks()
        await _complete_in_skuel(rig, task_uid)
        await rig.sync()  # 🆔 re-ingest + [x] ✅ write-back
        await rig.sync()  # the write-back re-ingests: the edge's hash is refreshed
        assert len(await rig.owned_tasks()) == 1

        rig.note.write_text(FRONTMATTER + "- [ ] Gym\n", encoding="utf-8")  # done line cleared
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, f"the fresh occurrence was read as the cleared line: {tasks}"
        assert sorted(status for _, status in tasks) == sorted(
            [EntityStatus.COMPLETED.value, EntityStatus.DRAFT.value]
        )

    async def test_a_second_completed_occurrence_added_later_is_still_extracted(
        self, rig: Rig
    ) -> None:
        """Two independently authored completed occurrences of the same task in
        one note — a weekly note logging ``Gym`` on Monday and again on Wednesday
        — differ only by their ✅ dates (and, once injected, their 🆔s). The
        second one, added after the first has synced, must still become its
        own task: the ✅ date is the user's discriminator, and recognising
        SKUEL's own write-back must not cost it (Codex P1 on #1143)."""
        rig.note.write_text(FRONTMATTER + "- [x] Gym ✅ 2026-08-17\n", encoding="utf-8")
        await rig.sync()
        assert len(await rig.owned_tasks()) == 1

        rig.note.write_text(
            rig.note.read_text(encoding="utf-8") + "- [x] Gym ✅ 2026-08-19\n", encoding="utf-8"
        )
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, f"the second completed occurrence was swallowed: {tasks}"
        assert {status for _, status in tasks} == {EntityStatus.COMPLETED.value}
