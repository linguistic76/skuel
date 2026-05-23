"""Regression guard for the interim FastHTML empty-`application/json` parse_form shim.

FastHTML's ``parse_form`` runs for every route before handlers and crashes
(``JSONDecodeError``) on an empty body with ``Content-Type: application/json`` — so a
bodyless POST sent with that header 500s framework-side (e.g. ``POST /api/ps/{uid}/engage``).
``adapters.inbound.fasthtml_empty_json_patch`` mirrors FastHTML's own empty-multipart
guard for the json case.

These tests drive a real FastHTML app through Starlette's ``TestClient``, so they exercise
the actual ``_wrap_req`` → ``parse_form`` path. If a FastHTML upgrade ever changes that
internal (so the monkeypatch no longer takes effect), ``test_empty_json_body_does_not_500``
fails loudly instead of silently reintroducing the 500. Remove this shim + test once a
FastHTML release carrying the upstream fix is pinned (see
``docs/upstream/FASTHTML_EMPTY_JSON_PARSE_FORM.md``).
"""

import fasthtml.core as fhcore
from fasthtml.common import FastHTML
from starlette.requests import Request
from starlette.testclient import TestClient

from adapters.inbound.fasthtml_empty_json_patch import (
    _original_parse_form,
    apply_empty_json_parse_form_patch,
)


def _client() -> TestClient:
    apply_empty_json_parse_form_patch()
    app = FastHTML()

    @app.post("/noBody")
    async def no_body(request):  # bodyless action route, like engage
        return "ok"

    @app.post("/withBody")
    async def with_body(request, a: int = 0):
        return f"a={a}"

    # raise_server_exceptions=False → a framework 500 surfaces as a 500 response
    # (rather than re-raising), so we can assert on status codes deterministically.
    return TestClient(app, raise_server_exceptions=False)


def test_empty_json_body_does_not_500():
    """A bodyless POST with Content-Type: application/json reaches the handler (200, not 500)."""
    resp = _client().post("/noBody", headers={"content-type": "application/json"})
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    assert resp.text == "ok"


def test_non_empty_json_body_still_parsed():
    """The shim delegates non-empty bodies to the original parse_form (no behavior change)."""
    resp = _client().post("/withBody", json={"a": 7})
    assert resp.status_code == 200
    assert resp.text == "a=7"


def test_patch_is_installed_and_idempotent():
    apply_empty_json_parse_form_patch()
    first = fhcore.parse_form
    apply_empty_json_parse_form_patch()
    assert fhcore.parse_form is first  # idempotent — re-applying doesn't re-wrap


def _empty_json_request() -> Request:
    """A POST Request with Content-Type: application/json and an empty body."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


async def test_shim_is_still_required():
    """Tripwire: fails once FastHTML handles an empty application/json body natively.

    Runs the *original* (pre-shim) ``parse_form`` that the installed FastHTML shipped.
    While the gap remains, it raises ``ValueError`` (JSONDecodeError) on an empty json
    body and this test passes — the shim is still doing real work. Once a FastHTML
    release carrying AnswerDotAI/fasthtml#880 is pinned, the original returns ``{}``
    and this test FAILS, which is the signal to retire the workaround: delete
    ``adapters/inbound/fasthtml_empty_json_patch.py``, its bootstrap Step-0 call,
    this test file, and ``docs/upstream/FASTHTML_EMPTY_JSON_PARSE_FORM.md``. This keeps
    the temporary monkeypatch from silently outliving its purpose.
    """
    try:
        result = await _original_parse_form(_empty_json_request())
    except ValueError:
        return  # FastHTML still raises on empty json → shim still required (expected)
    raise AssertionError(
        f"FastHTML's parse_form now returns {result!r} for an empty application/json body "
        "— the interim shim is redundant. Remove fasthtml_empty_json_patch.py, its bootstrap "
        "Step-0 call, this test file, and docs/upstream/FASTHTML_EMPTY_JSON_PARSE_FORM.md "
        "(upstream fix: AnswerDotAI/fasthtml#880)."
    )
