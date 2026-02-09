"""
Reports Processing Service
============================

Orchestrates processing of submitted reports.

Routes reports to appropriate processors:
- Audio files -> TranscriptionService -> LLM formatting -> Activity Extraction
- Text files -> Direct LLM processing -> Activity Extraction
- PDFs -> OCR -> LLM extraction (future)
- Images -> Vision API -> LLM analysis (future)
- Manual review -> Human review queue (future)

This service is a facade that coordinates existing processors.

**Activity Extraction (DSL Integration):**

When `extract_activities=True` in instructions, the processor will:
1. Parse processed content for Activity Lines (@context tags)
2. Create corresponding entities (Tasks, Habits, Goals, Events)
3. Store extraction results in report metadata

This transforms journals from passive records into active task managers.
"""

from typing import Any

from core.models.report.report import (
    Report,
    ReportStatus,
)
from core.services.reports.reports_submission_service import ReportSubmissionService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class ReportsProcessingService:
    """
    Orchestrator service for report processing.

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


    Source Tag: "report_processor_explicit"
    - Format: "report_processor_explicit" for user-created relationships
    - Format: "report_processor_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        report_service: ReportSubmissionService,
        transcription_service=None,  # TranscriptionService (simplified, Dec 2025)
        transcript_processor=None,  # TranscriptProcessorService (for LLM processing)
        report_relationship_service=None,  # ReportsRelationshipService (Option A)
        activity_extractor=None,  # ReportActivityExtractorService (DSL extraction)
        journal_classifier=None,  # JournalModeClassifier (LLM weight inference)
        journal_generator=None,  # JournalOutputGenerator (je_output formatting)
        event_bus=None,
    ) -> None:
        """
        Initialize reports processing service.

        Args:
            report_service: ReportSubmissionService for status updates
            transcription_service: TranscriptionService for audio transcription (simplified)
            transcript_processor: TranscriptProcessorService for LLM formatting
            report_relationship_service: ReportsRelationshipService for graph relationships (Option A)
            activity_extractor: ReportActivityExtractorService for DSL-based entity extraction
            journal_classifier: JournalModeClassifier for multi-modal weight inference
            journal_generator: JournalOutputGenerator for je_output file generation
            event_bus: Event bus for domain events (optional)
        """
        self.report_service = report_service
        self.transcription_service = transcription_service
        self.transcript_processor = transcript_processor
        self.report_relationship_service = report_relationship_service
        self.activity_extractor = activity_extractor
        self.journal_classifier = journal_classifier
        self.journal_generator = journal_generator
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.reports_processing")

    # ========================================================================
    # MAIN PROCESSING ENTRY POINT
    # ========================================================================

    async def process_report(
        self, report_uid: str, instructions: dict[str, Any] | None = None
    ) -> Result[Report]:
        """
        Process a report using appropriate processor.

        Routes to processor based on:
        1. Report type (journal, transcript, report, etc.)
        2. File type (audio, text, pdf, image, video)
        3. Processor type (LLM, human, hybrid, automatic)

        Updates report status throughout:
        SUBMITTED -> QUEUED -> PROCESSING -> COMPLETED (or FAILED)

        Args:
            report_uid: Report UID to process
            instructions: Processor-specific instructions (optional)

        Returns:
            Result containing processed report
        """
        # Get report
        report_result = await self.report_service.get_report(report_uid)

        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", report_uid))

        # Check if already processed
        if report.status in {ReportStatus.COMPLETED, ReportStatus.PROCESSING}:
            return Result.fail(
                Errors.validation(
                    message=f"Report already {report.status.value}",
                    field="status",
                    value=report.status.value,
                )
            )

        # Update status to QUEUED
        await self.report_service.update_report_status(report_uid, ReportStatus.QUEUED)

        # Route to appropriate processor
        try:
            result = await self._route_to_processor(report, instructions)

            if result.is_error:
                # Mark as failed
                await self.report_service.update_report_status(
                    report_uid,
                    ReportStatus.FAILED,
                    error_message=result.error.user_message
                    if result.error
                    else "Processing failed",
                )
                return result

            # Mark as completed
            await self.report_service.update_report_status(report_uid, ReportStatus.COMPLETED)

            # Get updated report
            updated_result = await self.report_service.get_report(report_uid)
            if updated_result.is_error:
                return Result.fail(updated_result.expect_error())
            if not updated_result.value:
                return Result.fail(Errors.not_found("Report", report_uid))
            return Result.ok(updated_result.value)

        except Exception as e:
            self.logger.error(
                f"Unexpected error processing report {report_uid}: {e}", exc_info=True
            )

            # Mark as failed
            await self.report_service.update_report_status(
                report_uid, ReportStatus.FAILED, error_message=str(e)
            )

            return Result.fail(
                Errors.system(
                    message=f"Processing failed: {e!s}", operation="process_report", exception=e
                )
            )

    # ========================================================================
    # PROCESSOR ROUTING
    # ========================================================================

    async def _route_to_processor(
        self, report: Report, instructions: dict[str, Any] | None
    ) -> Result[Report]:
        """
        Route report to appropriate processor based on type and file type.

        Routing logic:
        - Audio files -> Audio processor
        - Text files -> Text processor
        - Other types -> Error (not yet implemented)

        Args:
            report: Report to process
            instructions: Processor-specific instructions

        Returns:
            Result containing processed report
        """
        # Update status to PROCESSING
        await self.report_service.update_report_status(report.uid, ReportStatus.PROCESSING)

        # Route based on file type
        if not report.file_type:
            return Result.fail(Errors.validation("Cannot process report without file_type"))
        file_type = report.file_type.lower()

        if file_type.startswith("audio/"):
            return await self._process_audio(report, instructions)

        if file_type.startswith("text/"):
            return await self._process_text(report, instructions)

        # Unsupported type
        return Result.fail(
            Errors.validation(
                message=f"File type not yet supported: {report.file_type}",
                field="file_type",
                value=report.file_type,
            )
        )

    # ========================================================================
    # AUDIO PROCESSING
    # ========================================================================

    async def _process_audio(
        self, report: Report, instructions: dict[str, Any] | None
    ) -> Result[Report]:
        """
        Process audio file: transcribe + LLM formatting.

        Pipeline:
        1. TranscriptionService.create() + process()
        2. TranscriptProcessorService.process_transcript() (if journal type)
        3. Update report with processed content

        Args:
            report: Report with audio file
            instructions: Optional processing instructions

        Returns:
            Result containing processed report
        """
        if not self.transcription_service:
            return Result.fail(
                Errors.system(
                    message="Audio processing not available (transcription service not configured)",
                    operation="process_audio",
                )
            )

        self.logger.info(f"Processing audio report: {report.uid}")

        # Step 1: Create transcription record
        from core.models.transcription.transcription import TranscriptionCreateRequest

        create_request = TranscriptionCreateRequest(
            audio_file_path=report.file_path,
            original_filename=report.original_filename,
        )
        create_result = await self.transcription_service.create(create_request, report.user_uid)

        if create_result.is_error:
            return create_result

        # Step 2: Process with Deepgram
        transcription_uid = create_result.value.uid
        process_result = await self.transcription_service.process(transcription_uid)

        if process_result.is_error:
            return process_result

        transcription = process_result.value
        transcript_text = transcription.transcript_text

        self.logger.info(f"Audio transcribed: {report.uid} ({len(transcript_text)} chars)")

        # NOTE (January 2026): Journal-specific LLM processing REMOVED.
        # Journals are now a separate domain with their own processing pipeline.
        # Reports get the raw transcript as processed content.
        # See: core/services/journals_core_service.py for journal processing

        processed_content = transcript_text

        # Update report with processed content (raw transcript)
        update_result = await self.report_service.update_processed_content(
            uid=report.uid, processed_content=processed_content
        )

        if update_result.is_error:
            return update_result

        updated_report = update_result.value

        # Process journal if this is a JOURNAL type report
        if hasattr(report, "report_type"):
            from core.models.enums.report_enums import ReportType

            if report.report_type == ReportType.JOURNAL:
                await self._process_journal(updated_report, transcript_text, instructions)
                # Refresh report after journal processing
                refresh_result = await self.report_service.get_report(report.uid)
                if not refresh_result.is_error and refresh_result.value:
                    updated_report = refresh_result.value
        else:
            # Legacy path: Extract activities if enabled (DSL integration)
            if instructions and instructions.get("extract_activities", False):
                if self.activity_extractor:
                    await self._extract_activities(updated_report, report.user_uid, instructions)
                else:
                    self.logger.warning(
                        f"Activity extraction requested but extractor not configured for {report.uid}"
                    )

        return Result.ok(updated_report)

    # ========================================================================
    # TEXT PROCESSING
    # ========================================================================

    async def _process_text(
        self, report: Report, instructions: dict[str, Any] | None
    ) -> Result[Report]:
        """
        Process text file: read content and store.

        Pipeline:
        1. Read text file content
        2. Update report with processed content

        NOTE (January 2026): Journal-specific LLM processing REMOVED.
        Journals are now a separate domain with their own processing pipeline.
        See: core/services/journals_core_service.py

        Args:
            report: Report with text file
            instructions: Optional processing instructions (unused after domain separation)

        Returns:
            Result containing processed report
        """
        _ = instructions  # Unused after journal domain separation

        self.logger.info(f"Processing text report: {report.uid}")

        # Step 1: Read text content
        file_content_result = await self.report_service.get_file_content(report.uid)

        if file_content_result.is_error:
            return Result.fail(file_content_result.expect_error())

        text_content = file_content_result.value.decode("utf-8")

        # Step 2: Update report with processed content (raw text)
        update_result = await self.report_service.update_processed_content(
            uid=report.uid, processed_content=text_content
        )

        if update_result.is_error:
            return update_result

        updated_report = update_result.value

        # Process journal if this is a JOURNAL type report
        if hasattr(report, "report_type"):
            from core.models.enums.report_enums import ReportType

            if report.report_type == ReportType.JOURNAL:
                await self._process_journal(updated_report, text_content, instructions)
                # Refresh report after journal processing
                refresh_result = await self.report_service.get_report(report.uid)
                if not refresh_result.is_error and refresh_result.value:
                    updated_report = refresh_result.value
        else:
            # Legacy path: Extract activities if enabled (DSL integration)
            if instructions and instructions.get("extract_activities", False):
                if self.activity_extractor:
                    await self._extract_activities(updated_report, report.user_uid, instructions)
                else:
                    self.logger.warning(
                        f"Activity extraction requested but extractor not configured for {report.uid}"
                    )

        return Result.ok(updated_report)

    # ========================================================================
    # JOURNAL PROCESSING (Multi-Modal)
    # ========================================================================

    async def _process_journal(
        self, report: Report, content: str, instructions: dict[str, Any] | None
    ) -> None:
        """
        Process JOURNAL type report with multi-modal pipeline.

        Pipeline:
        1. Infer mode weights (activity, articulation, exploration)
        2. Generate formatted je_output file
        3. Extract activities if weight > threshold
        4. Store weights and je_output_path in metadata

        Args:
            report: Report with processed_content
            content: Raw content for classification
            instructions: Processing instructions (may contain mode threshold)
        """
        if not self.journal_classifier or not self.journal_generator:
            self.logger.warning(
                f"Journal processing requested but services not configured for {report.uid}"
            )
            return

        self.logger.info(f"Processing journal {report.uid} with multi-modal pipeline")

        # Step 1: Infer mode weights
        user_declared_mode = instructions.get("journal_mode") if instructions else None
        weights_result = await self.journal_classifier.infer_weights(
            content, user_declared_mode=user_declared_mode
        )

        if weights_result.is_error:
            self.logger.error(f"Weight inference failed: {weights_result.error}")
            return

        weights = weights_result.value
        threshold = (
            self.journal_classifier.get_threshold_from_instructions(instructions)
            if self.journal_classifier
            else 0.2
        )

        # Step 2: Generate je_output file
        output_result = await self.journal_generator.generate(
            content=content,
            weights=weights,
            report_uid=report.uid,
            threshold=threshold,
        )

        if output_result.is_error:
            self.logger.error(f"je_output generation failed: {output_result.error}")
            return

        je_output_path = output_result.value

        # Step 3: Extract activities if weight exceeds threshold
        activities_extracted = 0
        if weights.should_extract_activities(threshold) and self.activity_extractor:
            self.logger.info(
                f"Activity weight {weights.activity} > {threshold}, extracting entities"
            )
            await self._extract_activities(report, report.user_uid, instructions)
            # Count would come from extraction result, but we don't have access here
            # This is tracked in report metadata by _extract_activities
            activities_extracted = 1  # Placeholder - actual count in metadata

        # Step 4: Store journal processing metadata
        current_metadata = report.metadata or {}
        current_metadata["journal_weights"] = weights.to_dict()
        current_metadata["je_output_path"] = je_output_path
        current_metadata["mode_threshold"] = threshold

        await self.report_service.update_report(
            uid=report.uid,
            updates={"metadata": current_metadata},
        )

        self.logger.info(
            f"Journal processing complete: {report.uid} - {weights.get_primary_mode().value}"
        )

    # ========================================================================
    # ACTIVITY EXTRACTION (DSL Integration)
    # ========================================================================

    async def _extract_activities(
        self, report: Report, user_uid: str, instructions: dict[str, Any] | None
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
            report: Processed report with content
            user_uid: User UID for entity ownership
            instructions: Processing instructions (may contain extraction options)
        """
        self.logger.info(f"Extracting activities from report {report.uid}")

        try:
            # Extract and create entities
            result = await self.activity_extractor.extract_and_create(
                report=report,
                user_uid=user_uid,
                create_relationships=instructions.get("create_activity_relationships", True)
                if instructions
                else True,
            )

            if result.is_ok:
                extraction = result.value
                self.logger.info(
                    f"Activity extraction complete for {report.uid}: "
                    f"found {extraction.activities_found} activities, "
                    f"created {extraction.total_created} entities "
                    f"(tasks={extraction.tasks_created}, habits={extraction.habits_created}, "
                    f"goals={extraction.goals_created}, events={extraction.events_created})"
                )

                if extraction.has_errors:
                    self.logger.warning(
                        f"Activity extraction had errors for {report.uid}: "
                        f"{len(extraction.parse_errors)} parse errors, "
                        f"{len(extraction.creation_errors)} creation errors"
                    )
            else:
                self.logger.warning(f"Activity extraction failed for {report.uid}: {result.error}")

        except Exception as e:
            # Activity extraction failure should not fail the entire processing
            self.logger.error(
                f"Unexpected error during activity extraction for {report.uid}: {e}",
                exc_info=True,
            )

    # ========================================================================
    # REPROCESSING
    # ========================================================================

    async def reprocess_report(
        self, report_uid: str, new_instructions: dict[str, Any] | None = None
    ) -> Result[Report]:
        """
        Reprocess an existing report with new instructions.

        Resets status to SUBMITTED and processes again.

        Args:
            report_uid: Report UID
            new_instructions: New processing instructions

        Returns:
            Result containing reprocessed report
        """
        # Reset status to SUBMITTED
        await self.report_service.update_report_status(report_uid, ReportStatus.SUBMITTED)

        # Process with new instructions
        return await self.process_report(report_uid, new_instructions)


# Backward compatibility alias
ProcessingPipelineService = ReportsProcessingService
