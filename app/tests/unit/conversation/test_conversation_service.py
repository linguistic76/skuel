"""
ConversationService unit tests — owner-private discussion store (ADR-078).

Covers: props→model conversion for sessions/turns, the not-found mapping on a
non-owner (backend None → 404-not-403), id minting + kind pass-through, and the
revisit-list / delete report semantics. Backend is mocked (unit tier;
the owner-visibility + delete-completeness behaviours are integration guards 1/2
against a live Docker Neo4j).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.models.conversation import CONVERSATION_KIND_DISCUSSION, ConversationSession
from core.services.conversation import ConversationService
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _session_row(session_id: str = "cs_abc123abc123", user_uid: str = "user_mike") -> dict:
    now = datetime.now(UTC)
    return {
        "session_id": session_id,
        "user_uid": user_uid,
        "kind": CONVERSATION_KIND_DISCUSSION,
        "started_at": now,
        "last_activity": now,
        "title": "On the nature of practice",
        "source_selection": '{"canon": [], "vault": false}',
        "model": "gpt-4o",
    }


def _turn_row(turn_number: int = 1, role: str = "user") -> dict:
    return {
        "turn_id": f"ct_00000000000{turn_number}",
        "session_id": "cs_abc123abc123",
        "role": role,
        "content": "What does the canon say about deliberate practice?",
        "timestamp": datetime.now(UTC),
        "turn_number": turn_number,
    }


def _backend(**overrides) -> SimpleNamespace:
    backend = SimpleNamespace(
        create_session=AsyncMock(return_value=Result.ok(_session_row())),
        append_exchange=AsyncMock(
            return_value=Result.ok([_turn_row(1, "user"), _turn_row(2, "assistant")])
        ),
        save_transcript=AsyncMock(return_value=Result.ok(_session_row())),
        update_session_meta=AsyncMock(return_value=Result.ok(True)),
        get_session=AsyncMock(return_value=Result.ok(_session_row())),
        list_sessions=AsyncMock(return_value=Result.ok([_session_row()])),
        get_turns=AsyncMock(return_value=Result.ok([_turn_row(1), _turn_row(2, "assistant")])),
        delete_session=AsyncMock(return_value=Result.ok(True)),
    )
    for key, value in overrides.items():
        setattr(backend, key, value)
    return backend


class TestCreateSession:
    async def test_mints_id_and_returns_frozen_model(self) -> None:
        backend = _backend()
        service = ConversationService(backend)

        result = await service.create_session(
            "user_mike", CONVERSATION_KIND_DISCUSSION, "On practice", "{}", "gpt-4o"
        )

        assert result.is_ok
        session = result.value
        assert isinstance(session, ConversationSession)
        assert session.user_uid == "user_mike"
        assert session.kind == CONVERSATION_KIND_DISCUSSION
        # The service mints the id and passes it to the backend (cs_ prefix).
        minted_id = backend.create_session.await_args.args[0]
        assert minted_id.startswith("cs_")

    async def test_unknown_owner_yields_not_found(self) -> None:
        backend = _backend(create_session=AsyncMock(return_value=Result.ok(None)))
        service = ConversationService(backend)

        result = await service.create_session("user_ghost", "discussion", "t", "{}", "gpt-4o")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND


class TestAppendExchange:
    async def test_returns_turn_pair_on_success(self) -> None:
        service = ConversationService(_backend())

        result = await service.append_exchange(
            "cs_abc123abc123", "user_mike", "my question", "the reply"
        )

        assert result.is_ok
        user_turn, assistant_turn = result.value
        assert (user_turn.turn_number, user_turn.role) == (1, "user")
        assert (assistant_turn.turn_number, assistant_turn.role) == (2, "assistant")

    async def test_non_owner_session_is_not_found_not_forbidden(self) -> None:
        # Backend returns None when the session is absent OR not owned — the
        # service must surface 404, never 403 (SKUEL ownership convention).
        backend = _backend(append_exchange=AsyncMock(return_value=Result.ok(None)))
        service = ConversationService(backend)

        result = await service.append_exchange("cs_someoneelse", "user_mike", "hi", "reply")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND


class TestSaveTranscript:
    async def test_delegates_one_atomic_write_with_ordered_turns(self) -> None:
        # Save promotes the whole transcript in ONE backend transaction — NOT
        # create_session + a loop of appends (Codex #638 P2). The service mints
        # the session id + every turn's id/ordinal and hands them over as a batch.
        backend = _backend()
        service = ConversationService(backend)

        result = await service.save_transcript(
            "user_mike",
            CONVERSATION_KIND_DISCUSSION,
            "Saved chat",
            "{}",
            "gpt-4o",
            [("u1", "a1"), ("u2", "a2")],
        )

        assert result.is_ok
        assert isinstance(result.value, ConversationSession)
        backend.save_transcript.assert_awaited_once()
        # No create-then-append path — that would expose a partial session.
        backend.create_session.assert_not_awaited()
        backend.append_exchange.assert_not_awaited()
        # Ordered, id- and ordinal-stamped turn payload: 2 pairs → 4 turns.
        sid, uid, _kind, _title, _sel, _model, turns, _now = backend.save_transcript.await_args.args
        assert sid.startswith("cs_") and uid == "user_mike"
        assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
        assert [t["turn_number"] for t in turns] == [1, 2, 3, 4]
        assert [t["content"] for t in turns] == ["u1", "a1", "u2", "a2"]
        assert all(t["turn_id"].startswith("ct_") for t in turns)

    async def test_empty_transcript_is_validation_error_no_write(self) -> None:
        backend = _backend()
        service = ConversationService(backend)

        result = await service.save_transcript("user_mike", "discussion", "t", "{}", "gpt-4o", [])

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        backend.save_transcript.assert_not_awaited()

    async def test_unknown_owner_yields_not_found(self) -> None:
        backend = _backend(save_transcript=AsyncMock(return_value=Result.ok(None)))
        service = ConversationService(backend)

        result = await service.save_transcript(
            "user_ghost", "discussion", "t", "{}", "gpt-4o", [("u", "a")]
        )

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND

    async def test_backend_failure_propagates(self) -> None:
        backend = _backend(
            save_transcript=AsyncMock(
                return_value=Result.fail(Errors.database("save_transcript", "boom"))
            )
        )
        service = ConversationService(backend)

        result = await service.save_transcript(
            "user_mike", "discussion", "t", "{}", "gpt-4o", [("u", "a")]
        )

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.DATABASE


class TestReadPaths:
    async def test_get_session_returns_none_when_absent(self) -> None:
        backend = _backend(get_session=AsyncMock(return_value=Result.ok(None)))
        service = ConversationService(backend)

        result = await service.get_session("cs_missing", "user_mike")

        assert result.is_ok
        assert result.value is None

    async def test_list_sessions_converts_rows_and_passes_default_limit(self) -> None:
        backend = _backend()
        service = ConversationService(backend)

        result = await service.list_sessions("user_mike")

        assert result.is_ok
        assert all(isinstance(s, ConversationSession) for s in result.value)
        _uid, limit = backend.list_sessions.await_args.args
        assert limit == 50

    async def test_get_turns_orders_and_converts(self) -> None:
        service = ConversationService(_backend())

        result = await service.get_turns("cs_abc123abc123", "user_mike")

        assert result.is_ok
        assert [t.turn_number for t in result.value] == [1, 2]
        assert [t.role for t in result.value] == ["user", "assistant"]

    async def test_get_turns_on_non_owner_is_not_found(self) -> None:
        # None (not empty list) distinguishes not-owned from owned-but-empty.
        backend = _backend(get_turns=AsyncMock(return_value=Result.ok(None)))
        service = ConversationService(backend)

        result = await service.get_turns("cs_someoneelse", "user_mike")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND


class TestUpdateMeta:
    async def test_rename_passes_title_only(self) -> None:
        backend = _backend()
        service = ConversationService(backend)

        result = await service.rename_session("cs_abc123abc123", "user_mike", "New title")

        assert result.is_ok and result.value is True
        # Rename updates title, leaves source_selection (None → coalesce keeps it).
        sid, uid, title, source = backend.update_session_meta.await_args.args
        assert (sid, uid, title, source) == ("cs_abc123abc123", "user_mike", "New title", None)

    async def test_update_source_selection_passes_source_only(self) -> None:
        backend = _backend()
        service = ConversationService(backend)

        result = await service.update_source_selection(
            "cs_abc123abc123", "user_mike", '{"vault": true}'
        )

        assert result.is_ok
        _sid, _uid, title, source, model = backend.update_session_meta.await_args.args
        assert (title, source, model) == (None, '{"vault": true}', None)

    async def test_update_source_selection_co_persists_model(self) -> None:
        # A session-backed follow-up co-persists the per-conversation model so a
        # mid-thread switch survives a later continue (last-write-wins).
        backend = _backend()
        service = ConversationService(backend)

        result = await service.update_source_selection(
            "cs_abc123abc123", "user_mike", '{"vault": true}', model="claude-sonnet-4-6"
        )

        assert result.is_ok
        _sid, _uid, title, source, model = backend.update_session_meta.await_args.args
        assert (title, source, model) == (None, '{"vault": true}', "claude-sonnet-4-6")


class TestDelete:
    async def test_reports_whether_a_session_was_deleted(self) -> None:
        assert (await ConversationService(_backend()).delete_session("cs_x", "user_mike")).value

        backend = _backend(delete_session=AsyncMock(return_value=Result.ok(False)))
        result = await ConversationService(backend).delete_session("cs_nope", "user_mike")
        assert result.value is False
