"""
Service Decorators - Generic Error Handling and Validation
===========================================================

This module provides reusable decorators for all SKUEL services.

Extracted from base_service.py to promote reusability across the entire codebase.

Core decorators:
- with_error_handling: Generic try/except wrapper with error categorization
- requires_graph_intelligence: Validates graph_intel availability for Phase 1-4 methods

Philosophy:
- Decorators are pure utilities (no service dependencies)
- Error categorization uses type checking (not string matching)
- Supports both async and sync functions
- FAIL-FAST: No graceful degradation - errors should surface, not hide

DRY Impact: These decorators eliminate ~500+ repetitive try/except patterns.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any, Literal, TypeVar

from core.services.protocols import HasLogger
from core.utils.result_simplified import Errors, Result

# Type variable for preserving return types through decorators
F = TypeVar("F", bound=Callable[..., Any])

# Type alias for forced error types
ErrorType = Literal["database", "system", "validation", "not_found", "auto"]


def _categorize_exception(
    e: Exception,
    operation: str,
    error_type: ErrorType,
    context: dict[str, Any] | None = None,
) -> Result[Any]:
    """
    Shared exception categorization logic.

    Extracted to eliminate duplication between async/sync wrappers.

    Args:
        e: The caught exception
        operation: Operation name for error messages
        error_type: Forced error type or "auto" for intelligent categorization
        context: Optional context dict (uid, path, etc.) for error details

    Returns:
        Result.fail() with appropriate error type
    """
    # If error type is forced, use it directly
    if error_type != "auto":
        if error_type == "database":
            return Result.fail(
                Errors.database(operation=operation, message=str(e), details=context)
            )
        elif error_type == "validation":
            return Result.fail(
                Errors.validation(
                    message=str(e),
                    field=context.get("field", "unknown") if context else "unknown",
                )
            )
        elif error_type == "not_found":
            entity_type = context.get("entity_type", "Entity") if context else "Entity"
            return Result.fail(Errors.not_found(f"{entity_type}: {e!s}"))
        else:  # system
            return Result.fail(Errors.system(message=str(e), operation=operation, exception=e))

    # Auto-categorization: Check exception type first
    exception_name = type(e).__name__

    # ValueError -> validation error
    if isinstance(e, ValueError):
        return Result.fail(
            Errors.validation(
                message=str(e),
                field=context.get("field", "unknown") if context else "unknown",
            )
        )

    # Database-related exceptions
    if "Neo4j" in exception_name or "Driver" in exception_name or "Session" in exception_name:
        return Result.fail(Errors.database(operation=operation, message=str(e), details=context))

    # String matching fallback for legacy error messages
    error_msg_lower = str(e).lower()
    if "not found" in error_msg_lower:
        return Result.fail(Errors.not_found(str(e)))
    elif "database" in error_msg_lower or "neo4j" in error_msg_lower:
        return Result.fail(Errors.database(operation=operation, message=str(e), details=context))
    elif "validation" in error_msg_lower or "invalid" in error_msg_lower:
        return Result.fail(
            Errors.validation(
                message=str(e),
                field=context.get("field", "unknown") if context else "unknown",
            )
        )

    # Default to system error
    return Result.fail(Errors.system(message=str(e), operation=operation, exception=e))


def _extract_context(
    func: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    uid_param: str | None,
) -> dict[str, Any]:
    """
    Extract context from function arguments for error messages.

    Args:
        func: The decorated function
        args: Positional arguments
        kwargs: Keyword arguments
        uid_param: Name of the UID parameter to extract

    Returns:
        Context dict with extracted values
    """
    context: dict[str, Any] = {}

    if uid_param:
        # Try kwargs first
        if uid_param in kwargs:
            context["uid"] = kwargs[uid_param]
        else:
            # Try positional args using function signature
            try:
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                if uid_param in params:
                    idx = params.index(uid_param)
                    # Account for 'self' in method signatures
                    if idx < len(args):
                        context["uid"] = args[idx]
            except (ValueError, IndexError):
                pass

    return context


def with_error_handling(
    operation: str = "operation",
    error_type: ErrorType = "auto",
    uid_param: str | None = None,
) -> Callable[[F], F]:
    """
    Generic error handling decorator.

    Eliminates repetitive try/except patterns across all service methods.
    This decorator addresses a DRY violation that appeared 500+ times in the codebase.

    Args:
        operation: Operation name for error messages and logging
        error_type: Force a specific error type or "auto" for intelligent categorization
            - "database": Always return Errors.database()
            - "system": Always return Errors.system()
            - "validation": Always return Errors.validation()
            - "not_found": Always return Errors.not_found()
            - "auto": (default) Categorize based on exception type
        uid_param: Name of the UID parameter to extract for error context
            If specified, the UID will be included in error details.

    Returns:
        Decorated function with automatic error handling

    Examples:
        # Basic usage (auto-categorization)
        @with_error_handling("create_task")
        async def create(self, entity: Task) -> Result[Task]:
            return await self.backend.create(entity)

        # Force database error type (for known DB operations)
        @with_error_handling("search", error_type="database")
        async def search(self, query: str) -> Result[list[Task]]:
            return await self.backend.execute_query(...)

        # Extract UID for error context
        @with_error_handling("get_task", error_type="database", uid_param="uid")
        async def get(self, uid: str) -> Result[Task]:
            return await self.backend.get(uid)
            # On error: {"uid": "task:123"} included in error details

    Error Handling (when error_type="auto"):
        - ValueError → Errors.validation()
        - Neo4j exceptions → Errors.database()
        - "not found" messages → Errors.not_found()
        - All others → Errors.system()
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return await func(self, *args, **kwargs)
            except Exception as e:
                if isinstance(self, HasLogger):
                    self.logger.error(f"Failed to {operation}: {e}")

                context = _extract_context(func, args, kwargs, uid_param)
                return _categorize_exception(e, operation, error_type, context)

        @wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                if isinstance(self, HasLogger):
                    self.logger.error(f"Failed to {operation}: {e}")

                context = _extract_context(func, args, kwargs, uid_param)
                return _categorize_exception(e, operation, error_type, context)

        # Return appropriate wrapper based on function type
        # Cast needed because we return a wrapper with same signature
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def requires_graph_intelligence(operation: str):
    """
    Decorator for Phase 1-4 graph intelligence methods.

    Eliminates repetitive graph_intel availability checks across all services.
    This pattern appears 38+ times in the codebase with identical implementation:

    if not self.graph_intel:
        return Result.fail(Errors.system(
            message="GraphIntelligenceService not available - Phase 1-4 queries disabled",
            operation="method_name"
        ))

    Single decorator ensures consistency and reduces maintenance burden.

    Args:
        operation: Operation name for error messages

    Returns:
        Decorated function with automatic graph_intel validation

    Example:
        # Before (repeated in every Phase 1-4 method):
        async def get_habit_with_context(self, uid: str) -> Result:
            if not self.graph_intel:
                return Result.fail(Errors.system(
                    message="GraphIntelligenceService not available - Phase 1-4 queries disabled",
                    operation="get_habit_with_context"
                ))
            # ... method logic

        # After (clean and declarative):
        from core.utils.decorators import requires_graph_intelligence

        @requires_graph_intelligence("get_habit_with_context")
        async def get_habit_with_context(self, uid: str) -> Result:
            # ... method logic only

    Note:
        Services that use Phase 1-4 graph intelligence should store graph_intel
        in their __init__ method (usually named graph_intelligence_service).
    """

    def decorator(func) -> Any:
        @wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            graph_intel = getattr(self, "graph_intel", None)
            if not graph_intel:
                return Result.fail(
                    Errors.system(
                        message="GraphIntelligenceService not available - Phase 1-4 queries disabled",
                        operation=operation,
                    )
                )
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
