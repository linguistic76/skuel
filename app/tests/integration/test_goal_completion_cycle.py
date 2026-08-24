"""Goal completion through the real services, both doors (ADR-087 PR-3 and PR-4).

Goals is the chokepoint with TWO prior-conditional effects, not one: reopening clears
``achieved_date`` *and* resets the 100% progress ``complete_goal`` wrote. Both ride the
same write-time condition, so what only a database can settle is that they fire
together, fire on the right prior, and — under a race — never leave the pair
inconsistent.

The second class covers the OTHER door onto a Goal completion: ``complete_milestone``,
which derives achievement from a progress recompute rather than a status a caller
supplied, and carries its own ``patch_if_prior_not_in`` for the status/stamp pair.
Against a real graph the question there is the one a same-day unit test cannot answer —
whether a repeat really leaves the stored date alone.

Two invariants are asserted at every step:

1. ``achieved_date`` is non-null exactly when the goal is COMPLETED.
2. A goal in a NON-TERMINAL status never carries the 100% a completion wrote. (A
   terminal target — archive / cancel / fail — deliberately keeps it as a historical
   record; only a reopen resets.) A reopen that decided its reset from a pre-read
   could break this: read ACTIVE, miss the reset, land after a concurrent complete.

``tests/unit/services/test_completion_stamping.py`` pins which guard each service
builds, ``tests/unit/services/goals/test_goal_progress_status_guard.py`` the verdicts the
progress writers derive from the prior, and ``test_status_guarded_update.py`` the
primitive itself.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.base import BaseEvent
from core.events.goal_events import GoalAchieved
from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.goal.milestone import Milestone
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_progress_service import GoalsProgressService

USER = "user_goal_cycle"


class _CapturingBus:
    """Records what the chokepoint publishes; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


class _UserContextStub:
    """``complete_milestone`` reads exactly one field off the context it is handed.

    A real ``UserContext`` here would mean building (and keeping in sync) ~250 fields to
    supply a ``user_uid`` — the events it feeds are asserted through the capturing bus.
    """

    user_uid: str = USER


async def _props(
    neo4j_driver: AsyncDriver, uid: str
) -> dict[str, Any]:  # boundary: raw stored node properties
    async with neo4j_driver.session() as session:
        result = await session.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=uid)
        record = await result.single()
        return dict(record["n"]) if record else {}


def _assert_invariants(props: dict[str, Any]) -> None:
    status = EntityStatus(props["status"])
    assert (props.get("achieved_date") is not None) is (status is EntityStatus.COMPLETED), (
        f"stamp invariant broken: status={props.get('status')}, "
        f"achieved_date={props.get('achieved_date')!r}"
    )
    # The progress reset fires on a REOPEN only. A terminal target (archive / cancel /
    # fail) keeps the 100% as a historical record, which is why this half of the pair is
    # scoped to the non-terminal statuses.
    if not status.is_terminal():
        assert props["progress_percentage"] != 100.0, (
            "a reopened goal is carrying the 100% a completion wrote"
        )


async def _backdate(neo4j_driver: AsyncDriver, uid: str, stamp: str) -> None:
    """Move the STORED achievement date into the past.

    Goal stamps ``date.today()``, so two completions on the same day leave the same value
    whether or not the second re-dated it — a same-day assertion cannot tell a protected
    stamp from an overwritten one. Backdating between the two writes is what makes the
    repeat tests (and their RED checks) bite.
    """
    async with neo4j_driver.session() as session:
        await (
            await session.run(
                "MATCH (n:Entity {uid: $uid}) SET n.achieved_date = $stamp",
                uid=uid,
                stamp=stamp,
            )
        ).consume()


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

    async def test_complete_reopen_complete_keeps_both_invariants(self, rig, neo4j_driver):
        service, backend, bus = rig
        uid = await self._seed(backend, "goal.cycle_1")

        assert (await service.complete_goal(uid)).is_ok
        props = await _props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        # The writer decides the storage type: an ISO string, as every other writer stores.
        assert props["achieved_date"] == date.today().isoformat()
        assert props["progress_percentage"] == 100.0
        _assert_invariants(props)

        assert (await service.activate_goal(uid)).is_ok
        props = await _props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ACTIVE.value
        assert "achieved_date" not in props, "the reopen left a stamp on an open goal"
        assert props["progress_percentage"] == 0.0, "the reopen left the goal at 100%"
        _assert_invariants(props)

        assert (await service.complete_goal(uid)).is_ok
        props = await _props(neo4j_driver, uid)
        assert props["achieved_date"] == date.today().isoformat()
        _assert_invariants(props)

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
        await _backdate(neo4j_driver, uid, original)

        assert (await service.complete_goal(uid)).is_ok
        props = await _props(neo4j_driver, uid)
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

        props = await _props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ARCHIVED.value
        assert "achieved_date" not in props
        assert props["progress_percentage"] == 100.0
        _assert_invariants(props)

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

            props = await _props(neo4j_driver, uid)
            _assert_invariants(props)


@pytest.mark.asyncio
class TestMilestoneCompletionCycle:
    """``GoalsProgressService.complete_milestone`` against a real graph (ADR-087 PR-4).

    The progress writers reach a completion by a different route than the chokepoint:
    nobody hands them ``status=completed``: they derive it from the recompute and then
    carry the status/stamp pair as one prior-conditional patch. A real database is what
    settles that the pair lands together, that the ISO storage shape matches every other
    writer's, and — with the stored stamp backdated in between — that a repeat really
    leaves it alone rather than merely writing today over today.
    """

    @pytest_asyncio.fixture
    async def rig(
        self, neo4j_driver: AsyncDriver, clean_neo4j: None
    ) -> tuple[GoalsProgressService, GoalsBackend, _CapturingBus]:
        # ``GoalsBackend``, not the bare universal backend the class above uses:
        # ``complete_milestone`` reads through ``get_goal``, which is a REAL method on the
        # domain backend (a ``get_or_fail`` wrapper), not one of the ``__getattr__``
        # aliases — a universal backend raises AttributeError on it.
        backend = GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
        bus = _CapturingBus()
        return GoalsProgressService(backend=backend, event_bus=bus), backend, bus

    async def _seed(self, backend: GoalsBackend, uid: str) -> str:
        created = await backend.create(
            Goal(
                uid=uid,
                user_uid=USER,
                title="milestone cycle",
                status=EntityStatus.ACTIVE,
                measurement_type=MeasurementType.MILESTONE,
                progress_percentage=50.0,
                milestones=(
                    Milestone(uid="m0", title="first", is_completed=True),
                    Milestone(uid="m1", title="second"),
                ),
            )
        )
        assert created.is_ok
        return uid

    async def test_the_last_milestone_completes_the_goal(self, rig, neo4j_driver):
        service, backend, bus = rig
        uid = await self._seed(backend, "goal.milestone_1")

        result = await service.complete_milestone(uid, 1, _UserContextStub())
        assert result.is_ok

        props = await _props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.COMPLETED.value
        # The writer decides the storage type: an ISO string, like every other writer.
        assert props["achieved_date"] == date.today().isoformat()
        assert props["progress_percentage"] == 100.0
        _assert_invariants(props)

        assert len(bus.of(GoalAchieved)) == 1

    async def test_re_completing_the_last_milestone_does_not_re_date(self, rig, neo4j_driver):
        """The defect the guard closes, with the stamp backdated so the assertion bites.

        Re-completing a milestone of a finished goal is a legal, reachable call. Before
        ADR-087 the writer decided "already achieved" from a status it had read, so a
        concurrent completion between that read and this write produced a fresh
        ``achieved_date`` and a duplicate ``GoalAchieved``.
        """
        service, backend, bus = rig
        uid = await self._seed(backend, "goal.milestone_2")

        assert (await service.complete_milestone(uid, 1, _UserContextStub())).is_ok

        original = "2026-04-02"
        await _backdate(neo4j_driver, uid, original)

        assert (await service.complete_milestone(uid, 1, _UserContextStub())).is_ok

        props = await _props(neo4j_driver, uid)
        assert props["achieved_date"] == original, (
            "re-completing a milestone of a finished goal re-dated its achievement"
        )
        assert props["status"] == EntityStatus.COMPLETED.value
        assert props["progress_percentage"] == 100.0, "the recompute itself still ran"
        _assert_invariants(props)

        assert len(bus.of(GoalAchieved)) == 1, "a repeat is not a second achievement"

    async def test_a_partial_completion_leaves_the_goal_open(self, rig, neo4j_driver):
        """The target half, against the graph: 1 of 2 milestones writes no status at all,
        so nothing can strand a stamp on an open goal."""
        service, backend, bus = rig
        uid = await self._seed(backend, "goal.milestone_3")

        assert (await service.complete_milestone(uid, 0, _UserContextStub())).is_ok

        props = await _props(neo4j_driver, uid)
        assert props["status"] == EntityStatus.ACTIVE.value
        assert "achieved_date" not in props
        assert props["progress_percentage"] == 50.0
        _assert_invariants(props)

        assert bus.of(GoalAchieved) == []
