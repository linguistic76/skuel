"""Security pins for OwnershipRouteFactory (the horizontal-authz gate).

Every USER_OWNED domain routes its per-entity reads and mutations through this
factory — a hole here is an IDOR across all of them at once. These tests pin
the generated route's ordering guarantees: authentication first, then the
ownership check (404, never 403 — no UID enumeration), and the service method
is only reached after both pass. SHARED scope skips ownership by design.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.route_factories.ownership_route_factory import (
    OwnershipRoute,
    OwnershipRouteFactory,
)
from core.models.enums import ContentScope
from core.utils.result_simplified import Errors, Result

_OWNER_UID = "user_owner"
_ENTITY_UID = "task_abc123"

_AUTH_TARGET = "adapters.inbound.route_factories.ownership_route_factory.require_authenticated_user"


class _TrackRequest(BaseModel):
    habit_uid: str = ""
    note: str = ""


def _fake_owner_auth(request: object) -> str:
    return _OWNER_UID


def _raise_401(request: object) -> str:
    raise HTTPException(401, "Authentication required")


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    owned: bool = True,
    authenticated: bool = True,
    scope: ContentScope = ContentScope.USER_OWNED,
) -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    ownership = (
        Result.ok(True)
        if owned
        else Result.fail(Errors.not_found(resource="task", identifier=_ENTITY_UID))
    )
    service.verify_ownership = AsyncMock(return_value=ownership)
    service.get_streak = AsyncMock(return_value=Result.ok({"streak": 3}))
    service.track = AsyncMock(return_value=Result.ok({"tracked": True}))

    monkeypatch.setattr(_AUTH_TARGET, _fake_owner_auth if authenticated else _raise_401)

    factory = OwnershipRouteFactory(
        service=service,
        domain_name="tasks",
        scope=scope,
        routes=[
            OwnershipRoute(path="/api/tasks/streak", method_name="get_streak"),
            OwnershipRoute(
                path="/api/tasks/track",
                method_name="track",
                request_schema=_TrackRequest,
                schema_extra_uid_field="habit_uid",
            ),
        ],
    )
    factory.register_routes(app, rt)
    return TestClient(app), service


def _post_json(client: TestClient, path: str, json: dict[str, object]):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthenticationFirst:
    def test_unauthenticated_is_401_and_never_touches_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch, authenticated=False)

        response = client.get(f"/api/tasks/streak?uid={_ENTITY_UID}")

        assert response.status_code == 401
        service.verify_ownership.assert_not_awaited()
        service.get_streak.assert_not_awaited()


class TestOwnershipGate:
    def test_non_owned_entity_is_404_not_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch, owned=False)

        response = client.get(f"/api/tasks/streak?uid={_ENTITY_UID}")

        # 404 (not 403) so an attacker cannot enumerate valid UIDs.
        assert response.status_code == 404
        service.verify_ownership.assert_awaited_once_with(_ENTITY_UID, _OWNER_UID)
        service.get_streak.assert_not_awaited()

    def test_non_owned_post_never_parses_into_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch, owned=False)

        response = _post_json(
            client, f"/api/tasks/track?uid={_ENTITY_UID}", {"note": "attacker payload"}
        )

        assert response.status_code == 404
        service.track.assert_not_awaited()

    def test_owned_entity_reaches_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = client.get(f"/api/tasks/streak?uid={_ENTITY_UID}")

        assert response.status_code == 200
        service.verify_ownership.assert_awaited_once_with(_ENTITY_UID, _OWNER_UID)
        service.get_streak.assert_awaited_once_with(_ENTITY_UID)

    def test_owned_post_injects_uid_into_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_json(client, f"/api/tasks/track?uid={_ENTITY_UID}", {"note": "hi"})

        assert response.status_code == 200
        model = service.track.await_args.args[0]
        assert model.habit_uid == _ENTITY_UID
        assert model.note == "hi"

    def test_missing_uid_param_is_400_before_ownership(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = client.get("/api/tasks/streak")

        assert response.status_code == 400
        service.verify_ownership.assert_not_awaited()
        service.get_streak.assert_not_awaited()


class TestSharedScope:
    def test_shared_scope_skips_ownership_but_still_authenticates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch, scope=ContentScope.SHARED)

        response = client.get(f"/api/tasks/streak?uid={_ENTITY_UID}")

        assert response.status_code == 200
        service.verify_ownership.assert_not_awaited()
        service.get_streak.assert_awaited_once_with(_ENTITY_UID)

    def test_shared_scope_still_rejects_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch, scope=ContentScope.SHARED, authenticated=False)

        response = client.get(f"/api/tasks/streak?uid={_ENTITY_UID}")

        assert response.status_code == 401
        service.get_streak.assert_not_awaited()
