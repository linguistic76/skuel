"""Unit tests for HierarchyReadMixin (DRY arc #3).

Exercises the shared typed-hierarchy reads through a real ``TasksCoreService`` host
(so the mixin MRO — HierarchyReadMixin + BaseService/ConversionHelpersMixin — and the
DomainConfig-sourced dto/model classes are all in play), with a mocked backend.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.models.task.task import Task
from core.services.tasks.tasks_core_service import TasksCoreService
from core.utils.result_simplified import Result


@pytest.fixture
def service() -> TasksCoreService:
    return TasksCoreService(backend=AsyncMock())


@pytest.mark.asyncio
async def test_get_subentities_converts_children(service: TasksCoreService) -> None:
    child = Task(uid="task.2", title="Child", user_uid="user_1")
    service.backend.get_children_raw = AsyncMock(return_value=Result.ok([child]))

    result = await service.get_subentities("task.1", depth=2)

    assert result.is_ok
    # _to_domain_model round-trips through the DTO, so compare by identity key, not ==.
    assert [t.uid for t in result.value] == ["task.2"]
    service.backend.get_children_raw.assert_awaited_once_with("task.1", 2)


@pytest.mark.asyncio
async def test_get_parent_entity_returns_none_when_root(service: TasksCoreService) -> None:
    service.backend.get_parent_raw = AsyncMock(return_value=Result.ok(None))

    result = await service.get_parent_entity("task.2")

    assert result.is_ok
    assert result.value is None


@pytest.mark.asyncio
async def test_get_parent_entity_converts_parent(service: TasksCoreService) -> None:
    parent = Task(uid="task.1", title="Parent", user_uid="user_1")
    service.backend.get_parent_raw = AsyncMock(return_value=Result.ok(parent))

    result = await service.get_parent_entity("task.2")

    assert result.is_ok
    assert result.value is not None
    assert result.value.uid == "task.1"


@pytest.mark.asyncio
async def test_get_entity_hierarchy_shape(service: TasksCoreService) -> None:
    current = Task(uid="task.1", title="Current", user_uid="user_1")
    ancestor = Task(uid="task.0", title="Ancestor", user_uid="user_1")
    sibling = Task(uid="task.9", title="Sibling", user_uid="user_1")
    child = Task(uid="task.2", title="Child", user_uid="user_1")
    service.backend.get = AsyncMock(return_value=Result.ok(current))
    service.backend.get_hierarchy_raw = AsyncMock(
        return_value=Result.ok(
            {"ancestors": [ancestor], "siblings": [sibling], "children": [child]}
        )
    )

    result = await service.get_entity_hierarchy("task.1")

    assert result.is_ok
    hierarchy = result.value
    assert hierarchy["current"].uid == "task.1"
    assert [t.uid for t in hierarchy["ancestors"]] == ["task.0"]
    assert [t.uid for t in hierarchy["siblings"]] == ["task.9"]
    assert [t.uid for t in hierarchy["children"]] == ["task.2"]
    assert hierarchy["depth"] == 1  # len(ancestors)


@pytest.mark.asyncio
async def test_get_subentities_propagates_backend_error(service: TasksCoreService) -> None:
    from core.utils.result_simplified import Errors

    service.backend.get_children_raw = AsyncMock(
        return_value=Result.fail(Errors.database(message="boom", operation="get_children_raw"))
    )

    result = await service.get_subentities("task.1")

    assert result.is_error
