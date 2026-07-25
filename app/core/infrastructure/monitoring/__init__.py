"""
Performance Monitoring Infrastructure
======================================

Prometheus-first metrics with in-memory cache for debugging.
- January 2026 (Option D: Prometheus as Primary)

Key Components:
- PrometheusMetrics: Source of truth for production monitoring
- MetricsCache: In-memory cache for debugging (last 100 items)
- HTTP Instrumentation: Request/response timing and logging
"""

from core.infrastructure.monitoring.aura_cap_check import check_aura_cap_headroom
from core.infrastructure.monitoring.http_instrumentation import (
    create_instrumented_wrapper,
    instrument_handler,
)

# NOTE: MetricsEventHandler not imported here to avoid circular dependency
# Import MetricsEventHandler directly in bootstrap.py instead
from core.infrastructure.monitoring.metrics_cache import MetricsCache
from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
from core.infrastructure.monitoring.query_metrics_cache import QueryMetricsCache

__all__ = [
    # Prometheus-first metrics
    "PrometheusMetrics",
    "MetricsCache",
    "QueryMetricsCache",
    # In-app AuraDB cap evaluator (production has no Prometheus)
    "check_aura_cap_headroom",
    # HTTP instrumentation
    "create_instrumented_wrapper",
    "instrument_handler",
]
