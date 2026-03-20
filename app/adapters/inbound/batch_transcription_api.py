"""
Batch Transcription API Routes
================================

Admin-only endpoints for batch audio transcription (Tier 1) and
batch LLM processing (Tier 2).

Two endpoints:
- POST /api/journals/batch-transcribe — audio → txt (preview or run)
- POST /api/journals/batch-process — txt → md via LLM

See: core/services/transcription/batch_transcription_service.py
See: core/services/transcription/batch_processing_service.py
"""

from pathlib import Path
from typing import Any

from starlette.requests import Request

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.batch_transcription.api")

# Default directories
DEFAULT_INPUT_DIR = "data/je_inputs"
DEFAULT_OUTPUT_DIR = "data/je_outputs"


def create_batch_transcription_api_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    batch_transcription_service: Any,
    batch_processing_service: Any | None = None,
    user_service: Any = None,
) -> RouteList:
    """
    Create batch transcription API routes (admin-only).

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        batch_transcription_service: BatchTranscriptionService
        batch_processing_service: BatchProcessingService (optional — Tier 2)
        user_service: UserService for admin role checks
    """
    get_user_service = make_service_getter(user_service)

    @rt("/api/journals/batch-transcribe")
    @require_admin(get_user_service)
    @boundary_handler(success_status=200)
    async def batch_transcribe(request: Request, current_user: Any = None) -> Result[dict[str, Any]]:
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
                return Result.fail(preview_result.expect_error())

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
            return Result.fail(result.expect_error())

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

    @rt("/api/journals/batch-process")
    @require_admin(get_user_service)
    @boundary_handler(success_status=200)
    async def batch_process(request: Request, current_user: Any = None) -> Result[dict[str, Any]]:
        """
        Batch process .txt transcripts through LLM to .md.

        POST body (JSON):
            input_dir: str — path to .txt files (default: data/je_outputs)
            output_dir: str — path for .md output (default: same as input_dir)
            enrichment_mode: str — "activity_tracking" | "idea_articulation" | "critical_thinking"
            custom_instructions: str — user-provided instruction text (overrides mode)
            model: str — LLM model (default: "gpt-4o-mini")
            temperature: float — sampling temperature (default: 0.7)
            max_tokens: int — max tokens per generation (default: 4000)
            skip_existing: bool — skip already-processed files (default: true)
            combined: bool — run Tier 1 + Tier 2 (audio_dir required, default: false)
            audio_dir: str — audio input dir for combined mode (default: data/je_inputs)

        Returns:
            Processing: {total_files, succeeded, failed, skipped, results, errors}
            Combined: {transcription: {...}, processing: {...}}
        """
        if not batch_processing_service:
            return Result.fail(
                Errors.system(
                    message="Batch processing service not available (requires AI)",
                    operation="batch_process",
                )
            )

        body = await request.json()
        input_dir = Path(body.get("input_dir", DEFAULT_OUTPUT_DIR))
        output_dir_str = body.get("output_dir")
        output_dir = Path(output_dir_str) if output_dir_str else None
        enrichment_mode = body.get("enrichment_mode")
        custom_instructions = body.get("custom_instructions")
        model = body.get("model", "gpt-4o-mini")
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4000)
        skip_existing = body.get("skip_existing", True)
        combined = body.get("combined", False)

        if combined:
            audio_dir = Path(body.get("audio_dir", DEFAULT_INPUT_DIR))
            combined_output = Path(body.get("output_dir", DEFAULT_OUTPUT_DIR))

            logger.info(
                f"Admin {current_user.uid} starting combined pipeline: "
                f"{audio_dir} → {combined_output}"
            )

            result = await batch_processing_service.transcribe_and_process(
                audio_dir=audio_dir,
                output_dir=combined_output,
                batch_transcription=batch_transcription_service,
                enrichment_mode=enrichment_mode,
                custom_instructions=custom_instructions,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                skip_existing=skip_existing,
            )

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(result.value)

        logger.info(
            f"Admin {current_user.uid} starting batch processing: "
            f"{input_dir} (mode={enrichment_mode or 'default'}, model={model})"
        )

        result = await batch_processing_service.process_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            enrichment_mode=enrichment_mode,
            custom_instructions=custom_instructions,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            skip_existing=skip_existing,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        batch = result.value
        return Result.ok(
            {
                "total_files": batch.total_files,
                "succeeded": batch.succeeded,
                "failed": batch.failed,
                "skipped": batch.skipped,
                "results": batch.results,
                "errors": batch.errors,
            }
        )

    logger.info("Batch transcription API routes created")
    return [batch_transcribe, batch_process]


__all__ = ["create_batch_transcription_api_routes"]
