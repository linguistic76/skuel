"""
Error Boundary Utilities
========================

Implements the "Results internally, exceptions at boundaries" pattern.
Provides utilities for converting between Results and exceptions at system boundaries.

Key Principles:
- Services return Result[T] for all operations
- Backends return Result[T] for database operations
- Routes (boundaries) convert Results to HTTP responses or raise exceptions
- Clean separation of concerns
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from starlette.responses import JSONResponse

from core.utils.result_simplified import ErrorCategory, ErrorContext, Errors, Result

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
    """
    if result.is_ok:
        return JSONResponse(content=result.value, status_code=success_status)

    # Map error categories to HTTP status codes
    error = result.expect_error()
    status_map = {
        ErrorCategory.VALIDATION: 400,  # Bad input
        ErrorCategory.FORBIDDEN: 403,  # Access denied (authenticated but not authorized)
        ErrorCategory.NOT_FOUND: 404,  # Resource not found
        ErrorCategory.BUSINESS: 422,  # Business rule violation
        ErrorCategory.DATABASE: 503,  # Service temporarily unavailable
        ErrorCategory.INTEGRATION: 502,  # Bad gateway (external service issue)
        ErrorCategory.SYSTEM: 500,  # Internal server error
    }

    status_code = status_map.get(error.category, 500)

    # Return error context as JSON
    return JSONResponse(content=error.to_dict(), status_code=status_code)


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


# ============================================================================
# SERVICE HELPERS - For Internal Use
# ============================================================================


def exception_to_result(func: Callable) -> Callable:
    """
    Decorator that catches exceptions and converts them to Result.fail().
    Used internally in services to ensure all operations return Results.

    Usage:
        @exception_to_result
        async def get_user(self, uid: str) -> Result[User]:
            user = await self.backend.get(uid)  # Might raise
            return Result.ok(user)
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Result[Any]:
        try:
            result = await func(*args, **kwargs)
            # Ensure we return a Result
            if not isinstance(result, Result):
                return Result.ok(result)
            return result
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}")
            return Result.fail(Errors.system(message=f"Exception in {func.__name__}", exception=e))

    return wrapper


def chain_results(*operations: Callable[..., Awaitable[Result[Any]]]) -> Callable:
    """
    Chain multiple Result-returning operations.
    Stops at first error and returns it.

    Usage:
        @chain_results(validate_input, check_permissions, perform_operation)
        async def complex_operation(self, data) -> Result[Output]:
            return Result.ok(data)

    Note: Generic typing of decorator chains is complex in Python's type system.
    The wrapper preserves the return type of the decorated function.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Result[Any]:
            # Run each operation in sequence
            for operation in operations:
                result = await operation(*args, **kwargs)
                if result.is_error:
                    return result  # type: ignore[no-any-return]

            # All operations succeeded, run the main function
            return await func(*args, **kwargs)  # type: ignore[no-any-return]

        return wrapper

    return decorator


# ============================================================================
# BACKEND HELPERS - For Data Layer
# ============================================================================


def safe_backend_operation(operation_name: str) -> Callable[[Callable], Callable]:
    """
    Decorator for backend operations that ensures they return Results.
    Catches database exceptions and converts them to Result.fail().

    Usage:
        @safe_backend_operation("fetch_user")
        async def get_user(self, uid: str) -> Result[User]:
            # Database operation that might throw
            record = await self.execute_query(...)
            return self._deserialize(record)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Result:
            try:
                result = await func(*args, **kwargs)
                # Wrap non-Result returns
                if not isinstance(result, Result):
                    return Result.ok(result)
                return result

            except Exception as e:
                logger.error(f"Backend operation {operation_name} failed: {e}")

                from core.utils.result_simplified import Errors

                error = Errors.database(operation=operation_name, message=str(e))
                return Result.fail(error)

        return wrapper

    return decorator


# ============================================================================
# EVENT HANDLER HELPERS
# ============================================================================


def safe_event_handler(event_name: str) -> Callable[[Callable], Callable]:
    """
    Decorator for event handlers - logs errors with structured context but doesn't propagate.

    Event handlers intentionally don't propagate errors because:
    1. Event handlers run asynchronously
    2. The event bus may have multiple handlers for the same event
    3. One handler failing shouldn't prevent other handlers from running

    Usage:
        @safe_event_handler("knowledge.applied_in_task")
        async def handle_knowledge_applied(self, event) -> None:
            await self.increment_substance_metric(...)

    The decorator provides:
    - Structured logging with event context
    - Error categorization for monitoring
    - Consistent error handling across all event handlers
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> None:
            try:
                await func(*args, **kwargs)
            except Exception as e:
                # Extract event info if available
                event_info = {}
                if len(args) > 1:
                    event = args[1]  # First arg is self, second is event
                    event_dict = getattr(event, "__dict__", None)
                    if event_dict:
                        event_info = {
                            k: str(v) for k, v in event_dict.items() if not k.startswith("_")
                        }

                logger.error(
                    f"Event handler failed: {event_name}",
                    extra={
                        "event_name": event_name,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "handler": func.__name__,
                        "event_data": event_info,
                    },
                )

        return wrapper

    return decorator


# ============================================================================
# MIGRATION HELPERS
# ============================================================================


def migrate_to_result(value: Any, error_msg: str = "Operation failed") -> Result:
    """
    Helper to migrate existing code that returns None on failure.

    Usage:
        # Old: user = await backend.get_user(uid)  # Returns None if not found
        # New: result = migrate_to_result(
        #     await backend.get_user(uid),
        #     f"User {uid} not found"
        # )
    """
    if value is None:
        from core.utils.result_simplified import Errors

        return Result.fail(Errors.not_found("resource", error_msg))
    return Result.ok(value)


def unwrap_or_none[T](result: Result[T]) -> T | None:
    """
    Get the value from a Result or None if it's an error.
    Useful during migration when backends expect None for "not found".

    Usage:
        result = await service.get_user(uid)
        user = unwrap_or_none(result)  # None if error, user if success
    """
    # Type-safe extraction: narrow type before accessing value
    if result.is_ok:
        return result.value
    return None


# ============================================================================
# EXAMPLES
# ============================================================================

"""
Example 1: Service using Result internally
==========================================

class UserService:
    @exception_to_result
    async def create_user(self, data: dict) -> Result[User]:
        # Validation
        if not data.get("email"):
            return Result.fail(Errors.validation("Email is required", field="email"))

        # Check duplicates
        existing = await self.backend.find_by_email(data["email"])
        if existing.is_ok and existing.value:
            return Result.fail(conflict_error("User already exists"))

        # Create user
        user = User(**data)
        result = await self.backend.create(user)

        return result  # Already a Result from backend


Example 2: Route boundary converting Result to response
=======================================================

@rt("/api/users", methods=["POST"])
@boundary_handler(success_status=201)
async def create_user_route(request):
    data = await request.json()
    result = await user_service.create_user(data)
    return result  # Automatically converted to (body, status_code)


Example 3: Backend returning Result
====================================

class UserBackend(Neo4jBackendBase):
    @safe_backend_operation("create_user")
    async def create(self, user: User) -> Result[User]:
        query = "CREATE (u:User $props) RETURN u"
        records = await self.execute_query(query, props=user.dict())

        if not records:
            return Result.fail(Errors.database("operation", "Failed to create user"))

        return Result.ok(self._deserialize(records[0]["u"]))
"""
