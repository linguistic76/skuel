"""The orchestration routes act on the caller's own goal or habit, over real HTTP.

Every orchestration route that takes a goal or habit uid reads that entity on
the caller's behalf, and two of them write from it: ``POST /goals/generate-tasks``
creates tasks owned by the goal's owner, ``POST /habits/schedule-events`` creates
events from the habit's title and description. The route verifies ownership of
the uid before the service behind it runs.

The routes are registered through the bootstrap's own entry point
(``create_orchestration_routes``) over the composed app's services, on a
``fast_app`` with real session middleware and a sign-in route.

The contract:

- a signed-out request to any of the fourteen routes is 401 — on the composed
  app's own route table too;
- another user's goal or habit is answered exactly as a uid that names nothing —
  same status, same body — the response carries none of its text, and no task
  or event is written for either user;
- the caller's own goal or habit is answered 200, and the two write routes write
  entities the caller owns;
- the three routes that write answer POST alone, behind the CSRF check.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from neo4j import AsyncDriver
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.lateral_routes_client import without_timestamp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

CALLER = "user_nb2a_caller"
OTHER = "user_nb2a_other"  # owns the foreign goal and habit; never signs in
USERS = (CALLER, OTHER)

OWN_GOAL = "goal_nb2a_own"
OWN_HABIT = "habit_nb2a_own"
FOREIGN_GOAL = "goal_nb2a_foreign"
FOREIGN_HABIT = "habit_nb2a_foreign"
MISSING_GOAL = "goal_nb2a_missing"
MISSING_HABIT = "habit_nb2a_missing"

# Text only the foreign entities carry — it must reach no response.
FOREIGN_MARK = "nb2a-foreign-private"


@dataclass(frozen=True)
class Door:
    """One uid-taking orchestration route."""

    method: str
    path: str
    uid_param: str
    kind: str  # "goal" | "habit"
    extra: str = ""

    def url(self, uid: str) -> str:
        return f"{self.path}?{self.uid_param}={uid}{self.extra}"

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}{self.extra}"


DOORS = (
    Door("GET", "/goals/task-templates", "uid", "goal"),
    Door("POST", "/goals/generate-tasks", "uid", "goal"),
    Door("POST", "/goals/generate-tasks", "uid", "goal", "&auto_create=true"),
    Door("GET", "/goals/predict-success", "uid", "goal"),
    Door("GET", "/goals/habit-impact", "uid", "goal"),
    Door("GET", "/goals/risk-assessment", "uid", "goal"),
    Door("GET", "/principles/goal-alignment", "goal_uid", "goal"),
    Door("GET", "/habits/event-templates", "uid", "habit"),
    Door("POST", "/habits/schedule-events", "uid", "habit"),
    Door("POST", "/habits/schedule-events", "uid", "habit", "&auto_create=true"),
    Door("GET", "/principles/habit-alignment", "habit_uid", "habit"),
)
_DOOR_IDS = [door.label for door in DOORS]

# The routes that take no uid — the caller's own aggregate.
SELF_SCOPED = (
    ("POST", "/goals/generate-tasks-all"),
    ("GET", "/goals/critical-tasks"),
    ("GET", "/principles/list"),
    ("GET", "/principles/motivational-profile"),
    ("GET", "/principles/suggest-actions"),
)

WRITE_ROUTES = (
    f"/goals/generate-tasks?uid={OWN_GOAL}&auto_create=true",
    f"/habits/schedule-events?uid={OWN_HABIT}&auto_create=true",
    "/goals/generate-tasks-all?auto_create=true",
)

_OWN = {"goal": OWN_GOAL, "habit": OWN_HABIT}
_FOREIGN = {"goal": FOREIGN_GOAL, "habit": FOREIGN_HABIT}
_MISSING = {"goal": MISSING_GOAL, "habit": MISSING_HABIT}


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $users OR n.user_uid IN $users DETACH DELETE n",
            users=list(USERS),
        )


async def _seed_owned(
    driver: AsyncDriver, *, label: str, entity_type: str, uid: str, owner: str, title: str
) -> None:
    async with driver.session() as session:
        await session.run(
            f"""
            MATCH (u:User {{uid: $owner}})
            MERGE (e:Entity:{label} {{uid: $uid}})
            SET e.title = $title, e.description = $title + ' description',
                e.entity_type = $entity_type, e.status = 'active', e.user_uid = $owner,
                e.recurrence_pattern = 'daily'
            MERGE (u)-[:OWNS]->(e)
            """,
            uid=uid,
            owner=owner,
            title=title,
            entity_type=entity_type,
        )


@pytest_asyncio.fixture(loop_scope="session")
async def driver(skuel_app) -> AsyncDriver:
    """Two users, each owning one active goal and one daily habit."""
    graph: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(graph)
    async with graph.session() as session:
        for uid in USERS:
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=uid)
    for owner, goal, habit, title in (
        (CALLER, OWN_GOAL, OWN_HABIT, "caller-owned"),
        (OTHER, FOREIGN_GOAL, FOREIGN_HABIT, FOREIGN_MARK),
    ):
        await _seed_owned(
            graph, label="Goal", entity_type="goal", uid=goal, owner=owner, title=f"{title} goal"
        )
        await _seed_owned(
            graph,
            label="Habit",
            entity_type="habit",
            uid=habit,
            owner=owner,
            title=f"{title} habit",
        )
    yield graph
    await _wipe(graph)


def _app(skuel_app):
    from fasthtml.common import fast_app

    from adapters.inbound.orchestration_routes import create_orchestration_routes

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="nb2a-orchestration-test-key")
    create_orchestration_routes(app, rt, skuel_app.state.services)

    @rt("/sign-in/{uid}")
    def sign_in(request: Request, uid: str) -> PlainTextResponse:
        set_current_user(request, user_uid=uid)
        return PlainTextResponse("ok")

    return app


@pytest_asyncio.fixture(loop_scope="session")
async def client(skuel_app, driver):
    """An HTTP client signed in as ``CALLER``, carrying a CSRF cookie and header."""
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(skuel_app)),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    ) as http:
        assert (await http.get(f"/sign-in/{CALLER}")).status_code == 200
        yield http


@pytest_asyncio.fixture(loop_scope="session")
async def signed_out(skuel_app, driver):
    """An HTTP client with no session, carrying a CSRF cookie and header."""
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(skuel_app)),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    ) as http:
        yield http


@pytest_asyncio.fixture(loop_scope="session")
async def composed_signed_out(skuel_app, driver):
    """An HTTP client over the composed app itself, with no session."""
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=skuel_app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    ) as http:
        yield http


async def _generated(driver: AsyncDriver) -> dict[str, list[tuple[str, str]]]:
    """``(label, title)`` of every Task and Event each user owns."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (u:User)-[:OWNS]->(e)
            WHERE u.uid IN $users AND (e:Task OR e:Event)
            RETURN u.uid AS owner, [l IN labels(e) WHERE l <> 'Entity'][0] AS label,
                   e.title AS title
            ORDER BY owner, label, title
            """,
            users=list(USERS),
        )
        owned: dict[str, list[tuple[str, str]]] = {uid: [] for uid in USERS}
        async for row in result:
            owned[row["owner"]].append((row["label"], row["title"]))
        return owned


async def _clear_generated(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (e) WHERE e.user_uid IN $users AND (e:Task OR e:Event) DETACH DELETE e",
            users=list(USERS),
        )


class TestSignedOut:
    @pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
    async def test_uid_route_requires_a_session(
        self, signed_out: httpx.AsyncClient, door: Door
    ) -> None:
        response = await signed_out.request(door.method, door.url(_FOREIGN[door.kind]))
        assert response.status_code == 401, response.text
        assert FOREIGN_MARK not in response.text

    @pytest.mark.parametrize(("method", "path"), SELF_SCOPED, ids=[p for _, p in SELF_SCOPED])
    async def test_self_scoped_route_requires_a_session(
        self, signed_out: httpx.AsyncClient, method: str, path: str
    ) -> None:
        response = await signed_out.request(method, path)
        assert response.status_code == 401, response.text


class TestComposedAppSignedOut:
    """The composed app's own route table and middleware, with no session."""

    @pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
    async def test_uid_route_requires_a_session(
        self, composed_signed_out: httpx.AsyncClient, door: Door
    ) -> None:
        response = await composed_signed_out.request(door.method, door.url(_FOREIGN[door.kind]))
        assert response.status_code == 401, response.text
        assert FOREIGN_MARK not in response.text

    @pytest.mark.parametrize(("method", "path"), SELF_SCOPED, ids=[p for _, p in SELF_SCOPED])
    async def test_self_scoped_route_requires_a_session(
        self, composed_signed_out: httpx.AsyncClient, method: str, path: str
    ) -> None:
        response = await composed_signed_out.request(method, path)
        assert response.status_code == 401, response.text


class TestAnotherUsersEntity:
    @pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
    async def test_is_answered_as_a_missing_uid_is(
        self, client: httpx.AsyncClient, driver: AsyncDriver, door: Door
    ) -> None:
        await _clear_generated(driver)

        foreign = await client.request(door.method, door.url(_FOREIGN[door.kind]))
        missing = await client.request(door.method, door.url(_MISSING[door.kind]))

        assert foreign.status_code == 404, foreign.text
        assert FOREIGN_MARK not in foreign.text
        assert missing.status_code == 404, missing.text
        assert without_timestamp(foreign) == without_timestamp(missing)
        assert await _generated(driver) == {CALLER: [], OTHER: []}


class TestOwnEntity:
    @pytest.mark.parametrize("door", DOORS, ids=_DOOR_IDS)
    async def test_is_answered(
        self, client: httpx.AsyncClient, driver: AsyncDriver, door: Door
    ) -> None:
        await _clear_generated(driver)
        response = await client.request(door.method, door.url(_OWN[door.kind]))
        assert response.status_code == 200, response.text

    async def test_generate_tasks_writes_tasks_the_caller_owns(
        self, client: httpx.AsyncClient, driver: AsyncDriver
    ) -> None:
        await _clear_generated(driver)
        response = await client.post(f"/goals/generate-tasks?uid={OWN_GOAL}&auto_create=true")
        assert response.status_code == 200, response.text

        generated = await _generated(driver)
        assert generated[OTHER] == []
        assert generated[CALLER], "the caller's goal yields at least its check-in task"
        assert {label for label, _ in generated[CALLER]} == {"Task"}
        assert len(response.json()) == len(generated[CALLER])

    async def test_task_templates_write_nothing(
        self, client: httpx.AsyncClient, driver: AsyncDriver
    ) -> None:
        await _clear_generated(driver)
        response = await client.get(f"/goals/task-templates?uid={OWN_GOAL}")
        assert response.status_code == 200, response.text
        assert response.json(), "templates for the caller's goal"
        assert await _generated(driver) == {CALLER: [], OTHER: []}

    async def test_schedule_events_writes_events_the_caller_owns(
        self, client: httpx.AsyncClient, driver: AsyncDriver
    ) -> None:
        await _clear_generated(driver)
        response = await client.post(
            f"/habits/schedule-events?uid={OWN_HABIT}&auto_create=true&days_ahead=2"
        )
        assert response.status_code == 200, response.text

        generated = await _generated(driver)
        assert generated[OTHER] == []
        assert generated[CALLER] == [("Event", "caller-owned habit")] * 2

    @pytest.mark.parametrize(("method", "path"), SELF_SCOPED, ids=[p for _, p in SELF_SCOPED])
    async def test_self_scoped_route_answers(
        self, client: httpx.AsyncClient, driver: AsyncDriver, method: str, path: str
    ) -> None:
        await _clear_generated(driver)
        response = await client.request(method, path)
        assert response.status_code == 200, response.text
        assert FOREIGN_MARK not in response.text


class TestWriteRoutesArePostBehindCsrf:
    @pytest.mark.parametrize("url", WRITE_ROUTES)
    async def test_get_is_not_allowed_and_writes_nothing(
        self, client: httpx.AsyncClient, driver: AsyncDriver, url: str
    ) -> None:
        await _clear_generated(driver)
        response = await client.get(url)
        assert response.status_code == 405, response.text
        assert await _generated(driver) == {CALLER: [], OTHER: []}

    @pytest.mark.parametrize("url", WRITE_ROUTES)
    async def test_post_without_the_csrf_token_is_refused(
        self, client: httpx.AsyncClient, driver: AsyncDriver, url: str
    ) -> None:
        await _clear_generated(driver)
        response = await client.post(url, headers={CSRF_HEADER_NAME: "not-the-token"})
        assert response.status_code == 403, response.text
        assert await _generated(driver) == {CALLER: [], OTHER: []}


class TestQueryValues:
    async def test_an_unreadable_auto_create_creates_nothing(
        self, client: httpx.AsyncClient, driver: AsyncDriver
    ) -> None:
        await _clear_generated(driver)
        response = await client.post(f"/goals/generate-tasks?uid={OWN_GOAL}&auto_create=maybe")
        assert response.status_code == 200, response.text
        assert response.json(), "templates for the caller's goal"
        assert await _generated(driver) == {CALLER: [], OTHER: []}

    async def test_days_ahead_is_capped(self, client: httpx.AsyncClient) -> None:
        response = await client.post(f"/habits/schedule-events?uid={OWN_HABIT}&days_ahead=100000")
        assert response.status_code == 200, response.text
        assert len(response.json()) == 90

    @pytest.mark.parametrize("days_ahead", ["", "abc", "0", "-4"])
    async def test_an_unreadable_days_ahead_is_the_schedulers_horizon(
        self, client: httpx.AsyncClient, days_ahead: str
    ) -> None:
        response = await client.post(
            f"/habits/schedule-events?uid={OWN_HABIT}&days_ahead={days_ahead}"
        )
        assert response.status_code == 200, response.text
        assert len(response.json()) == 7
