"""
User Stats Aggregator - Profile Hub Data Generation
====================================================

Focused service for generating ProfileHubData with domain statistics.

Responsibilities:
- Generating ProfileHubData from UserContext
- Querying recent activities across domains
- Generating recommendations from context
- Aggregating domain statistics (LEGACY - to be removed)

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressService: Learning progress tracking
- UserActivityService: Activity tracking
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation (THIS FILE)
- UserService: Facade coordinating all sub-services

Architecture:
- Depends on UserCoreService (get user)
- Depends on UserContextBuilder (build context)
- Uses ProfileHubData.from_context() (Pattern 3C)
- Requires Neo4j driver for recent activities query
"""

from typing import TYPE_CHECKING, Any

from core.services.user import UserContext
from core.services.user_stats_types import ProfileHubData
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger(__name__)


class UserStatsAggregator:
    """
    Generate ProfileHubData and aggregate user statistics.

    This service coordinates the generation of comprehensive user statistics
    by leveraging UserContext and ProfileHubData.from_context().

    Pattern 3C + UserContext Integration:
    - Builds UserContext from domain queries (single source of truth)
    - Uses ProfileHubData.from_context() to compute statistical view
    - Returns strongly-typed ProfileHubData with full context

    Architecture:
    - Requires UserCoreService (get user entity)
    - Requires UserContextBuilder (build rich context)
    - Queries Neo4j for recent activities
    - Generates recommendations from context
    """

    def __init__(
        self,
        user_core_service: Any,  # UserCoreService
        context_builder: Any,  # UserContextBuilder
        executor: "QueryExecutor",
    ) -> None:
        """
        Initialize stats aggregator.

        Args:
            user_core_service: UserCoreService for user CRUD
            context_builder: UserContextBuilder for context building
            executor: QueryExecutor for activity queries

        Raises:
            ValueError: If any dependency is None
        """
        if not user_core_service:
            raise ValueError("UserCoreService is required")
        if not context_builder:
            raise ValueError("UserContextBuilder is required")
        if not executor:
            raise ValueError("QueryExecutor is required")

        self.user_core = user_core_service
        self.context_builder = context_builder
        self.executor = executor

    # ========================================================================
    # PROFILE HUB DATA GENERATION
    # ========================================================================

    @with_error_handling("get_profile_hub_data", error_type="database", uid_param="user_uid")
    async def get_profile_hub_data(self, user_uid: str) -> Result[ProfileHubData]:
        """
        Get aggregated data for user profile hub.

        Pattern 3C + UserContext Integration:
        - Builds UserContext from domain queries (single source of truth)
        - Uses ProfileHubData.from_context() to compute statistical view
        - Returns strongly-typed ProfileHubData with full context

        This method gathers comprehensive statistics across all domains:
        - Tasks: Completion rates, active tasks, overdue items
        - Habits: Consistency, streaks, active habits
        - Goals: Progress, on-track vs at-risk, average completion
        - Learning: Knowledge mastered, paths active/completed, mastery levels
        - Recent activities: Latest actions across domains

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[ProfileHubData]: Strongly-typed profile hub data with frozen dataclasses

        Process:
            1. Load user entity (via UserCoreService)
            2. Build UserContext (via UserContextBuilder)
            3. Query recent activities (direct Neo4j query)
            4. Generate recommendations from context
            5. Build ProfileHubData from context (Pattern 3C)
        """
        # Load user via UserCoreService
        user_result = await self.user_core.get_user(user_uid)
        if not user_result.is_ok or not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Build UserContext from domain queries (via UserContextBuilder)
        # This is THE source of truth - contains all UIDs and relationships
        context_result = await self.context_builder.build_user_context(user_uid, user)
        if context_result.is_error:
            return context_result

        context = context_result.value

        # Get recent activities (not yet in context)
        recent_activities = await self._get_recent_activities(user_uid)

        # Generate recommendations from context (rich UID-based recommendations)
        recommendations = self._generate_recommendations_from_context(context)

        # Build ProfileHubData FROM context (Pattern 3C + UserContext)
        # Stats are computed from context, not separate queries
        hub_data = ProfileHubData.from_context(
            user=user,
            context=context,
            recent_activities=recent_activities,
            recommendations=recommendations,
        )

        return Result.ok(hub_data)

    # ========================================================================
    # RECOMMENDATIONS GENERATION
    # ========================================================================

    def _generate_recommendations_from_context(self, context: UserContext) -> list[dict[str, str]]:
        """
        Generate actionable recommendations from UserContext.

        Pattern 3C + UserContext:
        - Uses rich context (UIDs, relationships) instead of just stats
        - Can generate recommendations based on actual entities, not just counts

        Args:
            context: Complete unified user context

        Returns:
            List of recommendation dicts with type, message, priority

        Recommendations Generated:
            - Overdue tasks warning (high priority if > 3)
            - At-risk habits alert (medium priority)
            - Goal focus suggestion (medium priority if many active)
            - Ready to learn opportunities (low priority)
        """
        recommendations = []

        # Task recommendations - use context UIDs
        if len(context.overdue_task_uids) > 3:
            recommendations.append(
                {
                    "type": "tasks",
                    "priority": "high",
                    "message": f"You have {len(context.overdue_task_uids)} overdue tasks - consider reviewing priorities",
                }
            )

        # Habits recommendations
        at_risk_count = len(context.at_risk_habits)
        if at_risk_count > 0:
            recommendations.append(
                {
                    "type": "habits",
                    "priority": "medium",
                    "message": f"{at_risk_count} habits need attention to maintain streaks",
                }
            )

        # Goals recommendations
        if context.primary_goal_focus and len(context.active_goal_uids) > 5:
            recommendations.append(
                {
                    "type": "goals",
                    "priority": "medium",
                    "message": "Many active goals - consider focusing on your primary goal",
                }
            )

        # Learning recommendations
        ready_to_learn = context.get_ready_to_learn()
        if ready_to_learn:
            recommendations.append(
                {
                    "type": "learning",
                    "priority": "low",
                    "message": f"{len(ready_to_learn)} knowledge units ready to learn (prerequisites met)",
                }
            )

        return recommendations

    # ========================================================================
    # RECENT ACTIVITIES QUERY
    # ========================================================================

    async def _get_recent_activities(self, user_uid: str) -> list[dict[str, Any]]:
        """
        Get recent activities across all domains.

        Queries Neo4j for recent actions (completed tasks, mastered knowledge, achieved goals).

        Returns list of activity dicts with:
        - type: Domain type (task, habit, goal, knowledge)
        - action: Action performed (completed, started, mastered, etc.)
        - entity_uid: Entity UID
        - entity_title: Human-readable title
        - timestamp: When it occurred

        Args:
            user_uid: User's unique identifier

        Returns:
            List of recent activity dictionaries (up to 20 total)

        Activity Types:
            - task.completed: Recently completed tasks
            - knowledge.mastered: Recently mastered knowledge units
            - goal.completed: Recently achieved goals
            - habit.practiced: Recently practiced habits (from completions)
        """
        query = """
        MATCH (u:User {uid: $user_uid})

        // Recent completed tasks
        OPTIONAL MATCH (u)-[:HAS_TASK]->(t:Task {status: 'completed'})
        WHERE t.completed_at IS NOT NULL
        WITH u, collect({
            type: 'task',
            action: 'completed',
            entity_uid: t.uid,
            entity_title: t.title,
            timestamp: t.completed_at
        })[0..5] as task_activities

        // Recent mastered knowledge
        OPTIONAL MATCH (u)-[m:MASTERED]->(ku:Ku)
        WHERE m.mastered_at IS NOT NULL
        WITH u, task_activities, collect({
            type: 'knowledge',
            action: 'mastered',
            entity_uid: ku.uid,
            entity_title: ku.title,
            timestamp: m.mastered_at
        })[0..5] as knowledge_activities

        // Recent completed goals
        OPTIONAL MATCH (u)-[:HAS_GOAL]->(g:Goal {status: 'completed'})
        WHERE g.completed_at IS NOT NULL
        With task_activities, knowledge_activities, collect({
            type: 'goal',
            action: 'completed',
            entity_uid: g.uid,
            entity_title: g.title,
            timestamp: g.completed_at
        })[0..5] as goal_activities

        // Combine and sort by timestamp
        UNWIND (task_activities + knowledge_activities + goal_activities) as activity
        RETURN activity
        ORDER BY activity.timestamp DESC
        LIMIT 20
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            logger.warning(f"Error fetching recent activities: {result.error}")
            return []

        records = result.value or []
        return [record["activity"] for record in records if record and record.get("activity")]
