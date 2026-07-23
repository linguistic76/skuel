"""LLM chat-completion adapters (W1 — vendor SDKs behind a port)."""

from adapters.external.llm.anthropic_adapter import AnthropicChatAdapter
from adapters.external.llm.dsl_bridge_factory import create_llm_dsl_bridge
from adapters.external.llm.factory import ChatClients, create_chat_client
from adapters.external.llm.openai_adapter import OpenAIChatAdapter

__all__ = [
    "AnthropicChatAdapter",
    "ChatClients",
    "OpenAIChatAdapter",
    "create_chat_client",
    "create_llm_dsl_bridge",
]
