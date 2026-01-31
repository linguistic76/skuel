"""
Prometheus Bridge for PerformanceMonitor
=========================================

Exports existing PerformanceMonitor metrics to Prometheus.

This module bridges SKUEL's in-memory event bus performance monitoring
to Prometheus, allowing historical tracking and visualization in Grafana.

Metrics Exported:
- Event publication count by type
- Event handler execution count by type/handler
- Event handler duration (histogram)
- Event handler errors by type/handler
- Context invalidation count by user

Phase 3 - January 2026
"""

from typing import Any

from core.infrastructure.monitoring.performance_metrics import PerformanceMonitor
from core.utils.logging import get_logger

logger = get_logger(__name__)


class PrometheusPerformanceBridge:
    """
    Bridge between PerformanceMonitor and Prometheus.

    Reads metrics from in-memory PerformanceMonitor and updates
    Prometheus counters/histograms.
    """

    def __init__(
        self, performance_monitor: PerformanceMonitor, prometheus_metrics: Any
    ) -> None:
        """
        Initialize bridge.

        Args:
            performance_monitor: SKUEL's in-memory performance monitor
            prometheus_metrics: PrometheusMetrics instance
        """
        self.performance_monitor = performance_monitor
        self.prometheus_metrics = prometheus_metrics
        self._last_export_values: dict[str, int] = {}  # Track last exported values for delta

    async def export_to_prometheus(self) -> None:
        """
        Export current PerformanceMonitor data to Prometheus.

        This should be called periodically (e.g., every 30 seconds)
        to sync in-memory metrics to Prometheus.
        """
        if not self.performance_monitor.enabled:
            return

        try:
            # Export event metrics
            await self._export_event_metrics()

            # Export handler metrics
            await self._export_handler_metrics()

            # Export context invalidation metrics
            await self._export_context_metrics()

        except Exception as e:
            logger.error(f"Failed to export performance metrics to Prometheus: {e}")

    async def _export_event_metrics(self) -> None:
        """Export event publication metrics to Prometheus."""
        event_metrics = await self.performance_monitor.get_event_metrics()

        for event_data in event_metrics:
            event_type = event_data["event_type"]
            total_published = event_data["total_published"]

            # Track event publication count (use set instead of inc for absolute values)
            self.prometheus_metrics.events.events_published_total.labels(
                event_type=event_type
            ).inc(
                total_published - self._last_export_values.get(f"event:{event_type}", 0)
            )

            # Update last exported value
            self._last_export_values[f"event:{event_type}"] = total_published

            # Track event publish duration (average - Prometheus will compute over time)
            if event_data["avg_publish_duration_ms"] > 0:
                # Convert ms to seconds for Prometheus
                duration_seconds = event_data["avg_publish_duration_ms"] / 1000.0
                self.prometheus_metrics.events.event_publish_duration_seconds.labels(
                    event_type=event_type
                ).observe(duration_seconds)

    async def _export_handler_metrics(self) -> None:
        """Export event handler execution metrics to Prometheus."""
        handler_metrics = await self.performance_monitor.get_handler_metrics()

        for handler_data in handler_metrics:
            event_type = handler_data["event_type"]
            handler_name = handler_data["handler_name"]
            total_calls = handler_data["total_calls"]
            error_count = handler_data["error_count"]

            key = f"handler:{event_type}:{handler_name}"

            # Track handler calls (increment by delta since last export)
            calls_delta = total_calls - self._last_export_values.get(f"{key}:calls", 0)
            if calls_delta > 0:
                self.prometheus_metrics.events.event_handler_calls_total.labels(
                    event_type=event_type, handler=handler_name
                ).inc(calls_delta)
                self._last_export_values[f"{key}:calls"] = total_calls

            # Track handler errors (increment by delta since last export)
            errors_delta = error_count - self._last_export_values.get(f"{key}:errors", 0)
            if errors_delta > 0:
                self.prometheus_metrics.events.event_handler_errors_total.labels(
                    event_type=event_type, handler=handler_name
                ).inc(errors_delta)
                self._last_export_values[f"{key}:errors"] = error_count

            # Track handler duration (recent average)
            if handler_data["recent_avg_duration_ms"] > 0:
                duration_seconds = handler_data["recent_avg_duration_ms"] / 1000.0
                self.prometheus_metrics.events.event_handler_duration_seconds.labels(
                    event_type=event_type, handler=handler_name
                ).observe(duration_seconds)

    async def _export_context_metrics(self) -> None:
        """Export context invalidation metrics to Prometheus."""
        context_metrics = await self.performance_monitor.get_context_invalidation_metrics()

        for context_data in context_metrics:
            user_uid = context_data["user_uid"]
            total_invalidations = context_data["total_invalidations"]

            key = f"context:{user_uid}"

            # Track invalidations (increment by delta)
            delta = total_invalidations - self._last_export_values.get(key, 0)
            if delta > 0:
                self.prometheus_metrics.events.context_invalidations_total.labels(
                    user_uid=user_uid
                ).inc(delta)
                self._last_export_values[key] = total_invalidations


__all__ = ["PrometheusPerformanceBridge"]
