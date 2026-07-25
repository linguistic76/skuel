"""Batch transcription API security/wiring pins (adapters/inbound/batch_transcription_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the two batch-transcription doors — the ADMIN gate on the console route
(401/403), CSRF on both, and the Codex-P1 security contract on the user
folder route: client-supplied paths are IGNORED, the je_in/je_out staging
dirs come from ``JournalBatchService`` server-side. Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.batch_transcription_api import create_batch_transcription_api_routes
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.rate_limit import llm_quota_allowed, reset_buckets_for_testing
from core.config.intelligence_tier import IntelligenceTier
from core.constants import LLMQuota
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_admin"
_JE_IN = Path("/srv/vault/je_in")
_JE_OUT = Path("/srv/vault/je_out")


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
    # folder-transcribe records daily-quota units — clean buckets so tests
    # never accumulate against the shared _USER_UID.
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


def _batch_result() -> MagicMock:
    batch = MagicMock()
    batch.total_files = 2
    batch.succeeded = 2
    batch.failed = 0
    batch.skipped = 0
    batch.results = []
    batch.errors = []
    return batch


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    batch: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
    intelligence_tier: IntelligenceTier | None = IntelligenceTier.FULL,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    batch_service = MagicMock()
    batch_service.preview = MagicMock(
        return_value=Result.ok(
            MagicMock(files=[], total_files=0, total_size_mb=0.0, already_transcribed=0)
        )
    )
    batch_service.transcribe_batch = AsyncMock(return_value=Result.ok(_batch_result()))

    journal_batch = MagicMock()
    journal_batch.je_in_dir = _JE_IN
    journal_batch.je_out_dir = _JE_OUT

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.batch_transcription_api.require_authenticated_user", _fake_auth
        )
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_batch_transcription_api_routes(
        None,
        rt,
        batch_service,
        journal_batch,
        user_service=user_service,
        intelligence_tier=intelligence_tier,
    )
    return _Harness(client=TestClient(app), batch=batch_service)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAdminGate:
    def test_batch_transcribe_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, "/api/journals/batch-transcribe", {})

        assert response.status_code == 401
        harness.batch.transcribe_batch.assert_not_awaited()

    def test_batch_transcribe_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(harness.client, "/api/journals/batch-transcribe", {})

        assert response.status_code == 403
        harness.batch.transcribe_batch.assert_not_awaited()


class TestCsrfEnforcement:
    def test_folder_transcribe_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/journals/folder-transcribe", json={})

        assert response.status_code == 403
        harness.batch.transcribe_batch.assert_not_awaited()


class TestFolderTranscribeTierGate:
    """Per-user AI gate (ADR-043): transcription spends Deepgram money, so
    effective-CORE (REGISTERED) users are denied before any work happens."""

    def test_registered_user_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.REGISTERED)

        response = _post_json(harness.client, "/api/journals/folder-transcribe", {})

        assert response.status_code == 403
        harness.batch.transcribe_batch.assert_not_awaited()
        harness.batch.preview.assert_not_called()

    def test_missing_tier_fails_secure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No system tier wired → the gate cannot be evaluated → deny, not allow.
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER, intelligence_tier=None)

        response = _post_json(harness.client, "/api/journals/folder-transcribe", {})

        assert response.status_code == 403
        harness.batch.transcribe_batch.assert_not_awaited()

    def test_member_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(harness.client, "/api/journals/folder-transcribe", {})

        assert response.status_code == 200
        harness.batch.transcribe_batch.assert_awaited_once()


class TestFolderTranscribePathPinning:
    def test_client_supplied_paths_are_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Codex P1: accepting client paths would let any authenticated user
        # read/write arbitrary server directories. The je_* staging dirs are
        # fixed server-side.
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(
            harness.client,
            "/api/journals/folder-transcribe",
            {"input_dir": "/etc", "output_dir": "/tmp/exfil", "skip_existing": False},
        )

        assert response.status_code == 200
        harness.batch.transcribe_batch.assert_awaited_once_with(
            input_dir=_JE_IN, output_dir=_JE_OUT, skip_existing=False
        )

    def test_preview_only_never_transcribes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(
            harness.client, "/api/journals/folder-transcribe", {"preview_only": True}
        )

        assert response.status_code == 200
        assert response.json()["preview"] is True
        harness.batch.preview.assert_called_once_with(_JE_IN, _JE_OUT)
        harness.batch.transcribe_batch.assert_not_awaited()


class TestFolderTranscribeQuotaGate:
    """Daily LLM quota on the user folder-transcribe door (PR C2)."""

    def _exhaust_quota(self) -> None:
        for _ in range(LLMQuota.DAILY_LIMIT):
            assert llm_quota_allowed(_USER_UID)

    def test_member_over_quota_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)
        self._exhaust_quota()

        response = _post_json(harness.client, "/api/journals/folder-transcribe", {})

        assert response.status_code == 403
        harness.batch.transcribe_batch.assert_not_awaited()

    def test_preview_at_quota_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Preview spends no Deepgram money, so it neither burns nor requires quota.
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)
        self._exhaust_quota()

        response = _post_json(
            harness.client, "/api/journals/folder-transcribe", {"preview_only": True}
        )

        assert response.status_code == 200
        assert response.json()["preview"] is True
        harness.batch.transcribe_batch.assert_not_awaited()

    def test_real_run_records_one_unit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(harness.client, "/api/journals/folder-transcribe", {})

        assert response.status_code == 200
        harness.batch.transcribe_batch.assert_awaited_once()
        # Exactly one unit recorded: the window drains after LIMIT - 1 more.
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)
        assert llm_quota_allowed(_USER_UID) is False


class TestAdminBatchTranscribe:
    def test_defaults_applied_and_batch_awaited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/journals/batch-transcribe", {})

        assert response.status_code == 200
        payload = response.json()
        assert payload["preview"] is False
        assert payload["succeeded"] == 2
        harness.batch.transcribe_batch.assert_awaited_once_with(
            input_dir=Path("data/je_inputs"),
            output_dir=Path("data/je_outputs"),
            skip_existing=True,
        )
