"""The three-click sequence through the one completion door (ADR-087; one-door arc D0).

Complete → Undo → complete again is the sequence Today's UI produces, and it is the
one the completion-stamping invariant is most exposed to: the stamp must be non-null
exactly when the task is completed, at every step, and the subscribers must be told
about every genuine transition and nothing else.

``tests/unit/services/tasks/test_task_completed_publishers.py`` pins the same door
against a fake, and ``test_status_guarded_update.py`` pins the primitive itself. What
only a database can settle is that the door every click reaches —
``TasksCoreService.update_task``, where Today's complete posts ``completed`` and Undo
posts the prior status — leaves the node in the state the events describe.
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

USER = "user_three_click"

_COMPLETE = TaskUpdateIntent(status=EntityStatus.COMPLETED.value)
_REOPEN = TaskUpdateIntent(status=EntityStatus.ACTIVE.value)


class _CapturingBus:
    """Records what the door publishes; ``publish_async`` is the whole contract."""

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
    ) -> tuple[TasksCoreService, UniversalNeo4jBackend[Task], _CapturingBus]:
        """The one door over one real backend, publishing to one bus."""
        backend = UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"entity_type": "task"}
        )
        bus = _CapturingBus()
        return TasksCoreService(backend=backend, event_bus=bus), backend, bus

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
        core, backend, bus = rig
        uid = await self._seed(backend, "task.three_click_1")

        # Click 1 — complete, through the door Today posts to.
        assert (await core.update_task(uid, _COMPLETE)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        # The writer decides the storage type: an ISO string, as every other writer stores.
        assert props["completion_date"] == date.today().isoformat()

        # Click 2 — Undo, which posts the prior status through the same door.
        assert (await core.update_task(uid, _REOPEN)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ACTIVE.value
        assert "completion_date" not in props, "the reopen left a stamp on an open task"

        # Click 3 — complete again. A genuine second transition, not a re-post.
        assert (await core.update_task(uid, _COMPLETE)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        assert props["completion_date"] == date.today().isoformat()

        assert len(bus.of(TaskCompleted)) == 2, (
            "a reopen in the middle makes the second complete a real one"
        )
        assert len(bus.of(TaskReopened)) == 1

    async def test_a_re_post_with_no_reopen_between_writes_nothing_and_announces_nothing(
        self, rig, neo4j_driver
    ):
        """The contrast case: without the reopen the second complete is a re-post.
        The original stamp survives and nothing is published — the gate IS the
        transition, so no subscriber ever needs a repeat gate.
        """
        core, backend, bus = rig
        uid = await self._seed(backend, "task.three_click_2")

        assert (await core.update_task(uid, _COMPLETE)).is_ok

        # Backdate the stamp before re-completing. Two completes on the same day
        # would leave the same value whether or not the door re-dated it, so a
        # same-day assertion cannot tell a protected stamp from an overwritten one.
        original = "2026-04-02"
        async with neo4j_driver.session() as session:
            await (
                await session.run(
                    "MATCH (n:Entity {uid: $uid}) SET n.completion_date = $stamp",
                    uid=uid,
                    stamp=original,
                )
            ).consume()

        assert (await core.update_task(uid, _COMPLETE)).is_ok

        assert (await self._props(neo4j_driver, uid))["completion_date"] == original, (
            "re-completing an already-completed task re-dated its completion"
        )
        assert len(bus.of(TaskCompleted)) == 1, "a re-post announced a completion"
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

        core, backend, bus = rig
        for iteration in range(5):
            uid = await self._seed(backend, f"task.three_click_race_{iteration}")

            await asyncio.gather(core.update_task(uid, _COMPLETE), core.update_task(uid, _REOPEN))

            props = await self._props(neo4j_driver, uid)
            assert ("completion_date" in props) is (
                props["status"] == EntityStatus.COMPLETED.value
            ), f"stamp invariant broken on iteration {iteration}: {props.get('status')}"

        assert len(bus.of(TaskCompleted)) == 5, "each task may be completed for the first time once"
