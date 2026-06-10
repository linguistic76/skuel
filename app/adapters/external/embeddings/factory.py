"""
Embedding Client Factory — THE Provider Choice Chokepoint
=========================================================

``create_embedding_client()`` is the single place that decides which
embedding provider SKUEL uses (ADR-068: OpenAI now, BGE long-term). The
bootstrap composition root and every standalone script construct their
inference client here — swapping providers later (e.g. to
``HuggingFaceEmbeddingAdapter``) is a one-line change in this file.

Credential reads happen here (the composition-root layer for embedding
clients), never in core services (W1 / ADR-044).
"""

from __future__ import annotations

from adapters.external.embeddings.openai_adapter import OpenAIEmbeddingAdapter
from core.config.credential_store import get_credential


def create_embedding_client() -> OpenAIEmbeddingAdapter:
    """Construct the wired embedding inference client (``EmbeddingClientOperations``).

    Raises:
        ValueError: If the provider API key is missing (fail-fast; callers in
            FULL-tier bootstrap wrap this with INTELLIGENCE_TIER guidance).
    """
    api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True) or ""
    return OpenAIEmbeddingAdapter(api_key=api_key)


__all__ = ["create_embedding_client"]
