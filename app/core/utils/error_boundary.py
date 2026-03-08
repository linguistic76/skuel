"""
Error Boundary Utilities — Generic Safety Wrappers
===================================================

Framework-free decorators for wrapping operations in Result[T] error handling.
These are used by services, backends, and event handlers to ensure all
operations return Results and exceptions are properly captured.

HTTP-specific boundary converters (boundary_handler, result_to_response)
live in adapters/inbound/boundary.py.

See: /docs/patterns/ERROR_HANDLING.md
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from core.utils.result_simplified import Errors, Result

logger = logging.getLogger(__name__)


# ============================================================================
# SERVICE HELPERS - For Internal Use
# ============================================================================


def exception_to_result[R, **P](
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
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
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            result = await func(*args, **kwargs)
            # Ensure we return a Result
            if not isinstance(result, Result):
                return Result.ok(result)  # type: ignore[return-value]
            return result
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}")
            return Result.fail(Errors.system(message=f"Exception in {func.__name__}", exception=e))  # type: ignore[return-value]

    return wrapper  # type: ignore[return-value]


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


def safe_backend_operation[R, **P](
    operation_name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
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

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                result = await func(*args, **kwargs)
                # Wrap non-Result returns
                if not isinstance(result, Result):
                    return Result.ok(result)  # type: ignore[return-value]
                return result

            except Exception as e:
                logger.error(f"Backend operation {operation_name} failed: {e}")

                from core.utils.result_simplified import Errors

                error = Errors.database(operation=operation_name, message=str(e))
                return Result.fail(error)  # type: ignore[return-value]

        return wrapper  # type: ignore[return-value]

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
