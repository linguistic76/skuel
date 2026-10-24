"""A write route answers POST only — GET and HEAD are 405 and run nothing.

``@rt(path)`` with no ``methods=`` answers GET, HEAD and POST, and ``csrf_protected``
lets GET / HEAD / OPTIONS through unchecked by design. A write registered that way
runs on a link, an image URL inside rendered content or a browser prefetch, with the
viewer's session and no token — the reason the reader crawl in
``test_link_reader_far_nodes.py`` leaves every mutation path out.

Every write the bootstrap wires is driven here over real HTTP, as a signed-in user,
per route family:

- the CRUD factory's ``create`` / ``update`` / ``delete`` on every Activity domain —
  a GET answers 405 and the graph is unchanged (read back through the same doors);
  the POST control creates and deletes;
- the hand-written ``@csrf_protected`` writes (admin accounts, system registry,
  settings, pathways progress, performance, batch transcription, the auth forms,
  Askesis) — a GET and a HEAD answer 405; the POST control reaches the handler
  stack (any status but 405: the CSRF, role or body gate answers, never the router).

The static half — a registration that names no ``methods=`` fails
``scripts/audit_route_security.py`` — is ``tests/unit/test_route_security_audit.py``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from fasthtml.core import FastHTML
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import set_current_user
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.fasthtml_types import Request
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, wipe

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "postonly"
CALLER = seed_user_uid(f"{MARK}_caller")

# The hand-written writes, by route family. Each path is a `@csrf_protected` handler
# registered with methods=["POST"]; the admin reset-token door is one of the account
# doors, CSRF-protected and POST-only like its siblings.
CSRF_WRITES: dict[str, tuple[str, ...]] = {
    "admin": (
        "/api/admin/users/role",
        "/api/admin/users/deactivate",
        "/api/admin/users/activate",
        "/api/admin/users/hard-delete",
        "/api/admin/users/reset-password",
    ),
    "system": (
        "/api/services/register",
        "/api/services/unregister",
        "/api/alerts/thresholds",
    ),
    "settings": ("/settings/save",),
    "pathways": ("/api/pathways/progress",),
    "auth": (
        "/register/submit",
        "/login/submit",
        "/forgot-password",
        "/reset-password/submit",
    ),
}
# Families the bootstrap wires only when the named service is composed (FULL tier).
TIER_WRITES: dict[str, tuple[str, ...]] = {
    "batch_transcription": (
        "/api/journals/batch-transcribe",
        "/api/journals/folder-transcribe",
    ),
    "askesis": ("/askesis/api/submit",),
}
# The factory-applied writes the table carries beside the CRUD three: the field
# doors (POST /api/{domain}/{uid}/{field} — every field goes through the one
# registration site in activity_field_api_factory.py, so the two fields the Activity
# domains declare prove the site; /api/{domain}/{uid}/children is a read), the link
# doors, the hierarchy edge doors, and the AI doors.
_FACTORY_WRITES = (
    re.compile(r"^/api/[^/]+/\{uid\}/(status|priority)$"),
    re.compile(r"^/api/[^/]+/link-[a-z-]+$"),
    re.compile(r"^/api/[^/]+/(add-child|remove-child)$"),
    re.compile(r"^/api/[^/]+/ai/[a-z-]+$"),
)
ACTIVITY_SEGMENTS = ("tasks", "goals", "habits", "events", "choices", "principles")
# The fields a domain's create door requires beyond what the rig fills in.
_CREATE_EXTRAS: dict[str, dict[str, str]] = {
    "events": {"event_date": "2030-01-01", "start_time": "09:00", "end_time": "10:00"},
}
_CRUD_WRITE = re.compile(r"^/api/[^/]+/(create|update|delete)$")
# What csrf_protected passes through unchecked.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


Wired = tuple[FastHTML, httpx.AsyncClient]


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def wired(skuel_app: Any) -> AsyncIterator[Wired]:  # boundary: fasthtml-app
    """The whole route tree the bootstrap wires, and a client signed in as CALLER."""
    from fasthtml.common import fast_app

    from scripts.dev.bootstrap import _wire_all_routes

    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await wipe(driver, CALLER, MARK)
    async with driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=CALLER)

    container = skuel_app.state.container
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="post-only-test-key")
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
        yield app, client
    await wipe(driver, CALLER, MARK)


def _routes_at(app: FastHTML, path: str) -> list[set[str]]:
    return [
        set(getattr(route, "methods", None) or ())
        for route in app.routes
        if getattr(route, "path", None) == path
    ]


def _composed(skuel_app: Any, service: str) -> bool:  # boundary: fasthtml-app
    return getattr(skuel_app.state.container.services, service) is not None


def _csrf_writes(skuel_app: Any) -> list[str]:  # boundary: fasthtml-app
    """Every hand-written write this app wires — the tier-bound families when composed."""
    paths = [path for family in CSRF_WRITES.values() for path in family]
    for service, family in TIER_WRITES.items():
        if _composed(skuel_app, service):
            paths.extend(family)
    return paths


def _has_own_reader(app: FastHTML, path: str) -> bool:
    """A GET-only registration beside the write (``/api/alerts/thresholds`` has one)."""
    return any("GET" in methods and "POST" not in methods for methods in _routes_at(app, path))


# ── The route table ──────────────────────────────────────────────────────────


async def test_every_crud_write_in_the_table_answers_post_only(wired: Wired) -> None:
    app, _client = wired
    writes = {
        route.path: set(route.methods or ())
        for route in app.routes
        if _CRUD_WRITE.match(getattr(route, "path", "") or "")
        or any(pattern.match(getattr(route, "path", "") or "") for pattern in _FACTORY_WRITES)
    }
    # Positive controls: the six Activity domains' three writes are in the table,
    # as are a field door, a link door and a hierarchy door; a CRUD read still
    # answers GET.
    for segment in ACTIVITY_SEGMENTS:
        for write in ("create", "update", "delete"):
            assert f"/api/{segment}/{write}" in writes, (segment, write)
    for door in ("/api/tasks/{uid}/status", "/api/goals/link-knowledge", "/api/tasks/add-child"):
        assert door in writes, door
    assert "GET" in next(iter(_routes_at(app, "/api/tasks/get")))

    # A write names an unsafe verb — POST, or DELETE where that is the route's
    # contract (/api/form-submissions/delete) — and no safe one.
    safe_reachable = {
        path: methods for path, methods in writes.items() if not methods or methods & SAFE_METHODS
    }
    assert safe_reachable == {}, safe_reachable


async def test_every_csrf_write_in_the_table_answers_post_only(
    wired: Wired,
    skuel_app: Any,  # boundary: fasthtml-app
) -> None:
    app, _client = wired
    for path in _csrf_writes(skuel_app):
        registrations = _routes_at(app, path)
        assert registrations, f"{path} is not wired"
        # /forgot-password also carries its GET page, on its own registration.
        assert [methods for methods in registrations if "POST" in methods] == [{"POST"}], (
            path,
            registrations,
        )
    for service, family in TIER_WRITES.items():
        if not _composed(skuel_app, service):
            assert [path for path in family if _routes_at(app, path)] == [], service


# ── GET and HEAD are refused before any handler ──────────────────────────────


async def test_get_and_head_of_a_csrf_write_are_405(
    wired: Wired,
    skuel_app: Any,  # boundary: fasthtml-app
) -> None:
    app, client = wired
    # Positive control: a GET that reaches a handler is answered by the handler.
    assert (await client.get("/api/tasks/get", params={"uid": "nothing"})).status_code == 404
    for path in _csrf_writes(skuel_app):
        got = await client.get(path, params={"uid": CALLER})
        head = await client.head(path, params={"uid": CALLER})
        if _has_own_reader(app, path):
            # The path's GET is its reader's — answered by that handler, never 405.
            assert got.status_code != 405 and head.status_code != 405, path
            continue
        assert got.status_code == 405, (path, got.status_code)
        assert head.status_code == 405, (path, head.status_code)


async def test_post_of_a_csrf_write_reaches_its_handler(
    wired: Wired,
    skuel_app: Any,  # boundary: fasthtml-app
) -> None:
    # The control for the 405s: the same paths, on POST, are answered by the
    # handler stack — a role gate, a body gate or the handler itself — never 405.
    _app, client = wired
    for path in _csrf_writes(skuel_app):
        response = await client.post(path, params={"uid": CALLER}, json={})
        assert response.status_code != 405, (path, response.status_code)


# ── A CRUD write on GET changes nothing ──────────────────────────────────────


@pytest.mark.parametrize("segment", ACTIVITY_SEGMENTS)
async def test_crud_write_on_get_is_405_and_the_graph_is_unchanged(
    wired: Wired, segment: str
) -> None:
    _app, client = wired
    title = f"{MARK} {segment} keeps"
    uid = await create(client, segment, title, **_CREATE_EXTRAS.get(segment, {}))

    # create: nothing minted.
    ghost = f"{MARK} {segment} ghost"
    response = await client.get(f"/api/{segment}/create", params={"title": ghost})
    assert response.status_code == 405
    listed = await client.get(f"/api/{segment}/list")
    assert listed.status_code == 200
    assert ghost not in listed.text
    assert title in listed.text  # the control is listed

    # update: the title stands.
    response = await client.get(
        f"/api/{segment}/update", params={"uid": uid, "title": f"{MARK} renamed"}
    )
    assert response.status_code == 405
    got = await client.get(f"/api/{segment}/get", params={"uid": uid})
    assert got.status_code == 200
    assert got.json()["title"] == title

    # delete: the entity stands.
    response = await client.get(f"/api/{segment}/delete", params={"uid": uid})
    assert response.status_code == 405
    assert (await client.get(f"/api/{segment}/get", params={"uid": uid})).status_code == 200

    # The POST control: the same door, on POST, deletes.
    response = await client.post(f"/api/{segment}/delete", params={"uid": uid})
    assert response.status_code == 200, response.text
    assert (await client.get(f"/api/{segment}/get", params={"uid": uid})).status_code == 404
