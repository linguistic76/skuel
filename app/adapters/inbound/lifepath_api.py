"""
LifePath API Routes
===================

JSON API routes for LifePath domain operations.

Domain #14: The Destination - "Everything flows toward the life path"

API Routes:
- GET /api/lifepath/status - Get full status
- POST /api/lifepath/vision - Capture vision and get recommendations
- POST /api/lifepath/designate - Designate an LP as life path
- GET /api/lifepath/alignment - Get alignment data
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from core.models.lifepath_request import CaptureVisionRequest, DesignateLifePathRequest
from core.ports.query_types import (
    LifePathAlignmentResult,
    LifePathDesignation,
    LifePathRecommendation,
    LifePathStatus,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import LifePathOperations

logger = get_logger("skuel.routes.lifepath.api")


def create_lifepath_api_routes(
    app: Any,
    rt: Any,
    lifepath_service: "LifePathOperations",
) -> list[Any]:
    """
    Create LifePath API routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        lifepath_service: LifePath service facade

    Returns:
        List of registered route functions
    """

    @rt("/api/lifepath/status")
    @boundary_handler()
    async def api_get_status(request: Request) -> Result[LifePathStatus]:
        """Get full life path status."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return Result.fail(
                Errors.system("LifePath service unavailable", operation="get_status")
            )

        return await lifepath_service.get_full_status(user_uid)

    @rt("/api/lifepath/vision", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def api_capture_vision(request: Request) -> Result[LifePathRecommendation]:
        """Capture vision and get recommendations (JSON API)."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, CaptureVisionRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]

        if not lifepath_service:
            return Result.fail(
                Errors.system("LifePath service unavailable", operation="capture_vision")
            )

        return await lifepath_service.capture_and_recommend(user_uid, parsed.value.vision_statement)

    @rt("/api/lifepath/designate", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def api_designate(request: Request) -> Result[LifePathDesignation]:
        """Designate an LP as life path (JSON API)."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, DesignateLifePathRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]

        if not lifepath_service:
            return Result.fail(Errors.system("LifePath service unavailable", operation="designate"))

        return await lifepath_service.designate_and_calculate(user_uid, parsed.value.life_path_uid)

    @rt("/api/lifepath/alignment")
    @boundary_handler()
    async def api_get_alignment(request: Request) -> Result[LifePathAlignmentResult]:
        """Get alignment data (JSON API)."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return Result.fail(
                Errors.system("LifePath service unavailable", operation="get_alignment")
            )

        return await lifepath_service.get_alignment(user_uid)

    logger.info("LifePath API routes registered (4 routes)")

    return [api_get_status, api_capture_vision, api_designate, api_get_alignment]
