"""UserEntry API security/wiring pins (adapters/inbound/user_entry_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the ADR-054 unified UserEntry REST surface — auth gate (401), CSRF on
mutations (403), the upload-door input guards (missing file / bad pipeline /
unknown audience refuse before the service), ownership 404s (never 403), the
optional-service seams (processing 422 business, grounding 500 unavailable),
and exact service args on the happy paths (201 on create). Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.user_entry_api import create_user_entry_api_routes
from core.models.user_entry.user_entry import UserEntry
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_ENTRY_UID = "user_entry_1"
_KU_UID = "ku_stoicism_abc123"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _entry() -> UserEntry:
    return UserEntry(uid=_ENTRY_UID, title="My Entry", user_uid=_USER_UID)


def _quiet_outcome() -> MagicMock:
    outcome = MagicMock()
    outcome.any_success = False
    outcome.any_failure = False
    return outcome


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    entries: MagicMock
    processing: MagicMock | None
    grounding: MagicMock | None


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    with_processing: bool = True,
    with_grounding: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.create_entry = AsyncMock(return_value=Result.ok((_entry(), _quiet_outcome())))
    service.get_entry = AsyncMock(return_value=Result.ok(_entry()))
    service.list_for_user = AsyncMock(return_value=Result.ok([]))
    service.delete_entry = AsyncMock(return_value=Result.ok(True))

    processing = None
    if with_processing:
        processing = MagicMock()
        processing.process = AsyncMock(return_value=Result.ok(_entry()))

    grounding = None
    if with_grounding:
        grounding = MagicMock()
        grounding.remove = AsyncMock(return_value=Result.ok(True))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.user_entry_api.require_authenticated_user", _fake_auth
        )

    create_user_entry_api_routes(
        None,
        rt,
        service,
        processing_service=processing,
        grounding_service=grounding,
    )
    return _Harness(
        client=TestClient(app), entries=service, processing=processing, grounding=grounding
    )


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestAuthGate:
    def test_create_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.post(
            "/api/user-entries", json={"title": "My Entry"}, headers=_csrf(harness.client)
        )

        assert response.status_code == 401
        harness.entries.create_entry.assert_not_awaited()


class TestCsrfEnforcement:
    def test_delete_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(f"/api/user-entries/delete?uid={_ENTRY_UID}")

        assert response.status_code == 403
        harness.entries.delete_entry.assert_not_awaited()


class TestCreate:
    def test_created_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user-entries", json={"title": "My Entry"}, headers=_csrf(harness.client)
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["user_entry"]["uid"] == _ENTRY_UID
        assert "share_outcome" not in payload
        kwargs = harness.entries.create_entry.await_args.kwargs
        assert kwargs["user_uid"] == _USER_UID
        assert kwargs["request"].title == "My Entry"


class TestUploadGuards:
    def test_missing_file_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user-entries/upload", data={"title": "x"}, headers=_csrf(harness.client)
        )

        assert response.status_code == 400
        harness.entries.create_entry.assert_not_awaited()

    def test_invalid_pipeline_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user-entries/upload",
            data={"pipeline": "not-a-pipeline"},
            files={"file": ("entry.md", b"# Notes", "text/markdown")},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 400
        harness.entries.create_entry.assert_not_awaited()

    def test_unknown_audience_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user-entries/upload",
            data={"audience": "everyone"},
            files={"file": ("entry.md", b"# Notes", "text/markdown")},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 400
        harness.entries.create_entry.assert_not_awaited()

    def test_text_upload_carries_content_onto_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Worksheet turn-ins whose text is dropped can never receive feedback —
        # texty uploads must land on entry.content.
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user-entries/upload",
            files={"file": ("entry.md", b"# Notes", "text/markdown")},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 201
        req = harness.entries.create_entry.await_args.kwargs["request"]
        assert req.content == "# Notes"
        assert req.title == "entry.md"


class TestOptionalServiceSeams:
    def test_process_without_processing_service_is_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, with_processing=False)

        response = harness.client.post(
            "/api/user-entries/process",
            json={"uid": _ENTRY_UID},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 422

    def test_grounding_remove_without_service_is_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, with_grounding=False)

        response = harness.client.post(
            f"/api/user-entries/grounding/remove?uid={_ENTRY_UID}&ku_uid={_KU_UID}",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 500


class TestOwnership:
    def test_get_unowned_entry_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.entries.get_entry.return_value = Result.ok(None)

        response = harness.client.get(f"/api/user-entries/get?uid={_ENTRY_UID}")

        assert response.status_code == 404
        harness.entries.get_entry.assert_awaited_once_with(_ENTRY_UID, _USER_UID)


class TestList:
    def test_invalid_pipeline_filter_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/user-entries?pipeline=bogus")

        assert response.status_code == 400
        harness.entries.list_for_user.assert_not_awaited()


class TestDelete:
    def test_delete_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/user-entries/delete?uid={_ENTRY_UID}", headers=_csrf(harness.client)
        )

        assert response.status_code == 200
        assert response.json() == {"uid": _ENTRY_UID, "deleted": True}
        harness.entries.delete_entry.assert_awaited_once_with(_ENTRY_UID, _USER_UID)


class TestGrounding:
    def test_remove_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/user-entries/grounding/remove?uid={_ENTRY_UID}&ku_uid={_KU_UID}",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        assert response.json()["removed"] is True
        assert harness.grounding is not None
        harness.grounding.remove.assert_awaited_once_with(_ENTRY_UID, _KU_UID, _USER_UID)

    def test_absent_edge_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        assert harness.grounding is not None
        harness.grounding.remove.return_value = Result.ok(False)

        response = harness.client.post(
            f"/api/user-entries/grounding/remove?uid={_ENTRY_UID}&ku_uid={_KU_UID}",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 404
