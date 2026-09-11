"""``suggest_priority`` speaks the Priority vocabulary: three levels, canonical values."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.result_simplified import Result


def _service(answer: str) -> tuple[TasksAIService, AsyncMock]:
    service = TasksAIService.__new__(TasksAIService)
    service.backend = Mock()
    service.backend.get = AsyncMock(
        return_value=Result.ok(
            Task(
                uid="task_1",
                user_uid="user_1",
                title="Renew passport",
                status=EntityStatus.ACTIVE,
            )
        )
    )
    service.logger = Mock()
    insight = AsyncMock(return_value=Result.ok(answer))
    service._generate_insight = insight  # type: ignore[method-assign]
    return service, insight


@pytest.mark.asyncio
async def test_prompt_offers_only_the_three_levels() -> None:
    service, insight = _service("PRIORITY: HIGH\nREASONING: Expires in two weeks")

    await service.suggest_priority("task_1")

    call = insight.await_args
    assert call is not None
    prompt = call.args[0]
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
