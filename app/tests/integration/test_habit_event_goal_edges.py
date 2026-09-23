"""Real-Neo4j: habit-scheduled events contribute to every goal their habit supports.

``HabitEventScheduler`` used to stamp the habit's FIRST goal on ``event.fulfills_goal_uid``
— a field ``EventDTO`` does not declare, hidden from mypy by a ``type: ignore`` — and park
the full list in ``metadata["supports_goals"]``, which no reader consults. Nothing on the
create path wrote ``(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)``, the edge every Event→Goal
reader traverses. Worse, bootstrap built the scheduler with no relationship service, so
the goal branch never ran in production at all.

The scheduler now reads the habit's goals and sets them on the entity as
``contributes_to_goal_uids``; the Events create primitive turns each into an edge, through
the owner/kind/existence admission, BEFORE it publishes ``CalendarEventCreated``.

Everything here goes through production writers: the goals and the habit's
``SUPPORTS_GOAL`` edges are created by ``GoalsCoreService.create_goal`` /
``HabitsCoreService.create_habit``, the goals are read back by the real Habits
``UnifiedRelationshipService``, and the events persist through the real ``EventsService``.
Ordering is asserted by querying the graph from INSIDE a ``CalendarEventCreated``
subscriber — the moment the context rebuild would read it.
"""

from datetime import date, time, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import (
    EventsBackend,
    GoalsBackend,
    HabitsBackend,
)
from core.events.calendar_event_events import CalendarEventCreated
from core.models.enums import Domain, MeasurementType, Priority, RecurrencePattern
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import HABITS_CONFIG
from core.services.events_service import EventsService
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.habit_event_scheduler import EventSchedulingConfig, HabitEventScheduler
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.relationships.unified_relationship_service import (
    UnifiedRelationshipService,
)
from core.services.user import UserContext

USER = "user_test_habit_event_goals"
OTHER_USER = "user_test_habit_event_goals_victim"
CTG = RelationshipName.CONTRIBUTES_TO_GOAL.value


class _Inert:
    """Collaborator stub for facade construction — never exercised by create."""

    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self


@pytest_asyncio.fixture
async def event_bus():
    return InMemoryEventBus(capture_history=True)


@pytest_asyncio.fixture
async def users(neo4j_driver, clean_neo4j):
    async with neo4j_driver.session() as session:
        for uid in (USER, OTHER_USER):
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", uid=uid
            )


@pytest_asyncio.fixture
async def goals_service(neo4j_driver, clean_neo4j, event_bus):
    backend = GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
    return GoalsCoreService(backend=backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def habits_backend(neo4j_driver, clean_neo4j):
    return HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)


@pytest_asyncio.fixture
async def habits_service(habits_backend, event_bus):
    return HabitsCoreService(backend=habits_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def events_backend(neo4j_driver, clean_neo4j):
    return EventsBackend(neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY)


@pytest_asyncio.fixture
async def events_service(events_backend, event_bus):
    return EventsService(
        backend=events_backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


@pytest_asyncio.fixture
async def scheduler(habits_backend, events_service):
    return HabitEventScheduler(
        habits_backend=habits_backend,
        events_service=events_service,
        relationship_service=UnifiedRelationshipService(
            backend=habits_backend, config=HABITS_CONFIG
        ),
        config=EventSchedulingConfig(schedule_ahead_days=2),
    )


async def _goal(goals_service, title: str, user_uid: str = USER) -> str:
    result = await goals_service.create_goal(
        GoalCreateRequest(
            title=title,
            domain=Domain.TECH,
            priority=Priority.HIGH,
            measurement_type=MeasurementType.NUMERIC,
            target_value=10.0,
        ),
        user_uid,
    )
    assert result.is_ok, f"create_goal failed: {result.error}"
    return result.value.uid


async def _habit_supporting(habits_service, goal_uids: list[str]) -> str:
    result = await habits_service.create_habit(
        HabitCreateRequest(
            title="Read twenty pages",
            recurrence_pattern=RecurrencePattern.DAILY,
            target_days_per_week=7,
            linked_goal_uids=goal_uids,
        ),
        USER,
    )
    assert result.is_ok, f"create_habit failed: {result.error}"
    return result.value.uid


async def _goal_edges(neo4j_driver, event_uid: str) -> set[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (:Event {{uid: $uid}})-[:{CTG}]->(g:Goal) RETURN g.uid AS goal",
            uid=event_uid,
        )
        return {record["goal"] async for record in result}


def _record_goal_edges_at_publish(event_bus, neo4j_driver) -> dict[str, set[str]]:
    """What a ``CalendarEventCreated`` subscriber sees in the graph at publish time."""
    seen: dict[str, set[str]] = {}

    async def _on_created(event: CalendarEventCreated) -> None:
        seen[event.event_uid] = await _goal_edges(neo4j_driver, event.event_uid)

    event_bus.subscribe(CalendarEventCreated, _on_created)
    return seen


@pytest.mark.asyncio
class TestScheduledEventsContributeToTheHabitsGoals:
    async def test_every_scheduled_event_gets_one_edge_per_goal_before_it_is_announced(
        self, users, goals_service, habits_service, scheduler, event_bus, neo4j_driver
    ) -> None:
        goals = {await _goal(goals_service, "Fluency"), await _goal(goals_service, "Reading list")}
        habit_uid = await _habit_supporting(habits_service, sorted(goals))
        seen = _record_goal_edges_at_publish(event_bus, neo4j_driver)

        result = await scheduler.schedule_events_for_habit(
            habit_uid, UserContext(user_uid=USER), auto_create=True
        )

        assert result.is_ok, f"schedule failed: {result.error}"
        event_uids = [dto.uid for dto in result.value]
        assert event_uids, "the scheduler created no events"
        for event_uid in event_uids:
            assert await _goal_edges(neo4j_driver, event_uid) == goals, (
                "a habit-scheduled event does not contribute to its habit's goals"
            )
            assert seen.get(event_uid) == goals, (
                "CalendarEventCreated was published before the goal edges existed — the "
                "context rebuild it triggers would cache the event as goal-less"
            )

    async def test_the_edges_are_visible_to_the_batch_reader(
        self, users, goals_service, habits_service, scheduler, events_backend
    ) -> None:
        """``get_goal_links_for_events`` feeds ``enrich_events_with_goal_links`` — the
        direction proof: an edge written backwards reads back empty here."""
        goals = {await _goal(goals_service, "Fluency"), await _goal(goals_service, "Reading list")}
        habit_uid = await _habit_supporting(habits_service, sorted(goals))

        result = await scheduler.schedule_events_for_habit(
            habit_uid, UserContext(user_uid=USER), auto_create=True
        )
        event_uid = result.value[0].uid

        links = await events_backend.get_goal_links_for_events([event_uid])
        assert links.is_ok, f"get_goal_links_for_events failed: {links.error}"
        assert set(links.value.get(event_uid, [])) == goals

    async def test_streak_maintenance_events_contribute_too(
        self, users, goals_service, habits_service, scheduler, neo4j_driver
    ) -> None:
        goals = {await _goal(goals_service, "Fluency"), await _goal(goals_service, "Reading list")}
        habit_uid = await _habit_supporting(habits_service, sorted(goals))
        context = UserContext(
            user_uid=USER, habit_streaks={habit_uid: 5}, at_risk_habits=[habit_uid]
        )

        result = await scheduler.schedule_streak_maintenance(context, auto_create=True)

        assert result.is_ok, f"maintenance failed: {result.error}"
        assert result.value, "no maintenance event was created"
        assert await _goal_edges(neo4j_driver, result.value[0].uid) == goals

    async def test_the_goal_list_is_not_a_node_property_or_metadata(
        self, users, goals_service, habits_service, scheduler, neo4j_driver
    ) -> None:
        goal = await _goal(goals_service, "Fluency")
        habit_uid = await _habit_supporting(habits_service, [goal])

        result = await scheduler.schedule_events_for_habit(
            habit_uid, UserContext(user_uid=USER), auto_create=True
        )

        async with neo4j_driver.session() as session:
            row = await (
                await session.run(
                    "MATCH (e:Event {uid: $uid}) "
                    "RETURN e.contributes_to_goal_uids AS plural, "
                    "e.fulfills_goal_uid AS stamp, e.metadata AS metadata",
                    uid=result.value[0].uid,
                )
            ).single()
        assert row["plural"] is None
        assert row["stamp"] is None
        assert "supports_goals" not in (row["metadata"] or "")


@pytest.mark.asyncio
class TestRequestDoorGoalAdmission:
    """``POST /api/events/create`` accepts ``contributes_to_goal_uids`` — request input,
    so each UID must pass the owner/kind/existence admission before it becomes an edge."""

    async def test_another_users_goal_is_refused_and_the_own_goal_kept(
        self, users, goals_service, events_service, neo4j_driver
    ) -> None:
        own = await _goal(goals_service, "Mine")
        victims = await _goal(goals_service, "Theirs", user_uid=OTHER_USER)

        event = await events_service.create_event(
            EventCreateRequest(
                title="Study block",
                event_date=date.today() + timedelta(days=1),
                start_time=time(9, 0),
                end_time=time(10, 0),
                contributes_to_goal_uids=[own, victims],
            ),
            USER,
        )

        assert event.is_ok, f"create_event failed: {event.error}"
        assert await _goal_edges(neo4j_driver, event.value.uid) == {own}, (
            "a cross-user CONTRIBUTES_TO_GOAL edge reached the graph"
        )
