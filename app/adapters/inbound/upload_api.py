"""
Upload API Routes - Per-User Bulk File Upload
==============================================

User-facing API for uploading Activity Domain YAML files.
Unlike the admin ingestion API, this endpoint is available
to any authenticated user and restricts uploads to Activity
Domain types only (Task, Goal, Habit, Event, Choice, Principle).

Routes:
- POST /api/upload - Upload and ingest YAML files
"""

from typing import TYPE_CHECKING, Any

from starlette.datastructures import UploadFile
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.services.ingestion.user_upload_service import MAX_FILES_PER_REQUEST
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList

logger = get_logger("skuel.routes.upload")


def create_upload_api_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    upload_service: Any,
    user_service: Any = None,
) -> "RouteList":
    """Create user-facing upload API routes."""

    @rt("/api/upload", methods=["POST"])
    @boundary_handler(success_status=200)
    async def upload_files(request: Request) -> Any:
        """Upload and ingest YAML files for the authenticated user.

        Accepts multipart form with 'files' field (multiple UploadFile).
        Returns per-file results with success/failure status.
        """
        user_uid = require_authenticated_user(request)

        if not upload_service:
            return Errors.system("Upload service unavailable")

        form = await request.form()
        raw_files = form.getlist("files")

        if not raw_files:
            return Errors.validation("No files provided. Use the 'files' form field.")

        if len(raw_files) > MAX_FILES_PER_REQUEST:
            return Errors.validation(
                f"Too many files: {len(raw_files)} (max {MAX_FILES_PER_REQUEST})"
            )

        # Read each UploadFile into (filename, bytes) pairs
        file_pairs: list[tuple[str, bytes]] = []
        for raw_file in raw_files:
            if not isinstance(raw_file, UploadFile):
                continue
            content = await raw_file.read()
            filename = raw_file.filename or "unknown.yaml"
            file_pairs.append((filename, content))

        if not file_pairs:
            return Errors.validation("No valid files found in upload")

        result = await upload_service.upload_and_ingest(user_uid, file_pairs)

        if result.is_error:
            return result

        batch = result.value
        return {
            "total": batch.total,
            "successful": batch.successful,
            "failed": batch.failed,
            "results": [
                {
                    "filename": r.filename,
                    "success": r.success,
                    "entity_type": r.entity_type,
                    "uid": r.uid,
                    "error": r.error,
                }
                for r in batch.results
            ],
        }

    return []
