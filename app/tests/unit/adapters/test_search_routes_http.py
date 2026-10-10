"""The methods the two search API doors answer, through a ``TestClient``.

``GET /api/search/intelligent`` is a read with its query in ``q``; ``POST
/api/search/unified`` is CSRF-protected. A route registered without ``methods=``
answers every method FastHTML accepts, so each door's registration is pinned
here, and a ``POST`` to the read is refused before the router runs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fasthtml.common import FastHTML, fast_app
from starlette.routing import Route
from starlette.testclient import TestClient

from adapters.inbound.search_routes import create_search_api_routes


def _app_and_router() -> tuple[FastHTML, MagicMock]:
    app, rt = fast_app()
    search_router = MagicMock()
    search_router.intelligent_search = AsyncMock()
    create_search_api_routes(app, rt, search_router=search_router)
    return app, search_router


def _methods(app: FastHTML, path: str) -> set[str]:
    routes = [route for route in app.routes if isinstance(route, Route) and route.path == path]
    assert len(routes) == 1, f"{path} registered {len(routes)} times"
    return set(routes[0].methods or ())


def test_intelligent_search_is_a_get() -> None:
    app, _router = _app_and_router()

    assert _methods(app, "/api/search/intelligent") == {"GET", "HEAD"}


def test_unified_search_is_a_post() -> None:
    app, _router = _app_and_router()

    assert _methods(app, "/api/search/unified") == {"POST"}


def test_a_post_to_intelligent_search_is_refused_before_the_router_runs() -> None:
    app, search_router = _app_and_router()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/search/intelligent", data={"q": "urgent"})

    assert response.status_code == 405
    search_router.intelligent_search.assert_not_awaited()
