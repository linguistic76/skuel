"""Unit tests for the chat-model switcher seam (core.services.chat.model_selection).

The seam resolves a per-conversation model choice against the wired caller and
degrades OpenAI-safe, and lists the picker's options from what the caller can serve —
so a dev env with no Anthropic adapter never offers or errors on a Claude model.
"""

from unittest.mock import AsyncMock, MagicMock

from core.ports.llm_protocols import LLMCompletion
from core.services.chat import (
    DEFAULT_CHAT_MODEL,
    HEADLINE_CHAT_MODELS,
    available_chat_models,
    resolve_chat_model,
)
from core.services.llm_caller import UnifiedLLMCaller
from core.utils.result_simplified import Result


def _port() -> MagicMock:
    port = MagicMock()
    port.complete = AsyncMock(return_value=Result.ok(LLMCompletion(text="x", model="m")))
    return port


def _both() -> UnifiedLLMCaller:
    """A FULL-tier caller: both providers wired."""
    return UnifiedLLMCaller(openai=_port(), anthropic=_port())


def _openai_only() -> UnifiedLLMCaller:
    """The dev-env caller: OpenAI wired, no Anthropic key."""
    return UnifiedLLMCaller(openai=_port(), anthropic=None)


# ---------------------------------------------------------------------------
# resolve_chat_model
# ---------------------------------------------------------------------------


def test_supported_request_wins():
    assert resolve_chat_model("claude-sonnet-4-6", _both()) == "claude-sonnet-4-6"
    assert resolve_chat_model("gpt-4o-mini", _both()) == "gpt-4o-mini"


def test_none_request_uses_default():
    assert resolve_chat_model(None, _both()) == DEFAULT_CHAT_MODEL
    assert resolve_chat_model("", _both()) == DEFAULT_CHAT_MODEL


def test_unavailable_claude_degrades_openai_safe():
    # dev: a forged/stale Claude request must fall back to the safe default, never error.
    assert resolve_chat_model("claude-opus-4-6", _openai_only()) == DEFAULT_CHAT_MODEL


def test_unknown_model_degrades_to_default():
    assert resolve_chat_model("llama-3", _both()) == DEFAULT_CHAT_MODEL


def test_falls_back_to_first_supported_when_default_unsupported():
    # Unusual OpenAI-less wiring: the default gpt-4o isn't serveable, so resolution
    # picks the first model the caller does support rather than an unroutable default.
    anthropic_only = UnifiedLLMCaller(openai=None, anthropic=_port())
    resolved = resolve_chat_model("gpt-4o", anthropic_only, default="gpt-4o")
    assert resolved.startswith("claude")
    assert anthropic_only.is_model_supported(resolved)


# ---------------------------------------------------------------------------
# available_chat_models
# ---------------------------------------------------------------------------


def test_options_filtered_by_caller_support():
    both = available_chat_models(_both())
    values = [v for v, _ in both]
    assert "claude-sonnet-4-6" in values
    assert "gpt-4o" in values
    # Every offered option is a labelled (value, label) pair the caller can serve.
    assert all(len(pair) == 2 and pair[1] for pair in both)


def test_dev_env_offers_only_openai_models():
    values = [v for v, _ in available_chat_models(_openai_only())]
    assert values  # not empty
    assert all(v.startswith("gpt") for v in values)
    assert not any(v.startswith("claude") for v in values)


def test_options_are_a_subset_of_headline_in_order():
    both = available_chat_models(_both())
    headline_values = [v for v, _ in HEADLINE_CHAT_MODELS]
    offered_values = [v for v, _ in both]
    # Preserves headline ordering (curation lives in the module, availability in the caller).
    assert offered_values == [v for v in headline_values if v in offered_values]
