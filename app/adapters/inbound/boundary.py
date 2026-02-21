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
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from core.utils.result_simplified import ErrorCategory, ErrorContext, Result

logger = logging.getLogger(__name__)

T = TypeVar("T")

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

    # Return error context as JSON with toast header for errors
    response = JSONResponse(content=error.to_dict(), status_code=status_code)
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


def boundary_handler(success_status: int = 200) -> Callable[[Callable], Callable]:
    """
    Decorator for route handlers that automatically converts Results to responses.

    Usage:
        @boundary_handler()
        async def create_task(request):
            result = await task_service.create(...)  # Returns Result[Task]
            return result  # Automatically converted to response
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = await func(*args, **kwargs)

                # If it's a Result, convert to response
                if isinstance(result, Result):
                    return result_to_response(result, success_status)

                # Otherwise return as-is
                return result

            except HTTPException:
                raise  # Let Starlette handle with correct status code (e.g. 401)
            except Exception as e:
                # Log unexpected errors
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                # Return generic error response
                return {"error": str(e)}, 500

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
