"""
Unit Tests for Assessment Service
=================================

Tests get_assessments_for_student on AssessmentService — the read that
surfaces a student's received teacher assessments (ADR-054 Commit 6a).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    """Create a mock UserEntry backend (received-feedback read)."""
    backend = MagicMock()
    backend.get_assessments_for_student_raw = AsyncMock()
    return backend


@pytest.fixture
def core_service(mock_backend):
    """Create AssessmentService with a mocked backend."""
    from core.services.user_entry.assessment_service import AssessmentService

    return AssessmentService(backend=mock_backend)


class TestGetAssessments:
    """Test the received-assessments query."""

    @pytest.mark.asyncio
    async def test_get_assessments_for_student(self, core_service, mock_backend):
        """Test querying assessments received by a student."""
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
    async def test_get_assessments_for_student_backend_failure(self, core_service, mock_backend):
        """Test failure propagation from the backend read."""
        from core.utils.result_simplified import Errors

        mock_backend.get_assessments_for_student_raw.return_value = Result.fail(
            Errors.database("get_assessments_for_student_raw", "read failed")
        )

        result = await core_service.get_assessments_for_student(student_uid="user_student")

        assert result.is_error
