"""
Batch Transcription API Routes
================================

Endpoints for batch audio transcription (Tier 1).

Tier 2 (batch LLM txt→md) retired with ADR-054 — that path now lives
inside ``UserEntryProcessingService`` per the unified hub.

Endpoints:
- POST /api/journals/batch-transcribe     — admin console (any server path)
- POST /api/journals/folder-transcribe    — user journals UI (defaults to vault paths)

See: core/services/transcription/batch_transcription_service.py
"""

from pathlib import Path
from typing import Any

from adapters.inbound.auth import make_service_getter, require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.result_helpers import require_found
from core.config.intelligence_tier import IntelligenceTier
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.services.journal import JournalBatchService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.batch_transcription.api")

# Admin console defaults
DEFAULT_INPUT_DIR = "data/je_inputs"
DEFAULT_OUTPUT_DIR = "data/je_outputs"


def create_batch_transcription_api_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    batch_transcription_service: Any,
    journal_batch: JournalBatchService,
    user_service: Any = None,
    intelligence_tier: IntelligenceTier | None = None,
) -> list[Any]:
    """
    Create batch transcription API routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        batch_transcription_service: BatchTranscriptionService
        journal_batch: canonical home of the je_in/je_out staging-folder layout —
            folder-transcribe reads/writes ``journal_batch.je_in_dir/je_out_dir``
            so this surface writes where download/folder-process reads
        user_service: UserService for admin role checks + the per-user tier gate
        intelligence_tier: System intelligence tier for the per-user gate (ADR-043)
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
        Admin: batch transcribe audio files to text (any server-side path).

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
            preview_result = batch_transcription_service.preview(input_dir, output_dir)
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

    @rt("/api/journals/folder-transcribe")
    @csrf_protected
    @boundary_handler(success_status=200)
    async def folder_transcribe(request: Request) -> Result[dict[str, Any]]:
        """
        User: batch transcribe audio files to text from the vault transcription dirs.

        Paths are fixed server-side (``JournalBatchService.je_in_dir/je_out_dir`` —
        the canonical je_* staging-folder layout). Client-supplied paths are ignored —
        accepting them would let any authenticated user read from and write to
        arbitrary server directories.

        POST body (JSON):
            skip_existing: bool — skip already-transcribed files (default: true)
            preview_only: bool — if true, return file list without transcribing (default: false)

        Returns:
            Preview: {files, total_files, total_size_mb, already_transcribed}
            Transcribe: {total_files, succeeded, failed, skipped, results, errors}
        """
        user_uid = require_authenticated_user(request)

        # Per-user tier gate (ADR-043): every transcription spends Deepgram
        # money, so effective-CORE (REGISTERED) users are denied. Fail-secure —
        # missing dependencies mean the gate cannot be evaluated, so deny
        # rather than allow (mirrors askesis_api.py).
        if intelligence_tier is None or user_service is None:
            return Result.fail(
                Errors.forbidden(
                    action="batch transcription",
                    reason="AI features require a paid subscription",
                    required_role="MEMBER",
                )
            )
        user = require_found(await user_service.get_user(user_uid), "User", user_uid)
        if user.is_error:
            return Result.fail(Errors.database("get_user", "Could not verify user access tier"))
        effective_tier = get_user_intelligence_tier(intelligence_tier, user.value.role)
        if not effective_tier.ai_enabled:
            return Result.fail(
                Errors.forbidden(
                    action="batch transcription",
                    reason="AI features require a paid subscription",
                    required_role="MEMBER",
                )
            )

        body = await request.json()
        # Paths are fixed server-side — never sourced from the request body.
        # Accepting client-supplied paths would let any authenticated user
        # read from and write to arbitrary server directories (Codex P1).
        input_dir = journal_batch.je_in_dir
        output_dir = journal_batch.je_out_dir
        skip_existing = body.get("skip_existing", True)
        preview_only = body.get("preview_only", False)

        if preview_only:
            logger.info(f"User {user_uid} previewing folder transcription: {input_dir}")
            preview_result = batch_transcription_service.preview(input_dir, output_dir)
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
            f"User {user_uid} starting folder transcription: "
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
    return [batch_transcribe, folder_transcribe]


__all__ = ["create_batch_transcription_api_routes"]
