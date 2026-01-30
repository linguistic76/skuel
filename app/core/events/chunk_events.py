"""
Chunk Embedding Events
=======================

Events for async chunk-level embedding generation.

Published when KU chunks are created, consumed by background worker
for batch embedding generation.

Architecture:
- Zero latency impact on KU creation
- Batch processing for efficiency (25 chunks per API call)
- Graceful degradation if worker unavailable
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import DomainEvent


@dataclass(frozen=True)
class ChunkEmbeddingRequested(DomainEvent):
    """
    Published when KU chunks need embeddings.

    Triggered after KU creation with chunks.
    Worker processes in batches for efficiency.
    """

    ku_uid: str
    chunk_uids: tuple[str, ...]  # ["ku.python:chunk:0", ...]
    chunk_texts: tuple[str, ...]  # Context window for each chunk
    requested_at: datetime
    user_uid: str | None = None

    @property
    def event_type(self) -> str:
        return "chunk.embedding_requested"


@dataclass(frozen=True)
class ChunkEmbeddingsCompleted(DomainEvent):
    """
    Published when chunk embeddings have been generated and stored.

    Used for monitoring and debugging embedding generation pipeline.
    """

    ku_uid: str
    chunk_uids: tuple[str, ...]
    success_count: int
    failed_count: int
    completed_at: datetime

    @property
    def event_type(self) -> str:
        return "chunk.embeddings_completed"
