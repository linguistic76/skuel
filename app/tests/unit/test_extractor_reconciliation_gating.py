"""The Guard 2b identity branch's ok / refused gating (R4 PR 2, C1).

``ActivityExtractorService`` reconciles a recognised 🆔 line against the base
its edge holds and hands the outcome back on the result: the edge's base and
digest ADVANCE (``advanced_links``) only when the write it implied landed — or
when the verdict asked nothing — and HOLD (nothing queued, the line named on
``reconciliation_errors``) when the domain door refused it, the write failed,
or the request model rejected the line's values. DB-free: the tasks service is
a double whose ``get_task`` / ``update_task`` answer as the real one would.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import Pipeline
from core.models.sentinels import UNSET
from core.models.task.task import Task
from core.models.user_entry.user_entry import UserEntry
from core.services.dsl.activity_extractor import (
    ActivityExtractorService,
    ExtractedByVaultId,
    normalized_line_hash,
)
from core.utils.result_simplified import Errors, Result

OWNER = "user_mike"
VAULT_ID = "sk_ab12cd"
BASE = f"- [ ] Vacuum 🆔 {VAULT_ID}"
D1 = date(2026, 9, 10)


def _entry(content: str, *, vault_note: bool = True) -> UserEntry:
    return UserEntry(
        uid="ue:daily:user_mike:2026-09-15",
        title="2026-09-15",
        user_uid=OWNER,
        entity_type=EntityType.USER_ENTRY,
        status=EntityStatus.COMPLETED,
        pipeline=Pipeline.EXTRACT_ACTIVITIES,
        original_filename="2026-09-15.md",
        file_path="/vault/periodic_notes/2026-09-15.md",
        file_type="text/markdown",
        file_size=len(content),
        processed_content=content,
        metadata=(
            {"entry_kind": "daily", "vault_file_path": "periodic_notes/2026-09-15.md"}
            if vault_note
            else {"entry_kind": "daily"}
        ),
    )


def _task(status: EntityStatus = EntityStatus.DRAFT, *, owner: str = OWNER) -> Task:
    return Task(
        uid="task_vacuum",
        entity_type=EntityType.TASK,
        title="Vacuum",
        user_uid=owner,
        status=status,
        tags=("period:daily",),
    )


_NOT_FOUND = object()


def _tasks_service(
    task: Task | object | None = _NOT_FOUND, *, update: Result[Task] | None = None
) -> MagicMock:
    """A tasks double: ``task`` is what ``get_task`` returns (the open Vacuum task
    by default; ``None`` for a not-found), ``update`` what ``update_task`` answers."""
    found: Task | None = _task() if task is _NOT_FOUND else task  # type: ignore[assignment]
    svc = MagicMock()
    svc.get_task = AsyncMock(
        return_value=Result.ok(found)
        if found is not None
        else Result.fail(Errors.not_found("Entity", "task_vacuum"))
    )
    svc.update_task = AsyncMock(return_value=update if update is not None else Result.ok(found))
    svc.create_task = AsyncMock(return_value=Result.ok(_task()))
    return svc


def _edges(base: str | None = BASE) -> dict[str, tuple[ExtractedByVaultId, ...]]:
    return {VAULT_ID: (ExtractedByVaultId("task_vacuum", normalized_line_hash(BASE), base),)}


async def _run(
    content: str,
    svc: MagicMock,
    *,
    vault_note: bool = True,
    edges: dict[str, tuple[ExtractedByVaultId, ...]] | None = None,
):
    extractor = ActivityExtractorService(tasks_service=svc)
    result = await extractor.extract_and_create(
        _entry(content, vault_note=vault_note),
        OWNER,
        existing_line_hashes=frozenset({normalized_line_hash(BASE)}),
        existing_vault_ids=edges if edges is not None else _edges(),
    )
    assert result.is_ok, result
    return result.value


@pytest.mark.asyncio
class TestOkAdvances:
    async def test_a_vault_check_is_written_and_the_edge_advances(self) -> None:
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service()
        extraction = await _run(theirs + "\n", svc)

        svc.update_task.assert_awaited_once()
        uid, intent = svc.update_task.await_args.args
        assert uid == "task_vacuum"
        assert intent.status == EntityStatus.COMPLETED.value
        assert intent.completion_date == D1
        assert extraction.tasks_created == 0
        assert extraction.lines_skipped_existing == 1
        assert extraction.lines_reconciled == 1
        assert extraction.reconciliation_errors == []
        # Base AND digest move to the current line — the ✅ date is inside the
        # digest, so this is a rehash too.
        assert extraction.advanced_links == [
            ("task_vacuum", normalized_line_hash(theirs), VAULT_ID, theirs)
        ]
        assert extraction.refreshed_links == []
        assert extraction.lines_rehashed == 1
        assert extraction.to_dict()["advanced_links"] == [
            ["task_vacuum", normalized_line_hash(theirs), VAULT_ID]
        ]
        assert extraction.to_dict()["lines_reconciled"] == 1

    async def test_a_verdict_with_nothing_to_write_still_advances(self) -> None:
        """The 🆔 injection alone: same fields, nothing to write — but the base
        must move to the injected line, or it re-diffs every sync. No read
        of the task is even needed when the line is byte-identical to the
        base; here it differs (the token), so the task is read once."""
        svc = _tasks_service()
        seed = "- [ ] Vacuum"
        extraction = await _run(
            BASE + "\n",
            svc,
            edges={
                VAULT_ID: (ExtractedByVaultId("task_vacuum", normalized_line_hash(seed), seed),)
            },
        )
        svc.update_task.assert_not_awaited()
        assert extraction.lines_reconciled == 0
        assert extraction.advanced_links == [
            ("task_vacuum", normalized_line_hash(BASE), VAULT_ID, BASE)
        ]
        assert extraction.lines_rehashed == 0, "the digest is 🆔-blind"

    async def test_a_line_equal_to_its_base_reads_nothing_and_advances_nothing(self) -> None:
        svc = _tasks_service()
        extraction = await _run(BASE + "\n", svc)
        svc.get_task.assert_not_awaited()
        svc.update_task.assert_not_awaited()
        assert extraction.advanced_links == []
        assert extraction.refreshed_links == []
        assert extraction.lines_skipped_existing == 1

    async def test_a_dateless_tick_is_invisible_to_the_digest_but_not_to_the_branch(self) -> None:
        """``[x]`` collapses to ``[ ]`` in the digest, so Guard 2's hash test
        would have skipped this line before the identity branch ran. Identity
        is judged first."""
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID}"
        svc = _tasks_service()
        extraction = await _run(theirs + "\n", svc)
        svc.update_task.assert_awaited_once()
        intent = svc.update_task.await_args.args[1]
        assert intent.status == EntityStatus.COMPLETED.value
        assert intent.completion_date == date.today()
        assert extraction.lines_rehashed == 0
        assert extraction.advanced_links == [
            ("task_vacuum", normalized_line_hash(theirs), VAULT_ID, theirs)
        ]

    async def test_the_race_row_writes_nothing_and_advances_the_base(self) -> None:
        """C1: completed in SKUEL, the line still ``[ ]`` but its text moved
        (another edit on the line) — the checkbox is unchanged against the
        base, so the completion stands and only the edit is applied."""
        theirs = f"- [ ] Vacuum upstairs 🆔 {VAULT_ID}"
        svc = _tasks_service(_task(EntityStatus.COMPLETED))
        extraction = await _run(theirs + "\n", svc)
        intent = svc.update_task.await_args.args[1]
        assert intent.title == "Vacuum upstairs"
        assert intent.status is UNSET, "no status change — the vault did not touch the box"
        assert extraction.advanced_links[0][3] == theirs

    async def test_a_dsl_line_reconciles_its_checkbox_only(self) -> None:
        base = f"- [ ] Call mom @context(task) 🆔 {VAULT_ID}"
        theirs = f"- [x] Call mom @context(task) 📅 2026-09-20 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service()
        extraction = await _run(
            theirs + "\n",
            svc,
            edges={
                VAULT_ID: (ExtractedByVaultId("task_vacuum", normalized_line_hash(base), base),)
            },
        )
        intent = svc.update_task.await_args.args[1]
        assert intent.status == EntityStatus.COMPLETED.value
        assert intent.completion_date == D1
        assert intent.due_date is UNSET
        assert intent.title is UNSET
        assert extraction.lines_reconciled == 1


@pytest.mark.asyncio
class TestRefusedHolds:
    async def test_a_refused_write_holds_base_and_digest_and_names_the_line(self) -> None:
        """The keep-a-day rule refuses clearing the only date: nothing is
        queued for the edge, the refusal names the line, and the next sync
        sees the same diff (the retry is the held base)."""
        theirs = f"- [ ] Vacuum 🆔 {VAULT_ID}"
        base = f"- [ ] Vacuum 📅 2026-09-20 🆔 {VAULT_ID}"
        refusal: Result[Task] = Result.fail(
            Errors.validation(
                message="A task needs a due date or a scheduled date — set one before "
                "clearing the other",
                field="due_date",
                value=None,
            )
        )
        svc = _tasks_service(update=refusal)
        extraction = await _run(
            theirs + "\n",
            svc,
            edges={
                VAULT_ID: (ExtractedByVaultId("task_vacuum", normalized_line_hash(base), base),)
            },
        )
        svc.update_task.assert_awaited_once()
        assert extraction.advanced_links == []
        assert extraction.refreshed_links == []
        assert extraction.lines_reconciled == 0
        [warning] = extraction.reconciliation_errors
        assert "'Vacuum'" in warning and VAULT_ID in warning
        assert "A task needs a due date" in warning
        assert extraction.to_dict()["reconciliation_errors"] == [warning]

    async def test_a_failed_write_holds_too(self) -> None:
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service(update=Result.fail(Errors.database("update_task", "boom")))
        extraction = await _run(theirs + "\n", svc)
        assert extraction.advanced_links == []
        assert extraction.lines_reconciled == 0
        assert len(extraction.reconciliation_errors) == 1

    async def test_a_value_the_request_model_refuses_never_reaches_the_door(self) -> None:
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ 2099-01-01"
        svc = _tasks_service()
        extraction = await _run(theirs + "\n", svc)
        svc.update_task.assert_not_awaited()
        assert extraction.advanced_links == []
        [warning] = extraction.reconciliation_errors
        assert "future" in warning and VAULT_ID in warning

    async def test_a_task_read_failure_holds(self) -> None:
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service()
        svc.get_task = AsyncMock(return_value=Result.fail(Errors.database("get_task", "boom")))
        extraction = await _run(theirs + "\n", svc)
        svc.update_task.assert_not_awaited()
        assert extraction.advanced_links == []
        assert len(extraction.reconciliation_errors) == 1

    async def test_a_task_of_another_user_is_refused(self) -> None:
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service(_task(owner="user_other"))
        extraction = await _run(theirs + "\n", svc)
        svc.update_task.assert_not_awaited()
        assert extraction.advanced_links == []
        [warning] = extraction.reconciliation_errors
        assert "not owned" in warning


@pytest.mark.asyncio
class TestTheGates:
    async def test_no_base_seeds_and_applies_nothing(self) -> None:
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service()
        extraction = await _run(theirs + "\n", svc, edges=_edges(base=None))
        svc.get_task.assert_not_awaited()
        svc.update_task.assert_not_awaited()
        assert extraction.advanced_links == []
        assert extraction.refreshed_links == [
            ("task_vacuum", normalized_line_hash(theirs), VAULT_ID, theirs)
        ]
        assert (extraction.bases_seeded, extraction.lines_rehashed) == (1, 1)

    async def test_a_non_vault_entry_never_reconciles(self) -> None:
        """An uploaded or API-processed entry holding a copied 🆔 line: the
        line is recognised (never re-minted) and its edge takes the plain
        refresh — digest moved, base held — but no task is read or written."""
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service()
        extraction = await _run(theirs + "\n", svc, vault_note=False)
        svc.get_task.assert_not_awaited()
        svc.update_task.assert_not_awaited()
        assert extraction.advanced_links == []
        assert extraction.refreshed_links == [
            ("task_vacuum", normalized_line_hash(theirs), VAULT_ID, theirs)
        ]
        assert extraction.lines_skipped_existing == 1

    async def test_an_edge_that_is_not_a_task_takes_the_plain_refresh(self) -> None:
        """A ``@context(task,habit)`` line holds one edge per domain under one
        🆔; the habit's is not the reconciler's."""
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service(task=None)  # get_task → not found
        extraction = await _run(theirs + "\n", svc)
        svc.update_task.assert_not_awaited()
        assert extraction.reconciliation_errors == []
        assert extraction.advanced_links == []
        assert extraction.refreshed_links == [
            ("task_vacuum", normalized_line_hash(theirs), VAULT_ID, theirs)
        ]

    async def test_a_same_text_sibling_is_still_a_new_task(self) -> None:
        """The pre-pass retirement of the stale digest is unconditional: a
        🆔-less sibling with the ORIGINAL text, arriving in the same ingest
        as the write-back, must not hash into the recognised line's old
        digest and be dropped by Guard 2 — reconciliation or not."""
        seed = "- [ ] Vacuum"
        theirs = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        svc = _tasks_service()
        extraction = await _run(
            f"{seed}\n{theirs}\n",
            svc,
            edges={
                VAULT_ID: (ExtractedByVaultId("task_vacuum", normalized_line_hash(seed), seed),)
            },
        )
        assert extraction.tasks_created == 1, extraction.to_dict()
        assert extraction.lines_reconciled == 1
