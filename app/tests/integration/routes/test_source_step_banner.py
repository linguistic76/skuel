"""An activity's source-step banner names a step its owner may read, over real HTTP.

An activity spawned by engaging a PathStep carries ``source_path_step_uid``, and its
detail page renders "From learning step: <title>" from it
(``ConnectionFetchBackend.fetch_source_pathstep``). The property is a plain uid a
vault file can write verbatim, so the reader decides what it shows:

- a published step (no ``publication_state``, or one marked published) shows;
- a draft step shows only to an owner who has ``ENGAGED_WITH`` it — a learner who
  started a step keeps seeing where the activity came from after it is unpublished;
- a draft step nobody engaged shows nothing, exactly as a uid that names no step.

The tasks routes are registered through the bootstrap's own entry point over the
composed app's services, on a ``fast_app`` with real session middleware and a
sign-in route.
"""

from __future__ import annotations

import re

import httpx
import pytest
import pytest_asyncio
from neo4j import AsyncDriver
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import PublicationState

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

CALLER = "user_nb2fr_caller"
BANNER = "From learning step"

# step uid -> (publication_state, whether CALLER engaged it)
STEPS: dict[str, tuple[PublicationState | None, bool]] = {
    "ps.nb2fr.no-state": (None, False),
    "ps.nb2fr.published": (PublicationState.PUBLISHED, False),
    "ps.nb2fr.draft": (PublicationState.DRAFT, False),
    "ps.nb2fr.draft-engaged": (PublicationState.DRAFT, True),
}
MISSING_STEP = "ps.nb2fr.missing"


def _title(step_uid: str) -> str:
    return f"title of {step_uid}"


def _task(step_uid: str) -> str:
    return f"task_nb2fr_{step_uid.rsplit('.', 1)[-1]}"


_TASKS = [_task(uid) for uid in (*STEPS, MISSING_STEP)]


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[CALLER, *STEPS, *_TASKS],
        )


@pytest_asyncio.fixture(loop_scope="session")
async def driver(skuel_app) -> AsyncDriver:
    """One user, four steps (two published, two draft), one task naming each — and one
    naming a step that does not exist."""
    graph: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(graph)
    async with graph.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=CALLER)
        for step_uid, (state, engaged) in STEPS.items():
            await session.run(
                """
                MERGE (s:Entity:PathStep {uid: $uid})
                SET s.title = $title, s.entity_type = 'path_step', s.status = 'active',
                    s.publication_state = $state
                WITH s
                MATCH (u:User {uid: $user})
                FOREACH (_ IN CASE WHEN $engaged THEN [1] ELSE [] END |
                    MERGE (u)-[:ENGAGED_WITH {uid: $uid + '-engagement', state: 'active'}]->(s))
                """,
                uid=step_uid,
                title=_title(step_uid),
                state=state.value if state else None,
                user=CALLER,
                engaged=engaged,
            )
        for step_uid in (*STEPS, MISSING_STEP):
            await session.run(
                """
                MATCH (u:User {uid: $user})
                MERGE (t:Entity:Task {uid: $uid})
                SET t.title = 'a spawned task', t.entity_type = 'task', t.status = 'active',
                    t.priority = 'medium', t.user_uid = $user, t.source_path_step_uid = $step
                MERGE (u)-[:OWNS]->(t)
                """,
                uid=_task(step_uid),
                user=CALLER,
                step=step_uid,
            )
    yield graph
    await _wipe(graph)


def _app(skuel_app):
    from fasthtml.common import fast_app

    from adapters.inbound.tasks_routes import create_tasks_routes

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="nb2fr-source-step-test-key")
    create_tasks_routes(app, rt, skuel_app.state.services)

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


@pytest_asyncio.fixture(loop_scope="session")
async def client(skuel_app, driver):
    """An HTTP client signed in as ``CALLER``."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(skuel_app)), base_url="http://test"
    ) as http:
        assert (await http.get(f"/sign-in/{CALLER}")).status_code == 200
        yield http


# A picker on the page mints a fresh 8-hex id per render.
_RENDER_ID = re.compile(r"-[0-9a-f]{8}\b")


async def _detail(client: httpx.AsyncClient, step_uid: str) -> str:
    response = await client.get(f"/tasks/detail/content?uid={_task(step_uid)}")
    assert response.status_code == 200, response.text
    return _RENDER_ID.sub("-<id>", response.text.replace(_task(step_uid), "<task>"))


@pytest.mark.parametrize("step_uid", ["ps.nb2fr.no-state", "ps.nb2fr.published"])
async def test_a_published_step_names_the_activitys_origin(
    client: httpx.AsyncClient, step_uid: str
) -> None:
    body = await _detail(client, step_uid)

    assert BANNER in body
    assert _title(step_uid) in body


async def test_a_draft_step_the_owner_engaged_still_names_the_origin(
    client: httpx.AsyncClient,
) -> None:
    body = await _detail(client, "ps.nb2fr.draft-engaged")

    assert BANNER in body
    assert _title("ps.nb2fr.draft-engaged") in body


async def test_a_draft_step_nobody_engaged_renders_as_a_missing_step(
    client: httpx.AsyncClient,
) -> None:
    draft = await _detail(client, "ps.nb2fr.draft")
    missing = await _detail(client, MISSING_STEP)

    assert BANNER not in draft
    assert _title("ps.nb2fr.draft") not in draft
    assert BANNER not in missing
    assert draft == missing
