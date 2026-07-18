"""
Unit tests for TaskEventHandlerService.

Tests cover:
- handle_task_completed: duration calibration, overdue detection, principle alignment
- handle_task_priority_changed: categorization, cascade impact, inflation detection
- handle_tasks_bulk_completed: batch pattern classification
- Fire-and-forget contract: exceptions logged, never propagated
- Module-level helpers: _categorize_priority_change, _detect_batch_pattern
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.events.task_events import (
    TaskCompleted,
    TaskPriorityChanged,
    TasksBulkCompleted,
)
from core.models.task.task import Task
from core.services.tasks.task_event_handler_service import (
    TaskEventHandlerService,
    _categorize_priority_change,
    _detect_batch_pattern,
)
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get_user_learning_state = AsyncMock(return_value=Result.ok({}))
    backend.update_user_learning_state = AsyncMock(return_value=Result.ok({}))
    return backend


@pytest.fixture
def mock_relationships() -> AsyncMock:
    rels = AsyncMock()
    rels.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return rels


@pytest.fixture
def mock_insight_store() -> AsyncMock:
    store = AsyncMock()
    store.create_insight = AsyncMock(return_value=Result.ok(True))
    return store


@pytest.fixture
def service(mock_backend: Mock) -> TaskEventHandlerService:
    return TaskEventHandlerService(backend=mock_backend)


@pytest.fixture
def service_with_rels(mock_backend: Mock, mock_relationships: AsyncMock) -> TaskEventHandlerService:
    return TaskEventHandlerService(backend=mock_backend, relationship_service=mock_relationships)


@pytest.fixture
def service_full(
    mock_backend: Mock, mock_relationships: AsyncMock, mock_insight_store: AsyncMock
) -> TaskEventHandlerService:
    return TaskEventHandlerService(
        backend=mock_backend,
        relationship_service=mock_relationships,
        insight_store=mock_insight_store,
    )


def _make_task(
    uid: str = "task_test_abc",
    duration_minutes: int | None = None,
    actual_minutes: int | None = None,
    priority: str | None = None,
) -> Mock:
    """Create a mock task with given attributes."""
    task = Mock(spec=Task)
    task.uid = uid
    task.title = "Test Task"
    task.duration_minutes = duration_minutes
    task.actual_minutes = actual_minutes
    task.priority = priority
    return task


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestCategorizePriorityChange:
    def test_escalation(self):
        assert _categorize_priority_change("low", "high") == "escalation"

    def test_de_escalation(self):
        assert _categorize_priority_change("critical", "medium") == "de-escalation"

    def test_lateral(self):
        assert _categorize_priority_change("medium", "medium") == "lateral"

    def test_unknown_values(self):
        assert _categorize_priority_change("unknown", "high") == "lateral"

    def test_full_escalation(self):
        assert _categorize_priority_change("low", "critical") == "escalation"


class TestDetectBatchPattern:
    def test_inbox_zero_sprint(self):
        at = datetime(2026, 3, 20, 14, 0)
        assert _detect_batch_pattern(6, at) == "inbox_zero_sprint"

    def test_end_of_day_cleanup(self):
        at = datetime(2026, 3, 20, 18, 30)
        assert _detect_batch_pattern(3, at) == "end_of_day_cleanup"

    def test_routine_batch(self):
        at = datetime(2026, 3, 20, 10, 0)
        assert _detect_batch_pattern(3, at) == "routine_batch"

    def test_large_batch_overrides_time(self):
        """inbox_zero_sprint takes precedence over end_of_day_cleanup."""
        at = datetime(2026, 3, 20, 19, 0)
        assert _detect_batch_pattern(8, at) == "inbox_zero_sprint"


# ---------------------------------------------------------------------------
# handle_task_completed tests
# ---------------------------------------------------------------------------


class TestHandleTaskCompleted:
    @pytest.mark.asyncio
    async def test_duration_calibration_happy_path(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """Duration EMA calibration persists to User node."""
        task = _make_task(duration_minutes=60, actual_minutes=90)
        mock_backend.get.return_value = Result.ok(task)
        mock_backend.get_user_learning_state.return_value = Result.ok({})

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        await service.handle_task_completed(event)

        mock_backend.update_user_learning_state.assert_called_once()
        call_args = mock_backend.update_user_learning_state.call_args
        assert call_args[0][0] == "user_mike"
        state = call_args[0][1]
        assert "task_duration_ratio" in state
        assert "task_completion_count" in state
        assert state["task_completion_count"] == 1

    @pytest.mark.asyncio
    async def test_duration_calibration_missing_data(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """No calibration when task lacks duration fields."""
        task = _make_task(duration_minutes=None, actual_minutes=None)
        mock_backend.get.return_value = Result.ok(task)

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        await service.handle_task_completed(event)

        mock_backend.update_user_learning_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_duration_calibration_ema_math(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """EMA calculation produces correct result with existing state."""
        task = _make_task(duration_minutes=60, actual_minutes=60)  # ratio = 1.0
        mock_backend.get.return_value = Result.ok(task)
        mock_backend.get_user_learning_state.return_value = Result.ok(
            {
                "task_duration_ratio": 1.5,
                "task_completion_count": 5,
            }
        )

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        await service.handle_task_completed(event)

        call_args = mock_backend.update_user_learning_state.call_args
        state = call_args[0][1]
        # EMA: 0.3 * 1.0 + 0.7 * 1.5 = 0.3 + 1.05 = 1.35
        assert state["task_duration_ratio"] == 1.35
        assert state["task_completion_count"] == 6

    @pytest.mark.asyncio
    async def test_overdue_pattern_logged(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """Overdue completion is logged."""
        mock_backend.get.return_value = Result.ok(None)

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
            was_overdue=True,
        )

        with patch.object(service.logger, "info") as mock_log:
            await service.handle_task_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "Overdue" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_principle_alignment_with_relationships(
        self,
        service_with_rels: TaskEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
    ):
        """Principle alignment is checked when relationship service available."""
        mock_backend.get.return_value = Result.ok(None)
        mock_relationships.get_related_uids.return_value = Result.ok(["principle_test_123"])

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        with patch.object(service_with_rels.logger, "info") as mock_log:
            await service_with_rels.handle_task_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "principle" in str(c).lower()]
            assert len(log_calls) >= 1

    @pytest.mark.asyncio
    async def test_principle_alignment_without_relationships(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """No principle check when relationship service absent."""
        mock_backend.get.return_value = Result.ok(None)

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        # Should not raise
        await service.handle_task_completed(event)

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.get.side_effect = ServiceUnavailable("connection lost")

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        # Should NOT raise
        await service.handle_task_completed(event)


# ---------------------------------------------------------------------------
# handle_task_priority_changed tests
# ---------------------------------------------------------------------------


class TestHandleTaskPriorityChanged:
    @pytest.mark.asyncio
    async def test_escalation_logged(self, service: TaskEventHandlerService, mock_backend: Mock):
        """Priority escalation is categorized and logged."""
        mock_backend.find_by.return_value = Result.ok([])

        event = TaskPriorityChanged(
            task_uid="task_test_abc",
            user_uid="user_mike",
            old_priority="low",
            new_priority="critical",
            occurred_at=datetime.now(),
            escalated_to_urgent=True,
        )

        with patch.object(service.logger, "info") as mock_log:
            await service.handle_task_priority_changed(event)
            log_calls = [c for c in mock_log.call_args_list if "escalation" in str(c)]
            assert len(log_calls) >= 1

    @pytest.mark.asyncio
    async def test_cascade_impact_with_relationships(
        self,
        service_with_rels: TaskEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
    ):
        """Cascade impact queries dependents (incoming DEPENDS_ON) via the backend."""
        mock_backend.find_by.return_value = Result.ok([])
        # Dependents are read from the backend with direction="incoming", not the
        # relationship service (whose method_key lookup has no incoming-DEPENDS_ON key).
        mock_backend.get_related_uids = AsyncMock(
            return_value=Result.ok(["task_dep_1", "task_dep_2"])
        )

        event = TaskPriorityChanged(
            task_uid="task_test_abc",
            user_uid="user_mike",
            old_priority="medium",
            new_priority="high",
            occurred_at=datetime.now(),
        )

        with patch.object(service_with_rels.logger, "info") as mock_log:
            await service_with_rels.handle_task_priority_changed(event)
            log_calls = [c for c in mock_log.call_args_list if "dependent" in str(c).lower()]
            assert len(log_calls) >= 1

    @pytest.mark.asyncio
    async def test_priority_inflation_detection(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """Warns when >60% of tasks are high/critical priority."""
        high_tasks = [_make_task(priority="high") for _ in range(4)]
        low_tasks = [_make_task(priority="low") for _ in range(1)]
        mock_backend.find_by.return_value = Result.ok(high_tasks + low_tasks)

        event = TaskPriorityChanged(
            task_uid="task_test_abc",
            user_uid="user_mike",
            old_priority="medium",
            new_priority="high",
            occurred_at=datetime.now(),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_task_priority_changed(event)
            warn_calls = [c for c in mock_warn.call_args_list if "inflation" in str(c).lower()]
            assert len(warn_calls) >= 1

    @pytest.mark.asyncio
    async def test_fire_and_forget_priority(
        self, service: TaskEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.find_by.side_effect = ServiceUnavailable("connection lost")

        event = TaskPriorityChanged(
            task_uid="task_test_abc",
            user_uid="user_mike",
            old_priority="low",
            new_priority="high",
            occurred_at=datetime.now(),
        )

        # Should NOT raise
        await service.handle_task_priority_changed(event)


# ---------------------------------------------------------------------------
# handle_tasks_bulk_completed tests
# ---------------------------------------------------------------------------


class TestHandleTasksBulkCompleted:
    @pytest.mark.asyncio
    async def test_batch_pattern_logged(self, service: TaskEventHandlerService):
        """Batch pattern is detected and logged."""
        event = TasksBulkCompleted(
            task_uids=["t1", "t2", "t3", "t4", "t5", "t6"],
            user_uid="user_mike",
            occurred_at=datetime(2026, 3, 20, 14, 0),
        )

        with patch.object(service.logger, "info") as mock_log:
            service.handle_tasks_bulk_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "inbox_zero_sprint" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_end_of_day_pattern(self, service: TaskEventHandlerService):
        """End-of-day cleanup pattern detected for evening batches."""
        event = TasksBulkCompleted(
            task_uids=["t1", "t2"],
            user_uid="user_mike",
            occurred_at=datetime(2026, 3, 20, 18, 30),
        )

        with patch.object(service.logger, "info") as mock_log:
            service.handle_tasks_bulk_completed(event)
            log_calls = [c for c in mock_log.call_args_list if "end_of_day_cleanup" in str(c)]
            assert len(log_calls) == 1


# ---------------------------------------------------------------------------
# Insight persistence tests
# ---------------------------------------------------------------------------


class TestInsightPersistence:
    @pytest.mark.asyncio
    async def test_overdue_completion_persists_insight(
        self,
        service_full: TaskEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        """Overdue task completion persists a COMPLETION_PATTERN insight."""
        mock_backend.get.return_value = Result.ok(None)

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
            was_overdue=True,
        )

        await service_full.handle_task_completed(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.insight_type.value == "completion_pattern"
        assert insight.domain == "tasks"
        assert insight.impact.value == "medium"

    @pytest.mark.asyncio
    async def test_no_insight_when_not_overdue(
        self,
        service_full: TaskEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        """Non-overdue completion does not persist overdue insight."""
        mock_backend.get.return_value = Result.ok(None)

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
            was_overdue=False,
        )

        await service_full.handle_task_completed(event)

        # No overdue insight (principle alignment may or may not fire)
        overdue_calls = [
            c for c in mock_insight_store.create_insight.call_args_list if "Overdue" in str(c)
        ]
        assert len(overdue_calls) == 0

    @pytest.mark.asyncio
    async def test_priority_inflation_persists_insight(
        self,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        """Priority inflation >60% persists an IMBALANCE_DETECTED insight."""
        service = TaskEventHandlerService(backend=mock_backend, insight_store=mock_insight_store)
        high_tasks = [_make_task(priority="high") for _ in range(4)]
        low_tasks = [_make_task(priority="low") for _ in range(1)]
        mock_backend.find_by.return_value = Result.ok(high_tasks + low_tasks)

        event = TaskPriorityChanged(
            task_uid="task_test_abc",
            user_uid="user_mike",
            old_priority="medium",
            new_priority="high",
            occurred_at=datetime.now(),
        )

        await service.handle_task_priority_changed(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert insight.insight_type.value == "imbalance_detected"
        assert insight.impact.value == "high"

    @pytest.mark.asyncio
    async def test_principle_alignment_persists_insight(
        self,
        service_full: TaskEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
        mock_insight_store: AsyncMock,
    ):
        """Principle alignment on completion persists a PRINCIPLE_ALIGNMENT insight."""
        mock_backend.get.return_value = Result.ok(None)
        mock_relationships.get_related_uids.return_value = Result.ok(["principle_test_123"])

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
        )

        await service_full.handle_task_completed(event)

        # Should have principle alignment insight
        alignment_calls = [
            c
            for c in mock_insight_store.create_insight.call_args_list
            if "Principle" in str(c) or "principle_alignment" in str(c)
        ]
        assert len(alignment_calls) >= 1

    @pytest.mark.asyncio
    async def test_insight_failure_does_not_propagate(
        self,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
    ):
        """Failed insight creation is logged but does not propagate."""
        service = TaskEventHandlerService(backend=mock_backend, insight_store=mock_insight_store)
        mock_backend.get.return_value = Result.ok(None)
        mock_insight_store.create_insight.return_value = Result(
            _error=Errors.database("create_insight", "InsightStore unavailable")
        )

        event = TaskCompleted(
            task_uid="task_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
            was_overdue=True,
        )

        # Should NOT raise
        await service.handle_task_completed(event)
