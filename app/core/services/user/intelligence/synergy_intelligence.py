"""
Synergy Intelligence Mixin
===========================

Method 6 of UserContextIntelligence:
- get_cross_domain_synergies() - Detect synergies between entities across domains

**Synergy Types Detected:**
1. Habit->Goal: Habits supporting multiple goals (high leverage)
2. Task->Habit: Tasks that build habits (behavior change)
3. Knowledge->Task: Knowledge enabling tasks (skill application)
4. Principle->Goal: Principles guiding goal pursuit (value alignment)
5. Goal->Learning: Goals requiring specific knowledge (learning gaps)
6. PS->Multi: Active engagements scored by completion ratio of spawned items
"""

from __future__ import annotations

from core.models.context_types import CrossDomainSynergy
from core.services.user.intelligence._base import IntelligenceMixinBase
from core.utils.result_simplified import Result


class SynergyIntelligenceMixin(IntelligenceMixinBase):
    """
    Mixin providing cross-domain synergy detection methods.

    Requires self.context (RichUserContext — rich-only fields are needed).
    """

    # =========================================================================
    # METHOD 6: Cross-Domain Synergies
    # =========================================================================

    async def get_cross_domain_synergies(  # skuel-lint: disable=SKUEL029 -- askesis_protocols protocol method + facade-delegated
        self,
        min_synergy_score: float = 0.3,
        include_types: list[str] | None = None,
    ) -> Result[list[CrossDomainSynergy]]:
        """
        Detect synergies between entities across different domains.

        **Synergy Types Detected:**
        1. Habit->Goal: Habits supporting multiple goals (high leverage)
        2. Task->Habit: Tasks that build habits (behavior change)
        3. Knowledge->Task: Knowledge enabling tasks (skill application)
        4. Principle->Goal: Principles guiding goal pursuit (value alignment)
        5. Goal->Learning: Goals requiring specific knowledge (learning gaps)

        **Use Cases:**
        - "Which habits give me the most bang for my buck?"
        - "What should I focus on to advance multiple goals?"
        - "How do my daily actions connect to my life path?"

        Args:
            min_synergy_score: Minimum score to include (0.0-1.0)
            include_types: Filter to specific types ["habit_goal", "task_habit", etc.]

        Returns:
            Result[list[CrossDomainSynergy]] sorted by score (highest first)
        """
        # Rich context is compile-time enforced via `context: RichUserContext`.
        synergies: list[CrossDomainSynergy] = []

        # Default to all types
        if include_types is None:
            include_types = [
                "habit_goal",
                "task_habit",
                "knowledge_task",
                "principle_goal",
                "goal_learning",
                "engagement_completion",
            ]

        # =====================================================================
        # 1. Habit->Goal Synergies (habits supporting multiple goals)
        # =====================================================================
        if "habit_goal" in include_types:
            habit_synergies = self._detect_habit_goal_synergies()
            synergies.extend(habit_synergies)

        # =====================================================================
        # 2. Task->Habit Synergies (tasks building habits)
        # =====================================================================
        if "task_habit" in include_types:
            task_habit_synergies = self._detect_task_habit_synergies()
            synergies.extend(task_habit_synergies)

        # =====================================================================
        # 3. Knowledge->Task Synergies (knowledge enabling tasks)
        # =====================================================================
        if "knowledge_task" in include_types:
            knowledge_synergies = self._detect_knowledge_task_synergies()
            synergies.extend(knowledge_synergies)

        # =====================================================================
        # 4. Principle->Goal Synergies (principles guiding goals)
        # =====================================================================
        if "principle_goal" in include_types:
            principle_synergies = self._detect_principle_goal_synergies()
            synergies.extend(principle_synergies)

        # =====================================================================
        # 5. Goal->Learning Synergies (goals requiring knowledge)
        # =====================================================================
        if "goal_learning" in include_types:
            goal_learning_synergies = self._detect_goal_learning_synergies()
            synergies.extend(goal_learning_synergies)

        # =====================================================================
        # 6. PS->Multi Synergies (engagement completion ratio)
        # =====================================================================
        if "engagement_completion" in include_types:
            engagement_synergies = self._detect_engagement_synergies()
            synergies.extend(engagement_synergies)

        # Filter by minimum score and sort by score (highest first)
        filtered_synergies = [s for s in synergies if s.synergy_score >= min_synergy_score]
        from core.utils.sort_functions import get_synergy_score

        filtered_synergies.sort(key=get_synergy_score, reverse=True)

        return Result.ok(filtered_synergies)

    def _detect_habit_goal_synergies(self) -> list[CrossDomainSynergy]:
        """
        Detect habits that support multiple goals.

        **High Leverage:** A habit supporting 3+ goals is extremely valuable.
        Example: "Daily exercise" -> Health goal, Energy goal, Stress reduction goal
        """
        habits_by_goal = self.context.get_habits_by_goal()
        at_risk_habits = self.context.get_habits_needing_reinforcement()
        synergies: list[CrossDomainSynergy] = []

        # Build reverse mapping: habit_uid -> [goal_uids]
        habit_to_goals: dict[str, list[str]] = {}
        for goal_uid, habit_uids in habits_by_goal.items():
            for habit_uid in habit_uids:
                if habit_uid not in habit_to_goals:
                    habit_to_goals[habit_uid] = []
                if goal_uid not in habit_to_goals[habit_uid]:
                    habit_to_goals[habit_uid].append(goal_uid)

        # Score each habit by number of goals supported
        for habit_uid, goal_uids in habit_to_goals.items():
            if len(goal_uids) < 1:
                continue

            # Score: 1 goal = 0.3, 2 goals = 0.5, 3+ goals = 0.7+
            base_score = min(0.9, 0.2 + (len(goal_uids) * 0.2))

            # Bonus for maintained streaks
            streak = self.context.habit_streaks.get(habit_uid, 0)
            streak_bonus = min(0.1, streak * 0.01)  # +0.01 per day, max +0.1

            synergy_score = min(1.0, base_score + streak_bonus)

            # Generate recommendations
            recommendations = []
            if streak < 7:
                recommendations.append(f"Build consistency - current streak: {streak} days")
            if len(goal_uids) >= 3:
                recommendations.append("High-leverage habit! Prioritize maintaining this.")
            if habit_uid in at_risk_habits:
                recommendations.append("At-risk! Don't break this streak.")

            synergy = CrossDomainSynergy(
                source_uid=habit_uid,
                source_domain="habit",
                target_uids=tuple(goal_uids),
                target_domain="goal",
                synergy_type="supports",
                synergy_score=synergy_score,
                rationale=f"This habit supports {len(goal_uids)} goals simultaneously",
                recommendations=tuple(recommendations),
            )
            synergies.append(synergy)

        return synergies

    def _detect_task_habit_synergies(self) -> list[CrossDomainSynergy]:
        """
        Detect tasks that build habits (behavior change opportunities).

        Example: "Write morning pages" task -> "Daily journaling" habit
        """
        habits_by_goal = self.context.get_habits_by_goal()
        synergies: list[CrossDomainSynergy] = []

        # Find tasks that contribute to habit-supporting goals
        for habit_uid in self.context.active_habit_uids:
            supporting_tasks: list[str] = []

            # Find goals this habit supports
            for goal_uid, habit_uids in habits_by_goal.items():
                if habit_uid in habit_uids:
                    # Find tasks for this goal
                    tasks = self.context.get_tasks_for_goal(goal_uid)
                    for task_uid in tasks:
                        if task_uid not in supporting_tasks:
                            supporting_tasks.append(task_uid)

            if supporting_tasks:
                synergy_score = min(0.8, 0.3 + (len(supporting_tasks) * 0.1))

                recommendations = []
                if len(supporting_tasks) >= 3:
                    recommendations.append("Multiple tasks reinforce this habit")
                recommendations.append("Complete these tasks to strengthen habit formation")

                synergy = CrossDomainSynergy(
                    source_uid=habit_uid,
                    source_domain="habit",
                    target_uids=tuple(supporting_tasks[:5]),
                    target_domain="task",
                    synergy_type="builds",
                    synergy_score=synergy_score,
                    rationale=f"{len(supporting_tasks)} tasks reinforce this habit",
                    recommendations=tuple(recommendations),
                )
                synergies.append(synergy)

        return synergies

    def _detect_knowledge_task_synergies(self) -> list[CrossDomainSynergy]:
        """
        Detect knowledge that enables multiple tasks.

        Example: "Python async" knowledge -> enables 5 coding tasks
        """
        synergies: list[CrossDomainSynergy] = []

        # Use context's knowledge_task_applications if available
        # Otherwise infer from prerequisites_needed
        for ku_uid in self.context.mastered_knowledge_uids:
            enabled_tasks: list[str] = []

            # Check which tasks require this knowledge
            for task_uid in self.context.active_task_uids:
                # Check if task is in blocked list and needs this knowledge
                prereqs = self.context.prerequisites_needed.get(task_uid, [])
                if ku_uid in prereqs:
                    enabled_tasks.append(task_uid)

            # Also check tasks where this knowledge could be applied
            # (tasks associated with goals that require this knowledge)
            aligned_goals = self._find_aligned_goals_for_ku(ku_uid)
            for goal_uid in aligned_goals:
                for task_uid in self.context.get_tasks_for_goal(goal_uid):
                    if task_uid not in enabled_tasks:
                        enabled_tasks.append(task_uid)

            if enabled_tasks:
                mastery = self.context.knowledge_mastery.get(ku_uid, 0.5)
                synergy_score = min(0.9, 0.3 + (len(enabled_tasks) * 0.1) + (mastery * 0.2))

                recommendations = []
                if mastery < 0.7:
                    recommendations.append(
                        "Deepen mastery to unlock more application opportunities"
                    )
                if len(enabled_tasks) >= 3:
                    recommendations.append("High-leverage knowledge! Apply across multiple tasks.")

                synergy = CrossDomainSynergy(
                    source_uid=ku_uid,
                    source_domain="knowledge",
                    target_uids=tuple(enabled_tasks[:5]),
                    target_domain="task",
                    synergy_type="enables",
                    synergy_score=synergy_score,
                    rationale=f"Enables {len(enabled_tasks)} tasks with {mastery:.0%} mastery",
                    recommendations=tuple(recommendations),
                )
                synergies.append(synergy)

        return synergies

    def _find_aligned_goals_for_ku(self, ku_uid: str) -> list[str]:
        """Find goals that would benefit from this knowledge."""
        return [
            goal_uid
            for goal_uid in self.context.learning_goals
            if ku_uid in self.context.prerequisites_needed.get(goal_uid, [])
        ]

    def _detect_principle_goal_synergies(self) -> list[CrossDomainSynergy]:
        """
        Detect principles guiding multiple goals.

        Example: "Growth mindset" principle -> guides Learning goal, Career goal, Health goal
        """
        synergies: list[CrossDomainSynergy] = []

        # Use principle_priorities and learning_goals to find connections
        for principle_uid in self.context.core_principle_uids:
            aligned_goals: list[str] = []

            # Check which goals align with this principle
            # (In full implementation, would query UnifiedRelationshipService)
            # For now, use learning_goals as proxy
            for goal_uid in self.context.learning_goals:
                # Assume principles align with learning goals
                aligned_goals.append(goal_uid)

            if aligned_goals:
                importance = self.context.principle_priorities.get(principle_uid, 0.5)
                synergy_score = min(0.9, 0.3 + (len(aligned_goals) * 0.15) + (importance * 0.2))

                recommendations = []
                if importance > 0.7:
                    recommendations.append("Core principle - ensure daily actions align")
                if len(aligned_goals) >= 2:
                    recommendations.append("This principle guides multiple goals")

                synergy = CrossDomainSynergy(
                    source_uid=principle_uid,
                    source_domain="principle",
                    target_uids=tuple(aligned_goals[:5]),
                    target_domain="goal",
                    synergy_type="informs",
                    synergy_score=synergy_score,
                    rationale=f"Guides {len(aligned_goals)} goals with {importance:.0%} importance",
                    recommendations=tuple(recommendations),
                )
                synergies.append(synergy)

        return synergies

    def _detect_goal_learning_synergies(self) -> list[CrossDomainSynergy]:
        """
        Detect goals that share knowledge requirements.

        Example: "Career advancement" and "Side project" goals both need "Python async"
        """
        synergies: list[CrossDomainSynergy] = []

        # Build knowledge -> goals mapping
        knowledge_to_goals: dict[str, list[str]] = {}
        for goal_uid in self.context.learning_goals:
            prereqs = self.context.prerequisites_needed.get(goal_uid, [])
            for ku_uid in prereqs:
                if ku_uid not in knowledge_to_goals:
                    knowledge_to_goals[ku_uid] = []
                if goal_uid not in knowledge_to_goals[ku_uid]:
                    knowledge_to_goals[ku_uid].append(goal_uid)

        # Score each knowledge unit by number of goals requiring it
        for ku_uid, goal_uids in knowledge_to_goals.items():
            if len(goal_uids) < 2:
                continue  # Only interesting if multiple goals need it

            # Check if already mastered
            is_mastered = ku_uid in self.context.mastered_knowledge_uids
            mastery = self.context.knowledge_mastery.get(ku_uid, 0.0)

            synergy_score = min(0.9, 0.3 + (len(goal_uids) * 0.2))
            if not is_mastered:
                synergy_score += 0.1  # Bonus for unlearned (actionable)

            recommendations = []
            if not is_mastered:
                recommendations.append(f"Learning this unlocks {len(goal_uids)} goals!")
            else:
                recommendations.append(
                    f"Apply your {mastery:.0%} mastery to advance multiple goals"
                )

            synergy = CrossDomainSynergy(
                source_uid=ku_uid,
                source_domain="knowledge",
                target_uids=tuple(goal_uids),
                target_domain="goal",
                synergy_type="enables",
                synergy_score=synergy_score,
                rationale=f"Required by {len(goal_uids)} goals"
                + (" (not yet mastered)" if not is_mastered else f" ({mastery:.0%} mastered)"),
                recommendations=tuple(recommendations),
            )
            synergies.append(synergy)

        return synergies

    def _detect_engagement_synergies(self) -> list[CrossDomainSynergy]:
        """
        Score each active PS engagement by completion ratio of its completable
        spawned items.

        Tasks/Goals/Choices have terminal states (completed/resolved); the ratio
        is computed over those domains only. Habits/Events/Principles spawned by
        the engagement are perpetual commitments — they emit a low-score "ongoing"
        synergy when an engagement spawned nothing terminal-eligible.

        Abandoned engagements are skipped entirely; completed engagements score
        1.0 (loop closed). Engaged-state synergies scale 0.3-0.9 with ratio.
        """
        engagements_map = self.context.active_ps_engagements
        if not engagements_map:
            return []

        completed_terminal = (
            self.context.completed_task_uids
            | self.context.completed_goal_uids
            | self.context.resolved_choice_uids
        )
        in_flight_terminal = (
            set(self.context.active_task_uids)
            | set(self.context.active_goal_uids)
            | set(self.context.pending_choice_uids)
        )

        synergies: list[CrossDomainSynergy] = []
        for engagement in engagements_map.values():
            if engagement.state == "abandoned":
                continue
            spawned = engagement.spawned_instance_uids
            if not spawned:
                continue

            completed = [u for u in spawned if u in completed_terminal]
            pending = [u for u in spawned if u in in_flight_terminal]
            completable = len(completed) + len(pending)

            if engagement.state == "completed":
                synergy_score = 1.0
                rationale = f"Engagement closed; spawned {len(spawned)} items"
                recommendations: tuple[str, ...] = ("Loop closed — knowledge consolidated",)
            elif completable == 0:
                synergy_score = 0.35
                rationale = (
                    f"Engaged; {len(spawned)} ongoing commitments (no terminal-state items spawned)"
                )
                recommendations = ("Maintain habits/events spawned by this engagement",)
            else:
                ratio = len(completed) / completable
                synergy_score = min(0.9, 0.3 + (ratio * 0.6))
                rationale = (
                    f"{len(completed)}/{completable} completable spawned items "
                    f"complete ({ratio:.0%})"
                )
                recs: list[str] = []
                if ratio >= 0.7:
                    recs.append("Closing the loop — finish remaining to complete engagement")
                elif ratio < 0.3 and len(pending) >= 3:
                    recs.append("Stalled — review or abandon if priorities shifted")
                elif pending:
                    recs.append(f"{len(pending)} items still pending")
                recommendations = tuple(recs)

            synergies.append(
                CrossDomainSynergy(
                    source_uid=engagement.ps_uid,
                    source_domain="pathstep",
                    target_uids=tuple(spawned[:6]),
                    target_domain="multi",
                    synergy_type="spawns",
                    synergy_score=synergy_score,
                    rationale=rationale,
                    recommendations=recommendations,
                )
            )

        return synergies


__all__ = ["SynergyIntelligenceMixin"]
