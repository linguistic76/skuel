"""
The life path's knowledge and the goals that serve it, read by a built UserContext.
===================================================================================

The designated life path is the learner's ``ULTIMATE_PATH`` LearningPath. Its knowledge
is every Ku its steps compose (``HAS_STEP``, then ``USES_KU`` / ``TRAINS_KU`` /
``CONTAINS_KNOWLEDGE``); a gap is one of those the learner has not mastered. A goal
serves the life path through ``SERVES_LIFE_PATH`` — written by
``POST /api/goals/link-life-path``, which links the caller's designated path only —
and, while no goal carries that link, an active goal serves it when it requires
knowledge the path holds.

The learner:

    LIFE        designated (the designate door) -> S1 -> KU_M (mastered), KU_P (in progress 0.5)
                                                -> S2 -> KU_U, KU_W (neither started;
                                                         KU_U requires KU_W)
    KU_OFF      in progress 0.2, on no step of the life path
    G_LEARN     a learning goal requiring KU_OFF
    G_REQUIRES  an outcome goal requiring KU_M
    G_LINKED    an outcome goal requiring nothing — linked to SPARE (a stale link, written
                raw), then to LIFE through the door after the first build

    OTHER_LIFE  another user's designated life path
    SPARE       a published learning path nobody designated

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import (
    create,
    seed_published_learning_path,
    seed_published_path_step,
    signed_in_client,
    write_edge,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

    from core.services.user import UserContext

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzlpknow"
USER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"  # designates OTHER_LIFE; never signs in

LIFE = f"lp.{MARK}.life"
OTHER_LIFE = f"lp.{MARK}.other-life"
SPARE = f"lp.{MARK}.spare"
S1 = f"ps.{MARK}.one"
S2 = f"ps.{MARK}.two"
KU_M = f"ku.{MARK}.a-mastered"
KU_P = f"ku.{MARK}.b-in-progress"
KU_U = f"ku.{MARK}.c-not-started"
KU_W = f"ku.{MARK}.d-needed-by-c"
KU_OFF = f"ku.{MARK}.off-path"


class Env:
    def __init__(
        self,
        client: httpx.AsyncClient,
        services: Any,  # boundary: the composed Services container
        uids: dict[str, str],
        before_link: UserContext,
    ) -> None:
        self.client = client
        self.services = services
        self.uids = uids
        self.before_link = before_link


async def _seed_ku(driver: AsyncDriver, uid: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MERGE (k:Entity:Ku {uid: $uid}) SET k.title = $uid, k.entity_type = 'ku'",
            uid=uid,
        )


async def _seed_curriculum(driver: AsyncDriver) -> None:
    for path in (LIFE, OTHER_LIFE, SPARE):
        await seed_published_learning_path(driver, path, path)
    for step in (S1, S2):
        await seed_published_path_step(driver, step, step)
    for ku in (KU_M, KU_P, KU_U, KU_W, KU_OFF):
        await _seed_ku(driver, ku)
    await write_edge(driver, LIFE, "HAS_STEP", S1, {"sequence": 1})
    await write_edge(driver, LIFE, "HAS_STEP", S2, {"sequence": 2})
    await write_edge(driver, S1, "USES_KU", KU_M)
    await write_edge(driver, S1, "USES_KU", KU_P)
    await write_edge(driver, S2, "TRAINS_KU", KU_U)
    await write_edge(driver, S2, "USES_KU", KU_W)
    await write_edge(driver, KU_U, "REQUIRES_KNOWLEDGE", KU_W, {"confidence": 0.9})
    await write_edge(driver, USER, "MASTERED", KU_M, {"mastery_score": 1.0})
    await write_edge(driver, USER, "IN_PROGRESS", KU_P, {"progress": 0.5})
    await write_edge(driver, USER, "IN_PROGRESS", KU_OFF, {"progress": 0.2})
    # Another user's life path: the designation edge alone, as the designate door writes it.
    async with driver.session() as session:
        await session.run("MERGE (o:User {uid: $uid}) SET o.title = $uid", uid=OTHER)
    await write_edge(driver, OTHER, "ULTIMATE_PATH", OTHER_LIFE)


async def _link_knowledge(client: httpx.AsyncClient, goal_uid: str, ku_uid: str) -> None:
    linked = await client.post(
        "/api/goals/link-knowledge", json={"goal_uid": goal_uid, "knowledge_uid": ku_uid}
    )
    assert linked.status_code == 200, linked.text


async def _link_life_path(
    client: httpx.AsyncClient, goal_uid: str, path_uid: str
) -> httpx.Response:
    return await client.post(
        "/api/goals/link-life-path", json={"goal_uid": goal_uid, "life_path_uid": path_uid}
    )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    async with signed_in_client(skuel_app, USER, MARK) as client:
        await _seed_curriculum(driver)
        designated = await client.post("/api/lifepath/designate", json={"life_path_uid": LIFE})
        assert designated.status_code == 200, designated.text
        uids = {
            "g_learn": await create(client, "goals", f"{MARK} learn", goal_type="learning"),
            "g_requires": await create(client, "goals", f"{MARK} requires", goal_type="outcome"),
            "g_linked": await create(client, "goals", f"{MARK} linked", goal_type="outcome"),
        }
        await _link_knowledge(client, uids["g_learn"], KU_OFF)
        await _link_knowledge(client, uids["g_requires"], KU_M)
        await write_edge(driver, uids["g_linked"], "SERVES_LIFE_PATH", SPARE)

        before = await services.context.context_builder.build_rich(USER)
        assert before.is_ok, before

        linked = await _link_life_path(client, uids["g_linked"], LIFE)
        assert linked.status_code == 200, linked.text

        # The rig's wipe on exit removes every node whose uid carries MARK, OTHER included.
        yield Env(client, services, uids, before.value)


async def _rich(env: Env) -> UserContext:
    # The builder itself, past the context cache: the link is written after a build.
    built = await env.services.context.context_builder.build_rich(USER)
    assert built.is_ok, built
    return built.value


async def _serves_life_path(env: Env) -> set[tuple[str, str]]:
    async with env.services.neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (g:Goal)-[:SERVES_LIFE_PATH]->(p)
            WHERE g.uid CONTAINS $mark OR p.uid CONTAINS $mark
            RETURN g.uid AS goal, p.uid AS path
            """,
            mark=MARK,
        )
        return {(row["goal"], row["path"]) async for row in result}


async def test_the_life_path_knowledge_is_what_its_steps_compose(env: Env) -> None:
    context = await _rich(env)

    assert context.life_path_uid == LIFE
    assert context.life_path_knowledge_uids == {KU_M, KU_P, KU_U, KU_W}
    # every Ku's prerequisites, a Ku the learner has not started included
    assert context.life_path_prerequisites == {KU_M: set(), KU_P: set(), KU_U: {KU_W}, KU_W: set()}


async def test_a_gap_is_life_path_knowledge_not_mastered(env: Env) -> None:
    """Not every weak Ku the learner has started: KU_OFF is on no step."""
    context = await _rich(env)

    assert context.get_life_path_gaps() == [KU_P, KU_U, KU_W]


async def test_the_link_door_writes_one_edge_to_the_designated_path(env: Env) -> None:
    """The goal's stale link to SPARE went when the link to LIFE was written."""
    assert await _serves_life_path(env) == {(env.uids["g_linked"], LIFE)}
    context = await _rich(env)
    assert context.life_path_goal_uids == {env.uids["g_linked"]}


async def test_the_link_door_refuses_another_users_life_path(env: Env) -> None:
    refused = await _link_life_path(env.client, env.uids["g_requires"], OTHER_LIFE)

    assert refused.status_code == 404, refused.text
    assert "NOT_FOUND_LIFE_PATH" in refused.text
    assert await _serves_life_path(env) == {(env.uids["g_linked"], LIFE)}


async def test_the_link_door_refuses_a_path_nobody_designated(env: Env) -> None:
    refused = await _link_life_path(env.client, env.uids["g_requires"], SPARE)

    assert refused.status_code == 404, refused.text
    assert "NOT_FOUND_LIFE_PATH" in refused.text
    assert await _serves_life_path(env) == {(env.uids["g_linked"], LIFE)}


async def test_until_a_goal_carries_the_link_a_goal_requiring_its_knowledge_serves(
    env: Env,
) -> None:
    """Before the link: the goal requiring KU_M; G_LEARN requires knowledge off the path.

    G_LINKED's link to SPARE, a path the learner has not designated, serves nothing.
    """
    assert env.before_link.life_path_goal_uids == set()
    assert env.before_link.get_life_path_goal_uids() == [env.uids["g_requires"]]


async def test_once_a_goal_carries_the_link_the_link_decides(env: Env) -> None:
    context = await _rich(env)

    assert context.get_life_path_goal_uids() == [env.uids["g_linked"]]
    intel = env.services.context_intelligence.create(context)
    alignment = (await intel.calculate_life_path_alignment()).value
    assert alignment.aligned_goals == (env.uids["g_linked"],)
    assert alignment.knowledge_gaps == (KU_P, KU_U, KU_W)


async def test_method_7_scores_knowledge_over_the_life_path(env: Env) -> None:
    """Mean mastery over KU_M (1.0), KU_P (0.5), KU_U and KU_W (not started, 0)."""
    context = await _rich(env)
    intel = env.services.context_intelligence.create(context)

    alignment = (await intel.calculate_life_path_alignment()).value

    assert alignment.knowledge_score == pytest.approx(0.375)


async def test_method_2_orders_the_unmastered_life_path_knowledge(env: Env) -> None:
    """KU_W first: it unlocks KU_U, which requires it (neither started); then by uid."""
    context = await _rich(env)
    intel = env.services.context_intelligence.create(context)

    critical_path = await intel.get_learning_path_critical_path()

    assert critical_path.is_ok, critical_path
    assert critical_path.value == [KU_W, KU_P, KU_U]


async def test_the_context_ranking_lifts_life_path_knowledge(env: Env) -> None:
    """The ready Kus are KU_P (on the path) and KU_OFF; only KU_P is the path's."""
    context = await _rich(env)
    intel = env.services.context_intelligence.create(context)

    steps = {step.ku_uid: step for step in intel._get_path_steps_from_context(max_steps=5)}

    assert set(steps) == {KU_P, KU_OFF}
    assert steps[KU_P].priority_score == pytest.approx(0.75)
    assert steps[KU_OFF].priority_score == pytest.approx(0.5)
    assert "Part of your life path" in steps[KU_P].rationale
    assert "life path" not in steps[KU_OFF].rationale


async def test_the_goal_page_shows_the_life_path_it_serves(env: Env) -> None:
    # The detail page's body is the HTMX fragment its shell loads.
    page = await env.client.get(f"/goals/detail/content?uid={env.uids['g_linked']}")

    assert page.status_code == 200, page.text
    assert "The life path this goal serves" in page.text
    assert f"/lp/{LIFE}" in page.text
