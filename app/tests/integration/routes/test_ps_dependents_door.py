"""What depends on a path step, over a real graph.

``/api/path-steps/dependencies``, ``/recommendations`` and ``/stats``' ``dependent_count`` all
ask one question: which steps require this one? The answer is the published steps holding
either prerequisite edge to it, each once. The seed holds everything else that can carry
such an edge: a Goal, a Ku and an Exercise are not steps and take no slot, a draft stays
unnamed and uncounted, a step holding both edges is one step, and a self-edge is not a
dependent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import pytest_asyncio
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import FastHTMLApp, Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

READER = seed_user_uid("psdependents_reader")
OTHER = seed_user_uid("psdependents_other")
TARGET = "ps.psdependents.target"
BY_BOTH = "ps.psdependents.a-by-both"
BY_KNOWLEDGE = "ps.psdependents.b-by-knowledge"
BY_STEP = "ps.psdependents.c-by-step"
TWO_HOPS = "ps.psdependents.two-hops"
DRAFT = "ps.psdependents.draft"
BEYOND_DRAFT = "ps.psdependents.beyond-draft"
CROWDED = "ps.psdependents.crowded"
CROWD = tuple(f"ps.psdependents.crowd-{n:02}" for n in range(12))
LEAF = "ps.psdependents.leaf"
KU = "ku.psdependents.concept"
EXERCISE = "ex.psdependents.exercise"
PRIVATE_GOAL = "goal.psdependents.private"
PRIVATE_TITLE = "a private goal of another user"
GOALS = tuple(f"goal.psdependents.crowd-{n:02}" for n in range(12))
_STEPS = (
    TARGET,
    BY_BOTH,
    BY_KNOWLEDGE,
    BY_STEP,
    TWO_HOPS,
    DRAFT,
    BEYOND_DRAFT,
    CROWDED,
    LEAF,
    *CROWD,
)
_ALL_GOALS = (PRIVATE_GOAL, *GOALS)
UIDS = (READER, OTHER, KU, EXERCISE, *_STEPS, *_ALL_GOALS)
_STAMP = "2000-01-01T00:00:00+00:00"

DEPENDENTS = "/api/path-steps/dependencies"
RECOMMENDATIONS = "/api/path-steps/recommendations"
STATS = "/api/path-steps/stats"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=list(UIDS))


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: FastHTMLApp) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        for user in (READER, OTHER):
            await session.run(
                "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.title = $uid", uid=user
            )
        await session.run(
            """
            UNWIND $steps AS uid
            MERGE (s:Entity:PathStep {uid: uid})
            SET s.title = uid, s.entity_type = 'path_step', s.status = 'active',
                s.created_at = $stamp, s.updated_at = $stamp
            """,
            steps=list(_STEPS),
            stamp=_STAMP,
        )
        await session.run(
            "MATCH (s:PathStep {uid: $uid}) SET s.publication_state = 'draft'", uid=DRAFT
        )
        await session.run(
            """
            UNWIND $goals AS uid
            MERGE (g:Entity:Goal {uid: uid})
            SET g.title = $title, g.entity_type = 'goal', g.status = 'active',
                g.user_uid = $other, g.created_at = $stamp, g.updated_at = $stamp
            """,
            goals=list(_ALL_GOALS),
            title=PRIVATE_TITLE,
            other=OTHER,
            stamp=_STAMP,
        )
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $ku})
            SET k.title = $ku, k.entity_type = 'ku', k.status = 'active',
                k.created_at = $stamp, k.updated_at = $stamp
            MERGE (e:Entity:Exercise {uid: $exercise})
            SET e.title = $exercise, e.entity_type = 'exercise', e.status = 'active',
                e.created_at = $stamp, e.updated_at = $stamp
            """,
            ku=KU,
            exercise=EXERCISE,
            stamp=_STAMP,
        )
        await session.run(
            """
            MATCH (t:PathStep {uid: $target}), (s:PathStep {uid: $by_step}),
                  (k:PathStep {uid: $by_knowledge}), (b:PathStep {uid: $by_both}),
                  (h:PathStep {uid: $two_hops}), (d:PathStep {uid: $draft}),
                  (y:PathStep {uid: $beyond}), (concept:Ku {uid: $ku}),
                  (e:Exercise {uid: $exercise}), (g:Goal {uid: $goal})
            MERGE (s)-[:REQUIRES_STEP]->(t)
            MERGE (k)-[:REQUIRES_KNOWLEDGE]->(t)
            MERGE (b)-[:REQUIRES_STEP]->(t)
            MERGE (b)-[:REQUIRES_KNOWLEDGE]->(t)
            MERGE (h)-[:REQUIRES_STEP]->(s)
            MERGE (d)-[:REQUIRES_STEP]->(t)
            MERGE (d)-[:REQUIRES_KNOWLEDGE]->(t)
            MERGE (y)-[:REQUIRES_STEP]->(d)
            MERGE (t)-[:REQUIRES_STEP]->(t)
            MERGE (concept)-[:REQUIRES_KNOWLEDGE]->(t)
            MERGE (e)-[:REQUIRES_KNOWLEDGE]->(t)
            MERGE (g)-[:REQUIRES_KNOWLEDGE]->(t)
            """,
            target=TARGET,
            by_step=BY_STEP,
            by_knowledge=BY_KNOWLEDGE,
            by_both=BY_BOTH,
            two_hops=TWO_HOPS,
            draft=DRAFT,
            beyond=BEYOND_DRAFT,
            ku=KU,
            exercise=EXERCISE,
            goal=PRIVATE_GOAL,
        )
        await session.run(
            """
            MATCH (c:PathStep {uid: $crowded})
            UNWIND $dependents AS uid
            MATCH (n:Entity {uid: uid})
            MERGE (n)-[:REQUIRES_KNOWLEDGE]->(c)
            """,
            crowded=CROWDED,
            dependents=[*GOALS, *CROWD],
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: FastHTMLApp, graph: AsyncDriver) -> FastHTMLApp:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="psdependents-test-key")
    await _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


def _client(app: FastHTMLApp) -> httpx.AsyncClient:
    token = mint_token()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=120,
    )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def anonymous(app: FastHTMLApp) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def reader(app: FastHTMLApp) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        assert (await client.get(f"/sign-in/{READER}")).status_code == 200
        yield client


async def _uids(client: httpx.AsyncClient, path: str, **params: str) -> list[str]:
    response = await client.get(path, params=params)
    assert response.status_code == 200, response.text[:300]
    return [step["uid"] for step in response.json()]


async def _dependent_count(client: httpx.AsyncClient, uid: str) -> int:
    response = await client.get(STATS, params={"uid": uid})
    assert response.status_code == 200, response.text[:300]
    count: int = response.json()["dependent_count"]
    return count


async def test_the_door_names_each_step_requiring_this_one_once_by_either_edge(
    reader: httpx.AsyncClient,
) -> None:
    assert await _uids(reader, DEPENDENTS, uid=TARGET) == [BY_BOTH, BY_KNOWLEDGE, BY_STEP]


async def test_what_requires_a_step_and_is_not_one_is_not_disclosed(
    reader: httpx.AsyncClient,
) -> None:
    response = await reader.get(DEPENDENTS, params={"uid": TARGET})

    assert PRIVATE_TITLE not in response.text
    assert PRIVATE_GOAL not in response.text


async def test_stats_counts_exactly_what_the_door_names(reader: httpx.AsyncClient) -> None:
    assert await _dependent_count(reader, TARGET) == 3


async def test_a_step_nothing_requires_answers_empty_and_counts_zero(
    reader: httpx.AsyncClient,
) -> None:
    assert await _uids(reader, DEPENDENTS, uid=LEAF) == []
    assert await _dependent_count(reader, LEAF) == 0


async def test_a_page_of_dependents_is_all_steps_and_the_count_is_not_paged(
    reader: httpx.AsyncClient,
) -> None:
    """Twelve goals on the same step take none of the ten slots."""
    assert await _uids(reader, DEPENDENTS, uid=CROWDED) == list(CROWD[:10])
    assert await _dependent_count(reader, CROWDED) == 12


async def test_a_draft_step_still_reads_its_own_dependents(reader: httpx.AsyncClient) -> None:
    """The caller named the draft, so it is not what the gate withholds here."""
    assert await _uids(reader, DEPENDENTS, uid=DRAFT) == [BEYOND_DRAFT]


async def test_published_curriculum_answers_a_signed_out_reader_the_same(
    anonymous: httpx.AsyncClient,
) -> None:
    assert await _uids(anonymous, DEPENDENTS, uid=TARGET) == [BY_BOTH, BY_KNOWLEDGE, BY_STEP]


@pytest.mark.parametrize("uid", ["ps.psdependents.missing", KU])
async def test_what_is_not_a_step_answers_not_found(reader: httpx.AsyncClient, uid: str) -> None:
    assert (await reader.get(DEPENDENTS, params={"uid": uid})).status_code == 404


async def test_recommendations_answer_from_the_same_read(reader: httpx.AsyncClient) -> None:
    assert await _uids(reader, RECOMMENDATIONS, uid=TARGET) == [BY_BOTH, BY_KNOWLEDGE, BY_STEP]


@pytest.mark.parametrize(
    ("params", "size"),
    [({}, 10), ({"type": ""}, 10), ({"type": "learning"}, 10), ({"type": "next"}, 5)],
)
async def test_recommendations_take_their_type(
    reader: httpx.AsyncClient, params: dict[str, str], size: int
) -> None:
    assert await _uids(reader, RECOMMENDATIONS, uid=CROWDED, **params) == list(CROWD[:size])


async def test_recommendations_refuse_a_type_they_do_not_know(reader: httpx.AsyncClient) -> None:
    response = await reader.get(RECOMMENDATIONS, params={"uid": TARGET, "type": "banana"})

    assert response.status_code == 400, response.text[:300]
