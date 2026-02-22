"""
Mock Endpoint Decorators - Development and Testing Support
===========================================================

Decorators to mark and manage mock/stub endpoints in intelligence APIs.

This module provides:
- @mock_endpoint: Mark routes that return mock data
- @stub_endpoint: Mark routes with minimal stub implementation
- Mock data tracking and documentation
- Development-only endpoint filtering

Usage:
    from core.utils.mock_decorators import mock_endpoint, stub_endpoint

    @rt("/api/recommendations", methods=["GET"])
    @mock_endpoint(reason="Awaiting ML model training", version="v1")
    async def get_recommendations(request):
        return Result.ok(MOCK_RECOMMENDATIONS)
"""

import functools
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.ports.base_protocols import HasBody, IsMockEndpoint, IsStubEndpoint

logger = logging.getLogger(__name__)

# Track all mock endpoints for reporting
_MOCK_ENDPOINTS_REGISTRY = []
_STUB_ENDPOINTS_REGISTRY = []


def mock_endpoint(
    reason: str | None = None,
    version: str = "v1",
    planned_completion: str | None = None,
    backend_required: bool = True,
) -> Callable:
    """
    Decorator to mark routes that return mock/stub data.

    This decorator:
    - Adds metadata to identify mock endpoints
    - Logs warning when mock endpoint is called
    - Tracks mock endpoints for documentation
    - Can be filtered out in production builds

    Args:
        reason: Why this endpoint returns mock data (e.g., "Awaiting ML model"),
        version: Mock data version (default "v1"),
        planned_completion: Target date for real implementation (e.g., "2025-Q4"),
        backend_required: Whether real backend implementation is needed (default True)

    Returns:
        Decorated async function,

    Example:
        @rt("/api/tasks/ai-suggestions", methods=["GET"])
        @mock_endpoint(
            reason="Awaiting GPT-4 integration",
            planned_completion="2025-Q4",
            backend_required=True
        )
        async def get_ai_suggestions(request):
            return Result.ok(MOCK_AI_SUGGESTIONS)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Log warning that mock endpoint is being called
            logger.warning(
                f"🔶 MOCK ENDPOINT CALLED: {func.__name__} (reason: {reason or 'not specified'})"
            )

            # Call original function
            result = await func(*args, **kwargs)

            # Add mock metadata to response if it's a response with body
            if isinstance(result, HasBody) and isinstance(result.body, bytes):
                # For JSONResponse, we can't easily modify without re-parsing
                # Just log and return as-is
                pass

            return result

        # Add metadata to function for introspection
        # MyPy can't type-check dynamic function attributes, but this is a valid Python pattern
        wrapper._is_mock_endpoint = True  # type: ignore[attr-defined]
        wrapper._mock_reason = reason  # type: ignore[attr-defined]
        wrapper._mock_version = version  # type: ignore[attr-defined]
        wrapper._mock_planned_completion = planned_completion  # type: ignore[attr-defined]
        wrapper._mock_backend_required = backend_required  # type: ignore[attr-defined]
        wrapper._mock_registered_at = datetime.now().isoformat()  # type: ignore[attr-defined]

        # Register in global registry
        _MOCK_ENDPOINTS_REGISTRY.append(
            {
                "function_name": func.__name__,
                "reason": reason,
                "version": version,
                "planned_completion": planned_completion,
                "backend_required": backend_required,
                "registered_at": wrapper._mock_registered_at,  # type: ignore[attr-defined]
            }
        )

        return wrapper

    return decorator


def stub_endpoint(status: str = "minimal_implementation", todos: list | None = None) -> Callable:
    """
    Decorator to mark routes with minimal stub implementation.

    Stub endpoints have basic structure but limited functionality.
    Different from mock endpoints which return fabricated data.

    Args:
        status: Implementation status (e.g., "minimal", "partial", "skeleton"),
        todos: List of tasks needed for full implementation

    Returns:
        Decorated async function,

    Example:
        @rt("/api/habits/optimization", methods=["POST"])
        @stub_endpoint(
            status="partial",
            todos=["Add habit pattern analysis", "Integrate calendar data"]
        )
        async def optimize_habit_schedule(request):
            # Minimal implementation - just validates input
            body = await request.json()
            return Result.ok({"message": "Optimization queued"})
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Log info that stub endpoint is being called
            logger.info(f"🔸 STUB ENDPOINT CALLED: {func.__name__} (status: {status})")

            # Call original function
            return await func(*args, **kwargs)

        # Add metadata to function for introspection
        # MyPy can't type-check dynamic function attributes, but this is a valid Python pattern
        wrapper._is_stub_endpoint = True  # type: ignore[attr-defined]
        wrapper._stub_status = status  # type: ignore[attr-defined]
        wrapper._stub_todos = todos or []  # type: ignore[attr-defined]
        wrapper._stub_registered_at = datetime.now().isoformat()  # type: ignore[attr-defined]

        # Register in global registry
        _STUB_ENDPOINTS_REGISTRY.append(
            {
                "function_name": func.__name__,
                "status": status,
                "todos": todos or [],
                "registered_at": wrapper._stub_registered_at,  # type: ignore[attr-defined]
            }
        )

        return wrapper

    return decorator


def get_mock_endpoints_report() -> dict:
    """
    Generate report of all mock endpoints in the system.

    Returns:
        Dict with mock endpoint statistics and details,

    Example:
        >>> report = get_mock_endpoints_report()
        >>> print(f"Total mock endpoints: {report['total_mock_endpoints']}")
    """
    return {
        "total_mock_endpoints": len(_MOCK_ENDPOINTS_REGISTRY),
        "total_stub_endpoints": len(_STUB_ENDPOINTS_REGISTRY),
        "mock_endpoints": _MOCK_ENDPOINTS_REGISTRY,
        "stub_endpoints": _STUB_ENDPOINTS_REGISTRY,
        "generated_at": datetime.now().isoformat(),
    }


def is_mock_endpoint(func: Callable) -> bool:
    """
    Check if a function is decorated with @mock_endpoint.

    Args:
        func: Function to check,

    Returns:
        True if function is a mock endpoint

    Example:
        >>> is_mock_endpoint(get_recommendations)
        True
    """
    return isinstance(func, IsMockEndpoint) and func._is_mock_endpoint


def is_stub_endpoint(func: Callable) -> bool:
    """
    Check if a function is decorated with @stub_endpoint.

    Args:
        func: Function to check,

    Returns:
        True if function is a stub endpoint

    Example:
        >>> is_stub_endpoint(optimize_schedule)
        True
    """
    return isinstance(func, IsStubEndpoint) and func._is_stub_endpoint


__all__ = [
    "get_mock_endpoints_report",
    "is_mock_endpoint",
    "is_stub_endpoint",
    "mock_endpoint",
    "stub_endpoint",
]
