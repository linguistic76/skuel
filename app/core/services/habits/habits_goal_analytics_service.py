"""
Habits Goal Analytics Service
==============================

Cross-domain analytics bridging Habits -> Goals.

Extracts goal system health, velocity, and impact analysis logic
from habits_ui.py route handlers into testable service methods.

Methods:
- get_system_health: Diagnose a goal's habit system health
- get_velocity: Track habit completion velocity toward a goal
- get_impact_analysis: Analyze habit impact on goal achievement
"""

from dataclasses import dataclass
from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.habits.goal_analytics")


@dataclass(frozen=True)
class GoalSystemHealth:
    """System health diagnostics for a goal's supporting habits."""

    goal_title: str
    system_strength: float
    diagnosis: str
    warnings: list[str]
    recommendations: list[str]
    habit_breakdown: list[dict[str, Any]]
    system_exists: bool


@dataclass(frozen=True)
class GoalVelocity:
    """Velocity tracking for habit completion toward a goal."""

    goal_title: str
    current_velocity: float
    trend: str  # "increasing" | "decreasing" | "stable"
    velocity_trend: list[dict[str, Any]]
    weighted_breakdown: dict[str, int]
    total_weighted_completions: int


@dataclass(frozen=True)
class GoalImpactAnalysis:
    """Impact analysis of habits on goal achievement."""

    goal_title: str
    achievement_probability: float
    overall_impact: float
    habits: list[dict[str, Any]]


class HabitsGoalAnalyticsService:
    """
    Cross-domain analytics bridging Habits -> Goals.

    Lives in habits package because primary data source is habit
    completion/consistency data. Requires goals_service to be
    post-wired after construction.
    """

    def __init__(
        self,
        habits_service: Any,
        goals_service: Any = None,
    ) -> None:
        self.habits_service = habits_service
        self.goals_service = goals_service

    async def _fetch_goal_with_habits(self, goal_uid: str) -> Result[tuple[Any, list[Any]]]:
        """Fetch a goal and its linked habits. DRYs the 3 analytics methods."""
        from core.models.goal.goal import Goal
        from core.models.habit.habit import Habit

        if not self.goals_service:
            return Result.fail({"type": "business", "message": "Goals service not available"})

        goal_result = await self.goals_service.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal: Goal = goal_result.value
        if goal is None:
            from core.utils.result_simplified import Errors

            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        # Fetch linked habit UIDs
        habit_uids_result = await self.goals_service.get_goal_habits(goal.uid)
        habit_uids: list[str] = habit_uids_result.value if habit_uids_result.is_ok else []

        # Fetch each habit
        habits: list[Habit] = []
        for habit_uid in habit_uids:
            habit_result = await self.habits_service.get_habit(habit_uid)
            if habit_result.is_error:
                logger.warning(f"Failed to fetch habit {habit_uid}: {habit_result.error}")
                continue
            habits.append(habit_result.value)

        return Result.ok((goal, habits))

    async def get_system_health(self, goal_uid: str) -> Result[GoalSystemHealth]:
        """Diagnose a goal's habit system health."""
        fetch_result = await self._fetch_goal_with_habits(goal_uid)
        if fetch_result.is_error:
            return Result.fail(fetch_result.expect_error())

        goal, habits = fetch_result.value

        # Build success rate map and habit breakdown
        habit_success_rates: dict[str, float] = {}
        habit_breakdown: list[dict[str, Any]] = []

        for habit in habits:
            habit_success_rates[habit.uid] = habit.success_rate
            habit_breakdown.append(
                {
                    "name": habit.title,
                    "essentiality": "supporting",
                    "consistency": habit.calculate_consistency_score(),
                    "impact": habit.predict_goal_impact(),
                }
            )

        # Get diagnosis from enriched model method
        diagnosis = goal.diagnose_system_health(habit_success_rates)

        return Result.ok(
            GoalSystemHealth(
                goal_title=goal.title,
                system_strength=diagnosis["system_strength"],
                diagnosis=diagnosis["diagnosis"],
                warnings=diagnosis["warnings"],
                recommendations=diagnosis["recommendations"],
                habit_breakdown=habit_breakdown,
                system_exists=diagnosis["system_exists"],
            )
        )

    async def get_velocity(self, goal_uid: str) -> Result[GoalVelocity]:
        """Track habit completion velocity toward a goal."""
        fetch_result = await self._fetch_goal_with_habits(goal_uid)
        if fetch_result.is_error:
            return Result.fail(fetch_result.expect_error())

        goal, habits = fetch_result.value

        # Build completion counts and weighted breakdown
        habit_completion_counts: dict[str, int] = {}
        weighted_breakdown: dict[str, int] = {
            "essential": 0,
            "critical": 0,
            "supporting": 0,
            "optional": 0,
        }

        for habit in habits:
            habit_completion_counts[habit.uid] = habit.total_completions
            weighted_breakdown["supporting"] += habit.total_completions

        # Calculate current velocity
        current_velocity = goal.calculate_habit_velocity(habit_completion_counts)
        total_weighted_completions = sum(weighted_breakdown.values())

        # Generate simplified velocity trend (last 4 weeks estimate)
        velocity_trend: list[dict[str, Any]] = []
        if current_velocity > 0:
            for i in range(1, 5):
                week_velocity = (current_velocity / 4) * i
                velocity_trend.append({"week": f"Week {i}", "velocity": round(week_velocity, 1)})
        else:
            velocity_trend.extend([{"week": f"Week {i}", "velocity": 0.0} for i in range(1, 5)])

        # Determine trend
        last_velocity: float = float(velocity_trend[-1]["velocity"]) if velocity_trend else 0.0
        first_velocity: float = float(velocity_trend[0]["velocity"]) if velocity_trend else 0.0
        if len(velocity_trend) > 1 and last_velocity > 0:
            if last_velocity > first_velocity:
                trend = "increasing"
            elif last_velocity < first_velocity:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return Result.ok(
            GoalVelocity(
                goal_title=goal.title,
                current_velocity=current_velocity,
                trend=trend,
                velocity_trend=velocity_trend,
                weighted_breakdown=weighted_breakdown,
                total_weighted_completions=int(total_weighted_completions),
            )
        )

    async def get_impact_analysis(self, goal_uid: str) -> Result[GoalImpactAnalysis]:
        """Analyze habit impact on goal achievement."""
        from operator import itemgetter

        fetch_result = await self._fetch_goal_with_habits(goal_uid)
        if fetch_result.is_error:
            return Result.fail(fetch_result.expect_error())

        goal, habits = fetch_result.value

        # Build habit data
        habit_completion_counts: dict[str, int] = {}
        habit_success_rates: dict[str, float] = {}
        habit_impacts: list[dict[str, Any]] = []

        for habit in habits:
            habit_completion_counts[habit.uid] = habit.total_completions
            habit_success_rates[habit.uid] = habit.success_rate
            habit_impacts.append(
                {
                    "name": habit.title,
                    "essentiality": "supporting",
                    "impact_score": habit.predict_goal_impact(),
                    "consistency": habit.calculate_consistency_score(),
                }
            )

        # Sort by impact score (highest first)
        habit_impacts.sort(key=itemgetter("impact_score"), reverse=True)

        # Calculate achievement probability: 60% system strength + 40% velocity
        system_strength = goal.calculate_system_strength(habit_success_rates=habit_success_rates)
        velocity = goal.calculate_habit_velocity(habit_completion_counts)
        normalized_velocity = min(velocity / 150.0, 1.0)
        achievement_probability = (system_strength * 0.6) + (normalized_velocity * 0.4)

        # Overall impact (average of all habit impacts)
        overall_impact = (
            sum(h["impact_score"] for h in habit_impacts) / len(habit_impacts)
            if habit_impacts
            else 0.0
        )

        return Result.ok(
            GoalImpactAnalysis(
                goal_title=goal.title,
                achievement_probability=achievement_probability,
                overall_impact=overall_impact,
                habits=habit_impacts,
            )
        )
