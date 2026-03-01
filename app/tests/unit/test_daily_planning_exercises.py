"""
Unit Tests — Daily Planning: Priority 2.5 Unsubmitted Exercises
===============================================================

Tests for the Priority 2.5 block in DailyPlanningMixin that surfaces
teacher-assigned exercises not yet submitted by the student.

Covers:
1. Happy path — exercises appear in plan with correct ContextualExercise fields
2. Overdue exercise — is_overdue=True, warning added, appears in priorities
3. No exercises — no exercises in plan, no warning
4. Capacity gate — exercises skipped when capacity full
5. Max 3 cap — 5 exercises returned from service, only 3 in plan
6. No due_date — exercise with due_date=None produces days_until_due=None, is_overdue=False
7. Service error — FeedbackRelationshipService returns failure → exercises empty, no crash
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from core.models.context_types import ContextualExercise, DailyWorkPlan
from core.services.user.intelligence.daily_planning import DailyPlanningMixin
from core.utils.result_simplified import Errors, Result

# =============================================================================
# HELPERS
# =============================================================================


def make_context(available_minutes: int = 480, user_uid: str = "user_test") -> object:
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
    mock.get_unsubmitted_exercises = AsyncMock(return_value=Result.ok([]))
    return mock


class MockDailyPlanningService(DailyPlanningMixin):
    """Concrete implementation of DailyPlanningMixin for unit testing."""

    def __init__(
        self,
        context: object,
        tasks: object,
        habits: object,
        goals: object,
        events: object,
        choices: object,
        principles: object,
        ku: object,
        feedback: object,
    ) -> None:
        self.context = context
        self.tasks = tasks
        self.habits = habits
        self.goals = goals
        self.events = events
        self.choices = choices
        self.principles = principles
        self.ku = ku
        self.feedback = feedback
        self.vector_search = None


def build_service(feedback_mock: AsyncMock) -> MockDailyPlanningService:
    """Build a service where only feedback is configured; all others are no-ops."""
    no_op = make_no_op_service()
    ctx = make_context()
    return MockDailyPlanningService(
        context=ctx,
        tasks=no_op,
        habits=no_op,
        goals=no_op,
        events=no_op,
        choices=no_op,
        principles=no_op,
        ku=no_op,
        feedback=feedback_mock,
    )


# =============================================================================
# TEST 1: Happy path
# =============================================================================


@pytest.mark.asyncio
async def test_exercises_appear_in_plan_happy_path() -> None:
    """Exercises returned by service appear in the plan with correct fields."""
    today = date.today()
    due_in_5 = (today + timedelta(days=5)).isoformat()

    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(
        return_value=Result.ok(
            [
                {"uid": "exercise_abc", "title": "Write a haiku", "due_date": due_in_5},
            ]
        )
    )

    service = build_service(feedback)
    result = await service.get_ready_to_work_on_today(respect_capacity=False)

    assert result.is_ok
    plan: DailyWorkPlan = result.value

    assert "exercise_abc" in plan.exercises
    assert len(plan.contextual_exercises) == 1

    cx: ContextualExercise = plan.contextual_exercises[0]
    assert cx.uid == "exercise_abc"
    assert cx.title == "Write a haiku"
    assert cx.due_date == today + timedelta(days=5)
    assert cx.days_until_due == 5
    assert cx.is_overdue is False
    assert cx.is_urgent is False  # 5 days away, not <= 3


# =============================================================================
# TEST 2: Overdue exercise
# =============================================================================


@pytest.mark.asyncio
async def test_overdue_exercise_adds_warning_and_priority() -> None:
    """Overdue exercises set is_overdue=True, add a warning, and surface in priorities."""
    today = date.today()
    overdue_date = (today - timedelta(days=2)).isoformat()

    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(
        return_value=Result.ok(
            [
                {"uid": "exercise_overdue", "title": "Late essay", "due_date": overdue_date},
            ]
        )
    )

    service = build_service(feedback)
    result = await service.get_ready_to_work_on_today(respect_capacity=False)

    assert result.is_ok
    plan: DailyWorkPlan = result.value

    cx: ContextualExercise = plan.contextual_exercises[0]
    assert cx.is_overdue is True
    assert cx.days_until_due == -2

    # Warning should mention overdue
    overdue_warnings = [w for w in plan.warnings if "overdue" in w.lower()]
    assert overdue_warnings, f"Expected overdue warning, got: {plan.warnings}"

    # Priority list should mention the overdue exercise
    overdue_priorities = [p for p in plan.priorities if "overdue exercise" in p.lower()]
    assert overdue_priorities, f"Expected overdue exercise in priorities, got: {plan.priorities}"


# =============================================================================
# TEST 3: No exercises
# =============================================================================


@pytest.mark.asyncio
async def test_no_exercises_no_warning() -> None:
    """When service returns empty list, no exercises appear and no exercise warning is added."""
    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(return_value=Result.ok([]))

    service = build_service(feedback)
    result = await service.get_ready_to_work_on_today(respect_capacity=False)

    assert result.is_ok
    plan: DailyWorkPlan = result.value

    assert plan.exercises == ()
    assert plan.contextual_exercises == ()
    exercise_warnings = [w for w in plan.warnings if "exercise" in w.lower()]
    assert not exercise_warnings


# =============================================================================
# TEST 4: Capacity gate
# =============================================================================


@pytest.mark.asyncio
async def test_exercises_skipped_when_capacity_full() -> None:
    """With respect_capacity=True and a full schedule, exercises are not added."""
    today = date.today()
    due = (today + timedelta(days=1)).isoformat()

    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(
        return_value=Result.ok(
            [{"uid": "exercise_capacity", "title": "Long essay", "due_date": due}]
        )
    )

    no_op = make_no_op_service()
    no_op.get_unsubmitted_exercises = feedback.get_unsubmitted_exercises

    # 3 min capacity — too small for a 60-min exercise
    ctx = make_context(available_minutes=3)
    service = MockDailyPlanningService(
        context=ctx,
        tasks=no_op,
        habits=no_op,
        goals=no_op,
        events=no_op,
        choices=no_op,
        principles=no_op,
        ku=no_op,
        feedback=feedback,
    )

    result = await service.get_ready_to_work_on_today(respect_capacity=True)

    assert result.is_ok
    plan: DailyWorkPlan = result.value
    assert plan.exercises == ()


# =============================================================================
# TEST 5: Max 3 cap
# =============================================================================


@pytest.mark.asyncio
async def test_max_3_exercises_even_if_5_returned() -> None:
    """Only 3 exercises are included in the plan even when 5 are returned."""
    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(
        return_value=Result.ok(
            [{"uid": f"exercise_{i}", "title": f"Exercise {i}", "due_date": None} for i in range(5)]
        )
    )

    service = build_service(feedback)
    result = await service.get_ready_to_work_on_today(respect_capacity=False)

    assert result.is_ok
    plan: DailyWorkPlan = result.value
    assert len(plan.exercises) == 3
    assert len(plan.contextual_exercises) == 3


# =============================================================================
# TEST 6: No due_date
# =============================================================================


@pytest.mark.asyncio
async def test_exercise_without_due_date() -> None:
    """Exercises with no due_date produce days_until_due=None and is_overdue=False."""
    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(
        return_value=Result.ok(
            [{"uid": "exercise_noduedate", "title": "Open-ended task", "due_date": None}]
        )
    )

    service = build_service(feedback)
    result = await service.get_ready_to_work_on_today(respect_capacity=False)

    assert result.is_ok
    plan: DailyWorkPlan = result.value

    assert len(plan.contextual_exercises) == 1
    cx: ContextualExercise = plan.contextual_exercises[0]
    assert cx.due_date is None
    assert cx.days_until_due is None
    assert cx.is_overdue is False
    assert cx.is_urgent is False


# =============================================================================
# TEST 7: Service error
# =============================================================================


@pytest.mark.asyncio
async def test_service_error_produces_empty_exercises() -> None:
    """FeedbackRelationshipService failure leaves exercises empty — no crash."""
    feedback = make_no_op_service()
    feedback.get_unsubmitted_exercises = AsyncMock(
        return_value=Result.fail(Errors.database("query", "Neo4j unreachable"))
    )

    service = build_service(feedback)
    result = await service.get_ready_to_work_on_today(respect_capacity=False)

    assert result.is_ok  # The plan itself should succeed
    plan: DailyWorkPlan = result.value
    assert plan.exercises == ()
    assert plan.contextual_exercises == ()


# =============================================================================
# TEST 8 & 9: Activity report rationale
# =============================================================================


def test_rationale_includes_report_reference_when_present() -> None:
    """Rationale mentions activity report when uid and period are set."""
    ctx = make_context()
    ctx.latest_activity_report_uid = "ku_report_xyz"
    ctx.latest_activity_report_period = "7d"

    service = MockDailyPlanningService(
        context=ctx,
        tasks=make_no_op_service(),
        habits=make_no_op_service(),
        goals=make_no_op_service(),
        events=make_no_op_service(),
        choices=make_no_op_service(),
        principles=make_no_op_service(),
        ku=make_no_op_service(),
        feedback=make_no_op_service(),
    )

    plan = DailyWorkPlan()
    rationale = service._generate_daily_rationale(plan, prioritize_life_path=False)
    assert "7d activity report" in rationale


def test_rationale_excludes_report_reference_when_absent() -> None:
    """Rationale is silent about activity report when uid is None."""
    service = build_service(make_no_op_service())

    plan = DailyWorkPlan()
    rationale = service._generate_daily_rationale(plan, prioritize_life_path=False)
    assert "activity report" not in rationale
