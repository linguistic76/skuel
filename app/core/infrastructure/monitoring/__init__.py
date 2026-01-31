"""
Performance Monitoring Infrastructure
======================================

Lightweight performance monitoring for SKUEL's event system.
Includes Prometheus metrics export for observability (Phase 1 - January 2026).
Phase 2: HTTP and database instrumentation (January 2026).
"""

from core.infrastructure.monitoring.http_instrumentation import (
    create_instrumented_wrapper,
    instrument_handler,
    instrument_with_boundary_handler,
)

# NOTE: MetricsEventHandler not imported here to avoid circular dependency
# (it imports EventBus, which imports get_performance_monitor from this module)
# Import MetricsEventHandler directly in bootstrap.py instead
from core.infrastructure.monitoring.performance_metrics import (
    ContextInvalidationMetrics,
    EventMetrics,
    HandlerMetrics,
    PerformanceMonitor,
    get_performance_monitor,
    reset_performance_monitor,
)
from core.infrastructure.monitoring.prometheus_bridge import PrometheusPerformanceBridge
from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics

__all__ = [
    "ContextInvalidationMetrics",
    "EventMetrics",
    "HandlerMetrics",
    "PerformanceMonitor",
    "get_performance_monitor",
    "reset_performance_monitor",
    "PrometheusMetrics",
    "PrometheusPerformanceBridge",
    "create_instrumented_wrapper",
    "instrument_handler",
    "instrument_with_boundary_handler",
]
