"""
Unit Tests — Daily Planning: Domain Health Warnings (FilteredContextProvider)
=============================================================================

Tests for _generate_domain_health_warnings() and _query_domain_stats() in
DailyPlanningMixin. These methods consume self.filtered_providers — the
FilteredContextProvider dict wired at bootstrap — to surface aggregate
domain stats as actionable warnings in the daily plan.

All stats dicts follow the BaseStats contract: guaranteed ``total`` and
``active`` keys, plus domain-specific extras.

Covers:
1. Large task backlog → warning
2. No active goals → warning
3. No habits tracked → warning
4. Healthy domains → no domain-health warnings
5. No providers wired → no crash, no warnings
6. Provider failure → graceful, no crash
7. Protocol conformance (runtime_checkable)
8. Events overload → warning
9. Pending choices decision fatigue → warning
10. No core principles → warning
11. Goals without habits cross-domain → warning
12. Tasks without goals cross-domain → warning
"""

from unittest.mock import AsyncMock

import pytest

from core.ports.filtered_context_protocols import FilteredContextProvider
from core.services.user.intelligence.daily_planning import DailyPlanningMixin
from core.services.user.intelligence.temporal_momentum import TemporalMomentumMixin
from core.utils.result_simplified import Errors, Result

# =============================================================================
# HELPERS
# =============================================================================


def make_context(
    available_minutes: int = 480,
    user_uid: str = "user_test",
) -> object:
    """Minimal UserContext stand-in for DailyPlanningMixin."""

    class _Context:
        pass

    ctx = _Context()
    ctx.user_uid = user_uid
    ctx.available_minutes_daily = available_minutes
    ctx.daily_habits = []
    ctx.primary_goal_focus = None
    ctx.learning_goals = []
    ctx.life_path_uid = None
    ctx.estimated_time_to_mastery = {}
    ctx.knowledge_mastery = {}
    ctx.current_workload_score = 0.5
    ctx.current_energy_level = "moderate"
    ctx.latest_activity_report_uid = None
    ctx.latest_activity_report_period = None
    ctx.entities_rich = {}
    ctx.unsubmitted_exercises = []
    ctx.pending_revised_exercises = []
    ctx.zpd_assessment = None
    return ctx


def make_no_op_service() -> AsyncMock:
    """Service that returns empty success (no items)."""
    mock = AsyncMock()
    mock.get_at_risk_habits_for_user = AsyncMock(return_value=Result.ok([]))
    mock.get_upcoming_events_for_user = AsyncMock(return_value=Result.ok([]))
    mock.get_actionable_tasks_for_user = AsyncMock(return_value=Result.ok([]))
    mock.get_ready_to_learn_for_user = AsyncMock(return_value=Result.ok([]))
    mock.get_advancing_goals_for_user = AsyncMock(return_value=Result.ok([]))
    mock.get_pending_decisions_for_user = AsyncMock(return_value=Result.ok([]))
    mock.get_aligned_principles_for_user = AsyncMock(return_value=Result.ok([]))
    return mock


def make_mock_provider(stats: dict[str, int | float]) -> AsyncMock:
    """Create a mock FilteredContextProvider returning given stats."""
    mock = AsyncMock()
    mock.get_filtered_context = AsyncMock(return_value=Result.ok({"entities": [], "stats": stats}))
    return mock


class MockDailyPlanningService(TemporalMomentumMixin, DailyPlanningMixin):
    """Concrete implementation of DailyPlanningMixin for unit testing."""

    def __init__(
        self,
        context: object,
        filtered_providers: dict[str, object] | None = None,
    ) -> None:
        self.context = context
        no_op = make_no_op_service()
        self.tasks = no_op
        self.habits = no_op
        self.goals = no_op
        self.events = no_op
        self.choices = no_op
        self.principles = no_op
        self.lesson = no_op
        self.report = no_op
        self.vector_search = None
        self.filtered_providers = filtered_providers or {}


def build_service(
    filtered_providers: dict[str, object] | None = None,
) -> MockDailyPlanningService:
    """Build a service with given filtered_providers; all domain services are no-ops."""
    ctx = make_context()
    return MockDailyPlanningService(context=ctx, filtered_providers=filtered_providers)


# =============================================================================
# TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_large_task_backlog_warning():
    """Tasks with active count > 30 triggers a backlog warning."""
    providers = {
        "tasks": make_mock_provider({"total": 50, "active": 45, "completed": 5, "overdue": 3}),
        "goals": make_mock_provider({"total": 2, "active": 2, "completed": 0}),
        "habits": make_mock_provider({"total": 3, "active": 3}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("active tasks" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_no_active_goals_warning():
    """Zero active goals triggers a direction warning."""
    providers = {
        "tasks": make_mock_provider({"total": 5, "active": 3, "completed": 2}),
        "goals": make_mock_provider({"total": 3, "active": 0, "completed": 3}),
        "habits": make_mock_provider({"total": 3, "active": 3}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("No active goals" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_no_habits_warning():
    """Zero tracked habits triggers a consistency warning."""
    providers = {
        "tasks": make_mock_provider({"total": 5, "active": 3, "completed": 2}),
        "goals": make_mock_provider({"total": 2, "active": 2}),
        "habits": make_mock_provider({"total": 0, "active": 0}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("No habits tracked" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_healthy_domains_no_warnings():
    """Healthy domain stats produce no domain-health warnings."""
    providers = {
        "tasks": make_mock_provider({"total": 10, "active": 7, "completed": 3}),
        "goals": make_mock_provider({"total": 3, "active": 2}),
        "habits": make_mock_provider({"total": 5, "active": 4}),
        "events": make_mock_provider({"total": 3, "active": 2, "today": 2}),
        "choices": make_mock_provider({"total": 2, "active": 1, "pending": 1}),
        "principles": make_mock_provider({"total": 5, "active": 5, "core": 2}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    domain_health_phrases = [
        "active tasks",
        "No active goals",
        "No habits tracked",
        "events today",
        "pending choices",
        "No core principles",
        "but no habits",
        "but no goals",
    ]
    for phrase in domain_health_phrases:
        assert not any(phrase in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_no_providers_no_crash():
    """Empty filtered_providers dict completes without error."""
    svc = build_service(filtered_providers={})
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    domain_health_phrases = ["active tasks", "No active goals", "No habits tracked"]
    for phrase in domain_health_phrases:
        assert not any(phrase in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_provider_failure_graceful():
    """A provider that returns Result.fail() doesn't crash the plan."""
    failing_provider = AsyncMock()
    failing_provider.get_filtered_context = AsyncMock(
        return_value=Result.fail(Errors.database("query", "connection lost"))
    )
    providers = {
        "tasks": failing_provider,
        "goals": failing_provider,
        "habits": failing_provider,
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    # No domain-health warnings when all providers fail
    domain_health_phrases = ["active tasks", "No active goals", "No habits tracked"]
    for phrase in domain_health_phrases:
        assert not any(phrase in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_events_overload_warning():
    """5+ events today triggers a schedule overload warning."""
    providers = {
        "tasks": make_mock_provider({"total": 5, "active": 3, "completed": 2}),
        "goals": make_mock_provider({"total": 2, "active": 2}),
        "habits": make_mock_provider({"total": 3, "active": 3}),
        "events": make_mock_provider({"total": 10, "active": 8, "scheduled": 8, "today": 6}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("events today" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_pending_choices_decision_fatigue():
    """5+ pending choices triggers a decision fatigue warning."""
    providers = {
        "tasks": make_mock_provider({"total": 5, "active": 3, "completed": 2}),
        "goals": make_mock_provider({"total": 2, "active": 2}),
        "habits": make_mock_provider({"total": 3, "active": 3}),
        "choices": make_mock_provider({"total": 7, "active": 5, "pending": 5, "decided": 2}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("pending choices" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_no_core_principles_warning():
    """Principles exist but none are core triggers a values warning."""
    providers = {
        "tasks": make_mock_provider({"total": 5, "active": 3, "completed": 2}),
        "goals": make_mock_provider({"total": 2, "active": 2}),
        "habits": make_mock_provider({"total": 3, "active": 3}),
        "principles": make_mock_provider({"total": 5, "active": 5, "core": 0}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("No core principles" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_goals_without_habits_cross_domain():
    """Many active goals with zero habits triggers a cross-domain warning."""
    providers = {
        "tasks": make_mock_provider({"total": 5, "active": 3, "completed": 2}),
        "goals": make_mock_provider({"total": 12, "active": 12}),
        "habits": make_mock_provider({"total": 0, "active": 0}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("but no habits" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_tasks_without_goals_cross_domain():
    """Many active tasks with zero goals triggers a cross-domain warning."""
    providers = {
        "tasks": make_mock_provider({"total": 25, "active": 25, "completed": 0}),
        "goals": make_mock_provider({"total": 3, "active": 0, "completed": 3}),
        "habits": make_mock_provider({"total": 3, "active": 3}),
    }
    svc = build_service(filtered_providers=providers)
    result = await svc.get_ready_to_work_on_today()

    assert not result.is_error
    plan = result.value
    assert any("but no goals" in w for w in plan.warnings)


def test_protocol_conformance():
    """Mock with get_filtered_context satisfies FilteredContextProvider protocol."""
    mock = make_mock_provider({"total": 1, "active": 1})
    assert isinstance(mock, FilteredContextProvider)
