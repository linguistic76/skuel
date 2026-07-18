"""Pathways API security/wiring pins (adapters/inbound/pathways_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): PIN tests over
the domain-specific pathways routes — auth gate (401), CSRF enforcement on
mutations (403), the progress route's mastery-vs-progress branching with
exact recorder kwargs (201 created), the no-knowledge-units input guard, and
the enroll route's HX-Redirect contract. Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.pathways_api import create_pathways_api_routes
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_PATH_UID = "lp.core.stoicism"
_STEP_UID = "ps.core.premeditatio"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _make_step(knowledge_uids: tuple[str, ...]) -> MagicMock:
    step = MagicMock()
    step.knowledge_uids = knowledge_uids
    return step


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    learning: MagicMock
    users: MagicMock
    progress: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    knowledge_uids: tuple[str, ...] = ("ku_a", "ku_b"),
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    learning_service = MagicMock()
    learning_service.get_path_steps = AsyncMock(return_value=Result.ok([]))
    learning_service.get_step = AsyncMock(return_value=Result.ok(_make_step(knowledge_uids)))

    user_service = MagicMock()
    user_service.record_knowledge_mastery = AsyncMock(return_value=Result.ok(True))
    user_service.record_knowledge_progress = AsyncMock(return_value=Result.ok(True))
    user_service.enroll_in_learning_path = AsyncMock(return_value=Result.ok(True))

    user_progress = MagicMock()

    if authenticated:
        monkeypatch.setattr("adapters.inbound.pathways_api.require_authenticated_user", _fake_auth)

    create_pathways_api_routes(
        app, rt, learning_service, user_service=user_service, user_progress=user_progress
    )
    return _Harness(
        client=TestClient(app),
        learning=learning_service,
        users=user_service,
        progress=user_progress,
    )


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_progress_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(
            harness.client,
            "/api/pathways/progress",
            {"step_uid": _STEP_UID, "mastery_level": 0.9, "completed": True},
        )

        assert response.status_code == 401
        harness.users.record_knowledge_mastery.assert_not_awaited()


class TestCsrfEnforcement:
    def test_enroll_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(f"/api/pathways/enroll/{_PATH_UID}")

        assert response.status_code == 403
        harness.users.enroll_in_learning_path.assert_not_awaited()


class TestProgressRecording:
    def test_completed_high_mastery_records_mastery_per_ku(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/pathways/progress",
            {"step_uid": _STEP_UID, "mastery_level": 0.9, "completed": True},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["updated_ku_uids"] == ["ku_a", "ku_b"]
        assert harness.users.record_knowledge_mastery.await_count == 2
        harness.users.record_knowledge_mastery.assert_any_await(
            user_uid=_USER_UID, knowledge_uid="ku_a", mastery_score=0.9
        )
        harness.users.record_knowledge_progress.assert_not_awaited()

    def test_incomplete_records_progress_not_mastery(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/pathways/progress",
            {"step_uid": _STEP_UID, "mastery_level": 0.9, "completed": False},
        )

        assert response.status_code == 201
        assert harness.users.record_knowledge_progress.await_count == 2
        harness.users.record_knowledge_progress.assert_any_await(
            user_uid=_USER_UID, knowledge_uid="ku_a", progress=0.9
        )
        harness.users.record_knowledge_mastery.assert_not_awaited()

    def test_step_without_knowledge_units_refuses_before_recorder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, knowledge_uids=())

        response = _post_json(
            harness.client,
            "/api/pathways/progress",
            {"step_uid": _STEP_UID, "mastery_level": 0.9, "completed": True},
        )

        assert response.status_code == 400
        harness.users.record_knowledge_mastery.assert_not_awaited()
        harness.users.record_knowledge_progress.assert_not_awaited()


class TestEnrollment:
    def test_enroll_redirects_to_path_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, f"/api/pathways/enroll/{_PATH_UID}")

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == f"/pathways/path/{_PATH_UID}"
        harness.users.enroll_in_learning_path.assert_awaited_once_with(_USER_UID, _PATH_UID)

    def test_enroll_failure_surfaces_error_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.users.enroll_in_learning_path.return_value = Result.fail(
            Errors.not_found("LearningPath", _PATH_UID)
        )

        response = _post_json(harness.client, f"/api/pathways/enroll/{_PATH_UID}")

        assert response.status_code == 404


class TestReadRoutes:
    def test_steps_forwards_path_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/pathways/steps?path_uid={_PATH_UID}")

        assert response.status_code == 200
        harness.learning.get_path_steps.assert_awaited_once_with(_PATH_UID)
