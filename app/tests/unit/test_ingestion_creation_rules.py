"""The vault door's copy of the Task creation rule — the engine's post-persist pass.

``UnifiedIngestionService._apply_creation_rules`` hands the write backend the
uids the upsert's own MERGE branch reported as CREATED when the batch is Tasks,
and nothing otherwise. What is pinned here, DB-free:

- the create signal is the upsert's marker, never a null prior status — a
  re-synced node that carries no ``status`` property reports a null prior too,
  and a re-sync is not a creation (a file whose dates were removed keeps them
  removed, as an app update that clears both dates does);
- only the Task batch reaches the backend;
- the pass runs BEFORE the ADR-087 status step (a born-completed task's
  completion event reads ``due_date`` back for ``was_overdue``);
- a failed write is logged and swallowed — the entity has already landed.

The write itself, and both real doors, run against a graph in
``tests/integration/test_vault_door_creation_rule.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from neo4j.exceptions import ServiceUnavailable

from core.models.enums.entity_enums import EntityType


class _FakeWriteBackend:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail
        self.order: list[str] = []

    async def apply_task_creation_due_dates(self, uids: list[str]) -> int:
        self.order.append("creation_rule")
        if self.fail:
            raise ServiceUnavailable("graph away")
        self.calls.append(list(uids))
        return len(uids)

    async def clear_completion_stamps(self, field_name: str, uids: list[str]) -> int:
        self.order.append("stamp_clear")
        return 0


def _service(backend: _FakeWriteBackend) -> Any:
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService

    return UnifiedIngestionService(
        write_backend=backend,  # type: ignore[arg-type]
        bulk_backend=object(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_only_the_batchs_creates_are_named():
    backend = _FakeWriteBackend()
    await _service(backend)._apply_creation_rules(
        EntityType.TASK, frozenset({"task.new", "task.also-new"})
    )
    assert backend.calls == [["task.also-new", "task.new"]]


@pytest.mark.asyncio
async def test_a_null_prior_status_is_not_a_create():
    """The marker, not the prior: a re-synced file with no ``status:`` line
    reports a null prior and must NOT be re-dated — the parity pass names
    only what the upsert's MERGE branch created."""
    backend = _FakeWriteBackend()
    await _service(backend)._apply_primitive_parity(
        EntityType.TASK,
        [{"uid": "task.resynced", "title": "no status line"}],
        {"task.resynced": None},
        frozenset(),
    )
    assert backend.calls == []


@pytest.mark.asyncio
async def test_a_batch_with_no_creates_never_reaches_the_backend():
    backend = _FakeWriteBackend()
    await _service(backend)._apply_creation_rules(EntityType.TASK, frozenset())
    assert backend.calls == []


@pytest.mark.asyncio
async def test_only_tasks_have_a_creation_rule():
    backend = _FakeWriteBackend()
    for entity_type in (EntityType.GOAL, EntityType.HABIT, EntityType.KU, EntityType.EVENT):
        await _service(backend)._apply_creation_rules(entity_type, frozenset({"x.new"}))
    assert backend.calls == []


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_not_raised():
    """The entity has landed; the backfill script is the remedy, not a failed file."""
    backend = _FakeWriteBackend(fail=True)
    await _service(backend)._apply_creation_rules(EntityType.TASK, frozenset({"task.new"}))
    assert backend.calls == []


@pytest.mark.asyncio
async def test_the_parity_pass_dates_before_it_transitions():
    """Creation rule first: the status step's completion event reads ``due_date``
    back to decide ``was_overdue`` — the service door publishes from the dated
    entity too."""
    backend = _FakeWriteBackend()
    # An open-arriving task with a leftover stamp line → the status step owes a
    # stamp-clear, which is how the ordering is observable without a bus.
    await _service(backend)._apply_primitive_parity(
        EntityType.TASK,
        [{"uid": "task.new", "status": "draft", "completion_date": "2026-03-04"}],
        {"task.new": None},
        frozenset({"task.new"}),
    )
    assert backend.order == ["creation_rule", "stamp_clear"]
