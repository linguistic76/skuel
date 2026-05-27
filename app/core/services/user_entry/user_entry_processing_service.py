"""
UserEntryProcessingService — ADR-054 Commit 1 (cosmic-kindling-papert)
=======================================================================

Pipeline dispatcher for ``UserEntry``. Reads ``entry.pipeline`` and routes
to the matching processor:

    Pipeline.NONE                     → no-op (already complete)
    Pipeline.TEACHER_REVIEW           → no-op (waits on teacher queue)
    Pipeline.TRANSCRIBE               → Deepgram audio → transcript
    Pipeline.LLM_SUMMARY              → LLM summarization of text/processed content
    Pipeline.TRANSCRIBE_AND_STRUCTURE → transcribe + LLM structuring (two entries)

TRANSCRIBE_AND_STRUCTURE produces a second ``UserEntry`` carrying the
LLM-structured output, linked back to the source with a ``TRANSFORMS``
edge (wired via ``UserEntryCreateRequest.transforms_of_uid`` on the
facade).

ADR-054: activity extraction from journals dropped; create Tasks/Goals directly.

See: /home/mike/.claude/plans/cosmic-kindling-papert.md
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.user_entry_events import (
    UserEntryProcessingCompleted,
    UserEntryProcessingFailed,
    UserEntryProcessingStarted,
)
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import EnrichmentMode
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.utils.exception_types import FILE_IO_EXCEPTIONS, LLM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.transcription_protocols import TranscriptionPort
    from core.services.llm_caller import UnifiedLLMCaller
    from core.services.output.instruction_resolver import InstructionResolver
    from core.services.user_entry.user_entry_service import UserEntryService


class UserEntryProcessingService:
    """Pipeline dispatcher for ``UserEntry``.

    Composes ``UserEntryService`` with the transcription and LLM
    adapters so every pipeline branch can run without routing through
    the legacy ``SubmissionsProcessingService`` / ``JournalOutputService``.
    """

    def __init__(
        self,
        entry_service: UserEntryService,
        transcription_adapter: TranscriptionPort | None = None,
        llm_caller: UnifiedLLMCaller | None = None,
        instruction_resolver: InstructionResolver | None = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.entry_service = entry_service
        self.transcription_adapter = transcription_adapter
        self.llm_caller = llm_caller
        self.instruction_resolver = instruction_resolver
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.user_entry.processing")

    # =========================================================================
    # DISPATCH
    # =========================================================================

    async def process(
        self,
        entry: UserEntry,
        instructions: str | None = None,
    ) -> Result[UserEntry]:
        """Run ``entry.pipeline`` on ``entry``.

        Args:
            entry: The UserEntry to process.
            instructions: Per-run override for pipeline instructions
                (e.g., custom LLM prompt). Falls back to ``entry.instructions``.

        Returns:
            Result[UserEntry] — the (possibly updated) entry.
        """
        pipeline = entry.pipeline

        if pipeline == Pipeline.NONE or pipeline == Pipeline.TEACHER_REVIEW:
            return Result.ok(entry)

        await self._emit_started(entry)

        if pipeline == Pipeline.TRANSCRIBE:
            return await self._run_transcribe(entry)

        if pipeline == Pipeline.LLM_SUMMARY:
            return await self._run_llm_summary(entry, instructions)

        if pipeline == Pipeline.TRANSCRIBE_AND_STRUCTURE:
            return await self._run_transcribe_and_structure(entry, instructions)

        return Result.fail(
            Errors.validation(
                f"Unknown pipeline: {pipeline}",
                field="pipeline",
            )
        )

    # =========================================================================
    # TRANSCRIBE
    # =========================================================================

    async def _run_transcribe(self, entry: UserEntry) -> Result[UserEntry]:
        if self.transcription_adapter is None:
            return await self._fail(
                entry,
                Errors.integration(
                    service="deepgram",
                    message="DeepgramAdapter not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )
        if not entry.file_path:
            return await self._fail(
                entry,
                Errors.validation(
                    "TRANSCRIBE pipeline requires entry.file_path",
                    field="file_path",
                ),
                phase="setup",
            )

        transcript = await self._transcribe(entry.file_path)
        if transcript.is_error:
            return await self._fail(entry, transcript.expect_error(), phase="transcribe")

        update_result = await self.entry_service.update_processed_content(
            uid=entry.uid,
            processed_content=transcript.value,
        )
        if update_result.is_error:
            return await self._fail(entry, update_result.expect_error(), phase="persist_transcript")

        updated = update_result.value
        await self._emit_completed(updated)
        return Result.ok(updated)

    # =========================================================================
    # LLM_SUMMARY
    # =========================================================================

    async def _run_llm_summary(
        self,
        entry: UserEntry,
        instructions: str | None,
    ) -> Result[UserEntry]:
        if self.llm_caller is None:
            return await self._fail(
                entry,
                Errors.business(
                    rule="llm_tier_required",
                    message=(
                        "Pipeline.LLM_SUMMARY requires INTELLIGENCE_TIER=full; "
                        "UnifiedLLMCaller is not configured."
                    ),
                ),
                phase="setup",
            )
        if self.instruction_resolver is None:
            return await self._fail(
                entry,
                Errors.system(
                    message="InstructionResolver not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )

        source_text = entry.processed_content or entry.content
        if not source_text:
            return await self._fail(
                entry,
                Errors.validation(
                    "LLM_SUMMARY pipeline requires entry.content or entry.processed_content",
                    field="content",
                ),
                phase="setup",
            )

        llm_result = await self._generate(
            source_text,
            custom_instructions=instructions or entry.instructions,
            enrichment_mode=self._resolve_enrichment_mode(entry),
        )
        if llm_result.is_error:
            return await self._fail(entry, llm_result.expect_error(), phase="generate_summary")

        update_result = await self.entry_service.update_processed_content(
            uid=entry.uid,
            processed_content=llm_result.value,
        )
        if update_result.is_error:
            return await self._fail(entry, update_result.expect_error(), phase="persist_summary")

        updated = update_result.value
        await self._emit_completed(updated)
        return Result.ok(updated)

    # =========================================================================
    # TRANSCRIBE_AND_STRUCTURE
    # =========================================================================

    async def _run_transcribe_and_structure(
        self,
        entry: UserEntry,
        instructions: str | None,
    ) -> Result[UserEntry]:
        if self.transcription_adapter is None:
            return await self._fail(
                entry,
                Errors.integration(
                    service="deepgram",
                    message="DeepgramAdapter not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )
        if self.llm_caller is None:
            return await self._fail(
                entry,
                Errors.business(
                    rule="llm_tier_required",
                    message=(
                        "Pipeline.TRANSCRIBE_AND_STRUCTURE requires INTELLIGENCE_TIER=full; "
                        "UnifiedLLMCaller is not configured."
                    ),
                ),
                phase="setup",
            )
        if self.instruction_resolver is None:
            return await self._fail(
                entry,
                Errors.system(
                    message="InstructionResolver not configured for UserEntryProcessingService",
                ),
                phase="setup",
            )
        if not entry.file_path:
            return await self._fail(
                entry,
                Errors.validation(
                    "TRANSCRIBE_AND_STRUCTURE pipeline requires entry.file_path",
                    field="file_path",
                ),
                phase="setup",
            )

        # Phase 1 — transcribe and store on the source entry
        transcript = await self._transcribe(entry.file_path)
        if transcript.is_error:
            return await self._fail(entry, transcript.expect_error(), phase="transcribe")

        update_source = await self.entry_service.update_processed_content(
            uid=entry.uid,
            processed_content=transcript.value,
        )
        if update_source.is_error:
            return await self._fail(entry, update_source.expect_error(), phase="update_source")
        updated_source = update_source.value

        # Phase 2 — LLM-structure the transcript
        structured = await self._generate(
            transcript.value,
            custom_instructions=instructions or entry.instructions,
            enrichment_mode=self._resolve_enrichment_mode(entry),
        )
        if structured.is_error:
            return await self._fail(updated_source, structured.expect_error(), phase="structure")

        # Phase 3 — persist the structured output as a second UserEntry.
        #
        # The child is PRIVATE and inherits no audience from the source
        # (ADR-054 §5: journal is private by policy; see
        # Pipeline.allows_sharing). The source itself is already on
        # pipeline=TRANSCRIBE_AND_STRUCTURE, so _validate_audience blocked
        # any explicit audience at submit time — the child is anchored to
        # the same norm rather than drifting to the default visibility.
        child_request = UserEntryCreateRequest(
            title=f"{entry.title} — structured",
            content=structured.value,
            pipeline=Pipeline.NONE,
            modality=entry.modality,
            transforms_of_uid=entry.uid,
            visibility=Visibility.PRIVATE,
            tags=list(entry.tags) if entry.tags else [],
        )
        child_result = await self.entry_service.create_entry(
            request=child_request,
            user_uid=entry.user_uid,
        )
        if child_result.is_error:
            return await self._fail(
                updated_source, child_result.expect_error(), phase="persist_child"
            )

        child, _share_outcome = child_result.value
        await self._emit_completed(updated_source, produced_entry_uid=child.uid)
        return Result.ok(updated_source)

    # =========================================================================
    # ADAPTER WRAPPERS
    # =========================================================================

    async def _transcribe(self, file_path: str) -> Result[str]:
        """Call Deepgram adapter, narrowing exceptions to the expected set."""
        assert self.transcription_adapter is not None
        try:
            result = await self.transcription_adapter.transcribe(audio_path=file_path)
        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(message=f"Audio file read failed: {e}", service="user_entry")
            )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.transcript_text)

    async def _generate(
        self,
        content: str,
        custom_instructions: str | None,
        enrichment_mode: EnrichmentMode,
    ) -> Result[str]:
        """Resolve an instruction template and call the LLM."""
        assert self.llm_caller is not None
        assert self.instruction_resolver is not None

        instruction_result = self.instruction_resolver.resolve(
            enrichment_mode=enrichment_mode,
            custom_instructions=custom_instructions,
        )
        if instruction_result.is_error:
            return Result.fail(instruction_result)
        instruction = instruction_result.value

        prompt = instruction.prompt_text.replace("{content}", content)

        try:
            return await self.llm_caller.generate(
                prompt=prompt,
                model=instruction.model,
                temperature=instruction.temperature,
                max_tokens=instruction.max_tokens,
            )
        except LLM_EXCEPTIONS as e:
            return Result.fail(
                Errors.integration(
                    service="llm",
                    message=f"LLM call failed: {e}",
                )
            )

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _resolve_enrichment_mode(entry: UserEntry) -> EnrichmentMode:
        """Pull EnrichmentMode from entry metadata or fall back to default."""
        raw = (entry.metadata or {}).get("enrichment_mode") if entry.metadata else None
        if isinstance(raw, EnrichmentMode):
            return raw
        if isinstance(raw, str):
            try:
                return EnrichmentMode(raw)
            except ValueError:
                pass
        return EnrichmentMode.ACTIVITY_TRACKING

    async def _fail(
        self, entry: UserEntry, error: Any, phase: str | None = None
    ) -> Result[UserEntry]:
        """Mark the entry as FAILED, emit failure event, return Result.fail.

        ``phase`` is the stage of the pipeline where the failure occurred
        (``setup``, ``transcribe``, ``update_source``, ``structure``,
        ``persist_child``, ``generate_summary``, ``persist_summary``,
        ``persist_transcript``). Threaded onto the emitted
        ``UserEntryProcessingFailed`` event so postmortems can tell a
        Deepgram blip apart from an LLM blip inside a
        ``TRANSCRIBE_AND_STRUCTURE`` run without re-reading logs.
        """
        message = getattr(error, "message", None) or str(error)
        phase_tag = f" [phase={phase}]" if phase else ""
        self.logger.error(
            f"UserEntry pipeline {entry.pipeline.value}{phase_tag} failed "
            f"for {entry.uid}: {message}"
        )
        try:
            await self.entry_service.backend.update(
                entry.uid,
                {
                    "processing_error": message,
                    "status": EntityStatus.FAILED.value,
                    "updated_at": datetime.now(),
                },
            )
        except Exception as update_exc:  # safety-net: failure-marking must not mask original error
            self.logger.warning(f"Failed to mark UserEntry {entry.uid} as FAILED: {update_exc}")

        if self.event_bus is not None:
            await publish_event(
                self.event_bus,
                UserEntryProcessingFailed(
                    entity_uid=entry.uid,
                    user_uid=entry.user_uid,
                    pipeline=entry.pipeline.value,
                    error=message,
                    failed_phase=phase,
                ),
                self.logger,
            )
        return Result.fail(error)

    async def _emit_started(self, entry: UserEntry) -> None:
        if self.event_bus is None:
            return
        await publish_event(
            self.event_bus,
            UserEntryProcessingStarted(
                entity_uid=entry.uid,
                user_uid=entry.user_uid,
                pipeline=entry.pipeline.value,
            ),
            self.logger,
        )

    async def _emit_completed(
        self,
        entry: UserEntry,
        produced_entry_uid: str | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        await publish_event(
            self.event_bus,
            UserEntryProcessingCompleted(
                entity_uid=entry.uid,
                user_uid=entry.user_uid,
                pipeline=entry.pipeline.value,
                produced_entry_uid=produced_entry_uid,
            ),
            self.logger,
        )
