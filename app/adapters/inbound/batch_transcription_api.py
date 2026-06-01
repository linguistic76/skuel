"""
Batch Transcription API Routes
================================

Admin-only endpoint for batch audio transcription (Tier 1).

Tier 2 (batch LLM txt→md) retired with ADR-054 Commit 6a — that path now
lives inside ``UserEntryProcessingService`` per the unified hub.

Endpoints:
- POST /api/journals/batch-transcribe — audio → txt (preview or run)

See: core/services/transcription/batch_transcription_service.py
"""

from pathlib import Path
from typing import Any

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.batch_transcription.api")

# Default directories
DEFAULT_INPUT_DIR = "data/je_inputs"
DEFAULT_OUTPUT_DIR = "data/je_outputs"


def create_batch_transcription_api_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    batch_transcription_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create batch transcription API routes (admin-only).

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        batch_transcription_service: BatchTranscriptionService
        user_service: UserService for admin role checks
    """
    get_user_service = make_service_getter(user_service)

    @rt("/api/journals/batch-transcribe")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler(success_status=200)
    async def batch_transcribe(
        request: Request, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """
        Batch transcribe audio files to text.

        POST body (JSON):
            input_dir: str — path to audio files (default: data/je_inputs)
            output_dir: str — path for .txt output (default: data/je_outputs)
            skip_existing: bool — skip already-transcribed files (default: true)
            preview_only: bool — if true, return file list without transcribing (default: false)

        Returns:
            Preview: {files, total_files, total_size_mb, already_transcribed}
            Transcribe: {total_files, succeeded, failed, skipped, results, errors}
        """
        body = await request.json()
        input_dir = Path(body.get("input_dir", DEFAULT_INPUT_DIR))
        output_dir = Path(body.get("output_dir", DEFAULT_OUTPUT_DIR))
        skip_existing = body.get("skip_existing", True)
        preview_only = body.get("preview_only", False)

        if preview_only:
            logger.info(f"Admin {current_user.uid} previewing batch transcription: {input_dir}")
            preview_result = await batch_transcription_service.preview(input_dir, output_dir)
            if preview_result.is_error:
                return Result.fail(preview_result)

            preview = preview_result.value
            return Result.ok(
                {
                    "preview": True,
                    "files": [{"name": f.name, "size_mb": f.size_mb} for f in preview.files],
                    "total_files": preview.total_files,
                    "total_size_mb": preview.total_size_mb,
                    "already_transcribed": preview.already_transcribed,
                }
            )

        logger.info(
            f"Admin {current_user.uid} starting batch transcription: "
            f"{input_dir} → {output_dir} (skip_existing={skip_existing})"
        )

        result = await batch_transcription_service.transcribe_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            skip_existing=skip_existing,
        )

        if result.is_error:
            return Result.fail(result)

        batch = result.value
        return Result.ok(
            {
                "preview": False,
                "total_files": batch.total_files,
                "succeeded": batch.succeeded,
                "failed": batch.failed,
                "skipped": batch.skipped,
                "results": batch.results,
                "errors": batch.errors,
            }
        )

    logger.info("Batch transcription API routes created")
    return [batch_transcribe]


__all__ = ["create_batch_transcription_api_routes"]
