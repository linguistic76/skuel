"""Exercises UI teacher-route pins (adapters/inbound/exercises_ui.py).

The three ``@require_teacher`` routes are driven through FastHTML's own
parameter binding — a real ``fast_app`` + TestClient — because the binding is
the contract under test. ``require_role``'s wrapper takes ``request``
positionally, and FastHTML fills the call from the *handler's* parameter
names; a handler that names its request anything else (``_request``) leaves
that positional unfilled and every request to the route is a ``TypeError``.
Hand-calling the handler with ``request=`` (as the integration audience tests
do) cannot see that, so these pins go through the client.

Pinned per route: the injected ``current_user`` is the caller (the owner
check receives its uid), the status is what the role gate and the body say,
and MEMBER is still refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.exercises_ui import create_exercises_ui_routes
from core.models.enums import EntityType, ExerciseScope, UserRole
from core.models.exercises.exercise import Exercise
from core.utils.result_simplified import Result

_USER_UID = "user_teacher"
_EXERCISE_UID = "exercise_1"
_TITLE = "Photosynthesis drill"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    # Role decorators check user.has_permission(required) on the entity —
    # bind the real hierarchy-aware enum method.
    user.has_permission = role.has_permission
    return user


def _exercise() -> Exercise:
    return Exercise(
        uid=_EXERCISE_UID,
        title=_TITLE,
        entity_type=EntityType.EXERCISE,
        instructions="Explain the light-dependent reactions.",
        scope=ExerciseScope.PERSONAL,
        owner_uid=_USER_UID,
    )


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    exercises: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.TEACHER,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    exercises = MagicMock()
    exercises.verify_ownership = AsyncMock(return_value=Result.ok(_exercise()))
    exercises.get_required_knowledge = AsyncMock(return_value=Result.ok([]))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_exercises_ui_routes(app, rt, exercises, user_service=user_service)
    return _Harness(client=TestClient(app), exercises=exercises)


class TestTeacherRoutesBindThroughFastHTML:
    def test_new_form_renders(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/exercises/new")

        assert response.status_code == 200

    @pytest.mark.parametrize("path", ["/exercises/{uid}/edit", "/exercises/{uid}/view"])
    def test_owner_check_receives_the_injected_user(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(path.format(uid=_EXERCISE_UID))

        assert response.status_code == 200
        assert _TITLE in response.text
        harness.exercises.verify_ownership.assert_awaited_once_with(_EXERCISE_UID, _USER_UID)


class TestRoleGateStillApplies:
    @pytest.mark.parametrize(
        "path", ["/exercises/new", "/exercises/{uid}/edit", "/exercises/{uid}/view"]
    )
    def test_member_is_403(self, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get(path.format(uid=_EXERCISE_UID))

        assert response.status_code == 403
        harness.exercises.verify_ownership.assert_not_awaited()

    def test_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get(f"/exercises/{_EXERCISE_UID}/edit")

        assert response.status_code == 401
