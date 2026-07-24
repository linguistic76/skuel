"""Route tests for the Journals persistence contract (ADR-073 + ADR-078).

The understanding wall (ADR-073 §2): the journal paths run their AI work and
return results *inline* / to the user's own `je_out/` folder — they write
**nothing** to the understanding channel (`user_entry_service`), across STANDARD
and FOUNDER tiers. That invariant is unchanged.

ADR-078 (as amended 2026-07-13) narrows ADR-073's "zero persistence" for
discussions only, and persistence is **opt-in**: a discussion is ephemeral by
default and reaches the owner-private `:ConversationSession` store ONLY through
an explicit `POST /journals/save` (the *Save this chat* gesture). The typed
`POST /journals/start` door persists **nothing** — it returns an ephemeral,
client-side transcript (this reverts P2's create-on-first-reply auto-save;
guard 7, ADR-078 §7). So a save persists to `conversation_service` (never to
`user_entry_service`); opening or continuing a chat without saving persists
nothing anywhere.

No Neo4j required: services are mocked and only the handler logic is exercised.
Mirrors the harness in `test_today_routes.py`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException

from core.utils.result_simplified import Errors, Result


@pytest.fixture(autouse=True)
def _disable_csrf_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the ``@csrf_protected`` wrapper fall through to the handler."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Clear the module-global rate-limit buckets so per-user counts don't leak
    across tests (many handlers here share ``@rate_limited`` on ``user_mike``)."""
    from adapters.inbound.rate_limit import reset_buckets_for_testing

    reset_buckets_for_testing()


def _make_request(
    user_uid: str | None = "user_mike",
    form: dict[str, str] | None = None,
    form_items: list[tuple[str, str]] | None = None,
) -> Any:
    """Build a POST request whose ``form()`` yields a starlette FormData.

    The journal-start handler reads multi-valued fields via ``form.getlist``
    (canon-shelf checkboxes), so a plain dict won't do — FormData carries both
    ``.get`` and ``.getlist``. ``form_items`` lets a test supply repeated keys
    (e.g. several ``canon_book_uids``); ``form`` is the single-value shorthand.
    """
    from starlette.datastructures import FormData

    session = {"user_uid": user_uid} if user_uid is not None else {}
    items = form_items if form_items is not None else list((form or {}).items())
    form_data = FormData(items)

    async def _form() -> FormData:
        return form_data

    return SimpleNamespace(
        method="POST",
        session=session,
        url=SimpleNamespace(path="/journals/start"),
        query_params={},
        form=_form,
        cookies={},
        headers={},
    )


def _make_user(is_founder: bool, role: Any = None) -> Any:
    from core.models.enums.user_enums import UserRole

    user = MagicMock()
    user.journal_tier.is_founder.return_value = is_founder
    # Real role so the per-user AI tier gate resolves for real (MEMBER = AI on).
    user.role = role if role is not None else UserRole.MEMBER
    return user


@pytest.fixture
def mock_services() -> Any:
    from core.config.intelligence_tier import IntelligenceTier

    services = MagicMock()

    # Real system tier so the per-user AI gate evaluates for real (not a
    # truthy MagicMock): FULL system + MEMBER user (fixture default) = AI on.
    services.intelligence_tier = IntelligenceTier.FULL

    services.user = MagicMock()
    services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=False)))

    from core.services.journal.journal_service import JournalFollowUp

    services.journal = MagicMock()
    services.journal.run_discussion = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="A discussion response.", sources=()))
    )
    services.journal.run_follow_up = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="A follow-up response.", sources=()))
    )
    services.journal.run_stage1 = AsyncMock(return_value=Result.ok("A scribe record."))
    services.journal.run_compiled = AsyncMock(return_value=Result.ok("# Compiled output"))
    services.journal.suggestions_available = True
    services.journal.active_goal_titles = AsyncMock(return_value=Result.ok([]))
    services.journal.suggest_activities = AsyncMock(return_value=Result.ok([]))

    # Persistence surface — every one of these must stay un-awaited on the
    # zero-persistence journal paths (ADR-073).
    services.user_entry = MagicMock()
    services.user_entry.create_entry = AsyncMock(
        return_value=Result.ok((MagicMock(uid="ue_x"), None))
    )
    services.user_entry.update_processed_content = AsyncMock(return_value=Result.ok(True))
    services.user_entry.submit_file = AsyncMock(
        return_value=Result.ok((MagicMock(uid="ue_x"), None))
    )
    services.user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))

    services.batch_transcription = None
    services.user_entry_processor = None

    # ADR-078 discussion store — a successful /journals/start persists an
    # owner-private session + opening turn pair here (never to user_entry).
    from datetime import UTC, datetime

    from core.models.conversation import ConversationSession, ConversationTurn

    _now = datetime.now(UTC)
    services.conversation = MagicMock()
    services.conversation.create_session = AsyncMock(
        return_value=Result.ok(
            ConversationSession(
                session_id="cs_abc123abc123",
                user_uid="user_mike",
                kind="discussion",
                started_at=_now,
                last_activity=_now,
                title="t",
                source_selection="{}",
                model="gpt-4o",
            )
        )
    )
    _pair = (
        ConversationTurn(
            turn_id="ct_000000000001",
            session_id="cs_abc123abc123",
            role="user",
            content="x",
            timestamp=_now,
            turn_number=1,
        ),
        ConversationTurn(
            turn_id="ct_000000000002",
            session_id="cs_abc123abc123",
            role="assistant",
            content="y",
            timestamp=_now,
            turn_number=2,
        ),
    )
    services.conversation.append_exchange = AsyncMock(return_value=Result.ok(_pair))
    services.conversation.get_turns = AsyncMock(return_value=Result.ok([]))
    # Save this chat (ADR-078 §5) — the only path into the store.
    _saved_session = ConversationSession(
        session_id="cs_saved0000001",
        user_uid="user_mike",
        kind="discussion",
        started_at=_now,
        last_activity=_now,
        title="Saved chat",
        source_selection="{}",
        model="gpt-4o",
    )
    services.conversation.save_transcript = AsyncMock(return_value=Result.ok(_saved_session))
    services.conversation.list_sessions = AsyncMock(return_value=Result.ok([_saved_session]))
    return services


@pytest.fixture
def handlers(mock_services: Any, tmp_path: Any) -> dict[str, Any]:
    """Register the journals routes and return path → handler.

    Wires a REAL ``JournalBatchService`` (je_* folders under ``tmp_path``) so
    the batch pipeline is exercised for real while the surrounding services
    stay mocked.
    """
    return _register(mock_services, vault_root=tmp_path)


def _assert_understanding_channel_untouched(services: Any) -> None:
    """The ADR-073/078 §2 wall: journal paths never write to user_entry.

    Unchanged by ADR-078 — discussion storage is a separate, understanding-
    agnostic channel (``conversation``); the understanding channel stays silent.
    """
    services.user_entry.create_entry.assert_not_awaited()
    services.user_entry.update_processed_content.assert_not_awaited()
    services.user_entry.submit_file.assert_not_awaited()


def _assert_no_discussion_persisted(services: Any) -> None:
    """No write to the store — the ADR-078 §7 guard-7 (opt-in) shape at the route.

    Opening or continuing a chat never touches the store; only an explicit
    ``/journals/save`` does. A create/append/save on any of these paths is the
    P2 auto-save regression this arc reverts.
    """
    services.conversation.create_session.assert_not_awaited()
    services.conversation.append_exchange.assert_not_awaited()
    services.conversation.save_transcript.assert_not_awaited()


def _make_upload_request(form_items: list[tuple[str, Any]], user_uid: str = "user_mike") -> Any:
    """Build a POST request whose ``form()`` yields a starlette FormData.

    Upload handlers use ``form.getlist("file")`` + ``UploadFile`` filtering, so a
    plain dict won't do — FormData carries the real multipart shape.
    """
    from starlette.datastructures import FormData

    form_data = FormData(form_items)

    async def _form() -> FormData:
        return form_data

    return SimpleNamespace(
        method="POST",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path="/journals/upload"),
        query_params={},
        form=_form,
        cookies={},
        headers={},
    )


def _text_upload(filename: str, content: bytes) -> Any:
    """A starlette UploadFile backed by an in-memory buffer."""
    import io

    from starlette.datastructures import UploadFile

    return UploadFile(file=io.BytesIO(content), filename=filename)


def _register(services: Any, vault_root: Any = None, llm_caller: Any = None) -> dict[str, Any]:
    """Register journals routes against ``services`` → path → handler.

    Used by tests that customise a service the route closure captures at
    registration time (e.g. ``batch_transcription``), which the module-level
    ``handlers`` fixture can't do after the fact. Builds a real
    ``JournalBatchService`` from the CURRENT ``services`` mocks — je_* staging
    folders resolve under ``vault_root``, the LLM caller is injected directly
    (``None`` = CORE-tier degradation).
    """
    from adapters.inbound.journals_routes import create_journals_routes
    from core.services.journal import JournalBatchService

    services.journal_batch = JournalBatchService(
        batch_transcription_service=services.batch_transcription,
        llm_caller=llm_caller,
        journal_service=services.journal,
        vault_root=vault_root,
    )

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_journals_routes(MagicMock(), rt_collector, services)
    return registered


class TestJournalsStartZeroPersistence:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/journals/start"](request=request)
        assert exc.value.status_code == 401

    async def test_standard_opens_discussion_is_ephemeral_not_persisted(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"raw_entry": "What's on my mind today."})
        response = await handlers["/journals/start"](request=request)

        # Typed text opens a discussion (both tiers), not the DNWF staging.
        mock_services.journal.run_discussion.assert_awaited_once()
        mock_services.journal.run_stage1.assert_not_awaited()
        # A STANDARD user can't summon canon/vault — gated off server-side.
        _, kwargs = mock_services.journal.run_discussion.call_args
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is False
        # Inline swap retargeted to the workspace — no redirect.
        assert response.status_code == 200
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        assert response.headers["HX-Reswap"] == "outerHTML"
        # ADR-078 §5: ephemeral by default — opening a chat persists NOTHING (the
        # transcript rides the response client-side until *Save this chat*).
        _assert_no_discussion_persisted(mock_services)
        _assert_understanding_channel_untouched(mock_services)
        # The opening transcript rides the composer as structured JSON (carrying
        # both the user turn and the assistant reply), with the Save affordance.
        html = response.body.decode()
        assert 'name="transcript_json"' in html
        assert "on my mind today" in html  # user turn is in the transcript
        assert "A discussion response." in html  # assistant turn too
        assert "Save this chat" in html

    async def test_founder_opens_discussion_not_dnwf_staging(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # Typed FOUNDER text opens a discussion too (ruling: typed = discussion);
        # the Scribe staging lives on the file/audio door, never here.
        mock_services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=True)))
        request = _make_request(form={"raw_entry": "Founder brainstorm."})
        response = await handlers["/journals/start"](request=request)

        mock_services.journal.run_discussion.assert_awaited_once()
        mock_services.journal.run_stage1.assert_not_awaited()
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        # Ephemeral by default — even for FOUNDERs, opening persists nothing.
        _assert_no_discussion_persisted(mock_services)
        _assert_understanding_channel_untouched(mock_services)

    async def test_founder_shelf_selection_scopes_canon(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # Checked shelf books → summon_canon on, scoped to those resource_uids;
        # the vault toggle rides its own flag. Any book checked means summon.
        mock_services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=True)))
        request = _make_request(
            form_items=[
                ("raw_entry", "Ground me in the shelf."),
                ("canon_book_uids", "res_a"),
                ("canon_book_uids", "res_b"),
                ("summon_vault", "true"),
            ]
        )
        await handlers["/journals/start"](request=request)

        _, kwargs = mock_services.journal.run_discussion.call_args
        assert kwargs["summon_canon"] is True
        assert kwargs["summon_vault"] is True
        assert kwargs["canon_book_uids"] == ["res_a", "res_b"]

    async def test_standard_forged_source_flags_are_ignored(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # A non-FOUNDER can forge the POST flags; the route must drop them.
        request = _make_request(
            form_items=[
                ("raw_entry", "Trying to summon."),
                ("canon_book_uids", "res_a"),
                ("summon_vault", "true"),
            ]
        )
        await handlers["/journals/start"](request=request)

        _, kwargs = mock_services.journal.run_discussion.call_args
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is False
        assert kwargs["canon_book_uids"] is None

    async def test_empty_entry_short_circuits_with_no_ai_and_no_persistence(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"raw_entry": "   "})
        await handlers["/journals/start"](request=request)

        mock_services.journal.run_discussion.assert_not_awaited()
        mock_services.journal.run_stage1.assert_not_awaited()
        _assert_no_discussion_persisted(mock_services)
        _assert_understanding_channel_untouched(mock_services)

    async def test_ai_failure_still_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.journal.run_discussion = AsyncMock(
            return_value=Result.fail(Errors.integration("llm", "boom"))
        )
        request = _make_request(form={"raw_entry": "Trigger an AI failure."})
        await handlers["/journals/start"](request=request)

        # A failed discussion leaves no session (persist happens only post-LLM).
        _assert_no_discussion_persisted(mock_services)
        _assert_understanding_channel_untouched(mock_services)


class TestJournalsSaveOptIn:
    """`POST /journals/save` is the ONLY path into the store (ADR-078 §5 opt-in)."""

    async def test_save_persists_folded_pairs_not_understanding(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        import json

        from fasthtml.common import to_xml

        transcript = json.dumps(
            [
                {"role": "user", "content": "Opening thought."},
                {"role": "assistant", "content": "A reply."},
                {"role": "user", "content": "Follow up."},
                {"role": "assistant", "content": "Another reply."},
            ]
        )
        response = await handlers["/journals/save"](
            request=_make_request(form={}),
            transcript_json=transcript,
            title="My chat",
        )

        # Saved via the single store path — the ordered transcript folds into
        # (user, assistant) pairs; no LLM call, no understanding write.
        mock_services.conversation.save_transcript.assert_awaited_once()
        args, _ = mock_services.conversation.save_transcript.call_args
        # positional: (user_uid, kind, title, source_selection, model, pairs)
        assert args[2] == "My chat"
        # No model field posted → the app-safe default is stored on the session.
        assert args[4] == "gpt-4o"
        assert args[5] == [
            ("Opening thought.", "A reply."),
            ("Follow up.", "Another reply."),
        ]
        mock_services.journal.run_discussion.assert_not_awaited()
        _assert_understanding_channel_untouched(mock_services)

        # The composer is swapped for its session-backed shape ("Saved ✓"), and
        # the saved chat is prepended to the revisit list via an OOB swap.
        html = to_xml(response)
        assert 'name="session_id"' in html
        assert "Saved" in html
        assert 'id="journal-discussions-panel"' in html
        assert "hx-swap-oob" in html

    async def test_save_empty_transcript_persists_nothing_and_spares_composer(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # An empty / whitespace transcript has no pairs to save — nothing reaches
        # the store (guard 7: no session is created without real content).
        response = await handlers["/journals/save"](
            request=_make_request(form={}),
            transcript_json="",
            title="x",
        )
        mock_services.conversation.save_transcript.assert_not_awaited()
        _assert_understanding_channel_untouched(mock_services)
        # The error is retargeted to the thread so the Save button's
        # #journal-composer/outerHTML swap can't destroy the composer (Codex #638).
        assert response.headers["HX-Retarget"] == "#journal-thread"
        assert response.headers["HX-Reswap"] == "beforeend"


class TestJournalsUploadZeroPersistence:
    """`POST /journals/upload` compiles to je_out/, never to Neo4j."""

    async def test_single_text_file_writes_je_out_and_persists_nothing(
        self,
        handlers: dict[str, Any],
        mock_services: Any,
        tmp_path: Any,
    ) -> None:
        # FOUNDER instructions_only → run_compiled → je_out/{stem}_out.md.
        # workspace_target=1 marks the /journals landing layout (has a workspace).
        mock_services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=True)))
        request = _make_upload_request(
            [
                ("file", _text_upload("reflection.txt", b"Ship the site by Friday.")),
                ("processing_mode", "instructions_only"),
                ("workspace_target", "1"),
            ]
        )
        response = await handlers["/journals/upload"](request=request)

        mock_services.journal.run_compiled.assert_awaited_once()
        assert (tmp_path / "je_out" / "reflection_out.md").read_text() == "# Compiled output"
        # Result is retargeted to the centre workspace, not the right-panel status.
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        _assert_understanding_channel_untouched(mock_services)
        # ADR-078 P3 PR2: the file door is ephemeral + savable. The composer opens
        # on the source→output pair (the file text as the user turn, the compiled
        # output as the assistant turn) with a Save button — no auto-persist.
        html = response.body.decode()
        assert 'name="transcript_json"' in html
        assert "Ship the site by Friday." in html  # source text = opening user turn
        assert "# Compiled output" in html  # compiled output = opening assistant turn
        assert "Save this chat" in html
        assert 'name="original_entry"' not in html  # flat accumulator is gone
        mock_services.conversation.save_transcript.assert_not_awaited()

    async def test_single_upload_without_workspace_does_not_retarget(
        self,
        handlers: dict[str, Any],
        mock_services: Any,
    ) -> None:
        # The /submissions/journal form omits workspace_target → the result must
        # NOT retarget to a missing #journal-workspace (Codex, #478).
        mock_services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=True)))
        request = _make_upload_request(
            [
                ("file", _text_upload("reflection.txt", b"Ship it.")),
                ("processing_mode", "instructions_only"),
            ]
        )
        response = await handlers["/journals/upload"](request=request)

        # Returned as a bare fragment (FT), not an HX-Retarget HTMLResponse.
        from starlette.responses import HTMLResponse

        assert not isinstance(response, HTMLResponse)
        _assert_understanding_channel_untouched(mock_services)

    async def test_no_file_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_upload_request([("processing_mode", "instructions_only")])
        await handlers["/journals/upload"](request=request)
        _assert_understanding_channel_untouched(mock_services)

    async def test_duplicate_output_stem_batch_is_rejected(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # Two files with the same STEM (note.txt / note.md) map to the same
        # je_out/ output, so the batch is rejected loudly rather than silently
        # dropping one — dedup is by stem, not filename (Kody + Codex, #478).
        request = _make_upload_request(
            [
                ("file", _text_upload("note.txt", b"first")),
                ("file", _text_upload("note.md", b"second")),
                ("processing_mode", "instructions_only"),
            ]
        )
        response = await handlers["/journals/upload"](request=request)

        from fasthtml.common import to_xml

        assert "same je_out/ output" in to_xml(response)
        _assert_understanding_channel_untouched(mock_services)

    async def test_empty_audio_batch_reports_error(self, mock_services: Any, tmp_path: Any) -> None:
        # A "Transcribe only" batch with no supported audio (e.g. a text folder)
        # must not render a false success (Codex, #478). Register handlers with a
        # batch service wired, since the closure captures it at registration.
        empty = SimpleNamespace(total_files=0, succeeded=0, failed=0, skipped=0, results=[])
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(empty)
        )
        registered = _register(mock_services, vault_root=tmp_path)

        request = _make_upload_request(
            [
                ("file", _text_upload("a.mp3", b"x")),
                ("file", _text_upload("b.mp3", b"y")),
                ("processing_mode", "transcribe_only"),
            ]
        )
        response = await registered["/journals/upload"](request=request)

        from fasthtml.common import to_xml

        assert "No supported audio files" in to_xml(response)
        _assert_understanding_channel_untouched(mock_services)

    async def test_single_transcribe_and_instructions_preflights_llm(
        self, mock_services: Any, tmp_path: Any
    ) -> None:
        # STANDARD single audio upload with Deepgram but no LLM must fail BEFORE
        # transcribing, so no Deepgram quota is spent (Codex, #478).
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_one = AsyncMock(
            return_value=Result.ok("transcript")
        )
        registered = _register(mock_services, vault_root=tmp_path, llm_caller=None)  # no LLM

        request = _make_upload_request(
            [
                ("file", _text_upload("memo.mp3", b"audio")),
                ("processing_mode", "transcribe_and_instructions"),
            ]
        )
        response = await registered["/journals/upload"](request=request)

        from fasthtml.common import to_xml

        assert "LLM service not available" in to_xml(response)
        mock_services.batch_transcription.transcribe_one.assert_not_awaited()
        _assert_understanding_channel_untouched(mock_services)

    async def test_structuring_forces_fresh_transcription(
        self, mock_services: Any, tmp_path: Any
    ) -> None:
        # folder-process transcribe_and_instructions must force skip_existing=False
        # even though folder reruns default to True — structured output must match
        # the current audio, never a stale same-stem transcript (Kody, #478).
        je_in = tmp_path / "je_in"
        je_in.mkdir()
        (je_in / "memo.mp3").write_bytes(b"audio")
        (tmp_path / "je_out").mkdir()

        done = SimpleNamespace(
            total_files=1,
            succeeded=1,
            failed=0,
            skipped=0,
            results=[{"name": "memo.mp3", "status": "success"}],
        )
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_batch = AsyncMock(return_value=Result.ok(done))
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("structured"))
        registered = _register(mock_services, vault_root=tmp_path, llm_caller=llm)

        request = _make_upload_request([("processing_mode", "transcribe_and_instructions")])
        await registered["/journals/folder-process"](request=request)

        _, kwargs = mock_services.batch_transcription.transcribe_batch.call_args
        assert kwargs.get("skip_existing") is False
        _assert_understanding_channel_untouched(mock_services)

    async def test_dedup_guard_is_mode_aware(self, mock_services: Any, tmp_path: Any) -> None:
        # Under "Transcribe only", an ignored same-stem text file (meeting.txt)
        # next to meeting.mp3 must NOT trigger the duplicate-output guard — only
        # the mp3 produces je_out output (Codex, #478).
        done = SimpleNamespace(
            total_files=1,
            succeeded=1,
            failed=0,
            skipped=0,
            results=[{"name": "meeting.mp3", "status": "success"}],
        )
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_batch = AsyncMock(return_value=Result.ok(done))
        registered = _register(mock_services, vault_root=tmp_path)

        request = _make_upload_request(
            [
                ("file", _text_upload("meeting.mp3", b"audio")),
                ("file", _text_upload("meeting.txt", b"ignored notes")),
                ("processing_mode", "transcribe_only"),
            ]
        )
        response = await registered["/journals/upload"](request=request)

        from fasthtml.common import to_xml

        # Not rejected: the batch actually ran instead of erroring on a false collision.
        assert "same je_out/ output" not in to_xml(response)
        mock_services.batch_transcription.transcribe_batch.assert_awaited_once()
        # Uploads force fresh transcription — never reuse a stale je_out transcript.
        _, kwargs = mock_services.batch_transcription.transcribe_batch.call_args
        assert kwargs.get("skip_existing") is False
        _assert_understanding_channel_untouched(mock_services)


class TestJournalExemplarLoading:
    """`je_raw`/`je_pro` are read off disk as few-shot exemplars (ADR-073 §4).

    Read-only, in-memory, bounded — never ingested or persisted. Driven on the
    service directly (``JournalBatchService._load_exemplars``) with the je_*
    folders rooted under ``tmp_path``.
    """

    @staticmethod
    def _service(tmp_path: Any, *, make_dirs: bool = True) -> tuple[Any, Any, Any]:
        from core.services.journal import JournalBatchService

        raw = tmp_path / "je_raw"
        pro = tmp_path / "je_pro"
        if make_dirs:
            raw.mkdir()
            pro.mkdir()
        return JournalBatchService(vault_root=tmp_path), raw, pro

    def test_matched_pairs_load_by_stem(self, tmp_path: Any) -> None:
        service, raw, pro = self._service(tmp_path)
        (raw / "example.md").write_text("RAW BODY")
        (pro / "example.md").write_text("PRO BODY")

        pairs = service._load_exemplars()
        assert pairs == [("RAW BODY", "PRO BODY")]

    def test_unmatched_files_are_skipped(self, tmp_path: Any) -> None:
        service, raw, pro = self._service(tmp_path)
        (raw / "lonely.md").write_text("no partner")  # only in je_raw
        (pro / "orphan.md").write_text("no partner")  # only in je_pro

        assert service._load_exemplars() == []

    def test_absent_folders_degrade_to_empty(self, tmp_path: Any) -> None:
        service, _raw, _pro = self._service(tmp_path, make_dirs=False)
        assert service._load_exemplars() == []

    def test_pair_count_is_capped(self, tmp_path: Any) -> None:
        from core.services.journal.journal_batch_service import EXEMPLAR_MAX_PAIRS

        service, raw, pro = self._service(tmp_path)
        for i in range(EXEMPLAR_MAX_PAIRS + 2):
            (raw / f"e{i}.md").write_text(f"raw {i}")
            (pro / f"e{i}.md").write_text(f"pro {i}")

        assert len(service._load_exemplars()) == EXEMPLAR_MAX_PAIRS

    def test_each_side_is_truncated(self, tmp_path: Any) -> None:
        from core.services.journal.journal_batch_service import EXEMPLAR_MAX_CHARS

        service, raw, pro = self._service(tmp_path)
        (raw / "big.md").write_text("R" * (EXEMPLAR_MAX_CHARS + 500))
        (pro / "big.md").write_text("P" * (EXEMPLAR_MAX_CHARS + 500))

        (raw_body, pro_body) = service._load_exemplars()[0]
        assert len(raw_body) == EXEMPLAR_MAX_CHARS
        assert len(pro_body) == EXEMPLAR_MAX_CHARS

    def test_undecodable_exemplar_is_skipped_not_raised(self, tmp_path: Any) -> None:
        # A non-UTF-8 exemplar must be skipped, never raise out of the helper
        # (UnicodeDecodeError is a UnicodeError, not an OSError). Kody #480.
        service, raw, pro = self._service(tmp_path)
        (raw / "bad.md").write_bytes(b"\xff\xfe not valid utf-8")
        (pro / "bad.md").write_text("valid partner")

        assert service._load_exemplars() == []  # skipped cleanly, no exception

    def test_preamble_empty_when_no_pairs(self) -> None:
        from core.services.journal.journal_batch_service import _build_exemplar_preamble

        assert _build_exemplar_preamble([]) == ""

    def test_understanding_only_je_pro_file_never_used_as_exemplar(self, tmp_path: Any) -> None:
        # ADR-073 amendment: `je_use: understanding` scopes the file to the
        # ingestion channel only — the loader must skip it even with a raw twin.
        service, raw, pro = self._service(tmp_path)
        (raw / "private.md").write_text("RAW BODY")
        (pro / "private.md").write_text(
            "---\npipeline: knowledge\nje_use: understanding\n---\nABOUT ME"
        )

        assert service._load_exemplars() == []

    def test_garbled_je_use_skips_exemplar_use(self, tmp_path: Any) -> None:
        # Unrecognized je_use is honored in neither direction (fail-closed
        # both ways — the ingestion gate skips it too).
        service, raw, pro = self._service(tmp_path)
        (raw / "typo.md").write_text("RAW BODY")
        (pro / "typo.md").write_text("---\nje_use: exmplar\n---\nSTYLED")

        assert service._load_exemplars() == []

    def test_frontmatter_stripped_from_exemplar_text(self, tmp_path: Any) -> None:
        # A consented je_pro file carries YAML frontmatter — consent metadata,
        # not style. It must never reach the LLM as exemplar text.
        service, raw, pro = self._service(tmp_path)
        (raw / "pair.md").write_text("RAW BODY")
        (pro / "pair.md").write_text(
            "---\ntype: user_entry\npipeline: knowledge\nje_use: both\n---\nSTYLED BODY"
        )

        pairs = service._load_exemplars()
        assert pairs == [("RAW BODY", "STYLED BODY")]

    def test_unterminated_frontmatter_fails_closed(self, tmp_path: Any) -> None:
        # Codex #608: an opening fence whose close falls OUTSIDE the bounded
        # read must skip the file — parsing the truncated text would default
        # je_use to BOTH and inject raw YAML into the prompt as style.
        from core.services.journal.journal_batch_service import (
            EXEMPLAR_FRONTMATTER_HEADROOM,
            EXEMPLAR_MAX_CHARS,
        )

        service, raw, pro = self._service(tmp_path)
        (raw / "big.md").write_text("RAW BODY")
        oversized = "---\nje_use: understanding\npad: " + "z" * (
            EXEMPLAR_MAX_CHARS + EXEMPLAR_FRONTMATTER_HEADROOM
        )
        (pro / "big.md").write_text(oversized + "\n---\nSTYLED")

        assert service._load_exemplars() == []

    def test_frontmatter_headroom_preserves_content_budget(self, tmp_path: Any) -> None:
        # The frontmatter block must not eat into the exemplar's char budget.
        from core.services.journal.journal_batch_service import EXEMPLAR_MAX_CHARS

        service, raw, pro = self._service(tmp_path)
        (raw / "big.md").write_text("R" * (EXEMPLAR_MAX_CHARS + 500))
        (pro / "big.md").write_text(
            "---\npipeline: knowledge\n---\n" + "P" * (EXEMPLAR_MAX_CHARS + 500)
        )

        (raw_body, pro_body) = service._load_exemplars()[0]
        assert len(raw_body) == EXEMPLAR_MAX_CHARS
        assert len(pro_body) == EXEMPLAR_MAX_CHARS
        assert pro_body == "P" * EXEMPLAR_MAX_CHARS


class TestJournalExemplarInjection:
    """Exemplars reach the LLM prompt and still persist nothing."""

    async def test_exemplars_injected_into_prompt_and_persist_nothing(
        self, mock_services: Any, tmp_path: Any
    ) -> None:
        # STANDARD single upload (instructions_only) routes through the service's
        # LLM path, which injects the je_raw/je_pro pair.
        raw = tmp_path / "je_raw"
        pro = tmp_path / "je_pro"
        raw.mkdir()
        pro.mkdir()
        (raw / "sample.md").write_text("RAW_EXEMPLAR_MARKER")
        (pro / "sample.md").write_text("PRO_EXEMPLAR_MARKER")

        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("processed"))
        # STANDARD user (default fixture)
        registered = _register(mock_services, vault_root=tmp_path, llm_caller=llm)

        request = _make_upload_request(
            [
                ("file", _text_upload("today.txt", b"My rough notes.")),
                ("processing_mode", "instructions_only"),
            ]
        )
        await registered["/journals/upload"](request=request)

        llm.generate.assert_awaited_once()
        _, kwargs = llm.generate.call_args
        prompt = kwargs["prompt"]
        assert "RAW_EXEMPLAR_MARKER" in prompt
        assert "PRO_EXEMPLAR_MARKER" in prompt
        assert "My rough notes." in prompt
        _assert_understanding_channel_untouched(mock_services)

    async def test_no_exemplars_leaves_prompt_clean(
        self, mock_services: Any, tmp_path: Any
    ) -> None:
        # Absent je_raw/je_pro → prompt is just the user's text (today's behavior).
        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("processed"))
        registered = _register(mock_services, vault_root=tmp_path, llm_caller=llm)

        request = _make_upload_request(
            [
                ("file", _text_upload("today.txt", b"My rough notes.")),
                ("processing_mode", "instructions_only"),
            ]
        )
        await registered["/journals/upload"](request=request)

        _, kwargs = llm.generate.call_args
        # No exemplar block header injected when the folders are absent.
        assert "— raw input" not in kwargs["prompt"]
        _assert_understanding_channel_untouched(mock_services)


class TestSuggestActivitiesZeroPersistence:
    """`POST /journals/suggest-activities` takes content in the body, stores nothing."""

    async def test_content_body_runs_bridge_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"content": "Ship the site by Friday."})
        await handlers["/journals/suggest-activities"](request=request)

        mock_services.journal.suggest_activities.assert_awaited_once()
        # No stored entry is read or written.
        mock_services.user_entry.get_entry.assert_not_called()
        _assert_understanding_channel_untouched(mock_services)

    async def test_core_tier_returns_inert_panel_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.journal = None
        request = _make_request(form={"content": "anything"})
        response = await handlers["/journals/suggest-activities"](request=request)

        assert response is not None
        _assert_understanding_channel_untouched(mock_services)


class TestJournalsAITierGate:
    """Per-user AI gate (ADR-043) on every LLM/Deepgram-spending journal route.

    REGISTERED signups resolve to effective CORE even on a FULL system — they
    must never reach ``run_discussion``/``run_follow_up``/the upload pipeline
    (each call spends OpenAI/Deepgram money). MEMBER+ passes; the pass-through
    side is also exercised by every other class here (the fixture user is
    MEMBER on a FULL system tier).
    """

    @staticmethod
    def _as_registered(mock_services: Any) -> None:
        from core.models.enums.user_enums import UserRole

        mock_services.user.get_user = AsyncMock(
            return_value=Result.ok(_make_user(is_founder=False, role=UserRole.REGISTERED))
        )

    async def test_registered_blocked_on_start(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        from fasthtml.common import to_xml

        self._as_registered(mock_services)
        request = _make_request(form={"raw_entry": "Costs money."})
        response = await handlers["/journals/start"](request=request)

        assert "paid subscription" in to_xml(response)
        mock_services.journal.run_discussion.assert_not_awaited()
        _assert_no_discussion_persisted(mock_services)

    async def test_registered_blocked_on_follow_up(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        from fasthtml.common import to_xml

        self._as_registered(mock_services)
        response = await handlers["/journals/follow-up"](
            request=_make_request(form={}), user_reply="More please."
        )

        assert "paid subscription" in to_xml(response)
        mock_services.journal.run_follow_up.assert_not_awaited()

    async def test_registered_blocked_on_upload(
        self, handlers: dict[str, Any], mock_services: Any, tmp_path: Any
    ) -> None:
        from fasthtml.common import to_xml

        self._as_registered(mock_services)
        request = _make_upload_request(
            [
                ("file", _text_upload("reflection.txt", b"Notes.")),
                ("processing_mode", "instructions_only"),
            ]
        )
        response = await handlers["/journals/upload"](request=request)

        assert "paid subscription" in to_xml(response)
        mock_services.journal.run_compiled.assert_not_awaited()
        assert not (tmp_path / "je_out" / "reflection_out.md").exists()

    async def test_registered_blocked_on_folder_process(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        from fasthtml.common import to_xml

        self._as_registered(mock_services)
        request = _make_request(form={"processing_mode": "transcribe_only"})
        response = await handlers["/journals/folder-process"](request=request)

        assert "paid subscription" in to_xml(response)

    async def test_registered_gets_inert_suggestions_panel(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        self._as_registered(mock_services)
        request = _make_request(form={"content": "Ship the site."})
        response = await handlers["/journals/suggest-activities"](request=request)

        assert response is not None
        mock_services.journal.suggest_activities.assert_not_awaited()

    async def test_failed_user_lookup_fails_secure(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # The gate cannot be evaluated → deny rather than allow.
        from fasthtml.common import to_xml

        mock_services.user.get_user = AsyncMock(
            return_value=Result.fail(Errors.database("get_user", "down"))
        )
        request = _make_request(form={"raw_entry": "Costs money."})
        response = await handlers["/journals/start"](request=request)

        assert "paid subscription" in to_xml(response)
        mock_services.journal.run_discussion.assert_not_awaited()

    async def test_member_passes_the_gate(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # Fixture default: MEMBER on a FULL system — the AI call goes through.
        request = _make_request(form={"raw_entry": "A paid member writes."})
        await handlers["/journals/start"](request=request)

        mock_services.journal.run_discussion.assert_awaited_once()
