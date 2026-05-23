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
from starlette.testclient import TestClient

from adapters.inbound.fasthtml_empty_json_patch import apply_empty_json_parse_form_patch


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
