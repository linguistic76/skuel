"""Malformed-JSON chokepoint guard (adapters/inbound/boundary.py).

FastHTML pre-parses ``application/json`` bodies during parameter extraction,
BEFORE any handler runs — a malformed body raises ``JSONDecodeError`` past
every route-level guard and used to surface as a 500.
``install_malformed_json_guard`` (wired once in bootstrap's
``_create_web_app``) maps it to the same ``Errors.validation`` 400 shape the
rest of the API boundary emits. Harness mirrors
``test_admin_api_security.py`` — real ``fast_app`` + ``TestClient``.
"""

from __future__ import annotations

from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.boundary import install_malformed_json_guard


def _make_client(*, raise_server_exceptions: bool = True) -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)
    install_malformed_json_guard(app)

    @rt("/echo", methods=["POST"])
    def echo(confirm: str = "") -> dict[str, str]:
        return {"confirm": confirm}

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


class TestMalformedJsonGuard:
    def test_malformed_json_body_is_400_validation(self) -> None:
        client = _make_client()

        response = client.post(
            "/echo",
            content=b"not json",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 400
        body = response.json()
        assert body["category"] == "validation"
        assert body["code"] == "VALIDATION_GENERIC"

    def test_valid_json_body_still_reaches_handler(self) -> None:
        client = _make_client()

        response = client.post("/echo", json={"confirm": "erase"})

        assert response.status_code == 200
        assert response.json()["confirm"] == "erase"

    def test_decode_error_on_non_json_request_stays_500(self) -> None:
        # A JSONDecodeError escaping a handler on a request that never declared
        # a JSON content type is a server bug, not client input — the guard
        # must re-raise so it keeps its 500.
        import json

        app, rt = fast_app(pico=False, default_hdrs=False)
        install_malformed_json_guard(app)

        @rt("/boom", methods=["POST"])
        def boom() -> dict[str, str]:
            json.loads("not json")
            return {"unreachable": "yes"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/boom", content=b"x", headers={"content-type": "text/plain"})

        assert response.status_code == 500

    def test_without_guard_malformed_json_is_500(self) -> None:
        # Pins WHY the chokepoint exists: with no guard installed, FastHTML's
        # param extraction lets the JSONDecodeError escape as a 500.
        app, rt = fast_app(pico=False, default_hdrs=False)

        @rt("/echo", methods=["POST"])
        def echo(confirm: str = "") -> dict[str, str]:
            return {"confirm": confirm}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/echo",
            content=b"not json",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 500
