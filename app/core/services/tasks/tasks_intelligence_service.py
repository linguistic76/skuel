"""
Tasks Intelligence Service
==========================

Task-specific intelligence features (NO AI dependencies).

Architecture: Shell delegates to 3 focused mixins in this directory:
  _core_intelligence_mixin.py    — get_task_with_context, categorize_cross_domain_context
  _analytics_mixin.py            — get_behavioral_insights, performance helpers
  _productivity_mixin.py         — analyze_learning_patterns, calculate_knowledge_aware_priorities,
                                   generate_task_insights, track_knowledge_mastery_progression,
                                   analyze_task_learning_metrics, generate_task_knowledge_insights

Created: Original November 2025
Updated: January 2026 - Migrated to BaseAnalyticsService (ADR-030)
Updated: April 2026 - Decomposed into focused mixins
Updated: April 2026 - Absorbed TasksLearningMetricsService (symmetry refactor):
  its two methods were task-level analytics mis-labeled as a "learning" service;
  folded back into _productivity_mixin alongside sibling analytics methods.

Provides:
- Behavioral insights and patterns (task-specific)
- Performance analytics and optimization (task-specific)
- Cross-domain context categorization (task-specific)
- Task-level learning metrics (knowledge complexity, bridge detection, mastery)

Domain-agnostic knowledge intelligence (knowledge suggestions, prerequisites,
learning opportunities) was extracted to ActivityKnowledgeIntelligenceService
(March 2026) — those methods work for all 6 activity domains, not just Tasks.

Related sub-services (extracted March 2026):
- TasksProductivityService: Dual-track productivity assessment (ADR-030)
- ActivityKnowledgeIntelligenceService: Knowledge intelligence (all domains)

NOTE: This service does NOT use AI (LLM/embeddings).
All methods are pure graph queries + Python calculations.
See TasksAIService for AI-powered features.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth, LearningLoop
from core.models.enums import Domain, EntityStatus, Priority
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import EntityUID, UserUID
from core.services.analytics_engine import AnalyticsEngine
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.tasks._analytics_mixin import _AnalyticsMixin
from core.services.tasks._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.tasks._productivity_mixin import _ProductivityMixin
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.ports.query_types import KnowledgePrerequisitesResult
    from core.services.relationships import UnifiedRelationshipService


class TasksIntelligenceService(
    _CoreIntelligenceMixin,
    _AnalyticsMixin,
    _ProductivityMixin,
    BaseAnalyticsService["TasksOperations", Task],
):
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
        graph_intel: GraphIntelligenceService | None = None,
        relationship_service: UnifiedRelationshipService[Any, Any, Any] | None = None,
        event_bus: Any | None = None,
        insight_store: Any | None = None,
    ) -> None:
        """
        Initialize tasks intelligence service (graph-based analytics).

        Args:
            backend: Tasks backend operations (protocol)
            graph_intel: Graph intelligence service (infrastructure only)
            relationship_service: UnifiedRelationshipService for specialized relationship queries
            event_bus: Event bus for publishing events (optional)
            insight_store: For persisting event-driven insights (optional)

        NOTE: No embeddings_service or llm_service parameters - this is intentional.
        This service uses graph queries and Python, not AI.
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )

        # AnalyticsEngine owned here — requires relationship_service to be wired
        # (BaseAnalyticsService stores relationship_service as self.relationships)
        self._analytics_engine = AnalyticsEngine(relationship_service=relationship_service)

        self._init_context_loader(
            get_entity=self.backend.get_task,
            dto_class=TaskDTO,
            model_class=Task,
            domain=Domain.TASKS,
            model_name="Task",
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # get_with_context() is inherited from _CoreIntelligenceMixin (_SharedCoreMixin).
    # ========================================================================

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
        task_result = await self.backend.get(uid)
        if task_result.is_error:
            return Result.fail(task_result)

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=uid))

        from core.utils.intelligence_queries import get_knowledge_prerequisites

        prerequisites: KnowledgePrerequisitesResult = {}
        if self.graph_intel is not None:
            prereq_result = await get_knowledge_prerequisites(
                graph=self.graph_intel, entity_uid=EntityUID(uid), depth=GraphDepth.DEFAULT
            )
            if prereq_result.is_ok:
                prerequisites = prereq_result.value

        insights = {
            "task_uid": uid,
            "task_title": task.title,
            "status": task.status.value if task.status else None,
            "priority": task.priority if task.priority else None,
            "knowledge_prerequisites": prerequisites.get("required_knowledge", []),
            "has_prerequisites": len(prerequisites.get("required_knowledge", [])) > 0,
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

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
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

        cutoff_date = datetime.now() - timedelta(days=period_days)
        tasks_result = await self.backend.find_by(user_uid=user_uid)

        if tasks_result.is_error:
            return Result.fail(tasks_result)

        all_tasks = tasks_result.value
        period_tasks = [task for task in all_tasks if task.created_at >= cutoff_date]

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

        trends = self._analyze_performance_trends(period_tasks)
        optimizations = self._identify_optimization_opportunities(period_tasks, metrics)

        # Include learned duration calibration (ADR-048)
        learning_state = {}
        state_result = await self.backend.get_user_learning_state(user_uid)
        if state_result.is_ok:
            state = state_result.value
            ratio = state.get("task_duration_ratio")
            count = int(state.get("task_completion_count") or 0)
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
