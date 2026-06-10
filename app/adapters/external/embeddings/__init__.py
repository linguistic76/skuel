"""Embedding inference adapters (W1 — vendor SDKs behind a port).

``create_embedding_client()`` is the provider chokepoint (ADR-068):
OpenAI is the wired provider; the HuggingFace/BGE adapter is staged
for the long-term swap.
"""

from adapters.external.embeddings.factory import create_embedding_client
from adapters.external.embeddings.huggingface_adapter import HuggingFaceEmbeddingAdapter
from adapters.external.embeddings.openai_adapter import OpenAIEmbeddingAdapter

__all__ = [
    "HuggingFaceEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
    "create_embedding_client",
]
