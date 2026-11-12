"""A user changes the name they are shown by, from the Account card on ``/settings``.

Over the bootstrapped app's routes and services, behind the bootstrap's own
session middleware: two accounts register and sign in through ``GraphAuthService``,
and each step is driven by the page's own control, the card's ``hx-post`` with the
fields the rendered form holds. The graph is then read raw: the name lands and
nothing else on the user node changes; a preferences save racing it keeps both; a
page that shows the user to someone else reads the new name; and the top bar's
avatar on the next page carries the new name's first letter.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from html import unescape
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
import pytest
import pytest_asyncio
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.context_middleware import AuthContextMiddleware
from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

_RUN = uuid.uuid4().hex[:8]
_PASSWORD = "name-Correct-1234"
DOOR = "/api/user/display-name"
FEEDBACK = "/activity-review/submit-feedback"
FORM_ENCODED = {"content-type": "application/x-www-form-urlencoded", "HX-Request": "true"}
_TRIALS = 5


class _CardForm(HTMLParser):
    """The fields of the one form on a page whose ``hx-post`` is the door."""

    def __init__(self) -> None:
        super().__init__()
        self.attrs: dict[str, str] | None = None
        self.fields: list[tuple[str, str]] = []
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "form" and a.get("hx-post") == DOOR:
            assert self.attrs is None, "two Account forms on one page"
            self.attrs, self._inside = a, True
        elif tag == "input" and self._inside and a.get("name"):
            self.fields.append((a["name"], a.get("value", "")))

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._inside = False


def _card_form(page: str) -> _CardForm:
    parsed = _CardForm()
    parsed.feed(page)
    assert parsed.attrs is not None, "the page has no Account form"
    return parsed


def _avatar_letter(page: str) -> str:
    disc = re.search(r"<div[^>]*--avatar-hue[^>]*>([^<]*)</div>", page)
    assert disc is not None, "the page has no avatar"
    return unescape(disc.group(1))


def _avatar_hue(page: str) -> str:
    hue = re.search(r"--avatar-hue: (\d+);", page)
    assert hue is not None
    return hue.group(1)


class _Account:
    """One signed-in account: its uid and its client."""

    def __init__(self, uid: str, client: httpx.AsyncClient) -> None:
        self.uid, self.client = uid, client

    async def save_name(self, typed: str) -> httpx.Response:
        """Type ``typed`` into the Account card as ``/settings`` renders it, and save."""
        page = (await self.client.get("/settings")).text
        form = _card_form(page)
        fields = [(n, typed if n == "display_name" else v) for n, v in form.fields]
        assert [n for n, _ in fields] == ["display_name"]
        return await self.client.post(DOOR, content=urlencode(fields), headers=FORM_ENCODED)


class _World:
    def __init__(
        self, app: FastHTMLApp, driver: AsyncDriver, learner: _Account, admin: _Account
    ) -> None:
        self.app, self.driver, self.learner, self.admin = app, driver, learner, admin

    async def properties(self, uid: str) -> dict[str, Any]:  # boundary: raw node properties
        async with self.driver.session() as session:
            record = await (
                await session.run("MATCH (u:User {uid: $uid}) RETURN properties(u) AS p", uid=uid)
            ).single()
        assert record is not None
        return dict(record["p"])


def _changed(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    return {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}


async def _remove(driver: AsyncDriver, uid: str, email: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid = $uid OR n.user_uid = $uid DETACH DELETE n", uid=uid
        )
        await session.run("MATCH (e:AuthEvent) WHERE e.email = $email DETACH DELETE e", email=email)


@pytest_asyncio.fixture(loop_scope="session")
async def world(skuel_app: FastHTMLApp) -> AsyncIterator[_World]:
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    container = skuel_app.state.container
    services = container.services
    driver: AsyncDriver = services.neo4j_driver
    graph_auth = services.graph_auth

    sessions: dict[str, tuple[str, str]] = {}
    emails: dict[str, str] = {}
    for who, name in (("learner", "Nadia Old"), ("admin", "Ada Admin")):
        username = f"name_{who}_{_RUN}"
        emails[who] = f"{username}@example.com"
        signup = await graph_auth.sign_up(
            email=emails[who], password=_PASSWORD, username=username, display_name=name
        )
        assert signup.is_ok, f"sign_up failed: {signup.error}"
        signin = await graph_auth.sign_in(email=emails[who], password=_PASSWORD)
        assert signin.is_ok, f"sign_in failed: {signin.error}"
        sessions[who] = (signup.value["user_uid"], signin.value["session_token"])
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) SET u.role = 'admin'", uid=sessions["admin"][0]
        )

    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="display-name-test-key")
    app.user_middleware.append(Middleware(AuthContextMiddleware, graph_auth=graph_auth))

    @rt("/sign-in/{who}")
    def sign_in(request: Request, who: str) -> PlainTextResponse:
        uid, token = sessions[who]
        set_current_user(request, user_uid=UserUID(uid), session_token=token)
        return PlainTextResponse("ok")

    await _wire_all_routes(app, rt, services, container.config, container.prometheus_metrics)

    def client() -> httpx.AsyncClient:
        token = mint_token()
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={CSRF_COOKIE_NAME: token},
            headers={CSRF_HEADER_NAME: token},
            timeout=60,
        )

    async with client() as learner, client() as admin:
        assert (await learner.get("/sign-in/learner")).status_code == 200
        assert (await admin.get("/sign-in/admin")).status_code == 200
        yield _World(
            app,
            driver,
            _Account(sessions["learner"][0], learner),
            _Account(sessions["admin"][0], admin),
        )
    for who, (uid, _) in sessions.items():
        await _remove(driver, uid, emails[who])


async def test_the_name_lands_and_nothing_else_on_the_node_changes(world: _World) -> None:
    learner = world.learner
    # A native ``updated_at``, as the role and password writers store it: a write of
    # the whole user would store it back as a string, and show in the diff.
    async with world.driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) SET u.updated_at = datetime()", uid=learner.uid
        )
    page = (await learner.client.get("/settings")).text
    assert _card_form(page).fields == [("display_name", "Nadia Old")]
    assert _avatar_letter(page) == "N"
    hue = _avatar_hue(page)
    before = await world.properties(learner.uid)

    saved = await learner.save_name("  Zoë New ")

    assert saved.status_code == 200, saved.text
    assert _card_form(saved.text).fields == [("display_name", "Zoë New")]
    assert "<nav" not in saved.text, "the door answers the card alone"
    after = await world.properties(learner.uid)
    assert _changed(before, after) == {"display_name"}
    assert after["display_name"] == "Zoë New"

    # The next page: the field holds the new name, the avatar its first letter on
    # the same colour.
    page = (await learner.client.get("/settings")).text
    assert _card_form(page).fields == [("display_name", "Zoë New")]
    assert _avatar_letter(page) == "Z"
    assert _avatar_hue(page) == hue
    assert _avatar_letter((await learner.client.get("/submit-activity-report")).text) == "Z"


@pytest.mark.parametrize(
    "typed", ["", "    ", "x" * 101, "two\nlines"], ids=["blank", "spaces", "too-long", "newline"]
)
async def test_a_name_that_is_not_one_is_refused_into_the_card(world: _World, typed: str) -> None:
    learner = world.learner
    before = await world.properties(learner.uid)

    refused = await learner.save_name(typed)

    assert refused.status_code == 400
    assert refused.headers["X-SKUEL-Refusal"] == "rendered"
    assert _card_form(refused.text).fields == [("display_name", before["display_name"])]
    assert 'role="alert"' in refused.text
    assert await world.properties(learner.uid) == before


async def test_a_json_caller_gets_the_stored_name(world: _World) -> None:
    admin = world.admin
    answered = await admin.client.post(DOOR, json={"display_name": " Ada Admin "})
    assert answered.status_code == 200
    assert answered.json() == {"display_name": "Ada Admin"}
    refused = await admin.client.post(DOOR, json={"display_name": " "})
    assert refused.status_code == 400
    assert (await world.properties(admin.uid))["display_name"] == "Ada Admin"


async def test_no_session_is_refused_and_writes_nothing(world: _World) -> None:
    before = await world.properties(world.learner.uid)
    token = mint_token()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=world.app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
    ) as stranger:
        refused = await stranger.post(DOOR, json={"display_name": "Mallory"})
    assert refused.status_code == 401
    assert await world.properties(world.learner.uid) == before


async def test_a_preferences_save_at_the_same_moment_keeps_both(
    skuel_app: FastHTMLApp, world: _World
) -> None:
    learner = world.learner
    user_service = skuel_app.state.services.user
    for trial in range(_TRIALS):
        name, goal = f"Racer {trial}", 30 + trial
        saved, prefs = await asyncio.gather(
            learner.save_name(name),
            user_service.update_preferences(UserUID(learner.uid), {"weekly_task_goal": goal}),
        )
        assert saved.status_code == 200, saved.text
        assert prefs.is_ok, prefs.error
        stored = await user_service.get_user(UserUID(learner.uid))
        assert stored.value.display_name == name, f"trial {trial}: the name was undone"
        assert stored.value.preferences.weekly_task_goal == goal, (
            f"trial {trial}: the preferences save was undone"
        )


async def test_a_page_that_shows_the_user_to_someone_else_reads_the_new_name(
    world: _World,
) -> None:
    """An admin's activity report says who wrote it, on the learner's page."""
    learner, admin = world.learner, world.admin
    written = await admin.client.post(
        FEEDBACK,
        content=urlencode({"subject_uid": learner.uid, "feedback_text": "A steady week."}),
        headers=FORM_ENCODED,
    )
    assert written.status_code == 200, written.text
    async with world.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (r:ActivityReport {user_uid: $uid}) RETURN r.uid AS uid", uid=learner.uid
            )
        ).single()
    assert record is not None
    detail = f"/activity-reports/detail/content?uid={record['uid']}"
    assert "From Ada Admin" in unescape((await learner.client.get(detail)).text)

    assert (await admin.save_name("Grace Reviewer")).status_code == 200

    page = unescape((await learner.client.get(detail)).text)
    assert "From Grace Reviewer" in page
    assert "Ada Admin" not in page
