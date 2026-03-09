"""
HTTP Boundary Utilities
=======================

Implements the "Results internally, exceptions at boundaries" pattern.
Converts Result[T] to HTTP responses at route boundaries.

Key Principles:
- Services return Result[T] for all operations
- Backends return Result[T] for database operations
- Routes (boundaries) convert Results to HTTP responses or raise exceptions

See: /docs/patterns/ERROR_HANDLING.md
"""

import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, ErrorContext, Result

logger = logging.getLogger(__name__)

P = ParamSpec("P")

# ============================================================================
# BOUNDARY CONVERTERS - For Routes/Adapters
# ============================================================================


def result_to_response[T](result: Result[T], success_status: int = 200) -> JSONResponse:
    """
    Convert a Result to an HTTP JSON response.
    Used at route boundaries to convert service Results to HTTP responses.

    Args:
        result: The Result from a service operation,
        success_status: HTTP status code for successful results

    Returns:
        JSONResponse with appropriate status code

    Note:
        If result.value is a dict with a '_headers' key, those headers will be
        added to the response and the '_headers' key will be removed from the content.
        This allows services to specify custom headers (e.g., toast notifications):

        return Result.ok({
            "task": task_data,
            "_headers": {
                "X-Toast-Message": "Task created successfully",
                "X-Toast-Type": "success"
            }
        })
    """
    if result.is_ok:
        content = result.value
        headers = {}

        # Extract _headers if present in dict response
        if isinstance(content, dict) and "_headers" in content:
            headers = content.pop("_headers")

        response = JSONResponse(content=content, status_code=success_status)

        # Add custom headers
        for key, value in headers.items():
            response.headers[key] = value

        return response

    # Map error categories to HTTP status codes
    error = result.expect_error()
    status_code = _get_status_for_error(error)

    # Return client-safe error context (no stack traces or internal details)
    response = JSONResponse(content=error.to_client_dict(), status_code=status_code)
    response.headers["X-Toast-Message"] = error.message
    response.headers["X-Toast-Type"] = "error"

    return response


def result_to_exception[T](result: Result[T]) -> T:
    """
    Unwrap a Result or raise an exception if it's an error.
    Used at boundaries when exception handling is preferred.

    Args:
        result: The Result to unwrap,

    Returns:
        The value if successful

    Raises:
        RuntimeError: If the result is an error
    """
    if result.is_ok:
        return result.value
    # Convert error context to exception
    error = result.expect_error()
    raise RuntimeError(f"{error.category.value}: {error.message}")


def boundary_handler(
    success_status: int = 200,
) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Coroutine[Any, Any, Any]]]:
    """
    Decorator for route handlers that automatically converts Results to responses.

    Typed with ParamSpec to preserve the wrapped function's parameter signature,
    enabling mypy to check call sites properly.

    Usage:
        @boundary_handler()
        async def create_task(request):
            result = await task_service.create(...)  # Returns Result[Task]
            return result  # Automatically converted to response
    """

    def decorator(
        func: Callable[P, Awaitable[Any]],
    ) -> Callable[P, Coroutine[Any, Any, Any]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            try:
                result = await func(*args, **kwargs)

                # If it's a Result, convert to response
                if isinstance(result, Result):
                    return result_to_response(result, success_status)

                # Otherwise return as-is (e.g. FastHTML FT nodes for UI routes)
                return result

            except HTTPException:
                raise  # Let Starlette handle with correct status code (e.g. 401)
            except Exception as e:
                # Log full error for debugging (server-side only)
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                # Return generic message — never expose exception details to clients
                return JSONResponse({"error": "An internal error occurred"}, status_code=500)

        return wrapper

    return decorator


def _get_status_for_error(error: ErrorContext) -> int:
    """Get appropriate HTTP status code for an error."""
    status_map = {
        ErrorCategory.VALIDATION: 400,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.BUSINESS: 422,
        ErrorCategory.DATABASE: 503,
        ErrorCategory.INTEGRATION: 502,
        ErrorCategory.SYSTEM: 500,
    }
    return status_map.get(error.category, 500)


# ============================================================================
# INSTRUMENTED BOUNDARY - Combines Prometheus metrics + Result[T] conversion
# ============================================================================

_boundary_logger = get_logger(__name__)


def instrument_with_boundary_handler(
    prometheus_metrics: Any,
    endpoint: str,
    success_status: int = 200,
) -> Callable[[Callable], Callable]:
    """
    Combined decorator that instruments HTTP requests AND converts Result[T] to JSONResponse.

    This integrates Prometheus instrumentation with SKUEL's boundary_handler pattern,
    tracking metrics while properly handling Result[T] return types.

    Args:
        prometheus_metrics: PrometheusMetrics instance
        endpoint: Endpoint path for metrics labels
        success_status: HTTP status code for successful results

    Returns:
        Decorated handler that tracks metrics and converts Results

    Example:
        @instrument_with_boundary_handler(metrics, "/api/tasks/create", success_status=201)
        async def create(request) -> Result[Task]:
            return await service.create(...)
    """

    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(request, *args: Any, **kwargs: Any) -> JSONResponse:
            start_time = time.time()
            method = request.method
            status_code = success_status

            try:
                # Execute handler
                result = await handler(request, *args, **kwargs)

                # Convert Result[T] to JSONResponse
                if isinstance(result, Result):
                    response = result_to_response(result, success_status)
                    status_code = response.status_code
                else:
                    # If not a Result, assume it's already a response
                    response = result
                    resp_status = getattr(response, "status_code", None)
                    if resp_status is not None:
                        status_code = resp_status

                # Track successful request
                if prometheus_metrics:
                    prometheus_metrics.http.requests_total.labels(
                        method=method, endpoint=endpoint, status=status_code
                    ).inc()

                return response

            except Exception:
                # Track failed request
                status_code = 500
                if prometheus_metrics:
                    prometheus_metrics.http.requests_total.labels(
                        method=method, endpoint=endpoint, status=status_code
                    ).inc()

                    prometheus_metrics.http.errors_total.labels(
                        method=method, endpoint=endpoint, status=status_code
                    ).inc()

                _boundary_logger.error(
                    f"Request failed: {method} {endpoint}",
                    exc_info=True,
                    extra={"endpoint": endpoint, "method": method},
                )

                # Re-raise exception
                raise

            finally:
                # Always track latency
                if prometheus_metrics:
                    duration = time.time() - start_time
                    prometheus_metrics.http.request_duration.labels(
                        method=method, endpoint=endpoint
                    ).observe(duration)

        # Override return annotation to prevent FastHTML from trying to construct Result[T]
        wrapper.__annotations__["return"] = JSONResponse

        return wrapper

    return decorator
