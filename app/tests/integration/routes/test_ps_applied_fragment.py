"""How you've applied this, over a real graph.

The PathStep page mounts ``/explore/ps/{uid}/applied`` for a signed-in reader; the
fragment scores the step's Kus against the reader's rich context (the MEGA-QUERY over
this graph). Seeded: a step teaching two Kus through two different composition edges,
the reader's two tasks applying one of them, another learner's task applying the other,
a step teaching no Ku, and a step the reader has applied nothing from.
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

READER = seed_user_uid("psapplied_reader")
OTHER = seed_user_uid("psapplied_other")
STEP = "ps.psapplied.step"
STEP_NO_KU = "ps.psapplied.no-ku"
STEP_UNAPPLIED = "ps.psapplied.unapplied"
KU_APPLIED = "ku.psapplied.applied"
KU_OTHERS = "ku.psapplied.others"
KU_UNAPPLIED = "ku.psapplied.unapplied"
TASK_ONE = "task.psapplied-one"
TASK_TWO = "task.psapplied-two"
TASK_OTHER = "task.psapplied-other"
UIDS = (
    READER,
    OTHER,
    STEP,
    STEP_NO_KU,
    STEP_UNAPPLIED,
    KU_APPLIED,
    KU_OTHERS,
    KU_UNAPPLIED,
    TASK_ONE,
    TASK_TWO,
    TASK_OTHER,
)
_STAMP = "2000-01-01T00:00:00+00:00"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids OR n.user_uid IN $users DETACH DELETE n",
            uids=list(UIDS),
            users=[READER, OTHER],
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: FastHTMLApp) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        for user in (READER, OTHER):
            await session.run(
                "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.title = $uid", uid=user
            )
        for uid, title in (
            (KU_APPLIED, "psapplied concept in practice"),
            (KU_OTHERS, "psapplied concept another learner practises"),
            (KU_UNAPPLIED, "psapplied concept nobody practises"),
        ):
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                SET k.title = $title, k.entity_type = 'ku', k.status = 'active',
                    k.created_at = $stamp, k.updated_at = $stamp
                """,
                uid=uid,
                title=title,
                stamp=_STAMP,
            )
        for uid, title in (
            (STEP, "psapplied step"),
            (STEP_NO_KU, "psapplied step teaching nothing"),
            (STEP_UNAPPLIED, "psapplied step not yet applied"),
        ):
            await session.run(
                """
                MERGE (s:Entity:PathStep {uid: $uid})
                SET s.title = $title, s.entity_type = 'path_step', s.status = 'active',
                    s.created_at = $stamp, s.updated_at = $stamp
                """,
                uid=uid,
                title=title,
                stamp=_STAMP,
            )
        for uid, owner, ku in (
            (TASK_ONE, READER, KU_APPLIED),
            (TASK_TWO, READER, KU_APPLIED),
            (TASK_OTHER, OTHER, KU_OTHERS),
        ):
            await session.run(
                """
                MATCH (u:User {uid: $owner}), (k:Ku {uid: $ku})
                CREATE (t:Entity:Task {uid: $uid})
                SET t.title = $uid, t.entity_type = 'task', t.user_uid = $owner,
                    t.status = 'active', t.created_at = $stamp, t.updated_at = $stamp
                MERGE (u)-[:OWNS]->(t)
                MERGE (t)-[:APPLIES_KNOWLEDGE]->(k)
                """,
                uid=uid,
                owner=owner,
                ku=ku,
                stamp=_STAMP,
            )
        await session.run(
            """
            MATCH (s:PathStep {uid: $step}), (a:Ku {uid: $applied}), (o:Ku {uid: $others}),
                  (un:PathStep {uid: $unapplied_step}), (nobody:Ku {uid: $unapplied})
            MERGE (s)-[:USES_KU]->(a)
            MERGE (s)-[:TRAINS_KU]->(o)
            MERGE (un)-[:USES_KU]->(nobody)
            """,
            step=STEP,
            applied=KU_APPLIED,
            others=KU_OTHERS,
            unapplied_step=STEP_UNAPPLIED,
            unapplied=KU_UNAPPLIED,
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: FastHTMLApp, graph: AsyncDriver) -> FastHTMLApp:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="psapplied-test-key")
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


async def test_the_page_mounts_the_section_for_a_signed_in_reader(
    reader: httpx.AsyncClient, anonymous: httpx.AsyncClient
) -> None:
    signed_in = await reader.get(f"/explore/ps/{STEP}/content")
    signed_out = await anonymous.get(f"/explore/ps/{STEP}/content")

    assert signed_in.status_code == 200, signed_in.text[:300]
    assert f'hx-get="/explore/ps/{STEP}/applied"' in signed_in.text
    assert signed_out.status_code == 200, signed_out.text[:300]
    assert "/applied" not in signed_out.text


async def test_the_fragment_needs_a_signed_in_reader(anonymous: httpx.AsyncClient) -> None:
    assert (await anonymous.get(f"/explore/ps/{STEP}/applied")).status_code == 401


async def test_each_ku_reads_this_learners_activity_and_no_one_elses(
    reader: httpx.AsyncClient,
) -> None:
    fragment = await reader.get(f"/explore/ps/{STEP}/applied")

    assert fragment.status_code == 200, fragment.text[:300]
    text = fragment.text
    assert f'href="/explore/ku/{KU_APPLIED}"' in text
    assert "psapplied concept in practice" in text
    # Two tasks at the tasks channel's 0.05 each.
    assert "Applied 10%" in text
    # A composition edge other than USES_KU counts, and another learner's task does not.
    assert f'href="/explore/ku/{KU_OTHERS}"' in text
    assert "Applied 0%" in text


async def test_a_step_with_nothing_applied_says_how_to_change_that(
    reader: httpx.AsyncClient,
) -> None:
    fragment = await reader.get(f"/explore/ps/{STEP_UNAPPLIED}/applied")

    assert fragment.status_code == 200, fragment.text[:300]
    assert "Theoretical only" in fragment.text
    assert "Link a task, habit, event, choice or principle" in fragment.text
    assert "Applied 0%" not in fragment.text


@pytest.mark.parametrize("uid", [STEP_NO_KU, "ps.psapplied.names-nothing"])
async def test_a_step_teaching_nothing_leaves_no_section(
    reader: httpx.AsyncClient, uid: str
) -> None:
    fragment = await reader.get(f"/explore/ps/{uid}/applied")

    assert fragment.status_code == 200, fragment.text[:300]
    assert 'id="ps-applied-fragment"' in fragment.text
    assert "applied this" not in fragment.text


async def test_the_json_door_answers_the_same_reading(reader: httpx.AsyncClient) -> None:
    door = await reader.get("/api/path-steps/my-context", params={"uid": STEP})

    assert door.status_code == 200, door.text[:300]
    body = door.json()
    rows = {row["ku_uid"]: row for row in body["underlying_kus"]}
    assert rows[KU_APPLIED]["ku_title"] == "psapplied concept in practice"
    assert rows[KU_APPLIED]["substance_score"] == 0.1
    assert rows[KU_OTHERS]["substance_score"] == 0.0
    assert body["taught_kus_count"] == 2
