"""
Backward compatibility shim — imports from embeddings_service.py.

All code has moved to core.services.embeddings_service.
This file re-exports names so existing imports continue to work.

See: /docs/decisions/ADR-048-huggingface-embeddings-migration.md
"""

from core.services.embeddings_service import (
    EMBEDDING_VERSION,
    HuggingFaceEmbeddingsService,
)
from core.services.embeddings_service import (
    HuggingFaceEmbeddingsService as Neo4jGenAIEmbeddingsService,
)

__all__ = [
    "EMBEDDING_VERSION",
    "HuggingFaceEmbeddingsService",
    "Neo4jGenAIEmbeddingsService",
]
