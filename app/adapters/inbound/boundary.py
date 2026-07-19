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
from json import JSONDecodeError
from types import MappingProxyType
from typing import Any, ParamSpec

from fasthtml.common import FT, to_xml
from pydantic_core import to_jsonable_python
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, ErrorContext, Errors, Result

logger = logging.getLogger(__name__)

P = ParamSpec("P")


# boundary: json-serialization — these helpers sit at the Result[T]→HTTP edge where
# T is genuinely erased: the input is whatever value any service returned (frozen
# domain dataclass, Pydantic model, dict, list, scalar) and the output is whatever
# JSON-basic shape it maps to. No concrete type can name either side.
def _unwrap_unserializable(value: Any) -> Any:
    """Fallback for types ``to_jsonable_python`` can't serialize natively.

    Frozen domain models wrap mutable dicts in ``MappingProxyType`` for deep
    immutability (e.g. ``Task.knowledge_confidence_scores``); unwrap those to
    plain dicts (the result is re-processed recursively). Anything else is a
    genuine type-design problem — raise so the boundary safety-net logs it.
    """
    if isinstance(value, MappingProxyType):
        return dict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def jsonable_content(content: Any) -> Any:  # boundary: json-serialization (see above)
    """Convert a service-layer value into JSON-safe Python.

    Handles the frozen domain dataclasses, Pydantic models, enums, datetimes,
    tuples, and nested containers that ``Result[T]`` values carry — Starlette's
    ``JSONResponse`` only accepts plain JSON types.
    """
    return to_jsonable_python(content, fallback=_unwrap_unserializable)


# ============================================================================
# BOUNDARY CONVERTERS - For Routes/Adapters
# ============================================================================


def result_to_response[T](result: Result[T], success_status: int = 200) -> Response:
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

        # Result[FT] handlers (the documented fragment convention) render as
        # HTML — jsonable_content cannot serialize FT nodes, so without this
        # branch every Result-wrapped fragment 500'd on SUCCESS.
        if isinstance(content, FT):
            return HTMLResponse(to_xml(content), status_code=success_status)

        headers = {}

        # Extract _headers if present in dict response
        if isinstance(content, dict) and "_headers" in content:
            headers = content.pop("_headers")

        response = JSONResponse(content=jsonable_content(content), status_code=success_status)

        # Add custom headers
        for key, value in headers.items():
            response.headers[key] = _header_safe(value)

        return response

    # Map error categories to HTTP status codes
    error = result.expect_error()
    status_code = _get_status_for_error(error)

    # Return client-safe error context (no stack traces or internal details)
    response = JSONResponse(content=error.to_client_dict(), status_code=status_code)
    response.headers["X-Toast-Message"] = _header_safe(error.message)
    response.headers["X-Toast-Type"] = "error"

    return response


def _header_safe(value: str) -> str:
    """Coerce a header value to latin-1 and a single line (RFC 9110).

    Error messages flow into X-Toast-Message verbatim; one em-dash must degrade
    the toast character, not 500 the whole response. Newlines are just as
    fatal: a multi-line Pydantic validation message in a header makes uvicorn
    drop the connection with NO response ("Invalid HTTP header value"), so
    CR/LF and other control characters collapse to spaces.
    """
    single_line = "".join(ch if ch == "\t" or (ch >= " " and ch != "\x7f") else " " for ch in value)
    return single_line.encode("latin-1", "replace").decode("latin-1")


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
            except Exception as e:  # safety-net: API boundary — catch-all after HTTPException
                # Log full error for debugging (server-side only)
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                # Return generic message — never expose exception details to clients
                return JSONResponse({"error": "An internal error occurred"}, status_code=500)

        return wrapper

    return decorator


def malformed_json_handler(request: Request, exc: Exception) -> Response:
    """Map a body-parse ``JSONDecodeError`` to a 400 validation response.

    FastHTML pre-parses ``application/json`` bodies during parameter
    extraction, BEFORE any handler runs — so a route's own malformed-body
    guard never executes and the raw ``JSONDecodeError`` would surface as a
    500. This is the single chokepoint that converts it to the same
    ``Errors.validation`` shape every API boundary emits.

    Only requests that declared a JSON content type are converted; a
    ``JSONDecodeError`` escaping a handler on any other request is a genuine
    server bug and is re-raised to keep its 500.

    Register via ``install_malformed_json_guard(app)`` (wired once at
    bootstrap in ``_create_web_app``).
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("application/json"):
        raise exc
    return result_to_response(Result.fail(Errors.validation("Malformed JSON in request body")))


def install_malformed_json_guard(app: FastHTMLApp) -> None:
    """Register the malformed-JSON → 400 handler on a FastHTML/Starlette app."""
    app.add_exception_handler(JSONDecodeError, malformed_json_handler)


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
        async def wrapper(request, *args: Any, **kwargs: Any) -> Response:
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

            except Exception:  # safety-net: metrics must not crash request
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
