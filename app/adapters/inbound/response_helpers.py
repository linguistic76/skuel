"""
Unified Response Helpers
========================

Shared response helpers for all route handlers.
Eliminates duplicate response functions across route files.

FASTHTML COMPATIBILITY (November 4, 2025):
These helpers return tuples `(dict, status_code)` instead of JSONResponse objects.
FastHTML automatically converts these to proper JSON responses.
"""

from typing import Any

from core.services.protocols import to_dict


# API-COMPAT: API-COMPAT-001 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
def success_response(
    data: Any, status_code: int = 200, headers: dict | None = None
) -> tuple[dict[str, Any], int]:
    """
    Create standardized success response with Pydantic model support.

    Args:
        data: Response data (supports Pydantic models)
        status_code: HTTP status code (default 200)
        headers: Optional response headers (ignored for FastHTML compatibility)

    Returns:
        Tuple of (response_dict, status_code) for FastHTML auto-conversion
    """
    # Use protocol-based conversion
    content = to_dict(data)
    return ({"success": True, "data": content}, status_code)


def error_response(
    message: str, details: Any = None, status_code: int = 400
) -> tuple[dict[str, Any], int]:
    """
    Create standardized error response.

    Args:
        message: Error message
        details: Optional error details
        status_code: HTTP status code (default 400)

    Returns:
        Tuple of (response_dict, status_code) for FastHTML auto-conversion
    """
    content: dict[str, Any] = {"success": False, "error": message}
    if details:
        content["details"] = details
    return (content, status_code)


def not_found_response(resource: str = "Resource") -> tuple[dict[str, Any], int]:
    """Create standardized 404 response."""
    return error_response(f"{resource} not found", status_code=404)


def validation_error_response(errors: Any) -> tuple[dict[str, Any], int]:
    """Create standardized validation error response."""
    return error_response("Validation failed", details=errors, status_code=422)


def unauthorized_response(message: str = "Unauthorized") -> tuple[dict[str, Any], int]:
    """Create standardized 401 response."""
    return error_response(message, status_code=401)


def server_error_response(message: str = "Internal server error") -> tuple[dict[str, Any], int]:
    """Create standardized 500 response."""
    return error_response(message, status_code=500)
