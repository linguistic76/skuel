"""Cypher's "today" is the zone's day, never the database's ``date()`` (UTC arc, PR 2b).

A process at TZ=UTC with the clock at 02:00Z is at 19:00 the previous day in
Vancouver. For a user on the default zone (``SKUEL_TIMEZONE`` unset: America/
Vancouver) today is that Vancouver day: a task due on it is not overdue in
``TasksBackend.get_stats_for_user``, a habit done on it is not streak-at-risk in
``HabitsBackend.get_active_habits_prioritized``, and the evening's alignment
snapshot (``LifePathBackend.record_alignment_snapshot``) is filed under it. At
18:00Z a user who chose Asia/Bangkok is at 01:00 the next day: today is the next
day, and a task due on the UTC day is overdue for them.

Each query takes ``$today`` from the zone helpers, so every test freezes the clock
they read (``core.utils.timestamp_helpers``) at 02:00Z or 18:00Z on the
testcontainer's own UTC date, and forces the process to UTC (CI's host; the
laptop's is Vancouver). The database's ``date()`` is that same UTC date, so a query
still reading it counts the Vancouver day's task as overdue, flags the habit and
files the snapshot a day late: red before the fix. The rows come from the real
writers — ``TasksCoreService.create_task`` (its due-date check reads the frozen
day), ``HabitsCompletionService.record_completion``, ``LifePathCoreService``, and
``UserService.update_preferences`` for the zone — and each test reads its premise
back raw. A user's reads run in that user's zone (``zone_scope`` over
``UserService.get_user_zone``), as a request of theirs does.

See: /docs/roadmap/utc-instants-arc.md § PR 2b
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import HabitsBackend, TasksBackend
from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.models.type_hints import UserUID
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.services.lifepath.lifepath_core_service import LifePathCoreService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.user_service import UserService
from core.utils import timestamp_helpers
from core.utils.timestamp_helpers import as_host_clock, today_in
from core.utils.zone_context import current_zone, zone_scope
from tests.helpers.forced_zone import forced_zone

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

VANCOUVER = ZoneInfo("America/Vancouver")
BANGKOK = ZoneInfo("Asia/Bangkok")

_RUN_ID = uuid.uuid4().hex[:8]
LIFE_PATH = "lp.utc-arc.today-in-zone"


def _at(day: date, hour: int) -> datetime:
    """``hour`` o'clock UTC on ``day``, aware."""
    return datetime.combine(day, time(hour), tzinfo=UTC)


class _Clock:
    """The clock the zone helpers read, set to one moment at a time."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    def at(self, moment: datetime) -> None:
        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                if tz is None:
                    return moment.astimezone().replace(tzinfo=None)
                return moment.astimezone(tz)

        self._monkeypatch.setattr(timestamp_helpers, "datetime", _Frozen)


@pytest.fixture
def utc_host(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A UTC process (CI, the cloud, the pinned app); the default zone is Vancouver."""
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    with forced_zone("UTC"):
        yield


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    return _Clock(monkeypatch)


@pytest_asyncio.fixture
async def utc_day(neo4j_driver) -> date:
    """The testcontainer's own UTC date: the day its ``date()`` returns."""
    async with neo4j_driver.session() as session:
        record = await (await session.run("RETURN toString(date()) AS day")).single()
    assert record is not None
    return date.fromisoformat(record["day"])


@pytest_asyncio.fixture
async def users(neo4j_driver, clean_neo4j, user_service) -> AsyncIterator[UserService]:
    """The real UserService; removes the users the test registered."""
    yield user_service
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User) WHERE u.uid ENDS WITH $run_id DETACH DELETE u", run_id=_RUN_ID
        )


async def _register(users: UserService, tag: str) -> UserUID:
    created = await users.create_user(f"zone_{tag}_{_RUN_ID}")
    assert created.is_ok, created
    return created.value.uid


async def _zone_of(users: UserService, uid: UserUID) -> ZoneInfo:
    zone = await users.get_user_zone(uid)
    assert zone.is_ok, zone
    return zone.value


async def _stored_zone_choice(neo4j_driver, uid: str) -> object:
    """The stored choice, read raw from the User node's ``preferences`` JSON string."""
    rows = await _raw(
        neo4j_driver, "MATCH (u:User {uid: $uid}) RETURN u.preferences AS preferences", uid=uid
    )
    assert len(rows) == 1
    preferences = rows[0]["preferences"]
    assert isinstance(preferences, str), "the mapper stores User.preferences as a JSON string"
    return json.loads(preferences).get("timezone")


async def _raw(neo4j_driver, query: str, **params: object) -> list[dict[str, object]]:
    async with neo4j_driver.session() as session:
        result = await session.run(query, **params)
        return [record.data() async for record in result]


def _tasks(neo4j_driver) -> tuple[TasksCoreService, TasksBackend]:
    backend = TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    return TasksCoreService(backend=backend, event_bus=InMemoryEventBus()), backend


async def _stored_due_dates(neo4j_driver, uid: str) -> list[tuple[object, str]]:
    rows = await _raw(
        neo4j_driver,
        """
        MATCH (:User {uid: $uid})-[:OWNS]->(t:Task)
        RETURN t.due_date AS due, valueType(t.due_date) AS type
        ORDER BY due
        """,
        uid=uid,
    )
    return [(row["due"], str(row["type"]).split(" ")[0]) for row in rows]


@pytest.mark.usefixtures("utc_host")
class TestADefaultUserInTheVancouverEvening:
    """02:00Z — the UTC day (the database's ``date()``) has turned; Vancouver's has not."""

    async def test_today_is_the_vancouver_day(self, neo4j_driver, users, clock, utc_day) -> None:
        uid = await _register(users, "default_today")
        assert await _stored_zone_choice(neo4j_driver, uid) is None  # no choice: the default
        zone = await _zone_of(users, uid)
        assert zone == VANCOUVER

        clock.at(_at(utc_day, 2))
        with zone_scope(zone):
            assert today_in(current_zone()) == utc_day - timedelta(days=1)

    async def test_a_task_due_that_day_is_not_overdue(
        self, neo4j_driver, users, clock, utc_day
    ) -> None:
        uid = await _register(users, "default_tasks")
        zone = await _zone_of(users, uid)
        service, backend = _tasks(neo4j_driver)
        today = utc_day - timedelta(days=1)  # Vancouver's day at 02:00Z
        yesterday = today - timedelta(days=1)

        # Both written three days before, while both days were ahead: the writer
        # refuses a due date already past.
        clock.at(_at(utc_day - timedelta(days=3), 12))
        with zone_scope(zone):
            for title, due in (("Due yesterday", yesterday), ("Due today", today)):
                created = await service.create_task(
                    TaskCreateRequest(title=title, due_date=due), uid
                )
                assert created.is_ok, created
        assert await _stored_due_dates(neo4j_driver, uid) == [
            (yesterday.isoformat(), "STRING"),
            (today.isoformat(), "STRING"),
        ]

        clock.at(_at(utc_day, 2))
        with zone_scope(zone):
            stats = await backend.get_stats_for_user(uid)

        assert stats.is_ok, stats
        assert stats.value["total"] == 2
        # Yesterday's task is overdue; today's is not. Against the database's
        # date() — the UTC day, already tomorrow in Vancouver — both would be.
        assert stats.value["overdue"] == 1

    async def test_a_habit_done_that_day_is_not_streak_at_risk(
        self, neo4j_driver, users, clock, utc_day
    ) -> None:
        uid = await _register(users, "default_habits")
        zone = await _zone_of(users, uid)
        habits = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)
        completions = HabitsCompletionService(
            habits,
            UniversalNeo4jBackend[HabitCompletion](
                neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
            ),
        )
        done, lapsed = f"habit.done_{_RUN_ID}", f"habit.lapsed_{_RUN_ID}"
        for habit_uid in (done, lapsed):
            created = await habits.create(
                Habit(uid=habit_uid, user_uid=uid, entity_type=EntityType.HABIT, title=habit_uid)
            )
            assert created.is_ok, created

        # Completions at 09:00 in Vancouver (16:00Z), stamped as the host clock
        # stamps them: the done habit yesterday and today (a two-day streak), the
        # lapsed one yesterday only (a one-day streak, not yet done today).
        today = utc_day - timedelta(days=1)
        yesterday = today - timedelta(days=1)
        for habit_uid, days in ((done, (yesterday, today)), (lapsed, (yesterday,))):
            for day in days:
                recorded = await completions.record_completion(
                    habit_uid, uid, completed_at=as_host_clock(_at(day, 16))
                )
                assert recorded.is_ok, recorded
        rows = await _raw(
            neo4j_driver,
            """
            MATCH (h:Habit) WHERE h.uid IN $uids
            RETURN h.uid AS uid, h.current_streak AS streak, h.last_completed AS last,
                   valueType(h.last_completed) AS type
            """,
            uids=[done, lapsed],
        )
        stored = {row["uid"]: row for row in rows}
        assert (stored[done]["streak"], stored[lapsed]["streak"]) == (2, 1)
        assert stored[done]["last"] == f"{today.isoformat()}T16:00:00"
        assert str(stored[done]["type"]).startswith("STRING")

        clock.at(_at(utc_day, 2))
        with zone_scope(zone):
            prioritized = await habits.get_active_habits_prioritized(uid, terminal_statuses=[])

        assert prioritized.is_ok, prioritized
        # The lapsed habit's streak is at risk and leads despite being shorter; the
        # done habit's is not. Against the database's date() both would be at risk,
        # and the longer streak would lead.
        assert [row["uid"] for row in prioritized.value] == [lapsed, done]

    async def test_the_evening_alignment_snapshot_is_filed_under_that_day(
        self, neo4j_driver, users, clock, utc_day
    ) -> None:
        uid = await _register(users, "default_lifepath")
        zone = await _zone_of(users, uid)
        await _raw(
            neo4j_driver,
            """
            CREATE (:Entity:LearningPath {uid: $lp, entity_type: 'learning_path',
                                          title: 'Live well', status: 'active'})
            """,
            lp=LIFE_PATH,
        )
        lifepath = LifePathCoreService(backend=LifePathBackend(Neo4jQueryExecutor(neo4j_driver)))
        designated = await lifepath.designate_life_path(uid, LIFE_PATH)
        assert designated.is_ok, designated

        clock.at(_at(utc_day, 2))
        with zone_scope(zone):
            scored = await lifepath.update_alignment_score(uid, 0.6)

        assert scored.is_ok, scored
        assert scored.value is True
        snapshots = await _raw(
            neo4j_driver,
            """
            MATCH (:User {uid: $uid})-[r:ALIGNMENT_SNAPSHOT]->(:Entity {uid: $lp})
            RETURN toString(r.date) AS day, valueType(r.date) AS type
            """,
            uid=uid,
            lp=LIFE_PATH,
        )
        # One snapshot, a DATE, on Vancouver's day — not the database's UTC day.
        assert [(row["day"], str(row["type"]).split(" ")[0]) for row in snapshots] == [
            ((utc_day - timedelta(days=1)).isoformat(), "DATE")
        ]


@pytest.mark.usefixtures("utc_host")
class TestABangkokUserInTheUtcEvening:
    """18:00Z — the database's UTC day, Vancouver's 11:00, and 01:00 the next day in Bangkok."""

    async def _bangkok_user(self, neo4j_driver, users: UserService) -> tuple[UserUID, ZoneInfo]:
        uid = await _register(users, "bangkok")
        chosen = await users.update_preferences(uid, {"timezone": "Asia/Bangkok"})
        assert chosen.is_ok, chosen
        assert await _stored_zone_choice(neo4j_driver, uid) == "Asia/Bangkok"
        zone = await _zone_of(users, uid)
        assert zone == BANGKOK
        return uid, zone

    async def test_today_is_the_next_day(self, neo4j_driver, users, clock, utc_day) -> None:
        _uid, zone = await self._bangkok_user(neo4j_driver, users)

        clock.at(_at(utc_day, 18))
        with zone_scope(zone):
            assert today_in(current_zone()) == utc_day + timedelta(days=1)
        assert today_in(current_zone()) == utc_day  # the default zone: 11:00 in Vancouver

    async def test_a_task_due_on_the_utc_day_is_overdue_for_them(
        self, neo4j_driver, users, clock, utc_day
    ) -> None:
        uid, zone = await self._bangkok_user(neo4j_driver, users)
        service, backend = _tasks(neo4j_driver)

        clock.at(_at(utc_day, 10))  # 17:00 in Bangkok: due today
        with zone_scope(zone):
            created = await service.create_task(
                TaskCreateRequest(title="Due on the UTC day", due_date=utc_day), uid
            )
        assert created.is_ok, created
        assert await _stored_due_dates(neo4j_driver, uid) == [(utc_day.isoformat(), "STRING")]

        clock.at(_at(utc_day, 18))  # 01:00 the next day in Bangkok
        with zone_scope(zone):
            stats = await backend.get_stats_for_user(uid)
        in_the_default_zone = await backend.get_stats_for_user(uid)

        assert stats.is_ok, stats
        # Overdue for the Bangkok user; against the database's date() — the UTC
        # day — it would not be.
        assert stats.value["overdue"] == 1
        # The day follows the zone read in: in Vancouver it is still the due day.
        assert in_the_default_zone.is_ok, in_the_default_zone
        assert in_the_default_zone.value["overdue"] == 0
