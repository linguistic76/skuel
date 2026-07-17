"""Tests for JournalBatchService — the zero-persistence je_in/upload → je_out engine.

Covers the three processing modes (instructions_only / transcribe_only /
transcribe_and_instructions): mode dispatch, per-phase degradation
(transcription failure vs LLM failure), tier guards, and the doorway output
naming formula (``{stem}.txt`` transcripts, ``{stem}_out.md`` compiled).
Driven with mocked transcription + LLM ports and ``tmp_path`` je_* folders —
mirrors the harness style of ``test_user_entry_pipeline_wiring.py``.

Zero-persistence (ADR-073) is structural here: the service takes no
graph-backed dependency at all, so there is nothing it *could* persist.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.journal.journal_batch_service import (
    BatchRunReport,
    JournalBatchService,
    _build_exemplar_preamble,
)
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _llm(response: str = "COMPILED", *, claude_supported: bool = True) -> MagicMock:
    llm = MagicMock()
    llm.is_model_supported = MagicMock(return_value=claude_supported)
    llm.generate = AsyncMock(return_value=Result.ok(response))
    return llm


def _batch_result(
    *,
    total_files: int = 1,
    succeeded: int = 1,
    failed: int = 0,
    skipped: int = 0,
    results: list[dict[str, Any]] | None = None,
) -> Any:
    return SimpleNamespace(
        total_files=total_files,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        results=results if results is not None else [{"name": "memo.mp3", "status": "success"}],
    )


def _make_service(
    tmp_path: Path,
    *,
    batch_transcription: Any = None,
    llm_caller: Any = None,
    journal_service: Any = None,
) -> JournalBatchService:
    return JournalBatchService(
        batch_transcription_service=batch_transcription,
        llm_caller=llm_caller,
        journal_service=journal_service,
        vault_root=tmp_path,
    )


# ---------------------------------------------------------------------------
# Staging folders + output naming
# ---------------------------------------------------------------------------


class TestWriteOutput:
    def test_doorway_naming_formula(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)

        assert service.write_output("memo", ".txt", "raw transcript") == "memo.txt"
        assert service.write_output("memo", "_out.md", "compiled") == "memo_out.md"
        assert (tmp_path / "je_out" / "memo.txt").read_text() == "raw transcript"
        assert (tmp_path / "je_out" / "memo_out.md").read_text() == "compiled"

    def test_untrusted_stem_path_components_are_stripped(self, tmp_path: Path) -> None:
        # Path(stem).name sanitization: an upload named "../../etc/passwd" must
        # land flat in je_out/, never traverse out of it.
        service = _make_service(tmp_path)

        filename = service.write_output("../../etc/passwd", "_out.md", "x")

        assert filename == "passwd_out.md"
        assert (tmp_path / "je_out" / "passwd_out.md").is_file()
        assert not (tmp_path.parent / "etc").exists()

    def test_creates_je_out_dir(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        assert not (tmp_path / "je_out").exists()
        service.write_output("a", ".txt", "t")
        assert (tmp_path / "je_out").is_dir()

    def test_staging_dirs_derive_from_vault_root(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        assert service.je_in_dir == tmp_path / "je_in"
        assert service.je_out_dir == tmp_path / "je_out"


# ---------------------------------------------------------------------------
# Instruction resolution
# ---------------------------------------------------------------------------


class TestResolveInstructions:
    def test_inline_content_wins_over_filename(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        resolved = service.resolve_instructions(
            instruction_content="inline wins",
            instruction_filename="whatever.md",
            processing_mode="instructions_only",
        )
        assert resolved == "inline wins"

    def test_transcribe_only_never_carries_instructions(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        resolved = service.resolve_instructions(
            instruction_content="",
            instruction_filename="named.md",
            processing_mode="transcribe_only",
        )
        assert resolved is None

    def test_absent_filename_resolves_none(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        resolved = service.resolve_instructions(
            instruction_content="",
            instruction_filename="",
            processing_mode="instructions_only",
        )
        assert resolved is None

    def test_named_file_loads_from_instructions_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.services.journal import instruction_loader

        monkeypatch.setattr(instruction_loader, "INSTRUCTIONS_DIR", tmp_path)
        (tmp_path / "custom.md").write_text("FROM FILE")
        service = _make_service(tmp_path)

        resolved = service.resolve_instructions(
            instruction_content="",
            instruction_filename="custom.md",
            processing_mode="instructions_only",
        )
        assert resolved == "FROM FILE"

    def test_path_traversal_is_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.services.journal import instruction_loader

        instructions_dir = tmp_path / "instructions"
        instructions_dir.mkdir()
        monkeypatch.setattr(instruction_loader, "INSTRUCTIONS_DIR", instructions_dir)
        (tmp_path / "secret.md").write_text("OUTSIDE")
        service = _make_service(tmp_path)

        resolved = service.resolve_instructions(
            instruction_content="",
            instruction_filename="../secret.md",
            processing_mode="instructions_only",
        )
        assert resolved is None


# ---------------------------------------------------------------------------
# compile_text dispatch
# ---------------------------------------------------------------------------


class TestCompileText:
    @pytest.mark.asyncio
    async def test_founder_routes_to_dnwf_compile_with_dials(self, tmp_path: Path) -> None:
        journal = MagicMock()
        journal.run_compiled = AsyncMock(return_value=Result.ok("# DNWF output"))
        llm = _llm()
        service = _make_service(tmp_path, llm_caller=llm, journal_service=journal)

        result = await service.compile_text(
            "entry text",
            "instructions",
            user_uid="user_1",
            is_founder=True,
            summon_canon=True,
            summon_vault=True,
        )

        assert result.is_ok and result.value == "# DNWF output"
        journal.run_compiled.assert_awaited_once_with(
            "entry text", "user_1", summon_canon=True, summon_vault=True
        )
        llm.generate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_founder_without_journal_service_falls_back_to_llm(self, tmp_path: Path) -> None:
        llm = _llm("single pass")
        service = _make_service(tmp_path, llm_caller=llm, journal_service=None)

        result = await service.compile_text("entry text", None, user_uid="user_1", is_founder=True)

        assert result.is_ok and result.value == "single pass"
        llm.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_standard_single_llm_pass_with_instruction_header(self, tmp_path: Path) -> None:
        llm = _llm()
        service = _make_service(tmp_path, llm_caller=llm)

        result = await service.compile_text(
            "raw body", "be concise", user_uid="user_1", is_founder=False
        )

        assert result.is_ok
        prompt = llm.generate.await_args.kwargs["prompt"]
        assert prompt.startswith("be concise")
        assert "---" in prompt
        assert prompt.endswith("raw body")

    @pytest.mark.asyncio
    async def test_no_instructions_no_exemplars_passes_bare_text(self, tmp_path: Path) -> None:
        llm = _llm()
        service = _make_service(tmp_path, llm_caller=llm)

        await service.compile_text("just the text", None, user_uid="user_1", is_founder=False)

        assert llm.generate.await_args.kwargs["prompt"] == "just the text"

    @pytest.mark.asyncio
    async def test_missing_llm_fails_tier_rule(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, llm_caller=None)

        result = await service.compile_text("text", None, user_uid="user_1", is_founder=False)

        assert result.is_error
        assert "INTELLIGENCE_TIER=full" in str(result.expect_error())

    @pytest.mark.asyncio
    async def test_llm_exception_becomes_integration_error(self, tmp_path: Path) -> None:
        llm = _llm()
        llm.generate = AsyncMock(side_effect=RuntimeError("socket closed"))
        service = _make_service(tmp_path, llm_caller=llm)

        result = await service.compile_text("text", None, user_uid="user_1", is_founder=False)

        assert result.is_error
        assert "socket closed" in str(result.expect_error())

    @pytest.mark.asyncio
    async def test_model_falls_back_when_claude_unsupported(self, tmp_path: Path) -> None:
        llm = _llm(claude_supported=False)
        service = _make_service(tmp_path, llm_caller=llm)

        await service.compile_text("text", None, user_uid="user_1", is_founder=False)

        assert llm.generate.await_args.kwargs["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_exemplar_pairs_are_injected_after_instructions(self, tmp_path: Path) -> None:
        (tmp_path / "je_raw").mkdir()
        (tmp_path / "je_pro").mkdir()
        (tmp_path / "je_raw" / "sample.md").write_text("RAW_MARKER")
        (tmp_path / "je_pro" / "sample.md").write_text("PRO_MARKER")
        llm = _llm()
        service = _make_service(tmp_path, llm_caller=llm)

        await service.compile_text("body", "INSTR", user_uid="user_1", is_founder=False)

        prompt = llm.generate.await_args.kwargs["prompt"]
        assert prompt.index("INSTR") < prompt.index("RAW_MARKER") < prompt.index("PRO_MARKER")
        assert prompt.endswith("body")

    def test_preamble_empty_without_pairs(self) -> None:
        assert _build_exemplar_preamble([]) == ""


# ---------------------------------------------------------------------------
# transcribe_upload
# ---------------------------------------------------------------------------


class TestTranscribeUpload:
    @pytest.mark.asyncio
    async def test_success_returns_transcript_and_cleans_temp_file(self, tmp_path: Path) -> None:
        captured: dict[str, str] = {}

        async def _transcribe_one(audio_path: str) -> Result[str]:
            captured["path"] = audio_path
            assert Path(audio_path).read_bytes() == b"audio-bytes"
            return Result.ok("hello world")

        transcription = MagicMock()
        transcription.transcribe_one = AsyncMock(side_effect=_transcribe_one)
        service = _make_service(tmp_path, batch_transcription=transcription)

        result = await service.transcribe_upload(b"audio-bytes", ".mp3")

        assert result.is_ok and result.value == "hello world"
        assert captured["path"].endswith(".mp3")
        assert not Path(captured["path"]).exists()  # temp file unlinked

    @pytest.mark.asyncio
    async def test_missing_transcription_service_fails_tier_rule(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, batch_transcription=None)

        result = await service.transcribe_upload(b"audio", ".mp3")

        assert result.is_error
        assert "FULL tier" in str(result.expect_error())

    @pytest.mark.asyncio
    async def test_transcription_failure_propagates(self, tmp_path: Path) -> None:
        transcription = MagicMock()
        transcription.transcribe_one = AsyncMock(
            return_value=Result.fail(Errors.integration(service="deepgram", message="API down"))
        )
        service = _make_service(tmp_path, batch_transcription=transcription)

        result = await service.transcribe_upload(b"audio", ".wav")

        assert result.is_error
        assert "API down" in str(result.expect_error())


# ---------------------------------------------------------------------------
# run_batch_over_dir — mode dispatch + degradation
# ---------------------------------------------------------------------------


class TestBatchUnknownMode:
    @pytest.mark.asyncio
    async def test_unknown_mode_reports_error(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)

        report = await service.run_batch_over_dir(tmp_path, "surprise_mode", None)

        assert report == BatchRunReport(
            ok=False, message="Unknown processing mode: 'surprise_mode'"
        )
        # Unknown mode fails before any filesystem effect — je_out/ is not created.
        assert not service.je_out_dir.exists()


class TestBatchTranscribeOnly:
    @pytest.mark.asyncio
    async def test_missing_transcription_service_fails_before_anything(
        self, tmp_path: Path
    ) -> None:
        service = _make_service(tmp_path, batch_transcription=None)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_only", None)

        assert not report.ok
        assert "FULL tier" in report.message

    @pytest.mark.asyncio
    async def test_success_counts_and_honors_skip_existing(self, tmp_path: Path) -> None:
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(_batch_result(total_files=3, succeeded=2, failed=0, skipped=1))
        )
        service = _make_service(tmp_path, batch_transcription=transcription)

        report = await service.run_batch_over_dir(
            tmp_path / "je_in", "transcribe_only", None, skip_existing=True
        )

        assert report.ok
        assert report.message == "2 transcribed, 0 failed, 1 skipped — results in je_out/"
        # transcribe_only passes the caller's skip_existing through unchanged.
        args, kwargs = transcription.transcribe_batch.call_args
        assert kwargs["skip_existing"] is True
        assert args == (tmp_path / "je_in", tmp_path / "je_out")

    @pytest.mark.asyncio
    async def test_all_failed_is_an_error(self, tmp_path: Path) -> None:
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(_batch_result(total_files=2, succeeded=0, failed=2))
        )
        service = _make_service(tmp_path, batch_transcription=transcription)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_only", None)

        assert not report.ok
        assert "2 failed" in report.message

    @pytest.mark.asyncio
    async def test_partial_failure_still_completes(self, tmp_path: Path) -> None:
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(_batch_result(total_files=2, succeeded=1, failed=1))
        )
        service = _make_service(tmp_path, batch_transcription=transcription)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_only", None)

        assert report.ok  # something succeeded — not a whole-run error

    @pytest.mark.asyncio
    async def test_no_audio_files_is_an_error_not_silent_success(self, tmp_path: Path) -> None:
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(_batch_result(total_files=0, succeeded=0, failed=0, results=[]))
        )
        service = _make_service(tmp_path, batch_transcription=transcription)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_only", None)

        assert not report.ok
        assert report.message == "No supported audio files found to transcribe"

    @pytest.mark.asyncio
    async def test_transcribe_batch_error_propagates(self, tmp_path: Path) -> None:
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.fail(Errors.integration(service="deepgram", message="quota"))
        )
        service = _make_service(tmp_path, batch_transcription=transcription)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_only", None)

        assert not report.ok
        assert "quota" in report.message


class TestBatchTranscribeAndInstructions:
    @pytest.mark.asyncio
    async def test_missing_llm_fails_before_transcribing(self, tmp_path: Path) -> None:
        # Deepgram quota must not be spent when the LLM leg can't run.
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock()
        service = _make_service(tmp_path, batch_transcription=transcription, llm_caller=None)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_and_instructions", None)

        assert not report.ok
        assert "INTELLIGENCE_TIER=full" in report.message
        transcription.transcribe_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_forces_fresh_transcription_even_when_skip_requested(
        self, tmp_path: Path
    ) -> None:
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(_batch_result(results=[]))
        )
        service = _make_service(tmp_path, batch_transcription=transcription, llm_caller=_llm())

        await service.run_batch_over_dir(
            tmp_path, "transcribe_and_instructions", None, skip_existing=True
        )

        # Structured output must reflect the CURRENT audio — never a stale
        # same-stem transcript, so skip_existing is forced off for this mode.
        assert transcription.transcribe_batch.call_args.kwargs["skip_existing"] is False

    @pytest.mark.asyncio
    async def test_structures_each_transcript_to_out_md(self, tmp_path: Path) -> None:
        je_out = tmp_path / "je_out"
        je_out.mkdir()
        (je_out / "memo.txt").write_text("the transcript")
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(
                _batch_result(results=[{"name": "memo.mp3", "status": "success"}])
            )
        )
        llm = _llm("STRUCTURED")
        service = _make_service(tmp_path, batch_transcription=transcription, llm_caller=llm)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_and_instructions", "instr")

        assert report.ok
        assert report.message == "1 transcribed, 1 structured, 0 failed — results in je_out/"
        assert (je_out / "memo_out.md").read_text() == "STRUCTURED"
        assert "the transcript" in llm.generate.await_args.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_llm_failure_phase_reports_error_and_keeps_transcript(
        self, tmp_path: Path
    ) -> None:
        # Transcription succeeded, LLM leg failed: the raw .txt stays in je_out
        # but the run is an error — the deliverable is the structured _out.md.
        je_out = tmp_path / "je_out"
        je_out.mkdir()
        (je_out / "memo.txt").write_text("the transcript")
        transcription = MagicMock()
        transcription.transcribe_batch = AsyncMock(
            return_value=Result.ok(
                _batch_result(results=[{"name": "memo.mp3", "status": "success"}])
            )
        )
        llm = _llm()
        llm.generate = AsyncMock(
            return_value=Result.fail(Errors.integration(service="llm", message="rate limited"))
        )
        service = _make_service(tmp_path, batch_transcription=transcription, llm_caller=llm)

        report = await service.run_batch_over_dir(tmp_path, "transcribe_and_instructions", None)

        assert not report.ok
        assert report.message == "1 transcribed, 0 structured, 1 failed — results in je_out/"
        assert (je_out / "memo.txt").exists()
        assert not (je_out / "memo_out.md").exists()


class TestBatchInstructionsOnly:
    @pytest.mark.asyncio
    async def test_missing_llm_fails_tier_rule(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, llm_caller=None)

        report = await service.run_batch_over_dir(tmp_path, "instructions_only", None)

        assert not report.ok
        assert "INTELLIGENCE_TIER=full" in report.message

    @pytest.mark.asyncio
    async def test_missing_input_dir_reports_error(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, llm_caller=_llm())
        missing = tmp_path / "nope"

        report = await service.run_batch_over_dir(missing, "instructions_only", None)

        assert not report.ok
        assert report.message == f"Input folder not found: {missing}"

    @pytest.mark.asyncio
    async def test_no_text_files_reports_error(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "je_in"
        input_dir.mkdir()
        (input_dir / "photo.png").write_bytes(b"\x89PNG")
        service = _make_service(tmp_path, llm_caller=_llm())

        report = await service.run_batch_over_dir(input_dir, "instructions_only", None)

        assert not report.ok
        assert report.message == "No text files found to process"

    @pytest.mark.asyncio
    async def test_compiles_each_text_file_to_out_md(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "je_in"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("alpha")
        (input_dir / "b.md").write_text("beta")
        service = _make_service(tmp_path, llm_caller=_llm("PROCESSED"))

        report = await service.run_batch_over_dir(input_dir, "instructions_only", None)

        assert report.ok
        assert report.message == "2 processed, 0 failed — results in je_out/"
        assert (tmp_path / "je_out" / "a_out.md").read_text() == "PROCESSED"
        assert (tmp_path / "je_out" / "b_out.md").read_text() == "PROCESSED"

    @pytest.mark.asyncio
    async def test_per_file_llm_failure_counts_and_continues(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "je_in"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("alpha")
        (input_dir / "b.txt").write_text("beta")
        llm = _llm()
        llm.generate = AsyncMock(
            side_effect=[
                Result.fail(Errors.integration(service="llm", message="boom")),
                Result.ok("PROCESSED"),
            ]
        )
        service = _make_service(tmp_path, llm_caller=llm)

        report = await service.run_batch_over_dir(input_dir, "instructions_only", None)

        assert report.ok  # one file made it — partial completion
        assert report.message == "1 processed, 1 failed — results in je_out/"

    @pytest.mark.asyncio
    async def test_all_files_failing_is_an_error(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "je_in"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("alpha")
        llm = _llm()
        llm.generate = AsyncMock(
            return_value=Result.fail(Errors.integration(service="llm", message="boom"))
        )
        service = _make_service(tmp_path, llm_caller=llm)

        report = await service.run_batch_over_dir(input_dir, "instructions_only", None)

        assert not report.ok
        assert report.message == "0 processed, 1 failed — results in je_out/"
