"""
Tasks Search Service - Search and Filtering
============================================

*Last updated: 2026-01-04*

Clean rewrite following CLAUDE.md patterns.
Handles advanced task search and discovery operations.

**Responsibilities:**
- Search tasks by relationships (goal, habit, knowledge)
- Smart task prioritization
- Semantic knowledge search
- Learning-aligned task discovery
- Curriculum task filtering
- Graph-aware faceted search (Phase 4 decomposition)

**Dependencies:**
- TasksOperations (backend protocol)
- UserContextService (optional - for context-aware operations)

Version: 2.0.0
Date: 2026-01-04
Changes:
- v2.0.0: Added graph_aware_faceted_search for One Path Forward decomposition
- v1.0.0: Initial implementation
"""

from __future__ import annotations

from operator import attrgetter, itemgetter, methodcaller
from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.enums import ActivityStatus
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.ku.lp_position import LpPosition
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations


class TasksSearchService(BaseService["BackendOperations[Ku]", Ku]):
    """
    Advanced search and discovery for tasks.


    Source Tag: "tasks_search_service_explicit"
    - Format: "tasks_search_service_explicit" for user-created relationships
    - Format: "tasks_search_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from tasks_search metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # DomainConfig consolidation (January 2026 Phase 2)
    # All configuration in one place, using centralized relationship registry
    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(ActivityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # RELATIONSHIP-BASED SEARCH
    # ========================================================================

    @with_error_handling("get_tasks_for_goal", error_type="database", uid_param="goal_uid")
    async def get_tasks_for_goal(self, goal_uid: str) -> Result[list[Ku]]:
        """
        Get all tasks that fulfill a specific goal.

        Pattern 1 (Graph-Aware Models): Simple query using fulfills_goal_uid field.

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing tasks fulfilling this goal, sorted by contribution
        """
        # Query backend for tasks with this goal
        result = await self.backend.find_by(fulfills_goal_uid=goal_uid)

        if result.is_error:
            return result

        tasks = self._to_domain_models(result.value, KuDTO, Ku)

        # Sort by contribution percentage
        tasks.sort(key=attrgetter("goal_progress_contribution"), reverse=True)

        self.logger.debug(f"Found {len(tasks)} tasks for goal {goal_uid}")
        return Result.ok(tasks)

    @with_error_handling("get_tasks_for_habit", error_type="database", uid_param="habit_uid")
    async def get_tasks_for_habit(self, habit_uid: str) -> Result[list[Ku]]:
        """
        Get all tasks that reinforce a specific habit.

        Pattern 1 (Graph-Aware Models): Simple query using reinforces_habit_uid field.

        Args:
            habit_uid: Habit UID

        Returns:
            Result containing tasks reinforcing this habit
        """
        result = await self.backend.find_by(reinforces_habit_uid=habit_uid)

        if result.is_error:
            return result

        tasks = self._to_domain_models(result.value, KuDTO, Ku)

        self.logger.debug(f"Found {len(tasks)} tasks for habit {habit_uid}")
        return Result.ok(tasks)

    @with_error_handling(
        "get_tasks_applying_knowledge", error_type="database", uid_param="knowledge_uid"
    )
    async def get_tasks_applying_knowledge(self, knowledge_uid: str) -> Result[list[Ku]]:
        """
        Get all tasks that apply specific knowledge.

        GRAPH-NATIVE: Query graph for APPLIES_KNOWLEDGE relationships.

        Args:
            knowledge_uid: Knowledge UID

        Returns:
            Result containing tasks applying this knowledge
        """
        # GRAPH-NATIVE: Query graph for tasks with APPLIES_KNOWLEDGE relationship to this knowledge
        task_uids_result = await self.backend.get_related_uids(
            knowledge_uid, RelationshipName.APPLIES_KNOWLEDGE, direction="incoming"
        )
        if task_uids_result.is_error:
            return Result.fail(task_uids_result.expect_error())

        task_uids = task_uids_result.value

        # Fetch task details for each UID
        tasks = []
        for task_uid in task_uids:
            task_result = await self.backend.get_task(task_uid)
            if task_result.is_ok and task_result.value:
                task = self._to_domain_model(task_result.value, KuDTO, Ku)
                tasks.append(task)

        self.logger.debug(f"Found {len(tasks)} tasks applying knowledge {knowledge_uid}")
        return Result.ok(tasks)

    @with_error_handling(
        "get_blocked_by_prerequisites", error_type="database", uid_param="user_uid"
    )
    async def get_blocked_by_prerequisites(self, user_uid: str) -> Result[list[Ku]]:
        """
        Get tasks blocked by missing prerequisites.

        A task is considered blocked if it has prerequisites (knowledge or tasks)
        that need to be satisfied before it can be started.

        Uses graph-native relationship queries.

        Args:
            user_uid: User UID

        Returns:
            Result containing blocked tasks
        """
        # Get user's tasks
        tasks_result = await self.backend.get_user_entities(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        # Unpack tuple (entities, total_count) from get_user_entities
        entities, _total = tasks_result.value

        # Filter tasks that have any prerequisites (using graph relationships)
        all_tasks = self._to_domain_models(entities, KuDTO, Ku)
        blocked_tasks = []

        for task in all_tasks:
            # Check for knowledge prerequisites
            knowledge_prereqs_result = await self.backend.count_related(
                uid=task.uid,
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing",
            )
            has_knowledge_prereqs = (
                knowledge_prereqs_result.is_ok and knowledge_prereqs_result.value > 0
            )

            # Check for task prerequisites
            task_prereqs_result = await self.backend.count_related(
                uid=task.uid,
                relationship_type=RelationshipName.REQUIRES_PREREQUISITE,
                direction="outgoing",
            )
            has_task_prereqs = task_prereqs_result.is_ok and task_prereqs_result.value > 0

            # Task is blocked if it has any prerequisites
            if has_knowledge_prereqs or has_task_prereqs:
                blocked_tasks.append(task)

        self.logger.debug(f"Found {len(blocked_tasks)} blocked tasks for user {user_uid}")
        return Result.ok(blocked_tasks)

    # ========================================================================
    # SMART PRIORITIZATION
    # ========================================================================

    @with_error_handling("get_prioritized_tasks", error_type="database")
    async def get_prioritized_tasks(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Ku]]:
        """
        Get prioritized tasks based on impact score and context.

        Gets all user tasks and sorts by impact score.

        Args:
            user_context: User context for prioritization,
            limit: Maximum tasks to return

        Returns:
            Result containing prioritized tasks
        """
        # Get all user's tasks
        tasks_result = await self.backend.get_user_entities(user_context.user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        # Unpack tuple (entities, total_count) from get_user_entities
        entities, _total = tasks_result.value

        # Convert to Task models and filter completed
        all_tasks = self._to_domain_models(entities, KuDTO, Ku)
        tasks = [task for task in all_tasks if task.status != ActivityStatus.COMPLETED]

        # Sort by impact score (descending)
        tasks.sort(key=methodcaller("impact_score"), reverse=True)

        # Return limited results
        prioritized = tasks[:limit]
        self.logger.debug(f"Prioritized {len(prioritized)} tasks for user {user_context.user_uid}")
        return Result.ok(prioritized)

    # ========================================================================
    # LEARNING-ALIGNED DISCOVERY
    # ========================================================================

    @with_error_handling("get_learning_relevant_tasks", error_type="database", uid_param="user_uid")
    async def get_learning_relevant_tasks(
        self, user_uid: str, learning_position: LpPosition, limit: int = 10
    ) -> Result[list[Ku]]:
        """
        Get tasks most relevant to user's current learning path position.

        Args:
            user_uid: User identifier,
            learning_position: User's learning path position,
            limit: Maximum tasks to return

        Returns:
            Result containing learning-relevant tasks sorted by relevance
        """
        # Get user's tasks
        tasks_result = await self.backend.get_user_entities(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        # Unpack tuple (entities, total_count) from get_user_entities
        entities, _total = tasks_result.value

        # Score tasks by learning relevance
        all_tasks = self._to_domain_models(entities, KuDTO, Ku)
        task_scores = []
        for task in all_tasks:
            # Skip completed tasks
            if task.status == ActivityStatus.COMPLETED:
                continue

            # GRAPH-NATIVE: Fetch knowledge relationships from graph
            applies_knowledge_result = await self.backend.get_related_uids(
                task.uid, RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
            )
            task_knowledge_uids = (
                applies_knowledge_result.value if applies_knowledge_result.is_ok else []
            )

            task_domain = str(task.priority.value) if task.priority else "general"

            relevance_score = learning_position.assess_task_relevance(
                task_domain, task_knowledge_uids
            )
            task_scores.append((task, relevance_score))

        # Sort by relevance score (highest first)
        task_scores.sort(key=itemgetter(1), reverse=True)

        # Return top tasks
        relevant_tasks = [task for task, score in task_scores[:limit]]

        self.logger.info(
            "Found %d learning-relevant tasks for user %s (from %d total)",
            len(relevant_tasks),
            user_uid,
            len(tasks_result.value),
        )

        return Result.ok(relevant_tasks)

    # ========================================================================
    # CURRICULUM TASK DISCOVERY
    # ========================================================================

    @with_error_handling("get_curriculum_tasks", error_type="database")
    async def get_curriculum_tasks(self) -> Result[list[Ku]]:
        """
        Get all tasks that originated from the curriculum.

        Uses Task.is_from_learning_step() to filter curriculum-driven tasks.

        Returns:
            Result containing list of tasks linked to learning steps
        """
        # Get all tasks
        all_tasks_result = await self.backend.list(QueryLimit.COMPREHENSIVE)
        if all_tasks_result.is_error:
            return Result.fail(all_tasks_result.expect_error())

        # Unpack tuple: backend.list() returns (tasks, total_count)
        tasks_data, _ = all_tasks_result.value

        # Filter using model method
        all_tasks = self._to_domain_models(tasks_data, KuDTO, Ku)
        curriculum_tasks = [task for task in all_tasks if task.is_from_learning_step()]

        self.logger.info(f"Found {len(curriculum_tasks)} curriculum-driven tasks")
        return Result.ok(curriculum_tasks)

    @with_error_handling("get_tasks_for_learning_step", error_type="database", uid_param="step_uid")
    async def get_tasks_for_learning_step(self, step_uid: str) -> Result[list[Ku]]:
        """
        Get all tasks linked to a specific learning step.

        Args:
            step_uid: LearningStep UID

        Returns:
            Result containing list of tasks for this learning step
        """
        # Get all tasks
        all_tasks_result = await self.backend.list(QueryLimit.COMPREHENSIVE)
        if all_tasks_result.is_error:
            return Result.fail(all_tasks_result.expect_error())

        # Unpack tuple: backend.list() returns (tasks, total_count)
        tasks_data, _ = all_tasks_result.value

        # Filter using model method
        all_tasks = self._to_domain_models(tasks_data, KuDTO, Ku)
        step_tasks = [task for task in all_tasks if task.fulfills_learning_step(step_uid)]

        self.logger.info(f"Found {len(step_tasks)} tasks for learning step {step_uid}")
        return Result.ok(step_tasks)

    # ========================================================================
    # GRAPH-BASED SEARCH
    # ========================================================================
    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_user_assigned_tasks", error_type="database", uid_param="user_uid")
    async def get_user_assigned_tasks(
        self, user_uid: str, include_completed: bool = False, limit: int = 100
    ) -> Result[list[Ku]]:
        """
        Get tasks assigned to user via graph traversal.

        Query: (Task)-[:ASSIGNED_TO]->(User)

        Args:
            user_uid: User UID,
            include_completed: Whether to include completed tasks,
            limit: Maximum number of tasks

        Returns:
            Result containing assigned tasks
        """
        # Custom Cypher query for reverse relationship: (Task)-[:ASSIGNED_TO]->(User)
        # This is an incoming relationship from Task's perspective
        status_filter = "" if include_completed else "AND t.status <> 'completed'"
        query = f"""
            MATCH (t:Ku)-[:ASSIGNED_TO]->(u:User {{uid: $user_uid}})
            WHERE t.uid IS NOT NULL {status_filter}
            RETURN t
            ORDER BY t.created_at DESC
            LIMIT $limit
        """

        records, _, _ = await self.backend.driver.execute_query(
            query, {"user_uid": user_uid, "limit": limit}
        )

        # Convert Neo4j nodes to domain models
        tasks = []
        for record in records:
            node = record["t"]
            task = self._to_domain_model(dict(node), KuDTO, Ku)
            tasks.append(task)

        self.logger.debug(f"Found {len(tasks)} assigned tasks for user {user_uid}")
        return Result.ok(tasks)

    @with_error_handling(
        "get_tasks_requiring_knowledge", error_type="database", uid_param="knowledge_uid"
    )
    async def get_tasks_requiring_knowledge(
        self, knowledge_uid: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[dict[str, Any]]]:
        """
        Get tasks that require specific knowledge.

        Optionally check if user has mastered the knowledge.

        Args:
            knowledge_uid: Knowledge UID,
            user_uid: Optional user UID to check mastery,
            limit: Maximum number of tasks

        Returns:
            Result containing tasks with readiness information
        """
        result = await self.backend.get_tasks_requiring_knowledge(knowledge_uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Filter and limit in service layer
        tasks = result.value

        # Filter by user_uid if provided
        if user_uid:
            tasks = [t for t in tasks if getattr(t, "user_uid", None) == user_uid]

        # Apply limit if provided
        if limit:
            tasks = tasks[:limit]

        self.logger.debug(f"Found {len(tasks)} tasks requiring knowledge {knowledge_uid}")
        return Result.ok(tasks)

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH
    # ========================================================================
    # graph_aware_faceted_search() is inherited from BaseService (January 2026)
    # Configured via _graph_enrichment_patterns class attribute above
    # See: BaseService.graph_aware_faceted_search() for implementation

    # ========================================================================
    # INTELLIGENT SEARCH
    # ========================================================================

    @with_error_handling("intelligent_search", error_type="database")
    async def intelligent_search(
        self, query: str, user_uid: str | None = None, limit: int = 50
    ) -> Result[tuple[list[Ku], ParsedSearchQuery]]:
        """
        Natural language search with semantic filter extraction.

        Parses queries like "urgent tech tasks in progress" to extract:
        - Priority filters (urgent → CRITICAL/HIGH)
        - Status filters (in progress → IN_PROGRESS)
        - Domain filters (tech → TECH)

        Args:
            query: Natural language search query
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing (tasks, parsed_query) tuple

        Example:
            >>> result = await search.intelligent_search("urgent tasks in progress")
            >>> tasks, parsed = result.value
            >>> print(f"Filters: {parsed.to_filter_summary()}")
        """
        # Parse query for semantic filters
        parser = SearchQueryParser()
        parsed = parser.parse(query)

        # Build filters from parsed query
        filters: dict[str, object] = {}

        # Apply priority filter (use highest priority if multiple)
        if parsed.priorities:
            highest_priority = parsed.get_highest_priority()
            if highest_priority:
                filters["priority"] = highest_priority.value

        # Apply status filter (use first status if multiple)
        if parsed.statuses:
            filters["status"] = parsed.statuses[0].value

        # Apply domain filter (use first domain if multiple)
        if parsed.domains:
            filters["domain"] = parsed.domains[0].value

        # Execute search
        if filters:
            # Use filtered search via backend
            result = await self.backend.find_by(limit=limit, **filters)
            if result.is_error:
                return Result.fail(result.expect_error())
            tasks = self._to_domain_models(result.value, KuDTO, Ku)
        else:
            # Fall back to text search using cleaned query
            result = await self.search(parsed.text_query, limit=limit)
            if result.is_error:
                return Result.fail(result.expect_error())
            tasks = result.value

        # Filter by user ownership if provided
        if user_uid and tasks:
            tasks = [t for t in tasks if getattr(t, "user_uid", None) == user_uid]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(tasks),
        )

        return Result.ok((tasks, parsed))
