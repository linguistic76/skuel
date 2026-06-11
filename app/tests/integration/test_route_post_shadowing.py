"""Regression test for the POST shadowing bug.

FastHTML's ``@rt(path)`` with no ``methods=`` registers BOTH GET and POST.
Starlette matches the *first*-registered route for a given path+method, so a
page handler declared first as bare ``@rt(path)`` silently SHADOWS a later
``@rt(path, methods=["POST"])`` submit on the same path — the submit never
runs and any CSRF gate on it is bypassed.

These tests pin the framework behavior:

* the *broken* shape (bare-GET page registered first) routes POST to the PAGE
  handler — reproducing the bug, and
* the *fixed* shape (page handler explicitly ``methods=["GET"]``) routes POST
  to the SUBMIT handler.

Builds a minimal ``fast_app`` so it runs without Neo4j/LLM dependencies.
"""

from fasthtml.common import fast_app
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient


def _client_for(page_methods: list[str] | None) -> TestClient:
    """Build an app where /thing/create has a page handler + a POST submit.

    ``page_methods`` controls the page handler's ``@rt`` registration:
    ``None`` = bare ``@rt(path)`` (the buggy GET+POST default), or an explicit
    list like ``["GET"]`` (the fix).
    """
    app, rt = fast_app(pico=False, default_hdrs=False)

    if page_methods is None:

        @rt("/thing/create")
        async def thing_page(request: Request) -> PlainTextResponse:
            return PlainTextResponse("PAGE")

    else:

        @rt("/thing/create", methods=page_methods)
        async def thing_page(request: Request) -> PlainTextResponse:
            return PlainTextResponse("PAGE")

    @rt("/thing/create", methods=["POST"])
    async def thing_submit(request: Request) -> PlainTextResponse:
        return PlainTextResponse("SUBMIT")

    return TestClient(app)


def test_bare_get_page_shadows_post_submit() -> None:
    # Reproduces the bug: bare @rt page registered first wins POST.
    client = _client_for(page_methods=None)
    assert client.get("/thing/create").text == "PAGE"
    assert client.post("/thing/create").text == "PAGE"  # ← submit shadowed


def test_get_only_page_lets_post_reach_submit() -> None:
    # The fix: GET-only page lets the POST submit handler run.
    client = _client_for(page_methods=["GET"])
    assert client.get("/thing/create").text == "PAGE"
    assert client.post("/thing/create").text == "SUBMIT"  # ← submit reached
