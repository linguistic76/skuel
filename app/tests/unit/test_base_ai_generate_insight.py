"""``BaseAIService._generate_insight`` hands its callers the response's text.

Runs the real ``LLMService`` over a scripted chat port. ``generate`` never
raises — a provider failure is a response with empty ``content`` and a set
``error`` — so the helper is the one place that failure becomes a failed
``Result``. Covered through ``TasksAIService``: a method that returns the
text directly, one that parses it, and the provider failure under both.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.services.llm_service import LLMService
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.result_simplified import ErrorCategory, Result
from tests.fixtures.llm_doubles import embeddings_double, failing_llm, scripted_llm


def _service(llm: LLMService) -> TasksAIService:
    backend = Mock()
    backend.get = AsyncMock(
        return_value=Result.ok(
            Task(uid="task_1", user_uid="user_1", title="Plan trip", status=EntityStatus.ACTIVE)
        )
    )
    return TasksAIService(backend=backend, llm_service=llm, embeddings_service=embeddings_double())


@pytest.mark.asyncio
async def test_direct_return_method_answers_the_text() -> None:
    service = _service(scripted_llm("Book the flights first."))

    result = await service.generate_task_insight("task_1")

    assert result.is_ok
    assert result.value == "Book the flights first."


@pytest.mark.asyncio
async def test_text_parsing_method_splits_the_text() -> None:
    service = _service(scripted_llm("- Book flights\n- Reserve hotel\n\n- Pack"))

    result = await service.generate_task_breakdown("task_1", max_subtasks=5)

    assert result.is_ok
    assert result.value == ["Book flights", "Reserve hotel", "Pack"]


@pytest.mark.asyncio
async def test_mock_provider_answers_text_with_no_network() -> None:
    service = _service(LLMService())

    result = await service.generate_task_insight("task_1")

    assert result.is_ok
    assert isinstance(result.value, str)
    assert result.value


@pytest.mark.parametrize("method", ["generate_task_insight", "generate_task_breakdown"])
@pytest.mark.asyncio
async def test_provider_failure_is_a_failed_result(method: str) -> None:
    service = _service(failing_llm("rate limited"))

    result = await getattr(service, method)("task_1")

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.INTEGRATION
    assert "rate limited" in error.message
