"""``/lp/{uid}`` — the one learning path detail page.

A signed-in learner sees their progress or Enroll, every visitor sees the path's
step tree (path → steps → Kus, read-only), and a uid that names no learning path is
the 404; ``/pathways/path/{uid}`` is not a route. Everything is measured over real
HTTP against the whole wired route tree.

The seeded path has two steps; the first composes two Kus, one of them a draft — a
step's own composition rides along with it (containment), as on the step's page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier

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

LEARNER = "user_lp1_learner"
ENROLLER = "user_lp1_enroller"
USERS = (LEARNER, ENROLLER)

PATH = "lp.lp1.path"
STEP_1 = "ps.lp1.first"
STEP_2 = "ps.lp1.second"
KU_A = "ku.lp1.alpha"
KU_DRAFT = "ku.lp1.draft"
TASK = "task_lp1_own"
CURRICULUM = (PATH, STEP_1, STEP_2, KU_A, KU_DRAFT)


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n.uid IN $uids OR n.user_uid IN $users
            DETACH DELETE n
            """,
            uids=[*USERS, *CURRICULUM, TASK],
            users=list(USERS),
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        for uid in USERS:
            await session.run("MERGE (u:User {uid: $uid}) SET u.username = $uid", uid=uid)
        await session.run(
            """
            MERGE (p:Entity:LearningPath {uid: $path})
            SET p.title = 'lp1 path title', p.entity_type = 'learning_path',
                p.description = 'lp1 path description', p.outcomes = ['lp1 outcome'],
                p.created_at = '2000-01-01T00:00:00+00:00',
                p.updated_at = '2000-01-01T00:00:00+00:00'
            WITH p
            UNWIND [[$s1, 'lp1 first step', 1], [$s2, 'lp1 second step', 2]] AS row
            MERGE (s:Entity:PathStep {uid: row[0]})
            SET s.title = row[1], s.entity_type = 'path_step',
                s.created_at = '2000-01-01T00:00:00+00:00',
                s.updated_at = '2000-01-01T00:00:00+00:00'
            MERGE (p)-[:HAS_STEP {sequence: row[2]}]->(s)
            """,
            path=PATH,
            s1=STEP_1,
            s2=STEP_2,
        )
        await session.run(
            """
            MATCH (s:PathStep {uid: $s1})
            UNWIND [[$a, 'lp1 alpha ku', null], [$d, 'lp1 draft ku', 'draft']] AS row
            MERGE (k:Entity:Ku {uid: row[0]})
            SET k.title = row[1], k.entity_type = 'ku', k.publication_state = row[2],
                k.created_at = '2000-01-01T00:00:00+00:00',
                k.updated_at = '2000-01-01T00:00:00+00:00'
            MERGE (s)-[:USES_KU]->(k)
            """,
            s1=STEP_1,
            a=KU_A,
            d=KU_DRAFT,
        )
        # Both learners have mastered the first step, not the second.
        await session.run(
            """
            MATCH (u:User) WHERE u.uid IN $users
            MATCH (s:PathStep {uid: $s1})
            MERGE (u)-[:MASTERED]->(s)
            """,
            users=list(USERS),
            s1=STEP_1,
        )
        # A non-path the learner owns — a uid the page must not read as a path.
        await session.run(
            """
            MATCH (u:User {uid: $u})
            MERGE (t:Entity:Task {uid: $t})
            SET t.title = 'lp1 own task', t.entity_type = 'task', t.user_uid = $u,
                t.status = 'active'
            MERGE (u)-[:OWNS]->(t)
            """,
            u=LEARNER,
            t=TASK,
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: Any, graph: AsyncDriver) -> Any:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="lp1-test-key")
    await _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


def _client(app: Any) -> httpx.AsyncClient:
    token = mint_token()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=60,
    )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def anonymous(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def learner(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        assert (await client.get(f"/sign-in/{LEARNER}")).status_code == 200
        yield client


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def enroller(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        assert (await client.get(f"/sign-in/{ENROLLER}")).status_code == 200
        yield client


async def test_the_page_is_a_shell_that_loads_the_path(anonymous: httpx.AsyncClient) -> None:
    page = await anonymous.get(f"/lp/{PATH}")
    assert page.status_code == 200
    assert f"/lp/{PATH}/content" in page.text


async def test_an_anonymous_visitor_sees_the_path_and_a_sign_in_link(
    anonymous: httpx.AsyncClient,
) -> None:
    body = await anonymous.get(f"/lp/{PATH}/content")
    assert body.status_code == 200
    for text in ("lp1 path title", "lp1 path description", "lp1 outcome", "Sign in to enroll"):
        assert text in body.text, text
    assert "/api/pathways/enroll/" not in body.text
    assert "Mastered" not in body.text
    # The steps, in path order, each linking its own page.
    first, second = body.text.index("lp1 first step"), body.text.index("lp1 second step")
    assert first < second
    for step in (STEP_1, STEP_2):
        assert f'href="/explore/ps/{step}"' in body.text, step


async def test_a_signed_in_learner_sees_enroll_and_their_mastered_step(
    learner: httpx.AsyncClient,
) -> None:
    body = await learner.get(f"/lp/{PATH}/content")
    assert body.status_code == 200
    assert f'hx-post="/api/pathways/enroll/{PATH}"' in body.text
    assert "Sign in to enroll" not in body.text
    # The badge sits on the first step's row only.
    rows = body.text.split('class="tree-node"')
    mastered_rows = [row for row in rows if "Mastered" in row]
    assert len(mastered_rows) == 1
    assert STEP_1 in mastered_rows[0]


async def test_enrolling_returns_to_the_path_page_with_the_learners_progress(
    enroller: httpx.AsyncClient,
) -> None:
    before = await enroller.get(f"/lp/{PATH}/content")
    assert "% complete" not in before.text

    enrolled = await enroller.post(f"/api/pathways/enroll/{PATH}")
    assert enrolled.status_code == 200
    assert enrolled.headers["HX-Redirect"] == f"/lp/{PATH}"

    after = await enroller.get(f"/lp/{PATH}/content")
    assert "50% complete" in after.text
    assert "/api/pathways/enroll/" not in after.text

    # The dashboard's card for the path counts the same mastered step, and names
    # the first one still to do.
    dashboard = await enroller.get("/pathways/content")
    assert "50.0% Complete" in dashboard.text
    assert "Current: lp1 second step" in dashboard.text


async def test_the_tree_rows_are_read_only(learner: httpx.AsyncClient) -> None:
    body = await learner.get(f"/lp/{PATH}/content")
    assert "hierarchyTree(" in body.text
    for handler in ("handleDragStart", "handleDrop", "startEdit", 'draggable="true"'):
        assert handler not in body.text, handler


@pytest.mark.parametrize("client_name", ["anonymous", "learner"])
async def test_a_step_expands_to_its_kus_drafts_included(
    client_name: str, request: pytest.FixtureRequest
) -> None:
    client: httpx.AsyncClient = request.getfixturevalue(client_name)
    kus = await client.get(f"/api/lp/{STEP_1}/children", params={"parent_depth": 0})
    assert kus.status_code == 200
    for ku in (KU_A, KU_DRAFT):
        assert f'href="/explore/ku/{ku}"' in kus.text, ku
    # A Ku is a leaf: no expander, no lazy load beneath it.
    assert 'data-has-children="true"' not in kus.text

    empty = await client.get(f"/api/lp/{STEP_2}/children", params={"parent_depth": 0})
    assert empty.status_code == 200
    assert "No items" in empty.text


async def test_the_lazy_load_still_answers_a_path_with_its_steps(
    anonymous: httpx.AsyncClient,
) -> None:
    steps = await anonymous.get(f"/api/lp/{PATH}/children", params={"parent_depth": -1})
    assert steps.status_code == 200
    for step in (STEP_1, STEP_2):
        assert f'href="/explore/ps/{step}"' in steps.text, step


@pytest.mark.parametrize("uid", [KU_A, TASK, "lp.lp1.absent"])
async def test_the_lazy_load_refuses_anything_but_a_path_or_a_step(
    learner: httpx.AsyncClient, uid: str
) -> None:
    refused = await learner.get(f"/api/lp/{uid}/children")
    assert refused.status_code == 404
    assert "lp1 own task" not in refused.text


@pytest.mark.parametrize("uid", [STEP_1, KU_A, TASK, "lp.lp1.absent"])
@pytest.mark.parametrize("client_name", ["anonymous", "learner"])
async def test_a_uid_that_names_no_path_is_the_404(
    client_name: str, uid: str, request: pytest.FixtureRequest
) -> None:
    client: httpx.AsyncClient = request.getfixturevalue(client_name)
    refused = await client.get(f"/lp/{uid}/content")
    assert refused.status_code == 404
    assert "Learning path not found" in refused.text
    assert "lp1 own task" not in refused.text


@pytest.mark.parametrize("url", [f"/pathways/path/{PATH}", f"/pathways/path/{PATH}/content"])
async def test_pathways_path_is_not_a_route(learner: httpx.AsyncClient, url: str) -> None:
    assert (await learner.get(url)).status_code == 404


async def test_the_path_cards_link_the_lp_page(learner: httpx.AsyncClient) -> None:
    browse = await learner.get("/pathways/browse/content")
    assert browse.status_code == 200
    assert f'href="/lp/{PATH}"' in browse.text
    assert "/pathways/path/" not in browse.text
