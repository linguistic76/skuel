"""
Performance Monitoring Tests
=============================

Tests for event system performance monitoring, bottleneck detection,
and context invalidation tracking.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events.base import BaseEvent
from core.infrastructure.monitoring import (
    get_performance_monitor,
    reset_performance_monitor,
)

if TYPE_CHECKING:
    from collections.abc import Generator

# ============================================================================
# TEST EVENTS
# ============================================================================


@dataclass(frozen=True)
class SampleEvent(BaseEvent):
    """Sample event for performance monitoring tests."""

    user_uid: str
    occurred_at: datetime

    @property
    def event_type(self) -> str:
        return "test.event"


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def performance_monitor() -> "Generator[Any, None, None]":
    """Create fresh performance monitor for each test."""
    reset_performance_monitor()
    monitor = get_performance_monitor(
        enabled=True,
        slow_handler_threshold_ms=50.0,  # Lower threshold for testing
        retention_hours=1,
    )
    yield monitor
    reset_performance_monitor()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    """Create event bus with performance monitoring enabled."""
    return InMemoryEventBus(capture_history=False, enable_performance_monitoring=True)


# ============================================================================
# PERFORMANCE MONITOR TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handler_metrics_recording(performance_monitor):
    """Test that handler execution is recorded."""
    # Record handler execution
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="test_handler", duration_ms=45.0, error=None
    )

    # Get metrics
    metrics = await performance_monitor.get_handler_metrics()

    assert len(metrics) == 1
    assert metrics[0]["handler_name"] == "test_handler"
    assert metrics[0]["event_type"] == "test.event"
    assert metrics[0]["total_calls"] == 1
    assert metrics[0]["avg_duration_ms"] == 45.0


@pytest.mark.asyncio
async def test_slow_handler_detection(performance_monitor):
    """Test detection of slow handlers."""
    # Record fast handler
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="fast_handler", duration_ms=10.0, error=None
    )

    # Record slow handler (above 50ms threshold)
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="slow_handler", duration_ms=120.0, error=None
    )

    # Get slow handlers
    slow_handlers = await performance_monitor.get_slow_handlers(threshold_ms=50.0)

    assert len(slow_handlers) == 1
    assert slow_handlers[0]["handler_name"] == "slow_handler"
    assert slow_handlers[0]["recent_avg_duration_ms"] > 50.0


@pytest.mark.asyncio
async def test_handler_error_tracking(performance_monitor):
    """Test that handler errors are tracked."""
    error = ValueError("Test error")

    # Record successful execution
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="error_handler", duration_ms=30.0, error=None
    )

    # Record failed execution
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="error_handler", duration_ms=25.0, error=error
    )

    # Get metrics
    metrics = await performance_monitor.get_handler_metrics()

    assert len(metrics) == 1
    assert metrics[0]["total_calls"] == 2
    assert metrics[0]["error_count"] == 1
    assert metrics[0]["error_rate"] == 50.0  # 1 error out of 2 calls


@pytest.mark.asyncio
async def test_event_publication_metrics(performance_monitor):
    """Test event publication metrics recording."""
    # Record event publication
    await performance_monitor.record_event_publication(
        event_type="test.event", duration_ms=75.0, handlers_called=3
    )

    # Record another publication
    await performance_monitor.record_event_publication(
        event_type="test.event", duration_ms=85.0, handlers_called=3
    )

    # Get metrics
    event_metrics = await performance_monitor.get_event_metrics()

    assert len(event_metrics) == 1
    assert event_metrics[0]["event_type"] == "test.event"
    assert event_metrics[0]["total_published"] == 2
    assert event_metrics[0]["avg_publish_duration_ms"] == 80.0
    assert event_metrics[0]["avg_handlers_per_event"] == 3.0


@pytest.mark.asyncio
async def test_context_invalidation_metrics(performance_monitor):
    """Test context invalidation tracking."""
    # Record invalidations
    await performance_monitor.record_context_invalidation(
        user_uid="user_123",
        duration_ms=12.0,
        reason="task_completed",
        affected_contexts=["askesis", "search"],
    )

    await performance_monitor.record_context_invalidation(
        user_uid="user_123",
        duration_ms=15.0,
        reason="goal_achieved",
        affected_contexts=["askesis", "recommendations"],
    )

    # Get metrics for specific user
    user_metrics = await performance_monitor.get_context_invalidation_metrics(user_uid="user_123")

    assert user_metrics is not None
    assert user_metrics["user_uid"] == "user_123"
    assert user_metrics["total_invalidations"] == 2
    assert user_metrics["avg_duration_ms"] == 13.5
    assert user_metrics["invalidations_by_reason"]["task_completed"] == 1
    assert user_metrics["invalidations_by_reason"]["goal_achieved"] == 1
    assert user_metrics["affected_contexts_count"]["askesis"] == 2
    assert user_metrics["affected_contexts_count"]["search"] == 1
    assert user_metrics["affected_contexts_count"]["recommendations"] == 1


@pytest.mark.asyncio
async def test_performance_summary(performance_monitor):
    """Test overall performance summary."""
    # Record various metrics
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="handler_1", duration_ms=30.0, error=None
    )

    await performance_monitor.record_handler_execution(
        event_type="test.event",
        handler_name="handler_2",
        duration_ms=120.0,  # Slow handler
        error=None,
    )

    await performance_monitor.record_event_publication(
        event_type="test.event", duration_ms=150.0, handlers_called=2
    )

    await performance_monitor.record_context_invalidation(
        user_uid="user_123", duration_ms=10.0, reason="test", affected_contexts=["test"]
    )

    # Get summary
    summary = await performance_monitor.get_summary()

    assert summary["enabled"] is True
    assert summary["total_handlers_monitored"] == 2
    assert summary["total_event_types"] == 1
    assert summary["total_users_tracked"] == 1
    assert summary["slow_handlers_count"] == 1  # handler_2 is slow
    assert summary["total_handler_calls"] == 2
    assert summary["total_handler_errors"] == 0
    assert summary["total_events_published"] == 1
    assert summary["total_context_invalidations"] == 1


# ============================================================================
# EVENT BUS INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_event_bus_performance_tracking(event_bus):
    """Test that event bus tracks performance automatically."""

    # Define test handlers
    async def fast_handler(event: SampleEvent):
        """Fast handler - should not be flagged as slow."""
        await asyncio.sleep(0.001)  # 1ms

    async def slow_handler(event: SampleEvent):
        """Slow handler - should be detected as bottleneck."""
        await asyncio.sleep(0.06)  # 60ms (above 50ms threshold)

    # Subscribe handlers
    event_bus.subscribe(SampleEvent, fast_handler)
    event_bus.subscribe(SampleEvent, slow_handler)

    # Publish event
    event = SampleEvent(user_uid="user_123", occurred_at=datetime.now())
    await event_bus.publish_async(event)

    # Wait for handlers to complete
    await asyncio.sleep(0.1)

    # Get slow handlers
    slow_handlers = await event_bus.get_slow_handlers(threshold_ms=50.0)

    # Should detect slow_handler
    assert len(slow_handlers) >= 1
    slow_handler_names = [h["handler_name"] for h in slow_handlers]
    assert "slow_handler" in slow_handler_names


@pytest.mark.asyncio
async def test_event_bus_error_tracking(event_bus):
    """Test that event bus tracks handler errors."""

    # Define handler that fails
    async def failing_handler(event: SampleEvent):
        """Handler that always fails."""
        raise ValueError("Intentional test error")

    # Subscribe handler
    event_bus.subscribe(SampleEvent, failing_handler)

    # Publish event (should not raise - errors are caught)
    event = SampleEvent(user_uid="user_123", occurred_at=datetime.now())
    await event_bus.publish_async(event)

    # Wait for handler to complete
    await asyncio.sleep(0.01)

    # Get performance metrics
    metrics = await event_bus.get_performance_metrics()

    assert metrics is not None
    assert metrics["summary"]["total_handler_errors"] >= 1


@pytest.mark.asyncio
async def test_multiple_events_performance(event_bus):
    """Test performance tracking across multiple events."""
    call_count = 0

    async def counting_handler(event: SampleEvent):
        """Handler that counts calls."""
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.001)

    # Subscribe handler
    event_bus.subscribe(SampleEvent, counting_handler)

    # Publish multiple events
    for i in range(5):
        event = SampleEvent(user_uid=f"user_{i}", occurred_at=datetime.now())
        await event_bus.publish_async(event)

    # Wait for all handlers to complete
    await asyncio.sleep(0.05)

    # Get metrics
    metrics = await event_bus.get_performance_metrics()

    assert metrics is not None
    assert metrics["summary"]["total_events_published"] >= 5
    assert call_count == 5


# ============================================================================
# CLEANUP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_metrics_reset(performance_monitor):
    """Test that metrics can be reset."""
    # Record some metrics
    await performance_monitor.record_handler_execution(
        event_type="test.event", handler_name="test_handler", duration_ms=30.0, error=None
    )

    # Verify metrics exist
    metrics_before = await performance_monitor.get_handler_metrics()
    assert len(metrics_before) == 1

    # Reset metrics
    await performance_monitor.reset()

    # Verify metrics are cleared
    metrics_after = await performance_monitor.get_handler_metrics()
    assert len(metrics_after) == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
