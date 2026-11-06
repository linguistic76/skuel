"""The PathStep page's relationship graph, over a real graph.

The page hands the graph the registry's edge types for a PathStep, the same vocabulary
``/api/path-steps/context`` traverses. Without them the route draws lateral edges only,
and a step's connections are composition, prerequisites and path membership. Seeded: a
step teaching a Ku, requiring a step, sitting in a path, with a draft prerequisite.
"""

from __future__ import annotations

import html
import json
import re
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

READER = seed_user_uid("psgraph_reader")
STEP = "ps.psgraph.step"
PREREQUISITE = "ps.psgraph.prerequisite"
DRAFT = "ps.psgraph.draft"
KU = "ku.psgraph.concept"
PATH = "lp.psgraph.path"
UIDS = (READER, STEP, PREREQUISITE, DRAFT, KU, PATH)
_STAMP = "2000-01-01T00:00:00+00:00"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=list(UIDS))


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: FastHTMLApp) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.title = $uid", uid=READER
        )
        for uid, label, kind in (
            (STEP, "PathStep", "path_step"),
            (PREREQUISITE, "PathStep", "path_step"),
            (DRAFT, "PathStep", "path_step"),
            (KU, "Ku", "ku"),
            (PATH, "LearningPath", "learning_path"),
        ):
            await session.run(
                f"""
                MERGE (n:Entity:{label} {{uid: $uid}})
                SET n.title = $uid, n.entity_type = $kind, n.status = 'active',
                    n.created_at = $stamp, n.updated_at = $stamp
                """,
                uid=uid,
                kind=kind,
                stamp=_STAMP,
            )
        await session.run(
            """
            MATCH (s:PathStep {uid: $step}), (p:PathStep {uid: $prerequisite}),
                  (d:PathStep {uid: $draft}), (k:Ku {uid: $ku}), (l:LearningPath {uid: $path})
            SET d.publication_state = 'draft'
            MERGE (s)-[:USES_KU]->(k)
            MERGE (s)-[:REQUIRES_STEP]->(p)
            MERGE (s)-[:REQUIRES_STEP]->(d)
            MERGE (l)-[:HAS_STEP]->(s)
            """,
            step=STEP,
            prerequisite=PREREQUISITE,
            draft=DRAFT,
            ku=KU,
            path=PATH,
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: FastHTMLApp, graph: AsyncDriver) -> FastHTMLApp:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="psgraph-test-key")
    await _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def reader(app: FastHTMLApp) -> AsyncIterator[httpx.AsyncClient]:
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=120,
    ) as client:
        assert (await client.get(f"/sign-in/{READER}")).status_code == 200
        yield client


async def _page_types(reader: httpx.AsyncClient) -> str:
    """The types the rendered page hands the graph, read from the page itself."""
    page = await reader.get(f"/explore/ps/{STEP}/content")
    assert page.status_code == 200, page.text[:300]
    match = re.search(r"""x-data=(['"])relationshipGraph\((.*?)\)\1""", page.text, re.DOTALL)
    assert match, page.text[:300]
    types: str = json.loads(f"[{html.unescape(match.group(2))}]")[3]
    return types


async def test_the_page_draws_the_steps_real_connections(reader: httpx.AsyncClient) -> None:
    drawn = await reader.get(
        f"/api/ps/{STEP}/lateral/graph", params={"depth": 1, "types": await _page_types(reader)}
    )

    assert drawn.status_code == 200, drawn.text[:300]
    assert {node["id"] for node in drawn.json()["nodes"]} == {STEP, KU, PREREQUISITE, PATH}


async def test_a_draft_stays_off_the_graph(reader: httpx.AsyncClient) -> None:
    drawn = await reader.get(
        f"/api/ps/{STEP}/lateral/graph", params={"depth": 2, "types": await _page_types(reader)}
    )

    assert DRAFT not in {node["id"] for node in drawn.json()["nodes"]}


async def test_without_the_types_the_same_step_is_one_dot(reader: httpx.AsyncClient) -> None:
    """Why the page names them: none of this step's edges is a lateral one."""
    drawn = await reader.get(f"/api/ps/{STEP}/lateral/graph", params={"depth": 2})

    assert [node["id"] for node in drawn.json()["nodes"]] == [STEP]
