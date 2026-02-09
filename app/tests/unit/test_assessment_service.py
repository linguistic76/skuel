"""
Unit Tests for Assessment Service Methods
============================================

Tests create_assessment, get_assessments_for_student,
and get_assessments_by_teacher on ReportsCoreService.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.report_enums import ReportType
from core.models.report.report import Report
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_backend():
    """Create a mock reports backend."""
    backend = MagicMock()
    backend.create = AsyncMock()
    backend.find_by = AsyncMock()
    backend.driver = MagicMock()
    backend.driver.execute_query = AsyncMock()
    return backend


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def mock_sharing_service():
    """Create a mock sharing service."""
    return MagicMock()


@pytest.fixture
def core_service(mock_backend, mock_event_bus, mock_sharing_service):
    """Create ReportsCoreService with mocked deps."""
    from core.services.reports.reports_core_service import ReportsCoreService

    return ReportsCoreService(
        backend=mock_backend,
        event_bus=mock_event_bus,
        sharing_service=mock_sharing_service,
    )


# ============================================================================
# CREATE ASSESSMENT TESTS
# ============================================================================


class TestCreateAssessment:
    """Test create_assessment method."""

    @pytest.mark.asyncio
    async def test_create_assessment_success(self, core_service, mock_backend):
        """Test successful assessment creation."""
        mock_backend.create.return_value = Result.ok(MagicMock())
        # Mock the relationship creation queries
        mock_backend.driver.execute_query.return_value = ([], None, None)

        result = await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Midterm Assessment",
            content="Good progress on fundamentals.",
        )

        assert not result.is_error
        # Verify backend.create was called with a Report
        assert mock_backend.create.call_count == 1
        created_report = mock_backend.create.call_args[0][0]
        assert isinstance(created_report, Report)
        assert created_report.report_type == ReportType.ASSESSMENT
        assert created_report.user_uid == "user_teacher"
        assert created_report.subject_uid == "user_student"
        assert created_report.title == "Midterm Assessment"

    @pytest.mark.asyncio
    async def test_create_assessment_creates_relationships(self, core_service, mock_backend):
        """Test that ASSESSMENT_OF and SHARES_WITH relationships are created."""
        mock_backend.create.return_value = Result.ok(MagicMock())
        mock_backend.driver.execute_query.return_value = ([], None, None)

        await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
        )

        # Should have at least 2 driver calls: ASSESSMENT_OF + SHARES_WITH
        assert mock_backend.driver.execute_query.call_count >= 2

    @pytest.mark.asyncio
    async def test_create_assessment_backend_failure(self, core_service, mock_backend):
        """Test failure propagation from backend."""
        mock_backend.create.return_value = Result.fail(Errors.database("create", "Create failed"))

        result = await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_create_assessment_with_metadata(self, core_service, mock_backend):
        """Test metadata is passed through."""
        mock_backend.create.return_value = Result.ok(MagicMock())
        mock_backend.driver.execute_query.return_value = ([], None, None)

        await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
            metadata={"rubric": "A"},
        )

        created_report = mock_backend.create.call_args[0][0]
        assert created_report.metadata == {"rubric": "A"}


# ============================================================================
# GET ASSESSMENTS TESTS
# ============================================================================


class TestGetAssessments:
    """Test assessment query methods."""

    @pytest.mark.asyncio
    async def test_get_assessments_for_student(self, core_service, mock_backend):
        """Test querying assessments by student."""
        mock_backend.driver.execute_query.return_value = (
            [
                {
                    "r": {
                        "uid": "report_123",
                        "user_uid": "user_teacher",
                        "report_type": "assessment",
                        "title": "Assessment 1",
                        "subject_uid": "user_student",
                    }
                },
            ],
            None,
            None,
        )

        result = await core_service.get_assessments_for_student(
            student_uid="user_student",
            limit=10,
        )

        assert not result.is_error
        assert mock_backend.driver.execute_query.call_count >= 1

    @pytest.mark.asyncio
    async def test_get_assessments_by_teacher(self, core_service, mock_backend):
        """Test querying assessments by teacher."""
        mock_backend.find_by.return_value = Result.ok([])

        result = await core_service.get_assessments_by_teacher(
            teacher_uid="user_teacher",
            limit=10,
        )

        assert not result.is_error
