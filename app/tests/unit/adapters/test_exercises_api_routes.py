"""Exercises API security/wiring pins (adapters/inbound/exercises_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): the
domain-specific exercise routes had zero TestClient coverage. These are PIN
tests, not exhaustive coverage: real ``fast_app`` + TestClient against mocked
services, pinning the auth gate (401), CSRF enforcement (403), the ADR-043
per-user AI tier gate on report generation (fail-secure), the report's
admission (``EntryReportService.admit_report`` decides who may have the
reviewer read an entry; the route asks it, answers its refusal, and hands the
writer only what it admitted), exact service args on the happy path, and the
teacher-role gate on curriculum linking (whose admission —
``ExerciseService.admit_requirement_change`` — the route asks before either
write, pinned through the real route in
``tests/integration/routes/test_exercise_required_knowledge_owner.py``). Who admission admits is pinned in
``tests/unit/services/test_entry_report_service.py`` and, through the real
route, in ``tests/integration/routes/test_ai_report_admission.py``. Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.exercises_api import create_exercises_api_routes
from adapters.inbound.rate_limit import llm_quota_allowed, reset_buckets_for_testing
from core.config.intelligence_tier import IntelligenceTier
from core.constants import LLMQuota
from core.models.enums import EntityType, ExerciseScope, UserRole
from core.models.exercises.exercise import Exercise
from core.services.exercises.exercise_service import AdmittedRequirementChange
from core.services.report.entry_report_service import AdmittedReport
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_SUBMISSION_UID = "entry_1"
_EXERCISE_UID = "exercise_1"
_CURRICULUM_UID = "ku_curriculum_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _reset_quota_buckets():
    # /api/exercises/report records daily-quota units — clean buckets so
    # tests never accumulate against the shared _USER_UID.
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    # Role decorators check user.has_permission(required) on the entity —
    # bind the real hierarchy-aware enum method.
    user.has_permission = role.has_permission
    return user


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    exercises: MagicMock
    reports: MagicMock
    admitted: AdmittedReport
    users: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.MEMBER,
    admitted: bool = True,
    intelligence_tier: IntelligenceTier | None = IntelligenceTier.FULL,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    exercise = MagicMock()
    exercise.uid = _EXERCISE_UID
    exercise.title = "Sample Exercise"

    exercises_service = MagicMock()
    exercises_service.get_exercise = AsyncMock(return_value=Result.ok(exercise))
    exercises_service.get_exercise_for_user = AsyncMock(return_value=Result.ok(exercise))
    exercises_service.get_exercise_for_submission = AsyncMock(
        return_value=Result.ok({"exercise_uid": _EXERCISE_UID})
    )
    requirement_change = AdmittedRequirementChange(_EXERCISE_UID, _USER_UID)
    exercises_service.admit_requirement_change = AsyncMock(
        return_value=Result.ok(requirement_change)
        if admitted
        else Result.fail(Errors.not_found("Exercise", _EXERCISE_UID))
    )
    exercises_service.link_to_curriculum = AsyncMock(return_value=Result.ok(True))
    exercises_service.unlink_from_curriculum = AsyncMock(return_value=Result.ok(True))
    exercises_service.get_required_knowledge_for_user = AsyncMock(return_value=Result.ok([]))
    exercises_service.get_exercises_for_curriculum = AsyncMock(return_value=Result.ok([]))

    report_entity = MagicMock()
    report_entity.uid = "report_1"
    report_entity.content = "feedback"
    admission = AdmittedReport(entry=MagicMock(), exercise=exercise, caller_uid=_USER_UID)
    entry_report_service = MagicMock()
    entry_report_service.admit_report = AsyncMock(
        return_value=Result.ok(admission)
        if admitted
        else Result.fail(Errors.not_found("UserEntry", _SUBMISSION_UID))
    )
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
        entry_report_service,
        user_service=user_service,
        intelligence_tier=intelligence_tier,
    )
    return _Harness(
        client=TestClient(app),
        exercises=exercises_service,
        reports=entry_report_service,
        admitted=admission,
        users=user_service,
    )


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


_REPORT_BODY = {"submission_uid": _SUBMISSION_UID, "exercise_uid": _EXERCISE_UID}


class TestLlmQuotaGate:
    """Daily LLM quota on the AI reviewer (PR #800 Codex P1)."""

    def _exhaust_quota(self) -> None:
        for _ in range(LLMQuota.DAILY_LIMIT):
            assert llm_quota_allowed(_USER_UID)

    def test_member_over_quota_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        self._exhaust_quota()

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 403
        harness.reports.generate_report.assert_not_awaited()

    def test_access_denial_burns_no_quota(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The unit is recorded after admission — a refused request's 404 must
        # not consume the caller's last unit.
        harness = _make_harness(monkeypatch, admitted=False)
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 404
        harness.reports.generate_report.assert_not_awaited()
        assert llm_quota_allowed(_USER_UID) is True

    def test_report_records_one_unit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 200
        harness.reports.generate_report.assert_awaited_once()
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)
        assert llm_quota_allowed(_USER_UID) is False


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


class TestReportAdmission:
    def test_the_route_asks_admission_with_the_caller_and_both_uids(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        harness.reports.admit_report.assert_awaited_once_with(
            _SUBMISSION_UID, _EXERCISE_UID, caller_uid=_USER_UID, caller_role=UserRole.TEACHER
        )

    def test_a_refused_admission_is_404_and_reaches_no_reviewer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Not-found (never 403) so entry UIDs don't leak (OWNERSHIP_VERIFICATION).
        harness = _make_harness(monkeypatch, admitted=False)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 404
        harness.reports.generate_report.assert_not_awaited()

    def test_happy_path_generates_on_the_admission_with_exact_args(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/exercises/report", _REPORT_BODY)

        assert response.status_code == 200
        payload = response.json()
        assert payload["report_uid"] == "report_1"
        assert payload["submission_uid"] == _SUBMISSION_UID
        assert payload["exercise_uid"] == _EXERCISE_UID
        harness.reports.generate_report.assert_awaited_once_with(
            harness.admitted, temperature=0.7, max_tokens=4000
        )


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
        harness.exercises.admit_requirement_change.assert_awaited_once_with(
            _EXERCISE_UID, _USER_UID, UserRole.TEACHER
        )
        harness.exercises.link_to_curriculum.assert_awaited_once_with(
            AdmittedRequirementChange(_EXERCISE_UID, _USER_UID), _CURRICULUM_UID
        )

    @pytest.mark.parametrize(
        ("door", "writer"),
        [
            ("/api/exercises/require-knowledge", "link_to_curriculum"),
            ("/api/exercises/unrequire-knowledge", "unlink_from_curriculum"),
        ],
    )
    def test_a_refused_admission_is_404_and_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, door: str, writer: str
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER, admitted=False)

        response = _post_json(
            harness.client,
            door,
            {"exercise_uid": _EXERCISE_UID, "curriculum_uid": _CURRICULUM_UID},
        )

        assert response.status_code == 404
        getattr(harness.exercises, writer).assert_not_awaited()

    def test_teacher_unlink_awaited_with_the_admission(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = _post_json(
            harness.client,
            "/api/exercises/unrequire-knowledge",
            {"exercise_uid": _EXERCISE_UID, "curriculum_uid": _CURRICULUM_UID},
        )

        assert response.status_code == 200
        harness.exercises.unlink_from_curriculum.assert_awaited_once_with(
            AdmittedRequirementChange(_EXERCISE_UID, _USER_UID), _CURRICULUM_UID
        )


class TestInputGuards:
    def test_required_knowledge_missing_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get("/api/exercises/required-knowledge")

        assert response.status_code == 400
        harness.exercises.get_required_knowledge_for_user.assert_not_awaited()


class TestScopedReads:
    """Both teacher reads hand the service the caller: the audience is the service's rule."""

    def test_required_knowledge_is_read_as_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get(f"/api/exercises/required-knowledge?uid={_EXERCISE_UID}")

        assert response.status_code == 200
        harness.exercises.get_required_knowledge_for_user.assert_awaited_once_with(
            _EXERCISE_UID, _USER_UID
        )

    def test_exercises_for_curriculum_are_listed_as_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get("/api/exercises/for-curriculum?curriculum_uid=ku_1")

        assert response.status_code == 200
        harness.exercises.get_exercises_for_curriculum.assert_awaited_once_with("ku_1", _USER_UID)


class TestMarkdownDownload:
    def test_missing_exercise_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.exercises.get_exercise_for_user.return_value = Result.ok(None)

        response = harness.client.get(f"/api/exercises/md?uid={_EXERCISE_UID}")

        assert response.status_code == 404

    def test_download_reads_through_the_audience_scoped_method(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The worksheet body is the exercise — this read must be scoped.

        Pinned at the wiring level because both methods answer alike here:
        without this, reverting the route to the unscoped ``get_exercise``
        would leave every other assertion in this class still green.
        """
        harness = _make_harness(monkeypatch)
        # A real Exercise, not the harness MagicMock: the renderer runs on the
        # 200 path, so only a real one reaches the assertions below.
        harness.exercises.get_exercise_for_user.return_value = Result.ok(
            Exercise(
                uid=_EXERCISE_UID,
                title="Sample Exercise",
                entity_type=EntityType.EXERCISE,
                instructions="do the thing",
                scope=ExerciseScope.PERSONAL,
                owner_uid=_USER_UID,
            )
        )

        response = harness.client.get(f"/api/exercises/md?uid={_EXERCISE_UID}")

        assert response.status_code == 200
        harness.exercises.get_exercise_for_user.assert_awaited_once_with(_EXERCISE_UID, _USER_UID)
        harness.exercises.get_exercise.assert_not_awaited()
