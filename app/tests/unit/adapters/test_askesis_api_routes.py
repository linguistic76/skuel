"""Askesis API security/wiring pins (adapters/inbound/askesis_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): PIN tests over
the single surviving Askesis route (``GET /api/askesis/ask``, ADR-059
follow-up) — auth gate (401), the fail-secure ADR-043 per-user AI tier gate
(missing tier config denies; REGISTERED users resolve to CORE even on a FULL
system), the question input guard refusing before the RAG pipeline, and exact
service args on the happy path. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.askesis_api import create_askesis_api_routes
from adapters.inbound.rate_limit import llm_quota_allowed, reset_buckets_for_testing
from core.config.intelligence_tier import IntelligenceTier
from core.constants import LLMQuota
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_owner"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _clean_quota_buckets():
    # /api/askesis/ask records daily-quota units — clean buckets so tests
    # never accumulate against the shared _USER_UID.
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    return user


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    askesis: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.MEMBER,
    intelligence_tier: IntelligenceTier | None = IntelligenceTier.FULL,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    askesis_service = MagicMock()
    askesis_service.answer_user_question = AsyncMock(
        return_value=Result.ok({"answer": "Practice.", "confidence": 0.9})
    )

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.askesis_api.require_authenticated_user", _fake_auth)

    create_askesis_api_routes(
        app,
        rt,
        askesis_service,
        intelligence_tier=intelligence_tier,
        user_service=user_service,
    )
    return _Harness(client=TestClient(app), askesis=askesis_service)


class TestAuthGate:
    def test_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/askesis/ask?question=hello")

        assert response.status_code == 401
        harness.askesis.answer_user_question.assert_not_awaited()


class TestAiTierGate:
    def test_missing_tier_config_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Fail-secure: no tier configured means the gate cannot be evaluated.
        harness = _make_harness(monkeypatch, intelligence_tier=None)

        response = harness.client.get("/api/askesis/ask?question=hello")

        assert response.status_code == 403
        harness.askesis.answer_user_question.assert_not_awaited()

    def test_registered_user_denied_on_full_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ADR-043: REGISTERED users resolve to CORE even when the system is FULL.
        harness = _make_harness(monkeypatch, role=UserRole.REGISTERED)

        response = harness.client.get("/api/askesis/ask?question=hello")

        assert response.status_code == 403
        harness.askesis.answer_user_question.assert_not_awaited()


class TestInputGuards:
    def test_missing_question_refuses_before_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/askesis/ask")

        assert response.status_code == 400
        harness.askesis.answer_user_question.assert_not_awaited()


class TestLlmQuotaGate:
    """Daily LLM quota on the Askesis RAG pipeline (PR #800 Codex P1)."""

    def _exhaust_quota(self) -> None:
        for _ in range(LLMQuota.DAILY_LIMIT):
            assert llm_quota_allowed(_USER_UID)

    def test_member_over_quota_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        self._exhaust_quota()

        response = harness.client.get("/api/askesis/ask?question=hello")

        assert response.status_code == 403
        harness.askesis.answer_user_question.assert_not_awaited()

    def test_validation_failure_burns_no_quota(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The unit is recorded after the question guard — a 400 must not
        # consume the user's last unit.
        harness = _make_harness(monkeypatch)
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)

        response = harness.client.get("/api/askesis/ask")

        assert response.status_code == 400
        assert llm_quota_allowed(_USER_UID) is True

    def test_ask_records_one_unit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/askesis/ask?question=hello")

        assert response.status_code == 200
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)
        assert llm_quota_allowed(_USER_UID) is False


class TestHappyPath:
    def test_question_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(
            "/api/askesis/ask?question=What%20should%20I%20learn%20next%3F&session_id=sess_1"
        )

        assert response.status_code == 200
        assert response.json()["answer"] == "Practice."
        harness.askesis.answer_user_question.assert_awaited_once_with(
            _USER_UID, "What should I learn next?", session_id="sess_1", model=None
        )

    def test_session_id_defaults_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/askesis/ask?question=hello")

        assert response.status_code == 200
        harness.askesis.answer_user_question.assert_awaited_once_with(
            _USER_UID, "hello", session_id=None, model=None
        )

    def test_model_query_param_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/askesis/ask?question=hello&model=gpt-4o-mini")

        assert response.status_code == 200
        harness.askesis.answer_user_question.assert_awaited_once_with(
            _USER_UID, "hello", session_id=None, model="gpt-4o-mini"
        )
