"""The malformed-body chokepoint (adapters/inbound/boundary.py).

FastHTML pre-parses every request body during parameter extraction, BEFORE any
handler runs, and refuses one it cannot read — unparseable JSON, a JSON array or
scalar, a multipart body the parser cannot frame, a required field that is
absent — by raising Starlette's ``HTTPException(400)``, which renders as plain
text. Starlette's own form reader raises the same 400 when a handler reads such a
body later. ``install_malformed_body_guard`` (wired once in bootstrap's
``_create_web_app``) answers every such 400 on a request that sent a body
FastHTML parses with the ``Errors.validation`` shape the rest of the API boundary
emits. It is keyed on the 400 status, so the auth guards' 401 and 403 never reach
it. Harness mirrors ``test_admin_api_security.py`` — real ``fast_app`` +
``TestClient``.
"""

from __future__ import annotations

import json

from fasthtml.common import fast_app
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from adapters.inbound.boundary import boundary_handler, install_malformed_body_guard
from adapters.inbound.form_helpers import parse_body
from core.utils.result_simplified import Result


class _Titled(BaseModel):
    title: str


def _make_client(*, guarded: bool = True) -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)
    if guarded:
        install_malformed_body_guard(app)

    @rt("/echo", methods=["POST"])
    def echo(confirm: str = "") -> dict[str, str]:
        return {"confirm": confirm}

    @rt("/required", methods=["POST", "GET"])
    def required(confirm: str) -> dict[str, str]:
        return {"confirm": confirm}

    @rt("/titled", methods=["POST"])
    @boundary_handler()
    async def titled(request) -> Result[dict[str, str]]:
        parsed = await parse_body(request, _Titled)
        if parsed.is_error:
            return Result.fail(parsed)
        return Result.ok({"title": parsed.value.title})

    @rt("/unauthenticated", methods=["POST"])
    def unauthenticated() -> dict[str, str]:
        raise HTTPException(401, "Authentication required")

    @rt("/forbidden", methods=["POST"])
    def forbidden() -> dict[str, str]:
        raise HTTPException(403, "Access denied")

    @rt("/boom", methods=["POST"])
    def boom() -> dict[str, str]:
        json.loads("not json")
        return {"unreachable": "yes"}

    return TestClient(app, raise_server_exceptions=False)


def _assert_validation_400(response, message: str) -> None:
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["category"] == "validation"
    assert body["message"] == message


class TestMalformedJson:
    def test_malformed_json_body_is_400_validation(self) -> None:
        response = _make_client().post(
            "/echo", content=b"not json", headers={"content-type": "application/json"}
        )

        _assert_validation_400(response, "Invalid JSON body")

    def test_a_json_array_or_scalar_body_is_400_validation(self) -> None:
        client = _make_client()

        for body in (b"[1, 2]", b"3", b'"text"'):
            response = client.post(
                "/echo", content=body, headers={"content-type": "application/json"}
            )

            _assert_validation_400(response, "JSON body must be an object")

    def test_valid_json_body_still_reaches_handler(self) -> None:
        response = _make_client().post("/echo", json={"confirm": "erase"})

        assert response.status_code == 200
        assert response.json()["confirm"] == "erase"

    def test_a_charset_json_body_is_read_by_the_route_reader(self) -> None:
        """FastHTML matches ``application/json`` exactly, so a body that names its
        charset skips the pre-parse: the route's own reader reads it, well-formed
        or not, and refuses in the same shape."""
        client = _make_client()
        headers = {"content-type": "application/json; charset=utf-8"}

        ok = client.post("/titled", content=b'{"title": "a"}', headers=headers)
        malformed = client.post("/titled", content=b"not json", headers=headers)
        array = client.post("/titled", content=b"[1, 2]", headers=headers)

        assert ok.status_code == 200
        assert ok.json() == {"title": "a"}
        _assert_validation_400(malformed, "Invalid JSON body")
        assert array.status_code == 400
        assert array.json()["category"] == "validation"

    def test_a_missing_required_field_on_a_json_post_is_400_validation(self) -> None:
        response = _make_client().post("/required", json={})

        _assert_validation_400(response, "Missing required field: confirm")

    def test_a_decode_error_escaping_a_handler_stays_500(self) -> None:
        """Only the framework's 400 is converted: a handler's own JSONDecodeError
        is a server bug, whatever the request declared."""
        response = _make_client().post("/boom", json={"x": 1})

        assert response.status_code == 500


class TestMalformedMultipart:
    def test_unparseable_multipart_body_is_400_validation(self) -> None:
        """A declared boundary the body never uses."""
        response = _make_client().post(
            "/echo",
            content=b"garbage without any boundary markers",
            headers={"content-type": "multipart/form-data; boundary=xyz"},
        )

        assert response.status_code == 400, response.text
        assert response.json()["category"] == "validation"

    def test_multipart_without_a_boundary_is_400_validation(self) -> None:
        response = _make_client().post(
            "/echo",
            content=b"garbage without any boundary markers",
            headers={"content-type": "multipart/form-data"},
        )

        _assert_validation_400(response, "Invalid form-data: no boundary")

    def test_well_formed_multipart_still_reaches_handler(self) -> None:
        response = _make_client().post("/echo", files={"confirm": (None, "erase")})

        assert response.status_code == 200
        assert response.json()["confirm"] == "erase"


class TestWhatTheChokepointLeavesAlone:
    def test_without_the_chokepoint_a_malformed_body_is_plain_text_400(self) -> None:
        """Pins WHY the chokepoint exists: FastHTML refuses the body itself, in
        Starlette's plain-text rendering, not the API's validation shape."""
        response = _make_client(guarded=False).post(
            "/echo", content=b"not json", headers={"content-type": "application/json"}
        )

        assert response.status_code == 400
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == "Invalid JSON body"

    def test_a_400_on_a_request_with_no_body_stays_plain_text(self) -> None:
        """A page load missing a query parameter sent no body to refuse."""
        response = _make_client().get("/required")

        assert response.status_code == 400
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == "Missing required field: confirm"

    def test_auth_refusals_keep_their_status_and_rendering(self) -> None:
        client = _make_client()

        for path, status, detail in (
            ("/unauthenticated", 401, "Authentication required"),
            ("/forbidden", 403, "Access denied"),
        ):
            response = client.post(path, json={"x": 1})

            assert response.status_code == status
            assert response.headers["content-type"].startswith("text/plain")
            assert response.text == detail
