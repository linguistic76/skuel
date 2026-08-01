"""
Unit Tests for Assessment Service Methods
============================================

Tests create_assessment, get_assessments_for_student,
and get_assessments_by_teacher on AssessmentService (ADR-054 Commit 6a).
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.report.entry_report import EntryReport
from core.utils.result_simplified import Errors, Result

# Helpers for mocking execute_query call sequence (returns Result[list[dict]])
AUTHORITY_MATCH = Result.ok([{"group_uid": "group_abc"}])
AUTHORITY_NO_MATCH: Result[list[dict[str, Any]]] = Result.ok([])
ASSESSMENT_CREATED = Result.ok([{"report_uid": "er_123"}])
STUDENT_MISSING: Result[list[dict[str, Any]]] = Result.ok([])


@pytest.fixture
def mock_backend():
    """Create a mock UserEntry backend (authority + query ops)."""
    backend = MagicMock()
    backend.find_by = AsyncMock()
    backend.execute_query = AsyncMock()
    backend.verify_teacher_authority = AsyncMock()
    backend.get_assessments_for_student_raw = AsyncMock()
    return backend


@pytest.fixture
def mock_report_backend():
    """Create a mock EntryReport backend (atomic assessment-node create)."""
    backend = MagicMock()
    backend.create_assessment_node = AsyncMock()
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
def core_service(mock_backend, mock_report_backend, mock_event_bus, mock_sharing_service):
    """Create AssessmentService with mocked deps."""
    from core.services.user_entry.assessment_service import AssessmentService

    return AssessmentService(
        backend=mock_backend,
        report_backend=mock_report_backend,
        event_bus=mock_event_bus,
    )


# ============================================================================
# CREATE ASSESSMENT TESTS
# ============================================================================


class TestCreateAssessment:
    """Test create_assessment method."""

    @pytest.mark.asyncio
    async def test_create_assessment_success(self, core_service, mock_backend, mock_report_backend):
        """Test successful assessment creation."""
        mock_report_backend.create_assessment_node.return_value = ASSESSMENT_CREATED
        mock_backend.verify_teacher_authority.return_value = AUTHORITY_MATCH

        result = await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Midterm Assessment",
            content="Good progress on fundamentals.",
        )

        assert not result.is_error
        # Verify the atomic create was called with an EntryReport
        assert mock_report_backend.create_assessment_node.call_count == 1
        created_ku = mock_report_backend.create_assessment_node.call_args[0][0]
        assert isinstance(created_ku, EntryReport)
        assert created_ku.entity_type == EntityType.ENTRY_REPORT
        assert created_ku.user_uid == "user_student"  # student always owns
        assert created_ku.author_uid == "user_teacher"  # teacher is the author
        assert created_ku.subject_uid == "user_student"
        assert created_ku.title == "Midterm Assessment"

    @pytest.mark.asyncio
    async def test_create_assessment_atomic_write(
        self, core_service, mock_backend, mock_report_backend
    ):
        """Test the write is ONE atomic backend call after the authority check.

        Node, student OWNS (the visibility anchor), and SHARES_WITH are
        written together by ``create_assessment_node`` — there is no separate
        relationship call whose failure could leave an invisible report
        behind a success response.
        """
        mock_report_backend.create_assessment_node.return_value = ASSESSMENT_CREATED
        mock_backend.verify_teacher_authority.return_value = AUTHORITY_MATCH

        await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
        )

        mock_backend.verify_teacher_authority.assert_awaited_once()
        mock_report_backend.create_assessment_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_assessment_backend_failure(
        self, core_service, mock_backend, mock_report_backend
    ):
        """Test failure propagation from the atomic create."""
        mock_backend.verify_teacher_authority.return_value = AUTHORITY_MATCH
        mock_report_backend.create_assessment_node.return_value = Result.fail(
            Errors.database("create_assessment_node", "Create failed")
        )

        result = await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_create_assessment_with_metadata(
        self, core_service, mock_backend, mock_report_backend
    ):
        """Test metadata is passed through."""
        mock_report_backend.create_assessment_node.return_value = ASSESSMENT_CREATED
        mock_backend.verify_teacher_authority.return_value = AUTHORITY_MATCH

        await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
            metadata={"rubric": "A"},
        )

        created_ku = mock_report_backend.create_assessment_node.call_args[0][0]
        assert created_ku.metadata == {"rubric": "A"}

    @pytest.mark.asyncio
    async def test_create_assessment_no_authority(
        self, core_service, mock_backend, mock_report_backend
    ):
        """Test that teacher without shared group is rejected."""
        mock_backend.verify_teacher_authority.return_value = AUTHORITY_NO_MATCH

        result = await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
        )

        assert result.is_error
        assert "authority" in str(result.expect_error()).lower()
        # report backend create should NOT have been called
        mock_report_backend.create_assessment_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_assessment_student_missing_is_error(
        self, core_service, mock_backend, mock_report_backend
    ):
        """Test an empty atomic-create result (student gone) maps to an error.

        The atomic Cypher creates nothing when the student MATCH finds no
        node, so an empty result must surface as a failure — never a success
        response for a report that does not exist.
        """
        mock_report_backend.create_assessment_node.return_value = STUDENT_MISSING
        mock_backend.verify_teacher_authority.return_value = AUTHORITY_MATCH

        result = await core_service.create_assessment(
            teacher_uid="user_teacher",
            subject_uid="user_student",
            title="Assessment",
            content="Content",
        )

        assert result.is_error
        assert "not found" in str(result.expect_error()).lower()


# ============================================================================
# GET ASSESSMENTS TESTS
# ============================================================================


class TestGetAssessments:
    """Test assessment query methods."""

    @pytest.mark.asyncio
    async def test_get_assessments_for_student(self, core_service, mock_backend):
        """Test querying assessments by student."""
        mock_backend.get_assessments_for_student_raw.return_value = Result.ok(
            [
                {
                    "report": {
                        "uid": "report_123",
                        "user_uid": "user_teacher",
                        "entity_type": "entry_report",
                        "title": "Assessment 1",
                        "subject_uid": "user_student",
                    }
                },
            ]
        )

        result = await core_service.get_assessments_for_student(
            student_uid="user_student",
            limit=10,
        )

        assert not result.is_error
        mock_backend.get_assessments_for_student_raw.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_assessments_by_teacher(self, core_service, mock_backend):
        """Test querying assessments by teacher."""
        mock_backend.find_by.return_value = Result.ok([])

        result = await core_service.get_assessments_by_teacher(
            teacher_uid="user_teacher",
            limit=10,
        )

        assert not result.is_error
