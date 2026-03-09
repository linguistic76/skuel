"""
Enhanced Tasks Service - Facade Pattern
========================================

Tasks service facade that delegates to specialized sub-services.

Sub-Services:
- TasksCoreService: CRUD operations
- TasksSearchService: Search and discovery (DomainSearchOperations[Task] protocol)
- TasksProgressService: Progress tracking and completion
- TasksSchedulingService: Scheduling and learning path integration
- UnifiedRelationshipService (TASKS_CONFIG): Dependencies and relationships
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.ports.search_protocols import TasksSearchOperations

# Domain models
from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO

# Analytics engine
from core.services.analytics_engine import (
    AnalyticsEngine,
)

# Base service
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService

# Sub-services
from core.services.tasks import (
    TasksCoreService,
    TasksIntelligenceService,
    TasksPlanningService,
    TasksProgressService,
    TasksSchedulingService,
)
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.activity_domain_config import create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    PRIORITY_SORT_ORDER,
    get_created_at_attr,
    get_project_and_title,
    get_task_due_date_sort_key,
    make_priority_order_getter,
)

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.graph_context import GraphContext
    from core.models.task.task_request import TaskCreateRequest
    from core.ports.query_types import ListContext
    from core.services.user import UserContext


# TypedDicts for analytics dashboard structure (fixes MyPy index errors)
class TaskStatistics(TypedDict):
    """Task statistics for analytics dashboard."""

    total_tasks: int
    recent_tasks: int
    completed_tasks: int
    completion_rate: float
    average_complexity: float
    learning_opportunities_total: int


class LearningPatternsData(TypedDict):
    """Learning patterns data for analytics dashboard."""

    patterns_detected: int
    patterns: list[dict[str, Any]]


class KnowledgeMasteryData(TypedDict):
    """Knowledge mastery data for analytics dashboard."""

    areas_tracked: int
    average_mastery_level: float
    top_mastery_areas: list[dict[str, Any]]


class InsightsData(TypedDict):
    """Insights data for analytics dashboard."""

    insights_generated: int
    key_insights: list[dict[str, Any]]


class AnalyticsStatus(TypedDict):
    """Analytics processing status."""

    patterns_analysis: str
    insights_generation: str
    mastery_tracking: str
    recommendations: str


class TaskAnalyticsDashboard(TypedDict):
    """Complete analytics dashboard data structure."""

    timeframe_days: int
    user_uid: str
    generated_at: str
    task_statistics: TaskStatistics
    learning_patterns: LearningPatternsData
    knowledge_mastery: KnowledgeMasteryData
    insights: InsightsData
    recommendations: list[Any]
    analytics_status: AnalyticsStatus


def _apply_task_secondary_filters(
    tasks: list[Any],
    project: str | None = None,
    assignee: str | None = None,
    due_filter: str | None = None,
) -> list[Any]:
    """Apply secondary filter criteria (project, assignee, due date) to task list.

    Status filtering is handled at Cypher level via get_for_user_filtered.
    """
    today = date.today()

    if project:
        tasks = [t for t in tasks if t.project == project]

    if assignee:
        tasks = [t for t in tasks if getattr(t, "assignee", None) == assignee]

    if due_filter == "today":
        tasks = [t for t in tasks if t.due_date == today]
    elif due_filter == "tomorrow":
        tomorrow = today + timedelta(days=1)
        tasks = [t for t in tasks if t.due_date == tomorrow]
    elif due_filter == "week":
        week_end = today + timedelta(days=7)
        tasks = [t for t in tasks if t.due_date and t.due_date <= week_end]
    elif due_filter == "overdue":
        tasks = [
            t
            for t in tasks
            if t.due_date and t.due_date < today and t.status != EntityStatus.COMPLETED
        ]

    return tasks


def _apply_task_sort(tasks: list[Any], sort_by: str = "due_date") -> list[Any]:
    """Sort tasks by specified field."""
    if sort_by == "due_date":
        return sorted(tasks, key=get_task_due_date_sort_key)
    elif sort_by == "priority":
        priority_sort_key = make_priority_order_getter(PRIORITY_SORT_ORDER)
        return sorted(tasks, key=priority_sort_key)
    elif sort_by == "created_at":
        return sorted(tasks, key=get_created_at_attr, reverse=True)
    elif sort_by == "project":
        return sorted(tasks, key=get_project_and_title)
    return sorted(tasks, key=get_task_due_date_sort_key)


class TasksService(BaseService["TasksOperations", Task]):
    """
    Tasks service facade with specialized sub-services.

    This facade:
    1. Delegates to 7 specialized sub-services for core operations
    2. Uses explicit delegation methods for all sub-service calls
    3. Retains explicit methods for complex orchestration and transformations
    4. Provides clean separation of concerns

    Delegation Methods:
    - Core CRUD: get_task, get_user_tasks, list_tasks, update_task, delete_task
    - Search: get_tasks_for_goal, get_tasks_for_habit, get_prioritized_tasks, etc.
    - Progress: check_prerequisites, unblock_task_if_ready, record_task_completion, etc.
    - Scheduling: create_task_with_context, get_next_learning_task, etc.
    - Analytics: analyze_learning_patterns, generate_task_insights, etc.

    Explicit Methods (custom logic):
    - create_task: Has special user_uid parameter handling
    - get_tasks_batch: Uses backend directly
    - complete_task_with_cascade: Orchestrates knowledge generation
    - get_task_with_dependencies: Transforms result
    - link_task_to_knowledge/goal: Passes specific parameters
    - analyze_task_knowledge_impact: Full orchestration
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        entity_label="Entity",
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: TasksCoreService
    search: TasksSearchOperations  # Forward ref - imported in TYPE_CHECKING
    progress: TasksProgressService
    scheduling: TasksSchedulingService
    planning: TasksPlanningService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService

    def __init__(
        self,
        backend: TasksOperations,
        ku_inference_service=None,
        analytics_engine=None,
        ku_generation_service=None,
        graph_intelligence_service=None,
        event_bus=None,
        ai_service: TasksAIService | None = None,
    ) -> None:
        """
        Initialize enhanced tasks service with specialized sub-services.

        Args:
            backend: Protocol-based backend for task operations,
            ku_inference_service: Service for automatic knowledge inference,
            analytics_engine: AnalyticsEngine for advanced analytics,
            ku_generation_service: InsightGenerationService for automatic knowledge generation,
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics,
            event_bus: Event bus for publishing domain events (optional)
            ai_service: Optional AI service for LLM/embeddings features (January 2026)
        """
        super().__init__(backend, "tasks")

        # AI service (optional - app works without it)
        self.ai: TasksAIService | None = ai_service

        self.logger = get_logger("skuel.services.tasks")

        # Use factory for search and relationships (common sub-services)
        common = create_common_sub_services(
            domain="tasks",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
        )

        # NOTE: Named 'search' for consistency with other domain facades
        # This shadows BaseService.search(), intentionally - we delegate via self.search.search()
        self.search: TasksSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships

        # Core and intelligence need domain-specific parameters - create manually
        self.core = TasksCoreService(
            backend=backend, ku_inference_service=ku_inference_service, event_bus=event_bus
        )

        # Intelligence service now uses BaseAnalyticsService (no AI dependencies)
        # See ADR-030 for the intelligence layer separation
        self.intelligence: TasksIntelligenceService = TasksIntelligenceService(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=self.relationships,
            event_bus=event_bus,
        )

        # Domain-specific sub-services
        self.progress = TasksProgressService(
            backend=backend, analytics_engine=analytics_engine, event_bus=event_bus
        )
        self.scheduling = TasksSchedulingService(backend=backend)
        self.planning = TasksPlanningService(
            backend=backend,
            relationship_service=self.relationships,
        )

        # Analytics engine for direct calls (simplified from TasksAnalyticsService)
        # January 2026: TasksAnalyticsService removed - AnalyticsEngine called directly
        self.analytics_engine = analytics_engine or AnalyticsEngine(
            relationship_service=self.relationships
        )
        self.ku_generation_service = ku_generation_service

        self.logger.info(
            "TasksService facade initialized with 7 sub-services: "
            "core, search, progress, scheduling, planning, relationships, intelligence"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Task entities."""
        return "Entity"

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_task(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_task(*args, **kwargs)

    async def get_user_tasks(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_tasks(*args, **kwargs)

    async def list_tasks(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.list_tasks(*args, **kwargs)

    async def get_user_items_in_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Any:
        return await self.core.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=include_completed,
        )

    async def update_task(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.update_task(*args, **kwargs)

    async def delete_task(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.delete_task(*args, **kwargs)

    # Search delegations
    async def get_tasks_for_goal(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_tasks_for_goal(*args, **kwargs)

    async def get_tasks_for_habit(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_tasks_for_habit(*args, **kwargs)

    async def get_tasks_applying_knowledge(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_tasks_applying_knowledge(*args, **kwargs)

    async def get_blocked_by_prerequisites(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_blocked_by_prerequisites(*args, **kwargs)

    async def get_prioritized_tasks(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_prioritized_tasks(*args, **kwargs)

    async def get_learning_relevant_tasks(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_learning_relevant_tasks(*args, **kwargs)

    async def get_curriculum_tasks(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_curriculum_tasks(*args, **kwargs)

    async def get_tasks_for_learning_step(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_tasks_for_learning_step(*args, **kwargs)

    # Progress delegations
    async def check_prerequisites(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.check_prerequisites(*args, **kwargs)

    async def unblock_task_if_ready(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.unblock_task_if_ready(*args, **kwargs)

    async def record_task_completion(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.record_task_completion(*args, **kwargs)

    async def assign_task_to_user(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.progress.assign_task_to_user(*args, **kwargs)

    # Scheduling delegations
    async def create_task_with_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.create_task_with_context(*args, **kwargs)

    async def create_task_with_learning_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.create_task_with_learning_context(*args, **kwargs)

    async def create_tasks_from_learning_path(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.create_tasks_from_learning_path(*args, **kwargs)

    async def get_next_learning_task(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.get_next_learning_task(*args, **kwargs)

    async def suggest_learning_aligned_tasks(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.suggest_learning_aligned_tasks(*args, **kwargs)

    async def create_task_from_learning_step(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.scheduling.create_task_from_learning_step(*args, **kwargs)

    # Planning delegations
    async def get_task_dependencies_for_user(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.planning.get_task_dependencies_for_user(*args, **kwargs)

    async def get_actionable_tasks_for_user(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.planning.get_actionable_tasks_for_user(*args, **kwargs)

    async def get_learning_tasks_for_user(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.planning.get_learning_tasks_for_user(*args, **kwargs)

    # Relationship delegations
    async def get_task_completion_impact(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_completion_impact(*args, **kwargs)

    async def analyze_task_learning_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_cross_domain_context(*args, **kwargs)

    async def get_task_with_semantic_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_with_semantic_context(*args, **kwargs)

    # Intelligence delegations
    async def analyze_task_learning_metrics(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.analyze_task_learning_metrics(*args, **kwargs)

    async def generate_task_knowledge_insights(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.generate_task_knowledge_insights(*args, **kwargs)

    async def get_learning_opportunities(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_learning_opportunities(*args, **kwargs)

    # ========================================================================
    # EXPLICIT CORE METHODS (custom logic)
    # ========================================================================

    async def create_task(self, task_request: TaskCreateRequest, user_uid: str) -> Result[Task]:
        """
        Create a task with automatic knowledge inference.

        Args:
            task_request: Task creation request
            user_uid: User UID (REQUIRED - fail-fast)

        Returns:
            Result containing created Task
        """
        return await self.core.create_task(task_request, user_uid)

    async def get_tasks_batch(self, uids: list[str]) -> Result[list[Task | None]]:
        """
        Get multiple tasks in one batched query.

        Critical for GraphQL DataLoader batching to prevent N+1 queries.

        Args:
            uids: List of task UIDs to fetch

        Returns:
            Result containing list of Tasks (None for missing UIDs)
            Entities returned in same order as input UIDs
        """
        # Access backend through BaseService
        return await self.backend.get_many(uids)

    # ========================================================================
    # PROGRESS TRACKING - Explicit orchestration method
    # ========================================================================

    async def complete_task_with_cascade(
        self,
        task_uid: str,
        user_context: UserContext,
        actual_minutes: int | None = None,
        quality_score: int | None = None,
    ) -> Result[Task]:
        """Complete a task and cascade updates through the system."""
        # Delegate to progress service for core completion
        result = await self.progress.complete_task_with_cascade(
            task_uid, user_context, actual_minutes, quality_score
        )

        # Trigger automatic knowledge generation - facade orchestration
        if result.is_ok and self.ku_generation_service:
            await self._trigger_knowledge_generation(user_context.user_uid)

        return result

    async def complete_task(
        self,
        uid: str,
        actual_minutes: int | None = None,
        quality_score: int | None = None,
    ) -> Result[Task]:
        """
        Complete a task (StatusRouteFactory compatible).

        Simplified version without user_context for route factory pattern.
        """
        return await self.progress.complete_task_with_cascade(
            uid, user_context=None, actual_minutes=actual_minutes, quality_score=quality_score
        )

    async def uncomplete_task(self, uid: str) -> Result[Task]:
        """
        Mark task as incomplete (StatusRouteFactory compatible).

        Reverts task status to IN_PROGRESS.
        """
        from core.models.enums import EntityStatus

        return await self.core.update_task(uid, {"status": EntityStatus.ACTIVE})

    # ========================================================================
    # RELATIONSHIPS AND DEPENDENCIES - Explicit methods (custom logic)
    # ========================================================================
    # Note: Simple delegations (get_task_completion_impact, analyze_task_learning_context,
    # get_task_with_semantic_context) are auto-generated via _delegations.

    async def get_task_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Task, GraphContext]]:
        """Get task with full graph context using pure Cypher graph intelligence."""
        return await self.relationships.get_with_context(uid, depth)

    async def get_task_with_dependencies(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        """Get task with complete dependency graph."""
        # Use get_with_context with "dependencies" intent
        result = await self.relationships.get_with_context(uid, depth, intent="dependencies")
        if result.is_error:
            return result
        task, context = result.value
        return Result.ok({"task": task, "graph_context": context})

    async def get_task_practice_opportunities(
        self, uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Find practice opportunities related to this task."""
        # Use get_with_context with "practice" intent
        result = await self.relationships.get_with_context(uid, depth, intent="practice")
        if result.is_error:
            return result
        task, context = result.value
        return Result.ok({"task": task, "practice_context": context})

    async def get_task_dependencies(self, task_uid: str) -> Result[list[Task]]:
        """Get task dependencies (both directions)."""
        # Get prerequisite task UIDs
        prereq_result = await self.relationships.get_related_uids("prerequisite_tasks", task_uid)
        if prereq_result.is_error:
            return Result.fail(prereq_result)

        prereq_uids = prereq_result.value
        if not prereq_uids:
            return Result.ok([])

        # Fetch the actual Task objects
        tasks = []
        for uid in prereq_uids:
            task_result = await self.core.get(uid)
            if task_result.is_ok and task_result.value:
                tasks.append(task_result.value)

        return Result.ok(tasks)

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        knowledge_score_required: float = 0.8,
        is_learning_opportunity: bool = False,
    ) -> Result[bool]:
        """Link task to required knowledge unit."""
        return await self.relationships.link_to_knowledge(
            task_uid,
            knowledge_uid,
            knowledge_score_required=knowledge_score_required,
            is_learning_opportunity=is_learning_opportunity,
        )

    async def link_task_to_goal(
        self,
        task_uid: str,
        goal_uid: str,
        contribution_percentage: float = 0.1,
        milestone_uid: str | None = None,
    ) -> Result[bool]:
        """Link task to goal it contributes to."""
        return await self.relationships.link_to_goal(
            task_uid,
            goal_uid,
            contribution_percentage=contribution_percentage,
            milestone_uid=milestone_uid,
        )

    async def create_task_dependency(
        self,
        dependent_task_uid: str,
        blocks_task_uid: str,
        is_hard_dependency: bool = True,
        dependency_type: str = "blocks",
    ) -> Result[bool]:
        """Create dependency between tasks."""
        properties = {
            "is_hard_dependency": is_hard_dependency,
            "dependency_type": dependency_type,
        }
        return await self.relationships.create_relationship(
            "prerequisite_tasks", dependent_task_uid, blocks_task_uid, properties
        )

    async def get_user_assigned_tasks(
        self, user_uid: str, include_completed: bool = False, limit: int = 100
    ) -> Result[list[Task]]:
        """Get tasks assigned to user via graph traversal."""
        # Use backend list with user_uid filter
        filters = {"user_uid": user_uid}
        if not include_completed:
            filters["status__ne"] = "completed"
        result = await self.backend.list(filters=filters, limit=limit)
        if result.is_error:
            return Result.fail(result)
        # list() returns tuple[list[Task], int]
        tasks, _ = result.value
        return Result.ok(tasks)

    async def get_tasks_requiring_knowledge(
        self, knowledge_uid: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Task]]:
        """Get tasks that require specific knowledge (returns Task objects, not dicts)."""
        # Use find_by_semantic_filter to find tasks with relationship to this knowledge
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid,
            min_confidence=0.0,  # Include all relationships
            direction="incoming",
        )

    async def create_semantic_knowledge_relationship(
        self,
        task_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create a semantic relationship between task and knowledge."""
        return await self.relationships.create_semantic_relationship(
            task_uid, knowledge_uid, semantic_type, confidence, notes
        )

    # ========================================================================
    # KNOWLEDGE ANALYSIS - Explicit orchestration method
    # ========================================================================

    async def analyze_task_knowledge_impact(self, task_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze the knowledge impact of a specific task using unified Task model.

        GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.

        Args:
            task_uid: Task identifier

        Returns:
            Result containing knowledge impact analysis
        """
        from core.services.tasks.task_relationships import TaskRelationships

        # Get task from backend
        task_result = await self.get_task(task_uid)
        if task_result.is_error:
            return Result.fail(task_result)

        task = task_result.value

        # GRAPH-NATIVE: Fetch relationship data from graph
        _rels = await TaskRelationships.fetch(task.uid, self.relationships)

        # Use unified Task model knowledge capabilities
        impact_analysis = {
            "task_uid": task.uid,
            "title": task.title,
            "knowledge_complexity_score": task.calculate_knowledge_complexity(),
            "learning_impact_score": task.calculate_learning_impact(),
            "is_knowledge_bridge": task.is_knowledge_bridge(),
            "validates_mastery": task.validates_knowledge_mastery(),
            "enhancement_summary": task.get_knowledge_enhancement_summary(),
            "all_knowledge_connections": task.get_all_knowledge_connections(),
            "combined_knowledge_uids": task.get_combined_knowledge_uids(),
        }

        return Result.ok(impact_analysis)

    # ========================================================================
    # ANALYTICS ENGINE - Direct calls (January 2026)
    # These methods call AnalyticsEngine directly, replacing TasksAnalyticsService.
    # ========================================================================

    async def analyze_learning_patterns(
        self, user_uid: str, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """
        Analyze learning patterns across user's task activities.

        Args:
            user_uid: User to analyze
            timeframe_days: Analysis timeframe in days

        Returns:
            Result containing detected learning patterns
        """
        tasks_result = await self.core.get_user_tasks(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        return await self.analytics_engine.analyze_learning_patterns(
            tasks_result.value, timeframe_days
        )

    async def calculate_knowledge_aware_priorities(
        self, user_uid: str, task_uids: list[str] | None = None
    ) -> Result[list[Any]]:
        """
        Calculate knowledge-aware priority scores for tasks.

        Args:
            user_uid: User whose tasks to prioritize
            task_uids: Specific task UIDs to prioritize (None for all)

        Returns:
            Result containing knowledge-aware priority scores
        """
        from operator import attrgetter

        from core.models.enums import EntityStatus
        from core.services.tasks.task_relationships import TaskRelationships

        tasks_result = await self.core.get_user_tasks(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        all_tasks = tasks_result.value

        # Filter to specific tasks or pending tasks
        if task_uids:
            tasks_to_prioritize = [t for t in all_tasks if t.uid in task_uids]
        else:
            tasks_to_prioritize = [
                t
                for t in all_tasks
                if t.status in [EntityStatus.DRAFT, EntityStatus.ACTIVE, EntityStatus.SCHEDULED]
            ]

        # Get learning patterns
        patterns_result = await self.analyze_learning_patterns(user_uid)
        patterns = patterns_result.value if patterns_result.is_ok else []

        # Fetch relationships and get knowledge UIDs
        import asyncio

        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
        )

        all_knowledge_uids: set[str] = set()
        for task, _rels in zip(all_tasks, rels_list, strict=False):
            all_knowledge_uids.update(task.get_combined_knowledge_uids())

        # Get mastery progressions
        mastery_result = await self.analytics_engine.track_knowledge_mastery_progression(
            all_tasks, list(all_knowledge_uids)
        )
        mastery_progressions = mastery_result.value if mastery_result.is_ok else {}

        # Calculate priorities
        priorities = []
        for task in tasks_to_prioritize:
            priority_result = await self.analytics_engine.calculate_knowledge_aware_priority(
                task, mastery_progressions, patterns
            )
            if priority_result.is_ok:
                priorities.append(priority_result.value)

        priorities.sort(key=attrgetter("final_priority_score"), reverse=True)
        return Result.ok(priorities)

    async def generate_task_insights(
        self, user_uid: str, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """
        Generate insights from user's completed tasks.

        Args:
            user_uid: User to analyze
            timeframe_days: Analysis timeframe in days

        Returns:
            Result containing generated task insights
        """
        from datetime import date, timedelta

        from core.models.enums import EntityStatus

        tasks_result = await self.core.get_user_tasks(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        cutoff_date = date.today() - timedelta(days=timeframe_days)
        completed_tasks = [
            task
            for task in tasks_result.value
            if task.status == EntityStatus.COMPLETED
            and task.completion_date
            and task.completion_date >= cutoff_date
        ]

        patterns_result = await self.analyze_learning_patterns(user_uid, timeframe_days)
        patterns = patterns_result.value if patterns_result.is_ok else []

        return await self.analytics_engine.generate_task_insights(completed_tasks, patterns)

    async def track_knowledge_mastery_progression(
        self, user_uid: str, knowledge_uids: list[str] | None = None
    ) -> Result[dict[str, Any]]:
        """
        Track knowledge mastery progression for user.

        Args:
            user_uid: User to analyze
            knowledge_uids: Specific knowledge UIDs to track (None for all)

        Returns:
            Result containing mastery progressions by knowledge UID
        """
        import asyncio

        from core.services.tasks.task_relationships import TaskRelationships

        tasks_result = await self.core.get_user_tasks(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        all_tasks = tasks_result.value

        # Determine knowledge UIDs to track
        if knowledge_uids is None:
            rels_list = await asyncio.gather(
                *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
            )
            all_knowledge_uids: set[str] = set()
            for task, _rels in zip(all_tasks, rels_list, strict=False):
                all_knowledge_uids.update(task.get_combined_knowledge_uids())
            knowledge_uids = list(all_knowledge_uids)

        return await self.analytics_engine.track_knowledge_mastery_progression(
            all_tasks, knowledge_uids
        )

    # ========================================================================
    # AUTOMATIC KNOWLEDGE GENERATION
    # ========================================================================

    async def _trigger_knowledge_generation(self, user_uid: str) -> None:
        """
        Trigger automatic knowledge generation from completed tasks.

        This method is called automatically when tasks are completed.
        """
        if not self.ku_generation_service:
            return

        try:
            knowledge_result = (
                await self.ku_generation_service.extract_knowledge_from_completed_tasks(
                    user_uid=user_uid, days_back=30, min_tasks=3
                )
            )

            if knowledge_result.is_ok and knowledge_result.value:
                curation_result = await self.ku_generation_service.curate_generated_knowledge(
                    knowledge_result.value
                )

                if curation_result.is_ok:
                    auto_published = curation_result.value.get("auto_publish", [])
                    for knowledge_dto in auto_published:
                        if self.ku_generation_service.ku_service:
                            await self.ku_generation_service.ku_service.create(
                                title=knowledge_dto.title,
                                body=knowledge_dto.content,
                                summary=knowledge_dto.content[:200] + "..."
                                if len(knowledge_dto.content) > 200
                                else knowledge_dto.content,
                                tags=knowledge_dto.tags,
                                domain=str(knowledge_dto.domain.value),
                                **knowledge_dto.metadata,
                            )
        except Exception as e:
            self.logger.warning(f"Knowledge generation failed for user {user_uid}: {e}")

    async def trigger_manual_knowledge_generation(
        self, user_uid: str, days_back: int = 30, min_tasks: int = 3
    ) -> Result[dict[str, Any]]:
        """
        Manually trigger knowledge generation and return results for review.

        Args:
            user_uid: User whose tasks to analyze
            days_back: Days of history to analyze
            min_tasks: Minimum completed tasks needed

        Returns:
            Result containing generation summary and knowledge units
        """
        from datetime import datetime

        from core.utils.result_simplified import Errors

        if not self.ku_generation_service:
            return Result.fail(
                Errors.system(
                    message="Knowledge generation service not available",
                    operation="trigger_manual_knowledge_generation",
                )
            )

        try:
            knowledge_result = (
                await self.ku_generation_service.extract_knowledge_from_completed_tasks(
                    user_uid=user_uid, days_back=days_back, min_tasks=min_tasks
                )
            )

            if knowledge_result.is_error:
                return Result.fail(knowledge_result.expect_error())

            generated_knowledge = knowledge_result.value

            if not generated_knowledge:
                return Result.ok(
                    {
                        "message": "No knowledge could be generated from completed tasks",
                        "generated_count": 0,
                        "curated_knowledge": {},
                    }
                )

            curation_result = await self.ku_generation_service.curate_generated_knowledge(
                generated_knowledge
            )

            if curation_result.is_error:
                return curation_result

            curated_knowledge = curation_result.value

            return Result.ok(
                {
                    "user_uid": user_uid,
                    "analysis_period_days": days_back,
                    "generated_knowledge_count": len(generated_knowledge),
                    "curated_knowledge": curated_knowledge,
                    "statistics": {
                        "auto_publish_ready": len(curated_knowledge.get("auto_publish", [])),
                        "review_recommended": len(curated_knowledge.get("review_recommended", [])),
                        "needs_improvement": len(curated_knowledge.get("needs_improvement", [])),
                        "low_quality": len(curated_knowledge.get("low_quality", [])),
                    },
                    "generation_timestamp": datetime.now().isoformat(),
                }
            )

        except Exception as e:
            self.logger.error(f"Manual knowledge generation failed for user {user_uid}: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Knowledge generation failed: {e!s}",
                    operation="trigger_manual_knowledge_generation",
                )
            )

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: str,
        project: str | None = None,
        assignee: str | None = None,
        due_filter: str | None = None,
        status_filter: str = "active",
        sort_by: str = "due_date",
    ) -> Result[ListContext]:
        """Get filtered and sorted tasks with pre-filter stats.

        Stats via Cypher COUNT (no entity deserialization).
        Status filter pushed to Cypher WHERE; project/assignee/due_filter applied Python-side.
        """
        import asyncio

        stats_result, entities_result = await asyncio.gather(
            self.core.get_stats_for_user(user_uid),
            self.core.get_for_user_filtered(user_uid, status_filter),
        )
        if stats_result.is_error:
            return Result.fail(stats_result)
        if entities_result.is_error:
            return Result.fail(entities_result)
        filtered = _apply_task_secondary_filters(
            entities_result.value, project, assignee, due_filter
        )
        sorted_tasks = _apply_task_sort(filtered, sort_by)
        return Result.ok({"entities": sorted_tasks, "stats": stats_result.value})


# Legacy alias removed - class renamed directly to TasksService
