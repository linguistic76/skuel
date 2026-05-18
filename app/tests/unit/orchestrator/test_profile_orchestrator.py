"""Tests for the ProfileOrchestrator."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import Priority
from core.orchestrator.profile_orchestrator import ProfileOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _item(priority: Priority | str = Priority.MEDIUM, status: str = "active") -> SimpleNamespace:
    return SimpleNamespace(priority=priority, status=status)


def _build(
    context_intelligence: MagicMock | None = None,
) -> tuple[ProfileOrchestrator, dict[str, MagicMock]]:
    mocks = {
        "tasks_service": MagicMock(),
        "goals_service": MagicMock(),
        "habits_service": MagicMock(),
        "events_service": MagicMock(),
        "choices_service": MagicMock(),
        "principles_service": MagicMock(),
        "exercise_report_service": MagicMock(),
        "activity_report_service": MagicMock(),
        "sharing_service": MagicMock(),
        "ps_service": MagicMock(),
        "exercises_service": MagicMock(),
    }
    mocks["tasks_service"].get_user_tasks = AsyncMock()
    mocks["goals_service"].get_user_goals = AsyncMock()
    mocks["habits_service"].get_user_habits = AsyncMock()
    mocks["events_service"].get_user_events = AsyncMock()
    mocks["choices_service"].get_user_choices = AsyncMock()
    mocks["principles_service"].get_user_principles = AsyncMock()
    mocks["exercise_report_service"].get_assessments_for_student = AsyncMock()
    mocks["activity_report_service"].get_history = AsyncMock()
    mocks["sharing_service"].get_shared_with_me = AsyncMock()
    mocks["ps_service"].get_all_user_knowledge_status = AsyncMock()
    mocks["exercises_service"].get_student_exercises = AsyncMock()

    orch = ProfileOrchestrator(
        tasks_service=mocks["tasks_service"],
        goals_service=mocks["goals_service"],
        habits_service=mocks["habits_service"],
        events_service=mocks["events_service"],
        choices_service=mocks["choices_service"],
        principles_service=mocks["principles_service"],
        exercise_report_service=mocks["exercise_report_service"],
        activity_report_service=mocks["activity_report_service"],
        sharing_service=mocks["sharing_service"],
        ps_service=mocks["ps_service"],
        exercises_service=mocks["exercises_service"],
        context_intelligence=context_intelligence,
    )
    return orch, mocks


@pytest.fixture
def full_built() -> tuple[ProfileOrchestrator, dict[str, MagicMock], MagicMock, MagicMock]:
    intel = MagicMock()
    intel.get_ready_to_work_on_today = AsyncMock()
    intel.calculate_life_path_alignment = AsyncMock()
    intel.get_cross_domain_synergies = AsyncMock()
    intel.get_optimal_next_path_steps = AsyncMock()
    factory = MagicMock()
    factory.create.return_value = intel
    orch, mocks = _build(context_intelligence=factory)
    return orch, mocks, factory, intel


# --- get_domain_preview_items ---


@pytest.mark.asyncio
async def test_get_domain_preview_items_invalid_slug_returns_validation_error() -> None:
    orch, mocks = _build()

    result = await orch.get_domain_preview_items("user-1", "widgets")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    mocks["tasks_service"].get_user_tasks.assert_not_called()


@pytest.mark.asyncio
async def test_get_domain_preview_items_tasks_dispatch() -> None:
    orch, mocks = _build()
    mocks["tasks_service"].get_user_tasks.return_value = Result.ok([])
    await orch.get_domain_preview_items("user-1", "tasks")
    mocks["tasks_service"].get_user_tasks.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_goals_dispatch() -> None:
    orch, mocks = _build()
    mocks["goals_service"].get_user_goals.return_value = Result.ok([])
    await orch.get_domain_preview_items("user-1", "goals")
    mocks["goals_service"].get_user_goals.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_habits_dispatch() -> None:
    orch, mocks = _build()
    mocks["habits_service"].get_user_habits.return_value = Result.ok([])
    await orch.get_domain_preview_items("user-1", "habits")
    mocks["habits_service"].get_user_habits.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_events_dispatch() -> None:
    orch, mocks = _build()
    mocks["events_service"].get_user_events.return_value = Result.ok([])
    await orch.get_domain_preview_items("user-1", "events")
    mocks["events_service"].get_user_events.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_choices_dispatch() -> None:
    orch, mocks = _build()
    mocks["choices_service"].get_user_choices.return_value = Result.ok([])
    await orch.get_domain_preview_items("user-1", "choices")
    mocks["choices_service"].get_user_choices.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_domain_preview_items_principles_dispatch() -> None:
    orch, mocks = _build()
    mocks["principles_service"].get_user_principles.return_value = Result.ok([])
    await orch.get_domain_preview_items("user-1", "principles")
    mocks["principles_service"].get_user_principles.assert_called_once_with("user-1")


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

    result = await orch.get_domain_preview_items("user-1", "tasks")

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

    result = await orch.get_domain_preview_items("user-1", "tasks")

    assert result.is_ok
    priorities = [item.priority for item in result.value]
    assert priorities == [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM]


@pytest.mark.asyncio
async def test_get_domain_preview_items_limits_to_three() -> None:
    orch, mocks = _build()
    items = [_item() for _ in range(10)]
    mocks["tasks_service"].get_user_tasks.return_value = Result.ok(items)

    result = await orch.get_domain_preview_items("user-1", "tasks")

    assert result.is_ok
    assert len(result.value) == 3


@pytest.mark.asyncio
async def test_get_domain_preview_items_service_error_propagates() -> None:
    orch, mocks = _build()
    mocks["tasks_service"].get_user_tasks.return_value = Result.fail(
        Errors.database("read", "boom")
    )

    result = await orch.get_domain_preview_items("user-1", "tasks")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE


# --- get_intelligence_data ---


@pytest.mark.asyncio
async def test_get_intelligence_data_core_tier_returns_none() -> None:
    orch, _ = _build(context_intelligence=None)
    context = MagicMock()

    result = await orch.get_intelligence_data(context)

    assert result.is_ok
    assert result.value is None


@pytest.mark.asyncio
async def test_get_intelligence_data_all_calls_succeed(
    full_built: tuple[ProfileOrchestrator, dict[str, MagicMock], MagicMock, MagicMock],
) -> None:
    orch, _, _, intel = full_built
    intel.get_ready_to_work_on_today.return_value = Result.ok({"plan": "x"})
    intel.calculate_life_path_alignment.return_value = Result.ok({"align": "y"})
    intel.get_cross_domain_synergies.return_value = Result.ok({"syn": "z"})
    intel.get_optimal_next_path_steps.return_value = Result.ok([{"ps": "1"}])

    result = await orch.get_intelligence_data(MagicMock())

    assert result.is_ok
    data = result.value
    assert data is not None
    assert data["daily_plan"] == {"plan": "x"}
    assert data["alignment"] == {"align": "y"}
    assert data["synergies"] == {"syn": "z"}
    assert data["path_steps"] == [{"ps": "1"}]
    assert data["partial_errors"] == []


@pytest.mark.asyncio
async def test_get_intelligence_data_partial_failure_still_returns_ok(
    full_built: tuple[ProfileOrchestrator, dict[str, MagicMock], MagicMock, MagicMock],
) -> None:
    orch, _, _, intel = full_built
    intel.get_ready_to_work_on_today.return_value = Result.ok({"plan": "x"})
    intel.calculate_life_path_alignment.return_value = Result.fail(Errors.database("read", "boom"))
    intel.get_cross_domain_synergies.return_value = Result.ok({"syn": "z"})
    intel.get_optimal_next_path_steps.return_value = Result.fail(Errors.database("read", "boom"))

    result = await orch.get_intelligence_data(MagicMock())

    assert result.is_ok
    data = result.value
    assert data is not None
    assert data["daily_plan"] == {"plan": "x"}
    assert data["alignment"] is None
    assert data["synergies"] == {"syn": "z"}
    assert data["path_steps"] is None
    assert len(data["partial_errors"]) == 2


@pytest.mark.asyncio
async def test_get_intelligence_data_all_calls_fail_returns_error(
    full_built: tuple[ProfileOrchestrator, dict[str, MagicMock], MagicMock, MagicMock],
) -> None:
    orch, _, _, intel = full_built
    err: Result[Any] = Result.fail(Errors.database("read", "boom"))
    intel.get_ready_to_work_on_today.return_value = err
    intel.calculate_life_path_alignment.return_value = err
    intel.get_cross_domain_synergies.return_value = err
    intel.get_optimal_next_path_steps.return_value = err

    result = await orch.get_intelligence_data(MagicMock())

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.SYSTEM


@pytest.mark.asyncio
async def test_get_intelligence_data_exception_caught_as_partial_error(
    full_built: tuple[ProfileOrchestrator, dict[str, MagicMock], MagicMock, MagicMock],
) -> None:
    orch, _, _, intel = full_built
    intel.get_ready_to_work_on_today.side_effect = RuntimeError("kaboom")
    intel.calculate_life_path_alignment.return_value = Result.ok({"align": "y"})
    intel.get_cross_domain_synergies.return_value = Result.ok({"syn": "z"})
    intel.get_optimal_next_path_steps.return_value = Result.ok([])

    result = await orch.get_intelligence_data(MagicMock())

    assert result.is_ok
    data = result.value
    assert data is not None
    assert data["daily_plan"] is None
    assert data["alignment"] == {"align": "y"}
    assert "Daily plan unavailable" in data["partial_errors"]


@pytest.mark.asyncio
async def test_get_intelligence_data_factory_misconfigured_returns_none(
    full_built: tuple[ProfileOrchestrator, dict[str, MagicMock], MagicMock, MagicMock],
) -> None:
    orch, _, factory, _ = full_built
    factory.create.side_effect = AttributeError("missing dep")

    result = await orch.get_intelligence_data(MagicMock())

    assert result.is_ok
    assert result.value is None


# --- Smoke delegation tests ---


@pytest.mark.asyncio
async def test_get_assigned_exercises_delegates() -> None:
    orch, mocks = _build()
    mocks["exercises_service"].get_student_exercises.return_value = Result.ok([])
    await orch.get_assigned_exercises("user-1")
    mocks["exercises_service"].get_student_exercises.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_get_recent_exercise_reports_delegates() -> None:
    orch, mocks = _build()
    mocks["exercise_report_service"].get_assessments_for_student.return_value = Result.ok([])
    await orch.get_recent_exercise_reports("user-1", limit=7)
    mocks["exercise_report_service"].get_assessments_for_student.assert_called_once_with(
        "user-1", limit=7
    )


@pytest.mark.asyncio
async def test_get_recent_activity_reports_delegates() -> None:
    orch, mocks = _build()
    mocks["activity_report_service"].get_history.return_value = Result.ok([])
    await orch.get_recent_activity_reports("user-1", limit=8)
    mocks["activity_report_service"].get_history.assert_called_once_with("user-1", limit=8)


@pytest.mark.asyncio
async def test_get_shared_with_me_items_delegates() -> None:
    orch, mocks = _build()
    mocks["sharing_service"].get_shared_with_me.return_value = Result.ok([])
    await orch.get_shared_with_me_items("user-1", limit=25)
    mocks["sharing_service"].get_shared_with_me.assert_called_once_with(user_uid="user-1", limit=25)


@pytest.mark.asyncio
async def test_get_knowledge_status_delegates() -> None:
    orch, mocks = _build()
    mocks["ps_service"].get_all_user_knowledge_status.return_value = Result.ok([])
    await orch.get_knowledge_status("user-1")
    mocks["ps_service"].get_all_user_knowledge_status.assert_called_once_with("user-1")
