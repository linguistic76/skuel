"""The mock factories keep the promise the pytest skill makes of them."""

from unittest.mock import AsyncMock

import pytest

from core.utils.result_simplified import Result
from tests.fixtures.service_factories import (
    create_mock_backend,
    create_mock_backend_for_base_service,
)


@pytest.mark.asyncio
async def test_behavior_for_a_method_outside_the_prebuilt_set_is_awaitable() -> None:
    backend = create_mock_backend({"link_task_to_goal": Result.ok(True)})

    assert isinstance(backend.link_task_to_goal, AsyncMock)
    assert (await backend.link_task_to_goal("task_x_000001", "goal_y_000001")).value is True


@pytest.mark.asyncio
async def test_behavior_for_a_prebuilt_method_rescripts_it() -> None:
    entity = object()
    backend = create_mock_backend({"get": Result.ok(entity)})

    assert (await backend.get("task_x_000001")).value is entity


@pytest.mark.asyncio
async def test_base_service_factory_scripts_an_unlisted_method_the_same_way() -> None:
    backend = create_mock_backend_for_base_service({"text_search_raw": Result.ok([])})

    assert isinstance(backend.text_search_raw, AsyncMock)
    assert (await backend.text_search_raw("q", ("title",))).value == []
