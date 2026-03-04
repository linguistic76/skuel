"""
Prometheus metrics endpoint.

This module provides the /metrics endpoint that Prometheus scrapes for telemetry data.

See: /monitoring/prometheus/prometheus.yml for scrape configuration
"""

from fasthtml.common import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList


def create_metrics_routes(app: FastHTMLApp, rt: RouteDecorator) -> RouteList:
    """
    Register Prometheus metrics endpoint.

    Args:
        app: FastHTML application instance
        rt: FastHTML router instance

    Returns:
        List of registered route handlers (for consistency with other route modules)
    """

    @rt("/metrics")
    def prometheus_metrics() -> Response:
        """
        Prometheus scrape endpoint.

        Returns metrics in Prometheus exposition format.
        This endpoint is called by Prometheus every 15s (see prometheus.yml).

        Returns:
            Response with Prometheus-formatted metrics
        """
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return [prometheus_metrics]
