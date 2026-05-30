"""Regression test: list-only facades unwrap the backend's (page, count) tuple.

backend.list() returns Result[tuple[list[T], int]] (the BaseService contract).
ResourceService.list_all / ExerciseService.list_all promise Result[list[T]], so
they must unwrap the page. Their backend is typed Any, so mypy cannot verify this
— without the unwrap, consumers iterating result.value hit the (list, int) tuple
and crash. Locks the fix that accompanies the _CrudMixin.list -> tuple change.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.resource_service import ResourceService
from core.utils.result_simplified import Result


@pytest.mark.asyncio
async def test_resource_list_all_returns_bare_list():
    backend = MagicMock()
    r1, r2 = MagicMock(), MagicMock()
    backend.list = AsyncMock(return_value=Result.ok(([r1, r2], 2)))

    service = ResourceService(backend)
    result = await service.list_all()

    assert result.is_ok
    # The page list, not the (list, int) tuple.
    assert result.value == [r1, r2]
    assert all(not isinstance(item, tuple) for item in result.value)


@pytest.mark.asyncio
async def test_exercise_list_all_returns_bare_list():
    from core.services.exercises.exercise_service import ExerciseService

    backend = MagicMock()
    e1 = MagicMock()
    backend.list = AsyncMock(return_value=Result.ok(([e1], 1)))

    service = ExerciseService(backend)
    result = await service.list_all()

    assert result.is_ok
    assert result.value == [e1]
