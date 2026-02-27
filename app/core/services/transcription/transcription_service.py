"""
Transcription Service - Simplified
===================================

Single, focused service for audio transcription.

Core Purpose: Audio file → Deepgram → Text

ARCHITECTURE DECISION (December 2025):
Replaces the over-engineered 997-line TranscriptionService + 846-line
AudioTranscriptionServiceV2 with a focused ~300-line service.

8 Core Methods:
1. create() - Create transcription record
2. get() - Get transcription by UID
3. process() - Send to Deepgram and update
4. retry() - Retry failed transcription
5. list() - List transcriptions with filters
6. search() - Search by transcript text
7. delete() - Delete transcription
8. update_status() - Update processing status

Everything else is inherited from BackendOperations or handled via events.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.transcription_events import (
    TranscriptionCompleted,
    TranscriptionCreated,
    TranscriptionFailed,
)
from core.models.transcription.transcription import (
    Transcription,
    TranscriptionCreateRequest,
    TranscriptionProcessOptions,
    TranscriptionStatus,
)
from core.services.metadata_manager_mixin import MetadataManagerMixin
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins

    from adapters.external.deepgram.adapter import DeepgramAdapter
    from core.ports.base_protocols import BackendOperations

logger = get_logger(__name__)


class TranscriptionService(MetadataManagerMixin):
    """
    Simplified transcription service.

    Single responsibility: manage audio transcription lifecycle.
    - Create transcription record
    - Process with Deepgram
    - Return results

    Event-driven: Publishes TranscriptionCompleted for downstream services
    (e.g., SubmissionsCoreService subscribes to create journal-type reports from transcripts).
    """

    def __init__(
        self,
        backend: BackendOperations[Transcription],
        deepgram_adapter: DeepgramAdapter | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize transcription service.

        Args:
            backend: Backend for persistence (required)
            deepgram_adapter: Adapter for Deepgram API (optional, required for processing)
            event_bus: Event bus for publishing events (optional)
        """
        if not backend:
            raise ValueError("Backend is required (fail-fast)")

        self.backend = backend
        self.deepgram = deepgram_adapter
        self.event_bus = event_bus
        self.logger = logger

    # ========================================================================
    # CORE CRUD (4 methods)
    # ========================================================================

    async def create(
        self,
        request: TranscriptionCreateRequest,
        user_uid: str,
    ) -> Result[Transcription]:
        """
        Create a new transcription record.

        Args:
            request: Creation request with audio file path
            user_uid: User who owns this transcription

        Returns:
            Result containing created Transcription
        """
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        # Create transcription model
        transcription = Transcription(
            uid=f"transcription:{uuid.uuid4()}",
            audio_file_path=request.audio_file_path,
            original_filename=request.original_filename,
            status=TranscriptionStatus.PENDING,
            user_uid=user_uid,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Persist
        result = await self.backend.create(transcription)
        if result.is_error:
            return result

        # Publish event
        event = TranscriptionCreated(
            transcription_uid=transcription.uid,
            user_uid=user_uid,
            audio_file_path=request.audio_file_path,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Created transcription {transcription.uid}")
        return Result.ok(transcription)

    async def get(self, uid: str) -> Result[Transcription | None]:
        """
        Get transcription by UID.

        Args:
            uid: Transcription UID

        Returns:
            Result containing Transcription or None if not found
        """
        return await self.backend.get(uid)

    async def delete(self, uid: str) -> Result[bool]:
        """
        Delete transcription.

        Args:
            uid: Transcription UID

        Returns:
            Result containing True if deleted
        """
        return await self.backend.delete(uid)

    async def list(
        self,
        user_uid: str | None = None,
        status: TranscriptionStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Result[builtins.list[Transcription]]:
        """
        List transcriptions with optional filters.

        Args:
            user_uid: Filter by user
            status: Filter by status
            limit: Max results
            offset: Skip results

        Returns:
            Result containing list of Transcriptions
        """
        filters = {}
        if user_uid:
            filters["user_uid"] = user_uid
        if status:
            filters["status"] = status.value

        result = await self.backend.list(limit=limit, offset=offset, **filters)
        if result.is_error:
            return Result.fail(result)
        items, _total = result.value
        return Result.ok(items)

    # ========================================================================
    # PROCESSING (2 methods)
    # ========================================================================

    async def process(
        self,
        uid: str,
        options: TranscriptionProcessOptions | None = None,
    ) -> Result[Transcription]:
        """
        Process transcription: send audio to Deepgram and update record.

        This is the main operation: audio file → Deepgram API → transcript.

        Args:
            uid: Transcription UID
            options: Processing options (language, model, etc.)

        Returns:
            Result containing updated Transcription with transcript
        """
        if not self.deepgram:
            return Result.fail(
                Errors.integration(
                    service="deepgram",
                    message="Deepgram adapter not configured",
                )
            )

        # Get transcription
        get_result = await self.get(uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found("Transcription", uid))

        transcription = get_result.value

        # Validate can process
        if not transcription.can_process() and not transcription.can_retry():
            return Result.fail(
                Errors.business(
                    rule="transcription_status",
                    message=f"Cannot process transcription with status: {transcription.status.value}",
                )
            )

        # Update status to PROCESSING
        transcription = replace(
            transcription,
            status=TranscriptionStatus.PROCESSING,
            updated_at=datetime.now(),
        )
        await self.backend.update(uid, {"status": "processing", **self.update_properties()})

        # Use provided options or defaults
        opts = options or TranscriptionProcessOptions()

        # Call Deepgram
        self.logger.info(f"Processing transcription {uid}")
        result = await self.deepgram.transcribe(
            audio_path=transcription.audio_file_path,
            language=opts.language,
            model=opts.model,
            punctuate=opts.punctuate,
            paragraphs=opts.paragraphs,
            diarize=opts.diarize,
        )

        if result.is_error:
            # Update status to FAILED
            error = result.expect_error()
            await self._mark_failed(uid, transcription.user_uid or "", error.message)
            return Result.fail(error)

        deepgram_result = result.value

        # Update with results
        updated = replace(
            transcription,
            status=TranscriptionStatus.COMPLETED,
            transcript_text=deepgram_result.transcript_text,
            confidence_score=deepgram_result.confidence_score,
            duration_seconds=deepgram_result.duration_seconds,
            word_count=deepgram_result.word_count,
            updated_at=datetime.now(),
        )

        update_result = await self.backend.update(
            uid,
            {
                "status": "completed",
                "transcript_text": deepgram_result.transcript_text,
                "confidence_score": deepgram_result.confidence_score,
                "duration_seconds": deepgram_result.duration_seconds,
                "word_count": deepgram_result.word_count,
                **self.update_properties(),
            },
        )

        if update_result.is_error:
            return update_result

        # Publish completion event
        if transcription.user_uid:
            event = TranscriptionCompleted(
                transcription_uid=uid,
                user_uid=transcription.user_uid,
                transcript_text=deepgram_result.transcript_text,
                audio_file_path=transcription.audio_file_path,
                confidence_score=deepgram_result.confidence_score,
                duration_seconds=deepgram_result.duration_seconds,
                word_count=deepgram_result.word_count,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Completed transcription {uid}: {deepgram_result.word_count} words")
        return Result.ok(updated)

    async def retry(self, uid: str) -> Result[Transcription]:
        """
        Retry a failed transcription.

        Args:
            uid: Transcription UID

        Returns:
            Result containing updated Transcription
        """
        # Get transcription
        get_result = await self.get(uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found("Transcription", uid))

        transcription = get_result.value

        if not transcription.can_retry():
            return Result.fail(
                Errors.business(
                    rule="transcription_status",
                    message="Only failed transcriptions can be retried",
                )
            )

        # Reset to pending and process
        await self.backend.update(
            uid,
            {"status": "pending", "error_message": None, **self.update_properties()},
        )

        return await self.process(uid)

    # ========================================================================
    # QUERY (2 methods)
    # ========================================================================

    async def search(
        self,
        query: str,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[Transcription]]:
        """
        Search transcriptions by transcript text.

        Args:
            query: Search text
            user_uid: Filter by user (optional)
            limit: Max results

        Returns:
            Result containing matching Transcriptions
        """
        # Get all and filter in memory (simple approach)
        # For production, use full-text search index
        list_result = await self.list(user_uid=user_uid, limit=limit * 2)
        if list_result.is_error:
            return list_result

        query_lower = query.lower()
        matches = [
            t for t in (list_result.value or []) if query_lower in (t.transcript_text or "").lower()
        ][:limit]

        return Result.ok(matches)

    async def get_by_status(
        self,
        status: TranscriptionStatus,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[Transcription]]:
        """
        Get transcriptions by status.

        Args:
            status: Status to filter by
            user_uid: Filter by user (optional)
            limit: Max results

        Returns:
            Result containing matching Transcriptions
        """
        return await self.list(user_uid=user_uid, status=status, limit=limit)

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    async def _mark_failed(
        self,
        uid: str,
        user_uid: str,
        error_message: str,
    ) -> None:
        """Mark transcription as failed and publish event."""
        await self.backend.update(
            uid,
            {
                "status": "failed",
                "error_message": error_message,
                **self.update_properties(),
            },
        )

        # Get audio path for event
        get_result = await self.get(uid)
        audio_path = get_result.value.audio_file_path if get_result.value else ""

        event = TranscriptionFailed(
            transcription_uid=uid,
            user_uid=user_uid,
            error_message=error_message,
            audio_file_path=audio_path,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)


__all__ = ["TranscriptionService"]
