"""
BatchChunkingService — regenerate ContentChunks for existing :Content nodes.

Used when the chunking algorithm changes (CHUNKING_ALGORITHM_VERSION bump) or
when chunks have drifted from their source body (corruption, partial writes).

Pulls body text from existing :Content nodes, re-runs EntityChunkingService,
and persists fresh chunks via Neo4jContentAdapter.store_content_with_chunks
(which is now idempotent — deletes old chunks before creating new ones).

Embedding regeneration is decoupled: after fresh chunks are persisted, this
service publishes ChunkEmbeddingRequested events so the existing async
EmbeddingBackgroundWorker picks them up. The migrate_chunk_embeddings.py
script can also be used as a one-shot batch alternative.

See: /docs/migrations/AUTOMATIC_CHUNKING_INTEGRATION_2026-01-29.md § Phase 2
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.ps_content.content_chunks import CHUNKING_ALGORITHM_VERSION
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import EventBusOperations
    from core.ports.chunk_protocols import BatchChunkingOperations

logger = get_logger("skuel.services.chunks.batch")


@dataclass
class RegenerationStats:
    """Outcome of a BatchChunkingService.regenerate_chunks call."""

    total_candidates: int = 0  # Parents matched by the query before filtering
    processed: int = 0  # Parents we actually attempted to regenerate
    succeeded: int = 0
    failed: int = 0
    skipped_already_current: int = 0  # version match, force=False
    skipped_no_body: int = 0  # :Content node exists but body is empty
    duration_seconds: float = 0.0
    errors: dict[str, str] = field(default_factory=dict)  # parent_uid -> error message

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "processed": self.processed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped_already_current": self.skipped_already_current,
            "skipped_no_body": self.skipped_no_body,
            "duration_seconds": round(self.duration_seconds, 2),
            "errors": self.errors,
        }


class BatchChunkingService:
    """Regenerate :ContentChunk nodes for existing :Content."""

    def __init__(
        self,
        backend: BatchChunkingOperations,
        chunking_service: Any,  # EntityChunkingService — boundary, no protocol extracted
        content_adapter: Any,  # Neo4jContentAdapter — boundary
        event_bus: EventBusOperations | None = None,
        max_concurrency: int = 10,
    ) -> None:
        """
        Args:
            backend: BatchChunkingOperations port for :Content candidate queries.
                Built at the composition root and injected so this service never
                imports the adapter (ADR-044 / SKUEL022 / SKUEL023).
            chunking_service: Produces fresh chunks from raw body text.
            content_adapter: Persists chunks via store_content_with_chunks (idempotent).
            event_bus: If provided, publishes ChunkEmbeddingRequested for each
                regenerated parent so the async worker re-embeds. Pass None to
                skip embedding regeneration (use migrate_chunk_embeddings.py
                separately).
            max_concurrency: Parents processed in parallel. Higher = faster but
                more Neo4j load.
        """
        self._backend = backend
        self.chunking_service = chunking_service
        self.content_adapter = content_adapter
        self.event_bus = event_bus
        self.max_concurrency = max_concurrency

    async def regenerate_chunks(
        self,
        parent_uids: list[str] | None = None,
        force: bool = False,
    ) -> Result[RegenerationStats]:
        """
        Regenerate chunks for the given parent UIDs (or all parents if None).

        Args:
            parent_uids: Restrict to these parents. None = every :Content node.
            force: If False, skip parents whose chunks already match the current
                CHUNKING_ALGORITHM_VERSION. If True, regenerate regardless.

        Returns:
            Result wrapping RegenerationStats. Per-parent errors do not fail the
            batch — they're recorded in stats.errors. Only catastrophic failures
            (e.g., the candidate query itself errors) produce Result.fail.
        """
        stats = RegenerationStats()
        start = time.time()

        try:
            candidates = await self._fetch_candidates(parent_uids, force)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to fetch regeneration candidates: {e}")
            return Result.fail(
                Errors.database(
                    operation="fetch_regeneration_candidates",
                    message=str(e),
                )
            )

        stats.total_candidates = len(candidates)
        logger.info(
            f"Regeneration candidates: {stats.total_candidates} "
            f"(parent_uids={'all' if parent_uids is None else len(parent_uids)}, force={force})"
        )

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _process(candidate: dict[str, Any]) -> None:
            async with semaphore:
                await self._regenerate_one(candidate, stats)

        await asyncio.gather(*(_process(c) for c in candidates))

        stats.duration_seconds = time.time() - start
        logger.info(
            f"Regeneration complete: {stats.succeeded}/{stats.processed} succeeded, "
            f"{stats.failed} failed, {stats.skipped_no_body} skipped "
            f"(no body), in {stats.duration_seconds:.2f}s"
        )
        return Result.ok(stats)

    async def _fetch_candidates(
        self, parent_uids: list[str] | None, force: bool
    ) -> list[dict[str, Any]]:
        """
        Pull :Content rows that need regeneration.

        When force=False, a candidate is one whose chunks include at least one
        with chunking_version ≠ current (or no chunks at all — the "ingested
        pre-versioning" case).
        """
        # Candidate-discovery Cypher lives in BatchChunkingBackend below the
        # boundary (ADR-044).
        return await self._backend.fetch_regeneration_candidates(
            parent_uids, force, CHUNKING_ALGORITHM_VERSION
        )

    async def _regenerate_one(self, candidate: dict[str, Any], stats: RegenerationStats) -> None:
        """Regenerate chunks for a single parent. Failures are recorded, not raised."""
        parent_uid = candidate["uid"]
        body = candidate.get("body") or ""
        fmt = candidate.get("format") or "markdown"

        if not body.strip():
            stats.skipped_no_body += 1
            return

        stats.processed += 1

        chunk_result = await self.chunking_service.process_content_for_ingestion(
            parent_uid=parent_uid,
            content_body=body,
            format=fmt,
        )

        if chunk_result.is_error:
            err = str(chunk_result.expect_error().message)
            stats.failed += 1
            stats.errors[parent_uid] = f"chunking failed: {err}"
            logger.warning(f"Regeneration failed for {parent_uid}: {err}")
            return

        content, _metadata = chunk_result.value
        stored = await self.content_adapter.store_content_with_chunks(parent_uid, content)
        if not stored:
            stats.failed += 1
            stats.errors[parent_uid] = "store_content_with_chunks returned False"
            logger.warning(f"Regeneration store failed for {parent_uid}")
            return

        stats.succeeded += 1

        if self.event_bus and content.chunks:
            await self._publish_embedding_request(parent_uid, content.chunks)

    async def _publish_embedding_request(self, parent_uid: str, chunks: list[Any]) -> None:
        """Re-emit ChunkEmbeddingRequested so the async worker re-embeds."""
        from core.events import ChunkEmbeddingRequested, publish_event

        await publish_event(
            self.event_bus,
            ChunkEmbeddingRequested(
                parent_uid=parent_uid,
                chunk_uids=tuple(c.chunk_id for c in chunks),
                chunk_texts=tuple(c.context_window for c in chunks),
                requested_at=datetime.now(),
                user_uid=None,  # Admin-initiated batch — no user attribution
            ),
            logger,
        )
