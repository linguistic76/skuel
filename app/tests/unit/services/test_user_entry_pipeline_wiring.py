"""Tests for UserEntryProcessingService active-pipeline wiring (ADR-054).

Covers TRANSCRIBE, LLM_SUMMARY, and TRANSCRIBE_AND_STRUCTURE: success paths,
adapter/LLM failures, and missing-dependency guards. The dispatcher is
driven with mocked ``DeepgramAdapter`` + ``UnifiedLLMCaller`` +
``InstructionResolver`` + ``UserEntryService`` to keep the test fully unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import EnrichmentMode
from core.models.user_entry.user_entry import UserEntry
from core.ports.output_generator_protocols import OutputInstruction
from core.services.user_entry.user_entry_processing_service import (
    UserEntryProcessingService,
)
from core.services.user_entry.user_entry_service import ShareOutcome
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeTranscriptionResult:
    transcript_text: str
    confidence_score: float = 0.95
    duration_seconds: float = 1.0
    word_count: int = 3


def _make_entry(
    pipeline: Pipeline,
    *,
    file_path: str | None = None,
    content: str | None = None,
    metadata: dict | None = None,
) -> UserEntry:
    return UserEntry(
        uid=f"ue_{pipeline.value}",
        title=f"Entry {pipeline.value}",
        user_uid="user_1",
        pipeline=pipeline,
        file_path=file_path,
        content=content,
        metadata=metadata or {},
    )


def _instruction(prompt_text: str = "PROMPT: {content}") -> OutputInstruction:
    return OutputInstruction(
        prompt_text=prompt_text,
        source="template",
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=4000,
    )


def _make_dispatcher(
    *,
    entry_service: MagicMock | None = None,
    transcription_adapter: MagicMock | None = None,
    llm_caller: MagicMock | None = None,
    instruction_resolver: MagicMock | None = None,
    event_bus: MagicMock | None = None,
) -> UserEntryProcessingService:
    return UserEntryProcessingService(
        entry_service=entry_service or MagicMock(),
        transcription_adapter=transcription_adapter,
        llm_caller=llm_caller,
        instruction_resolver=instruction_resolver,
        event_bus=event_bus,
    )


def _entry_service_with_updated(updated_entry: UserEntry) -> MagicMock:
    svc = MagicMock()
    svc.update_processed_content = AsyncMock(return_value=Result.ok(updated_entry))
    svc.backend = MagicMock()
    svc.backend.update = AsyncMock(return_value=Result.ok(True))
    svc.create_entry = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# TRANSCRIBE
# ---------------------------------------------------------------------------


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_success_updates_processed_content(self):
        entry = _make_entry(Pipeline.TRANSCRIBE, file_path="/tmp/audio.mp3")
        updated = _make_entry(Pipeline.TRANSCRIBE, file_path="/tmp/audio.mp3")
        svc = _entry_service_with_updated(updated)

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.ok(_FakeTranscriptionResult(transcript_text="hello world"))
        )

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
        )
        result = await dispatcher.process(entry)

        assert result.is_ok
        adapter.transcribe.assert_awaited_once_with(audio_path="/tmp/audio.mp3")
        svc.update_processed_content.assert_awaited_once_with(
            uid=entry.uid,
            processed_content="hello world",
        )

    @pytest.mark.asyncio
    async def test_missing_adapter_fails_business_rule(self):
        entry = _make_entry(Pipeline.TRANSCRIBE, file_path="/tmp/audio.mp3")
        svc = _entry_service_with_updated(entry)

        dispatcher = _make_dispatcher(entry_service=svc, transcription_adapter=None)
        result = await dispatcher.process(entry)

        assert result.is_error
        svc.backend.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_file_path_validation_error(self):
        entry = _make_entry(Pipeline.TRANSCRIBE, file_path=None)
        svc = _entry_service_with_updated(entry)
        adapter = MagicMock()
        adapter.transcribe = AsyncMock()

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
        )
        result = await dispatcher.process(entry)

        assert result.is_error
        adapter.transcribe.assert_not_awaited()
        svc.backend.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_adapter_failure_marks_entry_failed(self):
        entry = _make_entry(Pipeline.TRANSCRIBE, file_path="/tmp/audio.mp3")
        svc = _entry_service_with_updated(entry)

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.fail(Errors.integration(service="deepgram", message="API down"))
        )

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
        )
        result = await dispatcher.process(entry)

        assert result.is_error
        svc.update_processed_content.assert_not_awaited()
        svc.backend.update.assert_awaited_once()
        update_args = svc.backend.update.await_args
        assert update_args.args[1]["status"] == EntityStatus.FAILED.value
        assert "API down" in update_args.args[1]["processing_error"]


# ---------------------------------------------------------------------------
# LLM_SUMMARY
# ---------------------------------------------------------------------------


class TestLlmSummary:
    @pytest.mark.asyncio
    async def test_success_updates_processed_content(self):
        entry = _make_entry(Pipeline.LLM_SUMMARY, content="raw body")
        updated = _make_entry(Pipeline.LLM_SUMMARY, content="raw body")
        svc = _entry_service_with_updated(updated)

        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=Result.ok(_instruction()))

        llm = MagicMock()
        llm.generate = AsyncMock(return_value=Result.ok("SUMMARY"))

        dispatcher = _make_dispatcher(
            entry_service=svc,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        result = await dispatcher.process(entry, instructions="be concise")

        assert result.is_ok
        resolver.resolve.assert_called_once()
        kwargs = resolver.resolve.call_args.kwargs
        assert kwargs["custom_instructions"] == "be concise"
        assert kwargs["enrichment_mode"] == EnrichmentMode.ACTIVITY_TRACKING
        # prompt_text "{content}" should have been substituted before call
        llm.generate.assert_awaited_once()
        assert "raw body" in llm.generate.await_args.kwargs["prompt"]
        svc.update_processed_content.assert_awaited_once_with(
            uid=entry.uid,
            processed_content="SUMMARY",
        )

    @pytest.mark.asyncio
    async def test_no_llm_caller_fails_tier_rule(self):
        entry = _make_entry(Pipeline.LLM_SUMMARY, content="raw")
        svc = _entry_service_with_updated(entry)

        dispatcher = _make_dispatcher(
            entry_service=svc,
            llm_caller=None,
            instruction_resolver=MagicMock(),
        )
        result = await dispatcher.process(entry)

        assert result.is_error
        err = result.expect_error()
        assert "llm_tier_required" in str(err.details) or "llm" in str(err).lower()
        svc.backend.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_content_validation_error(self):
        entry = _make_entry(Pipeline.LLM_SUMMARY, content=None)
        svc = _entry_service_with_updated(entry)

        resolver = MagicMock()
        llm = MagicMock()
        llm.generate = AsyncMock()

        dispatcher = _make_dispatcher(
            entry_service=svc,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        result = await dispatcher.process(entry)

        assert result.is_error
        llm.generate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_llm_failure_marks_entry_failed(self):
        entry = _make_entry(Pipeline.LLM_SUMMARY, content="raw")
        svc = _entry_service_with_updated(entry)

        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=Result.ok(_instruction()))

        llm = MagicMock()
        llm.generate = AsyncMock(
            return_value=Result.fail(Errors.integration(service="llm", message="rate limited"))
        )

        dispatcher = _make_dispatcher(
            entry_service=svc,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        result = await dispatcher.process(entry)

        assert result.is_error
        svc.update_processed_content.assert_not_awaited()
        svc.backend.update.assert_awaited_once()
        assert svc.backend.update.await_args.args[1]["status"] == EntityStatus.FAILED.value


# ---------------------------------------------------------------------------
# TRANSCRIBE_AND_STRUCTURE
# ---------------------------------------------------------------------------


class TestTranscribeAndStructure:
    @pytest.mark.asyncio
    async def test_success_creates_structured_child_entry(self):
        source = _make_entry(
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/audio.mp3",
        )
        updated_source = _make_entry(
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/audio.mp3",
        )
        child = _make_entry(Pipeline.NONE)

        svc = _entry_service_with_updated(updated_source)
        svc.create_entry = AsyncMock(return_value=Result.ok((child, ShareOutcome())))

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.ok(_FakeTranscriptionResult(transcript_text="raw transcript"))
        )

        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=Result.ok(_instruction()))

        llm = MagicMock()
        llm.generate = AsyncMock(return_value=Result.ok("structured output"))

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        result = await dispatcher.process(source)

        assert result.is_ok
        adapter.transcribe.assert_awaited_once()
        svc.update_processed_content.assert_awaited_once_with(
            uid=source.uid,
            processed_content="raw transcript",
        )
        llm.generate.assert_awaited_once()
        svc.create_entry.assert_awaited_once()
        child_req = svc.create_entry.await_args.kwargs["request"]
        assert child_req.pipeline == Pipeline.NONE
        assert child_req.content == "structured output"
        assert child_req.transforms_of_uid == source.uid
        assert svc.create_entry.await_args.kwargs["user_uid"] == source.user_uid

    @pytest.mark.asyncio
    async def test_transcription_failure_aborts_structuring(self):
        source = _make_entry(
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/audio.mp3",
        )
        svc = _entry_service_with_updated(source)

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.fail(Errors.integration(service="deepgram", message="boom"))
        )
        resolver = MagicMock()
        llm = MagicMock()
        llm.generate = AsyncMock()

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        result = await dispatcher.process(source)

        assert result.is_error
        llm.generate.assert_not_awaited()
        svc.create_entry.assert_not_awaited()
        svc.backend.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_after_transcript_still_marks_failed(self):
        source = _make_entry(
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/audio.mp3",
        )
        updated_source = _make_entry(
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/audio.mp3",
        )
        svc = _entry_service_with_updated(updated_source)

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.ok(_FakeTranscriptionResult(transcript_text="raw"))
        )
        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=Result.ok(_instruction()))
        llm = MagicMock()
        llm.generate = AsyncMock(
            return_value=Result.fail(Errors.integration(service="llm", message="nope"))
        )

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        result = await dispatcher.process(source)

        assert result.is_error
        svc.create_entry.assert_not_awaited()
        # Transcript was persisted before the LLM call failed.
        svc.update_processed_content.assert_awaited_once()
        svc.backend.update.assert_awaited_once()
        assert svc.backend.update.await_args.args[1]["status"] == EntityStatus.FAILED.value


# ---------------------------------------------------------------------------
# Failure-event phase tagging (F8)
# ---------------------------------------------------------------------------


class TestFailedPhaseEventTag:
    """UserEntryProcessingFailed.failed_phase identifies the broken stage."""

    @staticmethod
    def _event_bus_and_captured() -> tuple[MagicMock, list[Any]]:
        captured: list[Any] = []

        async def _publish(event: Any) -> None:
            captured.append(event)

        bus = MagicMock()
        bus.publish_async = AsyncMock(side_effect=_publish)
        return bus, captured

    @pytest.mark.asyncio
    async def test_transcribe_adapter_failure_tags_phase_transcribe(self):
        entry = _make_entry(Pipeline.TRANSCRIBE, file_path="/tmp/a.mp3")
        svc = _entry_service_with_updated(entry)
        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.fail(Errors.integration(service="deepgram", message="boom"))
        )
        bus, captured = self._event_bus_and_captured()

        dispatcher = _make_dispatcher(
            entry_service=svc, transcription_adapter=adapter, event_bus=bus
        )
        await dispatcher.process(entry)

        failed = [e for e in captured if e.event_type == "user_entry.processing_failed"]
        assert len(failed) == 1
        assert failed[0].failed_phase == "transcribe"

    @pytest.mark.asyncio
    async def test_transcribe_missing_adapter_tags_phase_setup(self):
        entry = _make_entry(Pipeline.TRANSCRIBE, file_path="/tmp/a.mp3")
        svc = _entry_service_with_updated(entry)
        bus, captured = self._event_bus_and_captured()

        dispatcher = _make_dispatcher(entry_service=svc, transcription_adapter=None, event_bus=bus)
        await dispatcher.process(entry)

        failed = [e for e in captured if e.event_type == "user_entry.processing_failed"]
        assert len(failed) == 1
        assert failed[0].failed_phase == "setup"

    @pytest.mark.asyncio
    async def test_transcribe_and_structure_llm_failure_tags_phase_structure(self):
        """Multi-phase pipeline — LLM break after transcript lands tagged `structure`."""
        source = _make_entry(Pipeline.TRANSCRIBE_AND_STRUCTURE, file_path="/tmp/a.mp3")
        updated_source = _make_entry(Pipeline.TRANSCRIBE_AND_STRUCTURE, file_path="/tmp/a.mp3")
        svc = _entry_service_with_updated(updated_source)

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.ok(_FakeTranscriptionResult(transcript_text="raw"))
        )
        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=Result.ok(_instruction()))
        llm = MagicMock()
        llm.generate = AsyncMock(
            return_value=Result.fail(Errors.integration(service="llm", message="nope"))
        )
        bus, captured = self._event_bus_and_captured()

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
            llm_caller=llm,
            instruction_resolver=resolver,
            event_bus=bus,
        )
        await dispatcher.process(source)

        failed = [e for e in captured if e.event_type == "user_entry.processing_failed"]
        assert len(failed) == 1
        assert failed[0].failed_phase == "structure"

    @pytest.mark.asyncio
    async def test_transcribe_and_structure_transcribe_failure_tags_phase_transcribe(self):
        """Multi-phase pipeline — Deepgram break tagged `transcribe`, not `structure`."""
        source = _make_entry(Pipeline.TRANSCRIBE_AND_STRUCTURE, file_path="/tmp/a.mp3")
        svc = _entry_service_with_updated(source)

        adapter = MagicMock()
        adapter.transcribe = AsyncMock(
            return_value=Result.fail(Errors.integration(service="deepgram", message="boom"))
        )
        resolver = MagicMock()
        llm = MagicMock()
        bus, captured = self._event_bus_and_captured()

        dispatcher = _make_dispatcher(
            entry_service=svc,
            transcription_adapter=adapter,
            llm_caller=llm,
            instruction_resolver=resolver,
            event_bus=bus,
        )
        await dispatcher.process(source)

        failed = [e for e in captured if e.event_type == "user_entry.processing_failed"]
        assert len(failed) == 1
        assert failed[0].failed_phase == "transcribe"


# ---------------------------------------------------------------------------
# Enrichment mode resolution
# ---------------------------------------------------------------------------


class TestEnrichmentModeResolution:
    @pytest.mark.asyncio
    async def test_metadata_override_is_honored(self):
        entry = _make_entry(
            Pipeline.LLM_SUMMARY,
            content="raw",
            metadata={"enrichment_mode": EnrichmentMode.CRITICAL_THINKING.value},
        )
        svc = _entry_service_with_updated(entry)

        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=Result.ok(_instruction()))
        llm = MagicMock()
        llm.generate = AsyncMock(return_value=Result.ok("ok"))

        dispatcher = _make_dispatcher(
            entry_service=svc,
            llm_caller=llm,
            instruction_resolver=resolver,
        )
        await dispatcher.process(entry)

        kwargs = resolver.resolve.call_args.kwargs
        assert kwargs["enrichment_mode"] == EnrichmentMode.CRITICAL_THINKING
