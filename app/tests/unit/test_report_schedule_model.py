"""
Unit Tests for ReportSchedule Model
======================================

Tests schedule creation, DTO conversions, enum values,
and compute_next_due_at logic.
"""

from datetime import datetime, timedelta

import pytest

from core.models.report.report_schedule import (
    ReportDepth,
    ReportSchedule,
    ReportScheduleDTO,
    ScheduleType,
    schedule_dto_to_pure,
    schedule_pure_to_dto,
)

# ============================================================================
# ENUM TESTS
# ============================================================================


class TestScheduleEnums:
    """Test ScheduleType and ReportDepth enums."""

    def test_schedule_type_values(self):
        assert ScheduleType.WEEKLY.value == "weekly"
        assert ScheduleType.BIWEEKLY.value == "biweekly"
        assert ScheduleType.MONTHLY.value == "monthly"

    def test_report_depth_values(self):
        assert ReportDepth.SUMMARY.value == "summary"
        assert ReportDepth.STANDARD.value == "standard"
        assert ReportDepth.DETAILED.value == "detailed"

    def test_schedule_type_from_string(self):
        assert ScheduleType("weekly") == ScheduleType.WEEKLY
        assert ScheduleType("biweekly") == ScheduleType.BIWEEKLY
        assert ScheduleType("monthly") == ScheduleType.MONTHLY


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestReportScheduleModel:
    """Test ReportSchedule frozen dataclass."""

    def test_create_schedule(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
            day_of_week=0,
        )
        assert schedule.uid == "schedule_test_123"
        assert schedule.user_uid == "user_alice"
        assert schedule.schedule_type == ScheduleType.WEEKLY
        assert schedule.day_of_week == 0
        assert schedule.is_active is True
        assert schedule.depth == "standard"
        assert schedule.domains == []

    def test_schedule_is_frozen(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
        )
        with pytest.raises(AttributeError):
            schedule.day_of_week = 3  # type: ignore[misc]

    def test_schedule_with_domains(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.BIWEEKLY,
            domains=["tasks", "goals"],
            depth="detailed",
        )
        assert schedule.domains == ["tasks", "goals"]
        assert schedule.depth == "detailed"

    def test_is_due_past_due(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
            is_active=True,
            next_due_at=datetime.now() - timedelta(hours=1),
        )
        assert schedule.is_due() is True

    def test_is_due_not_yet(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
            is_active=True,
            next_due_at=datetime.now() + timedelta(hours=1),
        )
        assert schedule.is_due() is False

    def test_is_due_inactive(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
            is_active=False,
            next_due_at=datetime.now() - timedelta(hours=1),
        )
        assert schedule.is_due() is False

    def test_get_summary(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
            day_of_week=0,
        )
        summary = schedule.get_summary()
        assert "weekly" in summary.lower()


# ============================================================================
# CONVERSION TESTS
# ============================================================================


class TestScheduleConversions:
    """Test DTO conversion functions."""

    def test_pure_to_dto(self):
        schedule = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.WEEKLY,
            day_of_week=2,
            domains=["tasks"],
            depth="detailed",
        )
        dto = schedule_pure_to_dto(schedule)
        assert isinstance(dto, ReportScheduleDTO)
        assert dto.uid == "schedule_test_123"
        assert dto.schedule_type == "weekly"
        assert dto.day_of_week == 2
        assert dto.domains == ["tasks"]
        assert dto.depth == "detailed"

    def test_dto_to_pure(self):
        dto = ReportScheduleDTO(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type="biweekly",
            day_of_week=4,
            domains=["goals", "habits"],
            depth="summary",
            is_active=False,
        )
        schedule = schedule_dto_to_pure(dto)
        assert isinstance(schedule, ReportSchedule)
        assert schedule.schedule_type == ScheduleType.BIWEEKLY
        assert schedule.day_of_week == 4
        assert schedule.domains == ["goals", "habits"]
        assert schedule.is_active is False

    def test_roundtrip(self):
        original = ReportSchedule(
            uid="schedule_test_123",
            user_uid="user_alice",
            schedule_type=ScheduleType.MONTHLY,
            day_of_week=5,
            domains=["tasks", "goals"],
            depth="standard",
            is_active=True,
        )
        dto = schedule_pure_to_dto(original)
        restored = schedule_dto_to_pure(dto)
        assert restored.uid == original.uid
        assert restored.schedule_type == original.schedule_type
        assert restored.day_of_week == original.day_of_week
        assert restored.domains == original.domains


# ============================================================================
# COMPUTE_NEXT_DUE_AT TESTS
# ============================================================================


class TestComputeNextDueAt:
    """Test schedule date computation logic."""

    def test_weekly_next_due(self):
        from core.services.reports.report_schedule_service import ReportScheduleService

        next_due = ReportScheduleService.compute_next_due_at(ScheduleType.WEEKLY, day_of_week=0)
        # Should be within 7 days
        assert next_due > datetime.now()
        assert next_due <= datetime.now() + timedelta(days=7)
        assert next_due.weekday() == 0  # Monday

    def test_biweekly_next_due(self):
        from core.services.reports.report_schedule_service import ReportScheduleService

        next_due = ReportScheduleService.compute_next_due_at(ScheduleType.BIWEEKLY, day_of_week=3)
        # Should be within 14 days
        assert next_due > datetime.now()
        assert next_due <= datetime.now() + timedelta(days=14)
        assert next_due.weekday() == 3  # Thursday

    def test_monthly_next_due(self):
        from core.services.reports.report_schedule_service import ReportScheduleService

        next_due = ReportScheduleService.compute_next_due_at(ScheduleType.MONTHLY, day_of_week=5)
        # Should be at least 28 days away
        assert next_due > datetime.now() + timedelta(days=27)
        assert next_due.weekday() == 5  # Saturday
