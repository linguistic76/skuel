"""Principles API security/wiring pins (adapters/inbound/principles_api.py).

Testing-gap roadmap item 6 (first tranche): the per-domain ``*_api.py``
mutation modules had zero TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd since they were written).
These are PIN tests, not exhaustive coverage: real ``fast_app`` + TestClient
against a mocked PrinciplesService, pinning the auth gate (401), CSRF
enforcement (403), ownership-verification semantics (unowned principle → 404,
service never touched — including the conflicting-principle branch of
reflection), the reflection happy path with exact service kwargs, the input
guards that must refuse BEFORE the service, and the field-update factory
wiring. Harness mirrors ``test_admin_api_security.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.principles_api import create_principles_api_routes
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_PRINCIPLE_UID = "principle_1"
_CONFLICT_UID = "principle_2"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _not_owned(uid: str) -> Result[bool]:
    return Result.fail(Errors.not_found("principle", uid))


def _make_principles_service() -> MagicMock:
    service = MagicMock()
    service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    service.get_subprinciples = AsyncMock(return_value=Result.ok([]))
    service.get_parent_principle = AsyncMock(return_value=Result.ok(None))
    service.get_principle_hierarchy = AsyncMock(return_value=Result.ok({}))
    service.create_subprinciple_relationship = AsyncMock(return_value=Result.ok(True))
    service.remove_subprinciple_relationship = AsyncMock(return_value=Result.ok(True))
    service.link_principle_to_knowledge = AsyncMock(return_value=Result.ok(True))
    service.create_principle_expression = AsyncMock(return_value=Result.ok({"created": True}))
    service.get_user_principle_portfolio = AsyncMock(return_value=Result.ok({}))
    service.calculate_principle_integrity = AsyncMock(return_value=Result.ok({}))
    service.create_principle_link = AsyncMock(return_value=Result.ok({"linked": True}))
    service.get_principle_links = AsyncMock(return_value=Result.ok([]))
    service.get_quick_principle_impact = AsyncMock(return_value=Result.ok({}))
    service.batch_analyze_principle_adoption = AsyncMock(return_value=Result.ok({}))
    service.get_choice_guidance_effectiveness = AsyncMock(return_value=Result.ok({}))
    service.record_principle_reflection = AsyncMock(return_value=Result.ok({"recorded": True}))
    service.analyze_learning_patterns = AsyncMock(return_value=Result.ok([]))
    service.update_principle = AsyncMock(return_value=Result.ok(MagicMock()))
    return service


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)

    principles_service = _make_principles_service()

    if authenticated:
        # Patch at the names the target modules actually use (module-level import).
        monkeypatch.setattr(
            "adapters.inbound.principles_api.require_authenticated_user", _fake_auth
        )
        monkeypatch.setattr(
            "adapters.inbound.route_factories.activity_field_api_factory."
            "require_authenticated_user",
            _fake_auth,
        )

    create_principles_api_routes(app, rt, principles_service)
    return TestClient(app), principles_service


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


def _reflection_body() -> dict[str, object]:
    return {
        "principle_uid": _PRINCIPLE_UID,
        "alignment_level": "aligned",
        "evidence": "Kept my commitment under pressure",
        "reflection_quality_score": 0.8,
    }


class TestAuthGate:
    def test_portfolio_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch, authenticated=False)

        response = client.get("/api/principles/portfolio")

        assert response.status_code == 401
        service.get_user_principle_portfolio.assert_not_awaited()


class TestCsrfEnforcement:
    def test_reflection_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post("/api/principles/reflection", json=_reflection_body())

        assert response.status_code == 403
        service.record_principle_reflection.assert_not_awaited()


class TestOwnershipVerification:
    def test_integrity_of_unowned_principle_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)
        service.verify_ownership.return_value = _not_owned(_PRINCIPLE_UID)

        response = client.get(f"/api/principles/integrity?uid={_PRINCIPLE_UID}")

        assert response.status_code == 404
        service.verify_ownership.assert_awaited_once_with(_PRINCIPLE_UID, _USER_UID)
        service.calculate_principle_integrity.assert_not_awaited()

    def test_reflection_with_unowned_conflicting_principle_is_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The conflicting-principle branch runs a SECOND ownership check —
        # another user's principle in that slot must 404 and record nothing.
        client, service = _make_client(monkeypatch)
        service.verify_ownership.side_effect = [Result.ok(True), _not_owned(_CONFLICT_UID)]
        body = _reflection_body()
        body["conflicting_principle_uid"] = _CONFLICT_UID

        response = _post_json(client, "/api/principles/reflection", body)

        assert response.status_code == 404
        assert service.verify_ownership.await_count == 2
        service.record_principle_reflection.assert_not_awaited()


class TestReflectionHappyPath:
    def test_reflection_awaited_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_json(client, "/api/principles/reflection", _reflection_body())

        assert response.status_code == 200
        assert response.json() == {"recorded": True}
        service.record_principle_reflection.assert_awaited_once_with(
            principle_uid=_PRINCIPLE_UID,
            user_uid=_USER_UID,
            alignment_level="aligned",
            evidence="Kept my commitment under pressure",
            trigger_type=None,
            trigger_uid=None,
            conflicting_principle_uid=None,
            reflection_quality_score=0.8,
        )


class TestInputGuards:
    def test_reflection_invalid_alignment_level_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)
        body = _reflection_body()
        body["alignment_level"] = "transcendent"

        response = _post_json(client, "/api/principles/reflection", body)

        assert response.status_code == 400
        service.verify_ownership.assert_not_awaited()
        service.record_principle_reflection.assert_not_awaited()

    def test_integrity_missing_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = client.get("/api/principles/integrity")

        assert response.status_code == 400
        service.verify_ownership.assert_not_awaited()
        service.calculate_principle_integrity.assert_not_awaited()


class TestFieldUpdateRoutes:
    def test_invalid_priority_never_reaches_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # create_activity_field_api_routes wiring: route exists (not 404),
        # ownership is checked, and the PRIORITY_VALUES whitelist refuses the
        # garbage value before the facade update. Response is an HTMX inline
        # error banner fragment (200), so pin service args, not the body.
        client, service = _make_client(monkeypatch)

        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            f"/api/principles/{_PRINCIPLE_UID}/priority",
            data={"priority": "galactic"},
            headers={CSRF_HEADER_NAME: token},
        )

        assert response.status_code == 200
        service.verify_ownership.assert_awaited_once_with(_PRINCIPLE_UID, _USER_UID)
        service.update_principle.assert_not_awaited()
