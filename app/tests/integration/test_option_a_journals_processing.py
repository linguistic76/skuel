"""
Integration Test: Ku Processing Pipeline
=========================================

Tests the Ku processing pipeline for file submissions.

NOTE (February 2026): Tests updated for unified Ku model.
Reports are now Ku with ku_type=SUBMISSION.
The KuProcessingService:
- Routes files to appropriate processors based on file type
- Audio files: transcribed via TranscriptionService
- Text files: read directly from storage
- Stores raw content (no LLM processing - that's the Journal domain's job)

Test Coverage:
--------------
- Audio processing: transcription → storage
- Text processing: read → storage
- Status transitions: SUBMITTED → QUEUED → PROCESSING → COMPLETED
- Error handling and failure status

Implementation Date: November 10, 2025
Updated: February 2026 (Unified Ku model - Report → Ku)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from core.models.enums.ku_enums import KuStatus, KuType, ProcessorType
from core.models.ku import Ku
from core.services.reports import KuProcessingService
from core.utils.result_simplified import Errors, Result


@pytest.mark.asyncio
class TestOptionAJournalsProcessing:
    """Integration tests for Ku processing (post domain separation)."""

    # ==========================================================================
    # FIXTURES
    # ==========================================================================

    @pytest_asyncio.fixture
    async def mock_report_service(self):
        """Mock KuSubmissionService."""
        service = AsyncMock()

        # Mock Ku with transcript type
        ku = Ku(
            uid="report.test_transcript",
            title="Meeting Notes",
            user_uid="user.test",
            ku_type=KuType.SUBMISSION,
            status=KuStatus.SUBMITTED,
            file_path="/tmp/test_audio.mp3",
            file_type="audio/mpeg",
            file_size=1024000,
            original_filename="meeting_notes.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Track state changes (mutable reference)
        current_state = {"report": ku}

        # get_report returns current state
        def mock_get_report(uid):
            return Result.ok(current_state["report"])

        # update_report_status tracks status changes
        def mock_update_status(uid, status, error_message=None):
            updated = Ku(
                uid=current_state["report"].uid,
                title=current_state["report"].title,
                user_uid=current_state["report"].user_uid,
                ku_type=current_state["report"].ku_type,
                status=status,
                file_path=current_state["report"].file_path,
                file_type=current_state["report"].file_type,
                file_size=current_state["report"].file_size,
                original_filename=current_state["report"].original_filename,
                processor_type=current_state["report"].processor_type,
                created_at=current_state["report"].created_at,
                updated_at=datetime.now(),
                processed_content=current_state["report"].processed_content,
            )
            current_state["report"] = updated
            return Result.ok(updated)

        # update_processed_content stores the content
        def mock_update_content(uid, processed_content):
            updated = Ku(
                uid=current_state["report"].uid,
                title=current_state["report"].title,
                user_uid=current_state["report"].user_uid,
                ku_type=current_state["report"].ku_type,
                status=current_state["report"].status,
                file_path=current_state["report"].file_path,
                file_type=current_state["report"].file_type,
                file_size=current_state["report"].file_size,
                original_filename=current_state["report"].original_filename,
                processor_type=current_state["report"].processor_type,
                created_at=current_state["report"].created_at,
                updated_at=datetime.now(),
                processed_content=processed_content,
            )
            current_state["report"] = updated
            return Result.ok(updated)

        service.get_ku.side_effect = mock_get_report
        service.update_ku_status.side_effect = mock_update_status
        service.update_processed_content.side_effect = mock_update_content

        return service

    @pytest_asyncio.fixture
    async def mock_transcription_service(self):
        """Mock TranscriptionService (simplified per ADR-019).

        ADR-019 changed the API from:
            transcribe_file(file_path) → transcript
        To:
            create(request, user_uid) → Transcription (PENDING)
            process(uid) → Transcription (COMPLETED with transcript_text)
        """
        service = AsyncMock()

        # Mock Transcription object returned by create()
        created_transcription = MagicMock()
        created_transcription.uid = "transcription.test.123"

        # Mock Transcription object returned by process() (with transcript)
        processed_transcription = MagicMock()
        processed_transcription.uid = "transcription.test.123"
        processed_transcription.transcript_text = "This is the transcribed meeting content."

        # Mock the ADR-019 API
        service.create = AsyncMock(return_value=Result.ok(created_transcription))
        service.process = AsyncMock(return_value=Result.ok(processed_transcription))

        return service

    @pytest_asyncio.fixture
    async def processing_pipeline(
        self,
        mock_report_service,
        mock_transcription_service,
    ):
        """Create KuProcessingService with mocked dependencies.

        Note: transcript_processor and report_relationship_service are NOT passed
        because they are NOT used after the January 2026 domain separation.
        """
        return KuProcessingService(
            ku_submission_service=mock_report_service,
            transcription_service=mock_transcription_service,
            transcript_processor=None,  # Not used - journals have their own domain
            ku_relationship_service=None,  # Not used - journals have their own domain
            event_bus=None,
        )

    # ==========================================================================
    # AUDIO PROCESSING TESTS
    # ==========================================================================

    async def test_audio_processing_transcribes_content(
        self, processing_pipeline, mock_transcription_service
    ):
        """Test that audio files are transcribed via TranscriptionService."""
        # Arrange
        report_uid = "report.test_transcript"

        # Act
        result = await processing_pipeline.process_ku(report_uid)

        # Assert
        assert result.is_ok

        # Verify transcription service was called
        assert mock_transcription_service.create.called
        assert mock_transcription_service.process.called

    async def test_audio_processing_stores_raw_transcript(
        self, processing_pipeline, mock_report_service
    ):
        """Test that audio processing stores the raw transcript (no LLM formatting)."""
        # Arrange
        report_uid = "report.test_transcript"

        # Act
        result = await processing_pipeline.process_ku(report_uid)

        # Assert
        assert result.is_ok

        # Verify update_processed_content was called with raw transcript
        assert mock_report_service.update_processed_content.called
        call_args = mock_report_service.update_processed_content.call_args

        # Should be raw transcript text, not LLM-formatted
        assert call_args[1]["processed_content"] == "This is the transcribed meeting content."

    async def test_audio_processing_status_transitions(
        self, processing_pipeline, mock_report_service
    ):
        """Test that audio processing follows correct status transitions."""
        # Arrange
        report_uid = "report.test_transcript"

        # Act
        result = await processing_pipeline.process_ku(report_uid)

        # Assert
        assert result.is_ok

        # Verify status update calls
        status_calls = mock_report_service.update_ku_status.call_args_list

        # Should have: QUEUED, PROCESSING, COMPLETED
        assert len(status_calls) >= 2
        statuses = [call[0][1] for call in status_calls]

        assert KuStatus.QUEUED in statuses
        assert KuStatus.PROCESSING in statuses
        assert KuStatus.COMPLETED in statuses

    # ==========================================================================
    # TEXT PROCESSING TESTS
    # ==========================================================================

    async def test_text_processing_reads_content(self, mock_report_service):
        """Test that text files are read directly from storage."""
        # Arrange - Create text file Ku
        text_ku = Ku(
            uid="report.test_text",
            title="Notes",
            user_uid="user.test",
            ku_type=KuType.SUBMISSION,
            status=KuStatus.SUBMITTED,
            file_path="/tmp/test_notes.txt",
            file_type="text/plain",
            file_size=1024,
            original_filename="notes.txt",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_report_service.get_ku.side_effect = lambda _uid: Result.ok(text_ku)
        mock_report_service.get_file_content.return_value = Result.ok(
            b"This is the text file content."
        )

        pipeline = KuProcessingService(
            ku_submission_service=mock_report_service,
            transcription_service=None,  # Not needed for text
        )

        # Act
        result = await pipeline.process_ku("report.test_text")

        # Assert
        assert result.is_ok

        # Verify file content was read
        assert mock_report_service.get_file_content.called

        # Verify content was stored
        assert mock_report_service.update_processed_content.called
        call_args = mock_report_service.update_processed_content.call_args
        assert call_args[1]["processed_content"] == "This is the text file content."

    # ==========================================================================
    # ERROR HANDLING TESTS
    # ==========================================================================

    async def test_transcription_failure_marks_report_failed(
        self, mock_report_service, mock_transcription_service
    ):
        """Test that transcription failure marks Ku as FAILED."""
        # Arrange
        mock_transcription_service.create.return_value = Result.fail(
            Errors.system(message="Transcription service unavailable", operation="create")
        )

        pipeline = KuProcessingService(
            ku_submission_service=mock_report_service,
            transcription_service=mock_transcription_service,
        )

        # Act
        result = await pipeline.process_ku("report.test_transcript")

        # Assert
        assert result.is_error

        # Verify status was set to FAILED
        status_calls = mock_report_service.update_ku_status.call_args_list
        final_status = status_calls[-1][0][1]
        assert final_status == KuStatus.FAILED

    async def test_already_processing_report_rejected(self):
        """Test that already-processing Ku are rejected."""
        # Arrange - Ku already in PROCESSING state
        processing_ku = Ku(
            uid="report.processing",
            title="Processing",
            user_uid="user.test",
            ku_type=KuType.SUBMISSION,
            status=KuStatus.PROCESSING,  # Already processing
            file_path="/tmp/test.mp3",
            file_type="audio/mpeg",
            file_size=1024,
            original_filename="test.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Create fresh mock without side_effect interference
        mock_service = AsyncMock()
        mock_service.get_ku.return_value = Result.ok(processing_ku)

        pipeline = KuProcessingService(
            ku_submission_service=mock_service,
        )

        # Act
        result = await pipeline.process_ku("report.processing")

        # Assert
        assert result.is_error
        assert "already" in result.error.user_message.lower()

    async def test_unsupported_file_type_rejected(self):
        """Test that unsupported file types return an error."""
        # Arrange - Ku with unsupported file type
        pdf_ku = Ku(
            uid="report.pdf",
            title="PDF Report",
            user_uid="user.test",
            ku_type=KuType.SUBMISSION,
            status=KuStatus.SUBMITTED,
            file_path="/tmp/test.pdf",
            file_type="application/pdf",  # Not yet supported
            file_size=1024,
            original_filename="report.pdf",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Create fresh mock without side_effect interference
        mock_service = AsyncMock()
        mock_service.get_ku.return_value = Result.ok(pdf_ku)

        pipeline = KuProcessingService(
            ku_submission_service=mock_service,
        )

        # Act
        result = await pipeline.process_ku("report.pdf")

        # Assert
        assert result.is_error
        assert "not yet supported" in result.error.user_message.lower()

    # ==========================================================================
    # ARCHITECTURE VALIDATION TESTS
    # ==========================================================================

    async def test_ku_type_discriminator_works(self, mock_report_service):
        """Test that ku_type discriminator works correctly."""
        # Arrange
        assignment_ku = Ku(
            uid="report.transcript_type",
            title="Transcript",
            user_uid="user.test",
            ku_type=KuType.SUBMISSION,
            status=KuStatus.SUBMITTED,
            file_path="/tmp/test.mp3",
            file_type="audio/mpeg",
            file_size=1024,
            original_filename="meeting.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Act & Assert
        assert assignment_ku.ku_type == KuType.SUBMISSION

        # Can differentiate from other ku types
        curriculum_ku = Ku(
            uid="ku.curriculum_type",
            title="Curriculum Content",
            ku_type=KuType.CURRICULUM,
        )

        assert curriculum_ku.ku_type != KuType.SUBMISSION
        assert curriculum_ku.ku_type == KuType.CURRICULUM

    async def test_no_llm_processing_in_report_pipeline(
        self, processing_pipeline, mock_report_service
    ):
        """Test that Ku pipeline does NOT do LLM processing (domain separation)."""
        # Arrange
        report_uid = "report.test_transcript"

        # Act
        result = await processing_pipeline.process_ku(report_uid)

        # Assert
        assert result.is_ok

        # Verify raw content stored, not LLM-formatted
        call_args = mock_report_service.update_processed_content.call_args
        content = call_args[1]["processed_content"]

        # Raw transcript should be stored as-is
        assert content == "This is the transcribed meeting content."
        # NOT something like "# Meeting Notes\n\n## Summary\n..."

    async def test_reprocess_ku_resets_status(self, processing_pipeline, mock_report_service):
        """Test that reprocessing a Ku resets its status."""
        # First, complete initial processing
        report_uid = "report.test_transcript"
        await processing_pipeline.process_ku(report_uid)

        # Reset the mock to track reprocessing calls
        mock_report_service.update_ku_status.reset_mock()

        # Now, update the Ku to COMPLETED state for reprocessing test
        completed_ku = Ku(
            uid="report.test_transcript",
            title="Meeting Notes",
            user_uid="user.test",
            ku_type=KuType.SUBMISSION,
            status=KuStatus.COMPLETED,
            file_path="/tmp/test_audio.mp3",
            file_type="audio/mpeg",
            file_size=1024000,
            original_filename="meeting_notes.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            processed_content="Old content",
        )
        mock_report_service.get_ku.return_value = Result.ok(completed_ku)

        # Act - reprocess
        result = await processing_pipeline.reprocess_ku(report_uid)

        # Assert
        assert result.is_ok

        # Verify status was reset to SUBMITTED first
        status_calls = mock_report_service.update_ku_status.call_args_list
        first_status = status_calls[0][0][1]
        assert first_status == KuStatus.SUBMITTED
