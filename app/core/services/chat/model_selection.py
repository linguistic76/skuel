"""Per-conversation chat-model selection — the shared resolution seam (LLM switcher).

Model choice is **per conversation** (the claude.ai / chatgpt pattern): a conversation
carries a currently-selected model and each turn uses it. Switching is free — a
conversation's history is model-agnostic messages, so changing the selection simply
routes the NEXT turn to the new model; prior turns keep whatever generated them. There
is no mid-conversation state to migrate. Phase 1's ``UnifiedLLMCaller.complete(messages,
*, model=...)`` already routes per call, so the switcher only has to *choose* the model.

``resolve_chat_model`` is the ONE point both chat surfaces (Askesis + Journals) pass a
requested model through — the OpenAI-safe gate that lets a Claude request degrade
cleanly in an env without an ``ANTHROPIC_API_KEY``. Availability always comes from the
wired caller (``is_model_supported`` / ``get_supported_models``), never a second
hardcoded truth: in a dev env with no Anthropic adapter the Claude headline models are
simply absent from the picker, and a forged Claude request falls back to the safe
default instead of erroring at the provider port.

This module is the seam Phase 3's ChatFacade grows from — resolution lives here, not in
the surfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.llm_caller import LLMCallerProtocol

# The app-safe default for a fresh conversation. OpenAI is required at FULL-tier
# bootstrap (fail-fast), so ``gpt-4o`` is always reachable; Claude is opt-in per call
# and never a global default (a Claude default would break the no-Anthropic-key env).
DEFAULT_CHAT_MODEL = "gpt-4o"

# Curated headline models offered in a picker, in display order (value, label).
# Mirrors the Exercise editor's set — the shared vocabulary for a model switcher. This
# list carries curation + ordering + labels ONLY; whether an entry is actually *offered*
# is decided by the wired caller (see ``available_chat_models``), never this list.
HEADLINE_CHAT_MODELS: tuple[tuple[str, str], ...] = (
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-opus-4-6", "Claude Opus 4.6"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("gpt-4o", "GPT-4o"),
    ("gpt-4o-mini", "GPT-4o Mini"),
)


def _supported_models(caller: LLMCallerProtocol) -> set[str]:
    """Flatten the caller's concrete per-provider model lists into a lookup set.

    Uses the explicit ``get_supported_models`` lists, NOT the prefix-based
    ``is_model_supported`` — a bare prefix check treats any ``gpt*`` string (e.g.
    ``gpt-not-real``) as valid whenever the OpenAI adapter is wired, and would forward
    that forged/stale name to the provider, turning the answer into an error instead of
    the advertised OpenAI-safe degrade (Codex #781 P2). Validating against the concrete
    allowlist closes that gap.
    """
    return {model for models in caller.get_supported_models().values() for model in models}


def resolve_chat_model(
    requested: str | None,
    caller: LLMCallerProtocol,
    *,
    default: str = DEFAULT_CHAT_MODEL,
) -> str:
    """Resolve a per-conversation model choice to a model the caller can serve.

    The per-conversation selection wins when it is in the caller's concrete
    supported-model allowlist; otherwise it degrades OpenAI-safe to ``default`` (and,
    only if even the default is absent — an unusual OpenAI-less wiring — to the first
    model the caller does support). A forged or stale request (an unlisted ``gpt-*``
    name, or a Claude model in a no-Anthropic-key env) therefore answers via the safe
    default instead of erroring at the provider port.
    """
    provider_models = caller.get_supported_models()
    supported = {model for models in provider_models.values() for model in models}
    if requested and requested in supported:
        return requested
    if default in supported:
        return default
    for models in provider_models.values():
        if models:
            return models[0]
    return default


def available_chat_models(caller: LLMCallerProtocol) -> list[tuple[str, str]]:
    """Headline ``(value, label)`` pairs the caller can actually serve — a picker's options.

    Availability comes from the caller's concrete allowlist (``get_supported_models``),
    so a surface with no Anthropic adapter (dev) offers only the OpenAI models and never
    a Claude option that would silently fall back. Empty only when no adapter is wired
    (CORE tier) — the picker fails soft to no control.
    """
    supported = _supported_models(caller)
    return [(value, label) for value, label in HEADLINE_CHAT_MODELS if value in supported]


__all__ = [
    "DEFAULT_CHAT_MODEL",
    "HEADLINE_CHAT_MODELS",
    "available_chat_models",
    "resolve_chat_model",
]
