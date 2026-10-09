"""The Insights cards over real HTTP — the hub methods' first door, for a real user.

The section on ``/insights`` mounts one fragment per ``HubQuestion``; each
``/insights/hub/{question}`` builds the hub from the caller's rich context (the
MEGA-QUERY over this graph) and answers as a card. Seeded for one user: an overdue
task (what fits right now names it), a Ku in progress whose prerequisite is
unmastered (what unlocks the most names the prerequisite — a Ku the context carries
no title for, so the card's Ku batch resolves it), and a Ku in progress with no
prerequisites (ready to learn). No life path, no check-ins: the alignment and
perception cards answer with their truthful empty states, never a 500.

Everything is measured over real HTTP against the whole wired route tree; a card
over a stub entity would prove nothing (the F7b lesson).
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
from core.models.enums import HubQuestion

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

USER = "user_hubc_learner"
TASK = "task_hubc_overdue"
KU_PREREQ = "ku.hubc.prereq"
KU_BLOCKED = "ku.hubc.blocked"
KU_READY = "ku.hubc.ready"
UIDS = (USER, TASK, KU_PREREQ, KU_BLOCKED, KU_READY)


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids OR n.user_uid = $user DETACH DELETE n",
            uids=list(UIDS),
            user=USER,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        # The rich context resolves its owner through the User model, which needs a title.
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.title = $uid", uid=USER
        )
        await session.run(
            """
            MATCH (u:User {uid: $u})
            MERGE (t:Entity:Task {uid: $t})
            SET t.title = 'hubc overdue task', t.entity_type = 'task', t.user_uid = $u,
                t.status = 'active', t.due_date = '2000-01-02', t.priority = 'high',
                t.created_at = '2000-01-01T00:00:00+00:00',
                t.updated_at = '2000-01-01T00:00:00+00:00'
            MERGE (u)-[:OWNS]->(t)
            """,
            u=USER,
            t=TASK,
        )
        await session.run(
            """
            MATCH (u:User {uid: $u})
            UNWIND [[$prereq, 'hubc prerequisite concept'],
                    [$blocked, 'hubc blocked concept'],
                    [$ready, 'hubc ready concept']] AS row
            MERGE (k:Entity:Ku {uid: row[0]})
            SET k.title = row[1], k.entity_type = 'ku', k.status = 'active',
                k.created_at = '2000-01-01T00:00:00+00:00',
                k.updated_at = '2000-01-01T00:00:00+00:00'
            WITH u
            MATCH (blocked:Ku {uid: $blocked}), (prereq:Ku {uid: $prereq}), (ready:Ku {uid: $ready})
            MERGE (blocked)-[:REQUIRES_KNOWLEDGE]->(prereq)
            MERGE (u)-[:IN_PROGRESS {started_at: '2000-01-03T00:00:00+00:00'}]->(blocked)
            MERGE (u)-[:IN_PROGRESS {started_at: '2000-01-03T00:00:00+00:00'}]->(ready)
            """,
            u=USER,
            prereq=KU_PREREQ,
            blocked=KU_BLOCKED,
            ready=KU_READY,
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: Any, graph: AsyncDriver) -> Any:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="hubc-test-key")
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
        timeout=120,
    )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def anonymous(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def learner(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        assert (await client.get(f"/sign-in/{USER}")).status_code == 200
        yield client


async def test_the_page_mounts_one_fragment_per_question(learner: httpx.AsyncClient) -> None:
    page = await learner.get("/insights")
    assert page.status_code == 200
    assert 'id="insights-hub"' in page.text
    for question in HubQuestion:
        assert f'hx-get="{question.fragment_url()}"' in page.text, question


async def test_a_fragment_needs_a_signed_in_user(anonymous: httpx.AsyncClient) -> None:
    assert (await anonymous.get("/insights/hub/right-now")).status_code == 401


async def test_a_question_that_does_not_exist_is_404(learner: httpx.AsyncClient) -> None:
    assert (await learner.get("/insights/hub/critical-path")).status_code == 404


@pytest.mark.parametrize("question", list(HubQuestion))
async def test_every_card_answers_for_a_real_user(
    learner: httpx.AsyncClient, question: HubQuestion
) -> None:
    card = await learner.get(question.fragment_url())
    assert card.status_code == 200, card.text[:300]
    assert f'id="{question.mount_id()}"' in card.text
    assert question.label() in card.text
    assert "couldn't be answered" not in card.text, card.text[:500]


async def test_what_fits_right_now_names_the_overdue_task(learner: httpx.AsyncClient) -> None:
    card = await learner.get(HubQuestion.RIGHT_NOW.fragment_url())
    assert "hubc overdue task" in card.text
    assert f'href="/tasks/detail?uid={TASK}"' in card.text
    assert "This task is overdue" in card.text
    assert f"Overdue Task: {TASK}" not in card.text


async def test_what_unlocks_the_most_names_the_unmastered_prerequisite(
    learner: httpx.AsyncClient,
) -> None:
    card = await learner.get(HubQuestion.UNBLOCK_FIRST.fragment_url())
    # The prerequisite is not in progress, so the context holds no title for it:
    # the card's Ku batch resolved it.
    assert "hubc prerequisite concept" in card.text
    assert f'href="/explore/ku/{KU_PREREQ}"' in card.text
    assert "unlocks 1 unit" in card.text


async def test_what_to_learn_next_offers_the_prerequisite_first(
    learner: httpx.AsyncClient,
) -> None:
    """The unmastered concept nothing stands before — and that unlocks the blocked one.

    The two concepts in progress are the learner's current study, not an offer;
    the prerequisite is the one the ranking puts first, with what it unlocks.
    """
    card = await learner.get(HubQuestion.LEARN_NEXT.fragment_url())
    assert "hubc prerequisite concept" in card.text
    assert f'href="/explore/ku/{KU_PREREQ}"' in card.text
    assert "unlocks 1" in card.text
    assert "Knowledge Unit ku." not in card.text


async def test_alignment_without_a_life_path_points_at_designating_one(
    learner: httpx.AsyncClient,
) -> None:
    card = await learner.get(HubQuestion.ALIGNMENT.fragment_url())
    assert "haven't designated a life path" in card.text
    assert 'href="/lifepath"' in card.text


async def test_perception_without_checkins_points_at_the_self_checkin(
    learner: httpx.AsyncClient,
) -> None:
    card = await learner.get(HubQuestion.PERCEPTION.fragment_url())
    assert "No self-assessments yet" in card.text
    assert 'href="/self-checkin"' in card.text
