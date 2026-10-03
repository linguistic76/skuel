"""A reader renders only the owner's own node, or published shared content, across an edge.

A link edge joins one of a user's activities to another node. The link doors admit
only the user's own entities and published shared content as the far end, and the
readers hold the same line on their own: whatever wrote the edge, the node at its far
end is shown only when it is the reading user's own or shared content that is not a
draft (``build_far_node_clause``). The edge stays — a Ku reverted to draft drops off
its owner's pages, title and all, and comes back when it is republished.

Every edge here is seeded by raw Cypher, so the readers are measured without the
doors' help. Each of the caller's activities is linked three ways:

- to another user's entity (the mark no response and no context field may carry),
- to another of the caller's own entities (the CONTROL — the same readers still
  render it; without it "nothing foreign" would also be true of a reader that
  renders nothing),
- to a shared Ku, whose ``publication_state`` the draft test flips.

The whole wired route tree is crawled over real HTTP as the caller. Routes whose
path names a mutation are left out: a method-less CRUD route answers GET, and a GET
of ``/api/goals/delete?uid=`` deletes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
from core.models.enums import PublicationState

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

CALLER = "user_nb2e_caller"
OTHER = "user_nb2e_other"
USERS = (CALLER, OTHER)

FOREIGN_MARK = "nb2e-foreign-private"
CONTROL_MARK = "nb2e-control-linked"
KU_MARK = "nb2e-linked-ku"

OWN = {
    "Goal": "goal_nb2e_own",
    "Habit": "habit_nb2e_own",
    "Principle": "principle_nb2e_own",
    "Event": "event_nb2e_own",
    "Task": "task_nb2e_own",
    "Choice": "choice_nb2e_own",
}
FOREIGN = {
    "Goal": "goal_nb2e_foreign",
    "Habit": "habit_nb2e_foreign",
    "Task": "task_nb2e_foreign",
    "Choice": "choice_nb2e_foreign",
    "Principle": "principle_nb2e_foreign",
}
CONTROL = {label: uid.replace("_foreign", "_control") for label, uid in FOREIGN.items()}

KU = "ku.nb2e.linked"
KU_REQUIRING = "ku.nb2e.requiring"
STEP = "ps.nb2e.in-progress"
KNOWLEDGE_UIDS = (KU, KU_REQUIRING, STEP)

# (own label, edge, far label, direction: own->far unless "in") — the edges the link
# doors write, each seeded to the FOREIGN and to the CONTROL entity of the far label.
EDGES = (
    ("Goal", "REQUIRES_KNOWLEDGE", "Task", "out"),
    ("Habit", "REINFORCES_KNOWLEDGE", "Task", "out"),
    ("Principle", "GROUNDED_IN_KNOWLEDGE", "Task", "out"),
    ("Event", "CELEBRATES_GOAL", "Goal", "out"),
    ("Event", "REINFORCES_HABIT", "Habit", "out"),
    ("Principle", "GUIDES_CHOICE", "Choice", "out"),
    ("Principle", "GUIDES_GOAL", "Goal", "out"),
    ("Principle", "INSPIRES_HABIT", "Habit", "out"),
    ("Principle", "SUPPORTS_PRINCIPLE", "Principle", "in"),
    ("Goal", "SUPPORTS_GOAL", "Habit", "in"),
    ("Choice", "IMPACTS_HABIT", "Habit", "out"),
    ("Task", "APPLIES_KNOWLEDGE", "Task", "out"),
    ("Event", "APPLIES_KNOWLEDGE", "Task", "out"),
)

# (own label, edge) — the caller's activities linked to the shared Ku.
KU_EDGES = (
    ("Task", "APPLIES_KNOWLEDGE"),
    ("Event", "APPLIES_KNOWLEDGE"),
    ("Goal", "REQUIRES_KNOWLEDGE"),
    ("Habit", "REINFORCES_KNOWLEDGE"),
    ("Principle", "GROUNDED_IN_KNOWLEDGE"),
    ("Task", "REQUIRES_KNOWLEDGE"),
)

# The routes the old readers rendered another user's title on. Each must still render
# the caller's own linked entity.
READER_ROUTES = (
    "/events/content",
    "/events/detail/content",
    "/events/edit",
    "/events/list-fragment",
    "/goals/detail/content",
    "/goals/habit-impact",
    "/goals/predict-success",
    "/goals/risk-assessment",
    "/tasks/content",
    "/tasks/detail/content",
    "/tasks/list-fragment",
)

# Routes that show a Ku by LISTING the library, not by reading across an edge from
# one of the caller's entities: the reading plan's hero is the first library Ku. A
# listing answers to the catalogue's own publication rule, not to the far-node one.
LISTING_ROUTES = frozenset({"/explore/content"})

_MUTATING = ("delete", "update", "remove", "archive", "complete", "logout", "create")
_SKIPPED_PREFIXES = ("/sign-in", "/static", "/metrics")
_PATH_PARAM = re.compile(r"\{[^}]+\}")
_QUERY_NAMES = (
    "uid",
    "goal_uid",
    "habit_uid",
    "principle_uid",
    "event_uid",
    "task_uid",
    "choice_uid",
    "entity_uid",
)


@dataclass
class Crawl:
    """What one pass over the route tree, as the caller, returned."""

    requests: int = 0
    foreign: dict[str, set[str]] = field(default_factory=dict)
    control: dict[str, set[str]] = field(default_factory=dict)
    knowledge: set[str] = field(default_factory=set)

    def read(self, path: str, url: str, text: str) -> None:
        self.requests += 1
        found = set(re.findall(rf"{FOREIGN_MARK} \w+", text))
        found |= {uid for uid in FOREIGN.values() if uid in text}
        if found:
            self.foreign.setdefault(path, set()).update(found)
        # A control entity on a request for ANOTHER own entity was reached across a
        # seeded edge, not named by the request.
        linked = {
            label
            for label in re.findall(rf"{CONTROL_MARK} (\w+)", text)
            if CONTROL[label] not in url
        }
        if linked:
            self.control.setdefault(path, set()).update(linked)
        if KU_MARK in text or KU in text:
            self.knowledge.add(path)


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n.uid IN $users OR n.user_uid IN $users OR n.uid IN $knowledge
            DETACH DELETE n
            """,
            users=list(USERS),
            knowledge=list(KNOWLEDGE_UIDS),
        )


async def _seed_activity(driver: AsyncDriver, label: str, uid: str, owner: str, title: str) -> None:
    async with driver.session() as session:
        await session.run(
            f"""
            MATCH (u:User {{uid: $owner}})
            MERGE (e:Entity:{label} {{uid: $uid}})
            SET e.title = $title, e.description = $title + ' description',
                e.entity_type = $entity_type, e.status = 'active', e.user_uid = $owner,
                e.recurrence_pattern = 'daily', e.event_date = date(), e.priority = 'medium',
                e.created_at = datetime(), e.updated_at = datetime()
            MERGE (u)-[:OWNS]->(e)
            """,
            uid=uid,
            owner=owner,
            title=title,
            entity_type=label.lower(),
        )


async def _set_publication(driver: AsyncDriver, state: PublicationState | None) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (k:Ku {uid: $uid}) SET k.publication_state = $state",
            uid=KU,
            state=state.value if state else None,
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    async with driver.session() as session:
        for uid in USERS:
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=uid)
        for uid, title in ((KU, f"{KU_MARK} title"), (KU_REQUIRING, "nb2e requiring ku")):
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                SET k.title = $title, k.entity_type = 'ku',
                    k.created_at = datetime(), k.updated_at = datetime()
                """,
                uid=uid,
                title=title,
            )
        await session.run(
            "MATCH (a:Ku {uid: $a}), (b:Ku {uid: $b}) MERGE (a)-[:REQUIRES_KNOWLEDGE]->(b)",
            a=KU_REQUIRING,
            b=KU,
        )
        # The caller has mastered the requiring Ku, so its prerequisite — the linked
        # Ku — is in the knowledge half of the rich context too.
        await session.run(
            "MATCH (u:User {uid: $u}), (k:Ku {uid: $k}) MERGE (u)-[:MASTERED]->(k)",
            u=CALLER,
            k=KU_REQUIRING,
        )
        # A step the caller is working on names the linked Ku as a prerequisite — other
        # curriculum, not the step's own contents.
        await session.run(
            """
            MATCH (u:User {uid: $u}), (k:Ku {uid: $k})
            MERGE (s:Entity:PathStep {uid: $s})
            SET s.title = 'nb2e in-progress step', s.entity_type = 'path_step',
                s.created_at = datetime(), s.updated_at = datetime()
            MERGE (u)-[:IN_PROGRESS]->(s)
            MERGE (s)-[:REQUIRES_KNOWLEDGE]->(k)
            """,
            u=CALLER,
            k=KU,
            s=STEP,
        )
    for label, uid in OWN.items():
        await _seed_activity(driver, label, uid, CALLER, f"caller-owned {label}")
    for label, uid in FOREIGN.items():
        await _seed_activity(driver, label, uid, OTHER, f"{FOREIGN_MARK} {label}")
    for label, uid in CONTROL.items():
        await _seed_activity(driver, label, uid, CALLER, f"{CONTROL_MARK} {label}")
    async with driver.session() as session:
        for own, edge, far_label, direction in EDGES:
            pattern = (
                f"(a)-[:{edge} {{confidence: 0.9}}]->(b)"
                if direction == "out"
                else f"(b)-[:{edge} {{confidence: 0.9}}]->(a)"
            )
            for far in (FOREIGN, CONTROL):
                await session.run(
                    f"MATCH (a {{uid: $a}}), (b {{uid: $b}}) MERGE {pattern}",
                    a=OWN[own],
                    b=far[far_label],
                )
        for own, edge in KU_EDGES:
            await session.run(
                f"MATCH (a {{uid: $a}}), (k:Ku {{uid: $k}}) MERGE (a)-[:{edge} {{confidence: 0.9}}]->(k)",
                a=OWN[own],
                k=KU,
            )
    yield driver
    await _wipe(driver)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def http(skuel_app: Any, graph: AsyncDriver) -> AsyncIterator[httpx.AsyncClient]:
    """The whole route tree, wired by the bootstrap's own entry point, signed in as CALLER."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="nb2e-test-key")
    await _wire_all_routes(
        app, rt, container.services, container.config, container.prometheus_metrics
    )

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=60,
    ) as client:
        assert (await client.get(f"/sign-in/{CALLER}")).status_code == 200
        client.app = app  # type: ignore[attr-defined]  # the crawl reads its route table
        yield client


def _read_paths(app: Any) -> list[str]:
    paths: set[str] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if "GET" not in methods or not path or path.startswith(_SKIPPED_PREFIXES):
            continue
        if any(word in path for word in _MUTATING):
            continue
        paths.add(path)
    return sorted(paths)


async def _crawl(client: httpx.AsyncClient, paths: list[str]) -> Crawl:
    crawl = Crawl()
    for path in paths:
        for uid in OWN.values():
            url = _PATH_PARAM.sub(uid, path)
            query = "&".join(f"{name}={uid}" for name in _QUERY_NAMES)
            response = await client.get(f"{url}?{query}")
            crawl.read(path, url, response.text)
    return crawl


async def _rich_context(skuel_app: Any) -> str:
    result = await skuel_app.state.services.user.context_builder.build_rich(CALLER)
    assert result.is_ok, result
    return repr(result.value)


async def _readiness(skuel_app: Any) -> dict[str, Any]:
    """Whether the caller's task may start — it REQUIRES_KNOWLEDGE the linked Ku."""
    services = skuel_app.state.services
    context = await services.user.context_builder.build_rich(CALLER)
    assert context.is_ok, context
    result = await services.tasks.check_prerequisites(OWN["Task"], context.value)
    assert result.is_ok, result
    return dict(result.value)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def crawl(http: httpx.AsyncClient) -> Crawl:
    """One pass over every read route with each of the caller's own uids, Ku published."""
    return await _crawl(http, _read_paths(http.app))  # type: ignore[attr-defined]


async def test_no_route_returns_another_users_node(crawl: Crawl) -> None:
    assert crawl.requests > 1000
    assert crawl.foreign == {}


async def test_the_same_routes_still_render_the_callers_own_linked_entity(crawl: Crawl) -> None:
    """The control: every reader that used to carry the other user's title still
    reaches across the edge to the caller's own entity."""
    silent = [path for path in READER_ROUTES if not crawl.control.get(path)]
    assert silent == []


async def test_the_rich_context_carries_the_callers_node_and_not_the_other_users(
    skuel_app: Any, graph: AsyncDriver
) -> None:
    context = await _rich_context(skuel_app)

    assert FOREIGN_MARK not in context
    assert [uid for uid in FOREIGN.values() if uid in context] == []
    assert sorted(uid for uid in CONTROL.values() if uid in context) == sorted(CONTROL.values())


async def test_a_linked_ku_reverted_to_draft_is_hidden_and_republished_is_back(
    skuel_app: Any, graph: AsyncDriver, http: httpx.AsyncClient, crawl: Crawl
) -> None:
    readers = sorted(crawl.knowledge - LISTING_ROUTES)
    # The linked Ku is on the list and detail pages, and under the global
    # prerequisite map, while it is published.
    assert {"/tasks/content", "/tasks/detail/content", "/events/content"} <= set(readers)
    assert "/api/pathways/progress/summary" in readers
    assert KU in await _rich_context(skuel_app)

    try:
        await _set_publication(graph, PublicationState.DRAFT)
        hidden = await _crawl(http, readers)
        assert hidden.knowledge == set()
        drafted = await _rich_context(skuel_app)
        assert KU not in drafted
        assert KU_MARK not in drafted
        # The same readers still reach the caller's own linked entity.
        assert [p for p in READER_ROUTES if p in readers and not hidden.control.get(p)] == []
        # Hidden is not met: the task still waits on the prerequisite it cannot name.
        assert await _readiness(skuel_app) == {
            "can_start": False,
            "missing_knowledge": [],
            "incomplete_tasks": [],
        }

        await _set_publication(graph, PublicationState.PUBLISHED)
        assert (await _readiness(skuel_app))["missing_knowledge"] == [KU]
        restored = await _crawl(http, readers)
        assert sorted(restored.knowledge) == readers
        assert KU in await _rich_context(skuel_app)
    finally:
        await _set_publication(graph, None)
