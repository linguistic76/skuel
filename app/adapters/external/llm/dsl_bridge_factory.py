"""
LLM DSL Bridge factory (composition helper, below the hexagonal boundary).

``LLMDSLBridgeService`` lives in ``core/`` and depends only on the
``ChatCompletionPort``. This factory — which reads the credential and builds
the concrete ``OpenAIChatAdapter`` — must sit below the boundary because
``core/`` may not import adapters (ADR-044 / SKUEL022). Mirrors the
ingestion-service factory relocation.
"""

from __future__ import annotations

from adapters.external.llm.openai_adapter import OpenAIChatAdapter
from core.services.dsl.llm_dsl_bridge import LLMDSLBridgeService


def create_llm_dsl_bridge(
    openai_api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> LLMDSLBridgeService:
    """Create an LLM DSL Bridge with an OpenAI chat adapter.

    Args:
        openai_api_key: OpenAI API key (read from the credential store/env if
            not provided).
        model: Model to use (default: gpt-4o-mini for cost efficiency).

    Returns:
        A configured ``LLMDSLBridgeService``. If no API key is available, the
        bridge is returned without a chat port — its async ``transform`` then
        returns an integration error (use ``transform_sync`` for rule-based).
    """
    from core.config.credential_store import get_credential

    api_key = openai_api_key or get_credential("OPENAI_API_KEY", fallback_to_env=True)

    if not api_key:
        return LLMDSLBridgeService(chat_port=None, model=model)

    return LLMDSLBridgeService(
        chat_port=OpenAIChatAdapter(api_key=api_key, default_model=model),
        model=model,
    )


__all__ = ["create_llm_dsl_bridge"]
