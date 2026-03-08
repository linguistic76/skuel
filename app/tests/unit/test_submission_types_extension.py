"""
Unit Tests for Ku Types Extension
===================================

Tests EntityType enum values, display names,
is_processable, subject_uid on submission subclasses, and converter logic.
"""

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.feedback.activity_report import ActivityReport
from core.models.feedback.submission_feedback import SubmissionFeedback
from core.models.feedback.submission_feedback_dto import SubmissionFeedbackDTO
from core.models.submissions.submission import Submission

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestKuTypeEnum:
    """Test EntityType enum extensions."""

    def test_ai_feedback_enum_exists(self):
        assert EntityType.ACTIVITY_REPORT.value == "activity_report"

    def test_feedback_report_enum_exists(self):
        assert EntityType.SUBMISSION_FEEDBACK.value == "submission_feedback"

    def test_ai_feedback_display_name(self):
        assert EntityType.ACTIVITY_REPORT.get_display_name() == "Activity Report"

    def test_feedback_report_display_name(self):
        assert EntityType.SUBMISSION_FEEDBACK.get_display_name() == "Submission Feedback"

    def test_ai_feedback_is_processable(self):
        assert EntityType.ACTIVITY_REPORT.is_processable() is True

    def test_feedback_report_not_processable(self):
        assert EntityType.SUBMISSION_FEEDBACK.is_processable() is False

    def test_curriculum_not_processable(self):
        assert EntityType.KU.is_processable() is False

    def test_assignment_is_processable(self):
        assert EntityType.SUBMISSION.is_processable() is True

    def test_curriculum_not_user_owned(self):
        assert EntityType.KU.is_user_owned() is False

    def test_assignment_is_user_owned(self):
        assert EntityType.SUBMISSION.is_user_owned() is True

    def test_feedback_report_is_user_owned(self):
        assert EntityType.SUBMISSION_FEEDBACK.is_user_owned() is True

    def test_is_derived(self):
        assert EntityType.SUBMISSION.is_derived() is True
        assert EntityType.ACTIVITY_REPORT.is_derived() is True
        assert EntityType.SUBMISSION_FEEDBACK.is_derived() is True
        assert EntityType.KU.is_derived() is False


# ============================================================================
# KU MODEL TESTS
# ============================================================================


class TestKuSubjectUid:
    """Test subject_uid field on submission subclasses."""

    def test_subject_uid_defaults_none(self):
        ku = Submission(
            uid="ku_test_123",
            title="Test Ku",
            entity_type=EntityType.SUBMISSION,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.subject_uid is None

    def test_subject_uid_set_explicitly(self):
        ku = SubmissionFeedback(
            uid="ku_test_123",
            title="Midterm Feedback",
            entity_type=EntityType.SUBMISSION_FEEDBACK,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.subject_uid == "user_student"

    def test_is_ai_feedback_by_type(self):
        ku = ActivityReport(
            uid="ku_test_123",
            title="Progress Summary",
            entity_type=EntityType.ACTIVITY_REPORT,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.entity_type == EntityType.ACTIVITY_REPORT

    def test_is_feedback_report_by_type(self):
        ku = SubmissionFeedback(
            uid="ku_test_123",
            title="Teacher Feedback",
            entity_type=EntityType.SUBMISSION_FEEDBACK,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.entity_type == EntityType.SUBMISSION_FEEDBACK

    def test_is_user_owned(self):
        ku = Submission(
            uid="ku_test_123",
            title="My Submission",
            entity_type=EntityType.SUBMISSION,
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
        ku = SubmissionFeedback(
            uid="ku_test_123",
            title="Teacher Feedback",
            entity_type=EntityType.SUBMISSION_FEEDBACK,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        dto = ku.to_dto()
        assert dto.subject_uid == "user_student"

    def test_from_dto_preserves_subject_uid(self):
        dto = SubmissionFeedbackDTO(
            uid="ku_test_123",
            title="Teacher Feedback",
            entity_type=EntityType.SUBMISSION_FEEDBACK,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        ku = SubmissionFeedback.from_dto(dto)
        assert ku.subject_uid == "user_student"

    def test_roundtrip_none_subject_uid(self):
        ku = Submission(
            uid="ku_test_123",
            title="My Submission",
            entity_type=EntityType.SUBMISSION,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        dto = ku.to_dto()
        restored = Submission.from_dto(dto)
        assert restored.subject_uid is None
