"""
Regression guards for ContentEnrichmentService.

The chat-port collapse must preserve the pre-W1 model default: journal
formatting used gpt-4o-mini (the former OpenAIService default). The
OpenAIChatAdapter's own default is gpt-4, so the enrichment call must pass the
model explicitly — otherwise model/cost/latency silently change.

The formatting instructions are the prompt registry's ``transcript_formatting``
template, which a local ``data/instructions/transcript_formatting.md`` overrides.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.llm_protocols import LLMCompletion
from core.prompts import registry as registry_module
from core.prompts.registry import PromptRegistry
from core.services import content_enrichment_service as enrichment_module
from core.services.content_enrichment_service import ContentEnrichmentService
from core.utils.result_simplified import Result


@pytest.mark.asyncio
async def test_intelligent_editing_passes_gpt_4o_mini():
    svc = ContentEnrichmentService(backend=MagicMock())
    svc.chat_port = MagicMock()
    svc.chat_port.complete = AsyncMock(
        return_value=Result.ok(LLMCompletion(text="formatted", model="gpt-4o-mini"))
    )
    svc._parse_ai_response = MagicMock(return_value=MagicMock())  # bypass parsing

    result = await svc._apply_intelligent_editing("raw transcript", "format it", context={})

    assert result.is_ok
    assert svc.chat_port.complete.await_args.kwargs["model"] == "gpt-4o-mini"


def _registry_over(overrides: Path) -> PromptRegistry:
    """The committed templates, with a local override directory of the test's own."""
    return PromptRegistry(Path(registry_module.__file__).parent / "templates", overrides)


def _formatting_service() -> tuple[ContentEnrichmentService, AsyncMock]:
    """The service over a chat port whose ``complete`` the test reads back."""
    complete = AsyncMock(
        return_value=Result.ok(LLMCompletion(text="formatted", model="gpt-4o-mini"))
    )
    svc = ContentEnrichmentService(backend=MagicMock())
    svc.chat_port = MagicMock(complete=complete)
    return svc, complete


def _sent_prompt(complete: AsyncMock) -> str:
    call = complete.await_args
    assert call is not None, "the chat port was never called"
    return call.args[0][0]["content"]


@pytest.mark.asyncio
async def test_a_transcript_is_formatted_by_the_registry_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_over(tmp_path)
    monkeypatch.setattr(enrichment_module, "PROMPT_REGISTRY", registry)
    svc, complete = _formatting_service()

    result = await svc.process_transcript("um so today I walked")

    assert result.is_ok
    assert registry.get("transcript_formatting").content.strip() in _sent_prompt(complete)


@pytest.mark.asyncio
async def test_a_local_override_replaces_the_formatting_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "transcript_formatting.md").write_text(
        "Keep every word; add headings only.", encoding="utf-8"
    )
    monkeypatch.setattr(enrichment_module, "PROMPT_REGISTRY", _registry_over(tmp_path))
    svc, complete = _formatting_service()

    await svc.process_transcript("um so today I walked")

    prompt = _sent_prompt(complete)
    assert "Keep every word; add headings only." in prompt
    assert "Journal Formatting Instructions" not in prompt
