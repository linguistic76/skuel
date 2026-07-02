"""
Chunk Embedding Events
=======================

Events for async chunk-level embedding generation.

Published when a parent entity's content is chunked (currently PathStep, in
principle any chunkable Entity), consumed by the background worker for batch
embedding generation.

Architecture:
- Zero latency impact on ingestion
- Batch processing for efficiency (chunks embed concurrently; the inference
  clients are single-text, so batching is concurrency, not a batch endpoint)
- Graceful degradation if worker unavailable
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent


@dataclass(frozen=True)
class ChunkEmbeddingRequested(BaseEvent):
    """
    Published when a parent entity's chunks need embeddings.

    Triggered after chunking during ingestion or batch regeneration.
    Worker processes in batches for efficiency. Carries no ownership
    attribution: chunks hang off parents whose nodes already carry ownership.
    """

    parent_uid: str  # The parent Entity uid (e.g., PathStep) whose chunks need embedding
    chunk_uids: tuple[str, ...]  # ["ps:foo:chunk:0", ...]
    chunk_texts: tuple[str, ...]  # Context window for each chunk
    requested_at: datetime

    @property
    def event_type(self) -> str:
        return "chunk.embedding_requested"
