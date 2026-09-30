"""``suggest_priority`` speaks the Priority vocabulary: three levels, canonical values.

Runs the real ``LLMService`` over a scripted chat port, so the parse below
reads the text ``_generate_insight`` hands back — not a value a test injected
above the helper.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.result_simplified import Result
from tests.fixtures.llm_doubles import ScriptedChatCaller, embeddings_double, scripted_llm


def _service(answer: str) -> tuple[TasksAIService, ScriptedChatCaller]:
    backend = Mock()
    backend.get = AsyncMock(
        return_value=Result.ok(
            Task(
                uid="task_1",
                user_uid="user_1",
                title="Renew passport",
                status=EntityStatus.ACTIVE,
            )
        )
    )
    llm = scripted_llm(answer)
    service = TasksAIService(
        backend=backend, llm_service=llm, embeddings_service=embeddings_double()
    )
    assert isinstance(llm.caller, ScriptedChatCaller)
    return service, llm.caller


@pytest.mark.asyncio
async def test_prompt_offers_only_the_three_levels() -> None:
    service, caller = _service("PRIORITY: HIGH\nREASONING: Expires in two weeks")

    await service.suggest_priority("task_1")

    assert len(caller.calls) == 1
    prompt = caller.calls[0][-1]["content"]
    assert "HIGH, MEDIUM, LOW" in prompt
    assert "CRITICAL" not in prompt and "NONE" not in prompt


@pytest.mark.asyncio
async def test_suggestion_is_the_canonical_member_value() -> None:
    service, _ = _service("PRIORITY: High\nREASONING: Expires in two weeks")

    result = await service.suggest_priority("task_1")

    assert result.is_ok
    assert result.value["suggested_priority"] == "high"
    assert result.value["reasoning"] == "Expires in two weeks"


@pytest.mark.asyncio
async def test_answer_outside_the_vocabulary_reads_as_medium() -> None:
    service, _ = _service("PRIORITY: URGENT\nREASONING: Model went off-script")

    result = await service.suggest_priority("task_1")

    assert result.is_ok
    assert result.value["suggested_priority"] == "medium"
