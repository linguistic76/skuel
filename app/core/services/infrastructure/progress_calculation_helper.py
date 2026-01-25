"""
Progress Calculation Helper - Unified Progress Calculations
============================================================

Consolidates duplicate progress calculation logic from:
- GoalsProgressService.calculate_goal_progress_with_context()
- GoalsProgressService.update_goal_from_habit_progress()
- GoalsProgressService._update_goal_from_task_completion()
- GoalsProgressService._update_goal_from_habit_completion()

Provides reusable calculation methods for all Activity Domain progress services.

Version: 1.0.0
Date: 2026-01-19
"""

from __future__ import annotations

from dataclasses import dataclass

# Constants
STREAK_NORMALIZATION_DAYS: int = 30  # Streaks normalized to 30-day window
DEFAULT_PROGRESS_WEIGHTS: dict[str, float] = {
    "task": 0.3,
    "habit": 0.3,
    "knowledge": 0.2,
    "milestone": 0.2,
}


@dataclass(frozen=True)
class HabitContributionResult:
    """
    Result of habit-based progress calculation.

    Attributes:
        contribution: Weighted contribution (0.0-1.0)
        avg_consistency: Average consistency across all habits (0.0-1.0)
        habit_count: Number of habits included in calculation
    """

    contribution: float
    avg_consistency: float
    habit_count: int


@dataclass(frozen=True)
class ProgressContributions:
    """
    Result of multi-factor progress calculation.

    Attributes:
        task_contribution: Progress from completed tasks (0.0-1.0)
        habit_contribution: Progress from habit consistency (0.0-1.0)
        knowledge_completion: Progress from mastered knowledge (0.0-1.0)
        milestone_completion: Progress from completed milestones (0.0-1.0)
        combined_progress: Combined weighted progress (0.0-100.0)
        is_on_track: Whether current progress meets expected progress
    """

    task_contribution: float
    habit_contribution: float
    knowledge_completion: float
    milestone_completion: float
    combined_progress: float
    is_on_track: bool


class ProgressCalculationHelper:
    """
    Unified progress calculation for Goals, Tasks, Habits.

    Following PrerequisiteHelper pattern - static methods,
    frozen dataclass results, pure calculations with no side effects.

    Usage:
        # Calculate habit contribution
        result = ProgressCalculationHelper.calculate_habit_contribution(
            habit_uids=["habit.meditation", "habit.exercise"],
            habit_streaks={"habit.meditation": 15, "habit.exercise": 7},
        )
        print(f"Habit contribution: {result.contribution}")

        # Calculate full progress
        progress = ProgressCalculationHelper.calculate_full_progress(
            goal_tasks=["task.1", "task.2"],
            completed_task_uids={"task.1"},
            supporting_habit_uids=["habit.1"],
            habit_streaks={"habit.1": 10},
            required_knowledge_uids=["ku.python"],
            mastered_knowledge_uids={"ku.python"},
            current_value=50.0,
            target_value=100.0,
            measurement_type="mixed",
            expected_progress=40.0,
        )
    """

    @staticmethod
    def calculate_habit_contribution(
        habit_uids: list[str],
        habit_streaks: dict[str, int],
        habit_weights: dict[str, float] | None = None,
    ) -> HabitContributionResult:
        """
        Calculate habit-based progress contribution.

        Uses streak normalization: consistency = min(streak / 30, 1.0)
        Each habit contributes based on its streak consistency, optionally weighted.

        Args:
            habit_uids: List of supporting habit UIDs
            habit_streaks: Mapping of habit UID to current streak count
            habit_weights: Optional custom weights per habit (default: equal weights)

        Returns:
            HabitContributionResult with contribution, avg_consistency, habit_count

        Example:
            result = ProgressCalculationHelper.calculate_habit_contribution(
                habit_uids=["habit.meditation", "habit.exercise"],
                habit_streaks={"habit.meditation": 30, "habit.exercise": 15},
            )
            # result.contribution = 0.75 (avg of 1.0 and 0.5)
        """
        if not habit_uids:
            return HabitContributionResult(
                contribution=0.0,
                avg_consistency=0.0,
                habit_count=0,
            )

        total_weight = 0.0
        weighted_consistency = 0.0

        for habit_uid in habit_uids:
            # Get weight (default 1.0 for equal weighting)
            weight = habit_weights.get(habit_uid, 1.0) if habit_weights else 1.0

            # Get streak and normalize to consistency (0.0-1.0)
            streak = habit_streaks.get(habit_uid, 0)
            consistency = min(streak / float(STREAK_NORMALIZATION_DAYS), 1.0)

            weighted_consistency += consistency * weight
            total_weight += weight

        if total_weight == 0:
            return HabitContributionResult(
                contribution=0.0,
                avg_consistency=0.0,
                habit_count=len(habit_uids),
            )

        contribution = weighted_consistency / total_weight

        return HabitContributionResult(
            contribution=contribution,
            avg_consistency=contribution,  # Same when equal weights
            habit_count=len(habit_uids),
        )

    @staticmethod
    def calculate_task_contribution(
        task_uids: list[str],
        completed_task_uids: set[str],
    ) -> float:
        """
        Calculate task-based progress contribution.

        Args:
            task_uids: List of task UIDs associated with the goal
            completed_task_uids: Set of completed task UIDs

        Returns:
            Completion ratio (0.0-1.0)

        Example:
            contribution = ProgressCalculationHelper.calculate_task_contribution(
                task_uids=["task.1", "task.2", "task.3"],
                completed_task_uids={"task.1", "task.2"},
            )
            # contribution = 0.667
        """
        if not task_uids:
            return 0.0

        completed_count = sum(1 for uid in task_uids if uid in completed_task_uids)
        return completed_count / len(task_uids)

    @staticmethod
    def calculate_knowledge_completion(
        required_knowledge_uids: list[str],
        mastered_knowledge_uids: set[str],
    ) -> float:
        """
        Calculate knowledge-based progress contribution.

        Args:
            required_knowledge_uids: List of required knowledge UIDs
            mastered_knowledge_uids: Set of mastered knowledge UIDs

        Returns:
            Completion ratio (0.0-1.0), or 1.0 if no knowledge required

        Example:
            completion = ProgressCalculationHelper.calculate_knowledge_completion(
                required_knowledge_uids=["ku.python", "ku.testing"],
                mastered_knowledge_uids={"ku.python"},
            )
            # completion = 0.5
        """
        if not required_knowledge_uids:
            return 1.0  # No knowledge required = 100% complete

        required_set = set(required_knowledge_uids)
        mastered_count = len(required_set.intersection(mastered_knowledge_uids))
        return mastered_count / len(required_knowledge_uids)

    @staticmethod
    def calculate_milestone_completion(
        current_value: float,
        target_value: float,
    ) -> float:
        """
        Calculate milestone-based progress contribution.

        Args:
            current_value: Current progress value
            target_value: Target progress value

        Returns:
            Completion ratio (0.0-1.0)

        Example:
            completion = ProgressCalculationHelper.calculate_milestone_completion(
                current_value=75.0,
                target_value=100.0,
            )
            # completion = 0.75
        """
        if target_value <= 0:
            return 0.0

        return min(current_value / target_value, 1.0)

    @staticmethod
    def calculate_combined_progress(
        task_contribution: float,
        habit_contribution: float,
        knowledge_completion: float,
        milestone_completion: float,
        measurement_type: str,
        weights: dict[str, float] | None = None,
    ) -> float:
        """
        Calculate combined progress based on measurement type.

        Args:
            task_contribution: Task-based progress (0.0-1.0)
            habit_contribution: Habit-based progress (0.0-1.0)
            knowledge_completion: Knowledge-based progress (0.0-1.0)
            milestone_completion: Milestone-based progress (0.0-1.0)
            measurement_type: One of "milestone", "habit_based", "task_based", "mixed"
            weights: Optional custom weights for mixed calculation

        Returns:
            Combined progress percentage (0.0-100.0)

        Example:
            progress = ProgressCalculationHelper.calculate_combined_progress(
                task_contribution=0.5,
                habit_contribution=0.8,
                knowledge_completion=1.0,
                milestone_completion=0.3,
                measurement_type="mixed",
            )
            # Uses default weights: 0.3*0.5 + 0.3*0.8 + 0.2*1.0 + 0.2*0.3 = 0.65 * 100 = 65.0
        """
        if measurement_type == "milestone":
            return milestone_completion * 100

        if measurement_type == "habit_based":
            return habit_contribution * 100

        if measurement_type == "task_based":
            return task_contribution * 100

        # Mixed calculation with weights
        w = weights or DEFAULT_PROGRESS_WEIGHTS
        combined = (
            task_contribution * w.get("task", 0.3)
            + habit_contribution * w.get("habit", 0.3)
            + knowledge_completion * w.get("knowledge", 0.2)
            + milestone_completion * w.get("milestone", 0.2)
        )
        return combined * 100

    @staticmethod
    def calculate_full_progress(
        goal_tasks: list[str],
        completed_task_uids: set[str],
        supporting_habit_uids: list[str],
        habit_streaks: dict[str, int],
        required_knowledge_uids: list[str],
        mastered_knowledge_uids: set[str],
        current_value: float,
        target_value: float,
        measurement_type: str,
        expected_progress: float,
        habit_weights: dict[str, float] | None = None,
        progress_weights: dict[str, float] | None = None,
    ) -> ProgressContributions:
        """
        Calculate full progress with all contribution factors.

        Convenience method that combines all individual calculations.

        Args:
            goal_tasks: Task UIDs associated with goal
            completed_task_uids: Set of completed task UIDs
            supporting_habit_uids: Habit UIDs supporting the goal
            habit_streaks: Mapping of habit UID to streak count
            required_knowledge_uids: Required knowledge UIDs
            mastered_knowledge_uids: Set of mastered knowledge UIDs
            current_value: Current milestone value
            target_value: Target milestone value
            measurement_type: "milestone", "habit_based", "task_based", or "mixed"
            expected_progress: Expected progress percentage for is_on_track
            habit_weights: Optional weights per habit
            progress_weights: Optional weights for combined calculation

        Returns:
            ProgressContributions with all factors and combined progress
        """
        task_contribution = ProgressCalculationHelper.calculate_task_contribution(
            task_uids=goal_tasks,
            completed_task_uids=completed_task_uids,
        )

        habit_result = ProgressCalculationHelper.calculate_habit_contribution(
            habit_uids=supporting_habit_uids,
            habit_streaks=habit_streaks,
            habit_weights=habit_weights,
        )

        knowledge_completion = ProgressCalculationHelper.calculate_knowledge_completion(
            required_knowledge_uids=required_knowledge_uids,
            mastered_knowledge_uids=mastered_knowledge_uids,
        )

        milestone_completion = ProgressCalculationHelper.calculate_milestone_completion(
            current_value=current_value,
            target_value=target_value,
        )

        combined_progress = ProgressCalculationHelper.calculate_combined_progress(
            task_contribution=task_contribution,
            habit_contribution=habit_result.contribution,
            knowledge_completion=knowledge_completion,
            milestone_completion=milestone_completion,
            measurement_type=measurement_type,
            weights=progress_weights,
        )

        # Normalize to 0-100 range
        combined_progress = ProgressCalculationHelper.normalize_progress(combined_progress)

        return ProgressContributions(
            task_contribution=task_contribution,
            habit_contribution=habit_result.contribution,
            knowledge_completion=knowledge_completion,
            milestone_completion=milestone_completion,
            combined_progress=combined_progress,
            is_on_track=combined_progress >= expected_progress,
        )

    @staticmethod
    def check_achievement_threshold(
        old_progress: float,
        new_progress: float,
        threshold: float = 100.0,
    ) -> bool:
        """
        Check if progress just crossed the achievement threshold.

        Args:
            old_progress: Previous progress percentage
            new_progress: New progress percentage
            threshold: Achievement threshold (default 100.0)

        Returns:
            True if threshold was just crossed (was below, now at or above)

        Example:
            achieved = ProgressCalculationHelper.check_achievement_threshold(
                old_progress=95.0,
                new_progress=100.0,
            )
            # achieved = True
        """
        return old_progress < threshold <= new_progress

    @staticmethod
    def normalize_progress(progress: float) -> float:
        """
        Normalize progress to 0-100 range.

        Args:
            progress: Raw progress value

        Returns:
            Progress clamped to 0.0-100.0 range
        """
        return max(0.0, min(100.0, progress))
