"""The vault door's copy of the Task keep-a-day rule — the engine's post-persist pass.

``UnifiedIngestionService._apply_creation_rules`` hands the write backend every
Task uid the batch persisted — creates and re-syncs alike — and the write's own
guard (undated, has a ``created_at``) selects the rows. What is pinned here,
DB-free:

- every uid in the batch is named, whatever its prior status: the invariant
  "a task keeps a day" holds on re-sync too, because a file that dropped its
  last date line cannot be refused mid-upsert the way an app update is
  (``TasksCoreService._validate_update``) — restoring the day is the vault's
  equivalent;
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
async def test_every_persisted_task_is_named_whatever_its_prior():
    """Creates (null prior) and re-syncs alike: the write's guard, not the
    prior status, decides which rows are touched."""
    backend = _FakeWriteBackend()
    await _service(backend)._apply_creation_rules(
        EntityType.TASK,
        {"task.new": None, "task.resynced": "draft", "task.no-status-line": None},
    )
    assert backend.calls == [["task.new", "task.no-status-line", "task.resynced"]]


@pytest.mark.asyncio
async def test_an_empty_batch_never_reaches_the_backend():
    backend = _FakeWriteBackend()
    await _service(backend)._apply_creation_rules(EntityType.TASK, {})
    assert backend.calls == []


@pytest.mark.asyncio
async def test_only_tasks_have_a_creation_rule():
    backend = _FakeWriteBackend()
    for entity_type in (EntityType.GOAL, EntityType.HABIT, EntityType.KU, EntityType.EVENT):
        await _service(backend)._apply_creation_rules(entity_type, {"x.new": None})
    assert backend.calls == []


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_not_raised():
    """The entity has landed; the backfill script is the remedy, not a failed file."""
    backend = _FakeWriteBackend(fail=True)
    await _service(backend)._apply_creation_rules(EntityType.TASK, {"task.new": None})
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
    )
    assert backend.order == ["creation_rule", "stamp_clear"]
