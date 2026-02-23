"""
Tasks Planning Service - Context-First User Planning
=====================================================

Extracted from TasksRelationshipService (December 2025) - Phase 3 refactoring.

**Purpose:** Context-aware planning methods that leverage UserContext (~240 fields)
to provide personalized, filtered, and ranked task queries.

**Pattern:** Context-First - "Filter by readiness, rank by relevance, enrich with insights"

**Why Extracted:**
- Heavy UserContext dependency (HIGH RISK area)
- Separates planning logic from relationship queries
- Enables focused testing with UserContext mocks
- Clearer separation of concerns

**Methods:**
- get_task_dependencies_for_user: Dependencies enriched with context
- get_actionable_tasks_for_user: Ready-to-start tasks ranked by priority
- get_learning_tasks_for_user: Tasks that apply learning knowledge

**Static Helpers:**
- _calculate_readiness_score: Check prerequisites met
- _calculate_relevance_score: Check goal alignment
- _identify_blocking_reasons: What's preventing engagement
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.task.task import Task
from core.services.base_planning_service import BasePlanningService
from core.services.infrastructure import PrerequisiteHelper
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_priority_score, get_relevance_score

if TYPE_CHECKING:
    from core.models.context_types import ContextualDependencies, ContextualTask
    from core.ports import BackendOperations
    from core.services.user.unified_user_context import UserContext


class TasksPlanningService(BasePlanningService["BackendOperations[Task]", Task]):
    """
    Context-aware task planning service.

    Provides personalized task recommendations based on user context.
    All methods use UserContext (~240 fields) for filtering and ranking.

    **Naming Convention:** *_for_user() suffix indicates context-awareness

    Inherits from BasePlanningService:
    - Constructor with backend + relationship_service
    - set_relationship_service() for post-construction wiring
    - _get_entities_by_uids() for batch entity fetching
    - _get_related_uids() for relationship queries
    """

    _domain_name = "Tasks"

    def __init__(
        self,
        backend: BackendOperations[Task],
        relationship_service: Any | None = None,
    ) -> None:
        """
        Initialize service with required backend.

        Args:
            backend: TasksOperations backend (required)
            relationship_service: UnifiedRelationshipService for relationship queries (optional)
        """
        super().__init__(backend=backend, relationship_service=relationship_service)

    # ========================================================================
    # PRIVATE HELPER METHODS (Domain-Specific)
    # ========================================================================

    async def _get_tasks_by_uids(self, uids: list[str]) -> list[Task]:
        """Alias for base class method with domain-specific naming."""
        return await self._get_entities_by_uids(uids)

    async def _find_tasks_for_knowledge(
        self, knowledge_uid: str, user_uid: str, limit: int = 20
    ) -> Result[list[Task]]:
        """
        Find tasks that apply a specific knowledge unit for a user.

        Uses direct Cypher query (Direct Driver pattern) since this cross-domain
        reverse query doesn't map cleanly to UnifiedRelationshipService's generic API.

        Args:
            knowledge_uid: UID of the knowledge unit
            user_uid: UID of the user
            limit: Maximum tasks to return

        Returns:
            Result containing list of Tasks that apply the knowledge unit
        """
        from core.models.task.task import Task
        from core.utils.neo4j_mapper import from_neo4j_node

        query = """
        MATCH (t:Entity)-[:APPLIES_KNOWLEDGE|REQUIRES_KNOWLEDGE]->(ku:Entity {uid: $knowledge_uid})
        WHERE t.user_uid = $user_uid
        RETURN t
        LIMIT $limit
        """
        result = await self.backend.execute_query(
            query, {"knowledge_uid": knowledge_uid, "user_uid": user_uid, "limit": limit}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        tasks = [from_neo4j_node(record["t"], Task) for record in result.value]
        return Result.ok(tasks)

    # ========================================================================
    # CONTEXT-FIRST METHODS
    # ========================================================================
    # These methods leverage UserContext to provide personalized,
    # filtered, and ranked relationship queries.
    #
    # Naming Convention: *_for_user() suffix indicates context-awareness
    #
    # Philosophy: "Filter by readiness, rank by relevance, enrich with insights"

    @with_error_handling(
        "get_task_dependencies_for_user", error_type="database", uid_param="task_uid"
    )
    async def get_task_dependencies_for_user(
        self,
        task_uid: str,
        context: UserContext,
        include_transitive: bool = False,
        max_depth: int = 2,
    ) -> Result[ContextualDependencies]:
        """
        Get task dependencies filtered and ranked by user context.

        **Context-First Pattern:** Returns dependencies enriched with:
        - Readiness scores (prerequisites met?)
        - Relevance scores (goal alignment)
        - Blocking reasons (what's preventing engagement?)
        - Recommendations (what to do next)

        **Context Fields Used:**
        - knowledge_mastery: Filter by user's mastery levels
        - completed_task_uids: Check task prerequisites
        - active_goal_uids: Calculate goal alignment
        - overdue_task_uids: Mark urgency

        Args:
            task_uid: Task to get dependencies for
            context: User's complete context (~240 fields)
            include_transitive: Include dependencies of dependencies
            max_depth: Maximum traversal depth

        Returns:
            ContextualDependencies with enriched, categorized dependencies
        """
        from core.models.context_types import ContextualDependencies, ContextualTask

        # Get raw dependency UIDs and fetch Tasks
        dep_uids = await self._get_related_uids("prerequisite_tasks", task_uid)
        deps = await self._get_tasks_by_uids(dep_uids)

        # Enrich each dependency with context
        enriched = []
        for dep in deps:
            # Get this task's requirements using new API
            dep_knowledge = await self._get_related_uids("prerequisite_knowledge", dep.uid)
            dep_prereq_tasks = await self._get_related_uids("prerequisite_tasks", dep.uid)
            dep_goals: list[str] = []  # Would need goal relationship query

            contextual = ContextualTask.from_entity_and_context(
                uid=dep.uid,
                title=dep.title,
                context=context,
                goal_uids=dep_goals,
                prerequisite_knowledge=dep_knowledge,
                prerequisite_tasks=dep_prereq_tasks,
            )
            enriched.append(contextual)

        # Categorize into ready vs blocked
        ready = [e for e in enriched if e.can_start]
        blocked = [e for e in enriched if not e.can_start]

        # Sort by priority
        ready.sort(key=get_priority_score, reverse=True)
        blocked.sort(key=get_relevance_score, reverse=True)

        # Generate recommendation
        recommendation = ""
        if blocked:
            highest = blocked[0]
            if highest.blocking_reasons:
                recommendation = highest.blocking_reasons[0]
            else:
                recommendation = f"Complete prerequisites for '{highest.title}'"
        else:
            recommendation = "All dependencies ready - proceed with highest priority!"

        return Result.ok(
            ContextualDependencies(
                entity_uid=task_uid,
                entity_type="Task",
                ready_dependencies=tuple(ready),
                blocked_dependencies=tuple(blocked),
                total_blocking_items=len(blocked),
                recommended_next_action=recommendation,
            )
        )

    @with_error_handling("get_actionable_tasks_for_user", error_type="database")
    async def get_actionable_tasks_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[ContextualTask]]:
        """
        Get tasks user can start immediately, ranked by priority.

        **FAIL-FAST PATTERN:** Requires UserContext.active_tasks_rich to be populated.
        If rich context is not available, returns an error explaining why.

        **SKUEL Philosophy:** "All dependencies are REQUIRED - no graceful degradation"
        SKUEL runs at full capacity or not at all.

        **THE KEY METHOD** for daily planning - returns tasks that:
        1. Have all prerequisites met (knowledge mastery >= 0.7)
        2. Are not blocked by other incomplete tasks
        3. Align with user's active goals and principles

        **Context Fields Required:**
        - active_task_uids: User's current tasks
        - active_tasks_rich: Rich task data with graph_context (REQUIRED)
        - knowledge_mastery: Check knowledge prerequisites
        - completed_task_uids: Check task prerequisites
        - active_goal_uids: Calculate goal alignment
        - overdue_task_uids: Mark urgency

        Args:
            context: User's complete context (must have active_tasks_rich populated)
            limit: Maximum tasks to return

        Returns:
            Result[list[ContextualTask]] - sorted by priority (highest first)
            Returns error if active_tasks_rich is not populated
        """
        from core.models.context_types import ContextualTask

        # FAIL-FAST: Validate rich context is available
        rich_tasks = getattr(context, "active_tasks_rich", None)
        if rich_tasks is None or len(rich_tasks) == 0:
            if len(context.active_task_uids) > 0:
                # User has active tasks but rich context not populated
                return Result.fail(
                    Errors.system(
                        message=(
                            f"Rich context not populated for {len(context.active_task_uids)} active tasks. "
                            "MEGA-QUERY may not have been executed. "
                            "Use user_service.get_rich_unified_context() to build complete context."
                        ),
                        operation="get_actionable_tasks_for_user",
                    )
                )
            # No active tasks - return empty list (not an error)
            return Result.ok([])

        # Build lookup from rich context for O(1) access
        rich_tasks_by_uid: dict[str, dict] = {}
        for task_data in rich_tasks:
            task_dict = task_data.get("task", {})
            uid = task_dict.get("uid")
            if uid:
                rich_tasks_by_uid[uid] = task_data

        actionable = []

        for task_uid in context.active_task_uids:
            # FAIL-FAST: Every active task MUST be in rich context
            if task_uid not in rich_tasks_by_uid:
                return Result.fail(
                    Errors.system(
                        message=(
                            f"Task {task_uid} is in active_task_uids but missing from active_tasks_rich. "
                            "Context is inconsistent - MEGA-QUERY may have failed or been incomplete."
                        ),
                        operation="get_actionable_tasks_for_user",
                    )
                )

            task_data = rich_tasks_by_uid[task_uid]
            task_dict = task_data.get("task", {})
            title = task_dict.get("title", "")
            graph_ctx = task_data.get("graph_context", {})

            # Extract from graph_context
            knowledge_uids = [
                k.get("uid") for k in graph_ctx.get("applied_knowledge", []) if k.get("uid")
            ]
            prereq_task_uids = [
                t.get("uid") for t in graph_ctx.get("dependencies", []) if t.get("uid")
            ]
            applies_ku = knowledge_uids

            # Calculate readiness
            readiness = self._calculate_readiness_score(knowledge_uids, prereq_task_uids, context)

            # Skip if not ready
            if readiness < 0.7:
                continue

            # Get goal associations from context
            goal_uids = context.tasks_by_goal.get(task_uid, [])
            if not goal_uids:
                # Reverse lookup: find goals that contain this task
                for g_uid, t_uids in context.tasks_by_goal.items():
                    if task_uid in t_uids:
                        goal_uids.append(g_uid)

            contextual = ContextualTask.from_entity_and_context(
                uid=task_uid,
                title=title,
                context=context,
                goal_uids=goal_uids,
                knowledge_uids=applies_ku,
                prerequisite_knowledge=knowledge_uids,
                prerequisite_tasks=prereq_task_uids,
            )
            actionable.append(contextual)

        # Sort by priority (highest first)
        actionable.sort(key=get_priority_score, reverse=True)

        self.logger.info(
            f"Found {len(actionable)} actionable tasks for user "
            f"(from {len(context.active_task_uids)} active, all from rich context)"
        )

        return Result.ok(actionable[:limit])

    @with_error_handling("get_learning_tasks_for_user", error_type="database")
    async def get_learning_tasks_for_user(
        self,
        context: UserContext,
        knowledge_focus: list[str] | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualTask]]:
        """
        Get tasks that apply knowledge user is currently learning.

        **Philosophy:** "Learn by doing" - find tasks that reinforce learning.

        Returns tasks that APPLY knowledge units the user is actively learning,
        sorted by learning impact.

        **Context Fields Used:**
        - in_progress_knowledge_uids: Knowledge being learned
        - knowledge_mastery: Current mastery levels
        - active_task_uids: User's current tasks

        Args:
            context: User's complete context
            knowledge_focus: Specific knowledge to find tasks for (optional)
            limit: Maximum tasks to return

        Returns:
            List of ContextualTask that apply learning knowledge
        """
        from core.models.context_types import ContextualTask

        # Focus on knowledge user is building
        learning_ku = knowledge_focus or list(context.in_progress_knowledge_uids)

        if not learning_ku:
            # If no knowledge in progress, suggest knowledge with partial mastery
            learning_ku = [
                ku_uid
                for ku_uid, mastery in context.knowledge_mastery.items()
                if 0.3 <= mastery < 0.8  # Building but not mastered
            ][:10]

        learning_tasks = []
        seen_uids: set[str] = set()

        # NOTE: Loop contains iteration-specific error handling - DO NOT migrate to decorator
        for ku_uid in learning_ku:
            # Get tasks that apply this knowledge using direct Cypher
            tasks_result = await self._find_tasks_for_knowledge(
                ku_uid, user_uid=context.user_uid, limit=20
            )

            if tasks_result.is_error:
                continue

            for task in tasks_result.value or []:
                if task.uid in seen_uids:
                    continue
                if task.uid not in context.active_task_uids:
                    continue

                seen_uids.add(task.uid)

                # Get full applied knowledge list using new API
                applies_ku = await self._get_related_uids("knowledge", task.uid)
                if not applies_ku:
                    applies_ku = [ku_uid]

                # Calculate learning impact (more applied knowledge = higher impact)
                learning_impact = len([k for k in applies_ku if k in learning_ku])
                priority = min(1.0, learning_impact * 0.3 + 0.4)

                contextual = ContextualTask.from_entity_and_context(
                    uid=task.uid,
                    title=task.title,
                    context=context,
                    knowledge_uids=applies_ku,
                    readiness_override=0.8,
                    relevance_override=0.7,
                    priority_override=priority,
                )
                learning_tasks.append(contextual)

        # Sort by number of learning knowledge applied
        def get_learning_knowledge_count(task: ContextualTask) -> int:
            """Get count of learning knowledge applied by task."""
            return len([k for k in task.applies_knowledge if k in learning_ku])

        learning_tasks.sort(key=get_learning_knowledge_count, reverse=True)

        self.logger.info(f"Found {len(learning_tasks)} learning tasks for user")
        return Result.ok(learning_tasks[:limit])

    # ========================================================================
    # CONTEXT-FIRST HELPER METHODS (Delegate to PrerequisiteHelper)
    # ========================================================================

    @staticmethod
    def _calculate_readiness_score(
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        mastery_threshold: float = 0.7,
    ) -> float:
        """Calculate readiness score based on prerequisites met.

        Delegates to PrerequisiteHelper for unified logic.
        """
        return PrerequisiteHelper.calculate_readiness_score(
            required_knowledge_uids=required_knowledge_uids,
            required_task_uids=required_task_uids,
            context=context,
            mastery_threshold=mastery_threshold,
        )

    @staticmethod
    def _calculate_relevance_score(
        entity_goal_uids: list[str],
        entity_principle_uids: list[str],
        context: UserContext,
    ) -> float:
        """Calculate relevance score based on goal alignment."""
        if not entity_goal_uids and not entity_principle_uids:
            return 0.5

        goal_score = 0.0
        if entity_goal_uids:
            aligned = len([g for g in entity_goal_uids if g in context.active_goal_uids])
            goal_score = aligned / len(entity_goal_uids)
            if context.primary_goal_focus in entity_goal_uids:
                goal_score = min(1.0, goal_score + 0.2)

        principle_score = 0.0
        if entity_principle_uids:
            aligned = len([p for p in entity_principle_uids if p in context.core_principle_uids])
            principle_score = aligned / len(entity_principle_uids)

        if entity_goal_uids and entity_principle_uids:
            return (goal_score * 0.6) + (principle_score * 0.4)
        elif entity_goal_uids:
            return goal_score
        else:
            return principle_score

    @staticmethod
    def _identify_blocking_reasons(
        required_knowledge: list[str],
        required_tasks: list[str],
        context: UserContext,
        max_reasons: int = 3,
    ) -> list[str]:
        """Identify reasons blocking engagement.

        Delegates to PrerequisiteHelper for unified logic.
        """
        return PrerequisiteHelper.identify_blocking_reasons(
            required_knowledge_uids=required_knowledge,
            required_task_uids=required_tasks,
            context=context,
            max_reasons=max_reasons,
        )
