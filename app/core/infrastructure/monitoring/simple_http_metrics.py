"""
Simple HTTP Metrics Tracking for CRUD Routes
=============================================

Provides manual metrics tracking that can be called from within route handlers.
This approach works with SKUEL's Result[T] pattern and boundary_handler.

Usage in route factories:
    if self.prometheus_metrics:
        self.prometheus_metrics.http.requests_total.labels(
            method="POST", endpoint="/api/tasks/create", status=201
        ).inc()
"""

from typing import Any


class HttpMetricsTracker:
    """
    Helper class for tracking HTTP metrics in route handlers.

    This provides a cleaner interface than directly calling prometheus metrics.
    """

    def __init__(self, prometheus_metrics: Any) -> None:
        """
        Initialize tracker with PrometheusMetrics instance.

        Args:
            prometheus_metrics: PrometheusMetrics instance
        """
        self.metrics = prometheus_metrics

    def track_request(self, method: str, endpoint: str, status: int, duration: float) -> None:
        """
        Track a completed HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Endpoint path
            status: HTTP status code
            duration: Request duration in seconds
        """
        # Track request count
        self.metrics.http.requests_total.labels(
            method=method, endpoint=endpoint, status=status
        ).inc()

        # Track latency
        self.metrics.http.request_duration.labels(method=method, endpoint=endpoint).observe(
            duration
        )

        # Track errors (4xx, 5xx)
        if status >= 400:
            self.metrics.http.errors_total.labels(
                method=method, endpoint=endpoint, status=status
            ).inc()


def create_metrics_tracker(prometheus_metrics: Any | None) -> HttpMetricsTracker | None:
    """
    Create metrics tracker if prometheus_metrics is available.

    Args:
        prometheus_metrics: PrometheusMetrics instance or None

    Returns:
        HttpMetricsTracker or None
    """
    if prometheus_metrics:
        return HttpMetricsTracker(prometheus_metrics)
    return None
