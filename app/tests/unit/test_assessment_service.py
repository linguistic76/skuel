"""
Unit Tests for Assessment Service Methods
============================================

Tests create_assessment, get_assessments_for_student,
and get_assessments_by_teacher on KuCoreService.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.ku_enums import KuType
from core.models.ku import Ku
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
    """Create KuCoreService with mocked deps."""
    from core.services.reports.reports_core_service import KuCoreService

    return KuCoreService(
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
        # Verify backend.create was called with a Ku
        assert mock_backend.create.call_count == 1
        created_ku = mock_backend.create.call_args[0][0]
        assert isinstance(created_ku, Ku)
        assert created_ku.ku_type == KuType.FEEDBACK_REPORT
        assert created_ku.user_uid == "user_teacher"
        assert created_ku.subject_uid == "user_student"
        assert created_ku.title == "Midterm Assessment"

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

        created_ku = mock_backend.create.call_args[0][0]
        assert created_ku.metadata == {"rubric": "A"}


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
                    "k": {
                        "uid": "report_123",
                        "user_uid": "user_teacher",
                        "ku_type": "feedback_report",
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
