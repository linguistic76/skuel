"""
Graph-Health Poller Self-Observability Gauge Tests
==================================================

Tests for RelationshipMetrics.poll_last_success — the timestamp gauge the
graph-health background task (scripts/dev/bootstrap.py) baselines at task start
and refreshes after each error-free pass, so GraphHealthPollerStale can
fire when the 16 relationship/knowledge gauges freeze at stale values.

The poller itself is a closure inside bootstrap and not importable; these tests
guard the metric surface the poller writes to.
"""

import contextlib

import pytest

from core.infrastructure.monitoring import PrometheusMetrics


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


def test_poll_last_success_gauge_lifecycle(prometheus_metrics):
    """The poller self-observability gauge exists, exports 0 unset, and carries
    a real Unix timestamp after set_to_current_time().

    One test, not two: the unset-state and mutated-state assertions share the
    module-scoped gauge, so splitting them would create a test-order dependency.
    """
    gauge = prometheus_metrics.relationships.poll_last_success

    samples = gauge.collect()[0].samples
    assert samples[0].name == "skuel_graph_health_poll_last_success_timestamp_seconds"
    # Unset gauge exports 0 — exactly the boot false-positive the baseline
    # set_to_current_time() at task start exists to prevent.
    assert samples[0].value == 0.0

    gauge.set_to_current_time()

    assert gauge.collect()[0].samples[0].value > 0
