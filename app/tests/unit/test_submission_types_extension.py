"""
Unit Tests for Submission/Report Types Extension
===================================================

Tests EntityType enum values, display names, is_processable,
subject_uid on ExerciseReport, and converter logic.

Updated for ADR-054: ExerciseSubmission, JeInput, JeOutput collapsed into UserEntry.
"""

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.report.activity_report import ActivityReport
from core.models.report.exercise_report import ExerciseReport
from core.models.report.exercise_report_dto import ExerciseReportDTO
from core.models.user_entry.user_entry import UserEntry

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestKuTypeEnum:
    """Test EntityType enum extensions."""

    def test_activity_report_enum_exists(self):
        assert EntityType.ACTIVITY_REPORT.value == "activity_report"

    def test_exercise_report_enum_exists(self):
        assert EntityType.EXERCISE_REPORT.value == "exercise_report"

    def test_user_entry_enum_exists(self):
        assert EntityType.USER_ENTRY.value == "user_entry"

    def test_activity_report_display_name(self):
        assert EntityType.ACTIVITY_REPORT.get_display_name() == "Activity Report"

    def test_exercise_report_display_name(self):
        assert EntityType.EXERCISE_REPORT.get_display_name() == "Exercise Report"

    def test_activity_report_is_processable(self):
        assert EntityType.ACTIVITY_REPORT.is_processable() is True

    def test_exercise_report_not_processable(self):
        assert EntityType.EXERCISE_REPORT.is_processable() is False

    def test_user_entry_is_processable(self):
        assert EntityType.USER_ENTRY.is_processable() is True

    def test_curriculum_not_processable(self):
        assert EntityType.KU.is_processable() is False

    def test_user_entry_display_name(self):
        assert EntityType.USER_ENTRY.get_display_name() == "User Entry"

    def test_curriculum_not_user_owned(self):
        assert EntityType.KU.is_user_owned() is False

    def test_user_entry_is_user_owned(self):
        assert EntityType.USER_ENTRY.is_user_owned() is True

    def test_exercise_report_is_user_owned(self):
        assert EntityType.EXERCISE_REPORT.is_user_owned() is True

    def test_is_derived(self):
        assert EntityType.USER_ENTRY.is_derived() is True
        assert EntityType.ACTIVITY_REPORT.is_derived() is True
        assert EntityType.EXERCISE_REPORT.is_derived() is True
        assert EntityType.KU.is_derived() is False

    def test_legacy_aliases_resolve_to_user_entry(self):
        assert EntityType.from_string("exercise_submission") == EntityType.USER_ENTRY
        assert EntityType.from_string("je_input") == EntityType.USER_ENTRY
        assert EntityType.from_string("je_output") == EntityType.USER_ENTRY


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestKuSubjectUid:
    """Test subject_uid field on ExerciseReport (the only type that carries it)."""

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
        entry = UserEntry(
            uid="ue_test_123",
            title="My Submission",
            user_uid="user_alice",
            status=EntityStatus.COMPLETED,
        )
        assert entry.is_user_owned is True

    def test_curriculum_not_user_owned(self):
        ku = Curriculum(
            uid="ku_test_123",
            title="Shared Knowledge",
            entity_type=EntityType.PATH_STEP,
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
        dto = ExerciseReportDTO(
            uid="er_test_123",
            title="Teacher Feedback",
            entity_type=EntityType.EXERCISE_REPORT,
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="user_student",
        )
        ku = ExerciseReport.from_dto(dto)
        assert ku.subject_uid == "user_student"

    def test_roundtrip_report_preserves_subject_uid(self):
        ku = ExerciseReport(
            uid="er_test_456",
            title="Teacher Feedback",
            user_uid="user_teacher",
            status=EntityStatus.COMPLETED,
            subject_uid="es_submission_uid",
        )
        dto = ku.to_dto()
        restored = ExerciseReport.from_dto(dto)
        assert restored.subject_uid == "es_submission_uid"
