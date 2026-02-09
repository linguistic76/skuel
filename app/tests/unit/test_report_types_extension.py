"""
Unit Tests for Report Types Extension
=======================================

Tests PROGRESS and ASSESSMENT enum values, display names,
is_file_based, subject_uid on Report, and converter logic.
"""

from core.models.enums.report_enums import ReportStatus, ReportType
from core.models.report.report import Report, ReportDTO, report_dto_to_pure, report_pure_to_dto

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestReportTypeEnum:
    """Test ReportType enum extensions."""

    def test_progress_enum_exists(self):
        assert ReportType.PROGRESS.value == "progress"

    def test_assessment_enum_exists(self):
        assert ReportType.ASSESSMENT.value == "assessment"

    def test_progress_display_name(self):
        assert ReportType.PROGRESS.get_display_name() == "Progress Report"

    def test_assessment_display_name(self):
        assert ReportType.ASSESSMENT.get_display_name() == "Teacher Assessment"

    def test_progress_not_file_based(self):
        assert ReportType.PROGRESS.is_file_based() is False

    def test_assessment_not_file_based(self):
        assert ReportType.ASSESSMENT.is_file_based() is False

    def test_transcript_is_file_based(self):
        assert ReportType.TRANSCRIPT.is_file_based() is True

    def test_assignment_is_file_based(self):
        assert ReportType.ASSIGNMENT.is_file_based() is True

    def test_journal_is_file_based(self):
        assert ReportType.JOURNAL.is_file_based() is True

    def test_is_progress(self):
        assert ReportType.PROGRESS.is_progress() is True
        assert ReportType.ASSESSMENT.is_progress() is False

    def test_is_assessment(self):
        assert ReportType.ASSESSMENT.is_assessment() is True
        assert ReportType.PROGRESS.is_assessment() is False

    def test_is_system_generated(self):
        assert ReportType.PROGRESS.is_system_generated() is True
        assert ReportType.ASSESSMENT.is_system_generated() is False
        assert ReportType.TRANSCRIPT.is_system_generated() is False


# ============================================================================
# REPORT MODEL TESTS
# ============================================================================


class TestReportSubjectUid:
    """Test subject_uid field on Report."""

    def test_subject_uid_defaults_none(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_alice",
            report_type=ReportType.TRANSCRIPT,
            status=ReportStatus.COMPLETED,
        )
        assert report.subject_uid is None

    def test_subject_uid_set_explicitly(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_teacher",
            report_type=ReportType.ASSESSMENT,
            status=ReportStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert report.subject_uid == "user_student"

    def test_progress_defaults_subject_to_self(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_alice",
            report_type=ReportType.PROGRESS,
            status=ReportStatus.COMPLETED,
        )
        assert report.subject_uid == "user_alice"

    def test_assessment_defaults_subject_to_self(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_teacher",
            report_type=ReportType.ASSESSMENT,
            status=ReportStatus.COMPLETED,
        )
        assert report.subject_uid == "user_teacher"

    def test_is_progress_report_property(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_alice",
            report_type=ReportType.PROGRESS,
            status=ReportStatus.COMPLETED,
        )
        assert report.is_progress_report is True

    def test_is_assessment_property(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_teacher",
            report_type=ReportType.ASSESSMENT,
            status=ReportStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert report.is_assessment is True

    def test_is_about_self(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_alice",
            report_type=ReportType.PROGRESS,
            status=ReportStatus.COMPLETED,
        )
        assert report.is_about_self is True

    def test_is_about_other(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_teacher",
            report_type=ReportType.ASSESSMENT,
            status=ReportStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert report.is_about_self is False


# ============================================================================
# CONVERTER TESTS
# ============================================================================


class TestReportConversions:
    """Test subject_uid roundtrips through DTO conversions."""

    def test_pure_to_dto_preserves_subject_uid(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_teacher",
            report_type=ReportType.ASSESSMENT,
            status=ReportStatus.COMPLETED,
            subject_uid="user_student",
        )
        dto = report_pure_to_dto(report)
        assert dto.subject_uid == "user_student"

    def test_dto_to_pure_preserves_subject_uid(self):
        dto = ReportDTO(
            uid="report_test_123",
            user_uid="user_teacher",
            report_type=ReportType.ASSESSMENT.value,
            status="completed",
            subject_uid="user_student",
        )
        report = report_dto_to_pure(dto)
        assert report.subject_uid == "user_student"

    def test_roundtrip_none_subject_uid(self):
        report = Report(
            uid="report_test_123",
            user_uid="user_alice",
            report_type=ReportType.TRANSCRIPT,
            status=ReportStatus.COMPLETED,
        )
        dto = report_pure_to_dto(report)
        restored = report_dto_to_pure(dto)
        assert restored.subject_uid is None
