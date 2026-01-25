"""
API Response Helpers - Centralized Response Formatting
======================================================

Standardized JSON API response helpers used across all intelligence APIs.

This module provides consistent response formatting for:
- Success responses with data
- Error responses with details
- Intelligence-specific metadata
- Standardized status codes

Usage:
    from core.utils.api_responses import success_response, error_response

    @rt("/api/example", methods=["GET"])
    async def example_route(request):
        try:
            data = await service.get_data()
            return success_response(data)
        except Exception as e:
            return error_response(str(e), status_code=500)
"""

from datetime import datetime
from typing import Any

from starlette.responses import JSONResponse

from core.services.protocols import PydanticModel


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


def intelligence_response(
    data: Any,
    status_code: int = 200,
    intelligence_version: str = "v2",
    generated_at: datetime | None = None,
    confidence: float | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """
    Create intelligence-specific success response with metadata.

    Args:
        data: Intelligence data,
        status_code: HTTP status code (default 200),
        intelligence_version: Version of intelligence engine (default "v2"),
        generated_at: Timestamp of generation (defaults to now),
        confidence: Optional confidence score (0.0-1.0),
        headers: Optional custom headers

    Returns:
        JSONResponse with intelligence metadata,

    Example:
        >>> intelligence_response({"insights": [...]}, ConfidenceLevel.HIGH)
        JSONResponse({
            "success": True,
            "data": {"insights": [...]},
            "intelligence_version": "v2",
            "generated_at": "2025-10-09T...",
            "confidence": 0.92
        }, 200)
    """
    metadata = {
        "intelligence_version": intelligence_version,
        "generated_at": (generated_at or datetime.now()).isoformat(),
    }

    if confidence is not None:
        metadata["confidence"] = confidence

    return success_response(data=data, status_code=status_code, headers=headers, metadata=metadata)


def analytics_response(
    data: Any,
    period: str | None = None,
    aggregation: str | None = None,
    total_count: int | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """
    Create analytics-specific success response with metadata.

    Args:
        data: Analytics data,
        period: Time period of analytics (e.g., "day", "week", "month"),
        aggregation: Aggregation method used (e.g., "sum", "average", "count"),
        total_count: Total number of items analyzed,
        status_code: HTTP status code (default 200),
        headers: Optional custom headers

    Returns:
        JSONResponse with analytics metadata,

    Example:
        >>> analytics_response({"metrics": {...}}, period="week", total_count=150)
        JSONResponse({
            "success": True,
            "data": {"metrics": {...}},
            "period": "week",
            "total_count": 150,
            "generated_at": "2025-10-09T..."
        }, 200)
    """
    metadata = {"generated_at": datetime.now().isoformat()}

    if period:
        metadata["period"] = period

    if aggregation:
        metadata["aggregation"] = aggregation

    if total_count is not None:
        metadata["total_count"] = total_count

    return success_response(data=data, status_code=status_code, headers=headers, metadata=metadata)


def recommendation_response(
    recommendations: Any,
    recommendation_type: str | None = None,
    personalization_score: float | None = None,
    total_candidates: int | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """
    Create recommendation-specific success response with metadata.

    Args:
        recommendations: List of recommendations,
        recommendation_type: Type of recommendations (e.g., "content", "learning", "tasks"),
        personalization_score: Personalization score (0.0-1.0),
        total_candidates: Total number of items considered,
        status_code: HTTP status code (default 200),
        headers: Optional custom headers

    Returns:
        JSONResponse with recommendation metadata,

    Example:
        >>> recommendation_response(
        ...     [...], recommendation_type="learning", personalization_score=0.87
        ... )
        JSONResponse({
            "success": True,
            "data": [...],
            "recommendation_type": "learning",
            "personalization_score": 0.87,
            "generated_at": "2025-10-09T..."
        }, 200)
    """
    metadata = {"generated_at": datetime.now().isoformat()}

    if recommendation_type:
        metadata["recommendation_type"] = recommendation_type

    if personalization_score is not None:
        metadata["personalization_score"] = personalization_score

    if total_candidates is not None:
        metadata["total_candidates"] = total_candidates

    return success_response(
        data=recommendations, status_code=status_code, headers=headers, metadata=metadata
    )


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
    "analytics_response",
    "build_metadata",
    "error_response",
    "error_response_legacy",
    "intelligence_metadata",
    "intelligence_response",
    "recommendation_response",
    "success_response",
    "success_response_legacy",
]
