"""``/`` is one landing for every role (ADR-058, amended).

Driven through a real app with a real session: a helper route writes the
session flags the login flow would, then ``/`` is fetched without following
redirects. The contract is role-blind — an admin session lands exactly where
a member's does — so both flags are exercised.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.fasthtml_types import Request
from adapters.inbound.system_ui import create_system_ui_routes


def _client() -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="test-only")

    @rt("/_session")
    def _session(request: Request, admin: bool = False) -> str:
        """Write the session the login flow writes — the request's own
        session, so the cookie round-trips through the middleware."""
        request.session["user_uid"] = "user_x"
        request.session["is_admin"] = admin
        return "ok"

    create_system_ui_routes(app, rt, MagicMock())
    return TestClient(app)


def test_anonymous_root_is_the_login_landing() -> None:
    response = _client().get("/", follow_redirects=False)
    assert response.status_code == 200
    assert 'action="/login/submit"' in response.text


@pytest.mark.parametrize("admin", [False, True])
def test_authenticated_root_is_today_for_every_role(admin: bool) -> None:
    client = _client()
    assert client.get("/_session", params={"admin": str(admin).lower()}).status_code == 200
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/today"
