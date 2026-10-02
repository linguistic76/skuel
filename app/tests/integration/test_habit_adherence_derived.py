"""A habit's adherence is derived at read time from its completions — against a real graph.

``habit_completion_rates`` on the user context, the at-risk classification, the
momentum signal, ``HabitsStats.consistency_rate`` and the analytics habit metrics
all read one number: a habit's completions in the trailing adherence window over
what its frequency expects there (``core.models.habit.adherence``). The window
count is Cypher, so what decides it — which completions are inside the window,
whose they are, and that both completion doors leave a node it can see — is
proven here against the container. Completions go through the production doors
(``record_completion``, ``record_completions_bulk``) on the days they happened;
only the foreign record is the door used by the wrong user.

The users:

- KEPT — a daily habit completed on each of the last 28 days through
  ``record_completion``: 28 / 30.
- BULK — the same habit, the same 28 days, through ``record_completions_bulk``:
  the positive control, which must read exactly what KEPT reads.
- DROPPED — completed on seven days two to three weeks ago and twice six weeks
  ago, then dropped; plus two completions stamped in the future and five records
  another user wrote against its uid: 7 / 30, whatever the rest.
- INTRUDER — writes those five, and keeps a habit of their own.
- NO_HABITS — none at all: no rate, no consistency signal, no warning.

The design and what it leaves to the write side:
``docs/roadmap/habit-completion-persistence-bundle.md``.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
import pytest_asyncio
import time_machine
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.activity_backends import HabitsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.constants import HabitConsistencyWindow
from core.models.enums import RecurrencePattern
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.analytics.analytics_metrics_service import AnalyticsMetricsService
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.services.user import UserContext
from core.services.user.intelligence.temporal_momentum import TemporalMomentumMixin
from core.services.user.unified_user_context import is_rich
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user_stats_types import _compute_domain_stats_from_context
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

KEPT = UserUID("user_adherence_kept")
BULK = UserUID("user_adherence_bulk")
DROPPED = UserUID("user_adherence_dropped")
INTRUDER = UserUID("user_adherence_intruder")
NO_HABITS = UserUID("user_adherence_none")
USERS = (KEPT, BULK, DROPPED, INTRUDER, NO_HABITS)

KEPT_HABIT = "habit.adherence.kept"
BULK_HABIT = "habit.adherence.bulk"
DROPPED_HABIT = "habit.adherence.dropped"
INTRUDER_HABIT = "habit.adherence.intruder"

TODAY = today_in(current_zone())
KEPT_DAYS = [TODAY - timedelta(days=n) for n in range(28)]
DROPPED_DAYS = [TODAY - timedelta(days=n) for n in range(14, 21)]  # dropped two weeks ago
LONG_AGO_DAYS = [TODAY - timedelta(days=n) for n in (40, 41)]  # outside the window
FUTURE_DAYS = [TODAY + timedelta(days=n) for n in (1, 5)]
INTRUDER_DAYS = [TODAY - timedelta(days=n) for n in range(2, 7)]

KEPT_RATE = 28 / HabitConsistencyWindow.DAYS
DROPPED_RATE = 7 / HabitConsistencyWindow.DAYS


def _noon(day) -> datetime:
    """Noon on ``day`` in the current zone — when the user did it."""
    return datetime.combine(day, time(hour=12), tzinfo=current_zone())


def _on(day) -> time_machine.travel:
    """Freeze the process clock at noon on ``day``: a completion made that day."""
    return time_machine.travel(_noon(day).timestamp(), tick=False)


class _Momentum(TemporalMomentumMixin):
    """The momentum mixin over a built context — it reads nothing else."""

    def __init__(self, context: UserContext) -> None:
        assert is_rich(context), "the momentum signal reads a rich context"
        self.context = context


class _HabitsFacade:
    """The one facade call ``calculate_habit_metrics`` makes, answered from the graph."""

    def __init__(self, backend: HabitsBackend) -> None:
        self._backend = backend

    async def get_user_items_in_range(self, user_uid: str, **_: object) -> Result[list[Habit]]:
        return await self._backend.find_by(user_uid=user_uid)


async def _create_habit(backend: HabitsBackend, uid: str, user_uid: str) -> None:
    created = await backend.create(
        Habit(
            uid=uid,
            user_uid=user_uid,
            entity_type=EntityType.HABIT,
            title=uid,
            status=EntityStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
    )
    assert created.is_ok, created


@pytest_asyncio.fixture
async def graph(neo4j_driver: AsyncDriver, clean_neo4j) -> HabitsBackend:
    async with neo4j_driver.session() as session:
        await session.run(
            "UNWIND $uids AS uid MERGE (u:User {uid: uid}) SET u.title = uid", uids=list(USERS)
        )

    habits = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)
    completions = UniversalNeo4jBackend[HabitCompletion](
        neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
    )
    service = HabitsCompletionService(habits, completions)

    for uid, owner in (
        (KEPT_HABIT, KEPT),
        (BULK_HABIT, BULK),
        (DROPPED_HABIT, DROPPED),
        (INTRUDER_HABIT, INTRUDER),
    ):
        await _create_habit(habits, uid, owner)

    for day in KEPT_DAYS:
        with _on(day):
            kept = await service.record_completion(KEPT_HABIT, KEPT)
            bulk = await service.record_completions_bulk([BULK_HABIT], BULK)
        assert kept.is_ok and bulk.is_ok and len(bulk.value) == 1, (kept, bulk)

    for day in LONG_AGO_DAYS + DROPPED_DAYS:
        with _on(day):
            assert (await service.record_completion(DROPPED_HABIT, DROPPED)).is_ok
    for day in FUTURE_DAYS:
        stamped = await service.record_completion(DROPPED_HABIT, DROPPED, completed_at=_noon(day))
        assert stamped.is_ok, stamped
    for day in INTRUDER_DAYS:
        with _on(day):
            assert (await service.record_completion(DROPPED_HABIT, INTRUDER)).is_ok
            assert (await service.record_completion(INTRUDER_HABIT, INTRUDER)).is_ok

    # The premise: every completion is a node its writer owns, naming its habit.
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (u:User)-[:OWNS]->(hc:HabitCompletion)
            RETURN u.uid AS owner, hc.habit_uid AS habit, count(hc) AS n
            """
        )
        owned = {(r["owner"], r["habit"]): r["n"] async for r in result}
    assert owned == {
        (KEPT, KEPT_HABIT): 28,
        (BULK, BULK_HABIT): 28,
        (DROPPED, DROPPED_HABIT): 2 + 7 + 2,
        (INTRUDER, DROPPED_HABIT): 5,
        (INTRUDER, INTRUDER_HABIT): 5,
    }
    return habits


def _builder(neo4j_driver: AsyncDriver) -> UserContextBuilder:
    return UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))


async def _rich(neo4j_driver: AsyncDriver, user_uid: UserUID) -> UserContext:
    result = await _builder(neo4j_driver).build_rich_user_context(
        user_uid, User(uid=user_uid, title=user_uid, email=f"{user_uid}@test.com")
    )
    assert result.is_ok, result.error
    return result.value


async def _standard(neo4j_driver: AsyncDriver, user_uid: UserUID) -> UserContext:
    result = await _builder(neo4j_driver).build_user_context(
        user_uid, User(uid=user_uid, title=user_uid, email=f"{user_uid}@test.com")
    )
    assert result.is_ok, result.error
    return result.value


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitAdherenceInTheUserContext:
    async def test_a_habit_kept_daily_reads_its_window_and_is_not_at_risk(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        context = await _rich(neo4j_driver, KEPT)

        assert context.habit_completion_rates == {KEPT_HABIT: pytest.approx(KEPT_RATE)}
        assert context.habit_streaks[KEPT_HABIT] == 28
        assert context.at_risk_habits == []
        signals = _Momentum(context).compute_momentum_signals()
        assert signals["habit_consistency"] == pytest.approx(KEPT_RATE)
        assert not any(
            "Habit consistency" in w for w in _Momentum(context)._momentum_warnings(signals)
        )
        stats = _compute_domain_stats_from_context(context)
        assert stats.habits.consistency_rate == pytest.approx(KEPT_RATE)

    async def test_the_bulk_door_counts_exactly_what_the_single_door_counts(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        kept = await _rich(neo4j_driver, KEPT)
        bulk = await _rich(neo4j_driver, BULK)

        assert bulk.habit_completion_rates == {BULK_HABIT: kept.habit_completion_rates[KEPT_HABIT]}
        assert bulk.at_risk_habits == []

    async def test_a_dropped_habit_reads_what_the_window_holds(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        """Seven days inside the window count; the two six weeks ago, the two
        stamped in the future and the five another user wrote against its uid
        do not."""
        context = await _rich(neo4j_driver, DROPPED)

        assert context.habit_completion_rates == {DROPPED_HABIT: pytest.approx(DROPPED_RATE)}
        assert context.at_risk_habits == [DROPPED_HABIT]
        signals = _Momentum(context).compute_momentum_signals()
        assert signals["habit_consistency"] == pytest.approx(DROPPED_RATE)
        assert "Habit consistency is low — rebuilding streaks is today's priority" in (
            _Momentum(context)._momentum_warnings(signals)
        )

    async def test_the_intruder_reads_only_their_own_habit(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        context = await _rich(neo4j_driver, INTRUDER)

        assert context.habit_completion_rates == {
            INTRUDER_HABIT: pytest.approx(5 / HabitConsistencyWindow.DAYS)
        }

    async def test_a_user_with_no_habits_has_no_rate_and_no_consistency_warning(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        context = await _rich(neo4j_driver, NO_HABITS)

        assert context.habit_completion_rates == {}
        assert context.at_risk_habits == []
        signals = _Momentum(context).compute_momentum_signals()
        assert signals["habit_consistency"] is None
        assert not any(
            "Habit consistency" in w for w in _Momentum(context)._momentum_warnings(signals)
        )

    @pytest.mark.parametrize(
        ("user_uid", "rates"),
        [
            (KEPT, {KEPT_HABIT: KEPT_RATE}),
            (BULK, {BULK_HABIT: KEPT_RATE}),
            (DROPPED, {DROPPED_HABIT: DROPPED_RATE}),
            (INTRUDER, {INTRUDER_HABIT: 5 / HabitConsistencyWindow.DAYS}),
            (NO_HABITS, {}),
        ],
    )
    async def test_the_standard_build_derives_the_same_rates(
        self,
        neo4j_driver: AsyncDriver,
        graph: HabitsBackend,
        user_uid: UserUID,
        rates: dict[str, float],
    ) -> None:
        rich = await _rich(neo4j_driver, user_uid)
        standard = await _standard(neo4j_driver, user_uid)

        assert standard.habit_completion_rates == pytest.approx(rates)
        assert standard.habit_completion_rates == rich.habit_completion_rates


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitWindowCompletionsRead:
    async def test_each_habit_counts_its_owners_completions_in_the_window(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))
        first = HabitConsistencyWindow.start_date(TODAY).isoformat()
        last = HabitConsistencyWindow.end_date(TODAY).isoformat()

        result = await backend.get_habit_window_completions(
            [KEPT_HABIT, BULK_HABIT, DROPPED_HABIT, INTRUDER_HABIT, "habit.adherence.missing"],
            first,
            last,
        )

        assert result.is_ok, result.error
        assert result.value == {
            KEPT_HABIT: 28,
            BULK_HABIT: 28,
            DROPPED_HABIT: 7,
            INTRUDER_HABIT: 5,
        }

    async def test_the_analytics_habit_metrics_read_the_derived_rate(
        self, neo4j_driver: AsyncDriver, graph: HabitsBackend
    ) -> None:
        metrics = AnalyticsMetricsService(
            habits_service=_HabitsFacade(graph),
            cross_domain_backend=CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)),
        )

        kept = await metrics.calculate_habit_metrics(KEPT, TODAY, TODAY)
        dropped = await metrics.calculate_habit_metrics(DROPPED, TODAY, TODAY)

        assert kept.is_ok and dropped.is_ok
        assert kept.value["consistency_rate"] == round(KEPT_RATE * 100, 1)
        assert kept.value["completion_rate"] == round(KEPT_RATE * 100, 1)
        assert dropped.value["consistency_rate"] == round(DROPPED_RATE * 100, 1)
