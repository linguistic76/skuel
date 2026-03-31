"""
Path Step Context Service - Context-First Knowledge Recommendations
====================================================================

Provides personalized, context-aware knowledge recommendations by leveraging
UserContext to filter by readiness, rank by relevance, and enrich with insights.

Naming Convention: *_for_user() indicates context-awareness.

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_priority_score

if TYPE_CHECKING:
    from core.models.context_types import ContextualKnowledge
    from core.services.user.unified_user_context import UserContext


class PsContextService:
    """
    Context-first knowledge recommendations using UserContext.

    These methods follow the pattern:
    "Filter by readiness, rank by relevance, enrich with insights"
    """

    def __init__(self, repo: Any = None) -> None:
        """
        Initialize with backend.

        Args:
            repo: Backend for path step operations
        """
        if not repo:
            raise ValueError("Path step repository is required")

        self.repo = repo
        self.logger = get_logger("skuel.services.ps.context")

    # ========================================================================
    # CONTEXT-FIRST METHODS
    # ========================================================================

    @with_error_handling("get_ready_to_learn_for_user", error_type="database")
    async def get_ready_to_learn_for_user(
        self,
        context: "UserContext",
        domain: str | None = None,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        """
        Get knowledge units the user is ready to learn (prerequisites met).

        Context-First Pattern:
        - Filters by user's current mastery (knowledge_mastery field)
        - Ranks by goal alignment (active_goal_uids field)
        - Enriches with application opportunities

        Args:
            context: User's unified context with mastery data
            domain: Optional domain filter
            limit: Maximum results to return

        Returns:
            Result containing list of ContextualKnowledge objects
        """
        from core.models.context_types import ContextualKnowledge

        # Get mastered knowledge UIDs from context
        mastered_uids = list(context.knowledge_mastery.keys())

        results = await self.repo.find_ready_to_learn(mastered_uids, domain, limit)

        if results.is_error:
            return Result.fail(results)

        # Convert to ContextualKnowledge objects
        contextual_kus: list[ContextualKnowledge] = []
        for record in results.value:
            uid = record.get("uid", "")
            title = record.get("title", "")
            readiness = record.get("readiness", 0.0)
            prereq_uids = record.get("prereq_uids", [])
            dependent_count = record.get("dependent_count", 0)

            # Find application opportunities (tasks/habits that apply this knowledge)
            application_opps = self._find_application_opportunities(uid, context)

            contextual_ku = ContextualKnowledge.from_entity_and_context(
                uid=uid,
                title=title,
                context=context,
                prerequisite_uids=prereq_uids,
                application_task_uids=application_opps,
                dependent_count=dependent_count,
                readiness_override=readiness,  # Use Cypher-computed readiness
                weights=(0.5, 0.3, 0.2),
            )
            contextual_kus.append(contextual_ku)

        # Sort by priority score
        contextual_kus.sort(key=get_priority_score, reverse=True)

        self.logger.debug(f"Found {len(contextual_kus)} ready-to-learn path steps for user")
        return Result.ok(contextual_kus)

    @with_error_handling("get_learning_gaps_for_user", error_type="database")
    async def get_learning_gaps_for_user(
        self,
        context: "UserContext",
        goal_uid: str | None = None,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        """
        Get knowledge gaps blocking user's progress toward goals.

        Context-First Pattern:
        - Analyzes active goals from context (active_goal_uids)
        - Finds knowledge required by goals but not mastered
        - Ranks by impact (how many goals blocked)

        Args:
            context: User's unified context with goal and mastery data
            goal_uid: Optional specific goal to analyze (defaults to all active goals)
            limit: Maximum results to return

        Returns:
            Result containing list of ContextualKnowledge objects representing gaps
        """
        from core.models.context_types import ContextualKnowledge

        # Get target goal UIDs
        target_goals = [goal_uid] if goal_uid else list(context.active_goal_uids)

        if not target_goals:
            # No active goals = no goal-based learning gaps
            self.logger.debug("No active goals for learning gap analysis")
            return Result.ok([])

        # Get mastered knowledge UIDs from context
        mastered_uids = list(context.knowledge_mastery.keys())

        results = await self.repo.find_learning_gaps(target_goals, mastered_uids, limit)

        if results.is_error:
            return Result.fail(results)

        # Convert to ContextualKnowledge objects
        contextual_kus: list[ContextualKnowledge] = []
        for record in results.value:
            uid = record.get("uid", "")
            title = record.get("title", "")
            goals_blocked = record.get("goals_blocked", 0)
            blocking_goal_uids = record.get("blocking_goal_uids", [])
            readiness = record.get("readiness", 0.0)
            prereq_uids = record.get("prereq_uids", [])

            # Relevance is high because this blocks goals
            relevance = min(1.0, goals_blocked / max(1, len(target_goals)))

            contextual_ku = ContextualKnowledge.from_entity_and_context(
                uid=uid,
                title=title,
                context=context,
                prerequisite_uids=prereq_uids,  # Drives prerequisite_count
                application_task_uids=blocking_goal_uids,  # Goals that need this
                dependent_count=goals_blocked,
                readiness_override=readiness,  # Use Cypher-computed readiness
                relevance_override=relevance,
                weights=(0.4, 0.6),  # 2D: readiness + relevance (impact-weighted)
            )
            contextual_kus.append(contextual_ku)

        # Sort by priority score
        contextual_kus.sort(key=get_priority_score, reverse=True)

        self.logger.debug(
            f"Found {len(contextual_kus)} learning gaps for user (goals: {len(target_goals)})"
        )
        return Result.ok(contextual_kus)

    @with_error_handling("get_steps_to_reinforce_for_user", error_type="database")
    async def get_steps_to_reinforce_for_user(
        self,
        context: "UserContext",
        mastery_threshold: float = 0.7,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        """
        Get path steps the user should reinforce (mastered but decaying).

        Context-First Pattern:
        - Finds knowledge at risk of decay (low mastery after initial learning)
        - Prioritizes knowledge used in active goals/tasks
        - Suggests reinforcement opportunities

        Args:
            context: User's unified context with mastery data
            mastery_threshold: Mastery level below which reinforcement is suggested
            limit: Maximum results to return

        Returns:
            Result containing list of ContextualKnowledge objects needing reinforcement
        """
        from core.models.context_types import ContextualKnowledge

        # Get knowledge with mastery below threshold (but > 0, meaning started)
        needs_reinforcement = [
            (uid, mastery)
            for uid, mastery in context.knowledge_mastery.items()
            if 0 < mastery < mastery_threshold
        ]

        if not needs_reinforcement:
            self.logger.debug("No path steps need reinforcement")
            return Result.ok([])

        # Sort by mastery (lowest first - most urgent)
        def get_mastery_score(item: tuple[str, float]) -> float:
            """Get mastery score from (uid, mastery) tuple."""
            return item[1]

        needs_reinforcement.sort(key=get_mastery_score)

        # Query for details on these knowledge units
        uid_list = [uid for uid, _ in needs_reinforcement[: limit * 2]]  # Fetch extra for filtering

        results = await self.repo.find_reinforcement_candidates(
            uid_list, list(context.active_goal_uids)
        )

        if results.is_error:
            return Result.fail(results)

        # Build a lookup for query results
        ku_data = {}
        for record in results.value:
            ku_data[record.get("uid")] = record

        # Convert to ContextualKnowledge objects
        contextual_kus: list[ContextualKnowledge] = []
        for uid, mastery in needs_reinforcement:
            if uid not in ku_data:
                continue

            data = ku_data[uid]
            title = data.get("title", "")
            goal_relevance = data.get("goal_relevance", 0)
            dependent_count = data.get("dependent_count", 0)

            # Relevance based on goal usage
            relevance = (
                min(1.0, goal_relevance / max(1, len(context.active_goal_uids)))
                if context.active_goal_uids
                else 0.5
            )

            contextual_ku = ContextualKnowledge.from_entity_and_context(
                uid=uid,
                title=title,
                context=context,
                application_task_uids=list(context.active_task_uids[:3]),
                dependent_count=dependent_count,
                substance_score=mastery,  # Use mastery as substance proxy
                readiness_override=0.9,  # Already learned
                relevance_override=relevance,
                weights=(0.5, 0.3, 0.2),  # decay_urgency, relevance, impact
            )
            contextual_kus.append(contextual_ku)

            if len(contextual_kus) >= limit:
                break

        # Sort by priority score
        contextual_kus.sort(key=get_priority_score, reverse=True)

        self.logger.debug(f"Found {len(contextual_kus)} path steps needing reinforcement")
        return Result.ok(contextual_kus)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    @staticmethod
    def _calculate_knowledge_relevance(
        ku_uid: str,
        context: "UserContext",
    ) -> float:
        """
        Calculate relevance of a knowledge unit based on user context.

        Factors:
        - Used by active goals
        - Applied by active tasks
        - Reinforced by active habits

        Returns:
            Relevance score (0.0-1.0)
        """
        relevance = 0.0

        # Check if required by active goals (via tasks_by_goal proxy)
        # Higher relevance if knowledge is foundational to goals
        if context.active_goal_uids:
            relevance += 0.3

        # Check if applied in active tasks (via active_task_uids)
        if context.active_task_uids:
            relevance += 0.3

        # Check if part of current learning focus (via learning_path_step_uids)
        if context.learning_path_step_uids:
            relevance += 0.2

        # Check substance score for this knowledge
        if ku_uid in context.knowledge_mastery:
            # Partially mastered knowledge is highly relevant (finish what you started)
            mastery = context.knowledge_mastery[ku_uid]
            if 0 < mastery < 0.9:
                relevance += 0.2

        return min(1.0, relevance)

    @staticmethod
    def _find_application_opportunities(
        ku_uid: str,
        context: "UserContext",
    ) -> list[str]:
        """
        Find tasks/habits where user can apply this knowledge.

        Returns:
            List of task/habit UIDs that apply this knowledge
        """
        opportunities = []

        # Active tasks are potential application opportunities
        # In a full implementation, we'd query the graph for APPLIES_KNOWLEDGE
        # For now, return active task UIDs as proxies
        opportunities.extend(list(context.active_task_uids)[:3])

        return opportunities
