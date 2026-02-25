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

from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
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
    async def api_get_status(request: Request) -> Result[Any]:
        """Get full life path status."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return Result.fail(
                Errors.system("LifePath service unavailable", operation="get_status")
            )

        return await lifepath_service.get_full_status(user_uid)

    @rt("/api/lifepath/vision", methods=["POST"])
    @boundary_handler()
    async def api_capture_vision(request: Request) -> Result[Any]:
        """Capture vision and get recommendations (JSON API)."""
        user_uid = require_authenticated_user(request)

        body = await request.json()
        vision_statement = body.get("vision_statement", "").strip()

        if not vision_statement or len(vision_statement) < 10:
            return Result.fail(
                Errors.validation(
                    "Vision statement must be at least 10 characters",
                    field="vision_statement",
                    value=vision_statement,
                )
            )

        if not lifepath_service:
            return Result.fail(
                Errors.system("LifePath service unavailable", operation="capture_vision")
            )

        return await lifepath_service.capture_and_recommend(user_uid, vision_statement)

    @rt("/api/lifepath/designate", methods=["POST"])
    @boundary_handler()
    async def api_designate(request: Request) -> Result[Any]:
        """Designate an LP as life path (JSON API)."""
        user_uid = require_authenticated_user(request)

        body = await request.json()
        life_path_uid = body.get("life_path_uid", "").strip()

        if not life_path_uid:
            return Result.fail(
                Errors.validation("life_path_uid is required", field="life_path_uid", value="")
            )

        if not lifepath_service:
            return Result.fail(Errors.system("LifePath service unavailable", operation="designate"))

        return await lifepath_service.designate_and_calculate(user_uid, life_path_uid)

    @rt("/api/lifepath/alignment")
    @boundary_handler()
    async def api_get_alignment(request: Request) -> Result[Any]:
        """Get alignment data (JSON API)."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return Result.fail(
                Errors.system("LifePath service unavailable", operation="get_alignment")
            )

        return await lifepath_service.alignment.calculate_alignment(user_uid)

    logger.info("LifePath API routes registered (4 routes)")

    return [api_get_status, api_capture_vision, api_designate, api_get_alignment]
