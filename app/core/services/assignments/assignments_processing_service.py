"""
Assignment Processor Service
============================

Orchestrates processing of submitted assignments.

Routes assignments to appropriate processors:
- Audio files → TranscriptionService → LLM formatting → Activity Extraction
- Text files → Direct LLM processing → Activity Extraction
- PDFs → OCR → LLM extraction (future)
- Images → Vision API → LLM analysis (future)
- Manual review → Human review queue (future)

This service is a facade that coordinates existing processors.

**Activity Extraction (DSL Integration):**

When `extract_activities=True` in instructions, the processor will:
1. Parse processed content for Activity Lines (@context tags)
2. Create corresponding entities (Tasks, Habits, Goals, Events)
3. Store extraction results in assignment metadata

This transforms journals from passive records into active task managers.
"""

from typing import Any

from core.models.assignment.assignment import (
    Assignment,
    AssignmentStatus,
)
from core.services.assignments.assignments_submission_service import AssignmentSubmissionService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class AssignmentProcessorService:
    """
    Orchestrator service for assignment processing.

    Phase 1 Implementation:
    - Audio processing (transcription + LLM formatting)
    - Text processing (direct LLM formatting)
    - Status tracking throughout pipeline

    Future Enhancements:
    - PDF processing (OCR + LLM extraction)
    - Image processing (Vision API + LLM analysis)
    - Video processing (transcription + scene analysis)
    - Human review queue and workflow
    - Retry logic and error recovery


    Source Tag: "assignment_processor_explicit"
    - Format: "assignment_processor_explicit" for user-created relationships
    - Format: "assignment_processor_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        assignment_service: AssignmentSubmissionService,
        transcription_service=None,  # TranscriptionService (simplified, Dec 2025)
        transcript_processor=None,  # TranscriptProcessorService (for LLM processing)
        assignment_relationship_service=None,  # AssignmentRelationshipService (Option A)
        activity_extractor=None,  # JournalActivityExtractorService (DSL extraction)
        event_bus=None,
    ) -> None:
        """
        Initialize assignment processor service.

        Args:
            assignment_service: AssignmentSubmissionService for status updates
            transcription_service: TranscriptionService for audio transcription (simplified)
            transcript_processor: TranscriptProcessorService for LLM formatting
            assignment_relationship_service: AssignmentRelationshipService for graph relationships (Option A)
            activity_extractor: JournalActivityExtractorService for DSL-based entity extraction
            event_bus: Event bus for domain events (optional)
        """
        self.assignment_service = assignment_service
        self.transcription_service = transcription_service
        self.transcript_processor = transcript_processor
        self.assignment_relationship_service = assignment_relationship_service
        self.activity_extractor = activity_extractor
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.assignment_processor")

    # ========================================================================
    # MAIN PROCESSING ENTRY POINT
    # ========================================================================

    async def process_assignment(
        self, assignment_uid: str, instructions: dict[str, Any] | None = None
    ) -> Result[Assignment]:
        """
        Process an assignment using appropriate processor.

        Routes to processor based on:
        1. Assignment type (journal, transcript, report, etc.)
        2. File type (audio, text, pdf, image, video)
        3. Processor type (LLM, human, hybrid, automatic)

        Updates assignment status throughout:
        SUBMITTED → QUEUED → PROCESSING → COMPLETED (or FAILED)

        Args:
            assignment_uid: Assignment UID to process
            instructions: Processor-specific instructions (optional)

        Returns:
            Result containing processed assignment
        """
        # Get assignment
        assignment_result = await self.assignment_service.get_assignment(assignment_uid)

        if assignment_result.is_error:
            return Result.fail(assignment_result.expect_error())

        assignment = assignment_result.value
        if not assignment:
            return Result.fail(Errors.not_found("Assignment", assignment_uid))

        # Check if already processed
        if assignment.status in {AssignmentStatus.COMPLETED, AssignmentStatus.PROCESSING}:
            return Result.fail(
                Errors.validation(
                    message=f"Assignment already {assignment.status.value}",
                    field="status",
                    value=assignment.status.value,
                )
            )

        # Update status to QUEUED
        await self.assignment_service.update_assignment_status(
            assignment_uid, AssignmentStatus.QUEUED
        )

        # Route to appropriate processor
        try:
            result = await self._route_to_processor(assignment, instructions)

            if result.is_error:
                # Mark as failed
                await self.assignment_service.update_assignment_status(
                    assignment_uid,
                    AssignmentStatus.FAILED,
                    error_message=result.error.user_message
                    if result.error
                    else "Processing failed",
                )
                return result

            # Mark as completed
            await self.assignment_service.update_assignment_status(
                assignment_uid, AssignmentStatus.COMPLETED
            )

            # Get updated assignment
            updated_result = await self.assignment_service.get_assignment(assignment_uid)
            if updated_result.is_error:
                return Result.fail(updated_result.expect_error())
            if not updated_result.value:
                return Result.fail(Errors.not_found("Assignment", assignment_uid))
            return Result.ok(updated_result.value)

        except Exception as e:
            self.logger.error(
                f"Unexpected error processing assignment {assignment_uid}: {e}", exc_info=True
            )

            # Mark as failed
            await self.assignment_service.update_assignment_status(
                assignment_uid, AssignmentStatus.FAILED, error_message=str(e)
            )

            return Result.fail(
                Errors.system(
                    message=f"Processing failed: {e!s}", operation="process_assignment", exception=e
                )
            )

    # ========================================================================
    # PROCESSOR ROUTING
    # ========================================================================

    async def _route_to_processor(
        self, assignment: Assignment, instructions: dict[str, Any] | None
    ) -> Result[Assignment]:
        """
        Route assignment to appropriate processor based on type and file type.

        Routing logic:
        - Audio files → Audio processor
        - Text files → Text processor
        - Other types → Error (not yet implemented)

        Args:
            assignment: Assignment to process
            instructions: Processor-specific instructions

        Returns:
            Result containing processed assignment
        """
        # Update status to PROCESSING
        await self.assignment_service.update_assignment_status(
            assignment.uid, AssignmentStatus.PROCESSING
        )

        # Route based on file type
        file_type = assignment.file_type.lower()

        if file_type.startswith("audio/"):
            return await self._process_audio(assignment, instructions)

        if file_type.startswith("text/"):
            return await self._process_text(assignment, instructions)

        # Unsupported type
        return Result.fail(
            Errors.validation(
                message=f"File type not yet supported: {assignment.file_type}",
                field="file_type",
                value=assignment.file_type,
            )
        )

    # ========================================================================
    # AUDIO PROCESSING
    # ========================================================================

    async def _process_audio(
        self, assignment: Assignment, instructions: dict[str, Any] | None
    ) -> Result[Assignment]:
        """
        Process audio file: transcribe + LLM formatting.

        Pipeline:
        1. TranscriptionService.create() + process()
        2. TranscriptProcessorService.process_transcript() (if journal type)
        3. Update assignment with processed content

        Args:
            assignment: Assignment with audio file
            instructions: Optional processing instructions

        Returns:
            Result containing processed assignment
        """
        if not self.transcription_service:
            return Result.fail(
                Errors.system(
                    message="Audio processing not available (transcription service not configured)",
                    operation="process_audio",
                )
            )

        self.logger.info(f"Processing audio assignment: {assignment.uid}")

        # Step 1: Create transcription record
        from core.models.transcription.transcription import TranscriptionCreateRequest

        create_request = TranscriptionCreateRequest(
            audio_file_path=assignment.file_path,
            original_filename=assignment.original_filename,
        )
        create_result = await self.transcription_service.create(create_request, assignment.user_uid)

        if create_result.is_error:
            return create_result

        # Step 2: Process with Deepgram
        transcription_uid = create_result.value.uid
        process_result = await self.transcription_service.process(transcription_uid)

        if process_result.is_error:
            return process_result

        transcription = process_result.value
        transcript_text = transcription.transcript_text

        self.logger.info(f"Audio transcribed: {assignment.uid} ({len(transcript_text)} chars)")

        # NOTE (January 2026): Journal-specific LLM processing REMOVED.
        # Journals are now a separate domain with their own processing pipeline.
        # Assignments get the raw transcript as processed content.
        # See: core/services/journals_core_service.py for journal processing

        processed_content = transcript_text

        # Update assignment with processed content (raw transcript)
        return await self.assignment_service.update_processed_content(
            uid=assignment.uid, processed_content=processed_content
        )

    # ========================================================================
    # TEXT PROCESSING
    # ========================================================================

    async def _process_text(
        self, assignment: Assignment, instructions: dict[str, Any] | None
    ) -> Result[Assignment]:
        """
        Process text file: read content and store.

        Pipeline:
        1. Read text file content
        2. Update assignment with processed content

        NOTE (January 2026): Journal-specific LLM processing REMOVED.
        Journals are now a separate domain with their own processing pipeline.
        See: core/services/journals_core_service.py

        Args:
            assignment: Assignment with text file
            instructions: Optional processing instructions (unused after domain separation)

        Returns:
            Result containing processed assignment
        """
        _ = instructions  # Unused after journal domain separation

        self.logger.info(f"Processing text assignment: {assignment.uid}")

        # Step 1: Read text content
        file_content_result = await self.assignment_service.get_file_content(assignment.uid)

        if file_content_result.is_error:
            return Result.fail(file_content_result.expect_error())

        text_content = file_content_result.value.decode("utf-8")

        # Step 2: Update assignment with processed content (raw text)
        return await self.assignment_service.update_processed_content(
            uid=assignment.uid, processed_content=text_content
        )

    # ========================================================================
    # ACTIVITY EXTRACTION (DSL Integration)
    # ========================================================================

    async def _extract_activities(
        self, assignment: Assignment, user_uid: str, instructions: dict[str, Any] | None
    ) -> None:
        """
        Extract Activity Lines from processed content and create entities.

        This step integrates the SKUEL DSL parser to transform journals
        from passive records into active task managers.

        Activity Lines are markdown lines with @context() tags:
        ```
        - [ ] Call mom @context(task) @priority(1)
        - [ ] Morning meditation @context(habit) @duration(20m)
        ```

        Args:
            assignment: Processed assignment with content
            user_uid: User UID for entity ownership
            instructions: Processing instructions (may contain extraction options)
        """
        self.logger.info(f"Extracting activities from assignment {assignment.uid}")

        try:
            # Extract and create entities
            result = await self.activity_extractor.extract_and_create(
                assignment=assignment,
                user_uid=user_uid,
                create_relationships=instructions.get("create_activity_relationships", True)
                if instructions
                else True,
            )

            if result.is_ok:
                extraction = result.value
                self.logger.info(
                    f"Activity extraction complete for {assignment.uid}: "
                    f"found {extraction.activities_found} activities, "
                    f"created {extraction.total_created} entities "
                    f"(tasks={extraction.tasks_created}, habits={extraction.habits_created}, "
                    f"goals={extraction.goals_created}, events={extraction.events_created})"
                )

                if extraction.has_errors:
                    self.logger.warning(
                        f"Activity extraction had errors for {assignment.uid}: "
                        f"{len(extraction.parse_errors)} parse errors, "
                        f"{len(extraction.creation_errors)} creation errors"
                    )
            else:
                self.logger.warning(
                    f"Activity extraction failed for {assignment.uid}: {result.error}"
                )

        except Exception as e:
            # Activity extraction failure should not fail the entire processing
            self.logger.error(
                f"Unexpected error during activity extraction for {assignment.uid}: {e}",
                exc_info=True,
            )

    # ========================================================================
    # REPROCESSING
    # ========================================================================

    async def reprocess_assignment(
        self, assignment_uid: str, new_instructions: dict[str, Any] | None = None
    ) -> Result[Assignment]:
        """
        Reprocess an existing assignment with new instructions.

        Resets status to SUBMITTED and processes again.

        Args:
            assignment_uid: Assignment UID
            new_instructions: New processing instructions

        Returns:
            Result containing reprocessed assignment
        """
        # Reset status to SUBMITTED
        await self.assignment_service.update_assignment_status(
            assignment_uid, AssignmentStatus.SUBMITTED
        )

        # Process with new instructions
        return await self.process_assignment(assignment_uid, new_instructions)


# Backward compatibility alias
ProcessingPipelineService = AssignmentProcessorService
