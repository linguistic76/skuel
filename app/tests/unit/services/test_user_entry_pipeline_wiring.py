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
from core.models.relationship_names import RelationshipName
from core.models.user_entry.user_entry import UserEntry
from core.ports.output_generator_protocols import OutputInstruction
from core.services.dsl import ActivityExtractionResult, DSLTransformResult
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
    svc.update_processing_state = AsyncMock(return_value=Result.ok(updated_entry))
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
        svc.update_processing_state.assert_awaited_once()

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
        svc.update_processing_state.assert_awaited_once()

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
        svc.update_processing_state.assert_awaited_once()
        update_args = svc.update_processing_state.await_args
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
        svc.update_processing_state.assert_awaited_once()

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
        svc.update_processing_state.assert_awaited_once()
        assert svc.update_processing_state.await_args.args[1]["status"] == EntityStatus.FAILED.value


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
        svc.update_processing_state.assert_awaited_once()

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
        svc.update_processing_state.assert_awaited_once()
        assert svc.update_processing_state.await_args.args[1]["status"] == EntityStatus.FAILED.value


# ---------------------------------------------------------------------------
# EXTRACT_ACTIVITIES (ADR-069)
# ---------------------------------------------------------------------------


def _extract_entry_service(updated_entry: UserEntry) -> MagicMock:
    """Entry-service mock with the service surfaces the extraction branch uses."""
    svc = _entry_service_with_updated(updated_entry)
    svc.get_relationships = AsyncMock(return_value=Result.ok([]))
    svc.get_extracted_entities = AsyncMock(return_value=Result.ok([]))
    svc.get_user_active_extraction_twins = AsyncMock(return_value=Result.ok([]))
    svc.create_extracted_from_links = AsyncMock(return_value=Result.ok(1))
    svc.add_relationship = AsyncMock(return_value=Result.ok(True))
    svc.get_entry = AsyncMock(return_value=Result.ok(updated_entry))
    return svc


def _extraction_result(
    entry_uid: str,
    *,
    created_links: list[tuple[str, str, str | None]] | None = None,
    created_ku_uids: list[str] | None = None,
    referenced_ku_uids: list[str] | None = None,
) -> ActivityExtractionResult:
    return ActivityExtractionResult(
        entry_uid=entry_uid,
        user_uid="user_1",
        created_links=created_links or [],
        created_ku_uids=created_ku_uids or [],
        referenced_ku_uids=referenced_ku_uids or [],
    )


def _dsl_result_empty() -> DSLTransformResult:
    """A bridge result that recognised nothing (no activity lines appended)."""
    return DSLTransformResult(original_text="", transformed_text="", activity_lines=[])


def _teacher_user_service(can_create: bool = True) -> MagicMock:
    user = MagicMock()
    user.can_create_curriculum = MagicMock(return_value=can_create)
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


class TestExtractActivities:
    @pytest.mark.asyncio
    async def test_parser_only_success_persists_links_and_summary(self):
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- [ ] Call mom @context(task)")
        svc = _extract_entry_service(entry)

        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(
                _extraction_result(
                    entry.uid,
                    created_links=[("task:1", "hash1", None)],
                    referenced_ku_uids=["ku:tech/x"],
                )
            )
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        dispatcher.user_service = _teacher_user_service()
        result = await dispatcher.process(entry)

        assert result.is_ok
        svc.create_extracted_from_links.assert_awaited_once_with(
            entry.uid, [("task:1", "hash1", None)]
        )
        svc.add_relationship.assert_awaited_once()
        assert svc.add_relationship.await_args.args == (
            entry.uid,
            RelationshipName.APPLIES_KNOWLEDGE,
            "ku:tech/x",
        )
        svc.update_processing_state.assert_awaited_once()
        updates = svc.update_processing_state.await_args.args[1]
        assert updates["metadata"]["activity_extraction"]["status"] == "completed"
        assert updates["status"] == EntityStatus.COMPLETED.value
        assert "processing_error" not in updates

    @pytest.mark.asyncio
    async def test_bridge_failure_degrades_to_parser_only(self):
        # Non-checkbox prose so the bridge actually runs (a checkbox-only entry
        # would be stripped to empty and skip the bridge — see
        # test_checkbox_only_entry_skips_bridge).
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="some prose to tag")
        svc = _extract_entry_service(entry)

        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(
            return_value=Result.fail(Errors.integration(service="llm", message="rate limited"))
        )
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        dispatcher.dsl_bridge = bridge
        result = await dispatcher.process(entry)

        assert result.is_ok
        # Extraction still ran, over the ORIGINAL text.
        kwargs = extractor.extract_and_create.await_args.kwargs
        assert kwargs["content_override"] == entry.content
        # Degradation recorded, run completed.
        updates = svc.update_processing_state.await_args.args[1]
        assert "DSL bridge degraded to parser-only" in updates["processing_error"]
        assert updates["metadata"]["activity_extraction"]["status"] == "completed"
        assert "rate limited" in updates["metadata"]["activity_extraction"]["bridge_error"]

    @pytest.mark.asyncio
    async def test_bridge_success_appends_tagged_lines(self):
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="untagged prose")
        svc = _extract_entry_service(entry)

        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(
            return_value=Result.ok(
                DSLTransformResult(
                    original_text="untagged prose",
                    transformed_text="- @context(task) Call mom",
                    activity_lines=["- @context(task) Call mom"],
                )
            )
        )
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        dispatcher.dsl_bridge = bridge
        result = await dispatcher.process(entry)

        assert result.is_ok
        working = extractor.extract_and_create.await_args.kwargs["content_override"]
        assert working.startswith("untagged prose")
        assert "## Extracted Activities" in working
        assert "- @context(task) Call mom" in working

    @pytest.mark.asyncio
    async def test_checkbox_only_entry_skips_bridge(self):
        # Regression (Codex P1): a checkbox-only note leaves bridge_text empty
        # after the ADR-070 strip. The grounded transform_with_context prepends
        # the goal context BEFORE transform()'s blank check, so without this
        # guard an empty entry + active goals would call the LLM on just the goal
        # titles and could append @context lines extracted from the GOALS. The
        # bridge must be skipped entirely; the parser still runs over the
        # original checkbox text.
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- [ ] Call mom 🆔 sk_abc123")
        svc = _extract_entry_service(entry)

        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock()
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        g1 = MagicMock()
        g1.title = "Run a marathon"
        goals_service = MagicMock()
        goals_service.get_active = AsyncMock(return_value=Result.ok([g1]))

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        dispatcher.dsl_bridge = bridge
        dispatcher.goals_service = goals_service
        result = await dispatcher.process(entry)

        assert result.is_ok
        bridge.transform_with_context.assert_not_called()
        # Parser still runs over the ORIGINAL checkbox text.
        assert extractor.extract_and_create.await_args.kwargs["content_override"] == entry.content

    @pytest.mark.asyncio
    async def test_bridge_pre_pass_is_grounded_in_active_goals(self):
        # Regression guard for the grounding asymmetry fix: the entity-creating
        # EXTRACT_ACTIVITIES pre-pass must call the CONTEXT-aware bridge entry
        # grounded in the user's active goals — the same grounding the inert
        # journal "Suggested activities" preview uses — not bare transform().
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="finish the marathon plan")
        svc = _extract_entry_service(entry)

        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(return_value=Result.ok(_dsl_result_empty()))
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        g1 = MagicMock()
        g1.title = "Run a marathon"
        goals_service = MagicMock()
        goals_service.get_active = AsyncMock(return_value=Result.ok([g1]))

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        dispatcher.dsl_bridge = bridge
        dispatcher.goals_service = goals_service
        result = await dispatcher.process(entry)

        assert result.is_ok
        goals_service.get_active.assert_awaited_once_with("user_1", limit=10)
        _, kwargs = bridge.transform_with_context.call_args
        assert kwargs["active_goals"] == [{"title": "Run a marathon"}]

    @pytest.mark.asyncio
    async def test_bridge_pre_pass_ungrounded_without_goals_service(self):
        # No goals service wired (e.g. a slimmer compose): grounding degrades to
        # None, the bridge still runs context-aware (just ungrounded), the run
        # never fails on the missing soft signal.
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="finish the marathon plan")
        svc = _extract_entry_service(entry)

        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(return_value=Result.ok(_dsl_result_empty()))
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        dispatcher.dsl_bridge = bridge
        dispatcher.goals_service = None
        result = await dispatcher.process(entry)

        assert result.is_ok
        _, kwargs = bridge.transform_with_context.call_args
        assert kwargs["active_goals"] is None

    @pytest.mark.asyncio
    async def test_curriculum_gate_threads_fail_closed(self):
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- @context(ku) X")
        svc = _extract_entry_service(entry)
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        # No user_service at all → gate stays closed.
        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        result = await dispatcher.process(entry)

        assert result.is_ok
        kwargs = extractor.extract_and_create.await_args.kwargs
        assert kwargs["allow_curriculum_creation"] is False

    @pytest.mark.asyncio
    async def test_existing_hashes_are_read_and_threaded(self):
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- @context(task) X")
        svc = _extract_entry_service(entry)
        svc.get_extracted_entities = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "entity_uid": "task_prior",
                        "title": " Prior  Task ",
                        "labels": ["Entity", "Task"],
                        "source_line_hash": "abc",
                        "vault_id": None,
                    },
                    {
                        "entity_uid": "task_no_hash",
                        "title": "",
                        "labels": ["Entity", "Task"],
                        "source_line_hash": "",
                        "vault_id": None,
                    },
                ]
            )
        )
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        result = await dispatcher.process(entry)

        assert result.is_ok
        kwargs = extractor.extract_and_create.await_args.kwargs
        assert kwargs["existing_line_hashes"] == frozenset({"abc"})
        # Guard 3 (R3): the semantic map is built from the same read —
        # normalized title keyed by node label; the title-less row is skipped.
        assert kwargs["existing_extracted"] == {("Task", "prior task"): "task_prior"}

    @pytest.mark.asyncio
    async def test_user_owned_twins_are_read_and_threaded(self):
        """Guard 4 (cross-entry, F4): the user-wide active-twin map is built
        oldest-first (setdefault keeps the F4 winner) and handed to the
        extractor."""
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- @context(task) X")
        svc = _extract_entry_service(entry)
        svc.get_user_active_extraction_twins = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "entity_uid": "task_oldest",
                        "title": " Reflect  Daily ",
                        "labels": ["Entity", "Task"],
                    },
                    {
                        "entity_uid": "task_newer_twin",
                        "title": "reflect daily",
                        "labels": ["Entity", "Task"],
                    },
                    {"entity_uid": "task_untitled", "title": "", "labels": ["Entity", "Task"]},
                ]
            )
        )
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid))
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        result = await dispatcher.process(entry)

        assert result.is_ok
        kwargs = extractor.extract_and_create.await_args.kwargs
        assert kwargs["user_owned_semantic"] == {("Task", "reflect daily"): "task_oldest"}

    @pytest.mark.asyncio
    async def test_provenance_write_failure_fails_run(self):
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- @context(task) X")
        svc = _extract_entry_service(entry)
        svc.create_extracted_from_links = AsyncMock(
            return_value=Result.fail(Errors.database("create_extracted_from_links", "boom"))
        )
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(
                _extraction_result(entry.uid, created_links=[("task:1", "h", None)])
            )
        )
        bus = MagicMock()
        captured: list[Any] = []

        async def _publish(event: Any) -> None:
            captured.append(event)

        bus.publish_async = AsyncMock(side_effect=_publish)

        dispatcher = _make_dispatcher(entry_service=svc, event_bus=bus)
        dispatcher.activity_extractor = extractor
        result = await dispatcher.process(entry)

        assert result.is_error
        failed = [e for e in captured if e.event_type == "user_entry.processing_failed"]
        assert len(failed) == 1
        assert failed[0].failed_phase == "persist_links"

    @pytest.mark.asyncio
    async def test_ku_edge_failure_is_recorded_not_fatal(self):
        entry = _make_entry(Pipeline.EXTRACT_ACTIVITIES, content="- @context(task) X")
        svc = _extract_entry_service(entry)
        svc.add_relationship = AsyncMock(
            return_value=Result.fail(Errors.validation("Invalid relationship type"))
        )
        extractor = MagicMock()
        extractor.extract_and_create = AsyncMock(
            return_value=Result.ok(_extraction_result(entry.uid, referenced_ku_uids=["ku:typo/x"]))
        )

        dispatcher = _make_dispatcher(entry_service=svc)
        dispatcher.activity_extractor = extractor
        result = await dispatcher.process(entry)

        assert result.is_ok
        updates = svc.update_processing_state.await_args.args[1]
        link_errors = updates["metadata"]["activity_extraction"]["link_errors"]
        assert len(link_errors) == 1
        assert "ku:typo/x" in link_errors[0]


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
