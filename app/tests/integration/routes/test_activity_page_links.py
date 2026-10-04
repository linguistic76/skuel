"""A link between two Activities shows on both pages and both cards, under each side's name.

ADR-090 §2, ruling R10: an Activity page renders its domain's registry definitions that
carry a ``page_heading``, in both directions — the detail page's Connections section and
the list card. The pairs are derived, never hand-listed: every Activity link the
registry reads at both ends (``links_read_at_both_ends``, the invariant's own census).

Each pair gets its own two entities, created through the domains' real create doors
(``POST /api/{domain}/create``), joined by one seeded edge — many of these links have
no writer yet (R8), so the edge is written by Cypher. Each page is then read over real
HTTP as the owner: the far end's title must sit under the heading this side gives the
link (``heading_at``), on the detail page and on the entity's list card.

The routes are registered through the bootstrap's own entry point over the composed
app's services, on a ``fast_app`` with real session middleware and a sign-in route.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from core.models.enums.neo_labels import NeoLabel
from tests.helpers.activity_links import Link, heading_at, links_read_at_both_ends
from ui.activities._shared import safe_id

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

CALLER = "user_pagelinks_caller"

PAIRS = links_read_at_both_ends()

# label -> (URL segment, card id prefix)
DOMAINS: dict[NeoLabel, tuple[str, str]] = {
    NeoLabel.TASK: ("tasks", "task"),
    NeoLabel.GOAL: ("goals", "goal"),
    NeoLabel.HABIT: ("habits", "habit"),
    NeoLabel.EVENT: ("events", "event"),
    NeoLabel.CHOICE: ("choices", "choice"),
    NeoLabel.PRINCIPLE: ("principles", "principle"),
}

# The list filter that keeps a freshly created entity on its list.
LIST_FILTERS: dict[NeoLabel, str] = {
    NeoLabel.TASK: "status=active",
    NeoLabel.GOAL: "status=active",
    NeoLabel.HABIT: "status=active",
    NeoLabel.EVENT: "status=all",
    NeoLabel.CHOICE: "status=all",
    NeoLabel.PRINCIPLE: "status=all",
}


def _pair_id(link: Link) -> str:
    return f"{link.source.value}-{link.edge.value}-{link.target.value}"


def _title(link: Link, end: str) -> str:
    return f"pagelinks {_pair_id(link)} {end}"


def _create_body(label: NeoLabel, title: str) -> dict[str, str]:
    """The fewest fields each domain's create request requires."""
    today = datetime.now(UTC).date().isoformat()
    extra: dict[NeoLabel, dict[str, str]] = {
        NeoLabel.EVENT: {"event_date": today, "start_time": "09:00", "end_time": "10:00"},
        NeoLabel.CHOICE: {"description": f"{title} description"},
        NeoLabel.PRINCIPLE: {"statement": f"{title} statement"},
    }
    return {"title": title, **extra.get(label, {})}


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid = $user OR n.user_uid = $user DETACH DELETE n", user=CALLER
        )


def _app(skuel_app: Any) -> Any:
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="pagelinks-test-key")

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app, _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def client(skuel_app: Any) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client signed in as ``CALLER``, carrying a CSRF cookie and header."""
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=CALLER)
    app, wiring = _app(skuel_app)
    await wiring
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=60,
    ) as http:
        assert (await http.get(f"/sign-in/{CALLER}")).status_code == 200
        yield http
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def linked(skuel_app: Any, client: httpx.AsyncClient) -> dict[Link, tuple[str, str]]:
    """Each pair's two entities, created at the real doors and joined by its edge."""
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    uids: dict[Link, tuple[str, str]] = {}
    for link in PAIRS:
        ends = []
        for label, end in ((link.source, "source"), (link.target, "target")):
            segment, _prefix = DOMAINS[label]
            response = await client.post(
                f"/api/{segment}/create", json=_create_body(label, _title(link, end))
            )
            assert response.status_code == 201, (link, end, response.text)
            ends.append(response.json()["uid"])
        source_uid, target_uid = ends
        async with driver.session() as session:
            await session.run(
                f"MATCH (a {{uid: $a}}), (b {{uid: $b}}) MERGE (a)-[:{link.edge.value}]->(b)",
                a=source_uid,
                b=target_uid,
            )
        uids[link] = (source_uid, target_uid)
    return uids


def _ends(link: Link, uids: tuple[str, str]) -> list[tuple[NeoLabel, str, str, str]]:
    """Both ends of a link: (page label, page uid, heading there, far end's title)."""
    source_uid, target_uid = uids
    return [
        (
            link.source,
            source_uid,
            heading_at(link.source, "outgoing", link.edge, link.target),
            _title(link, "target"),
        ),
        (
            link.target,
            target_uid,
            heading_at(link.target, "incoming", link.edge, link.source),
            _title(link, "source"),
        ),
    ]


def _under_heading(html: str, heading: str, closing: str) -> str:
    """The markup between ``heading`` and the first ``closing`` tag after it."""
    start = html.find(heading)
    assert start != -1, f"no {heading!r} on the page"
    return html[start : html.index(closing, start)]


def _card(html: str, prefix: str, uid: str) -> str:
    """One list card's markup: from its id to the next card of the same domain."""
    start = html.find(f'id="{prefix}-{safe_id(uid)}"')
    assert start != -1, f"no card for {uid} on the list"
    following = html.find(f'id="{prefix}-', start + 1)
    return html[start : following if following != -1 else len(html)]


@pytest.mark.parametrize("link", PAIRS, ids=_pair_id)
async def test_both_detail_pages_show_the_link_under_their_own_heading(
    client: httpx.AsyncClient, linked: dict[Link, tuple[str, str]], link: Link
) -> None:
    for label, uid, heading, far_title in _ends(link, linked[link]):
        segment, _prefix = DOMAINS[label]
        response = await client.get(f"/{segment}/detail/content?uid={uid}")

        assert response.status_code == 200, (label, response.text[:500])
        assert far_title in _under_heading(response.text, heading, "</ul>"), (label, heading)


@pytest.mark.parametrize("link", PAIRS, ids=_pair_id)
async def test_both_list_cards_show_the_link_under_their_own_heading(
    client: httpx.AsyncClient, linked: dict[Link, tuple[str, str]], link: Link
) -> None:
    for label, uid, heading, far_title in _ends(link, linked[link]):
        segment, prefix = DOMAINS[label]
        response = await client.get(f"/{segment}/list-fragment?{LIST_FILTERS[label]}")

        assert response.status_code == 200, (label, response.text[:500])
        card = _card(response.text, prefix, uid)
        assert far_title in _under_heading(card, f"{heading}:", "</div>"), (label, heading)


async def test_the_pairs_are_the_registry_census() -> None:
    """The parametrization is the invariant's census, not a hand list (18 on the day)."""
    assert PAIRS
    assert links_read_at_both_ends() == PAIRS
    assert {link.source for link in PAIRS} | {link.target for link in PAIRS} <= set(DOMAINS)
