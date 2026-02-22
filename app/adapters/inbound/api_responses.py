"""
API Response Helpers - Result[T] Boundary Conversion
====================================================

Converts Result[T] to JSONResponse at HTTP boundaries via @boundary_handler.

Modern Usage (via boundary_handler):
    @rt("/api/example", methods=["GET"])
    @boundary_handler()
    async def example_route(request):
        result = await service.get_data()
        return result  # Auto-converted to JSONResponse

Legacy Direct Usage (calendar UI components only):
    from adapters.inbound.api_responses import error_response
    return error_response("Not found", status_code=404)

Available Functions:
    - success_response() - Used by @boundary_handler
    - error_response() - Used by @boundary_handler
    - build_metadata() - Used by services
    - intelligence_metadata() - Used by intelligence services
"""

from datetime import datetime
from typing import Any

from starlette.responses import JSONResponse

from core.ports import PydanticModel


def success_response(
    data: Any,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> JSONResponse:
    """
    Create standardized success response.

    Args:
        data: Response data (dict, list, Pydantic model, or primitive),
        status_code: HTTP status code (default 200),
        headers: Optional custom headers,
        metadata: Optional metadata to include in response

    Returns:
        JSONResponse with standardized success format,

    Example:
        >>> success_response({"items": [1, 2, 3]}, status_code=200)
        JSONResponse({"success": True, "data": {"items": [1, 2, 3]}}, 200)
    """
    # Handle Pydantic model serialization
    if isinstance(data, PydanticModel):
        content = data.model_dump()
    elif isinstance(data, list) and data and isinstance(data[0], PydanticModel):
        content = [item.model_dump() for item in data]
    else:
        content = data

    response_body = {"success": True, "data": content}

    # Add optional metadata
    if metadata:
        response_body.update(metadata)

    return JSONResponse(content=response_body, status_code=status_code, headers=headers or {})


def error_response(
    message: str,
    details: Any | None = None,
    status_code: int = 400,
    headers: dict[str, str] | None = None,
    error_code: str | None = None,
) -> JSONResponse:
    """
    Create standardized error response.

    Args:
        message: Human-readable error message,
        details: Optional detailed error information (dict, list, or string),
        status_code: HTTP status code (default 400),
        headers: Optional custom headers,
        error_code: Optional machine-readable error code

    Returns:
        JSONResponse with standardized error format,

    Example:
        >>> error_response("Validation failed", details={"field": "email"}, status_code=400)
        JSONResponse({"success": False, "error": "Validation failed", "details": {...}}, 400)
    """
    content = {"success": False, "error": message}

    # Add optional details
    if details is not None:
        content["details"] = details

    # Add optional error code
    if error_code:
        content["error_code"] = error_code

    return JSONResponse(content=content, status_code=status_code, headers=headers or {})


def build_metadata(user_uid: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """
    Build standardized metadata block for intelligence responses.

    Common metadata pattern across ALL intelligence APIs:
    - generated_at: ISO timestamp (always included)
    - user_uid: User identifier (if provided)
    - Any additional domain-specific fields (via kwargs)

    Args:
        user_uid: User identifier
        **kwargs: Additional metadata fields (period, analysis_scope, etc.)

    Returns:
        Metadata dictionary

    Example:
        >>> build_metadata(user_uid="demo_user", period="90_days", habits_analyzed=23)
        {
            "generated_at": "2025-10-20T...",
            "user_uid": "demo_user",
            "period": "90_days",
            "habits_analyzed": 23
        }
    """
    metadata = {"generated_at": datetime.now().isoformat()}

    if user_uid:
        metadata["user_uid"] = user_uid

    metadata.update(kwargs)
    return metadata


def intelligence_metadata(
    feature_type: str, user_uid: str | None = None, **kwargs: Any
) -> dict[str, Any]:
    """
    Build intelligence-specific metadata with feature type.

    Args:
        feature_type: Type of intelligence feature (e.g., "behavioral_insights", "pattern_analysis")
        user_uid: User identifier
        **kwargs: Additional metadata fields

    Returns:
        Intelligence metadata dictionary with feature_type

    Example:
        >>> intelligence_metadata(
        ...     "behavioral_insights", user_uid="demo_user", habits_analyzed=23
        ... )
        {
            "feature_type": "behavioral_insights",
            "generated_at": "2025-10-20T...",
            "user_uid": "demo_user",
            "habits_analyzed": 23
        }
    """
    metadata = build_metadata(user_uid=user_uid, **kwargs)
    metadata["feature_type"] = feature_type
    return metadata


__all__ = [
    "build_metadata",
    "error_response",
    "intelligence_metadata",
    "success_response",
]
