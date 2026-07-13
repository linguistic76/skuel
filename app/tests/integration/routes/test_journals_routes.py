"""Route tests for the Journals zero-persistence contract (ADR-073).

The contract: the journal text path (`POST /journals/start`), the file-upload
path (`POST /journals/upload`), and the suggestions panel
(`POST /journals/suggest-activities`) run their AI work and return results
*inline* / to the user's own `je_out/` folder — they must write **nothing** to
the store. These tests prove that invariant by asserting the persistence methods
on `user_entry_service` are never awaited, across STANDARD and FOUNDER tiers.

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


def _make_user(is_founder: bool) -> Any:
    user = MagicMock()
    user.journal_tier.is_founder.return_value = is_founder
    return user


@pytest.fixture
def mock_services() -> Any:
    services = MagicMock()

    services.user = MagicMock()
    services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=False)))

    from core.services.journal.journal_service import JournalFollowUp

    services.journal = MagicMock()
    services.journal.run_discussion = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="A discussion response.", sources=()))
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
    return services


@pytest.fixture
def handlers(mock_services: Any) -> dict[str, Any]:
    """Register the journals routes and return path → handler."""
    from adapters.inbound.journals_routes import create_journals_routes

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_journals_routes(MagicMock(), rt_collector, mock_services)
    return registered


def _assert_nothing_persisted(services: Any) -> None:
    services.user_entry.create_entry.assert_not_awaited()
    services.user_entry.update_processed_content.assert_not_awaited()
    services.user_entry.submit_file.assert_not_awaited()


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


def _register(services: Any) -> dict[str, Any]:
    """Register journals routes against ``services`` → path → handler.

    Used by tests that customise a service the route closure captures at
    registration time (e.g. ``batch_transcription``), which the module-level
    ``handlers`` fixture can't do after the fact.
    """
    from adapters.inbound.journals_routes import create_journals_routes

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

    async def test_standard_opens_discussion_and_persists_nothing(
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
        # Inline swap retargeted to the workspace — no redirect, no stored entry.
        assert response.status_code == 200
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        assert response.headers["HX-Reswap"] == "outerHTML"
        _assert_nothing_persisted(mock_services)

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
        _assert_nothing_persisted(mock_services)

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
        _assert_nothing_persisted(mock_services)

    async def test_ai_failure_still_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.journal.run_discussion = AsyncMock(
            return_value=Result.fail(Errors.integration("llm", "boom"))
        )
        request = _make_request(form={"raw_entry": "Trigger an AI failure."})
        await handlers["/journals/start"](request=request)

        _assert_nothing_persisted(mock_services)


class TestJournalsUploadZeroPersistence:
    """`POST /journals/upload` compiles to je_out/, never to Neo4j."""

    async def test_single_text_file_writes_je_out_and_persists_nothing(
        self,
        handlers: dict[str, Any],
        mock_services: Any,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        # FOUNDER instructions_only → run_compiled → je_out/{stem}_out.md.
        # workspace_target=1 marks the /journals landing layout (has a workspace).
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path)
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
        assert (tmp_path / "reflection_out.md").read_text() == "# Compiled output"
        # Result is retargeted to the centre workspace, not the right-panel status.
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        _assert_nothing_persisted(mock_services)

    async def test_single_upload_without_workspace_does_not_retarget(
        self,
        handlers: dict[str, Any],
        mock_services: Any,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        # The /submissions/journal form omits workspace_target → the result must
        # NOT retarget to a missing #journal-workspace (Codex, #478).
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path)
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
        _assert_nothing_persisted(mock_services)

    async def test_no_file_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_upload_request([("processing_mode", "instructions_only")])
        await handlers["/journals/upload"](request=request)
        _assert_nothing_persisted(mock_services)

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
        _assert_nothing_persisted(mock_services)

    async def test_empty_audio_batch_reports_error(
        self, mock_services: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # A "Transcribe only" batch with no supported audio (e.g. a text folder)
        # must not render a false success (Codex, #478). Register handlers with a
        # batch service wired, since the closure captures it at registration.
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path)
        empty = SimpleNamespace(total_files=0, succeeded=0, failed=0, skipped=0, results=[])
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(empty)
        )
        registered = _register(mock_services)

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
        _assert_nothing_persisted(mock_services)

    async def test_single_transcribe_and_instructions_preflights_llm(
        self, mock_services: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # STANDARD single audio upload with Deepgram but no LLM must fail BEFORE
        # transcribing, so no Deepgram quota is spent (Codex, #478).
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path)
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_one = AsyncMock(
            return_value=Result.ok("transcript")
        )
        mock_services.user_entry_processor = SimpleNamespace(llm_caller=None)  # no LLM
        registered = _register(mock_services)

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
        _assert_nothing_persisted(mock_services)

    async def test_structuring_forces_fresh_transcription(
        self, mock_services: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # folder-process transcribe_and_instructions must force skip_existing=False
        # even though folder reruns default to True — structured output must match
        # the current audio, never a stale same-stem transcript (Kody, #478).
        je_in = tmp_path / "je_in"
        je_in.mkdir()
        (je_in / "memo.mp3").write_bytes(b"audio")
        je_out = tmp_path / "je_out"
        je_out.mkdir()
        monkeypatch.setattr("adapters.inbound.journals_routes._je_in", lambda: je_in)
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: je_out)

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
        mock_services.user_entry_processor = SimpleNamespace(llm_caller=llm)
        registered = _register(mock_services)

        request = _make_upload_request([("processing_mode", "transcribe_and_instructions")])
        await registered["/journals/folder-process"](request=request)

        _, kwargs = mock_services.batch_transcription.transcribe_batch.call_args
        assert kwargs.get("skip_existing") is False
        _assert_nothing_persisted(mock_services)

    async def test_dedup_guard_is_mode_aware(
        self, mock_services: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # Under "Transcribe only", an ignored same-stem text file (meeting.txt)
        # next to meeting.mp3 must NOT trigger the duplicate-output guard — only
        # the mp3 produces je_out output (Codex, #478).
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path)
        done = SimpleNamespace(
            total_files=1,
            succeeded=1,
            failed=0,
            skipped=0,
            results=[{"name": "meeting.mp3", "status": "success"}],
        )
        mock_services.batch_transcription = MagicMock()
        mock_services.batch_transcription.transcribe_batch = AsyncMock(return_value=Result.ok(done))
        registered = _register(mock_services)

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
        _assert_nothing_persisted(mock_services)


class TestJournalExemplarLoading:
    """`je_raw`/`je_pro` are read off disk as few-shot exemplars (ADR-073 §4).

    Read-only, in-memory, bounded — never ingested or persisted.
    """

    @staticmethod
    def _wire(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> tuple[Any, Any]:
        raw = tmp_path / "je_raw"
        pro = tmp_path / "je_pro"
        raw.mkdir()
        pro.mkdir()
        monkeypatch.setattr("adapters.inbound.journals_routes._je_raw", lambda: raw)
        monkeypatch.setattr("adapters.inbound.journals_routes._je_pro", lambda: pro)
        return raw, pro

    def test_matched_pairs_load_by_stem(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from adapters.inbound.journals_routes import _load_journal_exemplars

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "example.md").write_text("RAW BODY")
        (pro / "example.md").write_text("PRO BODY")

        pairs = _load_journal_exemplars()
        assert pairs == [("RAW BODY", "PRO BODY")]

    def test_unmatched_files_are_skipped(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from adapters.inbound.journals_routes import _load_journal_exemplars

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "lonely.md").write_text("no partner")  # only in je_raw
        (pro / "orphan.md").write_text("no partner")  # only in je_pro

        assert _load_journal_exemplars() == []

    def test_absent_folders_degrade_to_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from adapters.inbound.journals_routes import _load_journal_exemplars

        monkeypatch.setattr(
            "adapters.inbound.journals_routes._je_raw", lambda: tmp_path / "nope_raw"
        )
        monkeypatch.setattr(
            "adapters.inbound.journals_routes._je_pro", lambda: tmp_path / "nope_pro"
        )
        assert _load_journal_exemplars() == []

    def test_pair_count_is_capped(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        from adapters.inbound.journals_routes import (
            _EXEMPLAR_MAX_PAIRS,
            _load_journal_exemplars,
        )

        raw, pro = self._wire(monkeypatch, tmp_path)
        for i in range(_EXEMPLAR_MAX_PAIRS + 2):
            (raw / f"e{i}.md").write_text(f"raw {i}")
            (pro / f"e{i}.md").write_text(f"pro {i}")

        assert len(_load_journal_exemplars()) == _EXEMPLAR_MAX_PAIRS

    def test_each_side_is_truncated(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        from adapters.inbound.journals_routes import (
            _EXEMPLAR_MAX_CHARS,
            _load_journal_exemplars,
        )

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "big.md").write_text("R" * (_EXEMPLAR_MAX_CHARS + 500))
        (pro / "big.md").write_text("P" * (_EXEMPLAR_MAX_CHARS + 500))

        (raw_body, pro_body) = _load_journal_exemplars()[0]
        assert len(raw_body) == _EXEMPLAR_MAX_CHARS
        assert len(pro_body) == _EXEMPLAR_MAX_CHARS

    def test_undecodable_exemplar_is_skipped_not_raised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # A non-UTF-8 exemplar must be skipped, never raise out of the helper
        # (UnicodeDecodeError is a UnicodeError, not an OSError). Kody #480.
        from adapters.inbound.journals_routes import _load_journal_exemplars

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "bad.md").write_bytes(b"\xff\xfe not valid utf-8")
        (pro / "bad.md").write_text("valid partner")

        assert _load_journal_exemplars() == []  # skipped cleanly, no exception

    def test_preamble_empty_when_no_pairs(self) -> None:
        from adapters.inbound.journals_routes import _build_exemplar_preamble

        assert _build_exemplar_preamble([]) == ""

    def test_understanding_only_je_pro_file_never_used_as_exemplar(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # ADR-073 amendment: `je_use: understanding` scopes the file to the
        # ingestion channel only — the loader must skip it even with a raw twin.
        from adapters.inbound.journals_routes import _load_journal_exemplars

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "private.md").write_text("RAW BODY")
        (pro / "private.md").write_text(
            "---\npipeline: knowledge\nje_use: understanding\n---\nABOUT ME"
        )

        assert _load_journal_exemplars() == []

    def test_garbled_je_use_skips_exemplar_use(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # Unrecognized je_use is honored in neither direction (fail-closed
        # both ways — the ingestion gate skips it too).
        from adapters.inbound.journals_routes import _load_journal_exemplars

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "typo.md").write_text("RAW BODY")
        (pro / "typo.md").write_text("---\nje_use: exmplar\n---\nSTYLED")

        assert _load_journal_exemplars() == []

    def test_frontmatter_stripped_from_exemplar_text(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # A consented je_pro file carries YAML frontmatter — consent metadata,
        # not style. It must never reach the LLM as exemplar text.
        from adapters.inbound.journals_routes import _load_journal_exemplars

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "pair.md").write_text("RAW BODY")
        (pro / "pair.md").write_text(
            "---\ntype: user_entry\npipeline: knowledge\nje_use: both\n---\nSTYLED BODY"
        )

        pairs = _load_journal_exemplars()
        assert pairs == [("RAW BODY", "STYLED BODY")]

    def test_unterminated_frontmatter_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # Codex #608: an opening fence whose close falls OUTSIDE the bounded
        # read must skip the file — parsing the truncated text would default
        # je_use to BOTH and inject raw YAML into the prompt as style.
        from adapters.inbound.journals_routes import (
            _EXEMPLAR_FRONTMATTER_HEADROOM,
            _EXEMPLAR_MAX_CHARS,
            _load_journal_exemplars,
        )

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "big.md").write_text("RAW BODY")
        oversized = "---\nje_use: understanding\npad: " + "z" * (
            _EXEMPLAR_MAX_CHARS + _EXEMPLAR_FRONTMATTER_HEADROOM
        )
        (pro / "big.md").write_text(oversized + "\n---\nSTYLED")

        assert _load_journal_exemplars() == []

    def test_frontmatter_headroom_preserves_content_budget(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # The frontmatter block must not eat into the exemplar's char budget.
        from adapters.inbound.journals_routes import (
            _EXEMPLAR_MAX_CHARS,
            _load_journal_exemplars,
        )

        raw, pro = self._wire(monkeypatch, tmp_path)
        (raw / "big.md").write_text("R" * (_EXEMPLAR_MAX_CHARS + 500))
        (pro / "big.md").write_text(
            "---\npipeline: knowledge\n---\n" + "P" * (_EXEMPLAR_MAX_CHARS + 500)
        )

        (raw_body, pro_body) = _load_journal_exemplars()[0]
        assert len(raw_body) == _EXEMPLAR_MAX_CHARS
        assert len(pro_body) == _EXEMPLAR_MAX_CHARS
        assert pro_body == "P" * _EXEMPLAR_MAX_CHARS


class TestJournalExemplarInjection:
    """Exemplars reach the LLM prompt and still persist nothing."""

    async def test_exemplars_injected_into_prompt_and_persist_nothing(
        self, mock_services: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # STANDARD single upload (instructions_only) routes through
        # _call_llm_with_instructions, which injects the je_raw/je_pro pair.
        raw = tmp_path / "je_raw"
        pro = tmp_path / "je_pro"
        raw.mkdir()
        pro.mkdir()
        (raw / "sample.md").write_text("RAW_EXEMPLAR_MARKER")
        (pro / "sample.md").write_text("PRO_EXEMPLAR_MARKER")
        monkeypatch.setattr("adapters.inbound.journals_routes._je_raw", lambda: raw)
        monkeypatch.setattr("adapters.inbound.journals_routes._je_pro", lambda: pro)
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path / "je_out")

        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("processed"))
        mock_services.user_entry_processor = SimpleNamespace(llm_caller=llm)
        registered = _register(mock_services)  # STANDARD user (default fixture)

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
        _assert_nothing_persisted(mock_services)

    async def test_no_exemplars_leaves_prompt_clean(
        self, mock_services: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # Absent je_raw/je_pro → prompt is just the user's text (today's behavior).
        monkeypatch.setattr(
            "adapters.inbound.journals_routes._je_raw", lambda: tmp_path / "nope_raw"
        )
        monkeypatch.setattr(
            "adapters.inbound.journals_routes._je_pro", lambda: tmp_path / "nope_pro"
        )
        monkeypatch.setattr("adapters.inbound.journals_routes._je_out", lambda: tmp_path / "je_out")

        llm = MagicMock()
        llm.is_model_supported = MagicMock(return_value=True)
        llm.generate = AsyncMock(return_value=Result.ok("processed"))
        mock_services.user_entry_processor = SimpleNamespace(llm_caller=llm)
        registered = _register(mock_services)

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
        _assert_nothing_persisted(mock_services)


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
        _assert_nothing_persisted(mock_services)

    async def test_core_tier_returns_inert_panel_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.journal = None
        request = _make_request(form={"content": "anything"})
        response = await handlers["/journals/suggest-activities"](request=request)

        assert response is not None
        _assert_nothing_persisted(mock_services)
