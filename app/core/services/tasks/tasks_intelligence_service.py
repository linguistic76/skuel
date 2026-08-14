"""
Tasks Intelligence Service
==========================

Task-specific intelligence features (NO AI dependencies).

Architecture: Shell delegates to focused mixins (graph context retrieval —
``get_with_context``, mechanism B — comes from the shared
``core.services.intelligence._core_intelligence_mixin``):
  _analytics_mixin.py            — get_behavioral_insights, performance helpers
  _productivity_mixin.py         — analyze_learning_patterns, calculate_knowledge_aware_priorities,
                                   generate_task_insights, track_knowledge_mastery_progression,
                                   analyze_task_learning_metrics, generate_task_knowledge_insights
  _dual_track_mixin.py           — assess_productivity_dual_track (ADR-030 perception gap)

Created: Original November 2025
Updated: January 2026 - Migrated to BaseAnalyticsService (ADR-030)
Updated: April 2026 - Decomposed into focused mixins
Updated: April 2026 - Absorbed TasksLearningMetricsService (symmetry refactor):
  its two methods were task-level analytics mis-labeled as a "learning" service;
  folded back into _productivity_mixin alongside sibling analytics methods.

Provides:
- Behavioral insights and patterns (task-specific)
- Performance analytics and optimization (task-specific)
- Cross-domain context (path-aware, via the CANONICAL typed reader)
- Task-level learning metrics (knowledge complexity, bridge detection, mastery)

Domain-agnostic knowledge intelligence (knowledge suggestions, prerequisites,
learning opportunities) was extracted to ActivityKnowledgeIntelligenceService
(March 2026) — those methods work for all 6 activity domains, not just Tasks.

Dual-track productivity assessment (ADR-030) lives in `_dual_track_mixin.py`
(user-level perception-gap: self-rating vs measured throughput).

Related sub-services (extracted March 2026):
- ActivityKnowledgeIntelligenceService: Knowledge intelligence (all domains)

NOTE: This service does NOT use AI (LLM/embeddings).
All methods are pure graph queries + Python calculations.
See TasksAIService for AI-powered features.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth, LearningLoop
from core.models.enums import EntityStatus, Priority
from core.models.task.task import Task
from core.models.type_hints import EntityUID, UserUID
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.infrastructure.prerequisite_checker import build_learning_requirements
from core.services.intelligence import (
    calculate_task_cross_domain_metrics,
    task_recommendations,
)
from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.tasks._analytics_mixin import _AnalyticsMixin
from core.services.tasks._dual_track_mixin import _DualTrackMixin
from core.services.tasks._productivity_mixin import _ProductivityMixin
from core.services.tasks.task_knowledge_analyzer import TaskKnowledgeAnalyzer
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.ports.query_types import KnowledgePrerequisitesResult
    from core.services.relationships import UnifiedRelationshipService
    from core.services.user.unified_user_context import UserContext


class TasksIntelligenceService(
    _CoreIntelligenceMixin,
    _AnalyticsMixin,
    _ProductivityMixin,
    _DualTrackMixin,
    BaseAnalyticsService["TasksOperations", Task],
):
    """
    Task-specific intelligence service (graph-based, no AI).

    Provides:
    - Behavioral insights and patterns (completion time, procrastination)
    - Performance analytics and optimization (rates, trends, duration calibration)
    - Dual-track productivity self-assessment (perception gap, ADR-030)
    - Cross-domain context (path-aware TaskCrossContext via the typed reader)

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

        # TaskKnowledgeAnalyzer owned here — requires relationship_service
        # (BaseAnalyticsService stores relationship_service as self.relationships);
        # graph_intel feeds sel_category resolution for cross-domain grouping.
        self._knowledge_analyzer = TaskKnowledgeAnalyzer(
            relationship_service=relationship_service, graph_intel=graph_intel
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # get_with_context() is inherited from the shared _CoreIntelligenceMixin.
    # ========================================================================

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7, user_context: UserContext | None = None
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a task.

        Protocol method: Provides task-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/tasks/insights route.

        Composes THREE sources:

        1. Task's distinctive READINESS lens — graph-intel ``get_knowledge_prerequisites``
           (``knowledge_prerequisites`` / ``has_prerequisites``) plus task-field insights
           (overdue / high-priority / has-description). This is Task-specific.
        2. A path-aware CROSS-DOMAIN block over the CANONICAL typed reader
           (``get_cross_domain_context_typed`` → path-aware ``TaskCrossContext``) via
           ``_analyze_entity_with_typed_context`` — knowledge it requires/applies + goals
           it contributes to, with cascade_impact / path_aware_context. Surfaced additively
           under the ``cross_domain`` key; every pre-existing key is preserved.
        3. A mastery-aware ``learning_requirements`` block (shared with the Goal lens via
           :func:`build_learning_requirements`) built from the task's REQUIRES_KNOWLEDGE
           edges. When ``user_context`` is supplied, ``knowledge_gaps`` / ``ready_to_start``
           reflect the user's actual ``knowledge_mastery``; context-free callers degrade to
           treating every requirement as an open gap.

        Degrades gracefully: a real cross-domain-context FETCH error logs and yields an
        empty ``cross_domain`` block rather than failing the whole route (an edge-less task
        still yields an OK empty context via the typed reader's ok-empty-context policy).

        Args:
            uid: Task UID
            min_confidence: Minimum confidence threshold (default: 0.7)
            user_context: Optional user context — enables real mastery in the
                ``learning_requirements`` block.

        Returns:
            Result containing insights data dict with knowledge prerequisites,
            task-field insights, an additive cross-domain block, and a mastery-aware
            learning-requirements block.
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

        cross_domain = await self._build_cross_domain_block(uid, min_confidence)
        # Source required-knowledge UIDs from the typed cross-domain reader when it's
        # available (no extra query — reuse what the block already resolved). If that fetch
        # failed (unavailable block), fall back to the graph-intel prerequisites so the
        # learning-requirements block stays consistent with the has_prerequisites readiness
        # lens instead of falsely reporting "ready, no gaps". Tasks have no learning-path
        # edges in their cross-context, so available_paths is empty.
        if cross_domain.get("available", False):
            required_knowledge_uids = cross_domain.get("context", {}).get("required_knowledge", [])
        else:
            required_knowledge_uids = [
                item["uid"]
                for item in prerequisites.get("required_knowledge", [])
                if item.get("uid")
            ]
        learning_requirements = build_learning_requirements(
            required_knowledge_uids=required_knowledge_uids,
            learning_path_uids=[],
            context=user_context,
        )

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
            # Additive path-aware cross-domain block (see _build_cross_domain_block).
            "cross_domain": cross_domain,
            # Additive mastery-aware learning-requirements block (shared with Goal).
            "learning_requirements": learning_requirements,
        }

        return Result.ok(insights)

    async def _build_cross_domain_block(self, uid: str, min_confidence: float) -> dict[str, Any]:
        """Build the additive path-aware cross-domain block for ``get_domain_insights``.

        Runs ``_analyze_entity_with_typed_context`` over the CANONICAL typed reader and
        flattens its ``context``/``metrics``/``recommendations`` into a single additive dict.
        Degrades to an empty block (``{"available": False, ...}``) on a real fetch error —
        the readiness lens still answers, the route does not 500. An edge-less task yields an
        OK empty context (``available: True`` with zeroed counts), not a failure.
        """
        from core.models.graph.path_aware_types import TaskCrossContext

        analysis_result = await self._analyze_entity_with_typed_context(
            uid=uid,
            metrics_fn=calculate_task_cross_domain_metrics,
            recommendations_fn=task_recommendations,
            min_confidence=min_confidence,
        )
        if analysis_result.is_error:
            self.logger.warning(
                f"Cross-domain context unavailable for task {uid}: "
                f"{analysis_result.expect_error().message}"
            )
            return {
                "available": False,
                "context": {},
                "metrics": {},
                "recommendations": [],
            }

        analysis = analysis_result.value
        context: TaskCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        return {
            "available": True,
            "context": {
                "total_connections": context.total_connections,
                "required_knowledge": [k.uid for k in context.required_knowledge],
                "applied_knowledge": [k.uid for k in context.applied_knowledge],
                "contributing_goals": [g.uid for g in context.contributing_goals],
            },
            "metrics": {
                "required_knowledge_count": metrics["required_knowledge_count"],
                "applied_knowledge_count": metrics["applied_knowledge_count"],
                "knowledge_coverage": metrics["knowledge_coverage"],
                "goal_support_count": metrics["goal_support_count"],
                "has_required_knowledge": metrics["has_required_knowledge"],
                "has_applied_knowledge": metrics["has_applied_knowledge"],
                "has_goal_support": metrics["has_goal_support"],
                "cascade_impact": metrics["cascade_impact"],
                "path_aware_context": metrics["path_aware_context"],
            },
            "recommendations": analysis["recommendations"],
        }

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
