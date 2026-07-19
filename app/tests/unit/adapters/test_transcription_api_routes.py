"""Transcription API security/wiring pins (adapters/inbound/transcription_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the transcription CRUD/processing routes — auth gate (401), CSRF enforcement
on mutations (403), ownership verification refusing before the service (404,
never 403), query input guards (400), and exact service args on the create
happy path. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.transcription_api import create_transcription_api_routes
from core.models.transcription.transcription import TranscriptionCreateRequest
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_TRANSCRIPTION_UID = "transcription_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _transcription() -> MagicMock:
    entity = MagicMock()
    entity.to_dict.return_value = {"uid": _TRANSCRIPTION_UID, "status": "pending"}
    return entity


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    service: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.create = AsyncMock(return_value=Result.ok(_transcription()))
    service.verify_ownership = AsyncMock(return_value=Result.ok(_transcription()))
    service.delete = AsyncMock(return_value=Result.ok(True))
    service.list = AsyncMock(return_value=Result.ok([]))
    service.process = AsyncMock(return_value=Result.ok(_transcription()))
    service.retry = AsyncMock(return_value=Result.ok(_transcription()))
    service.search = AsyncMock(return_value=Result.ok([]))
    service.get_by_status = AsyncMock(return_value=Result.ok([]))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.transcription_api.require_authenticated_user", _fake_auth
        )

    create_transcription_api_routes(app, rt, service)
    return _Harness(client=TestClient(app), service=service)


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestAuthGate:
    def test_create_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.post(
            "/api/transcriptions",
            json={"audio_file_path": "/audio/session.mp3"},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 401
        harness.service.create.assert_not_awaited()


class TestCsrfEnforcement:
    def test_create_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/transcriptions", json={"audio_file_path": "/audio/session.mp3"}
        )

        assert response.status_code == 403
        harness.service.create.assert_not_awaited()


class TestCreate:
    def test_create_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/transcriptions",
            json={"audio_file_path": "/audio/session.mp3", "language": "de"},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        assert response.json()["uid"] == _TRANSCRIPTION_UID
        request_arg, user_arg = harness.service.create.await_args.args
        assert isinstance(request_arg, TranscriptionCreateRequest)
        assert request_arg.audio_file_path == "/audio/session.mp3"
        assert request_arg.language == "de"
        assert user_arg == _USER_UID


class TestOwnershipVerification:
    def test_get_unowned_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.verify_ownership.return_value = Result.fail(
            Errors.not_found("transcription", _TRANSCRIPTION_UID)
        )

        response = harness.client.get(f"/api/transcriptions/get?uid={_TRANSCRIPTION_UID}")

        assert response.status_code == 404
        harness.service.verify_ownership.assert_awaited_once_with(_TRANSCRIPTION_UID, _USER_UID)

    def test_process_unowned_never_touches_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.verify_ownership.return_value = Result.fail(
            Errors.not_found("transcription", _TRANSCRIPTION_UID)
        )

        response = harness.client.post(
            f"/api/transcriptions/process?uid={_TRANSCRIPTION_UID}",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 404
        harness.service.process.assert_not_awaited()

    def test_delete_unowned_never_touches_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.verify_ownership.return_value = Result.fail(
            Errors.not_found("transcription", _TRANSCRIPTION_UID)
        )

        response = harness.client.delete(
            f"/api/transcriptions/delete?uid={_TRANSCRIPTION_UID}",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 404
        harness.service.delete.assert_not_awaited()


class TestInputGuards:
    def test_search_missing_query_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/transcriptions/search")

        assert response.status_code == 400
        harness.service.search.assert_not_awaited()

    def test_invalid_status_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/transcriptions/status?status=not-a-status")

        assert response.status_code == 400
        harness.service.get_by_status.assert_not_awaited()


class TestListScoping:
    def test_list_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/transcriptions")

        assert response.status_code == 200
        kwargs = harness.service.list.await_args.kwargs
        assert kwargs["user_uid"] == _USER_UID
        assert kwargs["status"] is None
