"""
Learning Step Intelligence Service
===================================

Intelligence service for Learning Steps - scoring, readiness, practice calculations.

**January 2026 - Unified Architecture:**
This service follows the Activity Domain pattern, extending BaseIntelligenceService.
Complex scoring and aggregation methods moved here from LsRelationshipService.

Methods:
- is_ready(): Check if step is ready based on prerequisite completion
- get_practice_summary(): Get practice opportunity counts
- practice_completeness_score(): Calculate practice completeness (0.0-1.0)
- calculate_guidance_strength(): Calculate guidance strength (0.0-1.0)
- has_prerequisites(): Check if step has prerequisites
- has_guidance(): Check if step has guidance
- has_practice_opportunities(): Check if step has practice opportunities

Architecture:
- Extends BaseIntelligenceService[BackendOperations[Ls], Ls]
- Uses direct Cypher for complex aggregation queries
- Returns Result[T] for error handling
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import Domain
from core.models.graph_context import GraphContext
from core.models.ls.ls import Ls
from core.models.ls.ls_dto import LearningStepDTO
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.graph_query_executor import GraphQueryExecutor
from core.services.intelligence import GraphContextOrchestrator
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations

logger = get_logger(__name__)


class LsIntelligenceService(BaseAnalyticsService["BackendOperations[Ls]", "Ls"]):
    """
    Intelligence service for Learning Steps.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Provides:
    - Readiness assessment based on prerequisites
    - Practice opportunity analysis
    - Guidance strength calculation
    - Practice completeness scoring

    These methods require complex graph queries that don't fit the
    generic UnifiedRelationshipService pattern.
    """

    _service_name = "ls.intelligence"

    def __init__(
        self,
        backend: BackendOperations[Ls],
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize LsIntelligenceService.

        NOTE: No embeddings_service or llm_service parameters (ADR-030).
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # Initialize query executor for direct Cypher access
        # Use driver from backend for complex queries
        driver = getattr(backend, "driver", None)
        self.executor: GraphQueryExecutor | None = GraphQueryExecutor(driver) if driver else None
        self.driver = driver

        # Initialize GraphContextOrchestrator for get_with_context pattern
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Ls, LearningStepDTO](
                service=self,
                backend_get_method="get",
                dto_class=LearningStepDTO,
                model_class=Ls,
                domain=Domain.LEARNING,
            )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ls, GraphContext]]:
        """
        Get learning step with full graph context.

        Protocol method: Uses GraphContextOrchestrator for generic pattern.
        Used by IntelligenceRouteFactory for GET /api/learning-steps/context route.

        Args:
            uid: Learning Step UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Ls, GraphContext) tuple
        """
        if self.orchestrator is None:
            return Result.fail(
                Errors.system(
                    message="Graph intelligence service required for context queries",
                    operation="get_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get learning step analytics for a user.

        Protocol method: Aggregates learning step metrics.
        Used by IntelligenceRouteFactory for GET /api/learning-steps/analytics route.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict

        Note: Learning Steps are shared curriculum content (no user ownership).
        This returns overall LS statistics rather than user-specific data.
        """
        # LS is shared content - get overall stats
        ls_result = await self.backend.find_by()
        if ls_result.is_error:
            return Result.fail(ls_result.expect_error())

        all_steps = ls_result.value or []
        total_steps = len(all_steps)

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_learning_steps": total_steps,
                "analytics": {
                    "total": total_steps,
                    "note": "Learning Steps are shared curriculum content",
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a learning step.

        Protocol method: Provides LS-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/learning-steps/insights route.

        Args:
            uid: Learning Step UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict with practice analysis
        """
        # Get learning step
        ls_result = await self.backend.get(uid)
        if ls_result.is_error:
            return Result.fail(ls_result.expect_error())

        ls = ls_result.value
        if not ls:
            return Result.fail(Errors.not_found(resource="LearningStep", identifier=uid))

        # Get practice summary
        practice_result = await self.get_practice_summary(uid)
        practice = practice_result.value if practice_result.is_ok else {}

        # Get practice completeness score
        completeness_result = await self.practice_completeness_score(uid)
        completeness = completeness_result.value if completeness_result.is_ok else 0.0

        # Check for prerequisites
        has_prereqs_result = await self.has_prerequisites(uid)
        has_prerequisites = has_prereqs_result.value if has_prereqs_result.is_ok else False

        return Result.ok(
            {
                "ls_uid": uid,
                "ls_title": ls.title,
                "ls_intent": getattr(ls, "intent", None),
                "practice_summary": practice,
                "practice_completeness": completeness,
                "has_prerequisites": has_prerequisites,
                "min_confidence": min_confidence,
            }
        )

    def _require_executor(self) -> Result[GraphQueryExecutor]:
        """Fail-fast guard for executor availability."""
        if not self.executor:
            return Result.fail(
                Errors.system(
                    message="GraphQueryExecutor not initialized - backend driver required",
                    operation="require_executor",
                )
            )
        return Result.ok(self.executor)

    # ========================================================================
    # READINESS ASSESSMENT
    # ========================================================================

    @with_error_handling("is_ready", error_type="database", uid_param="ls_uid")
    async def is_ready(self, ls_uid: str, completed_step_uids: set[str]) -> Result[bool]:
        """
        Check if learning step is ready based on prerequisite completion.

        A step is ready when ALL its prerequisite steps (via REQUIRES_STEP
        relationship) have been completed.

        Args:
            ls_uid: UID of the learning step
            completed_step_uids: Set of completed step UIDs

        Returns:
            Result[bool] - True if all prerequisites are met

        Example:
            result = await intelligence.is_ready(
                "ls:functions",
                {"ls:intro", "ls:syntax"}
            )
            if result.is_ok and result.value:
                print("Ready to learn functions!")
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return executor_result  # type: ignore[return-value]

        def _check_readiness(records: list[dict]) -> bool:
            if not records:
                return True  # No prerequisites = ready
            prereq_uids = set(records[0].get("prereq_uids") or [])
            return prereq_uids.issubset(completed_step_uids)

        return await executor_result.value.execute(
            query="""
                MATCH (ls:Ls {uid: $ls_uid})-[:REQUIRES_STEP]->(prereq:Ls)
                RETURN collect(prereq.uid) as prereq_uids
            """,
            params={"ls_uid": ls_uid},
            processor=_check_readiness,
            operation="is_ready",
        )

    # ========================================================================
    # PRACTICE ANALYSIS
    # ========================================================================

    @with_error_handling("get_practice_summary", error_type="database", uid_param="ls_uid")
    async def get_practice_summary(self, ls_uid: str) -> Result[dict[str, int]]:
        """
        Get summary of practice opportunities for a learning step.

        Counts habits, tasks, and events associated with this step via
        BUILDS_HABIT, ASSIGNS_TASK, and SCHEDULES_EVENT relationships.

        Args:
            ls_uid: UID of the learning step

        Returns:
            Result[dict] with structure:
            {"habits": int, "tasks": int, "events": int, "total": int}

        Example:
            result = await intelligence.get_practice_summary("ls:functions")
            if result.is_ok:
                print(f"Total practice: {result.value['total']} items")
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return executor_result  # type: ignore[return-value]

        def _process_summary(records: list[dict]) -> dict[str, int]:
            if not records:
                return {"habits": 0, "tasks": 0, "events": 0, "total": 0}

            habits = records[0].get("habits", 0)
            tasks = records[0].get("tasks", 0)
            events = records[0].get("events", 0)
            total = habits + tasks + events

            return {"habits": habits, "tasks": tasks, "events": events, "total": total}

        return await executor_result.value.execute(
            query="""
                MATCH (ls:Ls {uid: $ls_uid})
                OPTIONAL MATCH (ls)-[:BUILDS_HABIT]->(h)
                OPTIONAL MATCH (ls)-[:ASSIGNS_TASK]->(t)
                OPTIONAL MATCH (ls)-[:SCHEDULES_EVENT]->(e)
                RETURN count(DISTINCT h) as habits,
                       count(DISTINCT t) as tasks,
                       count(DISTINCT e) as events
            """,
            params={"ls_uid": ls_uid},
            processor=_process_summary,
            operation="get_practice_summary",
        )

    @with_error_handling("practice_completeness_score", error_type="database", uid_param="ls_uid")
    async def practice_completeness_score(self, ls_uid: str) -> Result[float]:
        """
        Calculate practice completeness (0.0-1.0).

        Full practice suite (habits + tasks + events) = 1.0
        Each type contributes 1/3 of the score.

        Args:
            ls_uid: UID of the learning step

        Returns:
            Result[float] - Practice completeness score (0.0 to 1.0)

        Example:
            result = await intelligence.practice_completeness_score("ls:functions")
            if result.is_ok:
                print(f"Practice completeness: {result.value:.0%}")
        """
        summary_result = await self.get_practice_summary(ls_uid)
        if summary_result.is_error:
            return Result.fail(summary_result.expect_error())

        summary = summary_result.value
        has_tasks = 1.0 if summary["tasks"] > 0 else 0.0
        has_habits = 1.0 if summary["habits"] > 0 else 0.0
        has_events = 1.0 if summary["events"] > 0 else 0.0

        score = (has_tasks + has_habits + has_events) / 3.0
        return Result.ok(score)

    # ========================================================================
    # GUIDANCE ANALYSIS
    # ========================================================================

    @with_error_handling("calculate_guidance_strength", error_type="database", uid_param="ls_uid")
    async def calculate_guidance_strength(self, ls_uid: str) -> Result[float]:
        """
        Calculate how well this step guides the learner (0.0-1.0).

        Scoring:
        - Principles provide values-based guidance (40% max)
        - Choices provide inspiration and options (60% max)

        Args:
            ls_uid: UID of the learning step

        Returns:
            Result[float] - Guidance strength score (0.0 to 1.0)

        Example:
            result = await intelligence.calculate_guidance_strength("ls:functions")
            if result.is_ok:
                print(f"Guidance strength: {result.value:.0%}")
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return executor_result  # type: ignore[return-value]

        def _calculate_score(records: list[dict]) -> float:
            if not records:
                return 0.0

            principle_count = records[0].get("principle_count", 0)
            choice_count = records[0].get("choice_count", 0)

            score = 0.0

            # Principles provide values-based guidance (40% max)
            if principle_count > 0:
                score += min(0.4, principle_count * 0.15)

            # Choices provide inspiration and options (60% max)
            if choice_count > 0:
                score += min(0.6, choice_count * 0.2)

            return min(1.0, score)

        return await executor_result.value.execute(
            query="""
                MATCH (ls:Ls {uid: $ls_uid})
                OPTIONAL MATCH (ls)-[:GUIDED_BY_PRINCIPLE]->(p)
                OPTIONAL MATCH (ls)-[:OFFERS_CHOICE]->(c)
                RETURN count(DISTINCT p) as principle_count,
                       count(DISTINCT c) as choice_count
            """,
            params={"ls_uid": ls_uid},
            processor=_calculate_score,
            operation="calculate_guidance_strength",
        )

    # ========================================================================
    # EXISTENCE CHECKS (Compound)
    # ========================================================================

    @with_error_handling("has_prerequisites", error_type="database", uid_param="ls_uid")
    async def has_prerequisites(self, ls_uid: str) -> Result[bool]:
        """
        Check if learning step has any prerequisites.

        Checks for both:
        - REQUIRES_STEP relationships (other steps)
        - REQUIRES_KNOWLEDGE relationships (KU prerequisites)

        Args:
            ls_uid: UID of the learning step

        Returns:
            Result[bool] - True if step has prerequisites

        Example:
            result = await intelligence.has_prerequisites("ls:functions")
            if result.is_ok and result.value:
                print("This step has prerequisites")
        """
        if not self.executor:
            return Result.fail(
                Errors.system(message="Query executor not available", operation="has_prerequisites")
            )

        return await self.executor.execute_exists(
            query="""
                MATCH (ls:Ls {uid: $ls_uid})
                WHERE exists((ls)-[:REQUIRES_STEP]->()) OR exists((ls)-[:REQUIRES_KNOWLEDGE]->())
                RETURN ls
            """,
            params={"ls_uid": ls_uid},
            operation="has_prerequisites",
        )

    @with_error_handling("has_guidance", error_type="database", uid_param="ls_uid")
    async def has_guidance(self, ls_uid: str) -> Result[bool]:
        """
        Check if learning step has guidance (principles or choices).

        Args:
            ls_uid: UID of the learning step

        Returns:
            Result[bool] - True if step has guidance

        Example:
            result = await intelligence.has_guidance("ls:functions")
            if result.is_ok and result.value:
                print("This step has guidance")
        """
        if not self.executor:
            return Result.fail(
                Errors.system(message="Query executor not available", operation="has_guidance")
            )

        return await self.executor.execute_exists(
            query="""
                MATCH (ls:Ls {uid: $ls_uid})
                WHERE exists((ls)-[:GUIDED_BY_PRINCIPLE]->()) OR exists((ls)-[:OFFERS_CHOICE]->())
                RETURN ls
            """,
            params={"ls_uid": ls_uid},
            operation="has_guidance",
        )

    @with_error_handling("has_practice_opportunities", error_type="database", uid_param="ls_uid")
    async def has_practice_opportunities(self, ls_uid: str) -> Result[bool]:
        """
        Check if learning step has practice opportunities.

        Checks for any of:
        - BUILDS_HABIT relationships
        - ASSIGNS_TASK relationships
        - SCHEDULES_EVENT relationships

        Args:
            ls_uid: UID of the learning step

        Returns:
            Result[bool] - True if step has practice opportunities

        Example:
            result = await intelligence.has_practice_opportunities("ls:functions")
            if result.is_ok and result.value:
                print("This step has practice opportunities")
        """
        if not self.executor:
            return Result.fail(
                Errors.system(
                    message="Query executor not available",
                    operation="has_practice_opportunities",
                )
            )

        return await self.executor.execute_exists(
            query="""
                MATCH (ls:Ls {uid: $ls_uid})
                WHERE exists((ls)-[:BUILDS_HABIT]->())
                   OR exists((ls)-[:ASSIGNS_TASK]->())
                   OR exists((ls)-[:SCHEDULES_EVENT]->())
                RETURN ls
            """,
            params={"ls_uid": ls_uid},
            operation="has_practice_opportunities",
        )
