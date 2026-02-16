"""
Ku Processing Service
========================

Orchestrates processing of submitted Ku (assignments, journals, etc.).

Routes Ku to appropriate processors:
- Audio files -> TranscriptionService -> LLM formatting -> Activity Extraction
- Text files -> Direct LLM processing -> Activity Extraction
- PDFs -> OCR -> LLM extraction (future)
- Images -> Vision API -> LLM analysis (future)

**Activity Extraction (DSL Integration):**

When `extract_activities=True` in instructions, the processor will:
1. Parse processed content for Activity Lines (@context tags)
2. Create corresponding entities (Tasks, Habits, Goals, Events)
3. Store extraction results in Ku metadata
"""

from typing import Any

from core.models.enums.ku_enums import KuStatus, KuType
from core.models.ku import Ku
from core.services.reports.reports_submission_service import KuSubmissionService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class KuProcessingService:
    """
    Orchestrator service for Ku processing.

    Routes submitted Ku through appropriate processing pipelines
    based on file type and Ku configuration.
    """

    def __init__(
        self,
        ku_submission_service: KuSubmissionService,
        transcription_service=None,
        content_enrichment=None,
        ku_relationship_service=None,
        activity_extractor=None,
        journal_generator=None,
        event_bus=None,
    ) -> None:
        """
        Initialize Ku processing service.

        Args:
            ku_submission_service: KuSubmissionService for status updates
            transcription_service: TranscriptionService for audio transcription
            content_enrichment: ContentEnrichmentService for LLM formatting
            ku_relationship_service: KuRelationshipService for graph relationships
            activity_extractor: ReportActivityExtractorService for DSL-based entity extraction
            journal_generator: JournalOutputGenerator for je_output file generation
            event_bus: Event bus for domain events (optional)
        """
        self.ku_submission_service = ku_submission_service
        self.transcription_service = transcription_service
        self.content_enrichment = content_enrichment
        self.ku_relationship_service = ku_relationship_service
        self.activity_extractor = activity_extractor
        self.journal_generator = journal_generator
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ku_processing")

    # ========================================================================
    # MAIN PROCESSING ENTRY POINT
    # ========================================================================

    async def process_ku(
        self, ku_uid: str, instructions: dict[str, Any] | None = None
    ) -> Result[Ku]:
        """
        Process a Ku using appropriate processor.

        Routes to processor based on file type and configuration.
        Updates Ku status throughout:
        SUBMITTED -> QUEUED -> PROCESSING -> COMPLETED (or FAILED)

        Args:
            ku_uid: Ku UID to process
            instructions: Processor-specific instructions (optional)

        Returns:
            Result containing processed Ku
        """
        ku_result = await self.ku_submission_service.get_ku(ku_uid)

        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found("Ku", ku_uid))

        if ku.status in {KuStatus.COMPLETED, KuStatus.PROCESSING}:
            return Result.fail(
                Errors.validation(
                    message=f"Ku already {ku.status.value}",
                    field="status",
                    value=ku.status.value,
                )
            )

        # Update status to QUEUED
        await self.ku_submission_service.update_ku_status(ku_uid, KuStatus.QUEUED)

        try:
            result = await self._route_to_processor(ku, instructions)

            if result.is_error:
                await self.ku_submission_service.update_ku_status(
                    ku_uid,
                    KuStatus.FAILED,
                    error_message=result.error.user_message
                    if result.error
                    else "Processing failed",
                )
                return result

            # Mark as completed
            await self.ku_submission_service.update_ku_status(ku_uid, KuStatus.COMPLETED)

            # Get updated Ku
            updated_result = await self.ku_submission_service.get_ku(ku_uid)
            if updated_result.is_error:
                return Result.fail(updated_result.expect_error())
            if not updated_result.value:
                return Result.fail(Errors.not_found("Ku", ku_uid))
            return Result.ok(updated_result.value)

        except Exception as e:
            self.logger.error(f"Unexpected error processing Ku {ku_uid}: {e}", exc_info=True)

            await self.ku_submission_service.update_ku_status(
                ku_uid, KuStatus.FAILED, error_message=str(e)
            )

            return Result.fail(
                Errors.system(
                    message=f"Processing failed: {e!s}", operation="process_ku", exception=e
                )
            )

    # ========================================================================
    # PROCESSOR ROUTING
    # ========================================================================

    async def _route_to_processor(self, ku: Ku, instructions: dict[str, Any] | None) -> Result[Ku]:
        """Route Ku to appropriate processor based on file type."""
        await self.ku_submission_service.update_ku_status(ku.uid, KuStatus.PROCESSING)

        if not ku.file_type:
            return Result.fail(Errors.validation("Cannot process Ku without file_type"))
        file_type = ku.file_type.lower()

        if file_type.startswith("audio/"):
            return await self._process_audio(ku, instructions)

        if file_type.startswith("text/"):
            return await self._process_text(ku, instructions)

        return Result.fail(
            Errors.validation(
                message=f"File type not yet supported: {ku.file_type}",
                field="file_type",
                value=ku.file_type,
            )
        )

    # ========================================================================
    # AUDIO PROCESSING
    # ========================================================================

    async def _process_audio(self, ku: Ku, instructions: dict[str, Any] | None) -> Result[Ku]:
        """
        Process audio file: transcribe + LLM formatting.

        Pipeline:
        1. TranscriptionService.create() + process()
        2. Journal processing if metadata indicates journal type
        3. Update Ku with processed content
        """
        if not self.transcription_service:
            return Result.fail(
                Errors.system(
                    message="Audio processing not available (transcription service not configured)",
                    operation="process_audio",
                )
            )

        self.logger.info(f"Processing audio Ku: {ku.uid}")

        # Step 1: Create transcription record
        from core.models.transcription.transcription import TranscriptionCreateRequest

        create_request = TranscriptionCreateRequest(
            audio_file_path=ku.file_path,
            original_filename=ku.original_filename,
        )
        create_result = await self.transcription_service.create(create_request, ku.user_uid)

        if create_result.is_error:
            return create_result

        # Step 2: Process with Deepgram
        transcription_uid = create_result.value.uid
        process_result = await self.transcription_service.process(transcription_uid)

        if process_result.is_error:
            return process_result

        transcription = process_result.value
        transcript_text = transcription.transcript_text

        self.logger.info(f"Audio transcribed: {ku.uid} ({len(transcript_text)} chars)")

        processed_content = transcript_text

        # Update Ku with processed content
        update_result = await self.ku_submission_service.update_processed_content(
            uid=ku.uid, processed_content=processed_content
        )

        if update_result.is_error:
            return update_result

        updated_ku = update_result.value

        # Check if journal processing is needed
        is_journal = ku.ku_type == KuType.JOURNAL

        if is_journal:
            await self._process_journal(updated_ku, transcript_text, instructions)
            refresh_result = await self.ku_submission_service.get_ku(ku.uid)
            if not refresh_result.is_error and refresh_result.value:
                updated_ku = refresh_result.value
        elif instructions and instructions.get("extract_activities", False):
            if self.activity_extractor:
                await self._extract_activities(updated_ku, ku.user_uid, instructions)
            else:
                self.logger.warning(
                    f"Activity extraction requested but extractor not configured for {ku.uid}"
                )

        return Result.ok(updated_ku)

    # ========================================================================
    # TEXT PROCESSING
    # ========================================================================

    async def _process_text(self, ku: Ku, instructions: dict[str, Any] | None) -> Result[Ku]:
        """
        Process text file: read content and store.

        Pipeline:
        1. Read text file content
        2. Update Ku with processed content
        """
        self.logger.info(f"Processing text Ku: {ku.uid}")

        # Step 1: Read text content
        file_content_result = await self.ku_submission_service.get_file_content(ku.uid)

        if file_content_result.is_error:
            return Result.fail(file_content_result.expect_error())

        text_content = file_content_result.value.decode("utf-8")

        # Step 2: Update Ku with processed content
        update_result = await self.ku_submission_service.update_processed_content(
            uid=ku.uid, processed_content=text_content
        )

        if update_result.is_error:
            return update_result

        updated_ku = update_result.value

        # Check if journal processing is needed
        is_journal = ku.ku_type == KuType.JOURNAL

        if is_journal:
            await self._process_journal(updated_ku, text_content, instructions)
            refresh_result = await self.ku_submission_service.get_ku(ku.uid)
            if not refresh_result.is_error and refresh_result.value:
                updated_ku = refresh_result.value
        elif instructions and instructions.get("extract_activities", False):
            if self.activity_extractor:
                await self._extract_activities(updated_ku, ku.user_uid, instructions)
            else:
                self.logger.warning(
                    f"Activity extraction requested but extractor not configured for {ku.uid}"
                )

        return Result.ok(updated_ku)

    # ========================================================================
    # JOURNAL PROCESSING
    # ========================================================================

    async def _process_journal(
        self, ku: Ku, content: str, instructions: dict[str, Any] | None
    ) -> None:
        """
        Process journal-type Ku with enrichment pipeline.

        Pipeline:
        1. Read enrichment_mode from instructions
        2. Generate formatted je_output file
        3. Extract activities if mode is activity_tracking
        4. Store enrichment_mode and je_output_path in metadata
        """
        if not self.journal_generator:
            self.logger.warning(
                f"Journal processing requested but generator not configured for {ku.uid}"
            )
            return

        # Step 1: Read enrichment mode from instructions
        enrichment_mode = instructions.get("enrichment_mode") if instructions else None

        self.logger.info(
            f"Processing journal Ku {ku.uid} (enrichment_mode: {enrichment_mode or 'activity_tracking'})"
        )

        # Step 2: Generate je_output file
        output_result = await self.journal_generator.generate(
            content=content,
            enrichment_mode=enrichment_mode,
            report_uid=ku.uid,
        )

        if output_result.is_error:
            self.logger.error(f"je_output generation failed: {output_result.error}")
            return

        je_output_path = output_result.value

        # Step 3: Extract activities if mode is activity_tracking (default)
        effective_mode = enrichment_mode or "activity_tracking"
        if effective_mode == "activity_tracking" and self.activity_extractor:
            self.logger.info(f"Extracting activities for {ku.uid}")
            await self._extract_activities(ku, ku.user_uid, instructions)

        # Step 4: Store journal processing metadata
        current_metadata = ku.metadata or {}
        current_metadata["enrichment_mode"] = effective_mode
        current_metadata["je_output_path"] = je_output_path

        await self.ku_submission_service.update_ku(
            uid=ku.uid,
            updates={"metadata": current_metadata},
        )

        self.logger.info(f"Journal processing complete: {ku.uid} - {effective_mode}")

    # ========================================================================
    # ACTIVITY EXTRACTION (DSL Integration)
    # ========================================================================

    async def _extract_activities(
        self, ku: Ku, user_uid: str, instructions: dict[str, Any] | None
    ) -> None:
        """
        Extract Activity Lines from processed content and create entities.

        Args:
            ku: Processed Ku with content
            user_uid: User UID for entity ownership
            instructions: Processing instructions
        """
        self.logger.info(f"Extracting activities from Ku {ku.uid}")

        try:
            result = await self.activity_extractor.extract_and_create(
                report=ku,
                user_uid=user_uid,
                create_relationships=instructions.get("create_activity_relationships", True)
                if instructions
                else True,
            )

            if result.is_ok:
                extraction = result.value
                self.logger.info(
                    f"Activity extraction complete for {ku.uid}: "
                    f"found {extraction.activities_found} activities, "
                    f"created {extraction.total_created} entities "
                    f"(tasks={extraction.tasks_created}, habits={extraction.habits_created}, "
                    f"goals={extraction.goals_created}, events={extraction.events_created})"
                )

                if extraction.has_errors:
                    self.logger.warning(
                        f"Activity extraction had errors for {ku.uid}: "
                        f"{len(extraction.parse_errors)} parse errors, "
                        f"{len(extraction.creation_errors)} creation errors"
                    )
            else:
                self.logger.warning(f"Activity extraction failed for {ku.uid}: {result.error}")

        except Exception as e:
            self.logger.error(
                f"Unexpected error during activity extraction for {ku.uid}: {e}",
                exc_info=True,
            )

    # ========================================================================
    # REPROCESSING
    # ========================================================================

    async def reprocess_ku(
        self, ku_uid: str, new_instructions: dict[str, Any] | None = None
    ) -> Result[Ku]:
        """
        Reprocess an existing Ku with new instructions.

        Resets status to SUBMITTED and processes again.

        Args:
            ku_uid: Ku UID
            new_instructions: New processing instructions

        Returns:
            Result containing reprocessed Ku
        """
        await self.ku_submission_service.update_ku_status(ku_uid, KuStatus.SUBMITTED)
        return await self.process_ku(ku_uid, new_instructions)
