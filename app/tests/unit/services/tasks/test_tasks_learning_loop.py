"""
Unit tests for Tasks adaptive learning loop (ADR-048).

Tests duration calibration via exponential moving average:
- EMA calculation correctness
- Cold-start defaults
- Ratio clamping at bounds
- Skip when missing duration data
- Performance analytics includes learned fields
- Convergence over multiple completions
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.constants import LearningLoop
from core.events.task_events import TaskCompleted
from core.models.task.task import Task
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.utils.result_simplified import Result


def _make_task(uid="task_test_abc", duration_minutes=30, actual_minutes=45, **kwargs):
    """Create a minimal Task for testing."""
    return MagicMock(
        spec=Task,
        uid=uid,
        duration_minutes=duration_minutes,
        actual_minutes=actual_minutes,
        **kwargs,
    )


def _make_event(task_uid="task_test_abc", user_uid="user_123"):
    """Create a TaskCompleted event."""
    return TaskCompleted(
        task_uid=task_uid,
        user_uid=user_uid,
        occurred_at=datetime.now(),
    )


def _make_backend():
    """Create a mock backend with learning methods."""
    backend = AsyncMock()
    backend.get = AsyncMock()
    backend.update = AsyncMock(return_value=Result.ok(True))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get_user_learning_state = AsyncMock(return_value=Result.ok({}))
    backend.update_user_learning_state = AsyncMock(return_value=Result.ok(True))
    return backend


def _make_service(backend=None):
    """Create TasksIntelligenceService with mocked backend."""
    if backend is None:
        backend = _make_backend()
    return TasksIntelligenceService(backend=backend)


class TestLearnFromCompletion:
    """Test learn_from_completion event handler."""

    @pytest.mark.asyncio
    async def test_ema_calculation_cold_start(self):
        """First completion uses EMA against default ratio of 1.0."""
        backend = _make_backend()
        task = _make_task(duration_minutes=30, actual_minutes=45)
        backend.get.return_value = Result.ok(task)
        backend.get_user_learning_state.return_value = Result.ok({})

        service = _make_service(backend)
        event = _make_event()

        await service.learn_from_completion(event)

        # ratio = 45/30 = 1.5, EMA = 0.3 * 1.5 + 0.7 * 1.0 = 1.15
        call_args = backend.update_user_learning_state.call_args[0]
        assert call_args[0] == "user_123"
        props = call_args[1]
        assert abs(props["task_duration_ratio"] - 1.15) < 0.01
        assert props["task_completion_count"] == 1

    @pytest.mark.asyncio
    async def test_ema_calculation_with_existing_state(self):
        """Subsequent completions build on existing EMA."""
        backend = _make_backend()
        task = _make_task(duration_minutes=60, actual_minutes=60)
        backend.get.return_value = Result.ok(task)
        backend.get_user_learning_state.return_value = Result.ok(
            {"task_duration_ratio": 1.5, "task_completion_count": 5}
        )

        service = _make_service(backend)
        event = _make_event()

        await service.learn_from_completion(event)

        # ratio = 60/60 = 1.0, EMA = 0.3 * 1.0 + 0.7 * 1.5 = 1.35
        props = backend.update_user_learning_state.call_args[0][1]
        assert abs(props["task_duration_ratio"] - 1.35) < 0.01
        assert props["task_completion_count"] == 6

    @pytest.mark.asyncio
    async def test_ratio_clamped_at_max(self):
        """Ratio is clamped to MAX_DURATION_RATIO."""
        backend = _make_backend()
        task = _make_task(duration_minutes=10, actual_minutes=100)
        backend.get.return_value = Result.ok(task)
        backend.get_user_learning_state.return_value = Result.ok({})

        service = _make_service(backend)
        await service.learn_from_completion(_make_event())

        # ratio = 100/10 = 10.0 -> clamped to 3.0
        # EMA = 0.3 * 3.0 + 0.7 * 1.0 = 1.6
        props = backend.update_user_learning_state.call_args[0][1]
        assert abs(props["task_duration_ratio"] - 1.6) < 0.01

    @pytest.mark.asyncio
    async def test_ratio_clamped_at_min(self):
        """Ratio is clamped to MIN_DURATION_RATIO."""
        backend = _make_backend()
        task = _make_task(duration_minutes=100, actual_minutes=1)
        backend.get.return_value = Result.ok(task)
        backend.get_user_learning_state.return_value = Result.ok({})

        service = _make_service(backend)
        await service.learn_from_completion(_make_event())

        # ratio = 1/100 = 0.01 -> clamped to 0.2
        # EMA = 0.3 * 0.2 + 0.7 * 1.0 = 0.76
        props = backend.update_user_learning_state.call_args[0][1]
        assert abs(props["task_duration_ratio"] - 0.76) < 0.01

    @pytest.mark.asyncio
    async def test_skip_when_no_estimated_duration(self):
        """Skip learning when task has no duration_minutes."""
        backend = _make_backend()
        task = _make_task(duration_minutes=None, actual_minutes=45)
        backend.get.return_value = Result.ok(task)

        service = _make_service(backend)
        await service.learn_from_completion(_make_event())

        backend.update_user_learning_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_when_no_actual_duration(self):
        """Skip learning when task has no actual_minutes."""
        backend = _make_backend()
        task = _make_task(duration_minutes=30, actual_minutes=None)
        backend.get.return_value = Result.ok(task)

        service = _make_service(backend)
        await service.learn_from_completion(_make_event())

        backend.update_user_learning_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_when_task_not_found(self):
        """Skip learning when task lookup fails."""
        backend = _make_backend()
        backend.get.return_value = Result.ok(None)

        service = _make_service(backend)
        await service.learn_from_completion(_make_event())

        backend.update_user_learning_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writes_predicted_duration_to_task(self):
        """Predicted duration is written back to the task node."""
        backend = _make_backend()
        task = _make_task(duration_minutes=30, actual_minutes=45)
        backend.get.return_value = Result.ok(task)
        backend.get_user_learning_state.return_value = Result.ok({})

        service = _make_service(backend)
        await service.learn_from_completion(_make_event())

        # predicted = round(30 * 1.15) = 34 or 35
        task_update_call = backend.update.call_args
        assert task_update_call[0][0] == "task_test_abc"
        predicted = task_update_call[0][1]["predicted_duration_minutes"]
        assert 34 <= predicted <= 35

    @pytest.mark.asyncio
    async def test_error_is_swallowed(self):
        """Errors in learn_from_completion don't propagate."""
        backend = _make_backend()
        backend.get.side_effect = Exception("DB down")

        service = _make_service(backend)
        # Should not raise
        await service.learn_from_completion(_make_event())

    @pytest.mark.asyncio
    async def test_convergence_over_multiple_completions(self):
        """EMA converges toward consistent ratio over repeated completions."""
        backend = _make_backend()
        service = _make_service(backend)

        # Simulate 10 completions where actual is always 1.5x estimated
        current_ratio = LearningLoop.DEFAULT_DURATION_RATIO
        for i in range(10):
            task = _make_task(duration_minutes=60, actual_minutes=90)
            backend.get.return_value = Result.ok(task)
            backend.get_user_learning_state.return_value = Result.ok(
                {"task_duration_ratio": current_ratio, "task_completion_count": i}
            )

            await service.learn_from_completion(_make_event())

            props = backend.update_user_learning_state.call_args[0][1]
            current_ratio = props["task_duration_ratio"]

        # After 10 samples at 1.5x, EMA should be close to 1.5
        assert abs(current_ratio - 1.5) < 0.05


class TestPerformanceAnalyticsLearningFields:
    """Test that get_performance_analytics includes learned fields."""

    @pytest.mark.asyncio
    async def test_includes_learning_state_when_present(self):
        backend = _make_backend()
        backend.find_by.return_value = Result.ok([])
        backend.get_user_learning_state.return_value = Result.ok(
            {"task_duration_ratio": 1.3, "task_completion_count": 8}
        )

        service = _make_service(backend)
        result = await service.get_performance_analytics("user_123")

        assert result.is_ok
        ls = result.value["learning_state"]
        assert ls["learned_duration_ratio"] == 1.3
        assert ls["learning_sample_count"] == 8
        assert ls["has_sufficient_learning_data"] is True

    @pytest.mark.asyncio
    async def test_insufficient_learning_data(self):
        backend = _make_backend()
        backend.find_by.return_value = Result.ok([])
        backend.get_user_learning_state.return_value = Result.ok(
            {"task_duration_ratio": 1.1, "task_completion_count": 3}
        )

        service = _make_service(backend)
        result = await service.get_performance_analytics("user_123")

        assert result.is_ok
        ls = result.value["learning_state"]
        assert ls["has_sufficient_learning_data"] is False

    @pytest.mark.asyncio
    async def test_empty_learning_state(self):
        backend = _make_backend()
        backend.find_by.return_value = Result.ok([])
        backend.get_user_learning_state.return_value = Result.ok({})

        service = _make_service(backend)
        result = await service.get_performance_analytics("user_123")

        assert result.is_ok
        ls = result.value["learning_state"]
        assert ls["learned_duration_ratio"] is None
        assert ls["learning_sample_count"] == 0
        assert ls["has_sufficient_learning_data"] is False
