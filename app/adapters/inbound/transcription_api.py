"""
Transcription API Routes
========================

Clean API routes for the simplified TranscriptionService.

Route Structure (8 endpoints matching 8 service methods):
- POST   /api/transcriptions          → create()
- GET    /api/transcriptions/{uid}    → get()
- DELETE /api/transcriptions/{uid}    → delete()
- GET    /api/transcriptions          → list()
- POST   /api/transcriptions/{uid}/process  → process()
- POST   /api/transcriptions/{uid}/retry    → retry()
- GET    /api/transcriptions/search   → search()
- GET    /api/transcriptions/status/{status} → get_by_status()

Each route maps to exactly one service method.
"""

from typing import Any

from core.auth import require_authenticated_user
from core.models.transcription.transcription import (
    TranscriptionCreateRequest,
    TranscriptionProcessOptions,
    TranscriptionStatus,
)
from core.services.transcription import TranscriptionService
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.transcription_api")


def create_transcription_api_routes(
    app: Any,
    rt: Any,
    transcription_service: TranscriptionService,
) -> list[Any]:
    """
    Create transcription API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        transcription_service: TranscriptionService instance

    Returns:
        List of created routes
    """
    routes: list[Any] = []

    # ========================================================================
    # CRUD ROUTES
    # ========================================================================

    @rt("/api/transcriptions", methods=["POST"])
    @boundary_handler()
    async def create_transcription(request) -> Result[Any]:
        """Create a new transcription."""
        user_uid = require_authenticated_user(request)
        body = await request.json()

        create_request = TranscriptionCreateRequest(**body)
        result = await transcription_service.create(create_request, user_uid)

        if result.is_ok:
            return Result.ok(result.value.to_dict())
        return result

    @rt("/api/transcriptions/get")
    @boundary_handler()
    async def get_transcription(_request, uid: str) -> Result[Any]:
        """Get transcription by UID."""
        result = await transcription_service.get(uid)

        if result.is_error:
            return result
        if not result.value:
            return Result.fail(Errors.not_found("Transcription", uid))

        return Result.ok(result.value.to_dict())

    @rt("/api/transcriptions/delete", methods=["DELETE"])
    @boundary_handler()
    async def delete_transcription(_request, uid: str) -> Result[Any]:
        """Delete transcription."""
        return await transcription_service.delete(uid)

    @rt("/api/transcriptions")
    @boundary_handler()
    async def list_transcriptions(request) -> Result[Any]:
        """List transcriptions with optional filters."""
        params = dict(request.query_params)

        user_uid = params.get("user_uid")
        status_str = params.get("status")
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        status = TranscriptionStatus(status_str) if status_str else None

        result = await transcription_service.list(
            user_uid=user_uid,
            status=status,
            limit=limit,
            offset=offset,
        )

        if result.is_error:
            return result

        return Result.ok([t.to_dict() for t in (result.value or [])])

    # ========================================================================
    # PROCESSING ROUTES
    # ========================================================================

    @rt("/api/transcriptions/process", methods=["POST"])
    @boundary_handler()
    async def process_transcription(request, uid: str) -> Result[Any]:
        """Process transcription with Deepgram."""
        body = await request.json() if request.headers.get("content-length") else {}

        options = TranscriptionProcessOptions(**body) if body else None
        result = await transcription_service.process(uid, options)

        if result.is_ok:
            return Result.ok(result.value.to_dict())
        return result

    @rt("/api/transcriptions/retry", methods=["POST"])
    @boundary_handler()
    async def retry_transcription(_request, uid: str) -> Result[Any]:
        """Retry a failed transcription."""
        result = await transcription_service.retry(uid)

        if result.is_ok:
            return Result.ok(result.value.to_dict())
        return result

    # ========================================================================
    # QUERY ROUTES
    # ========================================================================

    @rt("/api/transcriptions/search")
    @boundary_handler()
    async def search_transcriptions(request) -> Result[Any]:
        """Search transcriptions by transcript text."""
        params = dict(request.query_params)
        query = params.get("q")

        if not query:
            return Result.fail(Errors.validation("Query parameter 'q' is required", field="q"))

        user_uid = params.get("user_uid")
        limit = int(params.get("limit", 100))

        result = await transcription_service.search(query, user_uid=user_uid, limit=limit)

        if result.is_error:
            return result

        return Result.ok([t.to_dict() for t in (result.value or [])])

    @rt("/api/transcriptions/status")
    @boundary_handler()
    async def get_by_status(request, status: str) -> Result[Any]:
        """Get transcriptions by status."""
        params = dict(request.query_params)

        try:
            status_enum = TranscriptionStatus(status)
        except ValueError:
            return Result.fail(Errors.validation(f"Invalid status: {status}", field="status"))

        user_uid = params.get("user_uid")
        limit = int(params.get("limit", 100))

        result = await transcription_service.get_by_status(status_enum, user_uid=user_uid, limit=limit)

        if result.is_error:
            return result

        return Result.ok([t.to_dict() for t in (result.value or [])])

    # ========================================================================
    # HEALTH CHECK
    # ========================================================================

    @rt("/api/transcriptions/health")
    async def transcription_health(_request) -> dict[str, Any]:
        """Health check endpoint."""
        from datetime import datetime

        return {
            "status": "healthy",
            "service": "transcription",
            "version": "3.0",
            "timestamp": datetime.now().isoformat(),
        }

    # Collect all routes
    routes.extend(
        [
            create_transcription,
            get_transcription,
            delete_transcription,
            list_transcriptions,
            process_transcription,
            retry_transcription,
            search_transcriptions,
            get_by_status,
            transcription_health,
        ]
    )

    logger.info(f"Transcription API routes registered: {len(routes)} endpoints")

    return routes


__all__ = ["create_transcription_api_routes"]
