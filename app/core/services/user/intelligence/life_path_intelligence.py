"""
Life Path Intelligence Mixin
=============================

Method 7 of UserContextIntelligence:
- calculate_life_path_alignment() - Multi-dimensional life path alignment scoring

**Philosophy:** "Everything flows toward the life path"

This module measures how well a user's daily activities, knowledge,
habits, goals, and principles align with their ultimate life path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.user.intelligence.types import LifePathAlignment
from core.utils.result_simplified import Result
from core.utils.sort_functions import make_dict_score_getter

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


class LifePathIntelligenceMixin:
    """
    Mixin providing life path alignment methods.

    Requires self.context (UserContext).
    """

    context: UserContext

    # =========================================================================
    # METHOD 7: Life Path Alignment
    # =========================================================================

    async def calculate_life_path_alignment(self) -> Result[LifePathAlignment]:
        """
        Calculate comprehensive life path alignment.

        **Phase 3 Addition:** Multi-dimensional life path alignment scoring.

        **Philosophy:** "Everything flows toward the life path"

        **Alignment Dimensions (5):**
        1. Knowledge Alignment (25%): Mastery of life path knowledge
        2. Activity Alignment (25%): Tasks/habits supporting life path
        3. Goal Alignment (20%): Active goals contributing to life path
        4. Principle Alignment (15%): Values supporting life path direction
        5. Momentum (15%): Recent activity trend toward life path

        **Use Cases:**
        - "Am I living in alignment with my life purpose?"
        - "Where am I drifting from my path?"
        - "What should I prioritize to get back on track?"

        Returns:
            Result containing LifePathAlignment with overall score, dimension scores, and insights
        """
        # Check if user has a life path defined
        if not self.context.life_path_uid:
            return Result.ok(
                LifePathAlignment(
                    overall_score=0.0,
                    alignment_level="undefined",
                    knowledge_score=0.0,
                    activity_score=0.0,
                    goal_score=0.0,
                    principle_score=0.0,
                    momentum_score=0.0,
                    strengths=[],
                    gaps=["No life path defined - consider defining your ultimate direction"],
                    recommendations=["Define your life path to enable alignment tracking"],
                    life_path_uid=None,
                    life_path_milestones_completed=0,
                    life_path_milestones_total=0,
                    aligned_goals=[],
                    supporting_habits=[],
                    knowledge_gaps=[],
                )
            )

        # Calculate dimension scores
        knowledge_score = self._calculate_knowledge_alignment()
        activity_score = self._calculate_activity_alignment()
        goal_score = self._calculate_goal_alignment()
        principle_score = self._calculate_principle_alignment()
        momentum_score = self._calculate_momentum_score()

        # Weighted average for overall score
        overall_score = (
            knowledge_score * 0.25
            + activity_score * 0.25
            + goal_score * 0.20
            + principle_score * 0.15
            + momentum_score * 0.15
        )

        # Determine alignment level
        alignment_level = self._determine_alignment_level(overall_score)

        # Generate insights
        strengths = self._identify_alignment_strengths(
            knowledge_score, activity_score, goal_score, principle_score, momentum_score
        )
        gaps = self._identify_alignment_gaps(
            knowledge_score, activity_score, goal_score, principle_score, momentum_score
        )
        recommendations = self._generate_alignment_recommendations(
            knowledge_score, activity_score, goal_score, principle_score, momentum_score
        )

        # Gather supporting data
        aligned_goals = self._get_life_path_aligned_goals()
        supporting_habits = self._get_life_path_supporting_habits()
        knowledge_gaps = self.context.get_life_path_gaps()

        # Calculate milestone progress
        milestones_total = len(self.context.life_path_milestones)
        milestones_completed = self._count_completed_milestones()

        return Result.ok(
            LifePathAlignment(
                overall_score=overall_score,
                alignment_level=alignment_level,
                knowledge_score=knowledge_score,
                activity_score=activity_score,
                goal_score=goal_score,
                principle_score=principle_score,
                momentum_score=momentum_score,
                strengths=strengths,
                gaps=gaps,
                recommendations=recommendations,
                life_path_uid=self.context.life_path_uid,
                life_path_milestones_completed=milestones_completed,
                life_path_milestones_total=milestones_total,
                aligned_goals=aligned_goals,
                supporting_habits=supporting_habits,
                knowledge_gaps=knowledge_gaps,
            )
        )

    def _calculate_knowledge_alignment(self) -> float:
        """
        Calculate knowledge alignment score (0.0-1.0).

        Based on mastery of life path knowledge.
        """
        # Get all knowledge related to life path goals
        life_path_knowledge_uids: list[str] = []
        for goal_uid in self.context.learning_goals:
            prereqs = self.context.prerequisites_needed.get(goal_uid, [])
            life_path_knowledge_uids.extend(prereqs)

        # Remove duplicates
        life_path_knowledge_uids = list(set(life_path_knowledge_uids))

        if not life_path_knowledge_uids:
            # Use context's life path alignment calculation
            return self.context.life_path_alignment_score

        # Calculate average mastery
        total_mastery = 0.0
        for ku_uid in life_path_knowledge_uids:
            mastery = self.context.knowledge_mastery.get(ku_uid, 0.0)
            total_mastery += mastery

        return total_mastery / len(life_path_knowledge_uids) if life_path_knowledge_uids else 0.0

    def _calculate_activity_alignment(self) -> float:
        """
        Calculate activity alignment score (0.0-1.0).

        Based on tasks and habits supporting life path goals.
        """
        if not self.context.active_task_uids and not self.context.active_habit_uids:
            return 0.0

        aligned_activities = 0
        total_activities = len(self.context.active_task_uids) + len(self.context.active_habit_uids)

        # Count tasks aligned with learning goals (life path proxy)
        for task_uid in self.context.active_task_uids:
            for goal_uid in self.context.learning_goals:
                if task_uid in self.context.tasks_by_goal.get(goal_uid, []):
                    aligned_activities += 1
                    break

        # Count habits aligned with learning goals
        for habit_uid in self.context.active_habit_uids:
            for goal_uid in self.context.learning_goals:
                if habit_uid in self.context.habits_by_goal.get(goal_uid, []):
                    aligned_activities += 1
                    break

        return aligned_activities / total_activities if total_activities > 0 else 0.0

    def _calculate_goal_alignment(self) -> float:
        """
        Calculate goal alignment score (0.0-1.0).

        Based on active goals contributing to life path.
        """
        if not self.context.active_goal_uids:
            return 0.0

        # Learning goals are directly aligned with life path
        aligned_count = len(set(self.context.learning_goals) & set(self.context.active_goal_uids))
        total_goals = len(self.context.active_goal_uids)

        # Also consider goal progress
        total_progress = sum(self.context.goal_progress.values())
        avg_progress = (
            total_progress / len(self.context.goal_progress) if self.context.goal_progress else 0.0
        )

        # Combine alignment ratio with progress
        alignment_ratio = aligned_count / total_goals if total_goals > 0 else 0.0
        return (alignment_ratio * 0.7) + (avg_progress * 0.3)

    def _calculate_principle_alignment(self) -> float:
        """
        Calculate principle alignment score (0.0-1.0).

        Enhanced three-component calculation:
        1. Choice-principle alignment ratio (40%) - How many choices align with principles
        2. Principle alignment by domain (30%) - Domain-level principle alignment
        3. Principle integration score (30%) - Overall principle-choice integration

        Based on values supporting life path direction.
        """
        if not self.context.core_principle_uids:
            return 0.5  # Neutral if no principles defined

        scores: list[float] = []

        # Component 1: Choice-principle alignment (40% weight)
        total_decisions = (
            self.context.decisions_aligned_with_principles
            + self.context.decisions_against_principles
        )
        if total_decisions > 0:
            choice_alignment = self.context.decisions_aligned_with_principles / total_decisions
            scores.append(choice_alignment * 0.40)
        else:
            scores.append(0.20)  # Neutral contribution when no decision data

        # Component 2: Domain alignment (30% weight)
        if self.context.principle_alignment_by_domain:
            domain_avg = sum(self.context.principle_alignment_by_domain.values()) / len(
                self.context.principle_alignment_by_domain
            )
            scores.append(domain_avg * 0.30)
        else:
            scores.append(0.15)  # Neutral contribution when no domain data

        # Component 3: Principle integration score (30% weight)
        # Uses the new principle_integration_score from UserContext
        scores.append(self.context.principle_integration_score * 0.30)

        return sum(scores)

    def _calculate_momentum_score(self) -> float:
        """
        Calculate momentum score (0.0-1.0).

        Based on recent activity trend toward life path.
        """
        momentum_factors = []

        # Factor 1: Streak health (habits being maintained)
        if self.context.active_habit_uids:
            maintained_habits = len(
                [
                    h
                    for h in self.context.active_habit_uids
                    if self.context.habit_streaks.get(h, 0) >= 3
                ]
            )
            streak_ratio = maintained_habits / len(self.context.active_habit_uids)
            momentum_factors.append(streak_ratio)

        # Factor 2: Recent task completion (estimate from workload)
        # Lower workload = more tasks completed recently
        workload_inverse = 1.0 - min(1.0, self.context.current_workload_score)
        momentum_factors.append(workload_inverse * 0.5 + 0.25)  # Normalize to 0.25-0.75

        # Factor 3: Learning progress (new knowledge being acquired)
        if self.context.recently_mastered_uids:
            learning_momentum = min(1.0, len(self.context.recently_mastered_uids) * 0.2)
            momentum_factors.append(learning_momentum)

        # Factor 4: At-risk habits (negative indicator)
        if self.context.at_risk_habits:
            at_risk_penalty = max(0.0, 1.0 - len(self.context.at_risk_habits) * 0.2)
            momentum_factors.append(at_risk_penalty)

        return sum(momentum_factors) / len(momentum_factors) if momentum_factors else 0.5

    def _determine_alignment_level(self, score: float) -> str:
        """Determine alignment level from score."""
        if score >= 0.9:
            return "flourishing"
        elif score >= 0.7:
            return "aligned"
        elif score >= 0.4:
            return "exploring"
        else:
            return "drifting"

    def _identify_alignment_strengths(
        self,
        knowledge: float,
        activity: float,
        goal: float,
        principle: float,
        momentum: float,
    ) -> list[str]:
        """Identify areas where alignment is strong."""
        strengths = []

        if knowledge >= 0.7:
            strengths.append("Strong knowledge foundation for life path")
        if activity >= 0.7:
            strengths.append("Daily activities well aligned with life purpose")
        if goal >= 0.7:
            strengths.append("Goals actively supporting life path direction")
        if principle >= 0.7:
            strengths.append("Values strongly guiding life path decisions")
        if momentum >= 0.7:
            strengths.append("Positive momentum toward life path goals")

        if not strengths:
            # Find the best dimension even if below 0.7
            scores = {
                "knowledge": knowledge,
                "activity": activity,
                "goal": goal,
                "principle": principle,
                "momentum": momentum,
            }
            score_getter = make_dict_score_getter(scores)
            best = max(scores, key=score_getter)
            strengths.append(f"Best alignment in {best} dimension ({scores[best]:.0%})")

        return strengths

    def _identify_alignment_gaps(
        self,
        knowledge: float,
        activity: float,
        goal: float,
        principle: float,
        momentum: float,
    ) -> list[str]:
        """Identify areas where alignment is lacking."""
        gaps = []

        if knowledge < 0.5:
            gaps.append("Knowledge gaps in life path areas")
        if activity < 0.5:
            gaps.append("Daily activities not aligned with life purpose")
        if goal < 0.5:
            gaps.append("Active goals not supporting life path")
        if principle < 0.5:
            gaps.append("Values not clearly guiding decisions")
        if momentum < 0.5:
            gaps.append("Losing momentum toward life path goals")

        return gaps

    def _generate_alignment_recommendations(
        self,
        knowledge: float,
        activity: float,
        goal: float,
        principle: float,
        momentum: float,
    ) -> list[str]:
        """Generate actionable recommendations to improve alignment."""
        recommendations = []

        # Knowledge recommendations
        if knowledge < 0.5:
            recommendations.append("Focus on learning life path prerequisites")
        elif knowledge < 0.7:
            recommendations.append("Deepen mastery in key life path knowledge areas")

        # Activity recommendations
        if activity < 0.5:
            recommendations.append("Align more daily tasks with life path goals")
        elif activity < 0.7:
            recommendations.append("Add habits that reinforce life path direction")

        # Goal recommendations
        if goal < 0.5:
            recommendations.append("Set more goals aligned with your life path")
        elif goal < 0.7:
            recommendations.append("Prioritize progress on life path goals")

        # Principle recommendations
        if principle < 0.5:
            recommendations.append("Clarify core principles guiding your life path")
        elif principle < 0.7:
            recommendations.append("Make more decisions aligned with your principles")

        # Momentum recommendations
        if momentum < 0.5:
            recommendations.append("Build consistent habits to maintain momentum")
            if self.context.at_risk_habits:
                recommendations.append(f"Address {len(self.context.at_risk_habits)} at-risk habits")

        # If doing well, encourage continuation
        if not recommendations:
            recommendations.append("Continue current trajectory - you're well aligned!")
            recommendations.append("Consider setting more ambitious life path milestones")

        return recommendations[:5]  # Limit to 5 recommendations

    def _get_life_path_aligned_goals(self) -> list[str]:
        """Get goals aligned with life path."""
        aligned = []
        for goal_uid in self.context.active_goal_uids:
            if goal_uid in self.context.learning_goals:
                aligned.append(goal_uid)
        return aligned

    def _get_life_path_supporting_habits(self) -> list[str]:
        """Get habits supporting life path goals."""
        supporting = []
        for habit_uid in self.context.active_habit_uids:
            for goal_uid in self.context.learning_goals:
                if habit_uid in self.context.habits_by_goal.get(goal_uid, []):
                    supporting.append(habit_uid)
                    break
        return supporting

    def _count_completed_milestones(self) -> int:
        """Count completed life path milestones."""
        completed = 0
        for milestone_uid in self.context.life_path_milestones:
            # Check if milestone is in completed goals or mastered knowledge
            if (
                milestone_uid in self.context.mastered_knowledge_uids
                or self.context.goal_progress.get(milestone_uid, 0) >= 1.0
            ):
                completed += 1
        return completed


__all__ = ["LifePathIntelligenceMixin"]
