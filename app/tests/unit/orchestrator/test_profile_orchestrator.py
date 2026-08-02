"""Tests for the ProfileOrchestrator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import Priority
from core.models.enums.entity_enums import EntityType
from core.orchestrator.profile_orchestrator import ProfileOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _item(priority: Priority | str = Priority.MEDIUM, status: str = "active") -> SimpleNamespace:
    return SimpleNamespace(priority=priority, status=status)


def _build() -> tuple[ProfileOrchestrator, dict[str, MagicMock]]:
    mocks = {
        "tasks_service": MagicMock(),
        "goals_service": MagicMock(),
        "habits_service": MagicMock(),
        "events_service": MagicMock(),
        "choices_service": MagicMock(),
        "principles_service": MagicMock(),
        "sharing_service": MagicMock(),
    }
    mocks["tasks_service"].get_user_tasks = AsyncMock()
    mocks["goals_service"].get_user_goals = AsyncMock()
    mocks["habits_service"].get_user_habits = AsyncMock()
    mocks["events_service"].get_user_events = AsyncMock()
    mocks["choices_service"].get_user_choices = AsyncMock()
    mocks["principles_service"].get_user_principles = AsyncMock()
    mocks["sharing_service"].get_shared_with_me = AsyncMock()

    orch = ProfileOrchestrator(
        tasks_service=mocks["tasks_service"],
        goals_service=mocks["goals_service"],
        habits_service=mocks["habits_service"],
        events_service=mocks["events_service"],
        choices_service=mocks["choices_service"],
        principles_service=mocks["principles_service"],
        sharing_service=mocks["sharing_service"],
    )
    return orch, mocks


# --- get_domain_preview_items ---


@pytest.mark.asyncio
async def test_get_domain_preview_items_invalid_slug_returns_validation_error() -> None:
    orch, mocks = _build()

    result = await orch.get_domain_preview_items("user_1", "widgets")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    mocks["tasks_service"].get_user_tasks.assert_not_called()


@pytest.mark.asyncio
async def test_get_domain_preview_items_tasks_dispatch() -> None:
    orch, mocks = _build()
    mocks["tasks_service"].get_user_tasks.return_value = Result.ok([])
    await orch.get_domain_preview_items("user_1", "tasks")
    mocks["tasks_service"].get_user_tasks.assert_called_once_with("user_1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_goals_dispatch() -> None:
    orch, mocks = _build()
    mocks["goals_service"].get_user_goals.return_value = Result.ok([])
    await orch.get_domain_preview_items("user_1", "goals")
    mocks["goals_service"].get_user_goals.assert_called_once_with("user_1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_habits_dispatch() -> None:
    orch, mocks = _build()
    mocks["habits_service"].get_user_habits.return_value = Result.ok([])
    await orch.get_domain_preview_items("user_1", "habits")
    mocks["habits_service"].get_user_habits.assert_called_once_with("user_1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_events_dispatch() -> None:
    orch, mocks = _build()
    mocks["events_service"].get_user_events.return_value = Result.ok([])
    await orch.get_domain_preview_items("user_1", "events")
    mocks["events_service"].get_user_events.assert_called_once_with("user_1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_choices_dispatch() -> None:
    orch, mocks = _build()
    mocks["choices_service"].get_user_choices.return_value = Result.ok([])
    await orch.get_domain_preview_items("user_1", "choices")
    mocks["choices_service"].get_user_choices.assert_called_once_with("user_1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_principles_dispatch() -> None:
    orch, mocks = _build()
    mocks["principles_service"].get_user_principles.return_value = Result.ok([])
    await orch.get_domain_preview_items("user_1", "principles")
    mocks["principles_service"].get_user_principles.assert_called_once_with("user_1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_filters_out_terminal_statuses() -> None:
    orch, mocks = _build()
    items = [
        _item(status="active"),
        _item(status="completed"),
        _item(status="failed"),
        _item(status="cancelled"),
        _item(status="archived"),
        _item(status="active"),
    ]
    mocks["tasks_service"].get_user_tasks.return_value = Result.ok(items)

    result = await orch.get_domain_preview_items("user_1", "tasks")

    assert result.is_ok
    assert len(result.value) == 2
    assert all(item.status == "active" for item in result.value)


@pytest.mark.asyncio
async def test_get_domain_preview_items_sorts_by_priority_descending() -> None:
    orch, mocks = _build()
    items = [
        _item(priority=Priority.LOW),
        _item(priority=Priority.CRITICAL),
        _item(priority=Priority.MEDIUM),
        _item(priority=Priority.HIGH),
    ]
    mocks["tasks_service"].get_user_tasks.return_value = Result.ok(items)

    result = await orch.get_domain_preview_items("user_1", "tasks")

    assert result.is_ok
    priorities = [item.priority for item in result.value]
    assert priorities == [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM]


@pytest.mark.asyncio
async def test_get_domain_preview_items_limits_to_three() -> None:
    orch, mocks = _build()
    items = [_item() for _ in range(10)]
    mocks["tasks_service"].get_user_tasks.return_value = Result.ok(items)

    result = await orch.get_domain_preview_items("user_1", "tasks")

    assert result.is_ok
    assert len(result.value) == 3


@pytest.mark.asyncio
async def test_get_domain_preview_items_service_error_propagates() -> None:
    orch, mocks = _build()
    mocks["tasks_service"].get_user_tasks.return_value = Result.fail(
        Errors.database("read", "boom")
    )

    result = await orch.get_domain_preview_items("user_1", "tasks")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE


# --- Smoke delegation tests ---


@pytest.mark.asyncio
async def test_get_shared_with_me_items_delegates() -> None:
    orch, mocks = _build()
    mocks["sharing_service"].get_shared_with_me.return_value = Result.ok([])
    await orch.get_shared_with_me_items("user_1", limit=25)
    mocks["sharing_service"].get_shared_with_me.assert_called_once_with(
        user_uid="user_1", limit=25, entity_type=None, sharer_uid=None
    )


@pytest.mark.asyncio
async def test_get_shared_with_me_items_forwards_filters() -> None:
    """Arc 2 C4: the inbox filters pass through the orchestrator untouched."""
    orch, mocks = _build()
    mocks["sharing_service"].get_shared_with_me.return_value = Result.ok([])
    await orch.get_shared_with_me_items(
        "user_1", limit=25, entity_type=EntityType.ENTRY_REPORT, sharer_uid="user_admin"
    )
    mocks["sharing_service"].get_shared_with_me.assert_called_once_with(
        user_uid="user_1",
        limit=25,
        entity_type=EntityType.ENTRY_REPORT,
        sharer_uid="user_admin",
    )
