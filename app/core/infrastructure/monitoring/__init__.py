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
from core.infrastructure.monitoring.uid_grammar_check import UID_BREACH_SAMPLE, check_uid_grammar

__all__ = [
    # Prometheus-first metrics
    "PrometheusMetrics",
    "MetricsCache",
    "QueryMetricsCache",
    # In-app evaluators (production has no Prometheus): AuraDB caps, uid grammar
    "check_aura_cap_headroom",
    "check_uid_grammar",
    "UID_BREACH_SAMPLE",
    # HTTP instrumentation
    "create_instrumented_wrapper",
    "instrument_handler",
]
