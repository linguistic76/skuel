"""
Schedule Intelligence Mixin
============================

Method 8 of UserContextIntelligence:
- get_schedule_aware_recommendations() - Recommendations considering schedule and capacity

Schedule-aware recommendations take into account:
- Current events and scheduled activities
- Energy levels and preferred times
- Available time slots
- Workload and capacity limits
- Conflict detection and avoidance
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from core.models.context_types import ScheduleAwareRecommendation
from core.models.enums.entity_enums import EntityType

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


class ScheduleIntelligenceMixin:
    """
    Mixin providing schedule-aware recommendation methods.

    Requires self.context (UserContext).
    """

    context: UserContext

    # =========================================================================
    # METHOD 8: Schedule-Aware Recommendations
    # =========================================================================

    async def get_schedule_aware_recommendations(
        self,
        max_recommendations: int = 5,
        time_horizon_hours: int = 8,
        respect_energy: bool = True,
    ) -> list[ScheduleAwareRecommendation]:
        """
        Get recommendations that consider the user's schedule and capacity.

        This method synthesizes:
        - Current events and scheduled activities (Calendar domain)
        - Available time slots and capacity
        - Energy levels and preferred times
        - Priority and urgency across all domains
        - Conflict detection and avoidance

        **Synthesis Algorithm:**
        1. Calculate available time slots from events
        2. Assess current energy and capacity
        3. Gather candidates from all domains (tasks, habits, learning, goals)
        4. Score each candidate by schedule fit, energy match, and priority
        5. Filter and rank by overall score
        6. Generate actionable recommendations

        Args:
            max_recommendations: Maximum number of recommendations to return
            time_horizon_hours: How far ahead to look (default 8 hours)
            respect_energy: Whether to consider current energy level

        Returns:
            List of ScheduleAwareRecommendation sorted by overall score
        """
        recommendations: list[ScheduleAwareRecommendation] = []

        # Calculate available capacity
        available_minutes = self._calculate_available_minutes(time_horizon_hours)
        current_energy = self._assess_current_energy()
        current_time_slot = self._get_current_time_slot()

        # Check if user is at capacity (recommend rest)
        if self.context.current_workload_score >= 0.9:
            recommendations.append(
                self._create_rest_recommendation(
                    rationale="Workload is at 90%+ capacity. Consider taking a break."
                )
            )

        # Gather candidates from each domain and score them
        task_recs = await self._get_task_schedule_recommendations(
            available_minutes, current_energy, current_time_slot, respect_energy
        )
        habit_recs = await self._get_habit_schedule_recommendations(
            available_minutes, current_energy, current_time_slot, respect_energy
        )
        learning_recs = await self._get_learning_schedule_recommendations(
            available_minutes, current_energy, current_time_slot, respect_energy
        )
        goal_recs = await self._get_goal_schedule_recommendations(
            available_minutes, current_energy, current_time_slot, respect_energy
        )

        # Combine all recommendations
        all_recs = task_recs + habit_recs + learning_recs + goal_recs
        recommendations.extend(all_recs)

        # Sort by overall score (descending)
        from core.utils.sort_functions import get_schedule_recommendation_score

        recommendations.sort(key=get_schedule_recommendation_score, reverse=True)

        return recommendations[:max_recommendations]

    def _calculate_available_minutes(self, time_horizon_hours: int) -> int:
        """Calculate available minutes based on events and capacity."""
        total_minutes = time_horizon_hours * 60

        # Subtract time for today's events
        event_count = len(self.context.today_event_uids)
        # Assume average event is 60 minutes
        event_minutes = event_count * 60

        # Account for existing workload
        committed_minutes = int(total_minutes * self.context.current_workload_score)

        available = total_minutes - event_minutes - committed_minutes
        return max(0, min(available, self.context.available_minutes_daily))

    def _assess_current_energy(self) -> str:
        """Assess current energy level as a category."""
        if self.context.current_energy_level:
            return self.context.current_energy_level.value
        # Default based on time of day and workload
        if self.context.current_workload_score > 0.7:
            return "low"
        return "medium"

    def _get_current_time_slot(self) -> str:
        """Get current time slot based on preferred_time or actual time."""
        if self.context.preferred_time:
            return self.context.preferred_time.value

        hour = datetime.now().hour

        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def _create_rest_recommendation(self, rationale: str) -> ScheduleAwareRecommendation:
        """Create a rest recommendation when capacity is exceeded."""
        return ScheduleAwareRecommendation(
            uid="rest",
            entity_type="meta",
            recommendation_type="rest",
            title="Take a Break",
            rationale=rationale,
            suggested_time_slot="now",
            estimated_duration_minutes=15,
            fits_available_time=True,
            schedule_fit_score=1.0,
            energy_match_score=1.0,
            priority_score=0.9,
            overall_score=0.95,
        )

    async def _get_task_schedule_recommendations(
        self,
        available_minutes: int,
        current_energy: str,
        current_time_slot: str,
        respect_energy: bool,
    ) -> list[ScheduleAwareRecommendation]:
        """Get schedule-aware task recommendations."""
        recommendations = []

        # Prioritize overdue tasks
        for task_uid in self.context.overdue_task_uids[:3]:
            score = self._calculate_schedule_score(
                entity_type="task",
                priority=1.0,  # Overdue = highest priority
                energy_required="medium",
                current_energy=current_energy,
                time_slot=current_time_slot,
                respect_energy=respect_energy,
            )
            recommendations.append(
                ScheduleAwareRecommendation(
                    uid=task_uid,
                    entity_type="task",
                    recommendation_type="task",
                    title=f"Overdue Task: {task_uid}",
                    rationale="This task is overdue and needs attention",
                    suggested_time_slot="now",
                    estimated_duration_minutes=30,
                    fits_available_time=available_minutes >= 30,
                    schedule_fit_score=score["schedule_fit"],
                    energy_match_score=score["energy_match"],
                    priority_score=score["priority"],
                    overall_score=score["overall"],
                    deadline="overdue",
                    blocks_other_work=task_uid in self.context.blocked_task_uids,
                )
            )

        # Add today's tasks
        for task_uid in self.context.today_task_uids[:3]:
            if task_uid not in self.context.overdue_task_uids:
                priority = self.context.task_priorities.get(task_uid, 0.5)
                score = self._calculate_schedule_score(
                    entity_type="task",
                    priority=priority,
                    energy_required="medium",
                    current_energy=current_energy,
                    time_slot=current_time_slot,
                    respect_energy=respect_energy,
                )
                recommendations.append(
                    ScheduleAwareRecommendation(
                        uid=task_uid,
                        entity_type="task",
                        recommendation_type="task",
                        title=f"Today's Task: {task_uid}",
                        rationale="Scheduled for today",
                        suggested_time_slot=current_time_slot,
                        estimated_duration_minutes=30,
                        fits_available_time=available_minutes >= 30,
                        schedule_fit_score=score["schedule_fit"],
                        energy_match_score=score["energy_match"],
                        priority_score=score["priority"],
                        overall_score=score["overall"],
                    )
                )

        return recommendations

    async def _get_habit_schedule_recommendations(
        self,
        available_minutes: int,
        current_energy: str,
        current_time_slot: str,
        respect_energy: bool,
    ) -> list[ScheduleAwareRecommendation]:
        """Get schedule-aware habit recommendations."""
        recommendations = []

        # Prioritize at-risk habits (streak protection)
        for habit_uid in self.context.at_risk_habits[:3]:
            streak = self.context.habit_streaks.get(habit_uid, 0)
            # Higher streak = higher priority to maintain
            priority = min(1.0, 0.5 + (streak * 0.05))

            score = self._calculate_schedule_score(
                entity_type="habit",
                priority=priority,
                energy_required="low",  # Habits are usually easier
                current_energy=current_energy,
                time_slot=current_time_slot,
                respect_energy=respect_energy,
            )
            recommendations.append(
                ScheduleAwareRecommendation(
                    uid=habit_uid,
                    entity_type="habit",
                    recommendation_type="habit",
                    title=f"At-Risk Habit: {habit_uid}",
                    rationale=f"Protect your {streak}-day streak!",
                    suggested_time_slot="now",
                    estimated_duration_minutes=15,
                    fits_available_time=available_minutes >= 15,
                    schedule_fit_score=score["schedule_fit"],
                    energy_match_score=score["energy_match"],
                    priority_score=score["priority"],
                    overall_score=score["overall"],
                    streak_at_risk=True,
                )
            )

        # Add daily habits
        for habit_uid in self.context.daily_habits[:3]:
            if habit_uid not in self.context.at_risk_habits:
                streak = self.context.habit_streaks.get(habit_uid, 0)
                priority = min(1.0, 0.3 + (streak * 0.03))

                score = self._calculate_schedule_score(
                    entity_type="habit",
                    priority=priority,
                    energy_required="low",
                    current_energy=current_energy,
                    time_slot=current_time_slot,
                    respect_energy=respect_energy,
                )
                recommendations.append(
                    ScheduleAwareRecommendation(
                        uid=habit_uid,
                        entity_type="habit",
                        recommendation_type="habit",
                        title=f"Daily Habit: {habit_uid}",
                        rationale=f"Maintain your {streak}-day streak",
                        suggested_time_slot=current_time_slot,
                        estimated_duration_minutes=15,
                        fits_available_time=available_minutes >= 15,
                        schedule_fit_score=score["schedule_fit"],
                        energy_match_score=score["energy_match"],
                        priority_score=score["priority"],
                        overall_score=score["overall"],
                    )
                )

        return recommendations

    async def _get_learning_schedule_recommendations(
        self,
        available_minutes: int,
        current_energy: str,
        current_time_slot: str,
        respect_energy: bool,
    ) -> list[ScheduleAwareRecommendation]:
        """Get schedule-aware learning recommendations."""
        recommendations = []

        # Get ready-to-learn knowledge units
        ready_to_learn = self.context.get_ready_to_learn()[:3]

        for ku_uid in ready_to_learn:
            # Learning requires more energy
            energy_required = "high" if current_time_slot in ["morning", "afternoon"] else "medium"

            # Higher priority if aligned with life path
            is_life_path = ku_uid in self.context.life_path_milestones
            priority = 0.7 if is_life_path else 0.5

            score = self._calculate_schedule_score(
                entity_type="knowledge",
                priority=priority,
                energy_required=energy_required,
                current_energy=current_energy,
                time_slot=current_time_slot,
                respect_energy=respect_energy,
            )
            recommendations.append(
                ScheduleAwareRecommendation(
                    uid=ku_uid,
                    entity_type="knowledge",
                    recommendation_type="learn",
                    title=f"Learn: {ku_uid}",
                    rationale="Prerequisites met, ready to learn",
                    suggested_time_slot="morning" if current_energy != "low" else "later",
                    estimated_duration_minutes=45,
                    fits_available_time=available_minutes >= 45,
                    schedule_fit_score=score["schedule_fit"],
                    energy_match_score=score["energy_match"],
                    priority_score=score["priority"],
                    overall_score=score["overall"],
                    life_path_aligned=is_life_path,
                    preparation_needed=("Review prerequisites",) if not is_life_path else (),
                )
            )

        return recommendations

    async def _get_goal_schedule_recommendations(
        self,
        available_minutes: int,
        current_energy: str,
        current_time_slot: str,
        respect_energy: bool,
    ) -> list[ScheduleAwareRecommendation]:
        """Get schedule-aware goal advancement recommendations."""
        recommendations = []

        # Focus on primary goal
        if self.context.primary_goal_focus:
            goal_uid = self.context.primary_goal_focus
            progress = self.context.goal_progress.get(goal_uid, 0)

            # Lower progress = higher priority
            priority = 1.0 - (progress * 0.5)

            score = self._calculate_schedule_score(
                entity_type="goal",
                priority=priority,
                energy_required="medium",
                current_energy=current_energy,
                time_slot=current_time_slot,
                respect_energy=respect_energy,
            )
            recommendations.append(
                ScheduleAwareRecommendation(
                    uid=goal_uid,
                    entity_type="goal",
                    recommendation_type="goal",
                    title=f"Primary Goal: {goal_uid}",
                    rationale=f"Currently at {int(progress * 100)}% - advance toward completion",
                    suggested_time_slot=current_time_slot,
                    estimated_duration_minutes=60,
                    fits_available_time=available_minutes >= 60,
                    schedule_fit_score=score["schedule_fit"],
                    energy_match_score=score["energy_match"],
                    priority_score=score["priority"],
                    overall_score=score["overall"],
                    life_path_aligned=goal_uid in self.context.learning_goals,
                )
            )

        return recommendations

    def _calculate_schedule_score(
        self,
        entity_type: str,
        priority: float,
        energy_required: str,
        current_energy: str,
        time_slot: str,
        respect_energy: bool,
    ) -> dict[str, float]:
        """
        Calculate schedule-aware scoring for a recommendation.

        Returns dict with:
        - schedule_fit: How well it fits the current schedule (0.0-1.0)
        - energy_match: How well it matches current energy (0.0-1.0)
        - priority: Priority score (0.0-1.0)
        - overall: Weighted combination (0.0-1.0)
        """
        # Schedule fit based on time slot appropriateness
        schedule_fit = 0.7  # Default
        if entity_type == EntityType.TASK.value and time_slot in ["morning", "afternoon"]:
            schedule_fit = 0.9
        elif entity_type == EntityType.HABIT.value:
            schedule_fit = 0.85  # Habits are flexible
        elif (
            entity_type in ("knowledge", EntityType.LESSON.value, EntityType.KU.value)
            and time_slot == "morning"
        ):
            schedule_fit = 0.95  # Learning best in morning
        elif entity_type == EntityType.GOAL.value:
            schedule_fit = 0.75  # Goals need focused time

        # Energy match
        energy_levels = {"high": 3, "medium": 2, "low": 1}
        current = energy_levels.get(current_energy, 2)
        required = energy_levels.get(energy_required, 2)

        if respect_energy:
            if current >= required:
                energy_match = 1.0
            elif current == required - 1:
                energy_match = 0.7
            else:
                energy_match = 0.4
        else:
            energy_match = 0.8  # Ignore energy, give neutral score

        # Calculate overall score (weighted)
        # Priority: 40%, Schedule fit: 35%, Energy match: 25%
        overall = (priority * 0.4) + (schedule_fit * 0.35) + (energy_match * 0.25)

        return {
            "schedule_fit": schedule_fit,
            "energy_match": energy_match,
            "priority": priority,
            "overall": overall,
        }


__all__ = ["ScheduleIntelligenceMixin"]
