"""``Habit.success_rate`` is derived at read time at every habit read — against the composed app.

The rate is never a node property: every reader that consults it reads a habit
hydrated by ``enrich_habits_with_adherence`` — the same window count the user
context derives (``habit_completion_rates``). This module drives the composed
services (``skuel_app``) and checks each read the rate reaches — the facade's
CRUD and domain reads, the analytics endpoint, the pattern insights, scheduling,
the dual-track consistency score, the ZPD knowledge signals, the goal impact
analysis, and the planning service's contextual habits — against the context's
own number, and checks what each reader does with a habit that has no rate.

Completions go through the production doors (``record_completion``,
``record_completions_bulk``) on the days they happened (time-machined).

One user, five habits:

- KEPT — daily, created forty days ago, done on each of the last 28 days
  through ``record_completion``: 28 / 30, not at risk.
- BULK — the same through ``record_completions_bulk``: the positive control.
- YOUNG — daily, created two days ago, done all three days: 1.0 (measured over
  the days it has existed, not 3 / 30).
- QUARTERLY — done ten days ago: no rate (a 30-day window cannot hold a
  quarter), and kept on time, so not at risk.
- DROPPED — daily, done on seven days two to three weeks ago: 7 / 30, and
  overdue — at risk.

Design: ``docs/roadmap/habit-completion-persistence-bundle.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
import time_machine
from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.constants import HabitConsistencyWindow
from core.models.enums import Domain, RecurrencePattern
from core.models.enums.activity_enums import ConsistencyLevel
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService
from core.services.user import UserContext
from core.services.user.user_context_builder import UserContextBuilder
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

_USER = UserUID("user_ha2_success_rate")
_PREFIX = "ha2_"
KEPT = f"{_PREFIX}habit_kept"
BULK = f"{_PREFIX}habit_bulk"
YOUNG = f"{_PREFIX}habit_young"
QUARTERLY = f"{_PREFIX}habit_quarterly"
DROPPED = f"{_PREFIX}habit_dropped"
GOAL = f"{_PREFIX}goal"
KU = f"{_PREFIX}ku"
ALL_HABITS = (KEPT, BULK, YOUNG, QUARTERLY, DROPPED)

TODAY = today_in(current_zone())
KEPT_RATE = 28 / HabitConsistencyWindow.DAYS
DROPPED_RATE = 7 / HabitConsistencyWindow.DAYS
EXPECTED = {KEPT: KEPT_RATE, BULK: KEPT_RATE, YOUNG: 1.0, QUARTERLY: None, DROPPED: DROPPED_RATE}


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(hour=12), tzinfo=current_zone())


def _on(day: date) -> time_machine.travel:
    """Freeze the process clock at noon on ``day``: something done that day."""
    return time_machine.travel(_noon(day).timestamp(), tick=False)


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


@dataclass(frozen=True)
class _Composed:
    habits: HabitsService
    goals: GoalsService
    neo4j_driver: AsyncDriver


async def _create_habit(
    habits: HabitsService, uid: str, *, created: int, pattern: RecurrencePattern
) -> None:
    with _on(_days_ago(created)):
        result = await habits.create(
            Habit(
                uid=uid,
                user_uid=_USER,
                entity_type=EntityType.HABIT,
                title=uid,
                status=EntityStatus.ACTIVE,
                recurrence_pattern=pattern,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
    assert result.is_ok, result


async def _sweep(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) OPTIONAL MATCH (u)-[:OWNS]->(n) DETACH DELETE n, u",
            uid=_USER,
        )
        await session.run(
            "MATCH (n) WHERE n.uid STARTS WITH $prefix DETACH DELETE n", prefix=_PREFIX
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def services(skuel_app) -> AsyncIterator[_Composed]:
    composed = skuel_app.state.services
    assert composed.habits and composed.goals and composed.neo4j_driver
    services = _Composed(composed.habits, composed.goals, composed.neo4j_driver)
    driver = services.neo4j_driver
    await _sweep(driver)
    async with driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.email = $email",
            uid=_USER,
            email=f"{_USER}@example.test",
        )

    habits = services.habits
    daily = RecurrencePattern.DAILY
    for uid in (KEPT, BULK, DROPPED):
        await _create_habit(habits, uid, created=40, pattern=daily)
    await _create_habit(habits, YOUNG, created=2, pattern=daily)
    await _create_habit(habits, QUARTERLY, created=40, pattern=RecurrencePattern.QUARTERLY)

    doors = habits.completions
    for n in range(28):
        with _on(_days_ago(n)):
            assert (await doors.record_completion(KEPT, _USER)).is_ok
            bulk = await doors.record_completions_bulk([BULK], _USER)
            assert bulk.is_ok and len(bulk.value) == 1, bulk
    for n in range(14, 21):
        with _on(_days_ago(n)):
            assert (await doors.record_completion(DROPPED, _USER)).is_ok
    for n in range(3):
        with _on(_days_ago(n)):
            assert (await doors.record_completion(YOUNG, _USER)).is_ok
    with _on(_days_ago(10)):
        assert (await doors.record_completion(QUARTERLY, _USER)).is_ok

    goal = await services.goals.create(
        Goal(
            uid=GOAL,
            user_uid=_USER,
            title="Goal the habits support",
            domain=Domain.TECH,
            status=EntityStatus.ACTIVE,
        )
    )
    assert goal.is_ok, goal
    for uid in (KEPT, QUARTERLY, DROPPED):
        linked = await services.goals.link_goal_to_habit(GOAL, uid)
        assert linked.is_ok, linked
    async with driver.session() as session:
        await session.run(
            """
            CREATE (k:Entity {uid: $ku, entity_type: 'ku', title: $ku})
            WITH k
            MATCH (h:Habit) WHERE h.uid IN $habits
            CREATE (h)-[:REINFORCES_KNOWLEDGE]->(k)
            """,
            ku=KU,
            habits=[KEPT, QUARTERLY, DROPPED],
        )

    yield services
    await _sweep(driver)


async def _rich(driver: AsyncDriver) -> UserContext:
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(driver)))
    result = await builder.build_rich_user_context(
        _USER, User(uid=_USER, title=_USER, email=f"{_USER}@example.test")
    )
    assert result.is_ok, result
    return result.value


def _rate(value: float | None) -> object:
    return None if value is None else pytest.approx(value)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
class TestEveryHabitReadCarriesTheDerivedRate:
    async def test_the_context_derives_the_ruled_rates(self, services: _Composed) -> None:
        """The reference every read below is held to — and the ruled values."""
        context = await _rich(services.neo4j_driver)

        assert context.habit_completion_rates == {
            uid: pytest.approx(rate) for uid, rate in EXPECTED.items() if rate is not None
        }
        assert context.at_risk_habits == [DROPPED]

    async def test_the_facade_reads_carry_the_contexts_rate(self, services: _Composed) -> None:
        habits = services.habits
        for uid, rate in EXPECTED.items():
            got = await habits.get(uid)
            owned = await habits.get_for_user(uid, _USER)
            domain = await habits.get_habit(uid)
            assert got.is_ok and owned.is_ok and domain.is_ok
            assert got.value.success_rate == _rate(rate), uid
            assert owned.value.success_rate == _rate(rate), uid
            assert domain.value.success_rate == _rate(rate), uid

        listed = await habits.get_user_habits(_USER)
        page = await habits.list(user_uid=_USER, limit=50)
        assert listed.is_ok and page.is_ok
        for read in (listed.value, page.value[0]):
            assert {h.uid: h.success_rate for h in read} == {
                uid: _rate(rate) for uid, rate in EXPECTED.items()
            }

    async def test_the_node_never_holds_a_rate(self, services: _Composed) -> None:
        async with services.neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (h:Habit) WHERE h.uid IN $uids RETURN h.success_rate AS rate",
                uids=list(ALL_HABITS),
            )
            stored = [record["rate"] async for record in result]
        assert stored == [None] * len(ALL_HABITS)

    async def test_the_analytics_average_the_measured_and_count_the_one_rule(
        self, services: _Composed
    ) -> None:
        """The quarterly habit is not averaged as 0.0; at risk is the dropped habit alone."""
        result = await services.habits.intelligence.get_performance_analytics(_USER)

        assert result.is_ok, result
        measured = [rate for rate in EXPECTED.values() if rate is not None]
        assert result.value["avg_consistency"] == pytest.approx(
            round(sum(measured) / len(measured), 2)
        )
        assert result.value["at_risk_habits"] == 1

    async def test_the_pattern_insights_read_the_derived_rate(self, services: _Composed) -> None:
        kept = await services.habits.patterns.analyze_patterns(KEPT, _USER)
        dropped = await services.habits.patterns.analyze_patterns(DROPPED, _USER)
        quarterly = await services.habits.patterns.analyze_patterns(QUARTERLY, _USER)

        assert kept.is_ok and dropped.is_ok and quarterly.is_ok
        assert f"High success rate: {int(KEPT_RATE * 100)}%" in [
            p["pattern"] for p in kept.value.success_patterns
        ]
        assert f"Low success rate: {int(DROPPED_RATE * 100)}%" in [
            p["pattern"] for p in dropped.value.failure_patterns
        ]
        texts = [
            p["pattern"]
            for p in quarterly.value.success_patterns + quarterly.value.failure_patterns
        ]
        assert not any("success rate" in text for text in texts)

    async def test_scheduling_reads_the_derived_rate(self, services: _Composed) -> None:
        context = await _rich(services.neo4j_driver)
        dropped = await services.habits.scheduling.optimize_habit_schedule(DROPPED, context)
        quarterly = await services.habits.scheduling.optimize_habit_schedule(QUARTERLY, context)
        stacking = await services.habits.scheduling.suggest_habit_stacking(_USER)

        assert dropped.is_ok and quarterly.is_ok and stacking.is_ok
        assert dropped.value["success_rate"] == pytest.approx(DROPPED_RATE)
        assert any("below 50%" in r for r in dropped.value["recommendations"])
        assert quarterly.value["success_rate"] is None
        assert not any("below 50%" in r for r in quarterly.value["recommendations"])
        anchors = {s["anchor_habit_uid"]: s["success_rate"] for s in stacking.value}
        assert anchors[KEPT] == pytest.approx(KEPT_RATE)

    async def test_the_dual_track_score_reads_the_derived_rate(self, services: _Composed) -> None:
        intelligence = services.habits.intelligence
        kept = await intelligence.assess_consistency_dual_track(
            KEPT, _USER, ConsistencyLevel.CONSISTENT, "most days"
        )
        quarterly = await intelligence.assess_consistency_dual_track(
            QUARTERLY, _USER, ConsistencyLevel.CONSISTENT, "every quarter"
        )

        assert kept.is_ok and quarterly.is_ok
        assert f"Success rate: {KEPT_RATE * 100:.0f}%" in kept.value.system_evidence
        assert "No success rate yet" in quarterly.value.system_evidence
        assert quarterly.value.system_score >= 0.5

    async def test_the_zpd_signals_derive_the_rate_and_the_one_risk(
        self, services: _Composed
    ) -> None:
        """The Ku is at risk through the dropped habit; its strength is the strongest
        reinforcer's — the kept habit, streak 28 blended with its rate."""
        result = await services.habits.intelligence.get_zpd_knowledge_signals(_USER)

        assert result.is_ok, result
        assert result.value["reinforced_ku_uids"] == [KU]
        assert result.value["at_risk_ku_uids"] == [KU]
        streak_factor = min(1.0, 28 / 30)
        assert result.value["reinforcement_strength"][KU] == pytest.approx(
            round(streak_factor * 0.5 + KEPT_RATE * 0.5, 3)
        )

    async def test_the_goal_impact_reads_the_derived_rate_and_skips_no_rate(
        self, services: _Composed
    ) -> None:
        result = await services.goals.intelligence.analyze_habit_impact(GOAL)

        assert result.is_ok, result
        impacts = {a.habit_uid: a.current_consistency for a in result.value}
        assert impacts == {KEPT: pytest.approx(KEPT_RATE), DROPPED: pytest.approx(DROPPED_RATE)}

    async def test_planning_carries_the_contexts_rate_and_keeps_no_rate_none(
        self, services: _Composed
    ) -> None:
        context = await _rich(services.neo4j_driver)
        result = await services.habits.planning.get_habit_priorities_for_user(context, limit=10)

        assert result.is_ok, result
        rates = {h.uid: h.completion_rate for h in result.value}
        assert rates == {uid: _rate(rate) for uid, rate in EXPECTED.items()}
