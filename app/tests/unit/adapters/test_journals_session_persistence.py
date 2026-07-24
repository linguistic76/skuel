"""Opt-in discussion persistence on the typed door (ADR-078 §5, P3).

Covers the ephemeral-by-default `/journals/start`, the explicit `/journals/save`
gesture, and the `session_id`-branch of `/journals/follow-up`:

- start persists NOTHING — it returns an ephemeral composer carrying the
  ``transcript_json`` accumulator + a *Save this chat* button (no auto-save);
- save folds the ephemeral transcript into an owner-private session (create +
  turn pairs) and swaps the composer to its session-backed shape;
- a session-backed follow-up (a saved chat) reads prior turns from Neo4j,
  appends the new pair, and returns bubbles WITHOUT the OOB accumulator inputs;
- a non-owner / missing session (get_turns → not-found) is refused as 404-not-403
  and writes nothing.

Harness mirrors ``test_journals_follow_up_gate.py`` — real ``fast_app`` + CSRF.
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
from adapters.inbound.rate_limit import reset_buckets_for_testing
from core.models.conversation import ConversationSession, ConversationTurn
from core.services.journal.journal_service import JournalFollowUp
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_test"


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_and_csrf_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "adapters.inbound.journals_routes.require_authenticated_user",
        _fake_require_authenticated_user,
    )
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
    # The journals AI gate records daily-quota units per request — clean
    # buckets so tests never accumulate against the shared _USER_UID.
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


def _session(session_id: str = "cs_abc123abc123", model: str = "gpt-4o") -> ConversationSession:
    now = datetime.now(UTC)
    return ConversationSession(
        session_id=session_id,
        user_uid=_USER_UID,
        kind="discussion",
        started_at=now,
        last_activity=now,
        title="t",
        source_selection="{}",
        model=model,
    )


def _turn(turn_number: int, role: str, content: str) -> ConversationTurn:
    return ConversationTurn(
        turn_id=f"ct_00000000000{turn_number}",
        session_id="cs_abc123abc123",
        role=role,
        content=content,
        timestamp=datetime.now(UTC),
        turn_number=turn_number,
    )


def _conversation(**overrides: object) -> MagicMock:
    conv = MagicMock()
    conv.create_session = AsyncMock(return_value=Result.ok(_session()))
    conv.append_exchange = AsyncMock(
        return_value=Result.ok((_turn(1, "user", "x"), _turn(2, "assistant", "y")))
    )
    conv.get_turns = AsyncMock(
        return_value=Result.ok(
            [_turn(1, "user", "opening"), _turn(2, "assistant", "first response")]
        )
    )
    conv.save_transcript = AsyncMock(return_value=Result.ok(_session()))
    conv.list_sessions = AsyncMock(return_value=Result.ok([_session()]))
    conv.update_source_selection = AsyncMock(return_value=Result.ok(True))
    for key, value in overrides.items():
        setattr(conv, key, value)
    return conv


def _client(conversation: MagicMock) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    journal = MagicMock()
    journal.run_discussion = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="opening reply", sources=()))
    )
    journal.run_follow_up = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="follow-up reply", sources=()))
    )
    user = MagicMock()
    user.journal_tier.is_founder = MagicMock(return_value=False)
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))
    services = MagicMock()
    services.user = user_service
    services.journal = journal
    services.conversation = conversation
    create_journals_routes(app, rt, services)
    return TestClient(app), journal, conversation


def _post(client: TestClient, path: str, data: dict[str, str]) -> httpx2.Response:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data=data, headers={CSRF_HEADER_NAME: token})


class TestStartIsEphemeral:
    def test_start_persists_nothing_and_returns_savable_transcript(self) -> None:
        client, _journal, conv = _client(_conversation())

        response = _post(client, "/journals/start", {"raw_entry": "What's alive today?"})

        assert response.status_code == 200
        # Ephemeral by default (ADR-078 §5): opening a chat writes NOTHING.
        conv.create_session.assert_not_awaited()
        conv.append_exchange.assert_not_awaited()
        conv.save_transcript.assert_not_awaited()
        # The composer carries the structured transcript accumulator + Save, not a
        # session id and not the flat original_entry accumulator.
        body = response.text
        assert 'name="transcript_json"' in body
        assert "Save this chat" in body
        assert 'name="session_id"' not in body
        assert "What's alive today?" in body  # user turn is in the transcript


class TestSaveOptIn:
    def test_save_folds_transcript_and_swaps_to_session_composer(self) -> None:
        import json

        client, _journal, conv = _client(_conversation())
        transcript = json.dumps(
            [
                {"role": "user", "content": "Opening thought."},
                {"role": "assistant", "content": "A reply."},
                {"role": "user", "content": "Follow up."},
                {"role": "assistant", "content": "Another reply."},
            ]
        )

        response = _post(
            client, "/journals/save", {"transcript_json": transcript, "title": "My chat"}
        )

        assert response.status_code == 200
        conv.save_transcript.assert_awaited_once()
        _uid, _kind, title, _sel, _model, pairs = conv.save_transcript.await_args.args
        assert title == "My chat"
        assert pairs == [
            ("Opening thought.", "A reply."),
            ("Follow up.", "Another reply."),
        ]
        # The composer is swapped to its session-backed ("Saved ✓") shape.
        body = response.text
        assert 'name="session_id"' in body
        assert "Saved" in body

    def test_save_empty_transcript_writes_nothing_and_spares_composer(self) -> None:
        client, _journal, conv = _client(_conversation())

        response = _post(client, "/journals/save", {"transcript_json": "", "title": "x"})

        assert response.status_code == 200
        conv.save_transcript.assert_not_awaited()
        # The error is retargeted to the thread so the Save button's
        # #journal-composer/outerHTML swap can't destroy the composer.
        assert response.headers["HX-Retarget"] == "#journal-thread"
        assert response.headers["HX-Reswap"] == "beforeend"


class TestSessionFollowUp:
    def test_session_follow_up_reads_and_appends_without_oob(self) -> None:
        client, journal, conv = _client(_conversation())

        response = _post(
            client,
            "/journals/follow-up",
            {"user_reply": "tell me more", "session_id": "cs_abc123abc123"},
        )

        assert response.status_code == 200
        # Prior turns read from Neo4j (owner-scoped), context rebuilt from them.
        conv.get_turns.assert_awaited_once_with("cs_abc123abc123", _USER_UID)
        journal.run_follow_up.assert_awaited_once()
        kwargs = journal.run_follow_up.await_args.kwargs
        assert "first response" in kwargs["ai_response"]
        assert "opening" in kwargs["original_entry"]
        # New user + assistant turns appended atomically (one exchange).
        conv.append_exchange.assert_awaited_once()
        # Session-backed fragment carries NO OOB accumulator swap.
        assert "hx-swap-oob" not in response.text.lower()
        assert "journal-original-entry" not in response.text

    def test_ungrounded_follow_up_preserves_the_book_scope(self) -> None:
        # Codex #635 P2: a follow-up with canon OFF must record canon_on=false
        # WITHOUT erasing the session's book scope carried in the hidden field.
        import json

        client, _journal, conv = _client(_conversation())

        _post(
            client,
            "/journals/follow-up",
            {
                "user_reply": "just thinking",
                "session_id": "cs_abc123abc123",
                "canon_book_uids": "res_a,res_b",  # session scope, dial off
            },
        )

        conv.update_source_selection.assert_awaited_once()
        _sid, _uid, stored = conv.update_source_selection.await_args.args
        selection = json.loads(stored)
        assert selection["canon"] == ["res_a", "res_b"]  # scope preserved
        assert selection["canon_on"] is False  # dial off recorded

    def test_non_owner_session_is_refused_and_writes_nothing(self) -> None:
        conv = _conversation(
            get_turns=AsyncMock(
                return_value=Result.fail(Errors.not_found("ConversationSession", "cs_x"))
            )
        )
        client, journal, _conv = _client(conv)

        response = _post(
            client,
            "/journals/follow-up",
            {"user_reply": "sneak in", "session_id": "cs_not_mine"},
        )

        assert response.status_code == 200  # inline error fragment (404-not-403 semantics)
        assert "could not be found" in response.text.lower()
        journal.run_follow_up.assert_not_awaited()
        conv.append_exchange.assert_not_awaited()
