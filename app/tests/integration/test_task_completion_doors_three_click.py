"""The three-click sequence through the real Task services (ADR-087 PR-2).

Complete → Undo → complete again is the sequence Today's UI produces, and it is the
one the completion-stamping invariant is most exposed to: the stamp must be non-null
exactly when the task is completed, at every step, and the counting subscribers must
be told about all three transitions.

``tests/unit/services/tasks/test_task_completed_publishers.py`` pins the same
sequence against a fake, and ``test_status_guarded_update.py`` pins the primitive
itself. What only a database can settle is the two halves agreeing: that the doors
these clicks actually reach — the cascade complete
(``POST /today/tasks/{uid}/complete``) and the status chokepoint
(``POST /api/tasks/{uid}/status``, where Undo posts the prior status) — leave the
node in the state the events describe.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.base import BaseEvent
from core.events.task_events import TaskCompleted, TaskReopened
from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_progress_service import TasksProgressService

USER = "user_three_click"


class _CapturingBus:
    """Records what the doors publish; ``publish_async`` is the whole contract.

    Everything a door publishes is a ``BaseEvent``, and ``of`` narrows to the subtype
    asked for — so a test that reads ``.is_repeat`` off the result is type-checked
    against the event it actually selected.
    """

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


@pytest.mark.asyncio
class TestThreeClickSequence:
    @pytest_asyncio.fixture
    async def rig(
        self, neo4j_driver: AsyncDriver, clean_neo4j: None
    ) -> tuple[TasksProgressService, TasksCoreService, UniversalNeo4jBackend[Task], _CapturingBus]:
        """The two real services over one real backend, sharing one bus.

        Sharing the bus is the point: the sequence crosses two doors, and the
        assertion is about the events they publish between them.
        """
        backend = UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"entity_type": "task"}
        )
        bus = _CapturingBus()
        return (
            TasksProgressService(backend=backend, event_bus=bus),
            TasksCoreService(backend=backend, event_bus=bus),
            backend,
            bus,
        )

    async def _props(
        self, neo4j_driver: AsyncDriver, uid: str
    ) -> dict[str, Any]:  # boundary: raw stored node properties
        async with neo4j_driver.session() as session:
            result = await session.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=uid)
            record = await result.single()
            return dict(record["n"]) if record else {}

    async def _seed(self, backend: UniversalNeo4jBackend[Task], uid: str) -> str:
        created = await backend.create(
            Task(uid=uid, user_uid=USER, title="three click", status=EntityStatus.ACTIVE)
        )
        assert created.is_ok
        return uid

    async def test_complete_undo_complete_keeps_the_stamp_invariant_and_announces_each(
        self, rig, neo4j_driver
    ):
        progress, core, backend, bus = rig
        uid = await self._seed(backend, "task.three_click_1")

        # Click 1 — complete, through the cascade door Today posts to.
        first = await progress.complete_task_with_cascade(uid, user_context=None)
        assert first.is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        # The writer decides the storage type: an ISO string, as every other writer stores.
        assert props["completion_date"] == date.today().isoformat()

        # Click 2 — Undo, which posts the prior status through the status chokepoint.
        undo = await core.update_task(uid, TaskUpdateIntent(status=EntityStatus.ACTIVE.value))
        assert undo.is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ACTIVE.value
        assert "completion_date" not in props, "the reopen left a stamp on an open task"

        # Click 3 — complete again. A genuine second transition, not a re-post.
        second = await progress.complete_task_with_cascade(uid, user_context=None)
        assert second.is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        assert props["completion_date"] == date.today().isoformat()

        completed = bus.of(TaskCompleted)
        assert len(completed) == 2
        assert [event.is_repeat for event in completed] == [False, False], (
            "a reopen in the middle makes the second complete a real one"
        )
        assert len(bus.of(TaskReopened)) == 1

    async def test_a_repeat_complete_with_no_reopen_between_reports_itself(self, rig, neo4j_driver):
        """The contrast case, and the reason ``is_repeat`` exists: without the reopen
        the second complete is a re-post. The cascade still runs in full (the repair
        path) and the write still happens — but the original stamp survives and the
        event says so, which is what lets a counting subscriber decline it.
        """
        progress, _core, backend, bus = rig
        uid = await self._seed(backend, "task.three_click_2")

        assert (await progress.complete_task_with_cascade(uid, user_context=None)).is_ok

        # Backdate the stamp before re-completing. Two completes on the same day
        # would leave the same value whether or not the door re-dated it, so a
        # same-day assertion cannot tell a protected stamp from an overwritten one —
        # the RED check for this test is exactly that distinction.
        original = "2026-04-02"
        async with neo4j_driver.session() as session:
            await (
                await session.run(
                    "MATCH (n:Entity {uid: $uid}) SET n.completion_date = $stamp",
                    uid=uid,
                    stamp=original,
                )
            ).consume()

        assert (await progress.complete_task_with_cascade(uid, user_context=None)).is_ok

        assert (await self._props(neo4j_driver, uid))["completion_date"] == original, (
            "re-completing an already-completed task re-dated its completion"
        )
        assert [event.is_repeat for event in bus.of(TaskCompleted)] == [False, True]
        assert bus.of(TaskReopened) == []

    async def test_the_undo_races_the_complete_and_the_invariant_still_holds(
        self, rig, neo4j_driver
    ):
        """The client queues these two so they cannot interleave — but the server may
        not assume that. Whichever order they land in, the stamp must be non-null
        exactly when the status is completed, and exactly one writer may claim the
        completion.
        """
        import asyncio

        progress, core, backend, bus = rig
        for iteration in range(5):
            uid = await self._seed(backend, f"task.three_click_race_{iteration}")

            await asyncio.gather(
                progress.complete_task_with_cascade(uid, user_context=None),
                core.update_task(uid, TaskUpdateIntent(status=EntityStatus.ACTIVE.value)),
            )

            props = await self._props(neo4j_driver, uid)
            assert ("completion_date" in props) is (
                props["status"] == EntityStatus.COMPLETED.value
            ), f"stamp invariant broken on iteration {iteration}: {props.get('status')}"

        first_completions = [event for event in bus.of(TaskCompleted) if not event.is_repeat]
        assert len(first_completions) == 5, "each task may be completed for the first time once"
