"""
Goals Planning Service - Context-First User Planning Methods
=============================================================

Extracted from GoalsRelationshipService (December 2025) - Phase 2 refactoring.

**Purpose:** Methods that leverage UserContext to provide personalized,
filtered, and ranked goal queries for users.

**Pattern:** Uses UserContext (~240 fields) for context-aware filtering and ranking.

**Why Extracted:**
- Heavy UserContext dependency (HIGH RISK)
- Separates planning logic from pure graph queries
- Easier testing with context mocks
- Single responsibility: context-first planning

**Naming Convention:** `*_for_user()` suffix indicates context-awareness

**Philosophy:** "Filter by readiness, rank by relevance, enrich with insights"

**Methods:**
- get_advancing_goals_for_user: Goals with active momentum
- get_stalled_goals_for_user: Goals needing attention
- get_achievable_goals_for_user: Goals near completion

**Static Helpers:**
- _calculate_readiness_score_static: Prerequisites met calculation
- _calculate_relevance_score_static: Goal/principle alignment calculation

Version: 2.0.0
Date: 2026-01-08
History:
- v1.0.0: Initial extraction from GoalsRelationshipService
- v2.0.0: Migrated from GoalsGraphNativeService to UnifiedRelationshipService
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.goal.goal import Goal
from core.services.base_planning_service import BasePlanningService
from core.services.protocols.domain_protocols import GoalsOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.context_types import ContextualGoal
    from core.services.relationships import UnifiedRelationshipService
    from core.services.user.unified_user_context import UserContext


class GoalsPlanningService(BasePlanningService[GoalsOperations, Goal]):
    """
    Context-first user planning methods for Goals.

    Requires UserContext for personalized goal recommendations.
    Uses UnifiedRelationshipService for relationship queries.

    Inherits from BasePlanningService:
    - Constructor with backend + relationship_service
    - set_relationship_service() for post-construction wiring
    - _get_entities_by_uids() for batch entity fetching
    - _get_related_uids() for relationship queries
    """

    _domain_name = "Goals"

    @property
    def relationships(self) -> UnifiedRelationshipService | None:
        """Alias for _relationship_service (backward compatibility)."""
        return self._relationship_service

    @relationships.setter
    def relationships(self, value: UnifiedRelationshipService | None) -> None:
        """Alias setter for _relationship_service (backward compatibility)."""
        self._relationship_service = value

    # ========================================================================
    # CONTEXT-FIRST METHODS (November 25, 2025)
    # ========================================================================
    # These methods leverage UserContext to provide personalized,
    # filtered, and ranked relationship queries for goals.
    #
    # Naming Convention: *_for_user() suffix indicates context-awareness
    #
    # Philosophy: "Filter by readiness, rank by relevance, enrich with insights"

    @with_error_handling("get_advancing_goals_for_user", error_type="database")
    async def get_advancing_goals_for_user(
        self,
        context: UserContext,
        min_progress: float = 0.1,
        limit: int = 10,
    ) -> Result[list[ContextualGoal]]:
        """
        Get goals with active momentum, ranked by relevance and progress.

        **FAIL-FAST PATTERN:** Requires UserContext.active_goals_rich to be populated.
        If rich context is not available, returns an error explaining why.

        **SKUEL Philosophy:** "All dependencies are REQUIRED - no graceful degradation"
        SKUEL runs at full capacity or not at all.

        **THE KEY METHOD** for goal tracking - returns goals that:
        1. Have recent progress (tasks/habits contributing)
        2. Are not stalled (progress >= min_progress)
        3. Are aligned with user's priorities

        **Context Fields Required:**
        - active_goal_uids: User's current goals
        - active_goals_rich: Rich goal data with graph_context (REQUIRED)
        - goal_progress: Progress percentages by goal
        - tasks_by_goal: Tasks contributing to each goal
        - habits_by_goal: Habits reinforcing each goal
        - at_risk_goals: Goals needing attention
        - primary_goal_focus: User's main focus

        Args:
            context: User's complete context (must have active_goals_rich populated)
            min_progress: Minimum progress to consider "advancing"
            limit: Maximum goals to return

        Returns:
            Result[list[ContextualGoal]] - sorted by priority (highest first)
            Returns error if active_goals_rich is not populated
        """
        from core.models.context_types import ContextualGoal

        # FAIL-FAST: Validate rich context is available
        rich_goals = getattr(context, "active_goals_rich", None)
        if rich_goals is None or len(rich_goals) == 0:
            if len(context.active_goal_uids) > 0:
                # User has active goals but rich context not populated
                return Result.fail(
                    Errors.system(
                        message=(
                            f"Rich context not populated for {len(context.active_goal_uids)} active goals. "
                            "MEGA-QUERY may not have been executed. "
                            "Use user_service.get_rich_unified_context() to build complete context."
                        ),
                        operation="get_advancing_goals_for_user",
                    )
                )
            # No active goals - return empty list (not an error)
            return Result.ok([])

        # Build lookup from rich context for O(1) access
        rich_goals_by_uid: dict[str, dict] = {}
        for goal_data in rich_goals:
            goal_dict = goal_data.get("goal", {})
            uid = goal_dict.get("uid")
            if uid:
                rich_goals_by_uid[uid] = goal_data

        advancing_goals = []

        for goal_uid in context.active_goal_uids:
            # FAIL-FAST: Every active goal MUST be in rich context
            if goal_uid not in rich_goals_by_uid:
                return Result.fail(
                    Errors.system(
                        message=(
                            f"Goal {goal_uid} is in active_goal_uids but missing from active_goals_rich. "
                            "Context is inconsistent - MEGA-QUERY may have failed or been incomplete."
                        ),
                        operation="get_advancing_goals_for_user",
                    )
                )

            goal_data = rich_goals_by_uid[goal_uid]
            goal_dict = goal_data.get("goal", {})
            title = goal_dict.get("title", str(goal_uid))
            graph_ctx = goal_data.get("graph_context", {})

            # Extract from graph_context
            knowledge_uids = [
                k.get("uid") for k in graph_ctx.get("required_knowledge", []) if k.get("uid")
            ]
            principle_uids = [
                p.get("uid") for p in graph_ctx.get("aligned_principles", []) if p.get("uid")
            ]

            # Get current progress from context
            progress = context.goal_progress.get(goal_uid, 0.0)

            # Skip stalled goals
            if progress < min_progress:
                continue

            # Calculate readiness (knowledge prerequisites met)
            readiness = self._calculate_readiness_score_static(knowledge_uids, [], context)

            # Get contributing entities from context
            contributing_tasks = context.tasks_by_goal.get(goal_uid, [])
            contributing_habits = context.habits_by_goal.get(goal_uid, [])

            # Calculate relevance based on alignment
            relevance = self._calculate_relevance_score_static([goal_uid], principle_uids, context)

            # Higher relevance for primary focus
            if goal_uid == context.primary_goal_focus:
                relevance = min(1.0, relevance + 0.3)

            # Calculate urgency
            is_at_risk = goal_uid in context.at_risk_goals
            urgency = 0.8 if is_at_risk else 0.3

            priority = (readiness * 0.3) + (relevance * 0.4) + (progress * 0.2) + (urgency * 0.1)

            # Identify learning gaps
            learning_gaps = [
                ku_uid
                for ku_uid in knowledge_uids
                if context.knowledge_mastery.get(ku_uid, 0.0) < 0.7
            ]

            contextual = ContextualGoal(
                uid=goal_uid,
                title=title,
                readiness_score=readiness,
                relevance_score=relevance,
                priority_score=priority,
                current_progress=progress,
                contributing_tasks=tuple(contributing_tasks),
                contributing_habits=tuple(contributing_habits),
                knowledge_required=tuple(knowledge_uids),
                is_at_risk=is_at_risk,
                learning_gaps=tuple(learning_gaps),
            )
            advancing_goals.append(contextual)

        # Sort by priority (highest first)
        advancing_goals.sort(key=self._get_priority_score, reverse=True)

        self.logger.info(
            f"Found {len(advancing_goals)} advancing goals for user "
            f"(from {len(context.active_goal_uids)} active, all from rich context)"
        )

        return Result.ok(advancing_goals[:limit])

    @with_error_handling("get_stalled_goals_for_user", error_type="database")
    async def get_stalled_goals_for_user(
        self,
        context: UserContext,
        max_progress: float = 0.1,
        limit: int = 10,
    ) -> Result[list[ContextualGoal]]:
        """
        Get goals with minimal progress, identifying blockers.

        Helps identify goals that need attention by showing:
        1. Goals with low progress
        2. What's blocking progress (missing knowledge, no habits)
        3. Recommended next actions

        **Context Fields Used:**
        - active_goal_uids: User's current goals
        - goal_progress: Progress percentages
        - knowledge_mastery: Identify knowledge gaps
        - tasks_by_goal: Check for contributing tasks
        - habits_by_goal: Check for supporting habits

        Args:
            context: User's complete context
            max_progress: Maximum progress to consider "stalled"
            limit: Maximum goals to return

        Returns:
            List of ContextualGoal for stalled goals with blockers
        """
        from core.models.context_types import ContextualGoal

        stalled_goals = []

        for goal_uid in context.active_goal_uids:
            # Get goal
            goal_result = await self.backend.get(goal_uid)
            if goal_result.is_error or not goal_result.value:
                continue

            goal = goal_result.value

            # Get progress
            progress = context.goal_progress.get(goal_uid, 0.0)

            # Only include stalled goals
            if progress > max_progress:
                continue

            # Get requirements via relationship service
            knowledge_uids = []
            habit_uids = []
            if self.relationships:
                knowledge_result = await self.relationships.get_related_uids("knowledge", goal_uid)
                habits_result = await self.relationships.get_related_uids("habits", goal_uid)
                knowledge_uids = knowledge_result.value if knowledge_result.is_ok else []
                habit_uids = habits_result.value if habits_result.is_ok else []

            # Identify blocking reasons
            blocking_reasons = []

            # Check knowledge gaps
            knowledge_gaps = []
            for ku_uid in knowledge_uids:
                mastery = context.knowledge_mastery.get(ku_uid, 0.0)
                if mastery < 0.7:
                    knowledge_gaps.append(ku_uid)
                    blocking_reasons.append(f"Missing knowledge: {ku_uid} ({mastery:.0%})")

            # Check for supporting system
            contributing_tasks = context.tasks_by_goal.get(goal_uid, [])
            contributing_habits = context.habits_by_goal.get(goal_uid, [])

            if not contributing_tasks:
                blocking_reasons.append("No active tasks contributing to this goal")
            if not contributing_habits and habit_uids:
                blocking_reasons.append("Has required habits but none active")

            # Calculate scores
            readiness = self._calculate_readiness_score_static(knowledge_uids, [], context)
            relevance = 0.7  # Stalled goals are still relevant

            # Get title safely
            title = getattr(goal, "title", str(goal_uid))

            contextual = ContextualGoal(
                uid=goal_uid,
                title=title,
                readiness_score=readiness,
                relevance_score=relevance,
                priority_score=relevance * (1 - progress),  # Higher priority for lower progress
                current_progress=progress,
                contributing_tasks=tuple(contributing_tasks),
                contributing_habits=tuple(contributing_habits),
                knowledge_required=tuple(knowledge_uids),
                is_at_risk=True,  # Stalled = at risk
                blocking_reasons=tuple(blocking_reasons[:3]),
                learning_gaps=tuple(knowledge_gaps),
            )
            stalled_goals.append(contextual)

        # Sort by priority (most stalled first)
        stalled_goals.sort(key=self._get_current_progress)

        self.logger.info(f"Found {len(stalled_goals)} stalled goals for user")

        return Result.ok(stalled_goals[:limit])

    @with_error_handling("get_achievable_goals_for_user", error_type="database")
    async def get_achievable_goals_for_user(
        self,
        context: UserContext,
        min_progress: float = 0.7,
        limit: int = 5,
    ) -> Result[list[ContextualGoal]]:
        """
        Get goals near completion, prioritized for finishing.

        **Near-win psychology:** Goals close to completion deserve extra
        attention to maintain momentum and build confidence.

        **Context Fields Used:**
        - active_goal_uids: User's current goals
        - goal_progress: Progress percentages
        - tasks_by_goal: Final tasks to complete

        Args:
            context: User's complete context
            min_progress: Minimum progress to consider "achievable"
            limit: Maximum goals to return

        Returns:
            List of ContextualGoal for nearly complete goals
        """
        from core.models.context_types import ContextualGoal

        achievable_goals = []

        for goal_uid in context.active_goal_uids:
            # Get progress
            progress = context.goal_progress.get(goal_uid, 0.0)

            # Only include near-completion goals
            if progress < min_progress:
                continue

            # Get goal
            goal_result = await self.backend.get(goal_uid)
            if goal_result.is_error or not goal_result.value:
                continue

            goal = goal_result.value

            # Get remaining requirements via relationship service
            knowledge_uids = []
            unlocks = []
            if self.relationships:
                knowledge_result = await self.relationships.get_related_uids("knowledge", goal_uid)
                knowledge_uids = knowledge_result.value if knowledge_result.is_ok else []

                # Generate unlocks (what completing this goal enables)
                subgoals_result = await self.relationships.get_related_uids("subgoals", goal_uid)
                unlocks = subgoals_result.value if subgoals_result.is_ok else []

            contributing_tasks = context.tasks_by_goal.get(goal_uid, [])
            contributing_habits = context.habits_by_goal.get(goal_uid, [])

            # Identify what's left
            remaining_knowledge = [
                ku_uid
                for ku_uid in knowledge_uids
                if context.knowledge_mastery.get(ku_uid, 0.0) < 0.9
            ]

            # Calculate priority (closer = higher priority)
            priority = progress * 1.2  # Boost near-completion

            # Get title safely
            title = getattr(goal, "title", str(goal_uid))

            contextual = ContextualGoal(
                uid=goal_uid,
                title=title,
                readiness_score=1.0,  # Near completion = ready
                relevance_score=0.9,  # High relevance
                priority_score=min(1.0, priority),
                current_progress=progress,
                contributing_tasks=tuple(contributing_tasks),
                contributing_habits=tuple(contributing_habits),
                knowledge_required=tuple(remaining_knowledge),
                unlocks=tuple(unlocks),
            )
            achievable_goals.append(contextual)

        # Sort by progress (closest to completion first)
        achievable_goals.sort(key=self._get_current_progress, reverse=True)

        self.logger.info(f"Found {len(achievable_goals)} achievable goals for user")

        return Result.ok(achievable_goals[:limit])

    # ========================================================================
    # CONTEXT-FIRST HELPER METHODS (Static versions)
    # ========================================================================

    @staticmethod
    def _calculate_readiness_score_static(
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        mastery_threshold: float = 0.7,
    ) -> float:
        """Calculate readiness score based on prerequisites met."""
        total = len(required_knowledge_uids) + len(required_task_uids)
        if total == 0:
            return 1.0

        met = 0
        for ku_uid in required_knowledge_uids:
            if context.knowledge_mastery.get(ku_uid, 0.0) >= mastery_threshold:
                met += 1

        for task_uid in required_task_uids:
            if task_uid in context.completed_task_uids:
                met += 1

        return met / total

    @staticmethod
    def _calculate_relevance_score_static(
        entity_goal_uids: list[str],
        entity_principle_uids: list[str],
        context: UserContext,
    ) -> float:
        """Calculate relevance score based on goal and principle alignment."""
        if not entity_goal_uids and not entity_principle_uids:
            return 0.5

        goal_score = 0.0
        if entity_goal_uids:
            aligned = len([g for g in entity_goal_uids if g in context.active_goal_uids])
            goal_score = aligned / len(entity_goal_uids) if entity_goal_uids else 0
            if context.primary_goal_focus in entity_goal_uids:
                goal_score = min(1.0, goal_score + 0.2)

        principle_score = 0.0
        if entity_principle_uids:
            aligned = len([p for p in entity_principle_uids if p in context.core_principle_uids])
            principle_score = aligned / len(entity_principle_uids) if entity_principle_uids else 0

        if entity_goal_uids and entity_principle_uids:
            return (goal_score * 0.6) + (principle_score * 0.4)
        elif entity_goal_uids:
            return goal_score
        else:
            return principle_score

    @staticmethod
    def _get_priority_score(goal: ContextualGoal) -> float:
        """Get priority score for sorting (avoids lambda)."""
        return goal.priority_score

    @staticmethod
    def _get_current_progress(goal: ContextualGoal) -> float:
        """Get current progress for sorting (avoids lambda)."""
        return goal.current_progress
