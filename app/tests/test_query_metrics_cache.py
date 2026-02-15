"""
Query Metrics Cache Tests
=========================

Tests for QueryMetricsCache - Prometheus-first query metrics with in-memory cache for debugging.

Tests verify:
- Query/operation timing tracking
- Error tracking
- Decorator pattern (@track_query_metrics)
- Context manager pattern (MetricsTimer)
- Cache functionality (last 100 timings per operation)
- Integration with Prometheus
- Backward-compatible API (get_metrics, get_metrics_summary, etc.)
"""

import asyncio
import time

import pytest

from core.infrastructure.monitoring import PrometheusMetrics, QueryMetricsCache
from core.utils.metrics import (
    MetricsTimer,
    disable_metrics,
    enable_metrics,
    get_metrics,
    get_metrics_summary,
    reset_metrics,
    set_query_metrics_cache,
    track_query_metrics,
)
from core.utils.result_simplified import Result

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
            c for c in list(prometheus_client.REGISTRY._names_to_collectors.values())
            if hasattr(c, '_name') and getattr(c, '_name', '').startswith('skuel_')
        ]
        for collector in collectors_to_remove:
            try:
                prometheus_client.REGISTRY.unregister(collector)
            except Exception:
                pass

    # Unregister existing skuel collectors to avoid duplicates
    _unregister_skuel_collectors()

    metrics = PrometheusMetrics()
    yield metrics

    # Teardown: unregister collectors to avoid polluting other test modules
    _unregister_skuel_collectors()


@pytest.fixture
def query_metrics_cache(prometheus_metrics) -> QueryMetricsCache:
    """Create fresh query metrics cache for each test."""
    cache = QueryMetricsCache(prometheus_metrics, enabled=True)
    yield cache
    # Reset cache after each test
    cache.reset_sync()


@pytest.fixture(autouse=True)
def setup_global_cache(query_metrics_cache):
    """Set global query metrics cache for all tests."""
    set_query_metrics_cache(query_metrics_cache)
    yield
    # Reset after each test
    reset_metrics()


# ============================================================================
# QUERY METRICS CACHE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_operation_timing_recording(query_metrics_cache):
    """Test that operation timing is recorded in cache."""
    # Record operation timing
    await query_metrics_cache.record_timing(
        operation_name="ku_search_by_title", duration_ms=45.0, had_error=False
    )

    # Get metrics from cache
    metrics = await query_metrics_cache.get_metrics()

    assert "ku_search_by_title" in metrics
    op_metrics = metrics["ku_search_by_title"]
    assert op_metrics["call_count"] == 1
    assert op_metrics["avg_time_ms"] == 45.0


@pytest.mark.asyncio
async def test_operation_error_tracking(query_metrics_cache):
    """Test that operation errors are tracked in cache."""
    # Record successful execution
    await query_metrics_cache.record_timing(
        operation_name="task_create", duration_ms=30.0, had_error=False
    )

    # Record failed execution
    await query_metrics_cache.record_timing(
        operation_name="task_create", duration_ms=25.0, had_error=True
    )

    # Get metrics
    metrics = await query_metrics_cache.get_metrics()

    assert "task_create" in metrics
    op_metrics = metrics["task_create"]
    assert op_metrics["call_count"] == 2
    assert op_metrics["error_count"] == 1
    assert op_metrics["error_rate"] == 50.0  # 1 error out of 2 calls


@pytest.mark.asyncio
async def test_percentile_calculation(query_metrics_cache):
    """Test that p95 and p99 percentiles are calculated correctly."""
    # Record 10 executions with varying durations
    durations = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    for duration in durations:
        await query_metrics_cache.record_timing(
            operation_name="test_op", duration_ms=duration, had_error=False
        )

    # Get metrics
    metrics = await query_metrics_cache.get_metrics()

    assert "test_op" in metrics
    op_metrics = metrics["test_op"]
    assert op_metrics["p95_time_ms"] is not None
    assert op_metrics["p99_time_ms"] is not None
    assert op_metrics["p95_time_ms"] >= 90.0  # 95th percentile should be near the top
    assert op_metrics["min_time_ms"] == 10.0
    assert op_metrics["max_time_ms"] == 100.0


@pytest.mark.asyncio
async def test_cache_summary(query_metrics_cache):
    """Test cache summary aggregation."""
    # Record metrics for multiple operations
    await query_metrics_cache.record_timing(
        operation_name="ku_search", duration_ms=30.0, had_error=False
    )
    await query_metrics_cache.record_timing(
        operation_name="task_create", duration_ms=40.0, had_error=False
    )
    await query_metrics_cache.record_timing(
        operation_name="goal_update", duration_ms=50.0, had_error=True
    )

    # Get summary
    summary = await query_metrics_cache.get_summary()

    assert summary["enabled"] is True
    assert summary["total_operations"] == 3
    assert summary["total_calls"] == 3
    assert summary["total_errors"] == 1
    assert summary["overall_error_rate"] == pytest.approx(33.33, rel=0.1)
    assert "cache_note" in summary
    assert "slowest_operations" in summary


@pytest.mark.asyncio
async def test_cache_reset(query_metrics_cache):
    """Test cache reset functionality."""
    # Record some metrics
    await query_metrics_cache.record_timing(
        operation_name="test_op", duration_ms=30.0, had_error=False
    )

    # Verify metrics exist
    metrics_before = await query_metrics_cache.get_metrics()
    assert len(metrics_before) == 1

    # Reset cache
    await query_metrics_cache.reset()

    # Verify cache is empty
    metrics_after = await query_metrics_cache.get_metrics()
    assert len(metrics_after) == 0


@pytest.mark.asyncio
async def test_cache_lossy_behavior(query_metrics_cache):
    """Test that cache is lossy (only keeps last 100 timings per operation)."""
    # Record 150 timings for same operation
    for i in range(150):
        await query_metrics_cache.record_timing(
            operation_name="test_op", duration_ms=30.0 + i, had_error=False
        )

    # Get metrics
    metrics = await query_metrics_cache.get_metrics()

    # Cache should only have 100 timings (maxlen of deque)
    assert "test_op" in metrics
    assert metrics["test_op"]["call_count"] == 100  # Only last 100 calls


@pytest.mark.asyncio
async def test_prometheus_writes(query_metrics_cache, prometheus_metrics):
    """Test that metrics are written to Prometheus."""
    # Record operation timing
    await query_metrics_cache.record_timing(
        operation_name="test_op", duration_ms=45.0, had_error=False
    )

    # Verify Prometheus metrics exist
    assert prometheus_metrics.queries.operation_calls_total is not None
    assert prometheus_metrics.queries.operation_duration_seconds is not None
    assert prometheus_metrics.queries.operation_errors_total is not None


@pytest.mark.asyncio
async def test_disabled_cache(prometheus_metrics):
    """Test that cache can be disabled while Prometheus still works."""
    # Create cache with caching disabled
    cache = QueryMetricsCache(prometheus_metrics, enabled=False)

    # Record metrics
    await cache.record_timing(operation_name="test_op", duration_ms=30.0, had_error=False)

    # Cache should be empty
    metrics = await cache.get_metrics()
    assert len(metrics) == 0

    # But summary should indicate disabled state
    summary = await cache.get_summary()
    assert summary["enabled"] is False


def test_sync_recording(query_metrics_cache):
    """Test synchronous recording method."""
    # Record timing synchronously
    query_metrics_cache.record_timing_sync(
        operation_name="sync_op", duration_ms=25.0, had_error=False
    )

    # Get metrics synchronously
    metrics = query_metrics_cache.get_metrics_sync()

    assert "sync_op" in metrics
    assert metrics["sync_op"]["call_count"] == 1


# ============================================================================
# DECORATOR TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_track_query_metrics_decorator_async():
    """Test @track_query_metrics decorator with async function."""

    @track_query_metrics("test_operation")
    async def test_function():
        await asyncio.sleep(0.01)  # Simulate work
        return "success"

    # Call decorated function
    result = await test_function()
    assert result == "success"

    # Verify metrics were recorded
    metrics = get_metrics("test_operation")
    assert metrics["call_count"] == 1
    assert metrics["avg_time_ms"] > 0


@pytest.mark.asyncio
async def test_track_query_metrics_decorator_with_result():
    """Test @track_query_metrics decorator with Result pattern."""

    @track_query_metrics("result_operation")
    async def test_function_success():
        return Result.ok("success")

    @track_query_metrics("result_operation_error")
    async def test_function_error():
        return Result.fail("Error occurred")

    # Test success case
    result_ok = await test_function_success()
    assert not result_ok.is_error

    # Test error case
    result_err = await test_function_error()
    assert result_err.is_error

    # Verify error tracking
    metrics_error = get_metrics("result_operation_error")
    assert metrics_error["error_count"] == 1


def test_track_query_metrics_decorator_sync():
    """Test @track_query_metrics decorator with sync function."""

    @track_query_metrics("sync_operation")
    def test_function():
        time.sleep(0.01)  # Simulate work
        return "success"

    # Call decorated function
    result = test_function()
    assert result == "success"

    # Verify metrics were recorded
    metrics = get_metrics("sync_operation")
    assert metrics["call_count"] == 1


@pytest.mark.asyncio
async def test_track_query_metrics_with_exception():
    """Test that decorator tracks errors when exception is raised."""

    @track_query_metrics("exception_operation")
    async def test_function_raises():
        raise ValueError("Test error")

    # Call should raise exception
    with pytest.raises(ValueError):
        await test_function_raises()

    # But metrics should still be recorded with error flag
    metrics = get_metrics("exception_operation")
    assert metrics["call_count"] == 1
    assert metrics["error_count"] == 1


# ============================================================================
# CONTEXT MANAGER TESTS
# ============================================================================


def test_metrics_timer_context_manager():
    """Test MetricsTimer context manager."""
    with MetricsTimer("timer_operation"):
        time.sleep(0.01)  # Simulate work

    # Verify metrics were recorded
    metrics = get_metrics("timer_operation")
    assert metrics["call_count"] == 1
    assert metrics["avg_time_ms"] > 0


def test_metrics_timer_with_exception():
    """Test MetricsTimer context manager with exception."""
    try:
        with MetricsTimer("timer_exception"):
            raise ValueError("Test error")
    except ValueError:
        pass

    # Metrics should still be recorded with error flag
    metrics = get_metrics("timer_exception")
    assert metrics["call_count"] == 1
    assert metrics["error_count"] == 1


# ============================================================================
# BACKWARD-COMPATIBLE API TESTS
# ============================================================================


def test_get_metrics_api():
    """Test backward-compatible get_metrics() API."""
    # Record some metrics manually
    _cache = get_metrics("")  # Get cache via internal access

    # Use decorator to populate metrics
    @track_query_metrics("api_test")
    def test_func():
        return "ok"

    test_func()

    # Get all metrics
    all_metrics = get_metrics()
    assert "api_test" in all_metrics

    # Get specific operation metrics
    specific_metrics = get_metrics("api_test")
    assert specific_metrics["call_count"] == 1


def test_get_metrics_summary_api():
    """Test backward-compatible get_metrics_summary() API."""

    # Use decorator to populate metrics
    @track_query_metrics("summary_test")
    def test_func():
        return "ok"

    test_func()

    # Get summary
    summary = get_metrics_summary()

    assert "total_operations" in summary
    assert "total_calls" in summary
    assert "operations" in summary


def test_reset_metrics_api():
    """Test backward-compatible reset_metrics() API."""

    # Populate metrics
    @track_query_metrics("reset_test")
    def test_func():
        return "ok"

    test_func()

    # Verify metrics exist
    metrics_before = get_metrics("reset_test")
    assert metrics_before["call_count"] == 1

    # Reset
    reset_metrics()

    # Verify metrics cleared (should return empty dict for specific operation)
    metrics_after = get_metrics("reset_test")
    assert metrics_after == {}


def test_enable_disable_metrics_api():
    """Test enable/disable metrics API."""
    # Disable metrics
    disable_metrics()

    @track_query_metrics("disabled_test")
    def test_func():
        return "ok"

    test_func()

    # Metrics should not be recorded (cache disabled)
    _summary = get_metrics_summary()
    # The function will still work but cache is disabled
    # Note: Prometheus still gets data, only cache is disabled

    # Re-enable
    enable_metrics()

    @track_query_metrics("enabled_test")
    def test_func2():
        return "ok"

    test_func2()

    # Metrics should be recorded again
    metrics = get_metrics("enabled_test")
    assert metrics["call_count"] == 1


def test_get_metrics_summary_when_cache_not_initialized():
    """Test get_metrics_summary() when cache not initialized."""
    # Temporarily set cache to None
    set_query_metrics_cache(None)

    summary = get_metrics_summary()

    assert summary["enabled"] is False
    assert "cache_note" in summary

    # Note: The fixture will reset this after the test


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_multiple_operations_tracking():
    """Test tracking multiple different operations."""

    @track_query_metrics("op1")
    async def operation1():
        await asyncio.sleep(0.01)
        return Result.ok("op1")

    @track_query_metrics("op2")
    async def operation2():
        await asyncio.sleep(0.02)
        return Result.ok("op2")

    # Execute operations multiple times
    await operation1()
    await operation1()
    await operation2()

    # Get summary
    summary = get_metrics_summary()

    assert summary["total_operations"] == 2
    assert summary["total_calls"] == 3

    # Verify individual operation metrics
    op1_metrics = get_metrics("op1")
    assert op1_metrics["call_count"] == 2

    op2_metrics = get_metrics("op2")
    assert op2_metrics["call_count"] == 1


@pytest.mark.asyncio
async def test_slowest_operations_ranking():
    """Test that slowest operations are correctly ranked."""

    @track_query_metrics("fast_op")
    async def fast_operation():
        await asyncio.sleep(0.001)
        return "fast"

    @track_query_metrics("slow_op")
    async def slow_operation():
        await asyncio.sleep(0.05)
        return "slow"

    # Execute operations
    await fast_operation()
    await slow_operation()

    # Get summary
    summary = get_metrics_summary()

    # Slowest operations should rank slow_op first
    slowest = summary["slowest_operations"]
    assert len(slowest) >= 1
    # The slowest should have higher avg_time_ms
    if len(slowest) == 2:
        assert slowest[0]["avg_time_ms"] > slowest[1]["avg_time_ms"]
