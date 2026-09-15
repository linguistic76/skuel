"""R4 PR 1 — identity survives a line's disappearance for one sync.

The build plan (``docs/roadmap/r4-vault-inbound-propagation.md``) makes the
vault the place tasks are edited. Its foundation, this PR: a 🆔 line that
vanishes from a note no longer loses its task's identity at once. The retiring
write — the extraction pre-pass for a line gone from a surviving note, the
deletion statement for a deleted note — hard-deletes the edge as before and
STAMPS the task with everything the edge knew (``retired_vault_id``,
``retired_source_line``, ``vault_line_retired_at``). A 🆔 that reappears in any
note within one sync finds its task by the stamp and is re-linked; a 🆔 that is
live on another note is a move, and its edge is re-pointed in one statement;
and an end-of-sync sweep judges what is still stamped from before the sync
began — clearing terminal and still-tracked tasks' stamps, leaving an open
untracked task's in place until the cancel consequence ships (PR 3).

``EXTRACTED_FROM`` gains ``source_line`` — the line verbatim as SKUEL last saw
it, the base PR 2's three-way merge diffs the vault against. Here it is
written on create, seeded where absent, carried by re-point and revival, and
NEVER advanced: a base that advances before its consumer ships absorbs every
vault edit made in between as already seen.

Every case drives the real loop against the container (``_vault_rig.Rig``).
Two orders matter throughout: files ingest newest-mtime first, so A-first and
B-first are forced with ``Rig.order``; and a byte-identical rewrite is a
tracker skip, so a scenario that deletes a line changes another byte too.

Mutants each case must fail are named in the PR description; each was applied
by hand, run, seen to fail here, and restored.
"""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityStatus
from tests.integration._vault_rig import (
    FRONTMATTER,
    NOTE,
    Rig,
    complete_in_skuel,
    daily_frontmatter,
)

NOTE_B = "periodic_notes/2026-08-24.md"
FRONTMATTER_B = daily_frontmatter("2026-08-24")


async def _seeded_note(rig: Rig, body: str = "- [ ] Vacuum\n") -> tuple[str, str, str]:
    """Two syncs over note A holding ``body``: the task exists, its line carries
    a 🆔, and the injected note has been re-ingested (the tracker holds it).
    Returns ``(task_uid, vault_id, injected_line)``."""
    rig.note.write_text(FRONTMATTER + body, encoding="utf-8")
    await rig.sync()
    await rig.sync()  # the 🆔 edit re-ingests
    ((task_uid, _),) = await rig.owned_tasks()
    [(_, vault_id, _entry, _base)] = await rig.edges()
    assert vault_id and vault_id.startswith("sk_"), vault_id
    injected_line = next(
        ln for ln in rig.note.read_text(encoding="utf-8").splitlines() if vault_id in ln
    )
    return task_uid, vault_id, injected_line


def _entry_uid(rel_path: str) -> str:
    """The deterministic uid of a daily note (``ue:daily:{owner}:{date}``)."""
    return {NOTE: "2026-08-23", NOTE_B: "2026-08-24"}[rel_path]


@pytest.mark.asyncio
@pytest.mark.integration
class TestMovesKeepTheirTask:
    @pytest.mark.parametrize("first", ["A", "B"], ids=["A-first", "B-first"])
    async def test_a_line_cut_from_one_note_into_another_in_one_edit(
        self, rig: Rig, first: str
    ) -> None:
        """Cut from A, pasted into B, both edits in one sync. A-first: A's
        pre-pass retires and stamps, B revives by the stamp. B-first: B finds
        the live edge on A and re-points it, A then has nothing to retire. Either
        way: one task, its edge on B carrying the base A's edge held, no twin,
        no stamp left behind — and the outbound pass now aims at B."""
        task_uid, vault_id, line = await _seeded_note(rig)
        [(_, _, entry_a, base)] = await rig.edges()
        assert base == "- [ ] Vacuum", base

        rig.note.write_text(FRONTMATTER + "Moved it.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + line + "\n", encoding="utf-8")
        rig.order(*((rig.note, note_b) if first == "A" else (note_b, rig.note)))

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "the move minted a twin"
        )
        [(edge_uid, edge_id, entry, moved_base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry != entry_a and entry.endswith(_entry_uid(NOTE_B)), entry
        assert moved_base == base, "the base must travel with the identity"
        assert await rig.stamps() == []

        # The write-back follows the line: completing the task checks B's line.
        await complete_in_skuel(rig, task_uid)
        after = await rig.sync()
        assert after.tasks_marked_done == 1, after
        assert "- [x] Vacuum" in note_b.read_text(encoding="utf-8")
        assert "Vacuum" not in rig.note.read_text(encoding="utf-8")

    async def test_a_line_edited_during_a_b_first_move_keeps_the_old_base(self, rig: Rig) -> None:
        """The re-point carries the OLD edge's base, never the current line:
        an edit made during the move is the diff PR 2 must still see. The
        digest, by contrast, moves with the line (Guard 2b's refresh)."""
        task_uid, vault_id, line = await _seeded_note(rig)
        edited = line.replace("Vacuum", "Vacuum the hallway")

        rig.note.write_text(FRONTMATTER + "Moved it.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + edited + "\n", encoding="utf-8")
        rig.order(note_b, rig.note)

        await rig.sync()
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        [(_, edge_id, entry, base)] = await rig.edges()
        assert edge_id == vault_id and entry.endswith(_entry_uid(NOTE_B))
        assert base == "- [ ] Vacuum", f"the move-time edit became its own base: {base!r}"
        # PR 1 applies nothing: the task's title is what SKUEL had.
        got = await rig.tasks.get_task(task_uid)
        assert got.is_ok and got.value is not None and got.value.title == "Vacuum"

    async def test_cut_sync_paste_sync_is_the_same_task(self, rig: Rig) -> None:
        """The slow move across a sync boundary — the grace window itself. The
        first sync stamps (the task is open, so the sweep leaves it); the
        second finds the 🆔 in B, revives by the stamp, and clears it."""
        task_uid, vault_id, line = await _seeded_note(rig)

        rig.note.write_text(FRONTMATTER + "Cut it.\n", encoding="utf-8")
        cut = await rig.sync()
        assert not cut.warnings, cut.warnings
        assert await rig.edges() == []
        [stamp] = await rig.stamps()
        assert (stamp.uid, stamp.retired_vault_id, stamp.retired_source_line) == (
            task_uid,
            vault_id,
            "- [ ] Vacuum",
        )
        assert stamp.retired_at is not None

        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + line + "\n", encoding="utf-8")
        pasted = await rig.sync()
        assert not pasted.warnings, pasted.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "the slow move minted a twin"
        )
        [(edge_uid, edge_id, entry, base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert base == "- [ ] Vacuum", "the revived edge carries the stamp's base"
        assert await rig.stamps() == []

    async def test_delete_sync_restore_in_the_same_note_sync_is_the_same_task(
        self, rig: Rig
    ) -> None:
        """Same note or another is the same case: the restored 🆔 line finds
        its task by the stamp. The restore changes another byte too — a
        byte-identical rewrite would be a tracker skip."""
        task_uid, vault_id, line = await _seeded_note(rig)

        rig.note.write_text(FRONTMATTER + "Deleted for a moment.\n", encoding="utf-8")
        await rig.sync()
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        rig.note.write_text(FRONTMATTER + line + "\nRestored.\n", encoding="utf-8")
        restored = await rig.sync()
        assert not restored.warnings, restored.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE))
        assert await rig.stamps() == []


@pytest.mark.asyncio
@pytest.mark.integration
class TestTheSweep:
    async def test_a_deleted_done_line_is_stamped_then_swept(self, rig: Rig) -> None:
        """Tidying a done line out of a note: the sync that sees it gone
        stamps the task (and does NOT judge its own retirement — the grace);
        the next sync's sweep finds a terminal task and clears the stamp."""
        task_uid, vault_id, _line = await _seeded_note(rig)
        await complete_in_skuel(rig, task_uid)
        await rig.sync()  # [x] ✅ write-back
        await rig.sync()  # the write-back re-ingests

        rig.note.write_text(FRONTMATTER + "Tidied.\n", encoding="utf-8")
        tidied = await rig.sync()
        assert not tidied.warnings, tidied.warnings
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id
        # The base the stamp carries is the one the edge held — seeded at
        # creation and never advanced, SKUEL's own write-back included.
        assert stamp.retired_source_line == "- [ ] Vacuum"

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert await rig.stamps() == [], "a terminal task's stamp survives the grace"
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)]

    async def test_a_deleted_open_line_stays_open_and_stamped(self, rig: Rig) -> None:
        """Deletion evidence with no consequence yet: the stamp is left in
        place sync after sync, so PR 3's first sweep can apply the rule late
        rather than skip it."""
        task_uid, vault_id, _line = await _seeded_note(rig)

        rig.note.write_text(FRONTMATTER + "Gone.\n", encoding="utf-8")
        await rig.sync()
        again = await rig.sync()
        assert not again.warnings, again.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        [stamp] = await rig.stamps()
        assert (stamp.uid, stamp.retired_vault_id) == (task_uid, vault_id)

    async def test_a_deleted_note_stamps_its_tasks(self, rig: Rig) -> None:
        """Whole-note deletion is ``DETACH DELETE`` on the entry, which takes
        every edge with it: the tasks are stamped in that same statement.
        Then the sweep: the done one clears, the open one stays."""
        rig.note.write_text(FRONTMATTER + "- [ ] Vacuum\n- [ ] Read\n", encoding="utf-8")
        # A second note keeps the vault from looking wiped (the everything-
        # vanished refusal) once the first is deleted.
        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + "Still here.\n", encoding="utf-8")
        await rig.sync()
        await rig.sync()
        tasks = await rig.owned_tasks()
        assert len(tasks) == 2, tasks
        edges = await rig.edges()
        assert len(edges) == 2
        done_uid = next(uid for uid, _, _, base in edges if base == "- [ ] Read")
        open_uid = next(uid for uid, _, _, base in edges if base == "- [ ] Vacuum")
        ids = {uid: vault_id for uid, vault_id, _, _ in edges}
        await complete_in_skuel(rig, done_uid)
        await rig.sync()  # write-back into the note
        await rig.sync()  # re-ingest

        rig.note.unlink()
        deleted = await rig.sync()
        assert not deleted.warnings, deleted.warnings
        assert deleted.entities_deleted == 1, deleted
        assert await rig.edges() == []
        stamps = {s.uid: s for s in await rig.stamps()}
        assert set(stamps) == {done_uid, open_uid}, stamps
        assert stamps[done_uid].retired_vault_id == ids[done_uid]
        assert stamps[open_uid].retired_vault_id == ids[open_uid]
        assert stamps[open_uid].retired_source_line == "- [ ] Vacuum"

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert [s.uid for s in await rig.stamps()] == [open_uid]
        assert sorted(await rig.owned_tasks()) == sorted(
            [(done_uid, EntityStatus.COMPLETED.value), (open_uid, EntityStatus.DRAFT.value)]
        )

    async def test_a_task_retyped_in_a_second_note_is_tracked_twice(self, rig: Rig) -> None:
        """Guard 4 merges a 🆔-less line into the open twin — and, the twin
        having no edge to this entry, writes one, so the line is tracked and
        keyed by the outbound pass. Deleting the FIRST line then stamps the
        task, and the sweep clears the stamp because the task is still tracked
        from the second note: losing a line is not losing the task."""
        task_uid, vault_id, _line = await _seeded_note(rig)

        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + "- [ ] Vacuum\n", encoding="utf-8")
        retyped = await rig.sync()
        assert retyped.ids_injected == 1, retyped
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        edges = await rig.edges()
        assert [uid for uid, _, _, _ in edges] == [task_uid, task_uid], edges
        second_id = next(v for _, v, entry, _ in edges if entry.endswith(_entry_uid(NOTE_B)))
        assert second_id and second_id != vault_id
        assert second_id in rig.note_at(NOTE_B).read_text(encoding="utf-8")

        rig.note.write_text(FRONTMATTER + "Moved on.\n", encoding="utf-8")
        await rig.sync()
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id
        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert await rig.stamps() == []
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        assert [(uid, v) for uid, v, _, _ in await rig.edges()] == [(task_uid, second_id)]

    async def test_the_sweep_holds_over_a_note_it_could_not_read(self, rig: Rig) -> None:
        """A note that opted in and failed to ingest has not had its say. The
        done line moves into B, but B's frontmatter is broken: the sweep holds
        the stamp (with a warning) instead of clearing it as terminal — because
        once B is fixed, its line revives the task by that very stamp. Without
        the hold, Guard 4 (terminal twins ignored) would mint a duplicate
        completed task."""
        task_uid, vault_id, _line = await _seeded_note(rig)
        await complete_in_skuel(rig, task_uid)
        await rig.sync()
        await rig.sync()
        done_line = next(
            ln for ln in rig.note.read_text(encoding="utf-8").splitlines() if vault_id in ln
        )

        rig.note.write_text(FRONTMATTER + "Consolidated.\n", encoding="utf-8")
        broken_b = FRONTMATTER_B.replace("---\n\n", "  bad: [unclosed\n---\n\n", 1)
        rig.note_at(NOTE_B).write_text(broken_b + done_line + "\n", encoding="utf-8")
        stamped = await rig.sync()
        assert stamped.files_broken == 1, stamped
        # The retirement happened DURING this sync: nothing is pending yet
        # (the grace), so there is nothing to hold and no warning about it.
        assert stamped.retirements_held == 0, stamped
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        # Next sync: B is still broken (an ignored file carries no tracker
        # stamp, so it is re-attempted). The stamp is now past the grace and
        # the task is terminal — a clearing candidate — but the sweep holds.
        held = await rig.sync()
        assert held.files_broken == 1, held
        assert held.retirements_held == 1, held
        assert any("1 vault retirement(s) held" in w for w in held.warnings), held.warnings
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + done_line + "\n", encoding="utf-8")
        fixed = await rig.sync()
        assert not fixed.warnings, fixed.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "the restored line minted a twin — the stamp was cleared too early"
        )
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert await rig.stamps() == []


@pytest.mark.asyncio
@pytest.mark.integration
class TestTheBaseIsSeededNeverAdvanced:
    async def test_a_present_base_survives_a_vault_edit(self, rig: Rig) -> None:
        """The edge's ``source_line`` is what SKUEL last saw. A vault edit moves
        the digest (Guard 2b's refresh) but must leave the base alone: no
        reconciler consumes the diff yet, and advancing it would mark the edit
        as already seen — lost for good once PR 2 lands."""
        task_uid, vault_id, line = await _seeded_note(rig)
        [(_, _, _, base)] = await rig.edges()
        assert base == "- [ ] Vacuum"

        rig.note.write_text(
            FRONTMATTER + line.replace("Vacuum", "Vacuum upstairs") + "\n", encoding="utf-8"
        )
        edited = await rig.sync()
        assert not edited.warnings, edited.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        [(edge_uid, edge_id, _, base_after)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert base_after == "- [ ] Vacuum", f"the base advanced: {base_after!r}"

    async def test_an_edge_without_a_base_is_seeded_by_a_force_sync(self, rig: Rig) -> None:
        """Edges written before the base existed have none. The first sight of
        the line seeds it — a ``--force`` sync re-processes unchanged files, so
        one such sync after this PR seeds every base at once — and applies
        nothing."""
        task_uid, vault_id, line = await _seeded_note(rig)
        async with rig.driver.session() as session:
            await session.run(
                "MATCH (:Task {uid: $uid})-[r:EXTRACTED_FROM]->() REMOVE r.source_line",
                uid=task_uid,
            )
        [(_, _, _, none)] = await rig.edges()
        assert none is None

        quiet = await rig.sync()  # unchanged file: skipped, nothing seeded
        assert (quiet.entries_ingested, quiet.ids_injected) == (0, 0), quiet
        [(_, _, _, still_none)] = await rig.edges()
        assert still_none is None

        forced = await rig.sync(force=True)
        assert not forced.warnings, forced.warnings
        [(edge_uid, edge_id, _, seeded)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert seeded == line, "the seed is the line verbatim, 🆔 and all"
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
