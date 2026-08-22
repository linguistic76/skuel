"""CRUDRouteFactory search route authenticates and threads the user (ADR-085 G7).

``_register_search_route`` used to call the ``search_handler`` with no user at
all and no authentication — a latent unscoped read the moment any wiring
enabled it (none does today; the pin exists so the first wiring inherits the
closed shape). The route now mirrors the list route: USER_OWNED scope
authenticates and hands the handler ``user_uid``; SHARED scope passes
``user_uid=None`` for anonymous browse.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from starlette.exceptions import HTTPException

from adapters.inbound.route_factories.crud_route_factory import CRUDRouteFactory
from core.models.enums import ContentScope
from core.utils.result_simplified import Result


def _get_request() -> SimpleNamespace:
    """Minimal request shape: the CSRF wrapper reads .method (GET = safe)."""
    return SimpleNamespace(method="GET")


class _MockRouter:
    """Route decorator stand-in that records registered handlers by path."""

    def __init__(self) -> None:
        self.routes: dict[str, Any] = {}

    def __call__(self, path: str):
        def decorator(func):
            self.routes[path] = func
            return func

        return decorator


class _RecordingHandler:
    """search_handler stand-in recording the kwargs it was called with."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Result[list[Any]]:
        self.calls.append(kwargs)
        return Result.ok([])


def _make_factory(scope: ContentScope, handler: _RecordingHandler) -> CRUDRouteFactory:
    from pydantic import BaseModel

    class _CreateRequest(BaseModel):
        title: str

    class _UpdateRequest(BaseModel):
        title: str | None = None

    return CRUDRouteFactory(
        service=object(),  # search route never touches the service
        domain_name="tasks",
        create_schema=_CreateRequest,
        update_schema=_UpdateRequest,
        enable_search=True,
        search_handler=handler,
        scope=scope,
    )


@pytest.mark.anyio
async def test_user_owned_search_authenticates_and_threads_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _RecordingHandler()
    factory = _make_factory(ContentScope.USER_OWNED, handler)
    router = _MockRouter()

    def _fake_auth(request: Any) -> str:
        return "user_owner"

    monkeypatch.setattr(
        "adapters.inbound.route_factories.crud_route_factory.require_authenticated_user",
        _fake_auth,
    )

    factory._register_search_route(router)
    search = router.routes["/api/tasks/search"]

    response = await search(_get_request(), query="alpha")

    assert getattr(response, "status_code", 200) == 200
    assert handler.calls == [{"query": "alpha", "limit": 50, "offset": 0, "user_uid": "user_owner"}]


@pytest.mark.anyio
async def test_shared_search_passes_anonymous_user(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _RecordingHandler()
    factory = _make_factory(ContentScope.SHARED, handler)
    router = _MockRouter()

    def _explode(request: Any) -> str:
        raise AssertionError("SHARED search must not require authentication")

    monkeypatch.setattr(
        "adapters.inbound.route_factories.crud_route_factory.require_authenticated_user",
        _explode,
    )

    factory._register_search_route(router)
    search = router.routes["/api/tasks/search"]

    response = await search(_get_request(), query="alpha")

    assert getattr(response, "status_code", 200) == 200
    assert handler.calls[0]["user_uid"] is None


@pytest.mark.anyio
async def test_user_owned_search_refuses_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The auth gate runs BEFORE the handler — an anonymous caller never reaches it."""
    handler = _RecordingHandler()
    factory = _make_factory(ContentScope.USER_OWNED, handler)
    router = _MockRouter()

    def _refuse(request: Any) -> str:
        raise HTTPException(401, "Authentication required")

    monkeypatch.setattr(
        "adapters.inbound.route_factories.crud_route_factory.require_authenticated_user",
        _refuse,
    )

    factory._register_search_route(router)
    search = router.routes["/api/tasks/search"]

    with pytest.raises(HTTPException):
        await search(_get_request(), query="alpha")

    assert handler.calls == []
