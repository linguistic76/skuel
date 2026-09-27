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
and MEMBER is still refused. The ``/exercises/content`` fragment is
authentication-gated only: a failed read renders the banner, never the empty
state.
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


class TestExerciseListFragment:
    """``/exercises/content`` — the teacher's own list, where Delete lives.

    A failed read renders the error banner inside the fragment, never the empty
    state: an empty state over a failed read tells a teacher their exercises are
    gone. ``ui_boundary_handler`` renders the same banner text for any exception
    in the handler, so each case also pins that the service was awaited with the
    caller and that the boundary's logger never fired — the banner comes from the
    handler's failed-read branch, not from a blow-up.
    """

    _EMPTY_STATE = "No exercises yet"

    def _get(
        self, monkeypatch: pytest.MonkeyPatch, listed: Result[list[Exercise]]
    ) -> tuple[_Harness, str, int]:
        monkeypatch.setattr("adapters.inbound.exercises_ui.require_authenticated_user", _fake_auth)
        harness = _make_harness(monkeypatch)
        harness.exercises.list_user_exercises = AsyncMock(return_value=listed)
        boundary_logger = MagicMock()
        monkeypatch.setattr("adapters.inbound.boundary.logger", boundary_logger)
        response = harness.client.get("/exercises/content")
        harness.exercises.list_user_exercises.assert_awaited_once_with(_USER_UID)
        # The banner must come from the handler's failed-read branch, never
        # from the boundary's catch-all over a blow-up.
        boundary_logger.error.assert_not_called()
        return harness, response.text, response.status_code

    def test_a_failed_read_shows_the_banner_not_the_empty_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.utils.result_simplified import Errors

        _, body, status = self._get(
            monkeypatch, Result.fail(Errors.database(operation="list", message="boom"))
        )

        assert status == 200
        assert 'id="exercises-content"' in body
        assert "Error loading exercises" in body
        assert self._EMPTY_STATE not in body

    def test_no_exercises_is_the_empty_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, body, status = self._get(monkeypatch, Result.ok([]))

        assert status == 200
        assert self._EMPTY_STATE in body

    def test_an_exercise_renders_its_card_with_delete(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, body, status = self._get(monkeypatch, Result.ok([_exercise()]))

        assert status == 200
        assert _TITLE in body
        assert f'hx-post="/api/exercises/delete?uid={_EXERCISE_UID}"' in body
