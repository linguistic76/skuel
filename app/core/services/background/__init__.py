"""
Background Services
===================

Long-running background workers for async processing.

Workers:
- EmbeddingBackgroundWorker: Async embedding generation for activity domains
"""

from core.services.background.embedding_worker import EmbeddingBackgroundWorker

__all__ = ["EmbeddingBackgroundWorker"]
