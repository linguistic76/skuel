"""
Unit Tests for Ku Types Extension
===================================

Tests EntityType enum values, display names,
is_processable, subject_uid on submission subclasses, and converter logic.
"""

from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.ku import AiReport, Curriculum, Feedback, Submission
from core.models.ku.feedback_dto import FeedbackDTO

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestKuTypeEnum:
    """Test EntityType enum extensions."""

    def test_ai_report_enum_exists(self):
        assert EntityType.AI_REPORT.value == "ai_report"

    def test_feedback_report_enum_exists(self):
        assert EntityType.FEEDBACK_REPORT.value == "feedback_report"

    def test_ai_report_display_name(self):
        assert EntityType.AI_REPORT.get_display_name() == "AI Report"

    def test_feedback_report_display_name(self):
        assert EntityType.FEEDBACK_REPORT.get_display_name() == "Feedback Report"

    def test_ai_report_is_processable(self):
        assert EntityType.AI_REPORT.is_processable() is True

    def test_feedback_report_not_processable(self):
        assert EntityType.FEEDBACK_REPORT.is_processable() is False

    def test_curriculum_not_processable(self):
        assert EntityType.CURRICULUM.is_processable() is False

    def test_assignment_is_processable(self):
        assert EntityType.SUBMISSION.is_processable() is True

    def test_curriculum_not_user_owned(self):
        assert EntityType.CURRICULUM.is_user_owned() is False

    def test_assignment_is_user_owned(self):
        assert EntityType.SUBMISSION.is_user_owned() is True

    def test_feedback_report_is_user_owned(self):
        assert EntityType.FEEDBACK_REPORT.is_user_owned() is True

    def test_is_derived(self):
        assert EntityType.SUBMISSION.is_derived() is True
        assert EntityType.AI_REPORT.is_derived() is True
        assert EntityType.FEEDBACK_REPORT.is_derived() is True
        assert EntityType.CURRICULUM.is_derived() is False


# ============================================================================
# KU MODEL TESTS
# ============================================================================


class TestKuSubjectUid:
    """Test subject_uid field on submission subclasses."""

    def test_subject_uid_defaults_none(self):
        ku = Submission(
            uid="ku_test_123",
            title="Test Ku",
            ku_type=EntityType.SUBMISSION,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.subject_uid is None

    def test_subject_uid_set_explicitly(self):
        ku = Feedback(
            uid="ku_test_123",
            title="Midterm Feedback",
            ku_type=EntityType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.subject_uid == "user_student"

    def test_is_ai_report_by_type(self):
        ku = AiReport(
            uid="ku_test_123",
            title="Progress Summary",
            ku_type=EntityType.AI_REPORT,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.ku_type == EntityType.AI_REPORT

    def test_is_feedback_report_by_type(self):
        ku = Feedback(
            uid="ku_test_123",
            title="Teacher Feedback",
            ku_type=EntityType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.ku_type == EntityType.FEEDBACK_REPORT

    def test_is_user_owned(self):
        ku = Submission(
            uid="ku_test_123",
            title="My Submission",
            ku_type=EntityType.SUBMISSION,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert ku.is_user_owned is True

    def test_curriculum_not_user_owned(self):
        ku = Curriculum(
            uid="ku_test_123",
            title="Shared Knowledge",
            ku_type=EntityType.CURRICULUM,
        )
        assert ku.is_user_owned is False


# ============================================================================
# CONVERTER TESTS
# ============================================================================


class TestKuConversions:
    """Test subject_uid roundtrips through DTO conversions."""

    def test_to_dto_preserves_subject_uid(self):
        ku = Feedback(
            uid="ku_test_123",
            title="Teacher Feedback",
            ku_type=EntityType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        dto = ku.to_dto()
        assert dto.subject_uid == "user_student"

    def test_from_dto_preserves_subject_uid(self):
        dto = FeedbackDTO(
            uid="ku_test_123",
            title="Teacher Feedback",
            ku_type=EntityType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        ku = Feedback.from_dto(dto)
        assert ku.subject_uid == "user_student"

    def test_roundtrip_none_subject_uid(self):
        ku = Submission(
            uid="ku_test_123",
            title="My Submission",
            ku_type=EntityType.SUBMISSION,
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        dto = ku.to_dto()
        restored = Submission.from_dto(dto)
        assert restored.subject_uid is None
