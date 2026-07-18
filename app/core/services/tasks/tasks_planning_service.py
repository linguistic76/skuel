"""
Tasks Planning Service - Context-First User Planning
=====================================================

Extracted from the former TasksRelationshipService. Now uses UnifiedRelationshipService.

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
from core.models.type_hints import EntityUID, UserUID
from core.services.base_planning_service import BasePlanningService
from core.services.cross_domain import KnowledgeApplyingTask
from core.services.infrastructure import PrerequisiteChecker
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_priority_score, get_relevance_score

if TYPE_CHECKING:
    from core.models.context_types import ContextualDependencies, ContextualTask
    from core.ports.domain_protocols import TasksOperations
    from core.ports.query_types import RichEntityItem
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.user.unified_user_context import RichUserContext, UserContext


class TasksPlanningService(BasePlanningService["TasksOperations", Task]):
    """
    Context-aware task planning service.

    Provides personalized task recommendations based on user context.
    All methods use UserContext (~240 fields) for filtering and ranking.

    **Naming Convention:** *_for_user() suffix indicates context-awareness

    Inherits from BasePlanningService:
    - Constructor with backend + relationship_service
    - _get_entities_by_uids() for batch entity fetching
    - _get_related_uids() for relationship queries
    """

    _domain_name = "Tasks"

    def __init__(
        self,
        backend: TasksOperations,
        cross_domain_query: CrossDomainQueryService,
        relationship_service: Any | None = None,
    ) -> None:
        """
        Initialize service with required backend and cross-domain query service.

        Args:
            backend: TasksOperations backend (required)
            cross_domain_query: CrossDomainQueryService for multi-label reads (required)
            relationship_service: UnifiedRelationshipService for relationship queries (optional)
        """
        super().__init__(backend=backend, relationship_service=relationship_service)
        self.cross_domain_query = cross_domain_query

    # ========================================================================
    # PRIVATE HELPER METHODS (Domain-Specific)
    # ========================================================================

    async def _get_tasks_by_uids(self, uids: list[str]) -> list[Task]:
        """Alias for base class method with domain-specific naming."""
        return await self._get_entities_by_uids(uids)

    async def _find_tasks_for_knowledge(
        self, knowledge_uid: str, user_uid: UserUID, limit: int = 20
    ) -> Result[tuple[KnowledgeApplyingTask, ...]]:
        """
        Find tasks that apply a specific knowledge unit for a user.

        Delegates to ``CrossDomainQueryService.get_tasks_applying_knowledge`` —
        a single-query, typed cross-domain read. Returns lightweight
        ``KnowledgeApplyingTask`` projections (uid + title + edge type) because
        the single caller (``get_learning_tasks_for_user``) only reads those
        two fields — reconstructing a full ``Task`` would be waste.
        """
        result = await self.cross_domain_query.get_tasks_applying_knowledge(
            EntityUID(knowledge_uid), user_uid, limit
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.tasks)

    # ========================================================================
    # CONTEXT-FIRST METHODS
    # ========================================================================
    # These methods leverage UserContext to provide personalized,
    # filtered, and ranked relationship queries.
    #
    # Naming Convention: *_for_user() suffix indicates context-awareness
    #
    # Philosophy: "Filter by readiness, rank by relevance, enrich with insights"

    async def _get_transitive_dependency_uids(self, task_uid: str, max_depth: int) -> list[str]:
        """Fetch transitive dependency UIDs via variable-length DEPENDS_ON traversal.

        Args:
            task_uid: Root task UID
            max_depth: Maximum traversal depth (clamped to 1..10)

        Returns:
            Deduplicated list of dependency UIDs (excludes the root task)
        """
        from core.models.relationship_names import RelationshipName

        result = await self.backend.get_transitive_dependencies(
            task_uid, RelationshipName.DEPENDS_ON, max_depth
        )
        if result.is_error:
            self.logger.warning(f"Transitive dependency query failed: {result.error}")
            return []
        return result.value

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
            include_transitive: Include transitive dependencies (dependencies of dependencies)
            max_depth: Maximum traversal depth for transitive queries (1..10, default 2)

        Returns:
            ContextualDependencies with enriched, categorized dependencies
        """
        from core.models.context_types import ContextualDependencies, ContextualTask

        # Get dependency UIDs — direct or transitive
        if include_transitive:
            dep_uids = await self._get_transitive_dependency_uids(task_uid, max_depth)
        else:
            dep_uids = await self._get_related_uids("prerequisite_tasks", EntityUID(task_uid))
        deps = await self._get_tasks_by_uids(dep_uids)

        # Batch-fetch goals for all deps in one Cypher round-trip.
        goals_batch = await self.cross_domain_query.get_goals_for_tasks_batch(
            [dep.uid for dep in deps]
        )
        goals_by_task = goals_batch.value if not goals_batch.is_error else {}

        # Enrich each dependency with context
        enriched = []
        for dep in deps:
            dep_knowledge = await self._get_related_uids("prerequisite_knowledge", dep.uid)
            dep_prereq_tasks = await self._get_related_uids("prerequisite_tasks", dep.uid)
            dep_goals: list[str] = [g.uid for g in goals_by_task.get(dep.uid, ())]

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
                entity_uid=EntityUID(task_uid),
                entity_type="Task",
                ready_dependencies=tuple(ready),
                blocked_dependencies=tuple(blocked),
                total_blocking_items=len(blocked),
                recommended_next_action=recommendation,
            )
        )

    @with_error_handling("get_actionable_tasks_for_user", error_type="database")
    async def get_actionable_tasks_for_user(  # skuel-lint: disable=SKUEL029 -- facade-delegated: TasksService awaits this via delegation
        self,
        context: RichUserContext,
        limit: int = 10,
    ) -> Result[list[ContextualTask]]:
        """
        Get tasks user can start immediately, ranked by priority.

        **FAIL-FAST PATTERN:** Requires UserContext.entities_rich["tasks"] to be populated.
        If rich context is not available, returns an error explaining why.

        **SKUEL Philosophy:** "All dependencies are REQUIRED - no graceful degradation"
        SKUEL runs at full capacity or not at all.

        **THE KEY METHOD** for daily planning - returns tasks that:
        1. Have all prerequisites met (knowledge mastery >= 0.7)
        2. Are not blocked by other incomplete tasks
        3. Align with user's active goals and principles

        **Context Fields Required:**
        - active_task_uids: User's current tasks
        - entities_rich["tasks"]: Rich task data with graph_context (REQUIRED)
        - knowledge_mastery: Check knowledge prerequisites
        - completed_task_uids: Check task prerequisites
        - active_goal_uids: Calculate goal alignment
        - overdue_task_uids: Mark urgency

        Args:
            context: User's complete context (must have entities_rich["tasks"] populated)
            limit: Maximum tasks to return

        Returns:
            Result[list[ContextualTask]] - sorted by priority (highest first)
            Raises RichContextRequiredError if context was not built via build_rich().
        """
        from core.models.context_types import ContextualTask

        # Rich context is compile-time enforced via `context: RichUserContext`.
        # Build lookup from rich context for O(1) access
        rich_tasks_by_uid: dict[str, RichEntityItem] = {}
        for task_data in context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
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
                            f"Task {task_uid} is in active_task_uids but missing from entities_rich['tasks']. "
                            "Context is inconsistent - MEGA-QUERY may have failed or been incomplete."
                        ),
                        operation="get_actionable_tasks_for_user",
                    )
                )

            task_data = rich_tasks_by_uid[task_uid]
            task_dict = task_data.get("entity", {})
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

            # Get goal associations from context (tasks_by_goal is rich-context only)
            tasks_by_goal = context.tasks_by_goal_or_empty()
            goal_uids = tasks_by_goal.get(task_uid, [])
            if not goal_uids:
                # Reverse lookup: find goals that contain this task
                for g_uid, t_uids in tasks_by_goal.items():
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
    # CONTEXT-FIRST HELPER METHODS (Delegate to PrerequisiteChecker)
    # ========================================================================

    @staticmethod
    def _calculate_readiness_score(
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        mastery_threshold: float = 0.7,
    ) -> float:
        """Calculate readiness score based on prerequisites met.

        Delegates to PrerequisiteChecker for unified logic.
        """
        return PrerequisiteChecker.calculate_readiness_score(
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

        Delegates to PrerequisiteChecker for unified logic.
        """
        return PrerequisiteChecker.identify_blocking_reasons(
            required_knowledge_uids=required_knowledge,
            required_task_uids=required_tasks,
            context=context,
            max_reasons=max_reasons,
        )
