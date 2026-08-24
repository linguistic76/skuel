"""The Goal complete → reopen → complete cycle through the real service (ADR-087 PR-3).

Goals is the chokepoint with TWO prior-conditional effects, not one: reopening clears
``achieved_date`` *and* resets the 100% progress ``complete_goal`` wrote. Both now ride
the same write-time condition, so what only a database can settle is that they fire
together, fire on the right prior, and — under a race — never leave the pair
inconsistent.

Two invariants are asserted at every step:

1. ``achieved_date`` is non-null exactly when the goal is COMPLETED.
2. A goal in a NON-TERMINAL status never carries the 100% a completion wrote. (A
   terminal target — archive / cancel / fail — deliberately keeps it as a historical
   record; only a reopen resets.) A reopen that decided its reset from a pre-read
   could break this: read ACTIVE, miss the reset, land after a concurrent complete.

``tests/unit/services/test_completion_stamping.py`` pins which guard the service builds;
``test_status_guarded_update.py`` pins the primitive itself.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.base import BaseEvent
from core.events.goal_events import GoalAchieved
from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.services.goals.goals_core_service import GoalsCoreService

USER = "user_goal_cycle"


class _CapturingBus:
    """Records what the chokepoint publishes; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


@pytest.mark.asyncio
class TestGoalCompletionCycle:
    @pytest_asyncio.fixture
    async def rig(
        self, neo4j_driver: AsyncDriver, clean_neo4j: None
    ) -> tuple[GoalsCoreService, UniversalNeo4jBackend[Goal], _CapturingBus]:
        backend = UniversalNeo4jBackend[Goal](
            neo4j_driver, "Entity", Goal, default_filters={"entity_type": "goal"}
        )
        bus = _CapturingBus()
        return GoalsCoreService(backend=backend, event_bus=bus), backend, bus

    async def _props(
        self, neo4j_driver: AsyncDriver, uid: str
    ) -> dict[str, Any]:  # boundary: raw stored node properties
        async with neo4j_driver.session() as session:
            result = await session.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=uid)
            record = await result.single()
            return dict(record["n"]) if record else {}

    async def _seed(
        self, backend: UniversalNeo4jBackend[Goal], uid: str, progress: float = 30.0
    ) -> str:
        created = await backend.create(
            Goal(
                uid=uid,
                user_uid=USER,
                title="cycle",
                status=EntityStatus.ACTIVE,
                progress_percentage=progress,
            )
        )
        assert created.is_ok
        return uid

    def _assert_invariants(self, props: dict[str, Any]) -> None:
        status = EntityStatus(props["status"])
        assert (props.get("achieved_date") is not None) is (status is EntityStatus.COMPLETED), (
            f"stamp invariant broken: status={props.get('status')}, "
            f"achieved_date={props.get('achieved_date')!r}"
        )
        # The progress reset fires on a REOPEN only. A terminal target (archive /
        # cancel / fail) keeps the 100% as a historical record, which is why this
        # half of the pair is scoped to the non-terminal statuses.
        if not status.is_terminal():
            assert props["progress_percentage"] != 100.0, (
                "a reopened goal is carrying the 100% a completion wrote"
            )

    async def test_complete_reopen_complete_keeps_both_invariants(self, rig, neo4j_driver):
        service, backend, bus = rig
        uid = await self._seed(backend, "goal.cycle_1")

        assert (await service.complete_goal(uid)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        # The writer decides the storage type: an ISO string, as every other writer stores.
        assert props["achieved_date"] == date.today().isoformat()
        assert props["progress_percentage"] == 100.0
        self._assert_invariants(props)

        assert (await service.activate_goal(uid)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ACTIVE.value
        assert "achieved_date" not in props, "the reopen left a stamp on an open goal"
        assert props["progress_percentage"] == 0.0, "the reopen left the goal at 100%"
        self._assert_invariants(props)

        assert (await service.complete_goal(uid)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["achieved_date"] == date.today().isoformat()
        self._assert_invariants(props)

        assert len(bus.of(GoalAchieved)) == 2, (
            "a reopen in the middle makes the second complete a real achievement"
        )

    async def test_a_repeat_complete_does_not_re_date(self, rig, neo4j_driver):
        """Goal stamps ``date.today()``, so two completes on the same day leave the same
        value whether or not the door re-dated it — a same-day assertion cannot tell a
        protected stamp from an overwritten one. Backdating the stored stamp between the
        two writes is what makes this test bite (and what makes its RED check bite)."""
        service, backend, bus = rig
        uid = await self._seed(backend, "goal.cycle_2")

        assert (await service.complete_goal(uid)).is_ok

        original = "2026-04-02"
        async with neo4j_driver.session() as session:
            await (
                await session.run(
                    "MATCH (n:Entity {uid: $uid}) SET n.achieved_date = $stamp",
                    uid=uid,
                    stamp=original,
                )
            ).consume()

        assert (await service.complete_goal(uid)).is_ok
        props = await self._props(neo4j_driver, uid)
        assert props["achieved_date"] == original, (
            "re-completing an already-completed goal re-dated its achievement"
        )
        assert len(bus.of(GoalAchieved)) == 1, "a re-post is not a second achievement"

    async def test_archiving_a_completed_goal_keeps_its_historical_progress(
        self, rig, neo4j_driver
    ):
        """A terminal target is not a reopen. The stamp still clears (the invariant is
        about COMPLETED, not about terminality), but the 100% stays as a record."""
        service, backend, _bus = rig
        uid = await self._seed(backend, "goal.cycle_3")

        assert (await service.complete_goal(uid)).is_ok
        assert (await service.archive_goal(uid)).is_ok

        props = await self._props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ARCHIVED.value
        assert "achieved_date" not in props
        assert props["progress_percentage"] == 100.0
        self._assert_invariants(props)

    async def test_a_reopen_racing_a_complete_leaves_a_consistent_goal(self, rig, neo4j_driver):
        """Whichever order the two land in, both invariants must hold. Under the old
        read-then-write shape the reopen decided its reset from a status it read before
        the complete landed, which is exactly how an ACTIVE goal ends up at 100%."""
        service, backend, _bus = rig
        for iteration in range(5):
            uid = await self._seed(backend, f"goal.cycle_race_{iteration}")

            await asyncio.gather(
                service.complete_goal(uid),
                service.update_goal(uid, GoalUpdateIntent(status=EntityStatus.ACTIVE.value)),
            )

            props = await self._props(neo4j_driver, uid)
            self._assert_invariants(props)
