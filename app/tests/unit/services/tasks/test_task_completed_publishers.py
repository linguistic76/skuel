"""The completion-transition publishes at the Task write doors.

Every door to COMPLETED publishes ``TaskCompleted`` (PR-4 of the arc), and the
status chokepoint also publishes the mirror ``TaskReopened`` on a transition
back OUT (PR-6) — the signal that lets a subscriber hold "tasks completed" as a
recomputed number instead of a counter that can only rise.


Before this pass only the explicit-complete cascade did. The status chokepoint
(``POST /api/tasks/{uid}/status`` → ``update_task``) published ``TaskUpdated``
only, and ``complete_tasks_bulk`` published ``TasksBulkCompleted`` only — so a
task completed from a status control or a bulk selection silently skipped goal
progress, PS engagement auto-complete, duration calibration, analytics and
context invalidation.

Both new publishes are **transition-gated**, which is why both are always
``is_repeat=False``: the gate IS the transition, so a re-post of ``completed``
never reaches them. Only the explicit-complete cascade — deliberately preserved
as a repair path — reports a repeat.

The publisher side of ``is_repeat`` for that cascade lives in
``tests/unit/test_tasks_progress_service.py``; the subscriber side of the whole
contract lives in ``tests/unit/test_task_completed_is_repeat.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.events.task_events import TaskCompleted, TaskReopened, TasksBulkCompleted
from core.models.enums.entity_enums import EntityStatus
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.tasks.tasks_core_service import TasksCoreService
from core.utils.result_simplified import Errors, Result
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend

USER = "user_pr4"


class _RecordingBus:
    """Captures published events; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish_async(self, event: Any) -> None:
        self.events.append(event)

    def of(self, event_type: type) -> list[Any]:
        return [event for event in self.events if isinstance(event, event_type)]


def _core_service(
    current: Task, updated: Task
) -> tuple[TasksCoreService, _RecordingBus, Mock, StatusGuardedWriteRecorder]:
    """A faithful fake: reads return domain models, as the real backend does after
    ``from_neo4j_node`` (correction #12 — the shared ``mock_backend`` fixture returns
    raw dicts, which is not the writer shape), and the guarded write answers with the
    prior it would have read under the lock (ADR-087). The verdicts under test are
    derived from THAT prior now, not from ``backend.get``."""
    backend, recorder = guarded_backend(current, updated)
    bus = _RecordingBus()
    return TasksCoreService(backend=backend, event_bus=bus), bus, backend, recorder


# ---------------------------------------------------------------------------
# 1. The status chokepoint — update_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpdateTaskPublishesTaskCompleted:
    async def test_a_genuine_transition_publishes_exactly_one_event(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))

        assert result.is_ok
        completed = bus.of(TaskCompleted)
        assert len(completed) == 1
        assert completed[0].task_uid == "task_1"
        assert completed[0].user_uid == USER
        assert completed[0].is_repeat is False

    async def test_the_event_carries_analytics_context_without_extra_queries(self) -> None:
        """``was_overdue`` and ``completion_time_seconds`` come from the models
        already in hand — the post-write task, not a second read."""
        yesterday = date.today() - timedelta(days=1)
        current = Task(
            uid="task_1",
            user_uid=USER,
            title="t",
            status=EntityStatus.ACTIVE,
            due_date=yesterday,
            actual_minutes=45,
        )
        updated = Task(
            uid="task_1",
            user_uid=USER,
            title="t",
            status=EntityStatus.COMPLETED,
            due_date=yesterday,
            actual_minutes=45,
        )
        service, bus, backend, _recorder = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))

        assert result.is_ok
        event = bus.of(TaskCompleted)[0]
        assert event.was_overdue is True
        assert event.completion_time_seconds == 45 * 60
        # Stronger than before: a status-only update now reads NOTHING up front —
        # the prior rides back on the write itself (ADR-087).
        backend.get.assert_not_awaited()

    async def test_a_zero_duration_is_reported_not_dropped(self) -> None:
        """``is not None``, not truthiness — 0 is a legal reported duration."""
        current = Task(
            uid="task_1",
            user_uid=USER,
            title="t",
            status=EntityStatus.ACTIVE,
            actual_minutes=0,
        )
        updated = Task(
            uid="task_1",
            user_uid=USER,
            title="t",
            status=EntityStatus.COMPLETED,
            actual_minutes=0,
        )
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))

        assert result.is_ok
        assert bus.of(TaskCompleted)[0].completion_time_seconds == 0

    async def test_reposting_completed_publishes_nothing(self) -> None:
        """The gate is the transition, so a repeat never reaches the publish —
        which is why this door never needs ``is_repeat=True``."""
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))

        assert result.is_ok
        assert bus.of(TaskCompleted) == []

    async def test_a_non_status_write_publishes_nothing(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        updated = Task(uid="task_1", user_uid=USER, title="new", status=EntityStatus.ACTIVE)
        service, bus, backend, _recorder = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(title="new"))

        assert result.is_ok
        assert bus.of(TaskCompleted) == []
        backend.get.assert_not_awaited()

    async def test_a_lateral_status_write_publishes_nothing(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.PAUSED)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="paused"))

        assert result.is_ok
        assert bus.of(TaskCompleted) == []

    async def test_a_reopen_publishes_no_completion(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="active"))

        assert result.is_ok
        assert bus.of(TaskCompleted) == []

    async def test_a_failed_write_publishes_nothing(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        service, bus, backend, _recorder = _core_service(current, updated)
        backend.update_with_status_guard = AsyncMock(
            return_value=Result.fail(Errors.database("update_with_status_guard", "boom"))
        )

        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))

        assert result.is_error
        assert bus.of(TaskCompleted) == []


# ---------------------------------------------------------------------------
# 1b. The mirror transition — update_task publishes TaskReopened (PR-6)
# ---------------------------------------------------------------------------


def test_task_reopened_reaches_the_derived_event_registry() -> None:
    """``EVENT_REGISTRY`` is derived by comprehension over imported subclasses,
    so a new module that ``core/events/__init__.py`` never imports is invisible.
    ``TaskReopened`` lives beside ``TaskCompleted``, but assert the outcome, not
    the file it happens to sit in."""
    from core.events import EVENT_REGISTRY

    assert EVENT_REGISTRY[TaskReopened.event_type] is TaskReopened
    assert TaskReopened.event_type == "task.reopened"


@pytest.mark.asyncio
class TestUpdateTaskPublishesTaskReopened:
    async def test_a_genuine_reopen_publishes_exactly_one_event(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="active"))

        assert result.is_ok
        reopened = bus.of(TaskReopened)
        assert len(reopened) == 1
        assert reopened[0].task_uid == "task_1"
        assert reopened[0].user_uid == USER

    async def test_a_completion_publishes_no_reopen(self) -> None:
        """The two gates are mutually exclusive — one write is never both."""
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))

        assert result.is_ok
        assert len(bus.of(TaskCompleted)) == 1
        assert bus.of(TaskReopened) == []

    async def test_a_lateral_write_on_an_open_task_publishes_no_reopen(self) -> None:
        """Transition-gated in both directions: leaving an open task open is not
        a reopen, so a status control that never touched ``completed`` is silent."""
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.PAUSED)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(status="paused"))

        assert result.is_ok
        assert bus.of(TaskReopened) == []

    async def test_a_non_status_write_publishes_no_reopen(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        updated = Task(uid="task_1", user_uid=USER, title="new", status=EntityStatus.COMPLETED)
        service, bus, _, _ = _core_service(current, updated)

        result = await service.update_task("task_1", TaskUpdateIntent(title="new"))

        assert result.is_ok
        assert bus.of(TaskReopened) == []

    async def test_a_failed_write_publishes_no_reopen(self) -> None:
        current = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        service, bus, backend, _recorder = _core_service(current, updated)
        backend.update_with_status_guard = AsyncMock(
            return_value=Result.fail(Errors.database("update_with_status_guard", "boom"))
        )

        result = await service.update_task("task_1", TaskUpdateIntent(status="active"))

        assert result.is_error
        assert bus.of(TaskReopened) == []

    async def test_undo_after_a_complete_is_one_completion_then_one_reopen(self) -> None:
        """The Today's Undo sequence PR-6 exists for: PR-5 made Undo post the
        prior status through this chokepoint, so complete → Undo → complete is
        two real transitions INTO completed. The counter subscriber can only
        stay honest across that because the reopen in the middle is announced."""
        open_task = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        done_task = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)

        service, bus, _backend, recorder = _core_service(open_task, done_task)

        # complete
        assert (await service.update_task("task_1", TaskUpdateIntent(status="completed"))).is_ok

        # Undo → reopen
        recorder.set_state(done_task, open_task)
        assert (await service.update_task("task_1", TaskUpdateIntent(status="active"))).is_ok

        # complete again
        recorder.set_state(open_task, done_task)
        assert (await service.update_task("task_1", TaskUpdateIntent(status="completed"))).is_ok

        assert len(bus.of(TaskCompleted)) == 2
        assert len(bus.of(TaskReopened)) == 1


# ---------------------------------------------------------------------------
# 2. The bulk door — complete_tasks_bulk fans out per transitioning row
# ---------------------------------------------------------------------------


def _bulk_service(rows: dict[str, Task | None]) -> tuple[TasksCoreService, _RecordingBus, Mock]:
    """``rows`` maps uid → the stored task, or ``None`` for a row whose read fails."""

    async def get_by_uid(uid: str) -> Result[Any]:
        task = rows.get(uid)
        if task is None:
            return Result.fail(Errors.database("get", "transient read failure"))
        return Result.ok(task)

    async def update_by_uid(uid: str, changes: dict[str, Any]) -> Result[Any]:
        return Result.ok(rows[uid])

    backend = Mock()
    backend.get = AsyncMock(side_effect=get_by_uid)
    backend.update = AsyncMock(side_effect=update_by_uid)
    bus = _RecordingBus()
    return TasksCoreService(backend=backend, event_bus=bus), bus, backend


@pytest.mark.asyncio
class TestCompleteTasksBulkFansOut:
    async def test_only_the_transitioning_rows_get_a_task_completed(self) -> None:
        rows = {
            "task_active": Task(
                uid="task_active",
                user_uid=USER,
                title="t",
                status=EntityStatus.ACTIVE,
                actual_minutes=30,
            ),
            "task_done": Task(
                uid="task_done",
                user_uid=USER,
                title="t",
                status=EntityStatus.COMPLETED,
                completion_date=date(2026, 8, 1),
            ),
        }
        service, bus, _ = _bulk_service(rows)

        result = await service.complete_tasks_bulk(["task_active", "task_done"], USER)

        assert result.is_ok
        assert result.value == 2
        completed = bus.of(TaskCompleted)
        assert [event.task_uid for event in completed] == ["task_active"], (
            "an already-completed row published a completion it did not make"
        )
        assert completed[0].is_repeat is False, "a bulk call is not a repair path"
        assert completed[0].completion_time_seconds == 30 * 60

    async def test_the_batch_event_survives_alongside_the_per_row_events(self) -> None:
        """``TasksBulkCompleted`` classifies the batch (size, time of day), which
        per-row events cannot express — so both are published."""
        rows = {
            "task_a": Task(uid="task_a", user_uid=USER, title="a", status=EntityStatus.ACTIVE),
            "task_b": Task(uid="task_b", user_uid=USER, title="b", status=EntityStatus.ACTIVE),
        }
        service, bus, _ = _bulk_service(rows)

        result = await service.complete_tasks_bulk(["task_a", "task_b"], USER)

        assert result.is_ok
        assert [event.task_uid for event in bus.of(TaskCompleted)] == ["task_a", "task_b"]
        batch = bus.of(TasksBulkCompleted)
        assert len(batch) == 1
        assert batch[0].task_uids == ["task_a", "task_b"]
        assert batch[0].count == 2

    async def test_an_unreadable_row_publishes_nothing_and_is_not_named(self) -> None:
        """A failed read is skipped, and the batch event names the rows actually
        written — a slice of the input would name the wrong ones."""
        rows: dict[str, Task | None] = {
            "task_bad": None,
            "task_good": Task(
                uid="task_good", user_uid=USER, title="g", status=EntityStatus.ACTIVE
            ),
        }
        service, bus, _ = _bulk_service(rows)

        result = await service.complete_tasks_bulk(["task_bad", "task_good"], USER)

        assert result.is_ok
        assert result.value == 1
        assert [event.task_uid for event in bus.of(TaskCompleted)] == ["task_good"]
        assert bus.of(TasksBulkCompleted)[0].task_uids == ["task_good"]

    async def test_an_all_completed_batch_publishes_no_completions(self) -> None:
        rows = {
            "task_done": Task(
                uid="task_done",
                user_uid=USER,
                title="t",
                status=EntityStatus.COMPLETED,
                completion_date=date(2026, 8, 1),
            )
        }
        service, bus, _ = _bulk_service(rows)

        result = await service.complete_tasks_bulk(["task_done"], USER)

        assert result.is_ok
        assert bus.of(TaskCompleted) == []
        assert len(bus.of(TasksBulkCompleted)) == 1


# ---------------------------------------------------------------------------
# 3. No double-publish: the explicit-complete cascade never re-enters update_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_cascade_path_still_publishes_exactly_one_task_completed() -> None:
    """``complete_task_with_cascade`` writes through the *generic* CRUD
    (``self.update``), not ``update_task``, so PR-4's chokepoint publish cannot
    double up with the cascade's own."""
    from core.services.tasks.tasks_progress_service import TasksProgressService

    task = Task(uid="task_c", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
    stored = task.to_dto().to_dict()
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(stored))
    backend.update = AsyncMock(return_value=Result.ok(stored))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    bus = _RecordingBus()
    service = TasksProgressService(backend=backend, event_bus=bus)

    result = await service.complete_task_with_cascade("task_c", user_context=None)

    assert result.is_ok
    assert len(bus.of(TaskCompleted)) == 1
