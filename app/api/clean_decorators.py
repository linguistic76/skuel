"""
Clean API Decorators
====================

Decorators for API routes without legacy dependencies.
"""

__version__ = "1.0"


from collections.abc import Callable
from functools import wraps
from typing import Any


def json_api_route(
    path: str, methods: list[str] | None = None
) -> Callable[[Callable[..., Any]], Any]:
    """
    Decorator for JSON API routes.

    Args:
        path: The route path
        methods: HTTP methods (default: ['GET'])
    """
    if methods is None:
        methods = ["GET"]

    def decorator(func: Callable[..., Any]) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        # Add custom attributes to the wrapper function
        wrapper.route_path = path  # type: ignore[attr-defined]
        wrapper.route_methods = methods  # type: ignore[attr-defined]
        wrapper.is_json_api = True  # type: ignore[attr-defined]
        return wrapper

    return decorator


def dashboard_page_route(path: str) -> Callable[[Callable[..., Any]], Any]:
    """
    Decorator for dashboard page routes.

    Args:
        path: The route path
    """

    def decorator(func: Callable[..., Any]) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        # Add custom attributes to the wrapper function
        wrapper.route_path = path  # type: ignore[attr-defined]
        wrapper.route_methods = ["GET"]  # type: ignore[attr-defined]
        wrapper.is_dashboard = True  # type: ignore[attr-defined]
        return wrapper

    return decorator
