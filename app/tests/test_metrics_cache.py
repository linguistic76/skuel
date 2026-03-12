"""
Metrics Cache Tests
===================

Tests for MetricsCache - Prometheus-first metrics with in-memory cache for debugging.

Tests verify:
- Handler execution tracking
- Event publication metrics
- Context invalidation tracking
- Slow handler detection
- Cache functionality (last 100 items)
- Integration with Prometheus
"""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events.base import BaseEvent
from core.infrastructure.monitoring import MetricsCache, PrometheusMetrics

# ============================================================================
# TEST EVENTS
# ============================================================================


@dataclass(frozen=True)
class SampleEvent(BaseEvent):
    """Sample event for metrics cache tests."""

    user_uid: str
    occurred_at: datetime

    @property
    def event_type(self) -> str:
        return "test.event"


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def prometheus_metrics() -> PrometheusMetrics:
    """Create Prometheus metrics registry once per module.

    Handles duplicate collector registration when tests run alongside
    other modules that also create PrometheusMetrics.
    """
    import prometheus_client

    def _unregister_skuel_collectors():
        collectors_to_remove = [
            c
            for c in list(prometheus_client.REGISTRY._names_to_collectors.values())
            if hasattr(c, "_name") and getattr(c, "_name", "").startswith("skuel_")
        ]
        for collector in collectors_to_remove:
            with contextlib.suppress(Exception):
                prometheus_client.REGISTRY.unregister(collector)

    _unregister_skuel_collectors()
    metrics = PrometheusMetrics()
    yield metrics
    _unregister_skuel_collectors()


@pytest.fixture
def metrics_cache(prometheus_metrics) -> MetricsCache:
    """Create fresh metrics cache for each test."""
    cache = MetricsCache(prometheus_metrics, enabled=True)
    yield cache
    # Reset cache after each test
    import asyncio

    asyncio.run(cache.reset())


@pytest.fixture
def event_bus(metrics_cache) -> InMemoryEventBus:
    """Create event bus with metrics cache enabled."""
    return InMemoryEventBus(metrics_cache=metrics_cache)


# ============================================================================
# METRICS CACHE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_handler_metrics_recording(metrics_cache):
    """Test that handler execution is recorded in cache."""
    # Record handler execution
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="test_handler", duration_ms=45.0, error=None
    )

    # Get metrics from cache
    metrics = await metrics_cache.get_handler_metrics()

    assert len(metrics) == 1
    assert metrics[0]["handler_name"] == "test_handler"
    assert metrics[0]["event_type"] == "test.event"
    assert metrics[0]["total_calls"] == 1
    assert metrics[0]["recent_avg_duration_ms"] == 45.0


@pytest.mark.asyncio
async def test_slow_handler_detection(metrics_cache):
    """Test detection of slow handlers in cache."""
    # Record fast handler
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="fast_handler", duration_ms=10.0, error=None
    )

    # Record slow handler (above 100ms default threshold)
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="slow_handler", duration_ms=120.0, error=None
    )

    # Get slow handlers (default 100ms threshold)
    slow_handlers = await metrics_cache.get_slow_handlers(threshold_ms=50.0)

    assert len(slow_handlers) == 1
    assert slow_handlers[0]["handler_name"] == "slow_handler"
    assert slow_handlers[0]["recent_avg_duration_ms"] > 50.0


@pytest.mark.asyncio
async def test_handler_error_tracking(metrics_cache):
    """Test that handler errors are tracked in cache."""
    error = ValueError("Test error")

    # Record successful execution
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="error_handler", duration_ms=30.0, error=None
    )

    # Record failed execution
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="error_handler", duration_ms=25.0, error=error
    )

    # Get metrics
    metrics = await metrics_cache.get_handler_metrics()

    assert len(metrics) == 1
    assert metrics[0]["total_calls"] == 2
    assert metrics[0]["error_count"] == 1
    assert metrics[0]["error_rate"] == 50.0  # 1 error out of 2 calls


@pytest.mark.asyncio
async def test_event_publication_metrics(metrics_cache):
    """Test event publication metrics recording in cache."""
    # Record event publication
    await metrics_cache.record_event_publication(
        event_type="test.event", duration_ms=75.0, handlers_called=3
    )

    # Record another publication
    await metrics_cache.record_event_publication(
        event_type="test.event", duration_ms=85.0, handlers_called=3
    )

    # Get metrics
    event_metrics = await metrics_cache.get_event_metrics()

    assert len(event_metrics) == 1
    assert event_metrics[0]["event_type"] == "test.event"
    assert event_metrics[0]["total_published"] == 2
    assert event_metrics[0]["avg_handlers_per_event"] == 3.0


@pytest.mark.asyncio
async def test_context_invalidation_tracking(metrics_cache):
    """Test context invalidation metrics in cache."""
    # Record invalidation
    await metrics_cache.record_context_invalidation(
        user_uid="user_123",
        duration_ms=50.0,
        reason="task_completed",
        affected_contexts=["askesis", "search"],
    )

    # Record another invalidation
    await metrics_cache.record_context_invalidation(
        user_uid="user_123",
        duration_ms=60.0,
        reason="goal_achieved",
        affected_contexts=["askesis", "dashboard"],
    )

    # Get metrics
    context_metrics = await metrics_cache.get_context_invalidation_metrics(user_uid="user_123")

    assert context_metrics is not None
    assert context_metrics["user_uid"] == "user_123"
    assert context_metrics["total_invalidations"] == 2
    assert context_metrics["invalidations_by_reason"]["task_completed"] == 1
    assert context_metrics["invalidations_by_reason"]["goal_achieved"] == 1


@pytest.mark.asyncio
async def test_cache_summary(metrics_cache):
    """Test cache summary aggregation."""
    # Record some metrics
    await metrics_cache.record_handler_execution(
        event_type="test.event1", handler_name="handler1", duration_ms=30.0, error=None
    )
    await metrics_cache.record_handler_execution(
        event_type="test.event2", handler_name="handler2", duration_ms=40.0, error=None
    )
    await metrics_cache.record_event_publication(
        event_type="test.event1", duration_ms=50.0, handlers_called=2
    )
    await metrics_cache.record_context_invalidation(
        user_uid="user_123", duration_ms=25.0, reason="manual", affected_contexts=["askesis"]
    )

    # Get summary
    summary = await metrics_cache.get_summary()

    assert summary["enabled"] is True
    assert summary["total_handlers_cached"] == 2
    assert summary["total_event_types_cached"] == 1
    assert summary["total_users_tracked"] == 1
    assert summary["cached_handler_calls"] == 2
    assert "cache_note" in summary


@pytest.mark.asyncio
async def test_cache_reset(metrics_cache):
    """Test cache reset functionality."""
    # Record some metrics
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="handler", duration_ms=30.0, error=None
    )

    # Verify metrics exist
    metrics_before = await metrics_cache.get_handler_metrics()
    assert len(metrics_before) == 1

    # Reset cache
    await metrics_cache.reset()

    # Verify cache is empty
    metrics_after = await metrics_cache.get_handler_metrics()
    assert len(metrics_after) == 0


@pytest.mark.asyncio
async def test_cache_lossy_behavior(metrics_cache):
    """Test that cache is lossy (only keeps last 100 items)."""
    # Record 150 handler executions
    for i in range(150):
        await metrics_cache.record_handler_execution(
            event_type="test.event", handler_name="handler", duration_ms=30.0 + i, error=None
        )

    # Get metrics
    metrics = await metrics_cache.get_handler_metrics()

    # Cache should only have 100 items (maxlen of deque)
    assert len(metrics) == 1  # One handler tracked
    assert metrics[0]["total_calls"] == 100  # But only last 100 calls


@pytest.mark.asyncio
async def test_prometheus_writes(metrics_cache, prometheus_metrics):
    """Test that metrics are written to Prometheus."""
    # Record handler execution
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="test_handler", duration_ms=45.0, error=None
    )

    # Verify Prometheus counter was incremented
    # Note: We can't easily check the exact value without mocking,
    # but we can verify the metric exists
    assert prometheus_metrics.events.event_handler_calls_total is not None
    assert prometheus_metrics.events.event_handler_duration_seconds is not None


@pytest.mark.asyncio
async def test_disabled_cache(prometheus_metrics):
    """Test that cache can be disabled while Prometheus still works."""
    # Create cache with caching disabled
    cache = MetricsCache(prometheus_metrics, enabled=False)

    # Record metrics
    await cache.record_handler_execution(
        event_type="test.event", handler_name="handler", duration_ms=30.0, error=None
    )

    # Cache should be empty
    metrics = await cache.get_handler_metrics()
    assert len(metrics) == 0

    # But Prometheus should still be updated (we can't easily verify without mocking)
    summary = await cache.get_summary()
    assert summary["enabled"] is False


@pytest.mark.asyncio
async def test_event_bus_integration(event_bus, metrics_cache):
    """Test that event bus correctly uses metrics cache."""

    # Define test handlers
    handler_called = False

    async def test_handler(event):
        nonlocal handler_called
        handler_called = True
        await asyncio.sleep(0.01)  # Simulate some work

    # Subscribe handler
    event_bus.subscribe(SampleEvent, test_handler)

    # Publish event
    event = SampleEvent(user_uid="user_123", occurred_at=datetime.now())
    await event_bus.publish_async(event)

    # Wait for async handlers
    await asyncio.sleep(0.05)

    # Verify handler was called
    assert handler_called

    # Verify metrics were recorded
    handler_metrics = await metrics_cache.get_handler_metrics()
    assert len(handler_metrics) > 0

    event_metrics = await metrics_cache.get_event_metrics()
    assert len(event_metrics) > 0


@pytest.mark.asyncio
async def test_multiple_event_types(metrics_cache):
    """Test tracking multiple event types separately."""
    # Record metrics for different event types
    await metrics_cache.record_handler_execution(
        event_type="event.type1", handler_name="handler", duration_ms=30.0, error=None
    )
    await metrics_cache.record_handler_execution(
        event_type="event.type2", handler_name="handler", duration_ms=40.0, error=None
    )

    # Get all metrics
    all_metrics = await metrics_cache.get_handler_metrics()
    assert len(all_metrics) == 2

    # Get metrics filtered by event type
    type1_metrics = await metrics_cache.get_handler_metrics(event_type="event.type1")
    assert len(type1_metrics) == 1
    assert type1_metrics[0]["event_type"] == "event.type1"


@pytest.mark.asyncio
async def test_metric_min_max_tracking(metrics_cache):
    """Test that min/max durations are tracked correctly."""
    # Record executions with varying durations
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="handler", duration_ms=10.0, error=None
    )
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="handler", duration_ms=100.0, error=None
    )
    await metrics_cache.record_handler_execution(
        event_type="test.event", handler_name="handler", duration_ms=50.0, error=None
    )

    # Get metrics
    metrics = await metrics_cache.get_handler_metrics()

    assert len(metrics) == 1
    assert metrics[0]["min_duration_ms"] == 10.0
    assert metrics[0]["max_duration_ms"] == 100.0
    assert 40.0 < metrics[0]["recent_avg_duration_ms"] < 60.0  # Average of 10, 100, 50
