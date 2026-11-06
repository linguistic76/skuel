"""Blocking dependencies, over a real graph.

The PathStep page seeds its accordion from one read: the step's published direct
prerequisites, each with whether this reader completed it. Mike's ruling (2026-11-06):
completed is the rule the page's hero card uses, marked as read or mastered, so a learner
never sees a step shown as Completed while it still blocks the next one. The module pins
that against the hero card itself, for every state a prerequisite can be in.
"""

from __future__ import annotations

import html
import json
import re
from typing import TYPE_CHECKING, TypedDict

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

READER = seed_user_uid("psblocking_reader")
OTHER = seed_user_uid("psblocking_other")
TARGET = "ps.psblocking.target"
NO_PREREQS = "ps.psblocking.no-prereqs"
UNTOUCHED = "ps.psblocking.untouched"
IN_PROGRESS = "ps.psblocking.in-progress"
MARKED_READ = "ps.psblocking.marked-read"
MASTERED = "ps.psblocking.mastered"
OTHERS_ONLY = "ps.psblocking.others-only"
DRAFT = "ps.psblocking.draft"
KU_READ = "ku.psblocking.read"
_STEPS = (TARGET, NO_PREREQS, UNTOUCHED, IN_PROGRESS, MARKED_READ, MASTERED, OTHERS_ONLY, DRAFT)
UIDS = (READER, OTHER, *_STEPS, KU_READ)
_STAMP = "2000-01-01T00:00:00+00:00"


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
        for uid in _STEPS:
            await session.run(
                """
                MERGE (s:Entity:PathStep {uid: $uid})
                SET s.title = $uid, s.entity_type = 'path_step', s.status = 'active',
                    s.created_at = $stamp, s.updated_at = $stamp
                """,
                uid=uid,
                stamp=_STAMP,
            )
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            SET k.title = 'psblocking concept', k.entity_type = 'ku', k.status = 'active',
                k.created_at = $stamp, k.updated_at = $stamp
            """,
            uid=KU_READ,
            stamp=_STAMP,
        )
        await session.run(
            "MATCH (s:PathStep {uid: $uid}) SET s.publication_state = 'draft'", uid=DRAFT
        )
        await session.run(
            """
            MATCH (t:PathStep {uid: $target}), (s:PathStep)
            WHERE s.uid IN $steps
            MERGE (t)-[:REQUIRES_STEP]->(s)
            """,
            target=TARGET,
            steps=[UNTOUCHED, IN_PROGRESS, MARKED_READ, MASTERED, OTHERS_ONLY, DRAFT],
        )
        await session.run(
            """
            MATCH (t:PathStep {uid: $target}), (k:Ku {uid: $ku}), (u:User {uid: $reader})
            MERGE (t)-[:REQUIRES_KNOWLEDGE]->(k)
            MERGE (u)-[:MARKED_AS_READ]->(k)
            """,
            target=TARGET,
            ku=KU_READ,
            reader=READER,
        )
        await session.run(
            """
            MATCH (u:User {uid: $reader}), (o:User {uid: $other}),
                  (p:PathStep {uid: $in_progress}), (r:PathStep {uid: $read}),
                  (m:PathStep {uid: $mastered}), (x:PathStep {uid: $others_only}),
                  (d:PathStep {uid: $draft})
            MERGE (u)-[:IN_PROGRESS]->(p)
            MERGE (u)-[:MARKED_AS_READ]->(r)
            MERGE (u)-[:MASTERED]->(m)
            MERGE (o)-[:MARKED_AS_READ]->(x)
            MERGE (u)-[:MARKED_AS_READ]->(d)
            """,
            reader=READER,
            other=OTHER,
            in_progress=IN_PROGRESS,
            read=MARKED_READ,
            mastered=MASTERED,
            others_only=OTHERS_ONLY,
            draft=DRAFT,
        )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def app(skuel_app: FastHTMLApp, graph: AsyncDriver) -> FastHTMLApp:
    """The whole route tree, wired by the bootstrap's own entry point."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="psblocking-test-key")
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


class _PageSeed(TypedDict):
    """The keys of the page's Alpine seed these tests read."""

    progress_state: str
    blocking: list[dict[str, str]]


async def _seed(client: httpx.AsyncClient, uid: str) -> _PageSeed:
    page = await client.get(f"/explore/ps/{uid}/content")
    assert page.status_code == 200, page.text[:300]
    match = re.search(r"""x-data=(['"])pathstep\((.*?)\)\1""", page.text, re.DOTALL)
    assert match, page.text[:300]
    seed: _PageSeed = json.loads(html.unescape(match.group(2)))
    return seed


async def _statuses(client: httpx.AsyncClient, uid: str) -> dict[str, str]:
    seed = await _seed(client, uid)
    return {row["uid"]: row["status"] for row in seed["blocking"]}


async def test_each_prerequisite_reads_this_readers_state(reader: httpx.AsyncClient) -> None:
    statuses = await _statuses(reader, TARGET)

    assert statuses == {
        UNTOUCHED: "blocked",
        IN_PROGRESS: "blocked",
        OTHERS_ONLY: "blocked",
        MARKED_READ: "met",
        MASTERED: "met",
        KU_READ: "met",
    }


async def test_a_draft_prerequisite_neither_shows_nor_blocks(reader: httpx.AsyncClient) -> None:
    assert DRAFT not in await _statuses(reader, TARGET)


@pytest.mark.parametrize("prerequisite", [UNTOUCHED, IN_PROGRESS, MARKED_READ, MASTERED])
async def test_a_step_shown_as_completed_never_blocks_the_next_one(
    reader: httpx.AsyncClient, prerequisite: str
) -> None:
    """The ruling itself: the hero card and the accordion agree, state by state."""
    hero = (await _seed(reader, prerequisite))["progress_state"]
    status = (await _statuses(reader, TARGET))[prerequisite]

    assert (hero == "read") == (status == "met"), (hero, status)


async def test_a_prerequisite_links_to_its_own_kinds_page(reader: httpx.AsyncClient) -> None:
    rows = {row["uid"]: row for row in (await _seed(reader, TARGET))["blocking"]}

    assert rows[KU_READ]["href"] == f"/explore/ku/{KU_READ}"
    assert rows[KU_READ]["title"] == "psblocking concept"
    assert rows[MASTERED]["href"] == f"/explore/ps/{MASTERED}"


async def test_a_signed_out_reader_has_completed_nothing(anonymous: httpx.AsyncClient) -> None:
    statuses = await _statuses(anonymous, TARGET)

    assert set(statuses.values()) == {"blocked"}
    assert DRAFT not in statuses


async def test_a_step_with_no_prerequisites_blocks_nothing(reader: httpx.AsyncClient) -> None:
    assert await _statuses(reader, NO_PREREQS) == {}


async def test_the_insights_door_sees_the_same_prerequisites(reader: httpx.AsyncClient) -> None:
    with_prereqs = await reader.get("/api/path-steps/insights", params={"uid": TARGET})
    without = await reader.get("/api/path-steps/insights", params={"uid": NO_PREREQS})

    assert with_prereqs.status_code == 200, with_prereqs.text[:300]
    assert with_prereqs.json()["has_prerequisites"] is True
    assert without.json()["has_prerequisites"] is False
