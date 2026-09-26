"""A vault note whose frozen copy is not filed keeps its identity (Submit & Share arc R9).

A vault note is a living draft from its first sync — the door mints its uid —
and ``status: submitted`` files a frozen copy after the note itself has synced.
When the copy is refused, the note has still persisted: the sync reports the
refusal as an error, and the batch door records the note's uid in a *pending*
tracker row (empty hash, mtime 0), so the next sync re-ingests the file on the
same uid. Stamping nothing would lose the minted uid, and every retry would
write another living node for the same file. The pending row keeps the file's
real hash, so a rename before the retry is still recognised as a move.

Drives the production loop over a temp vault (``_vault_rig``): the reconciler,
smart-mode ``ingest_directory``, the per-file user-entry door, the tracker.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.services.ingestion.ingestion_tracker import PENDING_MTIME
from core.services.vault.vault_descriptor import VaultKind
from tests.integration._vault_rig import OWNER, Rig

TEACHER = "user_vault_retry_teacher"
GROUP = "group_vault_retry"
NOTE = "knowledge/retry-probe.md"
RENAMED = "knowledge/retry-probe-renamed.md"


def _note(audience: str) -> str:
    return (
        "---\n"
        "type: user_entry\n"
        "pipeline: knowledge\n"
        "title: Retry probe\n"
        "status: submitted\n"
        f"audience: {audience}\n"
        "---\n"
        "A note submitted for feedback.\n"
    )


async def _seed_class(rig: Rig) -> None:
    async with rig.driver.session() as session:
        await session.run(
            """
            MERGE (t:User {uid: $teacher})
            MERGE (s:User {uid: $student})
            MERGE (g:Group {uid: $group}) SET g.is_active = true, g.name = 'Retry class'
            MERGE (t)-[:OWNS]->(g)
            MERGE (s)-[:MEMBER_OF]->(g)
            """,
            teacher=TEACHER,
            student=OWNER,
            group=GROUP,
        )


async def _state(rig: Rig, note: str = NOTE) -> dict[str, Any]:
    async with rig.driver.session() as session:
        record = await (
            await session.run(
                """
                OPTIONAL MATCH (:User {uid: $owner})-[:OWNS]->(living:Entity:UserEntry)
                WHERE living.metadata CONTAINS 'retry-probe'
                WITH collect(living.uid) AS living_uids
                OPTIONAL MATCH (copy:Entity:UserEntry)
                WHERE copy.submitted_from_uid IN living_uids
                WITH living_uids, collect(copy.uid) AS copy_uids
                OPTIONAL MATCH (row:IngestionMetadata)
                WHERE row.file_path ENDS WITH $note
                RETURN living_uids, copy_uids, row.entity_uid AS row_uid,
                       row.content_hash AS row_hash, row.file_mtime AS row_mtime
                """,
                owner=OWNER,
                note=note,
            )
        ).single()
    assert record is not None
    return dict(record)


@pytest.mark.asyncio
async def test_a_refused_copy_keeps_the_notes_uid_and_retries_on_it(rig: Rig) -> None:
    await _seed_class(rig)
    note = rig.note_at(NOTE)
    note.parent.mkdir(parents=True, exist_ok=True)

    # 1. Submitted to nobody: the note syncs, its copy is refused and reported.
    note.write_text(_note("private"), encoding="utf-8")
    first = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)
    assert first.is_ok, first
    assert any("nothing to submit to" in e for e in first.value.errors), first.value.errors
    state = await _state(rig)
    assert len(state["living_uids"]) == 1, "the note itself synced"
    living_uid = state["living_uids"][0]
    assert state["copy_uids"] == []
    # The minted uid is kept, pending: the next sync must re-ingest the file.
    assert state["row_uid"] == living_uid
    assert state["row_mtime"] == PENDING_MTIME
    assert state["row_hash"], "the real hash is kept for move detection"

    # 2. Renamed before the retry, still refused: the move keeps the uid.
    renamed = rig.note_at(RENAMED)
    note.rename(renamed)
    second = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)
    assert second.is_ok, second
    assert any("nothing to submit to" in e for e in second.value.errors), second.value.errors
    state = await _state(rig, RENAMED)
    assert state["living_uids"] == [living_uid], "the renamed note is the same note"
    assert state["row_uid"] == living_uid
    assert state["row_mtime"] == PENDING_MTIME

    # 3. Fixed: the retry lands on the SAME note and files one copy.
    renamed.write_text(_note(f"teacher:{GROUP}"), encoding="utf-8")
    third = await rig.sync()
    assert third.errors == []
    state = await _state(rig, RENAMED)
    assert state["living_uids"] == [living_uid], "a retry never mints a second living node"
    assert len(state["copy_uids"]) == 1
    assert state["row_uid"] == living_uid
    assert state["row_mtime"] != PENDING_MTIME, "a filed copy stamps the row normally"

    # 4. Idle: nothing new.
    await rig.sync()
    state = await _state(rig, RENAMED)
    assert state["living_uids"] == [living_uid]
    assert len(state["copy_uids"]) == 1
