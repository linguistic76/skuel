"""The request's zone comes from the signed-in user's choice in the graph (testcontainer Neo4j).

ADR-089 §3: a user's zone is ``UserPreferences.timezone`` — an IANA name, or
no choice, which follows ``SKUEL_TIMEZONE``. ``AuthContextMiddleware`` reads the
choice in the same round trip that validates the session and sets the
request's zone from it; nothing is mirrored into the cookie, so a change in
Settings reaches the very next request.

Nothing is stubbed between the writers and the probe: a user registers
through ``GraphAuthService.sign_up`` (the register door's writer), chooses a
zone through ``UserService.update_preferences`` (the Settings door's writer),
signs in through ``sign_in``, and a real fast_app — SessionMiddleware, the
real middleware, the real session backend — answers a probe route with
``current_zone()``. Each test reads the stored ``preferences`` JSON back first,
so it pins its own premise.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.context_middleware import AuthContextMiddleware
from adapters.inbound.auth.session import set_current_user
from adapters.persistence.neo4j.session_backend import SessionBackend
from adapters.persistence.neo4j.user_backend import UserBackend
from core.auth.graph_auth import GraphAuthService
from core.utils.result_simplified import ErrorCategory
from core.utils.zone_context import current_zone

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

_RUN_ID = uuid.uuid4().hex[:8]
_PASSWORD = "zone-Correct-1234"


@pytest.fixture
def default_zone(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """SKUEL_TIMEZONE unset: the app default is America/Vancouver."""
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    return monkeypatch


@pytest_asyncio.fixture(loop_scope="session")
async def auth(neo4j_driver) -> AsyncIterator[tuple[GraphAuthService, list[str]]]:
    """Real GraphAuthService; tears down the users, sessions and auth events it made."""
    service = GraphAuthService(
        user_backend=UserBackend(neo4j_driver), session_backend=SessionBackend(neo4j_driver)
    )
    made: list[str] = []
    yield service, made
    async with neo4j_driver.session() as session:
        for username in made:
            await session.run(
                """
                OPTIONAL MATCH (u:User {uid: $uid})
                OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
                DETACH DELETE s, u
                """,
                uid=f"user_{username}",
            )
            await session.run(
                "MATCH (e:AuthEvent) WHERE e.email = $email DETACH DELETE e",
                email=f"{username}@example.com",
            )


async def _register(auth: tuple[GraphAuthService, list[str]], tag: str) -> str:
    service, made = auth
    username = f"zone_{tag}_{_RUN_ID}"
    made.append(username)
    signup = await service.sign_up(
        email=f"{username}@example.com", password=_PASSWORD, username=username
    )
    assert signup.is_ok, f"sign_up failed: {signup.error}"
    return username


async def _sign_in(auth: tuple[GraphAuthService, list[str]], username: str) -> str:
    signin = await auth[0].sign_in(email=f"{username}@example.com", password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    return signin.value["session_token"]


async def _stored_choice(neo4j_driver, username: str) -> Any:
    """The stored zone, read raw: the JSON ``preferences`` string on the User node."""
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (u:User {uid: $uid}) RETURN u.preferences AS preferences",
                uid=f"user_{username}",
            )
        ).single()
    assert record is not None
    raw = record["preferences"]
    assert isinstance(raw, str), "the mapper stores User.preferences as a JSON string"
    stored = json.loads(raw)
    assert "timezone" in stored
    return stored["timezone"]


def _client(service: GraphAuthService, username: str, token: str) -> httpx.AsyncClient:
    """A real fast_app with the bootstrap's middleware wiring and two probe routes."""
    from fasthtml.common import fast_app

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="zone-secret")
    app.user_middleware.append(Middleware(AuthContextMiddleware, graph_auth=service))

    @rt("/sign-in")
    def sign_in(request):
        set_current_user(request, user_uid=f"user_{username}", session_token=token)
        return PlainTextResponse("ok")

    @rt("/zone")
    def zone(request):
        return PlainTextResponse(current_zone().key)

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_a_bangkok_users_request_resolves_to_asia_bangkok(
    neo4j_driver, auth, user_service, default_zone
) -> None:
    username = await _register(auth, "bkk")
    chosen = await user_service.update_preferences(f"user_{username}", {"timezone": "Asia/Bangkok"})
    assert chosen.is_ok, f"update_preferences failed: {chosen.error}"
    assert await _stored_choice(neo4j_driver, username) == "Asia/Bangkok"
    token = await _sign_in(auth, username)

    async with _client(auth[0], username, token) as client:
        assert (await client.get("/zone")).text == "America/Vancouver", "anonymous: the default"
        assert (await client.get("/sign-in")).status_code == 200
        assert (await client.get("/zone")).text == "Asia/Bangkok"


async def test_a_change_in_settings_reaches_the_next_request(
    neo4j_driver, auth, user_service, default_zone
) -> None:
    username = await _register(auth, "change")
    await user_service.update_preferences(f"user_{username}", {"timezone": "Asia/Bangkok"})
    token = await _sign_in(auth, username)

    async with _client(auth[0], username, token) as client:
        await client.get("/sign-in")
        assert (await client.get("/zone")).text == "Asia/Bangkok"

        cleared = await user_service.update_preferences(f"user_{username}", {"timezone": None})
        assert cleared.is_ok
        assert await _stored_choice(neo4j_driver, username) is None
        assert (await client.get("/zone")).text == "America/Vancouver", "no new login needed"


async def test_a_freshly_registered_user_follows_skuel_timezone(
    neo4j_driver, auth, default_zone
) -> None:
    username = await _register(auth, "fresh")
    assert await _stored_choice(neo4j_driver, username) is None, "a new user has no choice"
    token = await _sign_in(auth, username)

    async with _client(auth[0], username, token) as client:
        await client.get("/sign-in")
        assert (await client.get("/zone")).text == "America/Vancouver"
        default_zone.setenv("SKUEL_TIMEZONE", "Europe/Lisbon")
        assert (await client.get("/zone")).text == "Europe/Lisbon"


async def test_the_validation_round_trip_carries_the_choice(neo4j_driver, auth, user_service):
    username = await _register(auth, "identity")
    token = await _sign_in(auth, username)

    before = await auth[0].validate_session_identity(token)
    assert before.is_ok and before.value == {"user_uid": f"user_{username}", "timezone": None}

    await user_service.update_preferences(f"user_{username}", {"timezone": "Asia/Bangkok"})
    after = await auth[0].validate_session_identity(token)
    assert after.is_ok and after.value == {
        "user_uid": f"user_{username}",
        "timezone": "Asia/Bangkok",
    }


async def test_a_named_users_zone_outside_a_request(
    neo4j_driver, auth, user_service, default_zone
) -> None:
    chooser = await _register(auth, "named")
    fresh = await _register(auth, "named_fresh")
    await user_service.update_preferences(f"user_{chooser}", {"timezone": "Asia/Bangkok"})

    chosen = await user_service.get_user_zone(f"user_{chooser}")
    assert chosen.is_ok and chosen.value == ZoneInfo("Asia/Bangkok")
    default = await user_service.get_user_zone(f"user_{fresh}")
    assert default.is_ok and default.value == ZoneInfo("America/Vancouver")

    missing = await user_service.get_user_zone(f"user_no_such_{_RUN_ID}")
    assert missing.is_error
    assert missing.expect_error().category == ErrorCategory.NOT_FOUND
