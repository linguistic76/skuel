"""
Tasks Intelligence Service
==========================

Task-specific intelligence features (NO AI dependencies).

Created: Original November 2025
Updated: January 2026 - Migrated to BaseAnalyticsService (ADR-030)

Provides:
- Behavioral insights and patterns (task-specific)
- Performance analytics and optimization (task-specific)
- Cross-domain context categorization (task-specific)

Domain-agnostic knowledge intelligence (knowledge suggestions, prerequisites,
learning opportunities) was extracted to ActivityKnowledgeIntelligenceService
(March 2026) — those methods work for all 6 activity domains, not just Tasks.

Related sub-services (extracted March 2026):
- TasksProductivityService: Dual-track productivity assessment (ADR-030)
- TasksLearningMetricsService: Task-level learning metrics via Task model
- ActivityKnowledgeIntelligenceService: Knowledge intelligence (all domains)

NOTE: This service does NOT use AI (LLM/embeddings).
All methods are pure graph queries + Python calculations.
See TasksAIService for AI-powered features.

Architecture:
- Uses shared intelligence utilities (NO cross-service dependencies)
- Uses GraphIntelligenceService for graph queries (infrastructure only)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from core.constants import GraphDepth, LearningLoop
from core.models.enums import CompletionStatus, Domain, EntityStatus, Priority
from core.models.enums.neo_labels import NeoLabel
from core.models.graph_context import GraphContext
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.intelligence import (
    GraphContextOrchestrator,
    PatternAnalyzer,
    RecommendationEngine,
    analyze_completion_trend,
)
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations, TasksRelationshipOperations


# =============================================================================
# HELPER FUNCTIONS (SKUEL012 - no lambdas)
# =============================================================================


def _has_high_priority_focus(tasks: Sequence[Any]) -> bool:
    """Check if more than 40% of tasks are high priority."""
    if not tasks:
        return False
    high_priority_count = len(
        [t for t in tasks if t.priority and Priority(t.priority).to_numeric() >= 3]
    )
    return high_priority_count / len(tasks) > 0.4


def _has_detailed_descriptions(tasks: Sequence[Any]) -> bool:
    """Check if more than 60% of tasks have descriptions."""
    if not tasks:
        return False
    with_description = len([t for t in tasks if t.description])
    return with_description / len(tasks) > 0.6


def _extract_completion_hour(task: Any) -> int | None:
    """Extract completion hour from task, or None if not completed."""
    return task.completed_at.hour if task.completed_at else None


class TasksIntelligenceService(BaseAnalyticsService["TasksOperations", Task]):
    """
    Task-specific intelligence service (graph-based, no AI).

    Provides:
    - Behavioral insights and patterns (completion time, procrastination)
    - Performance analytics and optimization (rates, trends, duration calibration)
    - Cross-domain context categorization (TaskCrossContext)

    Domain-agnostic knowledge intelligence was extracted to
    ActivityKnowledgeIntelligenceService (March 2026).

    NOTE: This service does NOT use AI (LLM/embeddings).
    All methods are pure graph queries + Python calculations.
    For AI-powered features, see TasksAIService.
    """

    # Service name for hierarchical logging
    _service_name = "tasks.intelligence"

    def __init__(
        self,
        backend: TasksOperations,
        graph_intelligence_service: GraphIntelligenceService | None = None,
        relationship_service: TasksRelationshipOperations | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize tasks intelligence service (graph-based analytics).

        Args:
            backend: Tasks backend operations (protocol)
            graph_intelligence_service: Graph intelligence service (infrastructure only)
            relationship_service: TasksRelationshipOperations protocol for specialized relationship queries
            event_bus: Event bus for publishing events (optional)

        NOTE: No embeddings_service or llm_service parameters - this is intentional.
        This service uses graph queries and Python, not AI.
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # Initialize GraphContextOrchestrator for get_with_context pattern
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Task, TaskDTO](
                service=self,
                backend_get_method="get_task",
                dto_class=TaskDTO,
                model_class=Task,
                domain=Domain.TASKS,
            )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Task, GraphContext]]:
        """
        Get task with full graph context.

        Protocol method: Uses GraphContextOrchestrator for generic pattern.
        Used by IntelligenceRouteFactory for GET /api/tasks/context route.

        Args:
            uid: Task UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Task, GraphContext) tuple
        """
        if self.orchestrator is None:
            return Result.fail(
                Errors.system(
                    message="Graph intelligence service required for context queries",
                    operation="get_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a task.

        Protocol method: Provides task-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/tasks/insights route.

        Args:
            uid: Task UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict with knowledge prerequisites
            and learning opportunities.
        """
        # Get task
        task_result = await self.backend.get(uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=uid))

        # Get knowledge prerequisites (inline — shared utility, no cross-service dependency)
        from core.utils.intelligence_queries import get_knowledge_prerequisites

        prereq_result = await get_knowledge_prerequisites(
            graph=self.graph_intel, entity_uid=uid, depth=GraphDepth.DEFAULT
        )
        prerequisites = prereq_result.value if prereq_result.is_ok else {}

        # Build insights response
        insights = {
            "task_uid": uid,
            "task_title": task.title,
            "status": task.status.value if task.status else None,
            "priority": task.priority if task.priority else None,
            "knowledge_prerequisites": prerequisites.get("prerequisites", []),
            "has_prerequisites": len(prerequisites.get("prerequisites", [])) > 0,
            "insights": {
                "is_overdue": task.is_overdue()
                if callable(getattr(task, "is_overdue", None))
                else False,
                "is_high_priority": bool(
                    task.priority and Priority(task.priority).to_numeric() >= 3
                ),
                "has_description": bool(task.description),
            },
            "min_confidence": min_confidence,
        }

        return Result.ok(insights)

    # ========================================================================
    # BEHAVIORAL INTELLIGENCE - Tasks-specific implementations
    # ========================================================================

    async def get_behavioral_insights(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze behavioral patterns from tasks.

        Analyzes:
        - Task completion patterns (time of day, day of week)
        - Procrastination patterns
        - Energy-task matching
        - Context productivity patterns

        Returns:
            Result containing:
            - behavior_patterns: Identified patterns
            - success_factors: Key success factors
            - recommendations: Behavioral recommendations
        """
        self.logger.info(f"Analyzing behavioral insights for user {user_uid}")

        # Get completed tasks in period
        cutoff_date = datetime.now() - timedelta(days=period_days)
        tasks_result = await self.backend.find_by(user_uid=user_uid, status=CompletionStatus.DONE)

        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        tasks = tasks_result.value
        recent_tasks = [
            task for task in tasks if task.completion_date and task.completion_date >= cutoff_date
        ]

        # Analyze completion patterns
        behavior_patterns = self._analyze_completion_patterns(recent_tasks)

        # Identify success factors
        success_factors = self._identify_success_factors(recent_tasks)

        # Generate recommendations
        recommendations = self._generate_behavioral_recommendations(
            behavior_patterns, success_factors
        )

        return Result.ok(
            {
                "behavior_patterns": behavior_patterns,
                "success_factors": success_factors,
                "recommendations": recommendations,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                    "tasks_analyzed": len(recent_tasks),
                },
            }
        )

    # ========================================================================
    # PERFORMANCE INTELLIGENCE - Tasks-specific implementations
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Analyze task performance metrics.

        Analyzes:
        - Completion rate trends
        - Average completion time
        - Priority distribution
        - Efficiency patterns

        Returns:
            Result containing:
            - metrics: Performance metrics
            - trends: Trend analysis
            - optimization_opportunities: Optimization suggestions
        """
        self.logger.info(f"Analyzing performance metrics for user {user_uid}")

        # Get tasks in period
        cutoff_date = datetime.now() - timedelta(days=period_days)
        tasks_result = await self.backend.find_by(user_uid=user_uid)

        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        all_tasks = tasks_result.value
        period_tasks = [task for task in all_tasks if task.created_at >= cutoff_date]

        # Calculate metrics
        # Note: Tasks use EntityStatus, not CompletionStatus (which is for habits)
        completed_tasks = [t for t in period_tasks if t.status == EntityStatus.COMPLETED]
        completion_rate = len(completed_tasks) / len(period_tasks) if period_tasks else 0.0

        metrics = {
            "total_tasks": len(period_tasks),
            "completed_tasks": len(completed_tasks),
            "completion_rate": round(completion_rate * 100, 1),
            "in_progress_tasks": len([t for t in period_tasks if t.status == EntityStatus.ACTIVE]),
            "overdue_tasks": len(
                [
                    t
                    for t in period_tasks
                    if t.due_date
                    and t.due_date < datetime.now().date()
                    and t.status != EntityStatus.COMPLETED
                ]
            ),
        }

        # Analyze trends
        trends = self._analyze_performance_trends(period_tasks)

        # Identify optimization opportunities
        optimizations = self._identify_optimization_opportunities(period_tasks, metrics)

        # Include learned duration calibration (ADR-048)
        learning_state = {}
        state_result = await self.backend.get_user_learning_state(user_uid)
        if state_result.is_ok:
            state = state_result.value
            ratio = state.get("task_duration_ratio")
            count = state.get("task_completion_count") or 0
            learning_state = {
                "learned_duration_ratio": ratio,
                "learning_sample_count": count,
                "has_sufficient_learning_data": count >= LearningLoop.MIN_SAMPLES_TASK_DURATION,
            }

        return Result.ok(
            {
                "metrics": metrics,
                "trends": trends,
                "optimization_opportunities": optimizations,
                "learning_state": learning_state,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                },
            }
        )

    # ========================================================================
    # CROSS-DOMAIN CONTEXT - Domain-specific categorization
    # ========================================================================

    @with_error_handling(
        "categorize_cross_domain_context", error_type="system", uid_param="task_uid"
    )
    async def categorize_cross_domain_context(
        self, task_uid: str, raw_context: list[dict[str, Any]]
    ) -> Result[dict[str, Any]]:
        """
        Categorize raw graph context into task-specific groups.

        This contains the domain-specific intelligence that was previously
        in the backend's get_task_cross_domain_context() method.

         Architecture:
        - Backend provides raw graph data via get_domain_context_raw()
        - Intelligence service performs domain-specific categorization
        - This achieves true separation: Backend = primitives, Intelligence = domain logic

        Args:
            task_uid: Task UID
            raw_context: Raw graph context from backend (list of entities with metadata)

        Returns:
            Result containing TaskCrossContext grouped by relationship semantic:
            - prerequisites: Tasks that must be completed first (DEPENDS_ON - outgoing)
            - dependents: Tasks that depend on this one (DEPENDS_ON - incoming)
            - required_knowledge: Knowledge needed to complete task (REQUIRES_KNOWLEDGE)
            - applied_knowledge: Knowledge this task applies (APPLIES_KNOWLEDGE)
            - contributing_goals: Goals this task fulfills (CONTRIBUTES_TO_GOAL, FULFILLS_GOAL)
        """
        from core.models.graph.path_aware_types import (
            PathAwareGoal,
            PathAwareKnowledge,
            PathAwareTask,
            TaskCrossContext,
        )

        # Group by entity type and relationship
        prerequisites = []
        dependents = []
        required_knowledge = []
        applied_knowledge = []
        contributing_goals = []

        for entity in raw_context:
            labels = entity["labels"]
            via_rels = entity["via_relationships"]

            # Task dependencies (bidirectional DEPENDS_ON)
            # Use directional markers (->DEPENDS_ON / <-DEPENDS_ON) to distinguish
            depends_on = RelationshipName.DEPENDS_ON.value
            if NeoLabel.ENTITY.value in labels and (
                f"->{depends_on}" in via_rels
                or depends_on in via_rels
                or f"<-{depends_on}" in via_rels
            ):
                task_entity = PathAwareTask(
                    uid=entity["uid"],
                    title=entity["title"],
                    distance=entity["distance"],
                    path_strength=entity["path_strength"],
                    via_relationships=via_rels,
                )

                # Check for directional relationship markers
                if f"->{depends_on}" in via_rels or depends_on in via_rels:
                    # Outgoing DEPENDS_ON = this task depends on the related task (prerequisite)
                    prerequisites.append(task_entity)
                elif f"<-{depends_on}" in via_rels:
                    # Incoming DEPENDS_ON = related task depends on this one (dependent)
                    dependents.append(task_entity)

            # Knowledge requirements (REQUIRES_KNOWLEDGE, APPLIES_KNOWLEDGE)
            elif NeoLabel.ENTITY.value in labels and (
                RelationshipName.REQUIRES_KNOWLEDGE.value in via_rels
                or RelationshipName.APPLIES_KNOWLEDGE.value in via_rels
            ):
                knowledge_entity = PathAwareKnowledge(
                    uid=entity["uid"],
                    title=entity["title"],
                    distance=entity["distance"],
                    path_strength=entity["path_strength"],
                    via_relationships=via_rels,
                )
                if RelationshipName.REQUIRES_KNOWLEDGE.value in via_rels:
                    required_knowledge.append(knowledge_entity)
                elif RelationshipName.APPLIES_KNOWLEDGE.value in via_rels:
                    applied_knowledge.append(knowledge_entity)

            # Goals this task contributes to/fulfills
            elif NeoLabel.ENTITY.value in labels and (
                RelationshipName.CONTRIBUTES_TO_GOAL.value in via_rels
                or RelationshipName.FULFILLS_GOAL.value in via_rels
            ):
                contributing_goals.append(
                    PathAwareGoal(
                        uid=entity["uid"],
                        title=entity["title"],
                        distance=entity["distance"],
                        path_strength=entity["path_strength"],
                        via_relationships=via_rels,
                    )
                )

        # Create path-aware context
        context = TaskCrossContext(
            task_uid=task_uid,
            prerequisites=prerequisites,
            dependents=dependents,
            required_knowledge=required_knowledge,
            applied_knowledge=applied_knowledge,
            contributing_goals=contributing_goals,
        )

        # Return dict representation for compatibility
        return Result.ok(
            {
                "task_uid": context.task_uid,
                "prerequisites": [
                    {
                        "uid": t.uid,
                        "title": t.title,
                        "distance": t.distance,
                        "path_strength": t.path_strength,
                        "via_relationships": t.via_relationships,
                    }
                    for t in context.prerequisites
                ],
                "dependents": [
                    {
                        "uid": t.uid,
                        "title": t.title,
                        "distance": t.distance,
                        "path_strength": t.path_strength,
                        "via_relationships": t.via_relationships,
                    }
                    for t in context.dependents
                ],
                "required_knowledge": [
                    {
                        "uid": k.uid,
                        "title": k.title,
                        "distance": k.distance,
                        "path_strength": k.path_strength,
                        "via_relationships": k.via_relationships,
                    }
                    for k in context.required_knowledge
                ],
                "applied_knowledge": [
                    {
                        "uid": k.uid,
                        "title": k.title,
                        "distance": k.distance,
                        "path_strength": k.path_strength,
                        "via_relationships": k.via_relationships,
                    }
                    for k in context.applied_knowledge
                ],
                "contributing_goals": [
                    {
                        "uid": g.uid,
                        "title": g.title,
                        "distance": g.distance,
                        "path_strength": g.path_strength,
                        "via_relationships": g.via_relationships,
                    }
                    for g in context.contributing_goals
                ],
            }
        )

    # ========================================================================
    # HELPER METHODS - Task-specific analysis functions
    # ========================================================================

    def _analyze_completion_patterns(self, tasks: list) -> list[dict[str, Any]]:
        """Analyze task completion patterns."""
        # Uses PatternAnalyzer from shared intelligence utilities (consolidation)
        peak_time = PatternAnalyzer.find_peak_time(tasks, _extract_completion_hour)
        if peak_time:
            return [
                {
                    "pattern": "peak_productivity",
                    "description": f"Most tasks completed around {peak_time['peak_hour']}:00",
                    "confidence": peak_time["confidence"],
                }
            ]
        return []

    def _identify_success_factors(self, tasks: list) -> list[str]:
        """Identify factors contributing to successful task completion."""
        if not tasks:
            return []
        # Uses PatternAnalyzer from shared intelligence utilities (consolidation)
        return PatternAnalyzer.identify_factors(
            tasks,
            conditions=[
                (
                    _has_high_priority_focus,
                    "High priority focus drives completion",
                ),
                (
                    _has_detailed_descriptions,
                    "Detailed task descriptions improve completion",
                ),
            ],
        )

    def _generate_behavioral_recommendations(
        self, patterns: list[dict], success_factors: list[str]
    ) -> list[str]:
        """Generate behavioral recommendations."""
        # Uses RecommendationEngine from shared intelligence utilities (consolidation)
        engine = RecommendationEngine()

        # Add recommendations based on patterns
        for pattern in patterns:
            if pattern.get("pattern") == "peak_productivity":
                engine.add_message(
                    f"Schedule high-priority tasks during your peak hours: {pattern.get('description', '')}"
                )

        # Add recommendations based on success factors
        engine.add_conditional(
            "Detailed task descriptions improve completion" in success_factors,
            "Continue adding detailed descriptions to tasks",
        )

        return engine.build()

    def _analyze_performance_trends(self, tasks: list) -> dict[str, Any]:
        """Analyze performance trends over time from task completion data."""
        # Uses analyze_completion_trend from shared intelligence utilities (consolidation)
        completed_count = sum(1 for task in tasks if task.status == CompletionStatus.DONE)
        result = analyze_completion_trend(completed_count, len(tasks))

        return {
            "completion_trend": result["trend"],
            "efficiency_trend": "stable",  # Could be enhanced with time tracking
            "quality_trend": "stable",  # Could be enhanced with quality metrics
            "completion_rate": result["completion_rate"],
            "tasks_analyzed": result["analyzed_count"],
        }

    def _identify_optimization_opportunities(
        self, tasks: list, metrics: dict
    ) -> list[dict[str, Any]]:
        """Identify opportunities for optimization based on tasks and metrics."""
        opportunities = []

        # Check for low completion rate (from metrics)
        if metrics["completion_rate"] < 70:
            opportunities.append(
                {
                    "area": "task_completion",
                    "suggestion": "Consider breaking down large tasks into smaller, manageable subtasks",
                    "potential_impact": "15-25% improvement in completion rate",
                }
            )

        # Check for overdue tasks (from metrics)
        if metrics.get("overdue_tasks", 0) > 5:
            opportunities.append(
                {
                    "area": "deadline_management",
                    "suggestion": "Review and adjust deadlines based on actual completion times",
                    "potential_impact": "Reduced stress and more realistic planning",
                }
            )

        # Analyze task title lengths (from tasks)
        if tasks:
            avg_title_length = sum(len(task.title) for task in tasks) / len(tasks)
            if avg_title_length < 10:
                # Explicit type annotation to allow mixed str/int values
                opportunity: dict[str, Any] = {
                    "area": "task_clarity",
                    "suggestion": "Add more descriptive task titles for better clarity",
                    "potential_impact": "Improved focus and reduced ambiguity",
                    "tasks_affected": len(tasks),
                }
                opportunities.append(opportunity)

        # Analyze task descriptions (from tasks)
        if tasks:
            tasks_without_description = sum(1 for task in tasks if not task.description)
            if tasks_without_description > len(tasks) * 0.5:  # Over 50% lack descriptions
                # Explicit type annotation to allow mixed str/int values
                # P3: Renamed to avoid redefinition error
                documentation_opportunity: dict[str, Any] = {
                    "area": "task_documentation",
                    "suggestion": "Add descriptions to tasks for better context and execution",
                    "potential_impact": "Clearer expectations and easier execution",
                    "tasks_needing_description": tasks_without_description,
                }
                opportunities.append(documentation_opportunity)

        # Duration calibration insights (ADR-048)
        learned_ratio = metrics.get("learned_duration_ratio")
        if learned_ratio is not None:
            if learned_ratio > 1.3:
                opportunities.append(
                    {
                        "area": "duration_estimation",
                        "suggestion": "Tasks consistently take longer than estimated — add buffer time",
                        "potential_impact": "More realistic planning and less overcommitment",
                        "learned_ratio": round(learned_ratio, 2),
                    }
                )
            elif learned_ratio < 0.7:
                opportunities.append(
                    {
                        "area": "duration_estimation",
                        "suggestion": "Tasks consistently finish faster than estimated — take on more",
                        "potential_impact": "Better use of available time",
                        "learned_ratio": round(learned_ratio, 2),
                    }
                )

        return opportunities
