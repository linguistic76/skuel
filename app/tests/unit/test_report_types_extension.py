"""
Unit Tests for Ku Types Extension
===================================

Tests KuType enum values, display names,
is_processable, subject_uid on submission subclasses, and converter logic.
"""

from core.models.enums.ku_enums import KuStatus, KuType
from core.models.ku import AiReportKu, CurriculumKu, FeedbackKu, KuDTO, SubmissionKu

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestKuTypeEnum:
    """Test KuType enum extensions."""

    def test_ai_report_enum_exists(self):
        assert KuType.AI_REPORT.value == "ai_report"

    def test_feedback_report_enum_exists(self):
        assert KuType.FEEDBACK_REPORT.value == "feedback_report"

    def test_ai_report_display_name(self):
        assert KuType.AI_REPORT.get_display_name() == "AI Report"

    def test_feedback_report_display_name(self):
        assert KuType.FEEDBACK_REPORT.get_display_name() == "Feedback Report"

    def test_ai_report_is_processable(self):
        assert KuType.AI_REPORT.is_processable() is True

    def test_feedback_report_not_processable(self):
        assert KuType.FEEDBACK_REPORT.is_processable() is False

    def test_curriculum_not_processable(self):
        assert KuType.CURRICULUM.is_processable() is False

    def test_assignment_is_processable(self):
        assert KuType.SUBMISSION.is_processable() is True

    def test_curriculum_not_user_owned(self):
        assert KuType.CURRICULUM.is_user_owned() is False

    def test_assignment_is_user_owned(self):
        assert KuType.SUBMISSION.is_user_owned() is True

    def test_feedback_report_is_user_owned(self):
        assert KuType.FEEDBACK_REPORT.is_user_owned() is True

    def test_is_derived(self):
        assert KuType.SUBMISSION.is_derived() is True
        assert KuType.AI_REPORT.is_derived() is True
        assert KuType.FEEDBACK_REPORT.is_derived() is True
        assert KuType.CURRICULUM.is_derived() is False


# ============================================================================
# KU MODEL TESTS
# ============================================================================


class TestKuSubjectUid:
    """Test subject_uid field on submission subclasses."""

    def test_subject_uid_defaults_none(self):
        ku = SubmissionKu(
            uid="ku_test_123",
            title="Test Ku",
            ku_type=KuType.SUBMISSION,
            user_uid="user_alice",
            status=KuStatus.COMPLETED,
        )
        assert ku.subject_uid is None

    def test_subject_uid_set_explicitly(self):
        ku = FeedbackKu(
            uid="ku_test_123",
            title="Midterm Feedback",
            ku_type=KuType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=KuStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.subject_uid == "user_student"

    def test_is_ai_report_property(self):
        ku = AiReportKu(
            uid="ku_test_123",
            title="Progress Summary",
            ku_type=KuType.AI_REPORT,
            user_uid="user_alice",
            status=KuStatus.COMPLETED,
        )
        assert ku.is_ai_report is True

    def test_is_feedback_report_property(self):
        ku = FeedbackKu(
            uid="ku_test_123",
            title="Teacher Feedback",
            ku_type=KuType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=KuStatus.COMPLETED,
            subject_uid="user_student",
        )
        assert ku.is_feedback_report is True

    def test_is_user_owned(self):
        ku = SubmissionKu(
            uid="ku_test_123",
            title="My Submission",
            ku_type=KuType.SUBMISSION,
            user_uid="user_alice",
            status=KuStatus.COMPLETED,
        )
        assert ku.is_user_owned is True

    def test_curriculum_not_user_owned(self):
        ku = CurriculumKu(
            uid="ku_test_123",
            title="Shared Knowledge",
            ku_type=KuType.CURRICULUM,
        )
        assert ku.is_user_owned is False


# ============================================================================
# CONVERTER TESTS
# ============================================================================


class TestKuConversions:
    """Test subject_uid roundtrips through DTO conversions."""

    def test_to_dto_preserves_subject_uid(self):
        ku = FeedbackKu(
            uid="ku_test_123",
            title="Teacher Feedback",
            ku_type=KuType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=KuStatus.COMPLETED,
            subject_uid="user_student",
        )
        dto = ku.to_dto()
        assert dto.subject_uid == "user_student"

    def test_from_dto_preserves_subject_uid(self):
        dto = KuDTO(
            uid="ku_test_123",
            title="Teacher Feedback",
            ku_type=KuType.FEEDBACK_REPORT,
            user_uid="user_teacher",
            status=KuStatus.COMPLETED,
            subject_uid="user_student",
        )
        ku = FeedbackKu.from_dto(dto)
        assert ku.subject_uid == "user_student"

    def test_roundtrip_none_subject_uid(self):
        ku = SubmissionKu(
            uid="ku_test_123",
            title="My Submission",
            ku_type=KuType.SUBMISSION,
            user_uid="user_alice",
            status=KuStatus.COMPLETED,
        )
        dto = ku.to_dto()
        restored = SubmissionKu.from_dto(dto)
        assert restored.subject_uid is None
