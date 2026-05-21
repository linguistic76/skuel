"""
Chunk Embedding Events
=======================

Events for async chunk-level embedding generation.

Published when a parent entity's content is chunked (currently PathStep, in
principle any chunkable Entity), consumed by the background worker for batch
embedding generation.

Architecture:
- Zero latency impact on ingestion
- Batch processing for efficiency (25 chunks per API call)
- Graceful degradation if worker unavailable
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


@dataclass(frozen=True)
class ChunkEmbeddingRequested(BaseEvent):
    """
    Published when a parent entity's chunks need embeddings.

    Triggered after chunking during ingestion or batch regeneration.
    Worker processes in batches for efficiency.
    """

    parent_uid: str  # The parent Entity uid (e.g., PathStep) whose chunks need embedding
    chunk_uids: tuple[str, ...]  # ["ps:foo:chunk:0", ...]
    chunk_texts: tuple[str, ...]  # Context window for each chunk
    requested_at: datetime
    user_uid: UserUID | None = None

    @property
    def event_type(self) -> str:
        return "chunk.embedding_requested"


@dataclass(frozen=True)
class ChunkEmbeddingsCompleted(BaseEvent):
    """
    Published when chunk embeddings have been generated and stored.

    Used for monitoring and debugging embedding generation pipeline.
    """

    parent_uid: str  # Matches ChunkEmbeddingRequested.parent_uid
    chunk_uids: tuple[str, ...]
    success_count: int
    failed_count: int
    completed_at: datetime

    @property
    def event_type(self) -> str:
        return "chunk.embeddings_completed"
