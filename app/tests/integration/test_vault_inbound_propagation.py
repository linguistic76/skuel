"""R4 — vault inbound propagation: identity survives one sync (PR 1), lines reconcile (PR 2), deletion cancels (PR 3).

The build plan (``docs/roadmap/done/r4-vault-inbound-propagation.md``) makes
the vault the place tasks are edited. Its foundation, PR 1: a 🆔 line that
vanishes from a note no longer loses its task's identity at once. The retiring
write — the extraction pre-pass for a line gone from a surviving note, the
deletion statement for a deleted note — hard-deletes the edge as before and
STAMPS the task with everything the edge knew (``retired_vault_id``,
``retired_source_line``, ``vault_line_retired_at``). A 🆔 that reappears in any
note within one sync finds its task by the stamp and is re-linked; a 🆔 that is
live on another note is a move, and its edge is re-pointed in one statement;
and an end-of-sync sweep judges what is still stamped from before the sync
began — clearing terminal and still-tracked tasks' stamps, and (PR 3,
``TestDeletionCancels``) CANCELLING an open untracked task through the Tasks
facade, its stamp cleared only when that write lands: removing an open task's
line is a decision, and two consecutive syncs without the 🆔 is the deletion.

``EXTRACTED_FROM`` gains ``source_line`` — the line verbatim as SKUEL last saw
it, the base the three-way merge diffs the vault against. Written on create,
seeded where absent, carried by re-point and revival; advanced by SKUEL's own
outbound writes (a 🆔 injection, ``[x] ✅``, an un-check — each applied to the
base as to the file) and by the reconciler once it has consumed the diff.

PR 2 (``TestReconciliation``): a recognised 🆔 line is reconciled against that
base — status both directions and the field edits, one intent, one write, one
verdict per line (``core/services/dsl/line_reconciliation.py``). The base and
digest advance only on an ok write; a refusal holds both and re-warns every
sync until the line and the task agree (C1).

Every case drives the real loop against the container (``_vault_rig.Rig``).
Two orders matter throughout: files ingest newest-mtime first, so A-first and
B-first are forced with ``Rig.order``; and a byte-identical rewrite is a
tracker skip, so a scenario that deletes a line — or completes a task in SKUEL
and syncs before the write-back — changes another byte too.

Mutants each case must fail are named in the PR descriptions (#1343, #1344,
PR 3); each was applied by script, run, seen to fail here, and restored.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.models.enums.activity_enums import Priority
from core.models.enums.entity_enums import EntityStatus
from core.models.task.task_request import TaskUpdateRequest
from core.services.vault.vault_descriptor import VaultKind
from tests.integration._vault_rig import (
    FRONTMATTER,
    NOTE,
    OWNER,
    Rig,
    cancel_in_skuel,
    complete_in_skuel,
    daily_frontmatter,
    reopen_in_skuel,
)

NOTE_B = "periodic_notes/2026-08-24.md"
FRONTMATTER_B = daily_frontmatter("2026-08-24")


async def _seeded_note(rig: Rig, body: str = "- [ ] Vacuum\n") -> tuple[str, str, str]:
    """Two syncs over note A holding ``body``: the task exists, its line carries
    a 🆔, the injected note has been re-ingested (the tracker holds it), and
    the edge's base is the injected line (the injection is SKUEL's own write).
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
        assert base == line, base

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

    @pytest.mark.parametrize("first", ["A", "B"], ids=["A-first", "B-first"])
    async def test_a_line_edited_during_a_move_lands_its_edit(self, rig: Rig, first: str) -> None:
        """The re-point (B-first) and the stamp (A-first) carry the OLD base,
        never the current line: an edit made during the move is a diff against
        it, and the identity branch applies it on the destination. A re-point
        that wrote the current line as the new base would drop the edit."""
        task_uid, vault_id, line = await _seeded_note(rig)
        edited = line.replace("Vacuum", "Vacuum the hallway")

        rig.note.write_text(FRONTMATTER + "Moved it.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + edited + "\n", encoding="utf-8")
        rig.order(*((rig.note, note_b) if first == "A" else (note_b, rig.note)))

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        [(_, edge_id, entry, base)] = await rig.edges()
        assert edge_id == vault_id and entry.endswith(_entry_uid(NOTE_B))
        assert base == edited, f"the base did not advance past the move-time edit: {base!r}"
        got = await rig.tasks.get_task(task_uid)
        assert got.is_ok and got.value is not None
        assert got.value.title == "Vacuum the hallway", "the move-time edit was dropped"

    async def test_cut_sync_paste_sync_is_the_same_task(self, rig: Rig) -> None:
        """The slow move across a sync boundary — the grace window itself. The
        first sync stamps (the task is open, so the sweep leaves it); the
        second finds the 🆔 in B, revives by the stamp, and clears it."""
        task_uid, vault_id, line = await _seeded_note(rig)

        rig.note.write_text(FRONTMATTER + "Cut it.\n", encoding="utf-8")
        cut = await rig.sync()
        assert not cut.warnings, cut.warnings
        assert cut.tasks_cancelled_by_deletion == 0, "a cut was judged as a deletion"
        assert await rig.edges() == []
        [stamp] = await rig.stamps()
        assert (stamp.uid, stamp.retired_vault_id, stamp.retired_source_line) == (
            task_uid,
            vault_id,
            line,
        )
        assert stamp.retired_at is not None

        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + line + "\n", encoding="utf-8")
        pasted = await rig.sync()
        assert not pasted.warnings, pasted.warnings
        assert pasted.tasks_cancelled_by_deletion == 0, (
            "the paste re-linked, then the sweep cancelled"
        )
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "the slow move minted a twin, or cancelled the task"
        )
        [(edge_uid, edge_id, entry, base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert base == line, "the revived edge carries the stamp's base"
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


async def _seeded_done_note(rig: Rig) -> tuple[str, str, str]:
    """``_seeded_note``, then completed in SKUEL and written back: the line reads
    ``- [x] Vacuum 🆔 sk_… ✅ date`` and the write-back has been re-ingested.
    Returns ``(task_uid, vault_id, done_line)``."""
    task_uid, vault_id, _line = await _seeded_note(rig)
    await complete_in_skuel(rig, task_uid)
    await rig.sync()  # [x] ✅ write-back
    await rig.sync()  # the write-back re-ingests
    done_line = next(
        ln for ln in rig.note.read_text(encoding="utf-8").splitlines() if vault_id in ln
    )
    assert done_line.startswith("- [x]") and "✅" in done_line, done_line
    return task_uid, vault_id, done_line


@pytest.mark.asyncio
@pytest.mark.integration
class TestDoneLinesMoveToo:
    """The twin shape the plan names. Guard 4 ignores terminal twins by design,
    so a completed task's line found by no edge and no stamp is minted again —
    a second COMPLETED copy. The stamp lookup (A-first, slow) and the one-
    statement re-point (B-first) are what stand between a move and that twin."""

    @pytest.mark.parametrize("first", ["A", "B"], ids=["A-first", "B-first"])
    async def test_a_done_line_cut_into_another_note_in_one_edit(
        self, rig: Rig, first: str
    ) -> None:
        task_uid, vault_id, done_line = await _seeded_done_note(rig)

        rig.note.write_text(FRONTMATTER + "Consolidated.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + done_line + "\n", encoding="utf-8")
        rig.order(*((rig.note, note_b) if first == "A" else (note_b, rig.note)))

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "the move minted a second completed task"
        )
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert await rig.stamps() == []
        quiet = await rig.sync()
        assert (quiet.ids_injected, quiet.tasks_marked_done) == (0, 0), quiet

    async def test_a_done_line_cut_sync_paste_sync_is_the_same_task(self, rig: Rig) -> None:
        task_uid, vault_id, done_line = await _seeded_done_note(rig)

        rig.note.write_text(FRONTMATTER + "Consolidated.\n", encoding="utf-8")
        await rig.sync()
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + done_line + "\n", encoding="utf-8")
        pasted = await rig.sync()
        assert not pasted.warnings, pasted.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "the slow move minted a second completed task"
        )
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert await rig.stamps() == []


@pytest.mark.asyncio
@pytest.mark.integration
class TestDslCheckboxLinesMoveToo:
    """A ``- [ ] … @context(task)`` checkbox line is a DSL line, and the outbound
    pass injects a 🆔 into it like any checkbox line it tracks — so the DSL
    door reads the 🆔 back (its identity when it moves), or a moved DSL line
    would lose its task through Guard 4 and a completed one would be minted
    twice. The obsidian-tasks metadata vocabulary stays uninterpreted on it."""

    async def test_a_done_dsl_task_line_cut_into_another_note(self, rig: Rig) -> None:
        task_uid, vault_id, _line = await _seeded_note(rig, "- [ ] Call mom @context(task)\n")
        got = await rig.tasks.get_task(task_uid)
        assert got.is_ok and got.value is not None and got.value.title == "Call mom"
        await complete_in_skuel(rig, task_uid)
        await rig.sync()  # [x] ✅ write-back
        await rig.sync()  # re-ingests: the DSL door reads the 🆔 — one task
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)]
        done_line = next(
            ln for ln in rig.note.read_text(encoding="utf-8").splitlines() if vault_id in ln
        )
        assert done_line.startswith("- [x]") and "@context(task)" in done_line, done_line

        rig.note.write_text(FRONTMATTER + "Consolidated.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + done_line + "\n", encoding="utf-8")
        rig.order(note_b, rig.note)

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "the moved DSL line minted a second completed task"
        )
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert await rig.stamps() == []
        got = await rig.tasks.get_task(task_uid)
        assert got.is_ok and got.value is not None and got.value.title == "Call mom", (
            "the 🆔 token leaked into the title"
        )


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
        assert tidied.tasks_cancelled_by_deletion == 0
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id
        # The base the stamp carries is the one the edge held — advanced to
        # SKUEL's own ``[x] ✅`` write-back when that write landed.
        assert stamp.retired_source_line is not None
        assert stamp.retired_source_line.startswith("- [x] Vacuum") and "✅" in (
            stamp.retired_source_line
        )

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert await rig.stamps() == [], "a terminal task's stamp survives the grace"
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "tidying a done line out of a note is not a state change — the sweep cancelled it"
        )
        assert swept.tasks_cancelled_by_deletion == 0

    async def test_a_deleted_open_line_is_cancelled_two_syncs_later(self, rig: Rig) -> None:
        """Rule 1. The sync that sees the line gone stamps the task and judges
        nothing (the grace — the line may be on its way to another note); the
        next sync's sweep finds an open, untracked task past the grace and
        cancels it through the facade, clearing the stamp because that write
        landed. Nothing is written to the vault by either sync (the line is
        gone, so there is nothing to un-check), the count reports on the
        sweep's sync only, and the sync after is quiet."""
        task_uid, vault_id, _line = await _seeded_note(rig)

        rig.note.write_text(FRONTMATTER + "Gone.\n", encoding="utf-8")
        gone = await rig.sync()
        assert not gone.warnings, gone.warnings
        assert gone.tasks_cancelled_by_deletion == 0, "judged in the sync that retired it"
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)]
        [stamp] = await rig.stamps()
        assert (stamp.uid, stamp.retired_vault_id) == (task_uid, vault_id)

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert swept.tasks_cancelled_by_deletion == 1, swept
        assert swept.tasks_marked_undone == 0 and swept.tasks_marked_done == 0
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.CANCELLED.value)]
        assert await rig.stamps() == [], "the stamp outlived the cancel that landed"
        assert rig.note.read_text(encoding="utf-8") == FRONTMATTER + "Gone.\n", (
            "a cancel-by-deletion wrote into the vault"
        )

        quiet = await rig.sync()
        assert not quiet.warnings, quiet.warnings
        assert quiet.tasks_cancelled_by_deletion == 0 and quiet.tasks_marked_undone == 0
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.CANCELLED.value)]

    async def test_a_deleted_note_stamps_its_tasks(self, rig: Rig) -> None:
        """Whole-note deletion is ``DETACH DELETE`` on the entry, which takes
        every edge with it: the tasks are stamped in that same statement.
        Then the sweep: the done one clears, untouched; the open one is
        cancelled — the note's deletion is the decision, two syncs later."""
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
        done_uid = next(uid for uid, _, _, base in edges if (base or "").startswith("- [ ] Read"))
        open_uid = next(uid for uid, _, _, base in edges if (base or "").startswith("- [ ] Vacuum"))
        ids = {uid: vault_id for uid, vault_id, _, _ in edges}
        await complete_in_skuel(rig, done_uid)
        await rig.sync()  # write-back into the note
        await rig.sync()  # re-ingest

        rig.note.unlink()
        deleted = await rig.sync()
        assert not deleted.warnings, deleted.warnings
        assert deleted.entities_deleted == 1, deleted
        assert deleted.tasks_cancelled_by_deletion == 0, "judged in the sync that retired it"
        assert await rig.edges() == []
        stamps = {s.uid: s for s in await rig.stamps()}
        assert set(stamps) == {done_uid, open_uid}, stamps
        assert stamps[done_uid].retired_vault_id == ids[done_uid]
        assert stamps[open_uid].retired_vault_id == ids[open_uid]
        assert stamps[open_uid].retired_source_line == f"- [ ] Vacuum 🆔 {ids[open_uid]}"

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert swept.tasks_cancelled_by_deletion == 1, swept
        assert await rig.stamps() == []
        assert sorted(await rig.owned_tasks()) == sorted(
            [(done_uid, EntityStatus.COMPLETED.value), (open_uid, EntityStatus.CANCELLED.value)]
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
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "a task still tracked from its second note was cancelled"
        )
        assert swept.tasks_cancelled_by_deletion == 0
        assert [(uid, v) for uid, v, _, _ in await rig.edges()] == [(task_uid, second_id)]

    @pytest.mark.parametrize("first", ["A", "B"], ids=["A-first", "B-first"])
    async def test_consolidating_both_lines_of_a_task_into_one_note_keeps_that_notes_edge(
        self, rig: Rig, first: str
    ) -> None:
        """A task tracked from A (🆔 X) and, retyped, from B (🆔 Y). The user
        cuts A's line and pastes it into B, which now holds both lines. One
        provenance edge per (task, entry): B's own edge (Y) must survive — a
        re-point or revival that MERGEd onto it would overwrite Y's identity
        and write-back mapping with X's. Either order: the move is refused,
        A's edge retires and stamps, the sweep sees a task still tracked from
        B and clears the stamp. No twin; X's line in B stays untracked."""
        task_uid, vault_id, line = await _seeded_note(rig)
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + "- [ ] Vacuum\n", encoding="utf-8")
        await rig.sync()  # Guard 4 merges and writes B's edge; Y injected
        await rig.sync()  # the injection re-ingests
        edges = await rig.edges()
        assert [uid for uid, _, _, _ in edges] == [task_uid, task_uid], edges
        second_id = next(v for _, v, entry, _ in edges if entry.endswith(_entry_uid(NOTE_B)))
        assert second_id and second_id != vault_id
        b_text = note_b.read_text(encoding="utf-8")
        assert second_id in b_text

        rig.note.write_text(FRONTMATTER + "Consolidated.\n", encoding="utf-8")
        note_b.write_text(b_text + line + "\n", encoding="utf-8")  # now both lines
        rig.order(*((rig.note, note_b) if first == "A" else (note_b, rig.note)))

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "consolidating minted a twin"
        )
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, second_id), "B's own edge was overwritten"
        assert entry.endswith(_entry_uid(NOTE_B))

        swept = await rig.sync()
        assert not swept.warnings, swept.warnings
        assert await rig.stamps() == []
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "a task still tracked from B was cancelled when A's line went"
        )
        assert swept.tasks_cancelled_by_deletion == 0
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
class TestDeletionCancels:
    """R4 PR 3 — the shapes around the cancel that the sweep cases above do
    not reach: the hold over an unreadable note with an OPEN task at stake,
    and what a 🆔 line typed back AFTER its cancel meets (ruled for PR 3:
    the stamp clears with the cancel, so a late re-type is a phantom)."""

    async def test_an_open_task_is_held_over_a_note_it_could_not_read_then_revived(
        self, rig: Rig
    ) -> None:
        """The open-task twin of ``TestTheSweep``'s hold case, where the stake
        is a cancel rather than a twin. The line moves into B, but B's
        frontmatter is broken: B has not had its say, so the sweep holds the
        stamp with a warning and cancels nothing — once B is fixed, its line
        revives the task by that stamp, still open. Without the hold the
        sweep would cancel a task whose line was in the vault all along."""
        task_uid, vault_id, line = await _seeded_note(rig)

        rig.note.write_text(FRONTMATTER + "Consolidated.\n", encoding="utf-8")
        broken_b = FRONTMATTER_B.replace("---\n\n", "  bad: [unclosed\n---\n\n", 1)
        rig.note_at(NOTE_B).write_text(broken_b + line + "\n", encoding="utf-8")
        stamped = await rig.sync()
        assert stamped.files_broken == 1, stamped
        assert stamped.retirements_held == 0 and stamped.tasks_cancelled_by_deletion == 0
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        held = await rig.sync()
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "the sweep cancelled over a note it could not read"
        )
        assert held.files_broken == 1, held
        assert held.retirements_held == 1 and held.tasks_cancelled_by_deletion == 0, held
        assert any("1 vault retirement(s) held" in w for w in held.warnings), held.warnings
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + line + "\n", encoding="utf-8")
        fixed = await rig.sync()
        assert not fixed.warnings, fixed.warnings
        assert fixed.tasks_cancelled_by_deletion == 0
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "revived, not cancelled — or a twin was minted"
        )
        [(edge_uid, edge_id, entry, base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert base == line
        assert await rig.stamps() == []

    async def test_a_vault_that_reads_empty_holds_the_sweep_instead_of_cancelling(
        self, rig: Rig
    ) -> None:
        """Cut the line, sync (stamped). Before the paste is synced the vault
        reads EMPTY — an unmounted root, a sync client mid-resync: the walk
        finds no files and the deletion valve refuses (every tracked file
        vanished). ``files_failed`` is 0 on such a sync, yet no note has had
        its say; the sweep must hold, or the unmount cancels the task whose
        paste is one sync away and the remount mints a twin beside it. Then
        the remount, with the paste in B: revived, not cancelled, no twin."""
        task_uid, vault_id, line = await _seeded_note(rig)
        rig.note.write_text(FRONTMATTER + "Cut it.\n", encoding="utf-8")
        await rig.sync()
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        notes = rig.vault / "periodic_notes"
        aside = rig.vault.parent / "unmounted"
        notes.rename(aside)
        notes.mkdir()
        unmounted = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)
        assert unmounted.is_ok, unmounted
        stats = unmounted.value
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "an unmounted vault cancelled a task awaiting its paste"
        )
        assert stats.vault_read_refused and stats.files_failed == 0, stats
        assert stats.retirements_held == 1 and stats.tasks_cancelled_by_deletion == 0, stats
        assert stats.entities_deleted == 0, "the deletion valve did not refuse"
        [stamp] = await rig.stamps()
        assert stamp.retired_vault_id == vault_id

        notes.rmdir()
        aside.rename(notes)
        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + line + "\n", encoding="utf-8")
        remounted = await rig.sync()
        assert not remounted.warnings, remounted.warnings
        assert remounted.tasks_cancelled_by_deletion == 0
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.DRAFT.value)], (
            "the remount minted a twin"
        )
        [(edge_uid, edge_id, entry, base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert base == line
        assert await rig.stamps() == []

    async def test_a_line_typed_back_after_its_cancel_is_a_new_task_beside_it(
        self, rig: Rig
    ) -> None:
        """The cost of clearing the stamp with the cancel (ruled, PR 3): a 🆔
        line typed back AFTER the sweep has cancelled its task finds no edge
        and no stamp — a phantom — and Guard 4 ignores terminal twins, so a
        NEW open task is minted beside the cancelled one and adopts the
        line's 🆔. The cancelled task is the record of the deletion, not
        resurrected; the residual's other door is the next case."""
        task_uid, vault_id, line = await _seeded_note(rig)
        rig.note.write_text(FRONTMATTER + "Gone.\n", encoding="utf-8")
        await rig.sync()
        swept = await rig.sync()
        assert swept.tasks_cancelled_by_deletion == 1, swept
        assert await rig.stamps() == []

        rig.note.write_text(FRONTMATTER + line + "\nBack.\n", encoding="utf-8")
        back = await rig.sync()
        assert not back.warnings, back.warnings
        assert back.tasks_cancelled_by_deletion == 0
        statuses = dict(await rig.owned_tasks())
        assert statuses.pop(task_uid) == EntityStatus.CANCELLED.value, (
            "the typed-back line resurrected the cancelled task"
        )
        [(new_uid, new_status)] = statuses.items()
        assert new_status == EntityStatus.DRAFT.value
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (new_uid, vault_id), "the 🆔 names the new task now"
        assert entry.endswith(_entry_uid(NOTE))

    async def test_un_cancelling_in_skuel_then_typing_the_line_back_reunites_them(
        self, rig: Rig
    ) -> None:
        """The residual's other door: un-cancel in SKUEL first (the task is an
        active twin again), then type the line back — Guard 4 merges the
        line into the open twin by title and, the twin having no edge to
        this note, writes one carrying the line's 🆔. One task, tracked."""
        task_uid, vault_id, line = await _seeded_note(rig)
        rig.note.write_text(FRONTMATTER + "Gone.\n", encoding="utf-8")
        await rig.sync()
        await rig.sync()
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.CANCELLED.value)]

        await reopen_in_skuel(rig, task_uid)
        rig.note.write_text(FRONTMATTER + line + "\nBack.\n", encoding="utf-8")
        back = await rig.sync()
        assert not back.warnings, back.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.ACTIVE.value)], (
            "the un-cancelled task was not reunited with its line"
        )
        [(edge_uid, edge_id, entry, base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE))
        assert base == line

    async def test_a_note_restored_after_its_tasks_were_cancelled_is_not_a_resurrection(
        self, rig: Rig
    ) -> None:
        """Delete a note, sync, sync (its open task cancelled, its done task's
        stamp cleared), then put the note back with both lines: neither task
        is revived — both 🆔s are phantoms by then and Guard 4 ignores
        terminal twins — so each line mints a new task beside its original.
        The same shape as the typed-back line, at note scale; a restore
        within one sync (the grace) is the revival, not this."""
        rig.note.write_text(FRONTMATTER + "- [ ] Vacuum\n- [ ] Read\n", encoding="utf-8")
        rig.note_at(NOTE_B).write_text(FRONTMATTER_B + "Still here.\n", encoding="utf-8")
        await rig.sync()
        await rig.sync()
        edges = await rig.edges()
        assert len(edges) == 2, edges
        done_uid = next(uid for uid, _, _, base in edges if (base or "").startswith("- [ ] Read"))
        open_uid = next(uid for uid, _, _, base in edges if (base or "").startswith("- [ ] Vacuum"))
        await complete_in_skuel(rig, done_uid)
        await rig.sync()
        await rig.sync()
        restored_text = rig.note.read_text(encoding="utf-8")

        rig.note.unlink()
        await rig.sync()
        swept = await rig.sync()
        assert swept.tasks_cancelled_by_deletion == 1, swept
        assert await rig.stamps() == []

        rig.note.write_text(restored_text + "Restored.\n", encoding="utf-8")
        restored = await rig.sync()
        assert not restored.warnings, restored.warnings
        assert restored.tasks_cancelled_by_deletion == 0
        statuses = dict(await rig.owned_tasks())
        assert statuses.pop(open_uid) == EntityStatus.CANCELLED.value, "resurrected"
        assert statuses.pop(done_uid) == EntityStatus.COMPLETED.value
        assert sorted(statuses.values()) == sorted(
            [EntityStatus.DRAFT.value, EntityStatus.COMPLETED.value]
        ), statuses
        assert {uid for uid, _, _, _ in await rig.edges()} == set(statuses), (
            "the restored lines are tracked by the new tasks, not the originals"
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestTheBaseIsSeeded:
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


async def _task_of(rig: Rig, task_uid: str):
    got = await rig.tasks.get_task(task_uid)
    assert got.is_ok and got.value is not None, got
    return got.value


def _line_with(note, vault_id: str) -> str:
    return next(ln for ln in note.read_text(encoding="utf-8").splitlines() if vault_id in ln)


@pytest.mark.asyncio
@pytest.mark.integration
class TestReconciliation:
    """R4 PR 2 — a recognised 🆔 line is reconciled three-way against its base.

    One intent, one ``update_task``, one verdict per line; base and digest
    advance only on ok. Status both directions, the field edits, and the
    refusal that holds the base and re-warns."""

    async def test_a_vault_check_completes_with_the_line_date(self, rig: Rig) -> None:
        """Checked with the obsidian-tasks plugin, which writes ``✅ date``
        after the 🆔. The task completes on that date; the outbound pass then
        has nothing to write (the line already carries the trailing marker),
        and the next sync is quiet."""
        task_uid, vault_id, line = await _seeded_note(rig)
        checked = line.replace("- [ ]", "- [x]") + " ✅ 2026-09-10"
        rig.note.write_text(FRONTMATTER + checked + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED
        assert task.completion_date == date(2026, 9, 10)
        assert synced.tasks_marked_done == 0, "the line was already done — nothing to write back"
        [(_, _, _, base)] = await rig.edges()
        assert base == checked, "the base advanced to the line the write consumed"
        assert _line_with(rig.note, vault_id) == checked

        quiet = await rig.sync()
        assert (quiet.entries_ingested, quiet.tasks_marked_done) == (0, 0), quiet

    async def test_a_dateless_tick_completes_with_today_and_is_dated_by_the_outbound(
        self, rig: Rig
    ) -> None:
        """Ticked in Obsidian without the plugin: no ✅. Today is the
        completion, and the outbound pass appends SKUEL's ``✅ today`` — from
        then on SKUEL owns the completion (a later reopen in SKUEL un-checks
        it). The base follows SKUEL's own write, so the next sync reads no
        vault edit."""
        task_uid, vault_id, line = await _seeded_note(rig)
        ticked = line.replace("- [ ]", "- [x]")
        rig.note.write_text(FRONTMATTER + ticked + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED
        assert task.completion_date == date.today()
        assert synced.tasks_marked_done == 1, synced
        dated = _line_with(rig.note, vault_id)
        assert dated == f"{ticked} ✅ {date.today().isoformat()}", dated
        [(_, _, _, base)] = await rig.edges()
        assert base == dated, "SKUEL's own ✅ write advanced the base"

        # The write-back re-ingests: the line equals its base, nothing moves.
        again = await rig.sync()
        assert not again.warnings and again.tasks_marked_done == 0, again
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED and task.completion_date == date.today()

        # SKUEL now owns the completion: a reopen in SKUEL un-checks the line.
        await reopen_in_skuel(rig, task_uid)
        reopened = await rig.sync()
        assert reopened.tasks_marked_undone == 1, reopened
        assert _line_with(rig.note, vault_id) == line

    async def test_a_vault_uncheck_reopens_and_the_stale_date_is_stripped(self, rig: Rig) -> None:
        """The user clicks the box off in Obsidian; the plugin's ✅ token stays
        on the line. The task reopens (stamp cleared by the guarded write),
        and the outbound un-check strips the token SKUEL wrote."""
        task_uid, vault_id, done_line = await _seeded_done_note(rig)
        unchecked = done_line.replace("- [x]", "- [ ]")
        rig.note.write_text(FRONTMATTER + unchecked + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.ACTIVE
        assert task.completion_date is None
        assert synced.tasks_marked_undone == 1, synced
        restored = _line_with(rig.note, vault_id)
        assert restored.startswith("- [ ] Vacuum") and "✅" not in restored, restored
        [(_, _, _, base)] = await rig.edges()
        assert base == restored

        quiet = await rig.sync()
        assert not quiet.warnings and quiet.tasks_marked_undone == 0, quiet
        assert (await _task_of(rig, task_uid)).status == EntityStatus.ACTIVE

    async def test_completed_in_skuel_and_synced_before_the_write_back_stays_completed(
        self, rig: Rig
    ) -> None:
        """The C1 race. Inbound runs before outbound: on the sync right after a
        completion in SKUEL the line still reads ``- [ ]``. The checkbox is
        unchanged against the base, so SKUEL's completion stands and the same
        sync's outbound pass writes ``[x] ✅``. The note changes another byte
        so it is re-ingested at all (a byte-identical file is a tracker skip)."""
        task_uid, vault_id, line = await _seeded_note(rig)
        await complete_in_skuel(rig, task_uid)
        rig.note.write_text(FRONTMATTER + line + "\nSome prose.\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        assert synced.entries_ingested == 1, synced
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED, "the inbound pass reopened it"
        assert synced.tasks_marked_done == 1, synced
        assert _line_with(rig.note, vault_id).startswith("- [x] Vacuum")

    async def test_reopened_in_skuel_and_synced_before_the_un_check_stays_reopened(
        self, rig: Rig
    ) -> None:
        """The mirror race: the line still reads ``[x] ✅`` — SKUEL's own
        write, which the base already holds — so the reopen stands and the
        outbound pass un-checks."""
        task_uid, vault_id, done_line = await _seeded_done_note(rig)
        await reopen_in_skuel(rig, task_uid)
        rig.note.write_text(FRONTMATTER + done_line + "\nSome prose.\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        assert synced.entries_ingested == 1, synced
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.ACTIVE, "the inbound pass re-completed it"
        assert synced.tasks_marked_undone == 1, synced
        restored = _line_with(rig.note, vault_id)
        assert restored.startswith("- [ ] Vacuum") and "✅" not in restored

    @pytest.mark.parametrize("first", ["A", "B"], ids=["A-first", "B-first"])
    async def test_a_line_moved_and_checked_in_one_edit_lands_its_check(
        self, rig: Rig, first: str
    ) -> None:
        """Cut from A, pasted into B checked, one sync. A-first: the stamp
        carries the base and the revival reconciles against it. B-first: the
        re-point carries it. Either way the check lands on the destination."""
        task_uid, vault_id, line = await _seeded_note(rig)
        checked = line.replace("- [ ]", "- [x]") + " ✅ 2026-09-11"
        rig.note.write_text(FRONTMATTER + "Moved it.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + checked + "\n", encoding="utf-8")
        rig.order(*((rig.note, note_b) if first == "A" else (note_b, rig.note)))

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.COMPLETED.value)], (
            "the check did not land, or the move minted a twin"
        )
        task = await _task_of(rig, task_uid)
        assert task.completion_date == date(2026, 9, 11)
        [(edge_uid, edge_id, entry, base)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert base == checked
        assert await rig.stamps() == []

    @pytest.mark.parametrize("first", ["A", "B"], ids=["A-first", "B-first"])
    async def test_a_done_line_moved_and_unchecked_in_one_edit_reopens(
        self, rig: Rig, first: str
    ) -> None:
        """The done-line variant, where a twin is the failure: Guard 4 ignores
        terminal twins, so a completed line found by no edge and no stamp is
        minted again. Moved AND un-checked in one edit: the task reopens on
        the destination, no twin, and the outbound strips SKUEL's ✅."""
        task_uid, vault_id, done_line = await _seeded_done_note(rig)
        unchecked = done_line.replace("- [x]", "- [ ]")
        rig.note.write_text(FRONTMATTER + "Moved it.\n", encoding="utf-8")
        note_b = rig.note_at(NOTE_B)
        note_b.write_text(FRONTMATTER_B + unchecked + "\n", encoding="utf-8")
        rig.order(*((rig.note, note_b) if first == "A" else (note_b, rig.note)))

        moved = await rig.sync()
        assert not moved.warnings, moved.warnings
        assert await rig.owned_tasks() == [(task_uid, EntityStatus.ACTIVE.value)], (
            "the uncheck did not land, or the move minted a twin"
        )
        [(edge_uid, edge_id, entry, _)] = await rig.edges()
        assert (edge_uid, edge_id) == (task_uid, vault_id)
        assert entry.endswith(_entry_uid(NOTE_B))
        assert moved.tasks_marked_undone == 1, moved
        restored = _line_with(note_b, vault_id)
        assert restored.startswith("- [ ] Vacuum") and "✅" not in restored
        assert await rig.stamps() == []

    async def test_a_retitle_and_a_re_date_in_the_vault_follow(self, rig: Rig) -> None:
        """Title, 📅, ⏳, priority and #tags — each three-way, applied because
        the vault changed it. The SKUEL-stamped ``period:daily`` tag survives
        (it is never on the line)."""
        task_uid, vault_id, _line = await _seeded_note(rig)
        # The dates sit in the future relative to the run: the second sync LOWERS the
        # priority, which the Tasks domain refuses on an overdue task — a literal date
        # here would turn this test red the morning after it.
        due = date.today() + timedelta(days=30)
        scheduled = due - timedelta(days=2)
        moved = due + timedelta(days=2)
        edited = f"- [ ] Vacuum the hallway ⏫ 📅 {due} ⏳ {scheduled} #home 🆔 {vault_id}"
        rig.note.write_text(FRONTMATTER + edited + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.title == "Vacuum the hallway"
        assert task.due_date == due
        assert task.scheduled_date == scheduled
        assert task.priority == Priority.HIGH.value
        assert set(task.tags) == {"period:daily", "home"}, task.tags
        assert task.status == EntityStatus.DRAFT
        [(_, _, _, base)] = await rig.edges()
        assert base == edited

        # And back: the vault moves the date and drops the tag; the priority
        # emoji goes — absence is medium.
        again = f"- [ ] Vacuum the hallway 📅 {moved} ⏳ {scheduled} 🆔 {vault_id}"
        rig.note.write_text(FRONTMATTER + again + "\n", encoding="utf-8")
        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.due_date == moved
        assert task.priority == Priority.MEDIUM.value
        assert set(task.tags) == {"period:daily"}, task.tags

    async def test_a_skuel_side_title_edit_survives_an_untouched_line(self, rig: Rig) -> None:
        """The title changed in SKUEL, the line did not (theirs == base): the
        merge keeps SKUEL's value. Another byte of the note changes so it
        re-ingests at all."""
        task_uid, _vault_id, line = await _seeded_note(rig)
        renamed = await rig.tasks.update_task(
            task_uid, TaskUpdateRequest(title="Vacuum (renamed in SKUEL)").to_intent()
        )
        assert renamed.is_ok, renamed
        rig.note.write_text(FRONTMATTER + line + "\nSome prose.\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings and synced.entries_ingested == 1, synced
        task = await _task_of(rig, task_uid)
        assert task.title == "Vacuum (renamed in SKUEL)", (
            "the untouched line overwrote SKUEL's edit"
        )

    async def test_a_skuel_side_title_edit_survives_a_line_edited_elsewhere(self, rig: Rig) -> None:
        """The stronger shape: the line DID change (a #tag was added), so the
        merge runs field by field — the title, unchanged on the vault side,
        keeps SKUEL's value while the tag lands."""
        task_uid, vault_id, line = await _seeded_note(rig)
        renamed = await rig.tasks.update_task(
            task_uid, TaskUpdateRequest(title="Vacuum (renamed in SKUEL)").to_intent()
        )
        assert renamed.is_ok, renamed
        tagged = line.replace(f"🆔 {vault_id}", f"#home 🆔 {vault_id}")
        rig.note.write_text(FRONTMATTER + tagged + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.title == "Vacuum (renamed in SKUEL)", "a field the vault left alone was applied"
        assert "home" in task.tags, task.tags
        [(_, _, _, base)] = await rig.edges()
        assert base == tagged

    async def test_reopened_in_skuel_before_the_write_back_re_ingests_stays_reopened(
        self, rig: Rig
    ) -> None:
        """Why SKUEL's own writes advance the base. Complete in SKUEL; the
        outbound pass writes ``[x] ✅`` — and the user reopens in SKUEL before
        that write-back has been re-ingested. The re-ingest then meets SKUEL's
        own ``[x] ✅`` on the line: with the base still at ``[ ]`` it would read
        as a vault check and re-complete the task SKUEL just reopened. The
        write-back advanced the base as it landed, so the box is unchanged
        against it and the reopen stands; the outbound pass un-checks."""
        task_uid, vault_id, line = await _seeded_note(rig)
        await complete_in_skuel(rig, task_uid)
        written = await rig.sync()  # [x] ✅ write-back, not yet re-ingested
        assert written.tasks_marked_done == 1, written
        [(_, _, _, base)] = await rig.edges()
        assert base is not None and base.startswith("- [x] Vacuum") and "✅" in base, base

        await reopen_in_skuel(rig, task_uid)
        synced = await rig.sync()  # the write-back re-ingests, task reopened
        assert not synced.warnings, synced.warnings
        assert synced.entries_ingested == 1, synced
        assert (await _task_of(rig, task_uid)).status == EntityStatus.ACTIVE, (
            "SKUEL's own write-back was read as a vault check"
        )
        assert synced.tasks_marked_undone == 1, synced
        assert _line_with(rig.note, vault_id) == line

    async def test_a_check_and_a_retitle_in_one_edit_both_land(self, rig: Rig) -> None:
        task_uid, vault_id, _line = await _seeded_note(rig)
        both = f"- [x] Vacuum upstairs 🆔 {vault_id} ✅ 2026-09-12"
        rig.note.write_text(FRONTMATTER + both + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED
        assert task.completion_date == date(2026, 9, 12)
        assert task.title == "Vacuum upstairs"
        [(_, _, _, base)] = await rig.edges()
        assert base == both

    async def test_removing_the_only_date_is_refused_held_and_re_warned(self, rig: Rig) -> None:
        """The keep-a-day rule (a task keeps a day) refuses clearing the only
        date. The refusal is a warning naming the line, the base is HELD, and
        the note is left un-stamped so the next sync re-reads the same diff
        and warns again — until the line and the task agree. Here the task
        gets a scheduled date in SKUEL, after which the clear is legal."""
        task_uid, vault_id, line = await _seeded_note(rig, "- [ ] Vacuum 📅 2026-09-20\n")
        task = await _task_of(rig, task_uid)
        assert (task.due_date, task.scheduled_date) == (date(2026, 9, 20), None)
        [(_, _, _, base_before)] = await rig.edges()
        assert base_before == line

        undated = f"- [ ] Vacuum 🆔 {vault_id}"
        rig.note.write_text(FRONTMATTER + undated + "\n", encoding="utf-8")
        refused = await rig.sync()
        assert refused.entries_ingested == 1, refused
        [warning] = refused.warnings
        assert "Vacuum" in warning and vault_id in warning, warning
        assert "needs a due date or a scheduled date" in warning, warning
        assert (await _task_of(rig, task_uid)).due_date == date(2026, 9, 20)
        [(_, _, _, base_held)] = await rig.edges()
        assert base_held == line, "the base advanced past a refused write"

        # Nothing changed in the vault — and the warning comes back anyway.
        again = await rig.sync()
        assert again.entries_ingested == 1, "the refused note was stamped as up to date"
        [warning] = again.warnings
        assert vault_id in warning
        [(_, _, _, base_still_held)] = await rig.edges()
        assert base_still_held == line

        # The task is given a day in SKUEL; the clear is now legal.
        scheduled = await rig.tasks.update_task(
            task_uid, TaskUpdateRequest(scheduled_date=date(2026, 9, 19)).to_intent()
        )
        assert scheduled.is_ok, scheduled
        cleared = await rig.sync()
        assert not cleared.warnings, cleared.warnings
        task = await _task_of(rig, task_uid)
        assert (task.due_date, task.scheduled_date) == (None, date(2026, 9, 19))
        [(_, _, _, base_after)] = await rig.edges()
        assert base_after == undated

        quiet = await rig.sync()
        assert quiet.entries_ingested == 0 and not quiet.warnings, quiet

    async def test_an_edit_made_before_this_pr_lands_on_the_next_force_sync(self, rig: Rig) -> None:
        """Between the seeding sync (#1343) and this PR, an edit synced under
        PR 1 moved the digest and held the base — the note is stamped as
        up to date, the diff is on the edge. A plain sync skips the unchanged
        note; the edit lands on its next change or on a ``--force`` sync."""
        task_uid, _vault_id, line = await _seeded_note(rig)
        edited = line.replace("Vacuum", "Vacuum upstairs")
        rig.note.write_text(FRONTMATTER + edited + "\n", encoding="utf-8")
        await rig.sync()  # applied here — now put the graph back to PR 1's state
        assert (await _task_of(rig, task_uid)).title == "Vacuum upstairs"
        reverted = await rig.tasks.update_task(
            task_uid, TaskUpdateRequest(title="Vacuum").to_intent()
        )
        assert reverted.is_ok, reverted
        async with rig.driver.session() as session:
            await session.run(
                "MATCH (:Task {uid: $uid})-[r:EXTRACTED_FROM]->() SET r.source_line = $base",
                uid=task_uid,
                base=line,
            )

        plain = await rig.sync()
        assert (plain.entries_ingested, plain.warnings) == (0, []), plain
        assert (await _task_of(rig, task_uid)).title == "Vacuum"

        forced = await rig.sync(force=True)
        assert not forced.warnings, forced.warnings
        assert (await _task_of(rig, task_uid)).title == "Vacuum upstairs"
        [(_, _, _, base)] = await rig.edges()
        assert base == edited

    async def test_a_cancelled_task_is_not_reopened_by_an_unchecked_line(self, rig: Rig) -> None:
        """A cancel is SKUEL's decision. The line stays open and diverges
        visibly — and the user can still complete it in the vault: ``[x]`` on
        a cancelled task is a check, applied."""
        task_uid, vault_id, line = await _seeded_note(rig)
        await cancel_in_skuel(rig, task_uid)
        rig.note.write_text(FRONTMATTER + line + "\nSome prose.\n", encoding="utf-8")
        synced = await rig.sync()
        assert not synced.warnings and synced.entries_ingested == 1, synced
        assert (await _task_of(rig, task_uid)).status == EntityStatus.CANCELLED
        assert _line_with(rig.note, vault_id) == line, "the line diverges visibly, untouched"

        # The user checks the cancelled task's line: a completion.
        checked = line.replace("- [ ]", "- [x]") + " ✅ 2026-09-13"
        rig.note.write_text(FRONTMATTER + checked + "\n", encoding="utf-8")
        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED
        assert task.completion_date == date(2026, 9, 13)

    async def test_a_dsl_checkbox_line_reconciles_its_checkbox_only(self, rig: Rig) -> None:
        """A ``@context(task)`` line is identity-tracked like any checkbox line:
        its tick reaches the task. The obsidian-tasks field vocabulary stays
        literal on it (one vocabulary per line) — a 📅 added to the line is
        text, and the description is not rewritten as the title."""
        task_uid, _vault_id, line = await _seeded_note(rig, "- [ ] Call mom @context(task)\n")
        task = await _task_of(rig, task_uid)
        assert task.title == "Call mom"
        due_before = task.due_date
        checked = (
            line.replace("- [ ]", "- [x]").replace("@context(task)", "@context(task) 📅 2026-09-20")
            + " ✅ 2026-09-14"
        )
        rig.note.write_text(FRONTMATTER + checked + "\n", encoding="utf-8")

        synced = await rig.sync()
        assert not synced.warnings, synced.warnings
        task = await _task_of(rig, task_uid)
        assert task.status == EntityStatus.COMPLETED
        assert task.completion_date == date(2026, 9, 14)
        assert task.title == "Call mom", "the DSL line's text was written as the title"
        assert task.due_date == due_before, "the 📅 on a DSL line is literal text"
