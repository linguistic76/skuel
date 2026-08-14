"""End-to-end CSRF tests.

Spins up a minimal Starlette app with ``CSRFMiddleware`` plus two routes —
one safe (GET) and one ``@csrf_protected`` (POST) — and exercises the full
double-submit cookie flow over ``TestClient``. Avoids the SKUEL bootstrap
so these tests run without Neo4j/LLM dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from adapters.inbound.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CSRFMiddleware,
    csrf_protected,
)

if TYPE_CHECKING:
    from starlette.requests import Request


def _build_app() -> Starlette:
    async def read(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    @csrf_protected
    async def write(request: Request) -> PlainTextResponse:
        return PlainTextResponse("written")

    async def static_asset(request: Request) -> PlainTextResponse:
        return PlainTextResponse("body {}")

    async def manifest(request: Request) -> PlainTextResponse:
        return PlainTextResponse("{}")

    return Starlette(
        routes=[
            Route("/read", read, methods=["GET"]),
            Route("/write", write, methods=["POST"]),
            Route("/static/css/main.css", static_asset, methods=["GET"]),
            Route("/manifest.json", manifest, methods=["GET"]),
        ],
        middleware=[Middleware(CSRFMiddleware)],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


class TestMiddlewareIssuance:
    def test_first_get_sets_cookie(self, client: TestClient):
        response = client.get("/read")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies
        assert len(response.cookies[CSRF_COOKIE_NAME]) >= 32

    def test_cookie_is_stable_across_requests(self, client: TestClient):
        r1 = client.get("/read")
        token = r1.cookies[CSRF_COOKIE_NAME]
        r2 = client.get("/read")
        # TestClient carries cookies forward — middleware must not re-mint.
        assert r2.cookies.get(CSRF_COOKIE_NAME) in (None, token)
        # Ensure subsequent verifications can succeed with this token.
        assert token


class TestProtectedWrites:
    def test_post_without_token_is_forbidden(self, client: TestClient):
        # Fresh client has no cookie yet; jump straight to POST.
        response = client.post("/write")
        assert response.status_code == 403

    def test_post_with_cookie_but_no_header_is_forbidden(self, client: TestClient):
        client.get("/read")  # mint cookie
        response = client.post("/write")
        assert response.status_code == 403

    def test_post_with_matching_header_succeeds(self, client: TestClient):
        client.get("/read")  # mint cookie
        token = client.cookies[CSRF_COOKIE_NAME]
        response = client.post("/write", headers={CSRF_HEADER_NAME: token})
        assert response.status_code == 200
        assert response.text == "written"

    def test_post_with_matching_form_field_succeeds(self, client: TestClient):
        client.get("/read")
        token = client.cookies[CSRF_COOKIE_NAME]
        response = client.post("/write", data={"csrf_token": token})
        assert response.status_code == 200
        assert response.text == "written"

    def test_post_with_mismatched_header_is_forbidden(self, client: TestClient):
        client.get("/read")
        response = client.post("/write", headers={CSRF_HEADER_NAME: "nope"})
        assert response.status_code == 403


class TestMintExemption:
    """Static assets and PWA subresources must not mint a new token — see
    the comment on `_MINT_EXEMPT_PREFIXES` in `adapters/inbound/csrf.py`."""

    def test_cookieless_static_fetch_does_not_set_cookie(self, client: TestClient):
        response = client.get("/static/css/main.css")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME not in response.cookies

    def test_cookieless_manifest_fetch_does_not_set_cookie(self, client: TestClient):
        response = client.get("/manifest.json")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME not in response.cookies

    def test_static_fetch_does_not_overwrite_existing_cookie(self, client: TestClient):
        client.get("/read")
        token = client.cookies[CSRF_COOKIE_NAME]
        # Simulate a cookieless parallel subresource fetch (preload scanner,
        # service worker install). Must not mint a replacement cookie.
        bare = TestClient(_build_app())
        bare.get("/static/css/main.css")
        assert CSRF_COOKIE_NAME not in bare.cookies
        # Original client's cookie survives and the form-POST flow still works.
        response = client.post("/write", headers={CSRF_HEADER_NAME: token})
        assert response.status_code == 200
