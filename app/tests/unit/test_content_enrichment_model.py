"""
W1 PR3 regression guard for ContentEnrichmentService.

The chat-port collapse must preserve the pre-W1 model default: journal
formatting used gpt-4o-mini (the former OpenAIService default). The
OpenAIChatAdapter's own default is gpt-4, so the enrichment call must pass the
model explicitly — otherwise model/cost/latency silently change.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.llm_protocols import LLMCompletion
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
