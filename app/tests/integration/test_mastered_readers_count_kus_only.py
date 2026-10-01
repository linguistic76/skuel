"""Every reader that reports "Kus mastered" counts Ku edges only.

A PathStep carries a MASTERED edge of its own once its last Ku is mastered
(``PsMasteryService.handle_knowledge_mastered``), through the same writer and in the
same shape as a Ku's. A reader that matched ``(User)-[:MASTERED]->(:Entity)`` and
labelled the count "knowledge" would then silently add one per completed step —
the per-user-substance class of bug, where every number stays plausible and none is
right. Each reader below is driven against a graph holding one mastered Ku and one
mastered step, and must answer with the Ku alone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from adapters.persistence.neo4j.user_progress_backend import UserProgressBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID

USER = UserUID("user_mastered_readers")
KU = "ku.readers.only-ku"
STEP = "ps.readers.the-step"


@pytest_asyncio.fixture
async def graph(neo4j_driver, clean_neo4j) -> None:
    """One Ku and one step, both mastered through the one real writer."""
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $u})", u=USER)
        await session.run(
            """
            CREATE (ps:Entity:PathStep {uid: $step, entity_type: 'path_step',
                                        title: 'The step', status: 'active'})
            CREATE (k:Entity:Ku {uid: $ku, entity_type: 'ku', title: 'The Ku'})
            CREATE (ps)-[:USES_KU]->(k)
            """,
            step=STEP,
            ku=KU,
        )
    backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    now = datetime.now(UTC).isoformat()
    assert (await backend.mark_mastered(USER, KU, now, 0.9, "report_approval")).is_ok
    assert (await backend.mark_mastered(USER, STEP, now, 1.0, "derived")).is_ok


@pytest.fixture
def cross_domain(neo4j_driver) -> CrossDomainBackend:
    return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))


@pytest.fixture
def context_executor(neo4j_driver) -> UserContextQueryExecutor:
    return UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))


@pytest.fixture
def progress(neo4j_driver) -> UserProgressBackend:
    return UserProgressBackend(Neo4jQueryExecutor(neo4j_driver))


@pytest.mark.asyncio
async def test_the_rich_context_knowledge_read(graph, context_executor) -> None:
    result = await context_executor.execute_mega_query(USER)
    assert result.is_ok
    mastery = result.value["uids"]["knowledge_mastery"]
    assert {item["uid"] for item in mastery} == {KU}


@pytest.mark.asyncio
async def test_the_standard_context_knowledge_read(graph, context_executor) -> None:
    result = await context_executor.execute_consolidated_query(USER)
    assert result.is_ok
    assert result.value["knowledge"]["mastered_uids"] == {KU}


@pytest.mark.asyncio
async def test_learning_velocity_total_kus(graph, cross_domain) -> None:
    start = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    result = await cross_domain.get_learning_velocity_metrics(USER, start)
    assert result.is_ok
    assert result.value[0]["total_kus"] == 1
    assert result.value[0]["recent_kus"] == 1


@pytest.mark.asyncio
async def test_user_learning_state_mastered_list(graph, cross_domain) -> None:
    result = await cross_domain.get_user_learning_state(USER)
    assert result.is_ok
    assert result.value[0]["mastered"] == [KU]


@pytest.mark.asyncio
async def test_system_totals(graph, cross_domain) -> None:
    result = await cross_domain.get_entity_system_metrics()
    assert result.is_ok
    row = result.value[0]
    assert row["total_kus"] == 1, "the corpus total is Ku nodes, not every entity"
    assert row["total_mastered"] == 1


@pytest.mark.asyncio
async def test_all_users_progress_mastered_count(graph, cross_domain) -> None:
    result = await cross_domain.get_all_users_progress()
    assert result.is_ok
    row = next(r for r in result.value if r["uid"] == USER)
    assert row["mastered_count"] == 1


@pytest.mark.asyncio
async def test_user_ku_detail_mastered_list(graph, cross_domain) -> None:
    result = await cross_domain.get_user_ku_detail(USER)
    assert result.is_ok
    assert [m["uid"] for m in result.value[0]["mastered_kus"]] == [KU]


@pytest.mark.asyncio
async def test_user_detail_stats_ku_mastered(graph, cross_domain) -> None:
    result = await cross_domain.get_user_detail_stats(USER)
    assert result.is_ok
    assert result.value[0]["ku_mastered"] == 1


@pytest.mark.asyncio
async def test_users_with_activity_counts_ku_mastered(graph, cross_domain) -> None:
    result = await cross_domain.get_users_with_activity_counts("u.uid = $uid", {"uid": USER})
    assert result.is_ok
    assert result.value[0]["ku_mastered"] == 1


@pytest.mark.asyncio
async def test_recent_activities_knowledge_leg(graph, cross_domain) -> None:
    result = await cross_domain.get_recent_activities(USER)
    assert result.is_ok
    mastered = [
        a["activity"]["entity_uid"] for a in result.value if a["activity"]["type"] == "knowledge"
    ]
    assert mastered == [KU]


@pytest.mark.asyncio
async def test_knowledge_profile_list_is_kus_and_membership_is_every_entity(
    graph, progress
) -> None:
    """The concept list counts Kus; the membership set holds the step too."""
    knowledge = await progress.get_mastered_knowledge(USER)
    assert knowledge.is_ok
    assert [row["knowledge_uid"] for row in knowledge.value] == [KU]

    members = await progress.get_mastered_entity_uids(USER)
    assert members.is_ok
    assert {row["uid"] for row in members.value} == {KU, STEP}
