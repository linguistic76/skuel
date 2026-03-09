"""
Unit Tests for Submission/Report Types Extension
===================================================

Tests EntityType enum values, display names,
is_processable, subject_uid on submission subclasses, and converter logic.
"""

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.report.activity_report import ActivityReport
from core.models.report.exercise_report import ExerciseReport
from core.models.report.submission_report import SubmissionReport
from core.models.report.submission_report_dto import SubmissionReportDTO
from core.models.submissions.exercise_submission import ExerciseSubmission
from core.models.submissions.submission import Submission

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestKuTypeEnum:
    """Test EntityType enum extensions."""

    def test_activity_report_enum_exists(self):
        assert EntityType.ACTIVITY_REPORT.value == "activity_report"

    def test_exercise_report_enum_exists(self):
        assert EntityType.EXERCISE_REPORT.value == "exercise_report"

    def test_journal_report_enum_exists(self):
        assert EntityType.JOURNAL_REPORT.value == "journal_report"

    def test_activity_report_display_name(self):
        assert EntityType.ACTIVITY_REPORT.get_display_name() == "Activity Report"

    def test_exercise_report_display_name(self):
        assert EntityType.EXERCISE_REPORT.get_display_name() == "Exercise Report"

    def test_activity_report_is_processable(self):
        assert EntityType.ACTIVITY_REPORT.is_processable() is True

    def test_exercise_report_not_processable(self):
        assert EntityType.EXERCISE_REPORT.is_processable() is False

    def test_journal_report_not_processable(self):
        assert EntityType.JOURNAL_REPORT.is_processable() is False

    def test_curriculum_not_processable(self):
        assert EntityType.KU.is_processable() is False

    def test_exercise_submission_is_processable(self):
        assert EntityType.EXERCISE_SUBMISSION.is_processable() is True

    def test_journal_submission_is_processable(self):
        assert EntityType.JOURNAL_SUBMISSION.is_processable() is True

    def test_curriculum_not_user_owned(self):
        assert EntityType.KU.is_user_owned() is False

    def test_exercise_submission_is_user_owned(self):
        assert EntityType.EXERCISE_SUBMISSION.is_user_owned() is True

    def test_exercise_report_is_user_owned(self):
        assert EntityType.EXERCISE_REPORT.is_user_owned() is True

    def test_is_derived(self):
        assert EntityType.EXERCISE_SUBMISSION.is_derived() is True
        assert EntityType.JOURNAL_SUBMISSION.is_derived() is True
        assert EntityType.ACTIVITY_REPORT.is_derived() is True
        assert EntityType.EXERCISE_REPORT.is_derived() is True
        assert EntityType.JOURNAL_REPORT.is_derived() is True
        assert EntityType.KU.is_derived() is False

    # Deprecated aliases still work
    def test_deprecated_aliases_still_work(self):
        assert EntityType.SUBMISSION.is_processable() is True
        assert EntityType.JOURNAL.is_processable() is True
        assert EntityType.SUBMISSION_REPORT.is_derived() is True


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestKuSubjectUid:
    """Test subject_uid field on submission subclasses."""

    def test_subject_uid_defaults_none(self):
        ku = ExerciseSubmission(
            uid="es_test_123",
            title="Test Submission",
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.subject_uid is None

    def test_subject_uid_set_explicitly(self):
        ku = ExerciseReport(
            uid="er_test_123",
            title="Midterm Feedback",
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.subject_uid == "user_student"

    def test_is_activity_report_by_type(self):
        ku = ActivityReport(
            uid="ar_test_123",
            title="Progress Summary",
            entity_type=EntityType.ACTIVITY_REPORT,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.entity_type == EntityType.ACTIVITY_REPORT

    def test_is_exercise_report_by_type(self):
        ku = ExerciseReport(
            uid="er_test_123",
            title="Teacher Feedback",
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.entity_type == EntityType.EXERCISE_REPORT

    def test_is_user_owned(self):
        ku = ExerciseSubmission(
            uid="es_test_123",
            title="My Submission",
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.is_user_owned is True

    def test_curriculum_not_user_owned(self):
        ku = Curriculum(
            uid="ku_test_123",
            title="Shared Knowledge",
            entity_type=EntityType.ARTICLE,
        )
        assert ku.is_user_owned is False


# ============================================================================
# CONVERTER TESTS
# ============================================================================


class TestKuConversions:
    """Test subject_uid roundtrips through DTO conversions."""

    def test_to_dto_preserves_subject_uid(self):
        ku = ExerciseReport(
            uid="er_test_123",
            title="Teacher Feedback",
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        dto = ku.to_dto()
        assert dto.subject_uid == "user_student"

    def test_from_dto_preserves_subject_uid(self):
        dto = SubmissionReportDTO(
            uid="er_test_123",
            title="Teacher Feedback",
            entity_type=EntityType.EXERCISE_REPORT,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        ku = SubmissionReport.from_dto(dto)
        assert ku.subject_uid == "user_student"

    def test_roundtrip_none_subject_uid(self):
        ku = Submission(
            uid="es_test_123",
            title="My Submission",
            entity_type=EntityType.EXERCISE_SUBMISSION,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        dto = ku.to_dto()
        restored = Submission.from_dto(dto)
        assert restored.subject_uid is None
