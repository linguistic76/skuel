"""
The learning state a built UserContext carries — goal kinds, Ku prerequisites, readiness.
=========================================================================================

Five ``UserContext`` fields were declared, read in 65 places and written by nothing:
the goal-kind lists, ``prerequisites_needed``, ``prerequisites_completed``,
``next_recommended_knowledge`` and the minutes map. Every reader saw the default. The
data was in the context all along — each goal's ``goal_type`` rides its properties, the
extractor built the per-Ku prerequisite map and dropped it — so the kinds are now written
from ``goal_type``, the map is kept as ``ku_prerequisites``, and readiness is read off the
built ``ready_to_learn_uids``.

A unit test over a hand-built context proves nothing here: the old fields were hand-fed
in every test and empty in every build. So each test reads a context the builder made,
over goals created at the real door and Ku edges as the learner's progress writers
leave them, and through the two ``/api/context`` routes that report them.

The learner's knowledge:

    KU_BASE      MASTERED
    KU_READY     IN_PROGRESS, requires KU_BASE           -> ready to learn
    KU_BLOCKED   IN_PROGRESS, requires KU_BASE, KU_UNSEEN -> blocked by KU_UNSEEN
    KU_UNSEEN    never touched
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

    from core.services.user import UserContext

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzctxlearn"
USER = f"user_{MARK}"

KU_BASE = f"ku.{MARK}.base"
KU_READY = f"ku.{MARK}.ready"
KU_BLOCKED = f"ku.{MARK}.blocked"
KU_UNSEEN = f"ku.{MARK}.unseen"


class Env:
    def __init__(self, client: httpx.AsyncClient, services: Any, goals: dict[str, str]) -> None:
        self.client = client
        self.services = services  # boundary: the composed Services container
        self.goals = goals


async def _seed_knowledge(driver: Any) -> None:  # boundary: neo4j AsyncDriver
    async with driver.session() as session:
        await session.run(
            """
            UNWIND $kus AS ku_uid
            MERGE (k:Entity:Ku {uid: ku_uid})
            SET k.title = ku_uid, k.entity_type = 'ku'
            """,
            kus=[KU_BASE, KU_READY, KU_BLOCKED, KU_UNSEEN],
        )
        await session.run(
            """
            MATCH (u:User {uid: $user})
            MATCH (base:Ku {uid: $base}), (ready:Ku {uid: $ready}),
                  (blocked:Ku {uid: $blocked}), (unseen:Ku {uid: $unseen})
            MERGE (u)-[:MASTERED {mastery_score: 1.0}]->(base)
            MERGE (u)-[:IN_PROGRESS {progress: 0.3}]->(ready)
            MERGE (u)-[:IN_PROGRESS {progress: 0.3}]->(blocked)
            MERGE (ready)-[:REQUIRES_KNOWLEDGE]->(base)
            MERGE (blocked)-[:REQUIRES_KNOWLEDGE]->(base)
            MERGE (blocked)-[:REQUIRES_KNOWLEDGE]->(unseen)
            """,
            user=USER,
            base=KU_BASE,
            ready=KU_READY,
            blocked=KU_BLOCKED,
            unseen=KU_UNSEEN,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, USER, MARK) as client:
        goals = {
            kind: await create(client, "goals", f"{MARK} {kind} goal", goal_type=kind)
            for kind in ("learning", "outcome", "process", "project")
        }
        # A finished learning goal is no active goal of any kind.
        goals["finished"] = await create(
            client, "goals", f"{MARK} finished learning goal", goal_type="learning"
        )
        finished = await client.post(
            f"/api/goals/{goals['finished']}/status", data={"status": "completed"}
        )
        assert finished.status_code == 200, finished.text
        assert "Missing status" not in finished.text and "Invalid status" not in finished.text
        services = skuel_app.state.services
        await _seed_knowledge(services.neo4j_driver)
        yield Env(client, services, goals)


async def _rich(env: Env) -> UserContext:
    built = await env.services.user.get_rich_unified_context(USER)
    assert built.is_ok, built
    return built.value


async def test_the_rich_build_sorts_the_active_goals_by_kind(env: Env) -> None:
    context = await _rich(env)

    assert context.learning_goals == [env.goals["learning"]]
    assert context.outcome_goals == [env.goals["outcome"]]
    assert context.process_goals == [env.goals["process"]]


async def test_the_standard_build_sorts_them_the_same_way(env: Env) -> None:
    built = await env.services.context.context_builder.build(USER)
    assert built.is_ok, built
    context = built.value

    assert context.learning_goals == [env.goals["learning"]]
    assert context.outcome_goals == [env.goals["outcome"]]
    assert context.process_goals == [env.goals["process"]]


async def test_the_build_keeps_each_kus_prerequisites(env: Env) -> None:
    context = await _rich(env)

    assert context.ku_prerequisites == {
        KU_BASE: set(),
        KU_READY: {KU_BASE},
        KU_BLOCKED: {KU_BASE, KU_UNSEEN},
    }
    assert context.blocked_knowledge_uids == {KU_BLOCKED}
    assert context.unmet_prerequisites(KU_BLOCKED) == {KU_UNSEEN}


async def test_ready_to_learn_is_the_started_ku_whose_prerequisites_are_mastered(
    env: Env,
) -> None:
    context = await _rich(env)

    assert context.get_ready_to_learn() == [KU_READY]


async def test_the_unblocking_order_names_the_prerequisite_holding_a_ku_back(
    env: Env,
) -> None:
    intelligence = env.services.context_intelligence.create(await _rich(env))

    order = await intelligence.get_unblocking_priority_order()

    assert order.is_ok, order
    assert order.value == [(KU_UNSEEN, 1)]


async def test_the_dashboard_counts_the_goal_kinds_and_the_ready_ku(env: Env) -> None:
    response = await env.client.get("/api/context/dashboard")

    assert response.status_code == 200, response.text
    dashboard = response.json()
    assert dashboard["goals"]["learning_goals"] == 1
    assert dashboard["goals"]["outcome_goals"] == 1
    assert dashboard["goals"]["process_goals"] == 1
    assert dashboard["learning"]["ready_to_learn_count"] == 1


async def test_the_adaptive_path_recommends_the_ready_ku(env: Env) -> None:
    response = await env.client.get("/api/context/learning/adaptive-path")

    assert response.status_code == 200, response.text
    path = response.json()
    assert path["ready_to_learn"] == [KU_READY]
    assert path["next_recommended"] == [KU_READY]
