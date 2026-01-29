"""
Learning Intelligence Mixin
============================

Methods 1-4 of UserContextIntelligence:
1. get_optimal_next_learning_steps() - What should I learn next?
2. get_learning_path_critical_path() - Fastest route to life path?
3. get_knowledge_application_opportunities() - Where can I apply this?
4. get_unblocking_priority_order() - What unlocks the most?

These methods synthesize KU, Goals, Tasks, and Context to determine
optimal learning priorities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.user.intelligence.types import LearningStep
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.context_types import ContextualKnowledge
    from core.services.user.unified_user_context import UserContext


class LearningIntelligenceMixin:
    """
    Mixin providing learning intelligence methods.

    Requires self.context (UserContext) and self.tasks, self.ku (relationship services).
    Optional: self.vector_search (Neo4jVectorSearchService) for semantic/learning-aware search.
    """

    context: UserContext
    tasks: Any  # TasksRelationshipService
    ku: Any  # KuGraphService
    vector_search: Any = None  # Neo4jVectorSearchService (optional - Phase 1 enhancement)

    # =========================================================================
    # METHOD 1: Optimal Next Learning Steps
    # =========================================================================

    async def get_optimal_next_learning_steps(
        self,
        max_steps: int = 5,
        consider_goals: bool = True,
        consider_capacity: bool = True,
    ) -> Result[list[LearningStep]]:
        """
        THE CORE METHOD - determine what to learn next based on ALL factors.

        **Synthesizes:**
        - KU service: get_ready_to_learn_for_user() - Prerequisites met
        - Vector search (Phase 1): Learning-aware search with mastery boosting
        - Goals service: Goal alignment
        - Tasks service: Knowledge application opportunities
        - Context: Capacity, energy, life path alignment

        **Ranking Factors:**
        - Prerequisites met (ready to learn)
        - Learning state (prefer unmastered content)
        - Goal alignment (helps achieve goals)
        - User capacity (fits available time)
        - Life path alignment (flows toward ultimate path)
        - Unblocking potential (unlocks other items)

        Args:
            max_steps: Maximum number of steps to return
            consider_goals: Weight by goal alignment
            consider_capacity: Respect user capacity limits

        Returns:
            Result[list[LearningStep]] ranked by priority with full context
        """
        # Phase 1 Enhancement: Try learning-aware search first (if available)
        if self.vector_search and hasattr(self.vector_search, "learning_aware_search"):
            # Use semantic/learning-aware search to find optimal next steps
            # This personalizes based on mastery state (MASTERED, IN_PROGRESS, etc.)
            search_query = self._generate_learning_query()
            vector_result = await self.vector_search.learning_aware_search(
                label="Ku",
                text=search_query,
                user_uid=self.context.user_uid,
                prefer_unmastered=True,
                limit=max_steps * 2,
            )

            if vector_result.is_ok and vector_result.value:
                # Convert vector results to learning steps
                return await self._vector_results_to_learning_steps(
                    vector_result.value, max_steps, consider_goals, consider_capacity
                )

        # Fallback: Get knowledge ready to learn from KU relationship service
        ready_result = await self.ku.get_ready_to_learn_for_user(self.context, limit=max_steps * 2)

        if ready_result.is_error or not ready_result.value:
            # Fall back to context-based approach
            return Result.ok(
                self._get_learning_steps_from_context(max_steps, consider_goals, consider_capacity)
            )

        learning_steps = []
        contextual_knowledge_list: list[ContextualKnowledge] = ready_result.value

        for contextual_ku in contextual_knowledge_list:
            # Get application opportunities
            applications = await self._get_application_opportunities_for_ku(contextual_ku.uid)

            # Count unlocks
            unlocks_count = self._count_items_unlocked_by(contextual_ku.uid)

            # Find aligned goals
            aligned_goals = self._find_aligned_goals(contextual_ku.uid)

            step = LearningStep(
                ku_uid=contextual_ku.uid,
                title=contextual_ku.title,
                rationale=self._generate_learning_rationale(
                    contextual_ku.uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=contextual_ku.prerequisites_met,
                aligns_with_goals=aligned_goals,
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_time_to_mastery.get(
                    contextual_ku.uid, 60
                ),
                priority_score=contextual_ku.priority_score,
                application_opportunities=applications,
            )

            learning_steps.append(step)

        # Sort by priority score (highest first)
        from core.utils.sort_functions import get_priority_score

        learning_steps.sort(key=get_priority_score, reverse=True)

        # Apply capacity filter if requested
        if consider_capacity:
            learning_steps = self._filter_by_capacity(learning_steps)

        return Result.ok(learning_steps[:max_steps])

    def _get_learning_steps_from_context(
        self,
        max_steps: int,
        consider_goals: bool,
        consider_capacity: bool,
    ) -> list[LearningStep]:
        """Fallback: Get learning steps from context when service unavailable."""
        ready_uids = self.context.get_ready_to_learn()

        if not ready_uids:
            return []

        learning_steps = []

        for ku_uid in ready_uids[: max_steps * 2]:
            priority_score = self._calculate_learning_priority(
                ku_uid, consider_goals, consider_capacity
            )

            # NOTE: This is a fallback path - no application discovery
            # when main KU service is unavailable (fail-fast principle)
            applications: dict[str, list[str]] = {
                "tasks": [],
                "habits": [],
                "goals": [],
                "events": [],
            }
            unlocks_count = self._count_items_unlocked_by(ku_uid)
            aligned_goals = self._find_aligned_goals(ku_uid)

            step = LearningStep(
                ku_uid=ku_uid,
                title=f"Knowledge Unit {ku_uid}",
                rationale=self._generate_learning_rationale(
                    ku_uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=True,
                aligns_with_goals=aligned_goals,
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_time_to_mastery.get(ku_uid, 60),
                priority_score=priority_score,
                application_opportunities=applications,
            )

            learning_steps.append(step)

        from core.utils.sort_functions import get_priority_score

        learning_steps.sort(key=get_priority_score, reverse=True)
        return learning_steps[:max_steps]

    def _calculate_learning_priority(
        self, ku_uid: str, consider_goals: bool, consider_capacity: bool
    ) -> float:
        """Calculate priority score for a knowledge unit (0.0-1.0)."""
        score = 0.5  # Base score

        # Factor 1: Goal alignment (30% weight)
        if consider_goals:
            aligned_goals = self._find_aligned_goals(ku_uid)
            if aligned_goals:
                goal_weight = min(0.3, len(aligned_goals) * 0.1)
                score += goal_weight

        # Factor 2: Unblocking potential (25% weight)
        unlocks_count = self._count_items_unlocked_by(ku_uid)
        if unlocks_count > 0:
            unblocking_weight = min(0.25, unlocks_count * 0.05)
            score += unblocking_weight

        # Factor 3: Life path alignment (25% weight)
        if self.context.life_path_uid and ku_uid in self.context.next_recommended_knowledge:
            score += 0.25

        # Factor 4: Capacity fit (20% weight)
        if consider_capacity:
            estimated_time = self.context.estimated_time_to_mastery.get(ku_uid, 60)
            if estimated_time <= self.context.available_minutes_daily:
                score += 0.2
            elif estimated_time <= self.context.available_minutes_daily * 2:
                score += 0.1

        return min(1.0, score)

    def _generate_learning_rationale(
        self,
        ku_uid: str,
        aligned_goals: list[str],
        unlocks_count: int,
        applications: dict[str, list[str]],
    ) -> str:
        """Generate human-readable rationale for why to learn this."""
        reasons = []

        if aligned_goals:
            reasons.append(f"Helps with {len(aligned_goals)} active goals")

        if unlocks_count > 0:
            reasons.append(f"Unlocks {unlocks_count} blocked items")

        total_apps = sum(len(items) for items in applications.values())
        if total_apps > 0:
            reasons.append(f"{total_apps} opportunities to apply this knowledge")

        if self.context.life_path_uid:
            reasons.append("Aligns with your life path")

        return "; ".join(reasons) if reasons else "Ready to learn"

    def _find_aligned_goals(self, ku_uid: str) -> list[str]:
        """Find goals that would benefit from this knowledge."""
        return [
            goal_uid
            for goal_uid in self.context.learning_goals
            if ku_uid in self.context.prerequisites_needed.get(goal_uid, [])
        ]

    def _count_items_unlocked_by(self, ku_uid: str) -> int:
        """Count how many blocked items would be unblocked by mastering this KU."""
        unblocked_count = 0

        for prereqs in self.context.prerequisites_needed.values():
            if ku_uid in prereqs:
                missing_prereqs = [
                    p for p in prereqs if p not in self.context.prerequisites_completed
                ]
                if len(missing_prereqs) == 1:
                    unblocked_count += 1

        return unblocked_count

    async def _get_application_opportunities_for_ku(self, ku_uid: str) -> dict[str, list[str]]:
        """
        Get application opportunities using DIRECT graph queries.

        Uses KuGraphService reverse relationship queries to find where
        knowledge is being applied across all activity domains.

        Fail-fast: All queries are REQUIRED. No graceful degradation.

        Returns:
            Dict with keys: tasks, habits, goals, events (all list[str])
        """
        opportunities: dict[str, list[str]] = {
            "tasks": [],
            "habits": [],
            "goals": [],
            "events": [],
        }

        # Get tasks that apply this knowledge (EXISTING - keep as is)
        tasks_result = await self.tasks.get_learning_tasks_for_user(
            self.context, knowledge_focus=[ku_uid]
        )
        if tasks_result.is_ok and tasks_result.value:
            opportunities["tasks"] = [t.uid for t in tasks_result.value[:5]]

        # Get habits reinforcing this knowledge (NEW - graph query via KuGraphService)
        habits_result = await self.ku.find_habits_reinforcing_knowledge(
            ku_uid, self.context.user_uid, only_active=True
        )
        if habits_result.is_ok:
            opportunities["habits"] = habits_result.value[:5]
        elif habits_result.is_error:
            # Fail-fast: propagate error
            raise RuntimeError(
                f"Failed to find habits for KU {ku_uid}: {habits_result.expect_error()}"
            )

        # Get events applying this knowledge (NEW - graph query via KuGraphService)
        events_result = await self.ku.find_events_applying_knowledge(
            ku_uid, self.context.user_uid, upcoming_only=True
        )
        if events_result.is_ok:
            opportunities["events"] = events_result.value[:5]
        elif events_result.is_error:
            # Fail-fast: propagate error
            raise RuntimeError(
                f"Failed to find events for KU {ku_uid}: {events_result.expect_error()}"
            )

        # Goals aligned with this knowledge (EXISTING - context-based is acceptable)
        opportunities["goals"] = self._find_aligned_goals(ku_uid)

        return opportunities

    def _filter_by_capacity(self, steps: list[LearningStep]) -> list[LearningStep]:
        """Filter learning steps by user capacity."""
        available = self.context.available_minutes_daily
        filtered = []
        total_time = 0

        for step in steps:
            if total_time + step.estimated_time_minutes <= available:
                filtered.append(step)
                total_time += step.estimated_time_minutes

        return filtered

    # =========================================================================
    # METHOD 2: Learning Path Critical Path
    # =========================================================================

    async def get_learning_path_critical_path(self) -> Result[list[str]]:
        """
        What's the fastest route to life path alignment?

        **Synthesizes:**
        - LP service: Learning path structure
        - KU service: Prerequisite chains
        - Context: Current mastery levels

        Returns:
            Result containing ordered list of KU UIDs representing critical path
        """
        if not self.context.life_path_uid:
            return Result.ok([])

        # Get all knowledge in life path
        life_path_knowledge = list(self.context.knowledge_mastery.keys())

        if not life_path_knowledge:
            return Result.ok([])

        # Filter to unmastered knowledge
        unmastered = [
            ku_uid
            for ku_uid in life_path_knowledge
            if ku_uid not in self.context.mastered_knowledge_uids
        ]

        # Build dependency graph and find critical path
        critical_path = []
        remaining = set(unmastered)
        completed = set(self.context.prerequisites_completed)

        while remaining:
            ready = []
            for ku_uid in remaining:
                prereqs = self.context.prerequisites_needed.get(ku_uid, [])
                unmet_prereqs = [p for p in prereqs if p not in completed]
                if not unmet_prereqs:
                    ready.append(ku_uid)

            if not ready:
                break

            # Choose the one that unlocks the most other items
            best_ku = max(ready, key=self._count_items_unlocked_by)
            critical_path.append(best_ku)
            remaining.remove(best_ku)
            completed.add(best_ku)

        return Result.ok(critical_path)

    # =========================================================================
    # METHOD 3: Knowledge Application Opportunities
    # =========================================================================

    async def get_knowledge_application_opportunities(
        self, ku_uid: str
    ) -> Result[dict[str, list[str]]]:
        """
        Where can I apply this knowledge in my life?

        **Synthesizes ALL 6 activity domains:**
        - Tasks: Tasks that require this knowledge
        - Habits: Habits that would benefit from this understanding
        - Goals: Goals that align with this knowledge
        - Events: Events where I could practice
        - Choices: Decisions informed by this knowledge
        - Principles: Values this knowledge supports

        Args:
            ku_uid: Knowledge unit UID

        Returns:
            Result containing dict of {domain: [uid_list]} showing application opportunities
        """
        opportunities: dict[str, list[str]] = {
            "tasks": [],
            "habits": [],
            "goals": [],
            "events": [],
            "choices": [],
            "principles": [],
        }

        # Tasks that apply this knowledge
        tasks_result = await self.tasks.get_learning_tasks_for_user(
            self.context, knowledge_focus=[ku_uid]
        )
        if tasks_result.is_ok and tasks_result.value:
            opportunities["tasks"] = [t.uid for t in tasks_result.value]

        # Goals aligned with this knowledge
        opportunities["goals"] = self._find_aligned_goals(ku_uid)

        # Habits that reinforce this knowledge (from context)
        for habit_uid in self.context.active_habit_uids:
            for goal_uid in opportunities["goals"]:
                if (
                    habit_uid in self.context.habits_by_goal.get(goal_uid, [])
                    and habit_uid not in opportunities["habits"]
                ):
                    opportunities["habits"].append(habit_uid)

        # Events where this could be practiced
        for event_uid in self.context.upcoming_event_uids:
            for habit_uid in opportunities["habits"]:
                if (
                    event_uid in self.context.events_by_habit.get(habit_uid, [])
                    and event_uid not in opportunities["events"]
                ):
                    opportunities["events"].append(event_uid)

        return Result.ok(opportunities)

    # =========================================================================
    # METHOD 4: Unblocking Priority Order
    # =========================================================================

    async def get_unblocking_priority_order(self) -> Result[list[tuple[str, int]]]:
        """
        What should I learn first to unlock the most items?

        **Synthesizes:**
        - Context: prerequisites_needed mapping
        - KU service: Readiness status
        - Tasks service: Blocked task counts

        Returns:
            Result containing list of (ku_uid, blocked_count) sorted by impact (highest first)
        """
        blocker_counts: dict[str, int] = {}

        for prereqs in self.context.prerequisites_needed.values():
            for prereq in prereqs:
                if prereq not in self.context.prerequisites_completed:
                    blocker_counts[prereq] = blocker_counts.get(prereq, 0) + 1

        from core.utils.sort_functions import get_second_item

        return Result.ok(sorted(blocker_counts.items(), key=get_second_item, reverse=True))

    # =========================================================================
    # Vector Search Helpers (Phase 1 Enhancement)
    # =========================================================================

    def _generate_learning_query(self) -> str:
        """
        Generate a semantic search query based on user's learning goals and life path.

        Combines:
        - Life path focus
        - Active learning goals
        - Current knowledge context
        """
        query_parts = []

        # Include life path focus
        if self.context.life_path_uid:
            # Extract meaningful terms from life path context
            query_parts.append("learning path knowledge")

        # Include learning goals context
        if self.context.learning_goals:
            query_parts.append("goal-aligned learning")

        # Include current learning focus
        if self.context.current_learning_focus:
            query_parts.append(self.context.current_learning_focus)

        # Default if no context
        if not query_parts:
            query_parts.append("ready to learn knowledge")

        return " ".join(query_parts)

    async def _vector_results_to_learning_steps(
        self,
        vector_results: list[dict[str, Any]],
        max_steps: int,
        consider_goals: bool,
        consider_capacity: bool,
    ) -> Result[list[LearningStep]]:
        """
        Convert vector search results to LearningStep objects.

        Args:
            vector_results: Results from learning_aware_search()
            max_steps: Maximum steps to return
            consider_goals: Whether to weight by goal alignment
            consider_capacity: Whether to filter by capacity

        Returns:
            Result[list[LearningStep]] with full context
        """
        learning_steps = []

        for result in vector_results[: max_steps * 2]:
            node = result["node"]
            ku_uid = node["uid"]
            score = result.get("score", 0.0)

            # Get application opportunities
            applications = await self._get_application_opportunities_for_ku(ku_uid)

            # Count unlocks
            unlocks_count = self._count_items_unlocked_by(ku_uid)

            # Find aligned goals
            aligned_goals = self._find_aligned_goals(ku_uid)

            # Check prerequisites met
            prereqs_needed = self.context.prerequisites_needed.get(ku_uid, [])
            unmet_prereqs = [
                p for p in prereqs_needed if p not in self.context.prerequisites_completed
            ]
            prerequisites_met = len(unmet_prereqs) == 0

            step = LearningStep(
                ku_uid=ku_uid,
                title=node.get("title", f"Knowledge Unit {ku_uid}"),
                rationale=self._generate_learning_rationale(
                    ku_uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=prerequisites_met,
                aligns_with_goals=aligned_goals,
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_time_to_mastery.get(ku_uid, 60),
                priority_score=score,  # Use vector search score
                application_opportunities=applications,
            )

            learning_steps.append(step)

        # Apply capacity filter if requested
        if consider_capacity:
            learning_steps = self._filter_by_capacity(learning_steps)

        return Result.ok(learning_steps[:max_steps])


__all__ = ["LearningIntelligenceMixin"]
