"""Choices API security/wiring pins (adapters/inbound/choices_api.py).

Testing-gap roadmap item 6 (first tranche): the per-domain ``*_api.py``
mutation modules had zero TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd since they were written).
These are PIN tests, not exhaustive coverage: real ``fast_app`` + TestClient
against mocked services, pinning the auth gate (401), CSRF enforcement (403),
ownership-verification semantics (unowned entity → 404, service never
touched), one happy-path mutation with exact service args, the input guards
that must refuse BEFORE the service, and the field-update factory wiring.
Harness mirrors ``test_admin_api_security.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.choices_api import create_choices_api_routes
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_CHOICE_UID = "choice_1"
_CHILD_UID = "choice_2"
_PRINCIPLE_UID = "principle_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _not_owned(resource: str, uid: str) -> Result[bool]:
    return Result.fail(Errors.not_found(resource, uid))


def _make_choices_service() -> MagicMock:
    service = MagicMock()
    service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    service.get_subchoices = AsyncMock(return_value=Result.ok([]))
    service.get_parent_choice = AsyncMock(return_value=Result.ok(None))
    service.get_choice_hierarchy = AsyncMock(return_value=Result.ok({}))
    service.create_subchoice_relationship = AsyncMock(return_value=Result.ok(True))
    service.remove_subchoice_relationship = AsyncMock(return_value=Result.ok(True))
    service.link_choice_to_goal = AsyncMock(return_value=Result.ok(True))
    service.link_choice_to_principle = AsyncMock(return_value=Result.ok(True))
    service.find_choices_aligned_with_principle = AsyncMock(return_value=Result.ok([]))
    service.analyze_learning_patterns = AsyncMock(return_value=Result.ok([]))
    service.update_choice = AsyncMock(return_value=Result.ok(MagicMock()))
    return service


def _make_ownership_service() -> MagicMock:
    service = MagicMock()
    service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    return service


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    choices: MagicMock
    goals: MagicMock
    principles: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    choices_service = _make_choices_service()
    goals_service = _make_ownership_service()
    principles_service = _make_ownership_service()

    if authenticated:
        # Patch at the names the target modules actually use (module-level import).
        monkeypatch.setattr("adapters.inbound.choices_api.require_authenticated_user", _fake_auth)
        monkeypatch.setattr(
            "adapters.inbound.route_factories.activity_field_api_factory."
            "require_authenticated_user",
            _fake_auth,
        )

    create_choices_api_routes(app, rt, choices_service, goals_service, principles_service)
    return _Harness(
        client=TestClient(app),
        choices=choices_service,
        goals=goals_service,
        principles=principles_service,
    )


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_children_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get(f"/api/choices/children?uid={_CHOICE_UID}")

        assert response.status_code == 401
        harness.choices.verify_ownership.assert_not_awaited()
        harness.choices.get_subchoices.assert_not_awaited()


class TestCsrfEnforcement:
    def test_add_child_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/choices/add-child",
            json={"parent_uid": _CHOICE_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 403
        harness.choices.create_subchoice_relationship.assert_not_awaited()


class TestOwnershipVerification:
    def test_children_of_unowned_choice_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.choices.verify_ownership.return_value = _not_owned("choice", _CHOICE_UID)

        response = harness.client.get(f"/api/choices/children?uid={_CHOICE_UID}")

        assert response.status_code == 404
        harness.choices.verify_ownership.assert_awaited_once_with(_CHOICE_UID, _USER_UID)
        harness.choices.get_subchoices.assert_not_awaited()

    def test_link_principle_with_unowned_principle_is_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cross-service ownership: choice owned, target principle owned by
        # another user — must surface as not-found, link never created.
        harness = _make_harness(monkeypatch)
        harness.principles.verify_ownership.return_value = _not_owned("principle", _PRINCIPLE_UID)

        response = _post_json(
            harness.client,
            "/api/choices/link-principle",
            {"choice_uid": _CHOICE_UID, "principle_uid": _PRINCIPLE_UID},
        )

        assert response.status_code == 404
        harness.principles.verify_ownership.assert_awaited_once_with(_PRINCIPLE_UID, _USER_UID)
        harness.choices.link_choice_to_principle.assert_not_awaited()


class TestLinkPrincipleHappyPath:
    def test_link_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/choices/link-principle",
            {
                "choice_uid": _CHOICE_UID,
                "principle_uid": _PRINCIPLE_UID,
                "alignment_score": 0.75,
            },
        )

        assert response.status_code == 200
        assert response.json() == {"linked": True}
        harness.choices.link_choice_to_principle.assert_awaited_once_with(
            _CHOICE_UID, _PRINCIPLE_UID, 0.75
        )


class TestAddChildWiring:
    def test_add_child_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/choices/add-child",
            {"parent_uid": _CHOICE_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 200
        assert response.json() == {"added": True}
        harness.choices.create_subchoice_relationship.assert_awaited_once_with(
            _CHOICE_UID, _CHILD_UID
        )

    def test_child_with_existing_parent_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.choices.get_parent_choice.return_value = Result.ok(MagicMock())

        response = _post_json(
            harness.client,
            "/api/choices/add-child",
            {"parent_uid": _CHOICE_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 400
        harness.choices.create_subchoice_relationship.assert_not_awaited()


class TestInputGuards:
    def test_children_missing_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/choices/children")

        assert response.status_code == 400
        harness.choices.verify_ownership.assert_not_awaited()
        harness.choices.get_subchoices.assert_not_awaited()

    def test_add_child_self_parent_refuses_before_ownership(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/choices/add-child",
            {"parent_uid": _CHOICE_UID, "child_uid": _CHOICE_UID},
        )

        assert response.status_code == 400
        harness.choices.verify_ownership.assert_not_awaited()
        harness.choices.create_subchoice_relationship.assert_not_awaited()


class TestFieldUpdateRoutes:
    def test_invalid_priority_never_reaches_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # create_activity_field_api_routes wiring: route exists (not 404),
        # ownership is checked, and the PRIORITY_VALUES whitelist refuses the
        # garbage value before the facade update. Response is an HTMX inline
        # error banner fragment (200), so pin service args, not the body.
        harness = _make_harness(monkeypatch)

        token = mint_token()
        harness.client.cookies.set(CSRF_COOKIE_NAME, token)
        response = harness.client.post(
            f"/api/choices/{_CHOICE_UID}/priority",
            data={"priority": "galactic"},
            headers={CSRF_HEADER_NAME: token},
        )

        assert response.status_code == 200
        harness.choices.verify_ownership.assert_awaited_once_with(_CHOICE_UID, _USER_UID)
        harness.choices.update_choice.assert_not_awaited()
