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
from starlette.responses import JSONResponse

from core.auth import require_authenticated_user
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.protocols import LifePathOperations

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
    async def api_get_status(request: Request) -> JSONResponse:
        """Get full life path status."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return JSONResponse({"error": "LifePath service unavailable"}, status_code=503)

        result = await lifepath_service.get_full_status(user_uid)

        if result.is_error:
            return JSONResponse({"error": str(result.expect_error())}, status_code=400)

        return JSONResponse(result.value)

    @rt("/api/lifepath/vision", methods=["POST"])
    async def api_capture_vision(request: Request) -> JSONResponse:
        """Capture vision and get recommendations (JSON API)."""
        user_uid = require_authenticated_user(request)

        body = await request.json()
        vision_statement = body.get("vision_statement", "").strip()

        if not vision_statement or len(vision_statement) < 10:
            return JSONResponse(
                {"error": "Vision statement must be at least 10 characters"},
                status_code=400,
            )

        if not lifepath_service:
            return JSONResponse({"error": "LifePath service unavailable"}, status_code=503)

        result = await lifepath_service.capture_and_recommend(user_uid, vision_statement)

        if result.is_error:
            return JSONResponse({"error": str(result.expect_error())}, status_code=400)

        return JSONResponse(result.value)

    @rt("/api/lifepath/designate", methods=["POST"])
    async def api_designate(request: Request) -> JSONResponse:
        """Designate an LP as life path (JSON API)."""
        user_uid = require_authenticated_user(request)

        body = await request.json()
        life_path_uid = body.get("life_path_uid", "").strip()

        if not life_path_uid:
            return JSONResponse({"error": "life_path_uid is required"}, status_code=400)

        if not lifepath_service:
            return JSONResponse({"error": "LifePath service unavailable"}, status_code=503)

        result = await lifepath_service.designate_and_calculate(user_uid, life_path_uid)

        if result.is_error:
            return JSONResponse({"error": str(result.expect_error())}, status_code=400)

        return JSONResponse(result.value)

    @rt("/api/lifepath/alignment")
    async def api_get_alignment(request: Request) -> JSONResponse:
        """Get alignment data (JSON API)."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return JSONResponse({"error": "LifePath service unavailable"}, status_code=503)

        result = await lifepath_service.alignment.calculate_alignment(user_uid)

        if result.is_error:
            return JSONResponse({"error": str(result.expect_error())}, status_code=400)

        return JSONResponse(result.value)

    logger.info("LifePath API routes registered (4 routes)")

    return [api_get_status, api_capture_vision, api_designate, api_get_alignment]
