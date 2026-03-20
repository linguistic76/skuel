"""
Unit tests for submission processing event publishing.

Tests cover:
- SubmissionProcessingStarted published when processing begins
- SubmissionProcessingCompleted published on successful processing
- SubmissionProcessingFailed published on processing failure (3 paths)
- Events not published when event_bus is None (graceful degradation)
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.events.submission_events import (
    SubmissionProcessingCompleted,
    SubmissionProcessingFailed,
    SubmissionProcessingStarted,
)
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.submissions.submission import Submission
from core.services.submissions.submissions_processing_service import (
    SubmissionsProcessingService,
)
from core.utils.result_simplified import Errors, Result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_submission(
    uid: str = "es_test_abc",
    user_uid: str = "user_123",
    status: EntityStatus = EntityStatus.SUBMITTED,
    file_type: str = "text/plain",
    processor_type_value: str = "automatic",
) -> Mock:
    """Create a mock submission."""
    sub = Mock(spec=Submission)
    sub.uid = uid
    sub.user_uid = user_uid
    sub.status = status
    sub.file_type = file_type
    sub.entity_type = EntityType.EXERCISE_SUBMISSION
    processor = Mock()
    processor.value = processor_type_value
    sub.processor_type = processor
    sub.original_filename = "test.txt"
    sub.file_path = "/tmp/test.txt"
    sub.metadata = {}
    return sub


@pytest.fixture
def mock_submission_service() -> AsyncMock:
    svc = AsyncMock()
    svc.update_submission_status = AsyncMock()
    svc.get_submission = AsyncMock()
    svc.update_processed_content = AsyncMock()
    svc.get_file_content = AsyncMock()
    return svc


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def service(mock_submission_service: AsyncMock, mock_event_bus: AsyncMock) -> SubmissionsProcessingService:
    return SubmissionsProcessingService(
        ku_submission_service=mock_submission_service,
        event_bus=mock_event_bus,
    )


@pytest.fixture
def service_no_bus(mock_submission_service: AsyncMock) -> SubmissionsProcessingService:
    return SubmissionsProcessingService(
        ku_submission_service=mock_submission_service,
        event_bus=None,
    )


# ---------------------------------------------------------------------------
# SubmissionProcessingStarted
# ---------------------------------------------------------------------------


class TestProcessingStartedEvent:
    """SubmissionProcessingStarted is published when _route_to_processor runs."""

    @pytest.mark.asyncio
    async def test_started_event_published(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Processing started event fires after status set to PROCESSING."""
        submission = _make_submission()
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        # _route_to_processor will fail on file read — that's fine,
        # we just need to verify the Started event was published before failure
        mock_submission_service.get_file_content.return_value = Result.fail(
            Errors.system("test stop")
        )

        await service.process_submission(submission.uid)

        # Find the Started event among publish calls
        started_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingStarted)
        ]
        assert len(started_events) == 1
        event = started_events[0]
        assert event.submission_uid == submission.uid
        assert event.user_uid == submission.user_uid
        assert event.processor_type == "automatic"

    @pytest.mark.asyncio
    async def test_started_event_not_published_for_already_completed(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """No events when submission is already completed (early return)."""
        submission = _make_submission(status=EntityStatus.COMPLETED)
        mock_submission_service.get_submission.return_value = Result.ok(submission)

        result = await service.process_submission(submission.uid)

        assert result.is_error
        mock_event_bus.publish_async.assert_not_called()


# ---------------------------------------------------------------------------
# SubmissionProcessingCompleted
# ---------------------------------------------------------------------------


class TestProcessingCompletedEvent:
    """SubmissionProcessingCompleted is published after successful processing."""

    @pytest.mark.asyncio
    async def test_completed_event_published(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Completed event fires with duration after successful text processing."""
        submission = _make_submission(file_type="text/plain")
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        mock_submission_service.get_file_content.return_value = Result.ok(b"Hello world")
        mock_submission_service.update_processed_content.return_value = Result.ok(submission)

        await service.process_submission(submission.uid)

        completed_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingCompleted)
        ]
        assert len(completed_events) == 1
        event = completed_events[0]
        assert event.submission_uid == submission.uid
        assert event.user_uid == submission.user_uid
        assert event.entity_type == EntityType.EXERCISE_SUBMISSION.value
        assert event.has_processed_content is True
        assert event.processing_duration_seconds is not None
        assert event.processing_duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_completed_event_not_published_on_failure(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """No completed event when processing fails."""
        submission = _make_submission(file_type="text/plain")
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        mock_submission_service.get_file_content.return_value = Result.fail(
            Errors.system("disk error")
        )

        await service.process_submission(submission.uid)

        completed_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingCompleted)
        ]
        assert len(completed_events) == 0


# ---------------------------------------------------------------------------
# SubmissionProcessingFailed
# ---------------------------------------------------------------------------


class TestProcessingFailedEvent:
    """SubmissionProcessingFailed is published on all failure paths."""

    @pytest.mark.asyncio
    async def test_failed_event_on_processor_error(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Failed event fires when processor returns Result.fail."""
        submission = _make_submission(file_type="text/plain")
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        mock_submission_service.get_file_content.return_value = Result.fail(
            Errors.system("read error")
        )

        result = await service.process_submission(submission.uid)

        assert result.is_error
        failed_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingFailed)
        ]
        assert len(failed_events) == 1
        event = failed_events[0]
        assert event.submission_uid == submission.uid
        assert event.user_uid == submission.user_uid
        assert len(event.error_message) > 0

    @pytest.mark.asyncio
    async def test_failed_event_on_neo4j_exception(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Failed event fires when Neo4j exception is raised."""
        from neo4j.exceptions import ServiceUnavailable

        submission = _make_submission(file_type="text/plain")
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        mock_submission_service.get_file_content.side_effect = ServiceUnavailable("connection lost")

        result = await service.process_submission(submission.uid)

        assert result.is_error
        failed_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingFailed)
        ]
        assert len(failed_events) == 1
        assert "connection lost" in failed_events[0].error_message

    @pytest.mark.asyncio
    async def test_failed_event_on_unexpected_exception(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Failed event fires on unexpected exceptions (safety-net path)."""
        submission = _make_submission(file_type="text/plain")
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        mock_submission_service.get_file_content.side_effect = RuntimeError("unexpected")

        result = await service.process_submission(submission.uid)

        assert result.is_error
        failed_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingFailed)
        ]
        assert len(failed_events) == 1
        assert "unexpected" in failed_events[0].error_message

    @pytest.mark.asyncio
    async def test_failed_event_on_unsupported_file_type(
        self,
        service: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Failed event fires when file type is not supported."""
        submission = _make_submission(file_type="application/pdf")
        mock_submission_service.get_submission.return_value = Result.ok(submission)

        result = await service.process_submission(submission.uid)

        assert result.is_error
        failed_events = [
            call.args[0]
            for call in mock_event_bus.publish_async.call_args_list
            if isinstance(call.args[0], SubmissionProcessingFailed)
        ]
        assert len(failed_events) == 1


# ---------------------------------------------------------------------------
# No event bus (graceful degradation)
# ---------------------------------------------------------------------------


class TestNoEventBus:
    """Events are silently skipped when event_bus is None."""

    @pytest.mark.asyncio
    async def test_processing_succeeds_without_event_bus(
        self,
        service_no_bus: SubmissionsProcessingService,
        mock_submission_service: AsyncMock,
    ) -> None:
        """Processing completes normally even without event bus."""
        submission = _make_submission(file_type="text/plain")
        mock_submission_service.get_submission.return_value = Result.ok(submission)
        mock_submission_service.get_file_content.return_value = Result.ok(b"content")
        mock_submission_service.update_processed_content.return_value = Result.ok(submission)

        result = await service_no_bus.process_submission(submission.uid)

        assert result.is_ok
