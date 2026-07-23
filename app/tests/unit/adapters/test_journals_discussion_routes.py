"""Discussion revisit/continue/delete/export/rename routes (ADR-078, PR3).

Covers the owner-private discussion-management routes: continue rehydrates the
workspace from stored turns (and 404s a non-owner), delete removes the session,
export streams a markdown transcript, and rename re-renders the revisit-list row.
Harness mirrors ``test_journals_session_persistence.py`` — real ``fast_app`` + CSRF.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.journals_routes import create_journals_routes
from core.models.conversation import ConversationSession, ConversationTurn
from core.utils.result_simplified import Result

_USER_UID = "user_test"
_SID = "cs_abc123abc123"


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_and_csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "adapters.inbound.journals_routes.require_authenticated_user",
        _fake_require_authenticated_user,
    )
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _session(source_selection: str = "{}", model: str = "gpt-4o") -> ConversationSession:
    now = datetime.now(UTC)
    return ConversationSession(
        session_id=_SID,
        user_uid=_USER_UID,
        kind="discussion",
        started_at=now,
        last_activity=now,
        title="On deliberate practice",
        source_selection=source_selection,
        model=model,
    )


def _turn(n: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(
        turn_id=f"ct_00000000000{n}",
        session_id=_SID,
        role=role,
        content=content,
        timestamp=datetime.now(UTC),
        turn_number=n,
    )


def _client(**conv_overrides: object) -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    conv = MagicMock()
    conv.get_session = AsyncMock(return_value=Result.ok(_session()))
    conv.get_turns = AsyncMock(
        return_value=Result.ok([_turn(1, "user", "opening q"), _turn(2, "assistant", "a reply")])
    )
    conv.list_sessions = AsyncMock(return_value=Result.ok([_session()]))
    conv.delete_session = AsyncMock(return_value=Result.ok(True))
    conv.rename_session = AsyncMock(return_value=Result.ok(True))
    for key, value in conv_overrides.items():
        setattr(conv, key, value)

    user = MagicMock()
    user.journal_tier.is_founder = MagicMock(return_value=False)
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))

    services = MagicMock()
    services.user = user_service
    services.journal = MagicMock()
    services.conversation = conv
    create_journals_routes(app, rt, services)
    return TestClient(app), conv


def _post(client: TestClient, path: str, data: dict[str, str] | None = None) -> httpx2.Response:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data=data or {}, headers={CSRF_HEADER_NAME: token})


class TestContinue:
    def test_continue_rehydrates_workspace_from_turns(self) -> None:
        client, conv = _client()

        response = client.get(f"/journals/discussion/{_SID}", headers={"HX-Request": "true"})

        assert response.status_code == 200
        conv.get_session.assert_awaited_once_with(_SID, _USER_UID)
        conv.get_turns.assert_awaited_once_with(_SID, _USER_UID)
        body = response.text
        assert "opening q" in body and "a reply" in body
        # Composer is bound to the session (no client accumulator).
        assert f'value="{_SID}"' in body and 'name="session_id"' in body

    def test_continue_non_owner_is_404(self) -> None:
        client, _conv = _client(get_session=AsyncMock(return_value=Result.ok(None)))

        response = client.get(f"/journals/discussion/{_SID}", headers={"HX-Request": "true"})

        assert response.status_code == 404


class TestDelete:
    def test_delete_removes_session_and_returns_empty(self) -> None:
        client, conv = _client()

        response = _post(client, f"/journals/discussion/{_SID}/delete")

        assert response.status_code == 200
        assert response.text == ""
        conv.delete_session.assert_awaited_once_with(_SID, _USER_UID)


class TestExport:
    def test_export_streams_markdown_transcript(self) -> None:
        client, _conv = _client()

        response = client.get(f"/journals/discussion/{_SID}/export")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "attachment" in response.headers["content-disposition"]
        assert ".md" in response.headers["content-disposition"]
        body = response.text
        assert "# On deliberate practice" in body
        assert "## You" in body and "opening q" in body
        assert "## Journal" in body and "a reply" in body

    def test_export_non_owner_is_404(self) -> None:
        client, _conv = _client(get_session=AsyncMock(return_value=Result.ok(None)))

        response = client.get(f"/journals/discussion/{_SID}/export")

        assert response.status_code == 404


class TestRename:
    def test_rename_persists_and_rerenders_row(self) -> None:
        client, conv = _client()

        response = _post(client, f"/journals/discussion/{_SID}/rename", {"title": "New name"})

        assert response.status_code == 200
        conv.rename_session.assert_awaited_once_with(_SID, _USER_UID, "New name")
        # The re-rendered row links back to continue.
        assert f"/journals/discussion/{_SID}" in response.text

    def test_rename_non_owner_is_404(self) -> None:
        client, _conv = _client(rename_session=AsyncMock(return_value=Result.ok(False)))

        response = _post(client, f"/journals/discussion/{_SID}/rename", {"title": "hijack"})

        assert response.status_code == 404
