"""Shared chat-surface helpers — the LLM switcher seam (Phase 2).

The single point both chat surfaces (Askesis + Journals) resolve a per-conversation
model choice through. This package is where Phase 3's ChatFacade (shared authored
instruction-set + shared conversation memory) grows from — keep model resolution here,
not scattered across the surfaces.
"""

from core.services.chat.model_selection import (
    DEFAULT_CHAT_MODEL,
    HEADLINE_CHAT_MODELS,
    available_chat_models,
    resolve_chat_model,
)

__all__ = [
    "DEFAULT_CHAT_MODEL",
    "HEADLINE_CHAT_MODELS",
    "available_chat_models",
    "resolve_chat_model",
]
