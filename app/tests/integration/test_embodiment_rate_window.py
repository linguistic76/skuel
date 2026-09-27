"""A habit completion inside the week counts toward its principle's embodiment rate.

``CrossDomainQueryService.get_embodiment_rates_7d``'s cutoff crosses the driver as an
ISO string read through ``datetime()``, the same way the stored ``completed_at`` is
read. Bound raw, a naive ``datetime`` arrives as a LOCAL DATETIME, and
``datetime(hc.completed_at) >= <LOCAL DATETIME>`` is null in Neo4j — a zoned value
never compares with a local one — so no completion would count.

Completions are recorded through the real writer (``record_completion``), whose
stamp is the host clock's naive ``datetime.now()`` stored as an offset-less string;
the cutoff is on that clock too. The two window-edge tests force a zone west and a
zone east of UTC, where a cutoff on any other clock would move the edge by the
zone's offset and flip one of them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.activity_backends import HabitsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.relationship_names import RelationshipName
from core.services.cross_domain.cross_domain_query_service import CrossDomainQueryService
from core.services.habits.habits_completion_service import HabitsCompletionService
from tests.helpers.forced_zone import forced_zone

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

USER = "user_embodiment_window"
HABIT = "habit.embodiment_window"
PRINCIPLE = "principle.embodiment_window"


@pytest_asyncio.fixture
async def seeded(
    neo4j_driver, clean_neo4j
) -> tuple[HabitsCompletionService, CrossDomainQueryService]:
    """One owned habit that embodies one owned principle; no completions yet."""
    habits_backend = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)
    principles_backend = UniversalNeo4jBackend[Principle](
        neo4j_driver, NeoLabel.PRINCIPLE, Principle, base_label=NeoLabel.ENTITY
    )
    completions_backend = UniversalNeo4jBackend[HabitCompletion](
        neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
    )

    habit = await habits_backend.create(
        Habit(uid=HABIT, user_uid=USER, entity_type=EntityType.HABIT, title="Evening walk")
    )
    assert habit.is_ok, habit
    principle = await principles_backend.create(
        Principle(uid=PRINCIPLE, user_uid=USER, title="Move every day")
    )
    assert principle.is_ok, principle
    edge = await habits_backend.create_relationships_batch(
        [(HABIT, PRINCIPLE, RelationshipName.EMBODIES_PRINCIPLE.value, None)]
    )
    assert edge.is_ok, edge

    completions = HabitsCompletionService(habits_backend, completions_backend)
    queries = CrossDomainQueryService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    return completions, queries


async def _completed_at_types(neo4j_driver) -> set[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (hc:HabitCompletion {habit_uid: $habit}) RETURN valueType(hc.completed_at) AS t",
            habit=HABIT,
        )
        return {record["t"] async for record in result}


class TestEmbodimentWindow:
    async def test_a_completion_this_week_reads_a_non_zero_rate(self, seeded, neo4j_driver) -> None:
        completions, queries = seeded
        recorded = await completions.record_completion(HABIT, USER)
        assert recorded.is_ok, recorded
        # The premise: the real writer stores an offset-less string.
        assert {t.split(" ")[0] for t in await _completed_at_types(neo4j_driver)} == {"STRING"}

        rates = await queries.get_embodiment_rates_7d([PRINCIPLE], USER)

        assert rates.is_ok, rates
        assert rates.value == {PRINCIPLE: pytest.approx(1 / 7)}

    async def test_inside_the_edge_counts_west_of_utc(self, seeded) -> None:
        """Four hours inside the week counts.

        Under America/Vancouver (UTC-7, or UTC-8 in winter) a cutoff on UTC would sit
        that many hours later than the host-clock stamps and drop this completion.
        """
        completions, queries = seeded
        with forced_zone("America/Vancouver"):
            recorded = await completions.record_completion(
                HABIT, USER, completed_at=datetime.now() - timedelta(days=6, hours=20)
            )
            assert recorded.is_ok, recorded
            rates = await queries.get_embodiment_rates_7d([PRINCIPLE], USER)

        assert rates.is_ok, rates
        assert rates.value == {PRINCIPLE: pytest.approx(1 / 7)}

    async def test_outside_the_edge_does_not_count_east_of_utc(self, seeded) -> None:
        """Four hours outside the week does not count.

        Under Asia/Bangkok (UTC+7) a cutoff on UTC would sit seven hours earlier than
        the host-clock stamps and admit this completion.
        """
        completions, queries = seeded
        with forced_zone("Asia/Bangkok"):
            recorded = await completions.record_completion(
                HABIT, USER, completed_at=datetime.now() - timedelta(days=7, hours=4)
            )
            assert recorded.is_ok, recorded
            rates = await queries.get_embodiment_rates_7d([PRINCIPLE], USER)

        assert rates.is_ok, rates
        assert rates.value == {PRINCIPLE: 0.0}
