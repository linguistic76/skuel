"""
Unit tests for LearningLoopEventHandlerService.

Tests cover:
- Module-level helpers: _classify_iteration_count, _classify_mastery_velocity, _is_feedback_anomaly
- handle_submission_created: skip guard, first attempt, iteration insight, error isolation, no insight_store
- handle_report_submitted: turnaround calc, EMA update, fast/slow anomaly, submission not found
- handle_submission_approved: skip guard, quick mastery, persistent learner, no exercise, error isolation
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from neo4j.exceptions import ServiceUnavailable

from core.events.learning_loop_events import ReportSubmitted, UserEntryApproved
from core.events.user_entry_events import UserEntryCreated
from core.services.user_entry.learning_loop_handler import (
    LearningLoopEventHandlerService,
    _classify_iteration_count,
    _classify_mastery_velocity,
    _is_feedback_anomaly,
)
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.count_entries_for_exercise = AsyncMock(return_value=Result.ok(1))
    backend.get_first_entry_for_exercise = AsyncMock(return_value=Result.ok(None))
    backend.get_exercise_for_entry = AsyncMock(return_value=Result.ok(None))
    backend.get_teacher_feedback_state = AsyncMock(return_value=Result.ok({}))
    backend.update_teacher_feedback_state = AsyncMock(return_value=Result.ok(True))
    return backend


@pytest.fixture
def mock_insight_store() -> AsyncMock:
    store = AsyncMock()
    store.create_insight = AsyncMock(return_value=Result.ok("insight_uid"))
    return store


@pytest.fixture
def service(mock_backend: Mock) -> LearningLoopEventHandlerService:
    return LearningLoopEventHandlerService(backend=mock_backend)


@pytest.fixture
def service_with_insights(
    mock_backend: Mock, mock_insight_store: AsyncMock
) -> LearningLoopEventHandlerService:
    return LearningLoopEventHandlerService(backend=mock_backend, insight_store=mock_insight_store)


def _make_submission_created(
    submission_uid: str = "es_test_abc",
    user_uid: str = "user_test",
    fulfills_exercise_uid: str | None = "exercise_abc",
) -> UserEntryCreated:
    return UserEntryCreated(
        entity_uid=submission_uid,
        user_uid=user_uid,
        pipeline="none",
        occurred_at=datetime.now(),
        fulfills_exercise_uid=fulfills_exercise_uid,
    )


def _make_report_submitted(
    submission_uid: str = "es_test_abc",
    teacher_uid: str = "user_teacher",
    student_uid: str = "user_student",
    report_uid: str = "sr_test_abc",
    occurred_at: datetime | None = None,
) -> ReportSubmitted:
    return ReportSubmitted(
        submission_uid=submission_uid,
        teacher_uid=teacher_uid,
        student_uid=student_uid,
        report_uid=report_uid,
        occurred_at=occurred_at or datetime.now(),
    )


def _make_submission_approved(
    submission_uid: str = "es_test_abc",
    teacher_uid: str = "user_teacher",
    student_uid: str = "user_student",
    mastered_ku_count: int = 2,
    occurred_at: datetime | None = None,
) -> UserEntryApproved:
    return UserEntryApproved(
        entity_uid=submission_uid,
        teacher_uid=teacher_uid,
        student_uid=student_uid,
        occurred_at=occurred_at or datetime.now(),
        mastered_ku_count=mastered_ku_count,
    )


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestClassifyIterationCount:
    def test_first_attempt(self):
        assert _classify_iteration_count(1) == "first_attempt"

    def test_zero(self):
        assert _classify_iteration_count(0) == "first_attempt"

    def test_second_attempt(self):
        assert _classify_iteration_count(2) == "second_attempt"

    def test_persistent(self):
        assert _classify_iteration_count(3) == "persistent"
        assert _classify_iteration_count(4) == "persistent"

    def test_extended_effort(self):
        assert _classify_iteration_count(5) == "extended_effort"
        assert _classify_iteration_count(10) == "extended_effort"


class TestClassifyMasteryVelocity:
    def test_quick_mastery(self):
        assert _classify_mastery_velocity(1, 24.0) == "quick_mastery"
        assert _classify_mastery_velocity(2, 40.0) == "quick_mastery"

    def test_standard(self):
        assert _classify_mastery_velocity(2, 72.0) == "standard"

    def test_persistent_learner(self):
        assert _classify_mastery_velocity(3, 100.0) == "persistent_learner"
        assert _classify_mastery_velocity(5, 200.0) == "persistent_learner"


class TestIsFeedbackAnomaly:
    def test_fast_anomaly(self):
        is_anomaly, anomaly_type = _is_feedback_anomaly(10.0, 48.0)
        assert is_anomaly is True
        assert anomaly_type == "fast"

    def test_slow_anomaly(self):
        is_anomaly, anomaly_type = _is_feedback_anomaly(100.0, 48.0)
        assert is_anomaly is True
        assert anomaly_type == "slow"

    def test_normal(self):
        is_anomaly, _ = _is_feedback_anomaly(48.0, 48.0)
        assert is_anomaly is False

    def test_zero_ema(self):
        is_anomaly, _ = _is_feedback_anomaly(10.0, 0.0)
        assert is_anomaly is False


# ---------------------------------------------------------------------------
# handle_submission_created tests
# ---------------------------------------------------------------------------


class TestHandleSubmissionCreated:
    @pytest.mark.anyio
    async def test_skips_without_exercise_uid(
        self, service: LearningLoopEventHandlerService, mock_backend: Mock
    ):
        event = _make_submission_created(fulfills_exercise_uid=None)
        await service.handle_submission_created(event)
        mock_backend.count_entries_for_exercise.assert_not_called()

    @pytest.mark.anyio
    async def test_first_attempt_no_insight(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        mock_backend.count_entries_for_exercise.return_value = Result.ok(1)
        event = _make_submission_created()
        await service_with_insights.handle_submission_created(event)
        mock_insight_store.create_insight.assert_not_called()

    @pytest.mark.anyio
    async def test_third_attempt_persists_insight(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        mock_backend.count_entries_for_exercise.return_value = Result.ok(3)
        event = _make_submission_created()
        await service_with_insights.handle_submission_created(event)
        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.domain == "user_entry"
        assert insight.supporting_data["iteration_count"] == 3
        assert insight.supporting_data["classification"] == "persistent"

    @pytest.mark.anyio
    async def test_error_isolation(self, mock_backend: Mock):
        """Errors are logged, never propagated."""
        mock_backend.count_entries_for_exercise.side_effect = ServiceUnavailable("boom")
        svc = LearningLoopEventHandlerService(backend=mock_backend)
        event = _make_submission_created()
        # Should not raise
        await svc.handle_submission_created(event)

    @pytest.mark.anyio
    async def test_no_insight_store(
        self, service: LearningLoopEventHandlerService, mock_backend: Mock
    ):
        """Works without insight_store — just logs."""
        mock_backend.count_entries_for_exercise.return_value = Result.ok(3)
        event = _make_submission_created()
        await service.handle_submission_created(event)
        # No error, no insight persisted (no store)


# ---------------------------------------------------------------------------
# handle_report_submitted tests
# ---------------------------------------------------------------------------


class TestHandleReportSubmitted:
    @pytest.mark.anyio
    async def test_turnaround_calc_and_ema_update(
        self, service_with_insights: LearningLoopEventHandlerService, mock_backend: Mock
    ):
        # Submission created 24 hours ago
        submission_created = datetime.now() - timedelta(hours=24)
        mock_sub = Mock()
        mock_sub.created_at = submission_created
        mock_backend.get.return_value = Result.ok(mock_sub)
        mock_backend.get_teacher_feedback_state.return_value = Result.ok(
            {
                "feedback_ema_hours": 48.0,
                "feedback_sample_count": 1,
            }
        )

        event = _make_report_submitted(occurred_at=datetime.now())
        await service_with_insights.handle_report_submitted(event)

        mock_backend.update_teacher_feedback_state.assert_called_once()
        call_props = mock_backend.update_teacher_feedback_state.call_args[0][1]
        assert "feedback_ema_hours" in call_props
        assert call_props["feedback_sample_count"] == 2

    @pytest.mark.anyio
    async def test_submission_not_found(
        self, service_with_insights: LearningLoopEventHandlerService, mock_backend: Mock
    ):
        mock_backend.get.return_value = Result.fail(
            Errors.not_found(resource="Submission", identifier="x")
        )
        event = _make_report_submitted()
        await service_with_insights.handle_report_submitted(event)
        mock_backend.update_teacher_feedback_state.assert_not_called()

    @pytest.mark.anyio
    async def test_fast_anomaly_insight(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        # Submission created 2 hours ago, EMA is 48h — fast anomaly
        submission_created = datetime.now() - timedelta(hours=2)
        mock_sub = Mock()
        mock_sub.created_at = submission_created
        mock_backend.get.return_value = Result.ok(mock_sub)
        mock_backend.get_teacher_feedback_state.return_value = Result.ok(
            {
                "feedback_ema_hours": 48.0,
                "feedback_sample_count": 5,  # Above MIN_SAMPLES_FEEDBACK
            }
        )

        event = _make_report_submitted(occurred_at=datetime.now())
        await service_with_insights.handle_report_submitted(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.supporting_data["anomaly_type"] == "fast"

    @pytest.mark.anyio
    async def test_slow_anomaly_insight(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        # Submission created 200 hours ago, EMA is 48h — slow anomaly
        # new_ema = 0.3*200 + 0.7*48 = 60+33.6 = 93.6, ratio = 200/93.6 ≈ 2.14 > 2.0
        submission_created = datetime.now() - timedelta(hours=200)
        mock_sub = Mock()
        mock_sub.created_at = submission_created
        mock_backend.get.return_value = Result.ok(mock_sub)
        mock_backend.get_teacher_feedback_state.return_value = Result.ok(
            {
                "feedback_ema_hours": 48.0,
                "feedback_sample_count": 5,
            }
        )

        event = _make_report_submitted(occurred_at=datetime.now())
        await service_with_insights.handle_report_submitted(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.supporting_data["anomaly_type"] == "slow"

    @pytest.mark.anyio
    async def test_no_anomaly_below_sample_threshold(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        # Fast turnaround, but only 1 sample — no anomaly insight
        submission_created = datetime.now() - timedelta(hours=2)
        mock_sub = Mock()
        mock_sub.created_at = submission_created
        mock_backend.get.return_value = Result.ok(mock_sub)
        mock_backend.get_teacher_feedback_state.return_value = Result.ok(
            {
                "feedback_ema_hours": 48.0,
                "feedback_sample_count": 1,
            }
        )

        event = _make_report_submitted(occurred_at=datetime.now())
        await service_with_insights.handle_report_submitted(event)

        mock_insight_store.create_insight.assert_not_called()


# ---------------------------------------------------------------------------
# handle_submission_approved tests
# ---------------------------------------------------------------------------


class TestHandleSubmissionApproved:
    @pytest.mark.anyio
    async def test_skips_zero_mastery(
        self, service_with_insights: LearningLoopEventHandlerService, mock_backend: Mock
    ):
        event = _make_submission_approved(mastered_ku_count=0)
        await service_with_insights.handle_submission_approved(event)
        mock_backend.get_exercise_for_entry.assert_not_called()

    @pytest.mark.anyio
    async def test_quick_mastery_insight(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        now = datetime.now()
        mock_backend.get_exercise_for_entry.return_value = Result.ok("exercise_abc")
        mock_backend.count_entries_for_exercise.return_value = Result.ok(1)
        mock_backend.get_first_entry_for_exercise.return_value = Result.ok(
            {
                "uid": "es_test_abc",
                "created_at": now - timedelta(hours=12),
            }
        )

        event = _make_submission_approved(occurred_at=now, mastered_ku_count=3)
        await service_with_insights.handle_submission_approved(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.insight_type.value == "mastery_achieved"
        assert insight.supporting_data["velocity"] == "quick_mastery"
        assert insight.supporting_data["mastered_ku_count"] == 3

    @pytest.mark.anyio
    async def test_persistent_learner_insight(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        now = datetime.now()
        mock_backend.get_exercise_for_entry.return_value = Result.ok("exercise_abc")
        mock_backend.count_entries_for_exercise.return_value = Result.ok(5)
        mock_backend.get_first_entry_for_exercise.return_value = Result.ok(
            {
                "uid": "es_first",
                "created_at": now - timedelta(hours=200),
            }
        )

        event = _make_submission_approved(occurred_at=now, mastered_ku_count=1)
        await service_with_insights.handle_submission_approved(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.insight_type.value == "learning_progress"
        assert insight.supporting_data["velocity"] == "persistent_learner"

    @pytest.mark.anyio
    async def test_no_exercise_found(
        self,
        service_with_insights: LearningLoopEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        mock_backend.get_exercise_for_entry.return_value = Result.ok(None)
        event = _make_submission_approved(mastered_ku_count=2)
        await service_with_insights.handle_submission_approved(event)
        mock_insight_store.create_insight.assert_not_called()

    @pytest.mark.anyio
    async def test_error_isolation(self, mock_backend: Mock):
        """Errors are logged, never propagated."""
        mock_backend.get_exercise_for_entry.side_effect = ServiceUnavailable("boom")
        svc = LearningLoopEventHandlerService(backend=mock_backend)
        event = _make_submission_approved(mastered_ku_count=2)
        # Should not raise
        await svc.handle_submission_approved(event)
