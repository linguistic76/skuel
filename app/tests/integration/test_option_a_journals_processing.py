"""
Integration Test: Assignment Processing Pipeline
================================================

Tests the Assignment processing pipeline for file submissions.

NOTE (January 2026): Tests updated for domain separation.
Journals are now a separate domain (JournalsCoreService).
Assignments handle TRANSCRIPT, REPORT, IMAGE_ANALYSIS, VIDEO_SUMMARY types only.

The AssignmentProcessorService:
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
Updated: January 2026 (Domain Separation - removed Journal-specific processing)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from core.models.assignment.assignment import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    ProcessorType,
)
from core.services.assignments import AssignmentProcessorService
from core.utils.result_simplified import Errors, Result


@pytest.mark.asyncio
class TestOptionAJournalsProcessing:
    """Integration tests for Assignment processing (post domain separation)."""

    # ==========================================================================
    # FIXTURES
    # ==========================================================================

    @pytest_asyncio.fixture
    async def mock_assignment_service(self):
        """Mock AssignmentSubmissionService."""
        service = AsyncMock()

        # Mock assignment with transcript type
        assignment = Assignment(
            uid="assignment.test_transcript",
            user_uid="user.test",
            assignment_type=AssignmentType.TRANSCRIPT,
            status=AssignmentStatus.SUBMITTED,
            file_path="/tmp/test_audio.mp3",
            file_type="audio/mpeg",
            file_size=1024000,
            original_filename="meeting_notes.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Track state changes (mutable reference)
        current_state = {"assignment": assignment}

        # get_assignment returns current state
        def mock_get_assignment(uid):
            return Result.ok(current_state["assignment"])

        # update_assignment_status tracks status changes
        def mock_update_status(uid, status, error_message=None):
            updated = Assignment(
                uid=current_state["assignment"].uid,
                user_uid=current_state["assignment"].user_uid,
                assignment_type=current_state["assignment"].assignment_type,
                status=status,
                file_path=current_state["assignment"].file_path,
                file_type=current_state["assignment"].file_type,
                file_size=current_state["assignment"].file_size,
                original_filename=current_state["assignment"].original_filename,
                processor_type=current_state["assignment"].processor_type,
                created_at=current_state["assignment"].created_at,
                updated_at=datetime.now(),
                processed_content=current_state["assignment"].processed_content,
                metadata=current_state["assignment"].metadata,
            )
            current_state["assignment"] = updated
            return Result.ok(updated)

        # update_processed_content stores the content
        def mock_update_content(uid, processed_content):
            updated = Assignment(
                uid=current_state["assignment"].uid,
                user_uid=current_state["assignment"].user_uid,
                assignment_type=current_state["assignment"].assignment_type,
                status=current_state["assignment"].status,
                file_path=current_state["assignment"].file_path,
                file_type=current_state["assignment"].file_type,
                file_size=current_state["assignment"].file_size,
                original_filename=current_state["assignment"].original_filename,
                processor_type=current_state["assignment"].processor_type,
                created_at=current_state["assignment"].created_at,
                updated_at=datetime.now(),
                processed_content=processed_content,
                metadata=current_state["assignment"].metadata,
            )
            current_state["assignment"] = updated
            return Result.ok(updated)

        service.get_assignment.side_effect = mock_get_assignment
        service.update_assignment_status.side_effect = mock_update_status
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
        mock_assignment_service,
        mock_transcription_service,
    ):
        """Create AssignmentProcessorService with mocked dependencies.

        Note: transcript_processor and assignment_relationship_service are NOT passed
        because they are NOT used after the January 2026 domain separation.
        """
        return AssignmentProcessorService(
            assignment_service=mock_assignment_service,
            transcription_service=mock_transcription_service,
            transcript_processor=None,  # Not used - journals have their own domain
            assignment_relationship_service=None,  # Not used - journals have their own domain
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
        assignment_uid = "assignment.test_transcript"

        # Act
        result = await processing_pipeline.process_assignment(assignment_uid)

        # Assert
        assert result.is_ok

        # Verify transcription service was called
        assert mock_transcription_service.create.called
        assert mock_transcription_service.process.called

    async def test_audio_processing_stores_raw_transcript(
        self, processing_pipeline, mock_assignment_service
    ):
        """Test that audio processing stores the raw transcript (no LLM formatting)."""
        # Arrange
        assignment_uid = "assignment.test_transcript"

        # Act
        result = await processing_pipeline.process_assignment(assignment_uid)

        # Assert
        assert result.is_ok

        # Verify update_processed_content was called with raw transcript
        assert mock_assignment_service.update_processed_content.called
        call_args = mock_assignment_service.update_processed_content.call_args

        # Should be raw transcript text, not LLM-formatted
        assert call_args[1]["processed_content"] == "This is the transcribed meeting content."

    async def test_audio_processing_status_transitions(
        self, processing_pipeline, mock_assignment_service
    ):
        """Test that audio processing follows correct status transitions."""
        # Arrange
        assignment_uid = "assignment.test_transcript"

        # Act
        result = await processing_pipeline.process_assignment(assignment_uid)

        # Assert
        assert result.is_ok

        # Verify status update calls
        status_calls = mock_assignment_service.update_assignment_status.call_args_list

        # Should have: QUEUED, PROCESSING, COMPLETED
        assert len(status_calls) >= 2
        statuses = [call[0][1] for call in status_calls]

        assert AssignmentStatus.QUEUED in statuses
        assert AssignmentStatus.PROCESSING in statuses
        assert AssignmentStatus.COMPLETED in statuses

    # ==========================================================================
    # TEXT PROCESSING TESTS
    # ==========================================================================

    async def test_text_processing_reads_content(self, mock_assignment_service):
        """Test that text files are read directly from storage."""
        # Arrange - Create text file assignment
        text_assignment = Assignment(
            uid="assignment.test_text",
            user_uid="user.test",
            assignment_type=AssignmentType.TRANSCRIPT,
            status=AssignmentStatus.SUBMITTED,
            file_path="/tmp/test_notes.txt",
            file_type="text/plain",
            file_size=1024,
            original_filename="notes.txt",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_assignment_service.get_assignment.side_effect = lambda _uid: Result.ok(text_assignment)
        mock_assignment_service.get_file_content.return_value = Result.ok(
            b"This is the text file content."
        )

        pipeline = AssignmentProcessorService(
            assignment_service=mock_assignment_service,
            transcription_service=None,  # Not needed for text
        )

        # Act
        result = await pipeline.process_assignment("assignment.test_text")

        # Assert
        assert result.is_ok

        # Verify file content was read
        assert mock_assignment_service.get_file_content.called

        # Verify content was stored
        assert mock_assignment_service.update_processed_content.called
        call_args = mock_assignment_service.update_processed_content.call_args
        assert call_args[1]["processed_content"] == "This is the text file content."

    # ==========================================================================
    # ERROR HANDLING TESTS
    # ==========================================================================

    async def test_transcription_failure_marks_assignment_failed(
        self, mock_assignment_service, mock_transcription_service
    ):
        """Test that transcription failure marks assignment as FAILED."""
        # Arrange
        mock_transcription_service.create.return_value = Result.fail(
            Errors.system(message="Transcription service unavailable", operation="create")
        )

        pipeline = AssignmentProcessorService(
            assignment_service=mock_assignment_service,
            transcription_service=mock_transcription_service,
        )

        # Act
        result = await pipeline.process_assignment("assignment.test_transcript")

        # Assert
        assert result.is_error

        # Verify status was set to FAILED
        status_calls = mock_assignment_service.update_assignment_status.call_args_list
        final_status = status_calls[-1][0][1]
        assert final_status == AssignmentStatus.FAILED

    async def test_already_processing_assignment_rejected(self):
        """Test that already-processing assignments are rejected."""
        # Arrange - Assignment already in PROCESSING state
        processing_assignment = Assignment(
            uid="assignment.processing",
            user_uid="user.test",
            assignment_type=AssignmentType.TRANSCRIPT,
            status=AssignmentStatus.PROCESSING,  # Already processing
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
        mock_service.get_assignment.return_value = Result.ok(processing_assignment)

        pipeline = AssignmentProcessorService(
            assignment_service=mock_service,
        )

        # Act
        result = await pipeline.process_assignment("assignment.processing")

        # Assert
        assert result.is_error
        assert "already" in result.error.user_message.lower()

    async def test_unsupported_file_type_rejected(self):
        """Test that unsupported file types return an error."""
        # Arrange - Assignment with unsupported file type
        pdf_assignment = Assignment(
            uid="assignment.pdf",
            user_uid="user.test",
            assignment_type=AssignmentType.REPORT,
            status=AssignmentStatus.SUBMITTED,
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
        mock_service.get_assignment.return_value = Result.ok(pdf_assignment)

        pipeline = AssignmentProcessorService(
            assignment_service=mock_service,
        )

        # Act
        result = await pipeline.process_assignment("assignment.pdf")

        # Assert
        assert result.is_error
        assert "not yet supported" in result.error.user_message.lower()

    # ==========================================================================
    # ARCHITECTURE VALIDATION TESTS
    # ==========================================================================

    async def test_assignment_type_discriminator_works(self, mock_assignment_service):
        """Test that assignment_type discriminator works correctly."""
        # Arrange
        transcript_assignment = Assignment(
            uid="assignment.transcript_type",
            user_uid="user.test",
            assignment_type=AssignmentType.TRANSCRIPT,  # Type discriminator
            status=AssignmentStatus.SUBMITTED,
            file_path="/tmp/test.mp3",
            file_type="audio/mpeg",
            file_size=1024,
            original_filename="meeting.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Act & Assert
        assert transcript_assignment.assignment_type == AssignmentType.TRANSCRIPT

        # Can differentiate from other assignment types
        report_assignment = Assignment(
            uid="assignment.report_type",
            user_uid="user.test",
            assignment_type=AssignmentType.REPORT,  # Different type
            status=AssignmentStatus.SUBMITTED,
            file_path="/tmp/test.pdf",
            file_type="application/pdf",
            file_size=1024,
            original_filename="report.pdf",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert report_assignment.assignment_type != AssignmentType.TRANSCRIPT
        assert report_assignment.assignment_type == AssignmentType.REPORT

    async def test_no_llm_processing_in_assignment_pipeline(
        self, processing_pipeline, mock_assignment_service
    ):
        """Test that assignment pipeline does NOT do LLM processing (domain separation)."""
        # Arrange
        assignment_uid = "assignment.test_transcript"

        # Act
        result = await processing_pipeline.process_assignment(assignment_uid)

        # Assert
        assert result.is_ok

        # Verify raw content stored, not LLM-formatted
        call_args = mock_assignment_service.update_processed_content.call_args
        content = call_args[1]["processed_content"]

        # Raw transcript should be stored as-is
        assert content == "This is the transcribed meeting content."
        # NOT something like "# Meeting Notes\n\n## Summary\n..."

    async def test_reprocess_assignment_resets_status(
        self, processing_pipeline, mock_assignment_service
    ):
        """Test that reprocessing an assignment resets its status."""
        # First, complete initial processing
        assignment_uid = "assignment.test_transcript"
        await processing_pipeline.process_assignment(assignment_uid)

        # Reset the mock to track reprocessing calls
        mock_assignment_service.update_assignment_status.reset_mock()

        # Now, update the assignment to COMPLETED state for reprocessing test
        completed_assignment = Assignment(
            uid="assignment.test_transcript",
            user_uid="user.test",
            assignment_type=AssignmentType.TRANSCRIPT,
            status=AssignmentStatus.COMPLETED,
            file_path="/tmp/test_audio.mp3",
            file_type="audio/mpeg",
            file_size=1024000,
            original_filename="meeting_notes.mp3",
            processor_type=ProcessorType.LLM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            processed_content="Old content",
        )
        mock_assignment_service.get_assignment.return_value = Result.ok(completed_assignment)

        # Act - reprocess
        result = await processing_pipeline.reprocess_assignment(assignment_uid)

        # Assert
        assert result.is_ok

        # Verify status was reset to SUBMITTED first
        status_calls = mock_assignment_service.update_assignment_status.call_args_list
        first_status = status_calls[0][0][1]
        assert first_status == AssignmentStatus.SUBMITTED
