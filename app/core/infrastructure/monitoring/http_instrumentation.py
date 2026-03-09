"""
HTTP Request Instrumentation for Prometheus
============================================

Provides decorators and helpers for instrumenting HTTP requests with Prometheus metrics.

This module tracks:
- Request count by method, endpoint, status
- Request latency by method, endpoint
- Error count by method, endpoint

Usage:
    from core.infrastructure.monitoring import PrometheusMetrics, instrument_handler

    metrics = PrometheusMetrics()

    @instrument_handler(metrics, endpoint_name="/api/tasks/create")
    async def create_handler(request):
        # ... handler logic ...
        return result
"""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from starlette.responses import JSONResponse

from core.utils.logging import get_logger

logger = get_logger(__name__)


def instrument_handler(
    prometheus_metrics: Any,
    endpoint_name: str | None = None,
) -> Callable:
    """
    Decorator to instrument HTTP request handlers with Prometheus metrics.

    Tracks request count, latency, and errors for each endpoint.

    Args:
        prometheus_metrics: PrometheusMetrics instance
        endpoint_name: Optional endpoint name (defaults to function name)

    Returns:
        Decorated handler function

    Example:
        @instrument_handler(metrics, endpoint_name="/api/tasks/create")
        async def create_task(request):
            return await service.create(task)
    """

    def decorator(handler: Callable) -> Callable:
        # Get endpoint name (use provided or function name)
        endpoint = endpoint_name or f"/{handler.__name__}"

        @wraps(handler)
        async def instrumented(request, *args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            method = request.method
            status_code = 200  # Default success status

            try:
                # Execute handler
                result = await handler(request, *args, **kwargs)

                # Extract status code from result if it's a Response object
                result_status = getattr(result, "status_code", None)
                if result_status is not None:
                    status_code = result_status

                # Track successful request
                prometheus_metrics.http.requests_total.labels(
                    method=method, endpoint=endpoint, status=status_code
                ).inc()

                return result

            except Exception:
                # Track failed request
                status_code = 500
                prometheus_metrics.http.requests_total.labels(
                    method=method, endpoint=endpoint, status=status_code
                ).inc()

                prometheus_metrics.http.errors_total.labels(
                    method=method, endpoint=endpoint, status=status_code
                ).inc()

                logger.error(
                    f"Request failed: {method} {endpoint}",
                    exc_info=True,
                    extra={"endpoint": endpoint, "method": method},
                )

                # Re-raise exception
                raise

            finally:
                # Always track latency
                duration = time.time() - start_time
                prometheus_metrics.http.request_duration.labels(
                    method=method, endpoint=endpoint
                ).observe(duration)

        return instrumented

    return decorator


def create_instrumented_wrapper(
    prometheus_metrics: Any, endpoint: str
) -> Callable[[Callable], Callable]:
    """
    Create an instrumented wrapper for a route handler.

    This is a helper for route factories that need to wrap handlers
    without using the decorator syntax.

    Args:
        prometheus_metrics: PrometheusMetrics instance
        endpoint: Endpoint path (e.g., "/api/tasks/create")

    Returns:
        Function that wraps a handler with instrumentation

    Example:
        wrapper = create_instrumented_wrapper(metrics, "/api/tasks/create")
        instrumented_handler = wrapper(original_handler)
    """

    def wrapper(handler: Callable) -> Callable:
        return instrument_handler(prometheus_metrics, endpoint_name=endpoint)(handler)

    return wrapper
