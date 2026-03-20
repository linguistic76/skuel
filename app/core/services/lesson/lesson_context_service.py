"""
Lesson Context Service - Context-First Knowledge Recommendations
=================================================================

Provides personalized, context-aware knowledge recommendations by leveraging
UserContext to filter by readiness, rank by relevance, and enrich with insights.

Naming Convention: *_for_user() indicates context-awareness.

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_priority_score

if TYPE_CHECKING:
    from core.models.context_types import ContextualKnowledge
    from core.services.user.unified_user_context import UserContext


class LessonContextService:
    """
    Context-first knowledge recommendations using UserContext.

    These methods follow the pattern:
    "Filter by readiness, rank by relevance, enrich with insights"
    """

    def __init__(self, repo: Any = None, neo4j_adapter: Any = None) -> None:
        """
        Initialize with backend and Neo4j adapter.

        Args:
            repo: LessonOperations backend
            neo4j_adapter: Neo4j adapter for graph operations
        """
        if not repo:
            raise ValueError("KU repository is required")
        if not neo4j_adapter:
            raise ValueError("Neo4j adapter is required for context service")

        self.repo = repo
        self.neo4j = neo4j_adapter
        self.logger = get_logger("skuel.services.lesson.context")

    async def _execute_query(
        self, query: str, params: dict[str, Any], operation: str = "execute_query"
    ) -> Result[list[Any]]:
        """
        Execute a Cypher query and return a Result.

        The neo4j_adapter.execute_query() returns a raw list. This helper
        wraps it to return a Result for consistent error handling.

        Args:
            query: Cypher query string
            params: Query parameters
            operation: Operation name for error messages

        Returns:
            Result containing the query results or an error
        """
        from core.utils.exception_types import NEO4J_EXCEPTIONS

        try:
            results = await self.neo4j.execute_query(query, params)
            return Result.ok(results if results is not None else [])
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(Errors.database(operation=operation, message=str(e)))
        except Exception as e:  # safety-net: catch unexpected errors
            return Result.fail(Errors.database(operation=operation, message=str(e)))

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

        # Query for knowledge units where user hasn't mastered
        # and prerequisites are mostly met
        query = """
        MATCH (ku:Entity)
        WHERE NOT ku.uid IN $mastered_uids
          AND ($domain IS NULL OR ku.domain = $domain)

        // Count prerequisites and how many user has mastered
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WITH ku,
             collect(prereq.uid) as prereq_uids,
             count(prereq) as total_prereqs

        // Calculate readiness based on prerequisites
        WITH ku, prereq_uids, total_prereqs,
             size([p IN prereq_uids WHERE p IN $mastered_uids]) as satisfied_prereqs

        WITH ku, prereq_uids, total_prereqs, satisfied_prereqs,
             CASE
               WHEN total_prereqs = 0 THEN 1.0
               ELSE toFloat(satisfied_prereqs) / total_prereqs
             END as readiness

        // Filter for ready-to-learn (>= 70% prerequisites met)
        WHERE readiness >= 0.7

        // Get what this enables (dependents)
        OPTIONAL MATCH (ku)<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               ku.summary as summary,
               readiness,
               total_prereqs,
               satisfied_prereqs,
               prereq_uids,
               count(dependent) as dependent_count
        ORDER BY readiness DESC, dependent_count DESC
        LIMIT $limit
        """

        params = {
            "mastered_uids": mastered_uids,
            "domain": domain,
            "limit": limit,
        }

        results = await self._execute_query(query, params, "get_ready_to_learn_for_user")

        if results.is_error:
            return Result.fail(results.expect_error())

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

        self.logger.debug(f"Found {len(contextual_kus)} ready-to-learn knowledge units for user")
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

        # Query for knowledge required by goals but not mastered
        query = """
        MATCH (goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku:Entity)
        WHERE goal.uid IN $goal_uids
          AND NOT ku.uid IN $mastered_uids

        // Count how many goals need this knowledge
        WITH ku, count(DISTINCT goal) as goals_blocked,
             collect(DISTINCT goal.uid) as blocking_goal_uids

        // Get prerequisite info
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WITH ku, goals_blocked, blocking_goal_uids,
             count(prereq) as prereq_count,
             collect(prereq.uid) as prereq_uids

        // Calculate how many prereqs are satisfied
        WITH ku, goals_blocked, blocking_goal_uids, prereq_count, prereq_uids,
             size([p IN prereq_uids WHERE p IN $mastered_uids]) as satisfied_prereqs

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               goals_blocked,
               blocking_goal_uids,
               prereq_count,
               satisfied_prereqs,
               CASE
                 WHEN prereq_count = 0 THEN 1.0
                 ELSE toFloat(satisfied_prereqs) / prereq_count
               END as readiness
        ORDER BY goals_blocked DESC, readiness DESC
        LIMIT $limit
        """

        params = {
            "goal_uids": target_goals,
            "mastered_uids": mastered_uids,
            "limit": limit,
        }

        results = await self.neo4j.execute_query(query, params)

        if results.is_error:
            return Result.fail(results.expect_error())

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

    @with_error_handling("get_lessons_to_reinforce_for_user", error_type="database")
    async def get_lessons_to_reinforce_for_user(
        self,
        context: "UserContext",
        mastery_threshold: float = 0.7,
        limit: int = 10,
    ) -> Result[list["ContextualKnowledge"]]:
        """
        Get knowledge units the user should reinforce (mastered but decaying).

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
            self.logger.debug("No knowledge units need reinforcement")
            return Result.ok([])

        # Sort by mastery (lowest first - most urgent)
        def get_mastery_score(item: tuple[str, float]) -> float:
            """Get mastery score from (uid, mastery) tuple."""
            return item[1]

        needs_reinforcement.sort(key=get_mastery_score)

        # Query for details on these knowledge units
        uid_list = [uid for uid, _ in needs_reinforcement[: limit * 2]]  # Fetch extra for filtering

        query = """
        UNWIND $uids as uid
        MATCH (ku:Entity {uid: uid})

        // Check if this knowledge is used by active goals
        OPTIONAL MATCH (goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku)
        WHERE goal.uid IN $active_goal_uids

        WITH ku, count(goal) as goal_relevance

        // Check what depends on this knowledge
        OPTIONAL MATCH (ku)<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               goal_relevance,
               count(dependent) as dependent_count
        """

        params = {
            "uids": uid_list,
            "active_goal_uids": list(context.active_goal_uids),
        }

        results = await self.neo4j.execute_query(query, params)

        if results.is_error:
            return Result.fail(results.expect_error())

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

        self.logger.debug(f"Found {len(contextual_kus)} knowledge units needing reinforcement")
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
