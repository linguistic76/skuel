"""Exercises API security/wiring pins (adapters/inbound/exercises_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): the
domain-specific exercise routes had zero TestClient coverage. These are PIN
tests, not exhaustive coverage: real ``fast_app`` + TestClient against mocked
services, pinning the auth gate (401), CSRF enforcement (403), the ADR-043
per-user AI tier gate on report generation (fail-secure), the owner-or-teacher
entry access rule (404, never 403 — UIDs must not leak), the PR #497
fulfilled-exercise pin for non-teachers, exact service kwargs on the happy
path, and the teacher-role gate on curriculum linking. Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.exercises_api import create_exercises_api_routes
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import UserRole
from core.models.user_entry.user_entry import UserEntry
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_SUBMISSION_UID = "entry_1"
_EXERCISE_UID = "exercise_1"
_CURRICULUM_UID = "ku_curriculum_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    # Role decorators check user.has_permission(required) on the entity —
    # bind the real hierarchy-aware enum method.
    user.has_permission = role.has_permission
    return user


def _make_entry(owner_uid: str = _USER_UID) -> MagicMock:
    # spec=UserEntry so the route's isinstance narrowing accepts it.
    entry = MagicMock(spec=UserEntry)
    entry.user_uid = owner_uid
    return entry


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    exercises: MagicMock
    transcripts: MagicMock
    reports: MagicMock
    users: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.MEMBER,
    entry_owner: str = _USER_UID,
    intelligence_tier: IntelligenceTier | None = IntelligenceTier.FULL,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    exercise = MagicMock()
    exercise.uid = _EXERCISE_UID
    exercise.title = "Sample Exercise"

    exercises_service = MagicMock()
    exercises_service.get_exercise = AsyncMock(return_value=Result.ok(exercise))
    exercises_service.get_exercise_for_submission = AsyncMock(
        return_value=Result.ok({"exercise_uid": _EXERCISE_UID})
    )
    exercises_service.link_to_curriculum = AsyncMock(return_value=Result.ok(True))
    exercises_service.unlink_from_curriculum = AsyncMock(return_value=Result.ok(True))
    exercises_service.get_required_knowledge = AsyncMock(return_value=Result.ok([]))
    exercises_service.get_exercises_for_curriculum = AsyncMock(return_value=Result.ok([]))

    transcript_service = MagicMock()
    transcript_service.get = AsyncMock(return_value=Result.ok(_make_entry(entry_owner)))

    report_entity = MagicMock()
    report_entity.uid = "report_1"
    report_entity.content = "feedback"
    entry_report_service = MagicMock()
    entry_report_service.generate_report = AsyncMock(return_value=Result.ok(report_entity))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        # Patch at the names the target modules actually use (module-level import).
        monkeypatch.setattr("adapters.inbound.exercises_api.require_authenticated_user", _fake_auth)
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_exercises_api_routes(
        app,
        rt,
        exercises_service,
        transcript_service,
        entry_report_service,
        user_service=user_service,
        intelligence_tier=intelligence_tier,
    )
    return _Harness(
        client=TestClient(app),
        exercises=exercises_service,
        transcripts=transcript_service,
        reports=entry_report_service,
        users=user_service,
    )


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


_REPORT_BODY = {"submission_uid": _SUBMISSION_UID, "exercise_uid": _EXERCISE_UID}


class TestAuthGate:
    def test_report_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 401
        harness.reports.generate_report.assert_not_awaited()

    def test_require_knowledge_unauthenticated_is_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(
            harness.client,
            "/api/exercises/require-knowledge",
            {"exercise_uid": _EXERCISE_UID, "curriculum_uid": _CURRICULUM_UID},
        )

        assert response.status_code == 401
        harness.exercises.link_to_curriculum.assert_not_awaited()


class TestCsrfEnforcement:
    def test_report_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/exercises/report", json=_REPORT_BODY)

        assert response.status_code == 403
        harness.reports.generate_report.assert_not_awaited()


class TestAiTierGate:
    def test_missing_tier_config_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Fail-secure: no tier configured means the gate cannot be evaluated.
        harness = _make_harness(monkeypatch, intelligence_tier=None)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 422
        harness.reports.generate_report.assert_not_awaited()

    def test_registered_user_denied_on_full_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ADR-043: REGISTERED users resolve to CORE even when the system is FULL.
        harness = _make_harness(monkeypatch, role=UserRole.REGISTERED)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 422
        harness.reports.generate_report.assert_not_awaited()


class TestReportEntryAccess:
    def test_non_teacher_cannot_report_on_foreign_entry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Not-found (never 403) so entry UIDs don't leak (OWNERSHIP_VERIFICATION).
        harness = _make_harness(monkeypatch, entry_owner="user_other")

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 404
        harness.reports.generate_report.assert_not_awaited()

    def test_non_teacher_pinned_to_fulfilled_exercise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # PR #497: a student may only run the exercise their entry FULFILLS.
        harness = _make_harness(monkeypatch)
        harness.exercises.get_exercise_for_submission.return_value = Result.ok(
            {"exercise_uid": "exercise_other"}
        )

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 404
        harness.reports.generate_report.assert_not_awaited()

    def test_owner_happy_path_generates_with_exact_kwargs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 200
        payload = response.json()
        assert payload["report_uid"] == "report_1"
        assert payload["submission_uid"] == _SUBMISSION_UID
        assert payload["exercise_uid"] == _EXERCISE_UID
        kwargs = harness.reports.generate_report.await_args.kwargs
        assert kwargs["user_uid"] == _USER_UID
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 4000
        assert kwargs["entry"].user_uid == _USER_UID
        assert kwargs["exercise"].uid == _EXERCISE_UID


class TestCurriculumLinkingRoleGate:
    def test_non_teacher_cannot_link_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(
            harness.client,
            "/api/exercises/require-knowledge",
            {"exercise_uid": _EXERCISE_UID, "curriculum_uid": _CURRICULUM_UID},
        )

        assert response.status_code == 403
        harness.exercises.link_to_curriculum.assert_not_awaited()

    def test_teacher_link_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = _post_json(
            harness.client,
            "/api/exercises/require-knowledge",
            {"exercise_uid": _EXERCISE_UID, "curriculum_uid": _CURRICULUM_UID},
        )

        assert response.status_code == 200
        harness.exercises.link_to_curriculum.assert_awaited_once_with(
            _EXERCISE_UID, _CURRICULUM_UID
        )


class TestInputGuards:
    def test_required_knowledge_missing_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get("/api/exercises/required-knowledge")

        assert response.status_code == 400
        harness.exercises.get_required_knowledge.assert_not_awaited()


class TestMarkdownDownload:
    def test_missing_exercise_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.exercises.get_exercise.return_value = Result.ok(None)

        response = harness.client.get(f"/api/exercises/md?uid={_EXERCISE_UID}")

        assert response.status_code == 404
