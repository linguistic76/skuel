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

from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.submissions.journal import Journal
from core.models.submissions.submission import Submission
from core.services.submissions.submissions_service import SubmissionsService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class SubmissionsProcessingService:
    """
    Orchestrator service for Ku processing.

    Routes submitted Ku through appropriate processing pipelines
    based on file type and Ku configuration.
    """

    def __init__(
        self,
        ku_submission_service: SubmissionsService,
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
            ku_submission_service: SubmissionsService for status updates
            transcription_service: TranscriptionService for audio transcription
            content_enrichment: ContentEnrichmentService for LLM formatting
            ku_relationship_service: SubmissionsRelationshipService for graph relationships
            activity_extractor: ActivityExtractorService for DSL-based entity extraction
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

    async def process_submission(
        self, ku_uid: str, instructions: dict[str, Any] | None = None
    ) -> Result[Entity]:
        """
        Process an entity using appropriate processor.

        Routes to processor based on file type and configuration.
        Updates Ku status throughout:
        SUBMITTED -> QUEUED -> PROCESSING -> COMPLETED (or FAILED)

        Args:
            ku_uid: Submission UID to process
            instructions: Processor-specific instructions (optional)

        Returns:
            Result containing processed submission
        """
        submission_result = await self.ku_submission_service.get_submission(ku_uid)

        if submission_result.is_error:
            return Result.fail(submission_result.expect_error())

        submission = submission_result.value
        if not submission:
            return Result.fail(Errors.not_found("Submission", ku_uid))

        if not isinstance(submission, Submission):
            return Result.fail(
                Errors.validation(
                    message="Only submission-type entities can be processed",
                    field="entity_type",
                )
            )

        if submission.status in {EntityStatus.COMPLETED, EntityStatus.PROCESSING}:
            return Result.fail(
                Errors.validation(
                    message=f"Submission already {submission.status.value}",
                    field="status",
                    value=submission.status.value,
                )
            )

        # Update status to QUEUED
        await self.ku_submission_service.update_submission_status(ku_uid, EntityStatus.QUEUED)

        try:
            result = await self._route_to_processor(submission, instructions)

            if result.is_error:
                await self.ku_submission_service.update_submission_status(
                    ku_uid,
                    EntityStatus.FAILED,
                    error_message=result.error.user_message
                    if result.error
                    else "Processing failed",
                )
                return result

            # Mark as completed
            await self.ku_submission_service.update_submission_status(
                ku_uid, EntityStatus.COMPLETED
            )

            # Get updated entity
            updated_result = await self.ku_submission_service.get_submission(ku_uid)
            if updated_result.is_error:
                return Result.fail(updated_result.expect_error())
            if not updated_result.value:
                return Result.fail(Errors.not_found("Submission", ku_uid))
            return Result.ok(updated_result.value)

        except Exception as e:
            self.logger.error(
                f"Unexpected error processing submission {ku_uid}: {e}", exc_info=True
            )

            await self.ku_submission_service.update_submission_status(
                ku_uid, EntityStatus.FAILED, error_message=str(e)
            )

            return Result.fail(
                Errors.system(
                    message=f"Processing failed: {e!s}", operation="process_ku", exception=e
                )
            )

    # ========================================================================
    # PROCESSOR ROUTING
    # ========================================================================

    async def _route_to_processor(
        self, submission: Submission, instructions: dict[str, Any] | None
    ) -> Result[Entity]:
        """Route submission to appropriate processor based on file type."""
        await self.ku_submission_service.update_submission_status(
            submission.uid, EntityStatus.PROCESSING
        )

        if not submission.file_type:
            return Result.fail(Errors.validation("Cannot process submission without file_type"))
        file_type = submission.file_type.lower()

        if file_type.startswith("audio/"):
            return await self._process_audio(submission, instructions)

        if file_type.startswith("text/"):
            return await self._process_text(submission, instructions)

        return Result.fail(
            Errors.validation(
                message=f"File type not yet supported: {submission.file_type}",
                field="file_type",
                value=submission.file_type,
            )
        )

    # ========================================================================
    # AUDIO PROCESSING
    # ========================================================================

    async def _process_audio(
        self, submission: Submission, instructions: dict[str, Any] | None
    ) -> Result[Entity]:
        """
        Process audio file: transcribe + LLM formatting.

        Pipeline:
        1. TranscriptionService.create() + process()
        2. Journal processing if metadata indicates journal type
        3. Update entity with processed content
        """
        if not self.transcription_service:
            return Result.fail(
                Errors.system(
                    message="Audio processing not available (transcription service not configured)",
                    operation="process_audio",
                )
            )

        self.logger.info(f"Processing audio submission: {submission.uid}")

        # Step 1: Create transcription record
        from core.models.transcription.transcription import TranscriptionCreateRequest

        create_request = TranscriptionCreateRequest(
            audio_file_path=submission.file_path,
            original_filename=submission.original_filename,
        )
        create_result = await self.transcription_service.create(create_request, submission.user_uid)

        if create_result.is_error:
            return create_result

        # Step 2: Process with Deepgram
        transcription_uid = create_result.value.uid
        process_result = await self.transcription_service.process(transcription_uid)

        if process_result.is_error:
            return process_result

        transcription = process_result.value
        transcript_text = transcription.transcript_text

        self.logger.info(f"Audio transcribed: {submission.uid} ({len(transcript_text)} chars)")

        processed_content = transcript_text

        # Update entity with processed content
        update_result = await self.ku_submission_service.update_processed_content(
            uid=submission.uid, processed_content=processed_content
        )

        if update_result.is_error:
            return update_result

        updated_submission = update_result.value

        # Check if journal processing is needed
        is_journal = submission.entity_type == EntityType.JOURNAL

        if is_journal:
            await self._process_journal(updated_submission, transcript_text, instructions)
            refresh_result = await self.ku_submission_service.get_submission(submission.uid)
            if not refresh_result.is_error and refresh_result.value:
                updated_submission = refresh_result.value
        elif instructions and instructions.get("extract_activities", False):
            if self.activity_extractor:
                await self._extract_activities(
                    updated_submission, submission.user_uid, instructions
                )
            else:
                self.logger.warning(
                    f"Activity extraction requested but extractor not configured for {submission.uid}"
                )

        return Result.ok(updated_submission)

    # ========================================================================
    # TEXT PROCESSING
    # ========================================================================

    async def _process_text(
        self, submission: Submission, instructions: dict[str, Any] | None
    ) -> Result[Entity]:
        """
        Process text file: read content and store.

        Pipeline:
        1. Read text file content
        2. Update entity with processed content
        """
        self.logger.info(f"Processing text submission: {submission.uid}")

        # Step 1: Read text content
        file_content_result = await self.ku_submission_service.get_file_content(submission.uid)

        if file_content_result.is_error:
            return Result.fail(file_content_result.expect_error())

        text_content = file_content_result.value.decode("utf-8")

        # Step 2: Update entity with processed content
        update_result = await self.ku_submission_service.update_processed_content(
            uid=submission.uid, processed_content=text_content
        )

        if update_result.is_error:
            return update_result

        updated_submission = update_result.value

        # Check if journal processing is needed
        is_journal = submission.entity_type == EntityType.JOURNAL

        if is_journal:
            await self._process_journal(updated_submission, text_content, instructions)
            refresh_result = await self.ku_submission_service.get_submission(submission.uid)
            if not refresh_result.is_error and refresh_result.value:
                updated_submission = refresh_result.value
        elif instructions and instructions.get("extract_activities", False):
            if self.activity_extractor:
                await self._extract_activities(
                    updated_submission, submission.user_uid, instructions
                )
            else:
                self.logger.warning(
                    f"Activity extraction requested but extractor not configured for {submission.uid}"
                )

        return Result.ok(updated_submission)

    # ========================================================================
    # JOURNAL PROCESSING
    # ========================================================================

    async def _process_journal(
        self, submission: Journal, content: str, instructions: dict[str, Any] | None
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
                f"Journal processing requested but generator not configured for {submission.uid}"
            )
            return

        # Step 1: Read enrichment mode and custom instructions from instructions dict
        enrichment_mode = instructions.get("enrichment_mode") if instructions else None
        custom_instructions = instructions.get("custom_instructions") if instructions else None

        if custom_instructions:
            self.logger.info(
                f"Processing journal submission {submission.uid} with custom instructions"
            )
        else:
            self.logger.info(
                f"Processing journal submission {submission.uid} (enrichment_mode: {enrichment_mode or 'activity_tracking'})"
            )

        # Step 2: Generate je_output file
        output_result = await self.journal_generator.generate(
            content=content,
            enrichment_mode=enrichment_mode,
            report_uid=submission.uid,
            custom_instructions=custom_instructions,
        )

        if output_result.is_error:
            self.logger.error(f"je_output generation failed: {output_result.error}")
            return

        je_output_path = output_result.value

        # Step 3: Extract activities if mode is activity_tracking (default)
        effective_mode = enrichment_mode or "activity_tracking"
        if effective_mode == "activity_tracking" and self.activity_extractor:
            self.logger.info(f"Extracting activities for {submission.uid}")
            await self._extract_activities(submission, submission.user_uid, instructions)

        # Step 4: Store journal processing metadata
        current_metadata = submission.metadata or {}
        current_metadata["enrichment_mode"] = effective_mode
        current_metadata["je_output_path"] = je_output_path

        await self.ku_submission_service.update_submission(
            uid=submission.uid,
            updates={"metadata": current_metadata},
        )

        self.logger.info(f"Journal processing complete: {submission.uid} - {effective_mode}")

    # ========================================================================
    # ACTIVITY EXTRACTION (DSL Integration)
    # ========================================================================

    async def _extract_activities(
        self, submission: SubmissionEntity, user_uid: str, instructions: dict[str, Any] | None
    ) -> None:
        """
        Extract Activity Lines from processed content and create entities.

        Args:
            ku: Processed submission with content
            user_uid: User UID for entity ownership
            instructions: Processing instructions
        """
        self.logger.info(f"Extracting activities from submission {submission.uid}")

        try:
            result = await self.activity_extractor.extract_and_create(
                report=submission,
                user_uid=user_uid,
                create_relationships=instructions.get("create_activity_relationships", True)
                if instructions
                else True,
            )

            if result.is_ok:
                extraction = result.value
                self.logger.info(
                    f"Activity extraction complete for {submission.uid}: "
                    f"found {extraction.activities_found} activities, "
                    f"created {extraction.total_created} entities "
                    f"(tasks={extraction.tasks_created}, habits={extraction.habits_created}, "
                    f"goals={extraction.goals_created}, events={extraction.events_created})"
                )

                if extraction.has_errors:
                    self.logger.warning(
                        f"Activity extraction had errors for {submission.uid}: "
                        f"{len(extraction.parse_errors)} parse errors, "
                        f"{len(extraction.creation_errors)} creation errors"
                    )
            else:
                self.logger.warning(
                    f"Activity extraction failed for {submission.uid}: {result.error}"
                )

        except Exception as e:
            self.logger.error(
                f"Unexpected error during activity extraction for {submission.uid}: {e}",
                exc_info=True,
            )

    # ========================================================================
    # REPROCESSING
    # ========================================================================

    async def reprocess_submission(
        self, ku_uid: str, new_instructions: dict[str, Any] | None = None
    ) -> Result[Entity]:
        """
        Reprocess an existing Ku with new instructions.

        Resets status to SUBMITTED and processes again.

        Args:
            ku_uid: Ku UID
            new_instructions: New processing instructions

        Returns:
            Result containing reprocessed Ku
        """
        await self.ku_submission_service.update_submission_status(ku_uid, EntityStatus.SUBMITTED)
        return await self.process_submission(ku_uid, new_instructions)
