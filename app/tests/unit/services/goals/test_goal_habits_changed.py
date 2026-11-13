"""A goal's habit membership has one trigger: ``GoalHabitsChanged``.

A HABIT_BASED goal's figure is its owner's supporting habits' average streak, so it
changes whenever a goal gains or loses a habit. Every door that writes or removes a
``(Habit)-[:SUPPORTS_GOAL]->(Goal)`` edge publishes the event, and
``GoalsProgressService.handle_goal_habits_changed`` is its one subscriber. The habit
twin of the contribution tally's ``GoalContributionsChanged``.

Pinned here, without a graph:

- the subscriber recomputes each goal named, and each goal a named habit supports now,
  once each; a goal deleted with the habit that named it is nothing to write;
- goal create and habit create announce only the habit links their batch WROTE;
- habit delete reads the habit's goals BEFORE the delete takes the edges;
- an engagement's deleted habit instance announces the goals it supported;
- the vault: a retraction names the goal on either side of the edge, a re-ingested
  habit or goal is announced, and a vault-written link gets the create doors'
  properties.

The doors end to end, over a real graph, are ``tests/integration/routes/
test_goal_habit_membership_doors.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.bulk_upsert_backend import (
    _CREATE_MARKER,
    build_relationship_template,
    relationship_template_params,
)
from core.events import GoalCreated, GoalHabitsChanged
from core.events.habit_events import HabitCompleted
from core.ingestion.ingestion_types import AuthoredEdge
from core.models.enums.entity_enums import EntityType
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import SUPPORTS_GOAL_LINK_PROPERTIES
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.ingestion.authored_edges import goals_losing_habits
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ps_engagement.ps_engagement_service import PsEngagementService
from core.utils.result_simplified import Errors, Result
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER
from tests.unit.test_goal_habit_create_edges import (
    USER_UID,
    StubBackend,
    make_goal_request,
    make_habit_request,
)

pytestmark = pytest.mark.usefixtures("held_run_clock")


def _announced(bus: InMemoryEventBus) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """Each GoalHabitsChanged the bus saw, as (user_uid, goal_uids, habit_uids)."""
    return [
        (e.user_uid, e.goal_uids, e.habit_uids)
        for e in bus.get_event_history()
        if isinstance(e, GoalHabitsChanged)
    ]


# ============================================================================
# THE SUBSCRIBER
# ============================================================================


def _progress(linked: dict[str, list[str] | None]) -> GoalsProgressService:
    """A progress service whose habit → goals read answers from ``linked`` (``None``
    for a failed read) and whose recompute is recorded."""
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.logger = Mock()

    async def find_linked_goals_for_habit(habit_uid: str, user_uid: str) -> Result[list[str]]:
        goals = linked.get(habit_uid, [])
        if goals is None:
            return Result.fail(Errors.database(message="away", operation="find"))
        return Result.ok(goals)

    backend = Mock()
    backend.find_linked_goals_for_habit = find_linked_goals_for_habit
    service.backend = backend
    service.recompute_habit_figure = AsyncMock(return_value=Result.ok(True))  # type: ignore[method-assign]
    return service


def _recomputed(service: GoalsProgressService) -> list[str]:
    return [c.args[0] for c in service.recompute_habit_figure.await_args_list]  # type: ignore[attr-defined]


@pytest.mark.asyncio
class TestTheSubscriber:
    async def test_each_named_goal_and_each_habits_goal_is_recomputed_once(self) -> None:
        service = _progress({"habit.a": ["goal.1", "goal.2"], "habit.b": ["goal.2"]})

        await service.handle_goal_habits_changed(
            GoalHabitsChanged(
                user_uid=USER_UID,
                goal_uids=("goal.1", "goal.1", "goal.0"),
                habit_uids=("habit.a", "habit.b"),
            )
        )

        assert _recomputed(service) == ["goal.1", "goal.0", "goal.2"]

    async def test_a_habit_whose_goals_cannot_be_read_does_not_stop_the_rest(self) -> None:
        service = _progress({"habit.lost": None, "habit.b": ["goal.2"]})

        await service.handle_goal_habits_changed(
            GoalHabitsChanged(user_uid=USER_UID, habit_uids=("habit.lost", "habit.b"))
        )

        assert _recomputed(service) == ["goal.2"]

    async def test_a_habit_completion_recomputes_the_habits_goals(self) -> None:
        service = _progress({"habit.a": ["goal.1"]})

        await service.handle_habit_completed(
            HabitCompleted(habit_uid="habit.a", user_uid=USER_UID, current_streak=3)
        )

        assert _recomputed(service) == ["goal.1"]

    async def test_a_goal_that_is_gone_is_nothing_to_write(self) -> None:
        """A habit deleted together with its goal (an abandoned engagement) names a
        goal the recompute cannot find: no write, and no error."""
        service = GoalsProgressService.__new__(GoalsProgressService)
        service.logger = Mock()
        backend = Mock()
        backend.recompute_progress_from_linked_habits = AsyncMock(
            return_value=Result.fail(Errors.not_found("Goal", "goal.gone"))
        )
        service.backend = backend

        result = await service.recompute_habit_figure("goal.gone")

        assert result.is_ok
        assert result.value is False


# ============================================================================
# THE CREATE DOORS
# ============================================================================


class _FailingBatch(StubBackend):
    async def create_relationships_batch(self, relationships: object) -> Result[int]:
        self.trace.append("batch_failed")
        return Result.fail(Errors.database(message="batch refused", operation="batch"))


@pytest.mark.asyncio
class TestGoalCreate:
    async def test_a_goal_born_with_habits_announces_itself_after_it_is_created(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = GoalsCoreService(backend=StubBackend(Goal), event_bus=bus)

        created = await core.create_goal(
            make_goal_request(supporting_habit_uids=["habit.a", "habit.b"]), USER_UID
        )

        assert created.is_ok
        assert _announced(bus) == [(USER_UID, (created.value.uid,), ())]
        kinds = [type(e) for e in bus.get_event_history()]
        assert kinds.index(GoalCreated) < kinds.index(GoalHabitsChanged)

    async def test_a_goal_with_no_habit_link_announces_nothing(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = GoalsCoreService(backend=StubBackend(Goal), event_bus=bus)

        await core.create_goal(make_goal_request(supporting_principle_uids=["pr.a"]), USER_UID)

        assert _announced(bus) == []

    async def test_a_failed_batch_announces_nothing(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = GoalsCoreService(backend=_FailingBatch(Goal), event_bus=bus)

        await core.create_goal(make_goal_request(supporting_habit_uids=["habit.a"]), USER_UID)

        assert _announced(bus) == []


@pytest.mark.asyncio
class TestHabitCreate:
    async def test_a_habit_born_linked_announces_the_goals_it_was_linked_to(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = HabitsCoreService(backend=StubBackend(Habit), event_bus=bus)

        created = await core.create_habit(
            make_habit_request(linked_goal_uids=["goal.a", "goal.b", "goal.a"]), USER_UID
        )

        assert created.is_ok
        assert _announced(bus) == [(USER_UID, ("goal.a", "goal.b"), ())]

    async def test_a_failed_batch_announces_nothing(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = HabitsCoreService(backend=_FailingBatch(Habit), event_bus=bus)

        await core.create_habit(make_habit_request(linked_goal_uids=["goal.a"]), USER_UID)

        assert _announced(bus) == []


# ============================================================================
# HABIT DELETE
# ============================================================================


class _DeletableHabits(StubBackend):
    """A habit backend that records the order of the goal read and the delete."""

    def __init__(self, goals: list[str], *, delete_ok: bool = True) -> None:
        super().__init__(Habit)
        self._goals = goals
        self._delete_ok = delete_ok

    async def get_goal_links_for_habits(
        self, habit_uids: list[str]
    ) -> Result[dict[str, list[str]]]:
        self.trace.append("goals_read")
        return Result.ok({uid: list(self._goals) for uid in habit_uids if self._goals})

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        self.trace.append(f"deleted(cascade={cascade})")
        if not self._delete_ok:
            return Result.fail(Errors.database(message="away", operation="delete"))
        return Result.ok(True)


@pytest.mark.asyncio
class TestHabitDelete:
    async def test_the_goals_are_read_before_the_delete_and_announced_after(self) -> None:
        backend = _DeletableHabits(["goal.a", "goal.b"])
        bus = InMemoryEventBus(capture_history=True)
        core = HabitsCoreService(backend=backend, event_bus=bus)

        result = await core.delete("habit.x", cascade=True)

        assert result.is_ok
        assert backend.trace == ["goals_read", "deleted(cascade=True)"]
        assert _announced(bus) == [(USER_UID, ("goal.a", "goal.b"), ())]

    async def test_a_habit_supporting_no_goal_announces_nothing(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = HabitsCoreService(backend=_DeletableHabits([]), event_bus=bus)

        await core.delete("habit.x", cascade=True)

        assert _announced(bus) == []

    async def test_a_failed_delete_announces_nothing(self) -> None:
        bus = InMemoryEventBus(capture_history=True)
        core = HabitsCoreService(
            backend=_DeletableHabits(["goal.a"], delete_ok=False), event_bus=bus
        )

        result = await core.delete("habit.x", cascade=True)

        assert result.is_error
        assert _announced(bus) == []


# ============================================================================
# PATHSTEP ENGAGEMENT — a deleted habit instance
# ============================================================================


@pytest.mark.asyncio
async def test_an_engagements_deleted_habit_announces_the_goals_it_supported() -> None:
    """A spawned habit the learner linked to a goal, then discarded or abandoned with its
    engagement: the goal loses a habit. Contribution goals stay on their own event."""
    bus = InMemoryEventBus(capture_history=True)
    service = PsEngagementService.__new__(PsEngagementService)
    service._event_bus = bus
    service.logger = Mock()

    await service._announce_goals(USER_UID, ["goal.task"], ["goal.habit", "goal.habit"])

    assert _announced(bus) == [(USER_UID, ("goal.habit",), ())]


# ============================================================================
# THE VAULT
# ============================================================================


class TestRetraction:
    def test_a_habit_files_dropped_goal_and_a_goal_files_dropped_habit_name_the_goal(
        self,
    ) -> None:
        dropped = [
            AuthoredEdge(RelationshipName.SUPPORTS_GOAL, "outgoing", "goal.from-habit-file"),
            AuthoredEdge(RelationshipName.SUPPORTS_GOAL, "incoming", "habit.from-goal-file"),
            AuthoredEdge(RelationshipName.CONTRIBUTES_TO_GOAL, "outgoing", "goal.contribution"),
        ]

        assert goals_losing_habits(dropped, "goal.the-file") == [
            "goal.from-habit-file",
            "goal.the-file",
        ]


class _FakeWriteBackend:
    async def apply_task_creation_due_dates(self, uids: list[str]) -> int:
        return 0

    async def clear_completion_stamps(self, field_name: str, uids: list[str]) -> int:
        return 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "expected"),
    [
        (EntityType.HABIT, ((), ("habit.v",))),
        (EntityType.GOAL, (("goal.v",), ())),
    ],
)
async def test_a_reingested_habit_or_goal_is_announced(
    entity_type: EntityType, expected: tuple[tuple[str, ...], tuple[str, ...]]
) -> None:
    """A re-synced habit may have gained ``connections.supports_goal``, a re-synced goal
    ``connections.supporting_habits``: the recompute counts graph state, so each is
    announced and an unchanged one costs a recount."""
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService

    bus = InMemoryEventBus(capture_history=True)
    service = UnifiedIngestionService(
        write_backend=_FakeWriteBackend(),  # type: ignore[arg-type]
        bulk_backend=object(),  # type: ignore[arg-type]
        default_user_uid=INGESTION_TEST_OWNER,
        event_bus=bus,
    )
    uid = "habit.v" if entity_type is EntityType.HABIT else "goal.v"

    await service._apply_primitive_parity(
        entity_type, [{"uid": uid, "user_uid": USER_UID, "status": "active"}], {uid: "active"}
    )

    assert _announced(bus) == [(USER_UID, *expected)]


class TestAVaultLinkGetsTheCreateDoorsProperties:
    """A ``SUPPORTS_GOAL`` link a vault file creates carries ``weight`` and
    ``essentiality``, as every app door writes it; an edge already there is left alone."""

    @pytest.mark.parametrize(
        ("entity_type", "field"),
        [
            (EntityType.HABIT, "connections.supports_goal"),
            (EntityType.GOAL, "connections.supporting_habits"),
            (EntityType.GOAL, "connections.supporting_principles"),
            (EntityType.PRINCIPLE, "connections.supports_goal"),
        ],
    )
    def test_every_supports_goal_field_declares_them(
        self, entity_type: EntityType, field: str
    ) -> None:
        config = ENTITY_CONFIGS[entity_type].relationship_config or {}
        assert config[field]["create_properties"] == dict(SUPPORTS_GOAL_LINK_PROPERTIES)

    def test_the_template_sets_them_on_create_only(self) -> None:
        config = ENTITY_CONFIGS[EntityType.HABIT].relationship_config or {}
        index = list(config).index("connections.supports_goal")

        template = build_relationship_template("Habit", "Entity", config).template
        params = relationship_template_params(config)

        set_lines = [line.strip() for line in template.splitlines() if "create_properties" in line]
        assert set_lines == [
            f"ON CREATE SET _r.{_CREATE_MARKER} = true, _r += $create_properties_{index}"
        ]
        assert params == {f"create_properties_{index}": dict(SUPPORTS_GOAL_LINK_PROPERTIES)}
