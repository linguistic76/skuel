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
7. **The write-back reverses.** Reopening the task in SKUEL un-checks its line
   and strips the ✅ date, restoring the pre-completion bytes exactly — and the
   sync after that writes nothing at all (ADR-070 Resolved Design Question 2,
   amended 2026-08-24). The inbound half — a vault-side check or un-check
   reaching the task — is ``test_vault_inbound_propagation.py``'s.
8. **A deleted line retires its edge.** A 🆔 line deleted from a note that
   still exists is the one deletion file-level propagation cannot see. The
   extraction pre-pass retires every edge whose line is gone by BOTH keys —
   🆔 nowhere in the text, digest on no 🆔-less line — so the same text typed
   back later is a new task, not a match against a dead edge; the task itself
   stays in SKUEL — stamped, and (R4 rule 1) an OPEN one is cancelled by the
   next sync's sweep, a terminal one left as it is; the sweep's cases are
   ``test_vault_inbound_propagation.py``'s. Record:
   ``docs/roadmap/done/line-deletions-leave-extracted-from-edges.md``.
9. **A stripped token is re-minted, not re-extracted.** One key gone is not a
   deletion: a 🆔-less line still hashing to its edge is the same line minus
   its token. It is recognised by hash (re-extracting it would duplicate a
   completed ``[x] ✅`` line, the twin Guard 2b exists to prevent) and the
   outbound pass injects a fresh 🆔 and re-keys the edge to it.

The unit-level contracts — which tokens the digest normalises, and Guard 2b
at the extractor — are pinned DB-free in
``tests/unit/test_obsidian_tasks_adapter.py`` and
``tests/unit/test_dsl_integration.py``; this file is path-filtered. The rig
itself lives in ``tests/integration/_vault_rig.py``, shared with the R4 arc
(``test_vault_inbound_propagation.py``): a retired line now also STAMPS its
task for the one-sync grace, which is that file's subject — here the stamp
is only ever asserted absent or irrelevant.
"""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityStatus
from tests.integration._vault_rig import (
    FRONTMATTER,
    TITLE,
    Rig,
    cancel_in_skuel,
    complete_in_skuel,
    reopen_in_skuel,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestReopenUnchecksTheVaultLine:
    """A task reopened in SKUEL gets its vault line back, byte for byte."""

    async def test_complete_then_reopen_restores_the_line_and_the_next_sync_is_quiet(
        self, rig: Rig
    ) -> None:
        rig.note.write_text(FRONTMATTER + f"- [ ] {TITLE}\n", encoding="utf-8")

        # Sync 1: the line becomes a Task and receives its 🆔.
        first = await rig.sync()
        assert first.ids_injected == 1, first
        tasks = await rig.owned_tasks()
        assert len(tasks) == 1, tasks
        (task_uid, _status) = tasks[0]
        # The line as it stands with its 🆔 — the exact bytes the reopen must
        # restore. Captured AFTER injection so the 🆔 is part of the baseline.
        injected = rig.note.read_text(encoding="utf-8")
        assert "🆔 sk_" in injected

        # Sync 2: completed in SKUEL → the outbound pass checks it and stamps ✅.
        await complete_in_skuel(rig, task_uid)
        second = await rig.sync()
        assert second.tasks_marked_done == 1, second
        assert second.tasks_marked_undone == 0, second
        done_line = rig.note.read_text(encoding="utf-8").splitlines()[-1]
        assert done_line.startswith("- [x]") and "✅ " in done_line, done_line

        # Sync 3: reopened in SKUEL → the line goes back to exactly what it was.
        await reopen_in_skuel(rig, task_uid)
        third = await rig.sync()
        assert third.tasks_marked_undone == 1, third
        assert third.tasks_marked_done == 0, third
        assert rig.note.read_text(encoding="utf-8") == injected, (
            "the reopen must restore the pre-completion line byte-for-byte"
        )

        # Sync 4: nothing left to do. The gate is what makes this quiet — an
        # ungated un-check arm would queue one for this still-open task on
        # every sync forever, and issue a write RPC per file to apply nothing.
        fourth = await rig.sync()
        assert fourth.tasks_marked_undone == 0, fourth
        assert fourth.tasks_marked_done == 0, fourth
        assert not fourth.warnings, fourth
        assert rig.note.read_text(encoding="utf-8") == injected

        # And the loop did not fork the task along the way.
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.ACTIVE.value)]


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

        await complete_in_skuel(rig, task_uid)

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
        # task line — 🆔 injected by the first sync and all — is byte-identical
        # and must be recognised.
        written = rig.note.read_text(encoding="utf-8")
        assert "🆔 sk_" in written, written
        rig.note.write_text(written + "\nA note about the day.\n", encoding="utf-8")
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
        await complete_in_skuel(rig, task_uid)
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
        await complete_in_skuel(rig, task_uid)
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
        await complete_in_skuel(rig, task_uid)
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


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeletedLinesRetireTheirEdges:
    async def test_a_line_typed_back_after_its_deletion_synced_is_a_fresh_task(
        self, rig: Rig
    ) -> None:
        """A task is cancelled in SKUEL (terminal, so Guard 4 ignores it; no
        write-back, so its unchecked digest never moves). The user clears the
        line; a later sync sees the same text typed back as a new to-do. The
        cleared line's edge went with it, so nothing in the exact-match set
        claims the typed-back line: it is a new task, injected as one."""
        rig.note.write_text(FRONTMATTER + f"- [ ] {TITLE}\n", encoding="utf-8")
        await rig.sync()
        await rig.sync()  # the 🆔 edit re-ingests
        ((task_uid, _),) = await rig.owned_tasks()
        [(_, old_id)] = await rig.extracted_edges()
        assert old_id and old_id.startswith("sk_"), old_id
        await cancel_in_skuel(rig, task_uid)

        rig.note.write_text(FRONTMATTER + "Skipped it this week.\n", encoding="utf-8")
        cleared = await rig.sync()
        assert not cleared.warnings, cleared.warnings
        assert await rig.extracted_edges() == [], "the cleared line's edge was left dangling"
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.CANCELLED.value)]

        rig.note.write_text(FRONTMATTER + f"- [ ] {TITLE}\n", encoding="utf-8")
        typed_back = await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, f"the typed-back line was swallowed as the deleted one: {tasks}"
        assert sorted(status for _, status in tasks) == sorted(
            [EntityStatus.CANCELLED.value, EntityStatus.DRAFT.value]
        )
        assert typed_back.ids_injected == 1, typed_back
        [(fresh_uid, fresh_id)] = await rig.extracted_edges()
        assert fresh_uid != task_uid
        written = rig.note.read_text(encoding="utf-8")
        assert fresh_id and fresh_id != old_id and fresh_id in written, (fresh_id, written)

    async def test_a_stripped_token_is_re_minted_onto_the_same_line(self, rig: Rig) -> None:
        """One key gone is not a deletion. The user strips the 🆔 token from
        a written-back ``[x] … ✅`` line and leaves the text: the line still
        hashes to its edge, so it is recognised (one completed task, not two)
        and the outbound pass injects a fresh 🆔 and re-keys the edge to it,
        keeping the write-back aimed at an id the file carries."""
        rig.note.write_text(FRONTMATTER + f"- [ ] {TITLE}\n", encoding="utf-8")
        await rig.sync()
        ((task_uid, _),) = await rig.owned_tasks()
        await complete_in_skuel(rig, task_uid)
        await rig.sync()  # 🆔 re-ingest + [x] ✅ write-back
        await rig.sync()  # the write-back re-ingests
        [(_, old_id)] = await rig.extracted_edges()
        written = rig.note.read_text(encoding="utf-8")
        assert old_id and f"🆔 {old_id}" in written, (old_id, written)

        rig.note.write_text(written.replace(f" 🆔 {old_id}", ""), encoding="utf-8")
        stripped = await rig.sync()
        assert not stripped.warnings, stripped.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "the stripped line was re-extracted as a second completed task"
        )
        assert stripped.ids_injected == 1, stripped
        [(edge_uid, new_id)] = await rig.extracted_edges()
        assert edge_uid == task_uid
        assert new_id and new_id != old_id
        healed = rig.note.read_text(encoding="utf-8")
        assert f"🆔 {new_id}" in healed and old_id not in healed, healed
        assert healed.startswith(FRONTMATTER + f"- [x] {TITLE}"), healed

        quiet = await rig.sync()  # the re-mint re-ingests: recognised by 🆔, nothing to write
        assert (quiet.ids_injected, quiet.tasks_marked_done) == (0, 0), quiet
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)]

    @pytest.mark.parametrize("remaining_body", ["", "Cleared the week.\n"], ids=["empty", "prose"])
    async def test_clearing_every_task_line_leaves_the_tasks_and_no_edges(
        self, rig: Rig, remaining_body: str
    ) -> None:
        """A note emptied of every 🆔 line — down to its frontmatter, or with
        prose left. Clearing the lines is not a hard deletion — both tasks
        stay in the graph, untouched by the sync that sees them gone (the
        grace) — but their provenance goes with the lines: no extraction
        error for an empty body, nothing to inject, nothing to mark, nothing
        to warn about. Two syncs on, both being open, the sweep cancels them
        (R4 rule 1) — still without writing to the note."""
        rig.note.write_text(FRONTMATTER + "- [ ] Gym\n- [ ] Read\n", encoding="utf-8")
        await rig.sync()
        await rig.sync()  # the 🆔 edit re-ingests: the tracker now holds the injected note
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, tasks
        assert len(await rig.extracted_edges()) == 2

        rig.note.write_text(FRONTMATTER + remaining_body, encoding="utf-8")
        cleared = await rig.sync()
        assert not cleared.warnings, cleared.warnings
        assert cleared.tasks_cancelled_by_deletion == 0, "judged in the sync that retired them"
        assert await rig.owned_tasks() == tasks, (
            "a vault-side line deletion is not a hard deletion, and not judged yet"
        )
        assert await rig.extracted_edges() == [], "the cleared lines' edges were left behind"

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert (swept.ids_injected, swept.tasks_marked_done, swept.tasks_marked_undone) == (0, 0, 0)
        assert swept.tasks_cancelled_by_deletion == 2, swept
        assert await rig.owned_tasks() == [
            (uid, EntityStatus.CANCELLED.value) for uid, _ in tasks
        ], "both open tasks were past the grace"
        assert await rig.extracted_edges() == []
        assert rig.note.read_text(encoding="utf-8") == FRONTMATTER + remaining_body
