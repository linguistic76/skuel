"""
Tasks Intelligence Service
==========================

Graph-based intelligence features for Tasks domain (NO AI dependencies).

Created: Original November 2025
Updated: January 2026 - Migrated to BaseAnalyticsService (ADR-030)

Provides:
- Knowledge generation from task patterns
- Learning opportunities discovery
- Behavioral insights and patterns
- Performance analytics and optimization
- Cross-domain intelligence

NOTE: This service does NOT use AI (LLM/embeddings).
All methods are pure graph queries + Python calculations.
See TasksAIService for AI-powered features.

Architecture:
- Uses shared intelligence utilities (NO cross-service dependencies)
- Uses GraphIntelligenceService for graph queries (infrastructure only)
- Returns Result[T] for error handling
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from operator import itemgetter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from core.constants import GraphDepth, QueryLimit
from core.models.enums import CompletionStatus, Domain, KuStatus, Priority
from core.models.enums.activity_enums import ProductivityLevel
from core.models.enums.neo_labels import NeoLabel
from core.models.graph_context import GraphContext
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName
from core.models.shared.dual_track import DualTrackResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.intelligence import (
    GraphContextOrchestrator,
    PatternAnalyzer,
    RecommendationEngine,
    analyze_completion_trend,
)
from core.services.tasks.task_relationships import TaskRelationships
from core.services.tasks_types import KnowledgePatternAnalysis
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_second_item

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations
    from core.services.protocols.domain_protocols import TasksRelationshipOperations


# =============================================================================
# HELPER FUNCTIONS (SKUEL012 - no lambdas)
# =============================================================================


def _extract_lowercase_title(task: Any) -> str:
    """Extract lowercase title from task for text analysis."""
    return task.title.lower()


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


class TasksIntelligenceService(BaseAnalyticsService["BackendOperations[Ku]", Ku]):
    """
    Tasks intelligence service using shared utilities (graph-based, no AI).

    Uses shared intelligence_queries utilities instead of cross-service dependencies.

    Provides:
    - Knowledge generation from task patterns
    - Learning opportunities discovery
    - Behavioral insights and patterns
    - Performance analytics and optimization
    - Cross-domain intelligence

    NOTE: This service does NOT use AI (LLM/embeddings).
    All methods are pure graph queries + Python calculations.
    For AI-powered features, see TasksAIService.

    Source Tag: "tasks_intelligence_explicit"
    - Format: "tasks_intelligence_explicit" for user-created relationships
    - Format: "tasks_intelligence_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification
    """

    # Service name for hierarchical logging
    _service_name = "tasks.intelligence"

    def __init__(
        self,
        backend: BackendOperations[Ku],
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
            self.orchestrator = GraphContextOrchestrator[Ku, KuDTO](
                service=self,
                backend_get_method="get_task",
                dto_class=KuDTO,
                model_class=Ku,
                domain=Domain.TASKS,
            )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, GraphContext]]:
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

        # Get knowledge prerequisites
        prereq_result = await self.get_knowledge_prerequisites(uid)
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
    # KNOWLEDGE INTELLIGENCE - Tasks-specific implementations
    # ========================================================================

    async def get_knowledge_suggestions(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge suggestions from task patterns.

        Analyzes:
        - Frequent task types and patterns
        - Repeated problem-solving approaches
        - Skills used across tasks
        - Knowledge gaps from incomplete tasks

        Returns:
            Result containing:
            - task_patterns: List of patterns with knowledge suggestions
            - learning_opportunities: Identified learning opportunities
            - knowledge_gaps: Areas where knowledge would help
        """
        # Determine scope for logging
        scope = f"task {entity_uid}" if entity_uid else f"all tasks for user {user_uid}"
        self.logger.info(f"Generating knowledge suggestions for {scope}")

        # Get tasks based on entity_uid parameter
        if entity_uid:
            # Analyze specific task only
            task_result = await self.backend.get(entity_uid)
            if task_result.is_error:
                return Result.fail(task_result.expect_error())

            if not task_result.value:
                return Result.fail(Errors.not_found(resource="Task", identifier=entity_uid))

            # Single task analysis
            tasks = [task_result.value]
        else:
            # Analyze all completed tasks for user
            tasks_result = await self.backend.find_by(
                user_uid=user_uid, status=CompletionStatus.DONE
            )

            if tasks_result.is_error:
                return Result.fail(tasks_result.expect_error())

            tasks = tasks_result.value

        # Analyze task patterns
        patterns = self._analyze_task_patterns(tasks)

        # Generate suggestions from patterns
        suggestions = [
            {
                "pattern": pattern["name"],
                "knowledge_suggestion": f"Create knowledge unit for {pattern['name']}",
                "confidence": min(0.5 + (pattern["frequency"] / 20), 0.95),
                "frequency": pattern["frequency"],
            }
            for pattern in patterns
            if pattern["frequency"] >= 3  # Frequent enough to warrant knowledge unit
        ]

        # Identify learning opportunities
        learning_opportunities = self._identify_learning_opportunities(tasks)

        # Identify knowledge gaps
        knowledge_gaps = self._identify_knowledge_gaps(tasks)

        # Build metadata
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "user_uid": user_uid,
            "tasks_analyzed": len(tasks),
        }
        if entity_uid:
            metadata["entity_uid"] = entity_uid
            metadata["scope"] = "single_task"
        else:
            metadata["scope"] = "all_user_tasks"

        return Result.ok(
            {
                "task_patterns": suggestions,
                "learning_opportunities": learning_opportunities,
                "knowledge_gaps": knowledge_gaps,
                "metadata": metadata,
            }
        )

    async def generate_knowledge_from_entities(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge units from completed tasks.

        Args:
            user_uid: User identifier
            period_days: Period to analyze (default 30 days)

        Returns:
            Result containing:
            - knowledge_units: Proposed knowledge units
            - patterns_discovered: Discovered patterns
            - documentation_suggestions: Documentation recommendations
        """
        self.logger.info(f"Generating knowledge units from tasks for user {user_uid}")

        # Get completed tasks in period
        cutoff_date = datetime.now() - timedelta(days=period_days)
        tasks_result = await self.backend.find_by(user_uid=user_uid, status=CompletionStatus.DONE)

        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        tasks = tasks_result.value
        # Filter by date
        recent_tasks = [
            task for task in tasks if task.completion_date and task.completion_date >= cutoff_date
        ]

        # Extract patterns
        patterns = self._analyze_task_patterns(recent_tasks)

        # Generate knowledge units from patterns
        knowledge_units = [
            {
                "title": f"{pattern['name']} Best Practices",
                "content": f"Knowledge extracted from {pattern['frequency']} {pattern['name']} tasks",
                "source_tasks": [
                    t.uid for t in recent_tasks if pattern["name"].lower() in t.title.lower()
                ],
                "confidence": min(0.5 + (pattern["frequency"] / 10), 0.95),
                "type": "best_practice",
            }
            for pattern in patterns
            if pattern["frequency"] >= 2
        ]

        return Result.ok(
            {
                "knowledge_units": knowledge_units,
                "patterns_discovered": [p["name"] for p in patterns],
                "documentation_suggestions": self._generate_documentation_suggestions(patterns),
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                    "tasks_analyzed": len(recent_tasks),
                },
            }
        )

    async def get_knowledge_prerequisites(self, entity_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze knowledge prerequisites for task using graph intelligence.

        Uses shared intelligence utilities (Phase 2 - Decoupled).

        Args:
            entity_uid: Task UID

        Returns:
            Result containing prerequisite knowledge and learning path
        """
        # Use shared utility function (no cross-service dependency)
        from core.utils.intelligence_queries import get_knowledge_prerequisites

        return await get_knowledge_prerequisites(
            graph=self.graph_intel, entity_uid=entity_uid, depth=GraphDepth.DEFAULT
        )

    # ========================================================================
    # LEARNING INTELLIGENCE - Tasks-specific implementations
    # ========================================================================

    async def get_learning_opportunities(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Discover learning opportunities from task patterns.

        Analyzes:
        - Failed or incomplete tasks
        - Tasks taking longer than expected
        - Tasks blocked by knowledge gaps
        - Skills used successfully

        Returns:
            Result containing:
            - opportunities: List of learning opportunities
            - recommended_focus: Suggested focus areas
            - estimated_impact: Impact assessment
        """
        self.logger.info(f"Discovering learning opportunities for user {user_uid}")

        # Get all tasks (completed and in-progress)
        tasks_result = await self.backend.find_by(user_uid=user_uid)

        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        tasks = tasks_result.value

        # Analyze for opportunities
        opportunities = []

        # 1. Find tasks with knowledge requirements (requires graph intelligence)
        if self.graph_intel:
            for task in tasks:
                context_result = await self.graph_intel.get_entity_context(
                    task.uid, GraphDepth.NEIGHBORHOOD
                )

                if context_result.is_ok:
                    context = context_result.value
                    knowledge_nodes = [
                        node
                        for node in context.nodes
                        if node.labels and NeoLabel.KU.value in node.labels
                    ]

                    if knowledge_nodes:
                        opportunities.append(
                            {
                                "type": "knowledge_gap",
                                "title": f"Learn concepts for: {task.title}",
                                "task_uid": task.uid,
                                "required_knowledge": [
                                    n.properties.get("title", "Unknown") for n in knowledge_nodes
                                ],
                                "priority": "high"
                                if task.priority and Priority(task.priority).to_numeric() >= 3
                                else "medium",
                            }
                        )

        # 2. Identify skill development opportunities
        skill_opportunities = self._identify_skill_opportunities(tasks)
        opportunities.extend(skill_opportunities)

        # Determine recommended focus
        recommended_focus = self._determine_focus_areas(opportunities)

        # Estimate impact
        impact_assessment = self._estimate_learning_impact(opportunities)

        return Result.ok(
            {
                "opportunities": opportunities[:10],  # Top 10 opportunities
                "recommended_focus": recommended_focus,
                "estimated_impact": impact_assessment,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "opportunities_found": len(opportunities),
                },
            }
        )

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
        # Note: Tasks use KuStatus, not CompletionStatus (which is for habits)
        completed_tasks = [t for t in period_tasks if t.status == KuStatus.COMPLETED]
        completion_rate = len(completed_tasks) / len(period_tasks) if period_tasks else 0.0

        metrics = {
            "total_tasks": len(period_tasks),
            "completed_tasks": len(completed_tasks),
            "completion_rate": round(completion_rate * 100, 1),
            "in_progress_tasks": len([t for t in period_tasks if t.status == KuStatus.ACTIVE]),
            "overdue_tasks": len(
                [
                    t
                    for t in period_tasks
                    if t.due_date
                    and t.due_date < datetime.now().date()
                    and t.status != KuStatus.COMPLETED
                ]
            ),
        }

        # Analyze trends
        trends = self._analyze_performance_trends(period_tasks)

        # Identify optimization opportunities
        optimizations = self._identify_optimization_opportunities(period_tasks, metrics)

        return Result.ok(
            {
                "metrics": metrics,
                "trends": trends,
                "optimization_opportunities": optimizations,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                },
            }
        )

    # ========================================================================
    # CROSS-DOMAIN CONTEXT - Domain-specific categorization (Phase 2B)
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

        Phase 2B Architecture:
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
            if NeoLabel.KU.value in labels and (
                "->DEPENDS_ON" in via_rels or "DEPENDS_ON" in via_rels or "<-DEPENDS_ON" in via_rels
            ):
                task_entity = PathAwareTask(
                    uid=entity["uid"],
                    title=entity["title"],
                    distance=entity["distance"],
                    path_strength=entity["path_strength"],
                    via_relationships=via_rels,
                )

                # Check for directional relationship markers
                if "->DEPENDS_ON" in via_rels or "DEPENDS_ON" in via_rels:
                    # Outgoing DEPENDS_ON = this task depends on the related task (prerequisite)
                    prerequisites.append(task_entity)
                elif "<-DEPENDS_ON" in via_rels:
                    # Incoming DEPENDS_ON = related task depends on this one (dependent)
                    dependents.append(task_entity)

            # Knowledge requirements (REQUIRES_KNOWLEDGE, APPLIES_KNOWLEDGE)
            elif NeoLabel.KU.value in labels and (
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
            elif NeoLabel.KU.value in labels and (
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
    # HELPER METHODS - Internal analysis functions
    # ========================================================================

    def _analyze_task_patterns(self, tasks: list) -> list[dict[str, Any]]:
        """Analyze patterns in task titles and descriptions."""
        # Uses PatternAnalyzer from shared intelligence utilities (Phase 5 consolidation)
        return PatternAnalyzer.extract_word_frequencies(
            [task.title for task in tasks], min_word_length=5, top_n=10
        )

    def _identify_learning_opportunities(self, tasks: list) -> list[str]:
        """Identify learning opportunities from task patterns."""
        # Uses PatternAnalyzer from shared intelligence utilities (Phase 5 consolidation)
        return PatternAnalyzer.detect_by_keywords(
            tasks,
            keyword_sets=[
                (
                    ["debug", "fix", "error", "bug", "issue"],
                    "Error handling patterns from repeated bug fixes",
                ),
                (["api", "integration", "connect", "sync"], "API integration best practices"),
            ],
            text_extractor=_extract_lowercase_title,
            min_matches=2,
        )

    def _identify_knowledge_gaps(self, tasks: list) -> list[str]:
        """Identify knowledge gaps from task patterns."""
        # Uses PatternAnalyzer from shared intelligence utilities (Phase 5 consolidation)
        return PatternAnalyzer.detect_by_indicator_tuples(
            tasks,
            indicators=[
                ("test", "Testing strategies"),
                ("performance", "Performance optimization"),
                ("security", "Security best practices"),
                ("deploy", "Deployment automation"),
            ],
            text_extractor=_extract_lowercase_title,
            min_matches=2,
        )

    def _generate_documentation_suggestions(self, patterns: list[dict]) -> list[str]:
        """Generate documentation suggestions from patterns."""
        return [
            f"Document {pattern['name']} workflow and best practices"
            for pattern in patterns[:5]  # Top 5 patterns
        ]

    def _identify_skill_opportunities(self, tasks: list) -> list[dict[str, Any]]:
        """Identify skill development opportunities from task titles and domains."""
        # Uses PatternAnalyzer from shared intelligence utilities (Phase 5 consolidation)
        return PatternAnalyzer.extract_skill_keywords(
            tasks,
            text_extractor=_extract_lowercase_title,
            skill_keywords=[
                "python",
                "javascript",
                "react",
                "api",
                "database",
                "testing",
                "deploy",
            ],
        )

    def _determine_focus_areas(self, opportunities: list[dict]) -> list[str]:
        """Determine recommended focus areas."""
        focus_areas = []

        # Count opportunity types
        type_counts = {}
        for opp in opportunities:
            opp_type = opp.get("type", "general")
            type_counts[opp_type] = type_counts.get(opp_type, 0) + 1

        # Recommend top 3 focus areas
        sorted_types = sorted(type_counts.items(), key=get_second_item, reverse=True)
        for opp_type, count in sorted_types[:3]:
            focus_areas.append(f"Focus on {opp_type.replace('_', ' ')} ({count} opportunities)")

        return focus_areas

    def _estimate_learning_impact(self, opportunities: list[dict]) -> dict[str, Any]:
        """Estimate impact of addressing learning opportunities."""
        return {
            "potential_time_savings": f"{len(opportunities) * 2} hours per week",
            "quality_improvement": "Estimated 20-40% improvement",
            "confidence_boost": "High" if len(opportunities) >= 5 else "Medium",
        }

    def _analyze_completion_patterns(self, tasks: list) -> list[dict[str, Any]]:
        """Analyze task completion patterns."""
        # Uses PatternAnalyzer from shared intelligence utilities (Phase 5 consolidation)
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
        # Uses PatternAnalyzer from shared intelligence utilities (Phase 5 consolidation)
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
        # Uses RecommendationEngine from shared intelligence utilities (Phase 5 consolidation)
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
        # Uses analyze_completion_trend from shared intelligence utilities (Phase 5 consolidation)
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

        return opportunities

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030 - January 2026)
    # ========================================================================

    async def assess_productivity_dual_track(
        self,
        user_uid: str,
        user_productivity_level: ProductivityLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
    ) -> Result[DualTrackResult[ProductivityLevel]]:
        """
        Dual-track productivity assessment for tasks.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        NOTE: Uses custom implementation (not BaseIntelligenceService template).
        Tasks is unique - it assesses USER productivity across all tasks,
        not a single entity. The template expects entity_uid → entity lookup,
        which doesn't apply here. See ADR-030 § "Each domain can choose".

        Pure calculation method - no AI dependencies.

        Args:
            user_uid: User UID to assess
            user_productivity_level: User's self-reported productivity level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their productivity
            period_days: Period to analyze (default 30 days)

        Returns:
            Result[DualTrackResult[ProductivityLevel]] with dual-track analysis

        Example:
            >>> from core.models.enums.activity_enums import ProductivityLevel
            >>> result = await service.assess_productivity_dual_track(
            ...     user_uid="user_mike",
            ...     user_productivity_level=ProductivityLevel.PRODUCTIVE,
            ...     user_evidence="I complete most tasks on time",
            ...     user_reflection="Could improve on complex tasks",
            ... )
            >>> if result.is_ok:
            ...     dual_track = result.value
            ...     print(f"Gap: {dual_track.perception_gap:.0%}")
        """
        # Calculate system assessment
        system_level, system_score, system_evidence = await self._calculate_system_productivity(
            None, user_uid, period_days
        )

        # Calculate user score
        user_score = self._productivity_level_to_score(user_productivity_level)

        # Calculate perception gap
        perception_gap = abs(user_score - system_score)

        # Determine gap direction
        if perception_gap < 0.1:
            direction = "aligned"
        elif user_score > system_score:
            direction = "user_higher"
        else:
            direction = "system_higher"

        # Generate insights and recommendations
        insights = self._generate_productivity_gap_insights(direction, perception_gap, "task")
        recommendations = self._generate_productivity_gap_recommendations(
            direction, perception_gap, None, system_evidence
        )

        # Build result
        # Note: Tasks is unique - assesses USER productivity, not a single entity.
        # entity_uid=user_uid and entity_type="productivity" reflect this.
        result = DualTrackResult[ProductivityLevel](
            entity_uid=user_uid,
            entity_type="productivity",
            user_level=user_productivity_level,
            user_score=user_score,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_level=system_level,
            system_score=system_score,
            system_evidence=tuple(system_evidence),
            perception_gap=perception_gap,
            gap_direction=direction,
            insights=tuple(insights),
            recommendations=tuple(recommendations[:4]),  # Limit to top 4
        )

        return Result.ok(result)

    async def _calculate_system_productivity(
        self, _entity: Any, user_uid: str, period_days: int = 30
    ) -> tuple[ProductivityLevel, float, list[str]]:
        """
        Calculate system productivity from task completion metrics.

        Examines:
        - Task completion rate
        - Overdue ratio
        - On-time completion rate
        - Priority handling

        Args:
            _entity: Unused (user assessment doesn't target a single entity)
            user_uid: User UID
            period_days: Period to analyze (default 30 days)

        Returns:
            Tuple of (ProductivityLevel, score, evidence_list)
        """
        evidence: list[str] = []
        cutoff_date = datetime.now() - timedelta(days=period_days)

        # Get tasks in period
        tasks_result = await self.backend.find_by(user_uid=user_uid)
        if tasks_result.is_error:
            return ProductivityLevel.MODERATELY_PRODUCTIVE, 0.5, ["Unable to fetch tasks"]

        all_tasks = tasks_result.value or []
        period_tasks = [task for task in all_tasks if task.created_at >= cutoff_date]

        if not period_tasks:
            return ProductivityLevel.MODERATELY_PRODUCTIVE, 0.5, ["No tasks in assessment period"]

        # Calculate metrics
        completed_tasks = [t for t in period_tasks if t.status == KuStatus.COMPLETED]
        completion_rate = len(completed_tasks) / len(period_tasks)

        # Calculate overdue ratio
        overdue_tasks = [
            t
            for t in period_tasks
            if t.due_date and t.due_date < datetime.now().date() and t.status != KuStatus.COMPLETED
        ]
        overdue_ratio = len(overdue_tasks) / len(period_tasks) if period_tasks else 0

        # Calculate on-time completion rate
        on_time_completed = [
            t
            for t in completed_tasks
            if t.due_date and t.completion_date and t.completion_date <= t.due_date
        ]
        on_time_rate = len(on_time_completed) / len(completed_tasks) if completed_tasks else 0

        # Calculate priority handling score
        high_priority_tasks = [
            t for t in period_tasks if t.priority and Priority(t.priority).to_numeric() >= 3
        ]
        high_priority_completed = [t for t in high_priority_tasks if t.status == KuStatus.COMPLETED]
        priority_rate = (
            len(high_priority_completed) / len(high_priority_tasks) if high_priority_tasks else 1.0
        )

        # Weighted score calculation
        score = (
            completion_rate * 0.4  # 40% weight on completion rate
            + (1 - overdue_ratio) * 0.25  # 25% weight on avoiding overdue
            + on_time_rate * 0.20  # 20% weight on on-time completion
            + priority_rate * 0.15  # 15% weight on priority handling
        )

        # Build evidence
        evidence.append(
            f"Completed {len(completed_tasks)}/{len(period_tasks)} tasks ({completion_rate:.0%})"
        )
        if overdue_tasks:
            evidence.append(f"{len(overdue_tasks)} tasks currently overdue")
        if on_time_completed:
            evidence.append(
                f"{len(on_time_completed)} tasks completed on time ({on_time_rate:.0%})"
            )
        if high_priority_tasks:
            evidence.append(
                f"High-priority completion: {len(high_priority_completed)}/{len(high_priority_tasks)}"
            )

        # Convert score to level
        system_level = ProductivityLevel.from_score(score)

        return system_level, score, evidence

    def _productivity_level_to_score(self, level: ProductivityLevel) -> float:
        """Convert ProductivityLevel to numeric score (0.0-1.0)."""
        return level.to_score()

    def _generate_productivity_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate productivity-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                "Your self-perception of productivity matches your task completion data. "
                "This indicates accurate self-awareness about your work output."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your task metrics suggest "
                f"(gap: {gap:.0%}). Consider: Are there completed tasks not tracked in SKUEL?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate optimism bias, "
                    "or external work not reflected in your task list."
                )
        else:  # system_higher
            insights.append(
                f"Your task completion shows higher productivity than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your accomplishments."
            )
            if gap > 0.3:
                insights.append(
                    "Consider celebrating your wins - you're accomplishing more than you realize!"
                )

        return insights

    def _generate_productivity_gap_recommendations(
        self, direction: str, _gap: float, _entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate productivity-specific gap recommendations."""
        recommendations: list[str] = []

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your productivity self-awareness is accurate."
            )
            recommendations.append(
                "Consider setting stretch goals to push your productivity further."
            )
        elif direction == "user_higher":
            recommendations.append("Review your task list to ensure all work is tracked.")
            recommendations.append(
                "Consider breaking down large tasks to better visualize progress."
            )
            # Check for overdue tasks in evidence
            if any("overdue" in e.lower() for e in evidence):
                recommendations.append(
                    "Address overdue tasks to align perceived and actual productivity."
                )
        else:  # system_higher
            recommendations.append(
                "Acknowledge your accomplishments - you're more productive than you think!"
            )
            if evidence:
                recommendations.append(
                    f"Review your metrics: {evidence[0]} shows solid productivity."
                )
            recommendations.append(
                "Consider why you underestimate your productivity - impostor syndrome can affect perception."
            )

        return recommendations[:4]

    # ========================================================================
    # TASK-LEVEL LEARNING METRICS (Moved from TasksAnalyticsService - January 2026)
    # Uses Task model capabilities + TaskRelationships for task-level analysis.
    # Different from get_learning_opportunities() which uses graph intelligence.
    # ========================================================================

    async def analyze_task_learning_metrics(
        self, _filters: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Analyze learning metrics from tasks using Task model capabilities.

        GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.

        This method analyzes individual tasks for:
        - Knowledge complexity score
        - Learning impact score
        - Knowledge bridge detection
        - Mastery validation

        Different from get_learning_opportunities() which uses graph intelligence
        to discover what knowledge is needed for tasks.

        Returns:
            Result containing list of task learning metrics sorted by impact
        """
        # Get tasks from backend
        tasks_result = await self.backend.list(limit=QueryLimit.SMALL)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        tasks, _ = tasks_result.value
        opportunities = []

        # GRAPH-NATIVE: Fetch relationships for tasks with learning opportunities
        tasks_with_opportunities = [task for task in tasks if task.learning_opportunities_count > 0]

        if not tasks_with_opportunities:
            return Result.ok([])

        # Fetch all relationships in parallel
        rels_list = await asyncio.gather(
            *[
                TaskRelationships.fetch(task.uid, self.relationships)
                for task in tasks_with_opportunities
            ]
        )

        for task, _rels in zip(tasks_with_opportunities, rels_list, strict=False):
            opportunity = {
                "task_uid": task.uid,
                "title": task.title,
                "opportunities_count": task.learning_opportunities_count,
                # NOTE: knowledge_patterns inferred from relationships, not stored field
                "knowledge_patterns": [],
                "complexity_score": task.calculate_knowledge_complexity(),
                "learning_impact": task.calculate_learning_impact(),
                "is_bridge_task": task.is_knowledge_bridge(),
                "validates_mastery": task.validates_knowledge_mastery(),
            }
            opportunities.append(opportunity)

        # Sort by learning impact (highest first)
        opportunities.sort(key=itemgetter("learning_impact"), reverse=True)

        return Result.ok(opportunities)

    async def generate_task_knowledge_insights(
        self, _domain_filter: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge insights using Task model capabilities.

        GRAPH-NATIVE: Fetches relationship data from graph to pass to Task methods.

        Returns:
            Result containing knowledge insights summary
        """
        # Get all tasks to analyze knowledge patterns
        tasks_result = await self.backend.list(limit=QueryLimit.COMPREHENSIVE)
        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        all_tasks, _ = tasks_result.value

        if not all_tasks:
            return Result.ok(
                {
                    "total_tasks_analyzed": 0,
                    "knowledge_bridge_tasks": 0,
                    "mastery_validation_tasks": 0,
                    "high_complexity_tasks": 0,
                    "total_learning_opportunities": 0,
                    "average_learning_opportunities": 0,
                    "bridge_task_ratio": 0,
                    "mastery_validation_ratio": 0,
                    "knowledge_discovery_patterns": {},
                }
            )

        # GRAPH-NATIVE: Fetch relationships for all tasks in parallel
        rels_list = await asyncio.gather(
            *[TaskRelationships.fetch(task.uid, self.relationships) for task in all_tasks]
        )

        knowledge_bridge_tasks = []
        mastery_validation_tasks = []
        high_complexity_tasks = []
        total_learning_opportunities = 0

        for task, _rels in zip(all_tasks, rels_list, strict=False):
            # Analyze using unified Task model capabilities
            if task.is_knowledge_bridge():
                knowledge_bridge_tasks.append(task)

            if task.validates_knowledge_mastery():
                mastery_validation_tasks.append(task)

            if task.calculate_knowledge_complexity() > 0.7:
                high_complexity_tasks.append(task)

            total_learning_opportunities += task.learning_opportunities_count

        # Generate insights
        insights = {
            "total_tasks_analyzed": len(all_tasks),
            "knowledge_bridge_tasks": len(knowledge_bridge_tasks),
            "mastery_validation_tasks": len(mastery_validation_tasks),
            "high_complexity_tasks": len(high_complexity_tasks),
            "total_learning_opportunities": total_learning_opportunities,
            "average_learning_opportunities": total_learning_opportunities / len(all_tasks)
            if all_tasks
            else 0,
            "bridge_task_ratio": len(knowledge_bridge_tasks) / len(all_tasks) if all_tasks else 0,
            "mastery_validation_ratio": len(mastery_validation_tasks) / len(all_tasks)
            if all_tasks
            else 0,
            "knowledge_discovery_patterns": self._analyze_task_knowledge_patterns(
                all_tasks, rels_list
            ),
        }

        return Result.ok(insights)

    def _analyze_task_knowledge_patterns(
        self, tasks: list[Ku], rels_list: list[TaskRelationships]
    ) -> KnowledgePatternAnalysis:
        """
        Analyze knowledge patterns across tasks using unified Task model.

        GRAPH-NATIVE: Requires relationship data for knowledge analysis.

        Args:
            tasks: List of tasks to analyze
            rels_list: List of TaskRelationships corresponding to tasks

        Returns:
            Knowledge pattern analysis
        """
        pattern_counts: dict[str, int] = {}
        knowledge_combinations: dict[tuple[str, ...], int] = {}

        for task, _rels in zip(tasks, rels_list, strict=False):
            # NOTE: Pattern counting skipped - knowledge_patterns inferred from relationships
            pass

            # Analyze knowledge combinations
            all_knowledge = task.get_combined_knowledge_uids()
            if len(all_knowledge) > 1:
                combo_key = tuple(sorted(all_knowledge))
                knowledge_combinations[combo_key] = knowledge_combinations.get(combo_key, 0) + 1

        return KnowledgePatternAnalysis(
            common_patterns=dict(
                sorted(pattern_counts.items(), key=itemgetter(1), reverse=True)[:10]
            ),
            frequent_knowledge_combinations=dict(
                sorted(knowledge_combinations.items(), key=itemgetter(1), reverse=True)[:5]
            ),
            total_unique_patterns=len(pattern_counts),
            total_knowledge_combinations=len(knowledge_combinations),
        )
