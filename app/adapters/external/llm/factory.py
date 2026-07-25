"""
Chat Client Factory — THE Chat Provider Choice Chokepoint
=========================================================

``create_chat_client()`` is the single place that decides which chat-completion
providers SKUEL wires and reads their credentials — the chat-side mirror of
``create_embedding_client()`` (ADR-068). Before this, chat adapters were
instantiated inline at three separate points in the composition root, each with
its own credential read, which let the LLM-consuming surfaces drift onto
different providers. One chokepoint keeps them convergent.

It sits below the hexagonal boundary (like ``dsl_bridge_factory``): it reads
credentials and constructs the vendor adapters + the ``UnifiedLLMCaller`` (a
core service that depends only on ``ChatCompletionPort``). ``core/`` may not
import adapters (ADR-044 / SKUEL022), so this assembly must live here.

OpenAI is required in FULL tier; Anthropic is optional (present only when
``ANTHROPIC_API_KEY`` is set). Callers gate on ``INTELLIGENCE_TIER`` before
calling — CORE tier never reaches here.
"""

from __future__ import annotations

from dataclasses import dataclass

from adapters.external.llm.anthropic_adapter import AnthropicChatAdapter
from adapters.external.llm.openai_adapter import OpenAIChatAdapter
from core.config.credential_store import get_credential
from core.ports.llm_protocols import ChatCompletionPort
from core.services.chat.model_selection import DEFAULT_CHAT_MODEL
from core.services.llm_caller import UnifiedLLMCaller

# Bootstrap placeholder values that mean "no key configured" (mirrors the
# checks the composition root used inline before this factory existed).
_OPENAI_PLACEHOLDER_KEYS = frozenset({"your-openai-api-key-here", "sk-"})


@dataclass(frozen=True)
class ChatClients:
    """The wired chat-completion capability of the app.

    Attributes:
        openai: The OpenAI chat adapter (always present in FULL tier — it is
            the required provider). Consumed directly by services that hardcode
            an OpenAI model (content enrichment) and, until the surfaces are
            re-rooted, the RAG ``LLMService``.
        caller: The multi-provider ``UnifiedLLMCaller`` that routes by model
            prefix (``gpt*`` → OpenAI, ``claude*`` → Anthropic). THE provider-
            agnostic chat path; Anthropic is reachable through it iff wired.
    """

    openai: ChatCompletionPort
    caller: UnifiedLLMCaller


def create_chat_client() -> ChatClients:
    """Construct the wired chat-completion clients (the chat chokepoint).

    Reads ``OPENAI_API_KEY`` (required) and ``ANTHROPIC_API_KEY`` (optional)
    once, builds the vendor adapters, and assembles the ``UnifiedLLMCaller``.

    Raises:
        ValueError: If ``OPENAI_API_KEY`` is missing or a bootstrap placeholder.
            FULL-tier callers surface this with ``INTELLIGENCE_TIER`` guidance;
            set ``INTELLIGENCE_TIER=core`` to run without chat features.
    """
    openai_api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
    if not openai_api_key or openai_api_key in _OPENAI_PLACEHOLDER_KEYS:
        raise ValueError(
            "FULL-tier bootstrap requires OPENAI_API_KEY. "
            "Set INTELLIGENCE_TIER=core to run without LLM features, or "
            "set OPENAI_API_KEY in the credential store / environment."
        )
    # One fallback model, not two: the adapter's no-model-given default is the
    # same DEFAULT_CHAT_MODEL that resolve_chat_model() degrades to.
    openai_chat = OpenAIChatAdapter(api_key=openai_api_key, default_model=DEFAULT_CHAT_MODEL)

    anthropic_api_key = get_credential("ANTHROPIC_API_KEY", fallback_to_env=True)
    anthropic_chat = AnthropicChatAdapter(api_key=anthropic_api_key) if anthropic_api_key else None

    caller = UnifiedLLMCaller(openai=openai_chat, anthropic=anthropic_chat)
    return ChatClients(openai=openai_chat, caller=caller)


__all__ = ["ChatClients", "create_chat_client"]
