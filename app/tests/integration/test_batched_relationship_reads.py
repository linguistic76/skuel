"""
Relationship reads over a set cost a fixed number of queries.
=============================================================

A read that asks the same relationship question of every entity in a set — the
complexity of each choice, the prerequisites of each task — runs one statement
per question, whatever the size of the set. Each test measures the statements a
read sends for a small set and for a larger one and asserts the two are equal,
then checks the answer against the per-entity read it replaces.

Statements are counted at ``AsyncSession.run``, the call every backend read goes
through.

See: core/utils/generic_fetcher.py (fetch_relationships_batch)
     adapters/persistence/neo4j/_relationship_crud_mixin.py (batch_count_related)
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from neo4j import AsyncDriver, AsyncSession

from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.lp_position import LpPosition
from core.services.choices.choice_relationships import CHOICE_QUERY_SPECS, ChoiceRelationships
from core.services.principles.principle_relationships import (
    PRINCIPLE_QUERY_SPECS,
    PrincipleRelationships,
)
from core.services.user import UserContext
from tests.helpers.seed_uids import seed_user_uid

USER = seed_user_uid("batched_reads")
STRANGER = seed_user_uid("batched_reads_stranger")
# The middle segment of each owner's seeded uids: ``{entity_type}.{tag}-{i}``.
TAGS: dict[str, str] = {USER: "batched", STRANGER: "batched-stranger"}
KU = "ku.batched-reads.concept"

SMALL = 3
LARGE = 7


@pytest.fixture
def statements(monkeypatch) -> list[str]:
    """Every statement a session runs from here on."""
    ran: list[str] = []
    original = AsyncSession.run

    async def counting_run(self: AsyncSession, query: Any, *args: Any, **kwargs: Any) -> Any:
        ran.append(str(query))
        return await original(self, query, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "run", counting_run)
    return ran


async def _run(neo4j_driver: AsyncDriver, query: str, **params: Any) -> None:
    async with neo4j_driver.session() as session:
        await session.run(query, **params)


async def _seed_owned(
    neo4j_driver: AsyncDriver, label: NeoLabel, entity_type: str, owner: str, first: int, last: int
) -> list[str]:
    """Owned nodes ``{entity_type}.{tag}-{i}`` for i in [first, last], as the create door owns them."""
    now = datetime.now(UTC).isoformat()
    await _run(
        neo4j_driver,
        f"""
        MERGE (u:User {{uid: $owner}})
        WITH u
        UNWIND range($first, $last) AS i
        CREATE (n:Entity:{label} {{
            uid: $entity_type + '.' + $tag + '-' + toString(i),
            user_uid: $owner,
            entity_type: $entity_type,
            title: $entity_type + ' ' + toString(i),
            status: 'active',
            created_at: $now,
            updated_at: $now
        }})
        CREATE (u)-[:OWNS]->(n)
        """,
        owner=owner,
        tag=TAGS[owner],
        first=first,
        last=last,
        entity_type=entity_type,
        now=now,
    )
    return [f"{entity_type}.{TAGS[owner]}-{i}" for i in range(first, last + 1)]


async def _seed_ku(neo4j_driver: AsyncDriver) -> None:
    await _run(
        neo4j_driver,
        "CREATE (:Entity:Ku {uid: $uid, entity_type: 'ku', title: 'Concept'})",
        uid=KU,
    )


async def _link(neo4j_driver: AsyncDriver, source: str, relationship: str, target: str) -> None:
    await _run(
        neo4j_driver,
        f"MATCH (a:Entity {{uid: $a}}), (b:Entity {{uid: $b}}) CREATE (a)-[:{relationship}]->(b)",
        a=source,
        b=target,
    )


async def _choices_and_principles(
    neo4j_driver: AsyncDriver, count: int
) -> tuple[list[str], list[str]]:
    """``count`` choices and principles for USER; principle i informs choices i and i+1.

    A stranger's principle informs the first choice — every read leaves it out.
    """
    choices = await _seed_owned(neo4j_driver, NeoLabel.CHOICE, "choice", USER, 1, count)
    principles = await _seed_owned(neo4j_driver, NeoLabel.PRINCIPLE, "principle", USER, 1, count)
    for i, principle in enumerate(principles):
        for choice in choices[i : i + 2]:
            await _link(neo4j_driver, principle, "INFORMS_CHOICE", choice)
    (foreign,) = await _seed_owned(neo4j_driver, NeoLabel.PRINCIPLE, "principle", STRANGER, 1, 1)
    await _link(neo4j_driver, foreign, "INFORMS_CHOICE", choices[0])
    return choices, principles


async def _grow(neo4j_driver: AsyncDriver, label: NeoLabel, entity_type: str) -> list[str]:
    return await _seed_owned(neo4j_driver, label, entity_type, USER, SMALL + 1, LARGE)


async def _measure(statements: list[str], read: Any) -> tuple[Any, int]:
    statements.clear()
    result = await read()
    return result, len(statements)


@pytest.mark.asyncio
class TestChoiceComplexityBatch:
    async def test_matches_the_single_read(self, services, clean_neo4j):
        choices, _principles = await _choices_and_principles(services.tasks.backend.driver, SMALL)
        relationships = services.choices.intelligence.relationships

        batch = await ChoiceRelationships.fetch_many(choices, relationships)

        assert batch.is_ok, batch
        for uid in choices:
            assert batch.value[uid] == await ChoiceRelationships.fetch(uid, relationships)
        assert batch.value[choices[0]].informing_principle_uids == ["principle.batched-1"]

    async def test_one_statement_per_key_whatever_the_number_of_choices(
        self, services, clean_neo4j, statements
    ):
        driver = services.tasks.backend.driver
        choices, _principles = await _choices_and_principles(driver, SMALL)
        intelligence = services.choices.intelligence

        small, small_count = await _measure(
            statements, lambda: intelligence.batch_analyze_decision_complexity(choices)
        )
        more = choices + await _grow(driver, NeoLabel.CHOICE, "choice")
        large, large_count = await _measure(
            statements, lambda: intelligence.batch_analyze_decision_complexity(more)
        )

        assert small.is_ok, small
        assert large.is_ok, large
        assert len(large.value) == LARGE
        assert small_count == large_count == len(CHOICE_QUERY_SPECS)


@pytest.mark.asyncio
class TestPrincipleAdoptionBatch:
    async def test_matches_the_single_read(self, services, clean_neo4j):
        _choices, principles = await _choices_and_principles(services.tasks.backend.driver, SMALL)
        relationships = services.principles.intelligence.relationships

        batch = await PrincipleRelationships.fetch_many(principles, relationships)

        assert batch.is_ok, batch
        for uid in principles:
            assert batch.value[uid] == await PrincipleRelationships.fetch(uid, relationships)
        assert len(batch.value[principles[0]].informed_choice_uids) == 2

    async def test_one_statement_per_key_whatever_the_number_of_principles(
        self, services, clean_neo4j, statements
    ):
        driver = services.tasks.backend.driver
        _choices, principles = await _choices_and_principles(driver, SMALL)
        intelligence = services.principles.intelligence

        small, small_count = await _measure(
            statements, lambda: intelligence.batch_analyze_principle_adoption(principles)
        )
        more = principles + await _grow(driver, NeoLabel.PRINCIPLE, "principle")
        large, large_count = await _measure(
            statements, lambda: intelligence.batch_analyze_principle_adoption(more)
        )

        assert small.is_ok, small
        assert large.is_ok, large
        assert len(large.value) == LARGE
        assert small_count == large_count == len(PRINCIPLE_QUERY_SPECS)


async def _tasks(neo4j_driver: AsyncDriver) -> list[str]:
    """SMALL tasks: the first requires knowledge, the second requires the third, all apply KU."""
    await _seed_ku(neo4j_driver)
    tasks = await _seed_owned(neo4j_driver, NeoLabel.TASK, "task", USER, 1, SMALL)
    await _link(neo4j_driver, tasks[0], "REQUIRES_KNOWLEDGE", KU)
    await _link(neo4j_driver, tasks[1], "REQUIRES_PREREQUISITE", tasks[2])
    for task in tasks:
        await _link(neo4j_driver, task, "APPLIES_KNOWLEDGE", KU)
    return tasks


@pytest.mark.asyncio
class TestTaskSetReads:
    async def test_blocked_by_prerequisites(self, services, clean_neo4j, statements):
        driver = services.tasks.backend.driver
        tasks = await _tasks(driver)

        small, small_count = await _measure(
            statements, lambda: services.tasks.search.get_blocked_by_prerequisites(USER)
        )
        await _grow(driver, NeoLabel.TASK, "task")
        large, large_count = await _measure(
            statements, lambda: services.tasks.search.get_blocked_by_prerequisites(USER)
        )

        assert small.is_ok, small
        assert large.is_ok, large
        assert {task.uid for task in large.value} == {tasks[0], tasks[1]}
        assert small_count == large_count

    async def test_learning_relevant_tasks(self, services, clean_neo4j, statements):
        """No active path: every task with no applied knowledge outranks every one with some."""
        driver = services.tasks.backend.driver
        tasks = await _tasks(driver)
        position = LpPosition(
            active_paths=[],
            current_steps={},
            completed_step_uids=set(),
            next_recommended=[],
            user_uid=USER,
            generated_at=datetime.now(UTC),
            readiness_scores={},
        )

        small, small_count = await _measure(
            statements,
            lambda: services.tasks.learning.get_learning_relevant_tasks(
                USER, position, limit=LARGE
            ),
        )
        grown = await _grow(driver, NeoLabel.TASK, "task")
        large, large_count = await _measure(
            statements,
            lambda: services.tasks.learning.get_learning_relevant_tasks(
                USER, position, limit=LARGE
            ),
        )

        assert small.is_ok, small
        assert large.is_ok, large
        ranked = [task.uid for task in large.value]
        assert set(ranked[: len(grown)]) == set(grown)
        assert set(ranked[len(grown) :]) == set(tasks)
        assert small_count == large_count


async def _goals(neo4j_driver: AsyncDriver) -> list[str]:
    """SMALL goals: the first is supported by a habit, the second requires KU."""
    await _seed_ku(neo4j_driver)
    goals = await _seed_owned(neo4j_driver, NeoLabel.GOAL, "goal", USER, 1, SMALL)
    (habit,) = await _seed_owned(neo4j_driver, NeoLabel.HABIT, "habit", USER, 1, 1)
    await _link(neo4j_driver, habit, "SUPPORTS_GOAL", goals[0])
    await _link(neo4j_driver, goals[1], "REQUIRES_KNOWLEDGE", KU)
    return goals


@pytest.mark.asyncio
class TestGoalSetReads:
    async def test_goals_needing_habits(self, services, clean_neo4j, statements):
        driver = services.tasks.backend.driver
        goals = await _goals(driver)
        context = UserContext(user_uid=USER)

        small, small_count = await _measure(
            statements, lambda: services.goals.learning.get_goals_needing_habits(context)
        )
        await _grow(driver, NeoLabel.GOAL, "goal")
        large, large_count = await _measure(
            statements, lambda: services.goals.learning.get_goals_needing_habits(context)
        )

        assert small.is_ok, small
        assert large.is_ok, large
        assert [goal.uid for goal in large.value] == [goals[0]]
        assert small_count == large_count

    async def test_goals_blocked_by_knowledge(self, services, clean_neo4j, statements):
        driver = services.tasks.backend.driver
        goals = await _goals(driver)
        context = UserContext(user_uid=USER)

        small, small_count = await _measure(
            statements, lambda: services.goals.learning.get_goals_blocked_by_knowledge(context)
        )
        await _grow(driver, NeoLabel.GOAL, "goal")
        large, large_count = await _measure(
            statements, lambda: services.goals.learning.get_goals_blocked_by_knowledge(context)
        )

        assert small.is_ok, small
        assert large.is_ok, large
        assert [goal.uid for goal in large.value] == [goals[1]]
        assert small_count == large_count
