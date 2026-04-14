"""
PathStep Intelligence Service
===============================

Intelligence service for PathSteps - scoring, readiness, practice calculations.

**January 2026 - Unified Architecture:**
This service follows the Activity Domain pattern, extending BaseIntelligenceService.
Complex scoring and aggregation methods consolidated here from the former PsRelationshipService.

Methods:
- is_ready(): Check if step is ready based on prerequisite completion
- get_practice_summary(): Get practice opportunity counts
- practice_completeness_score(): Calculate practice completeness (0.0-1.0)
- calculate_guidance_strength(): Calculate guidance strength (0.0-1.0)
- has_prerequisites(): Check if step has prerequisites
- has_guidance(): Check if step has guidance
- has_practice_opportunities(): Check if step has practice opportunities

Architecture:
- Extends BaseAnalyticsService[BackendOperations[PathStep], PathStep]
- Uses direct Cypher for complex aggregation queries
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import Domain
from core.models.pathways.path_step import PathStep
from core.models.pathways.path_step_dto import PathStepDTO
from core.models.type_hints import UserUID
from core.ports.query_types import PsDomainInsights, PsPerformanceAnalytics, PsPracticeSummaryResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import _CoreIntelligenceMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.ports import BackendOperations
    from core.services.user.unified_user_context import UserContext

logger = get_logger(__name__)


class PsIntelligenceService(
    _CoreIntelligenceMixin[PathStep],
    BaseAnalyticsService["BackendOperations[PathStep]", "PathStep"],
):
    """
    Intelligence service for PathSteps.

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

    _service_name = "ps.intelligence"

    def __init__(
        self,
        backend: BackendOperations[PathStep],
        graph_intel: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
        executor: Any | None = None,
    ) -> None:
        """
        Initialize PsIntelligenceService.

        NOTE: No embeddings_service or llm_service parameters (ADR-030).
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # Query executor for direct Cypher access
        self.executor = executor

        self._init_context_loader(
            get_entity=self.backend.get,
            dto_class=PathStepDTO,
            model_class=PathStep,
            domain=Domain.LEARNING,
            model_name="PathStep",
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory. `get_with_context()` is inherited from
    # `_CoreIntelligenceMixin[PathStep]` — typed return, one delegation.
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[PsPerformanceAnalytics]:
        """
        Get path step analytics for a user.

        Protocol method: Aggregates path step metrics.
        Used by IntelligenceRouteFactory for GET /api/path-steps/analytics route.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict

        Note: PathSteps are shared curriculum content (no user ownership).
        This returns overall PS statistics rather than user-specific data.
        """
        # PS is shared content - get overall stats
        ps_result = await self.backend.find_by()
        if ps_result.is_error:
            return Result.fail(ps_result)

        all_steps = ps_result.value or []
        total_steps = len(all_steps)

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_path_steps": total_steps,
                "analytics": {
                    "total": total_steps,
                    "note": "PathSteps are shared curriculum content",
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[PsDomainInsights]:
        """
        Get domain-specific insights for a path step.

        Protocol method: Provides PS-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/path-steps/insights route.

        Args:
            uid: Learning Step UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict with practice analysis
        """
        # Get path step
        ps_result = await self.backend.get(uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=uid))

        # Get practice summary
        practice_result = await self.get_practice_summary(uid)
        practice: PsPracticeSummaryResult = (
            practice_result.value
            if practice_result.is_ok
            else {
                "habits": 0,
                "tasks": 0,
                "events": 0,
                "goals": 0,
                "principles": 0,
                "choices": 0,
                "total": 0,
            }
        )

        # Get practice completeness score
        completeness_result = await self.practice_completeness_score(uid)
        completeness = completeness_result.value if completeness_result.is_ok else 0.0

        # Check for prerequisites
        has_prereqs_result = await self.has_prerequisites(uid)
        has_prerequisites = has_prereqs_result.value if has_prereqs_result.is_ok else False

        return Result.ok(
            {
                "ps_uid": uid,
                "ps_title": ps.title,
                "ps_intent": getattr(ps, "intent", None),
                "practice_summary": practice,
                "practice_completeness": completeness,
                "has_prerequisites": has_prerequisites,
                "min_confidence": min_confidence,
            }
        )

    def _require_executor(self) -> Result[Neo4jQueryExecutor]:
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

    @with_error_handling("is_ready", error_type="database", uid_param="ps_uid")
    async def is_ready(self, ps_uid: str, completed_step_uids: set[str]) -> Result[bool]:
        """
        Check if path step is ready based on prerequisite completion.

        A step is ready when ALL its prerequisite steps (via REQUIRES_STEP
        relationship) have been completed.

        Args:
            ps_uid: UID of the path step
            completed_step_uids: Set of completed step UIDs

        Returns:
            Result[bool] - True if all prerequisites are met

        Example:
            result = await intelligence.is_ready(
                "ps:functions",
                {"ps:intro", "ps:syntax"}
            )
            if result.is_ok and result.value:
                print("Ready to learn functions!")
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return Result.fail(executor_result.error)

        def _check_readiness(records: list[dict]) -> bool:
            if not records:
                return True  # No prerequisites = ready
            prereq_uids = set(records[0].get("prereq_uids") or [])
            return prereq_uids.issubset(completed_step_uids)

        return await executor_result.value.execute(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})-[:REQUIRES_STEP]->(prereq:Entity {entity_type: 'path_step'})
                RETURN collect(prereq.uid) as prereq_uids
            """,
            params={"ps_uid": ps_uid},
            processor=_check_readiness,
            operation="is_ready",
        )

    # ========================================================================
    # PRACTICE ANALYSIS
    # ========================================================================

    @with_error_handling("get_practice_summary", error_type="database", uid_param="ps_uid")
    async def get_practice_summary(self, ps_uid: str) -> Result[PsPracticeSummaryResult]:
        """
        Get summary of practice opportunities for a path step.

        Counts all 6 activity
        domains: habits, tasks, events, goals, principles, choices.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[dict] with structure:
            {"habits": int, "tasks": int, "events": int,
             "goals": int, "principles": int, "choices": int, "total": int}

        Example:
            result = await intelligence.get_practice_summary("ps:functions")
            if result.is_ok:
                print(f"Total practice: {result.value['total']} items")
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return Result.fail(executor_result.error)

        def _process_summary(records: list[dict]) -> dict[str, int]:
            if not records:
                return {
                    "habits": 0,
                    "tasks": 0,
                    "events": 0,
                    "goals": 0,
                    "principles": 0,
                    "choices": 0,
                    "total": 0,
                }

            habits = records[0].get("habits", 0)
            tasks = records[0].get("tasks", 0)
            events = records[0].get("events", 0)
            goals = records[0].get("goals", 0)
            principles = records[0].get("principles", 0)
            choices = records[0].get("choices", 0)
            total = habits + tasks + events + goals + principles + choices

            return {
                "habits": habits,
                "tasks": tasks,
                "events": events,
                "goals": goals,
                "principles": principles,
                "choices": choices,
                "total": total,
            }

        return await executor_result.value.execute(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                OPTIONAL MATCH (ps)-[:BUILDS_HABIT]->(h)
                OPTIONAL MATCH (ps)-[:ASSIGNS_TASK]->(t)
                OPTIONAL MATCH (ps)-[:SCHEDULES_EVENT]->(e)
                OPTIONAL MATCH (ps)-[:SUPPORTS_GOAL]->(g)
                OPTIONAL MATCH (ps)-[:GUIDED_BY_PRINCIPLE]->(p)
                OPTIONAL MATCH (ps)-[:INFORMS_CHOICE]->(c)
                RETURN count(DISTINCT h) as habits,
                       count(DISTINCT t) as tasks,
                       count(DISTINCT e) as events,
                       count(DISTINCT g) as goals,
                       count(DISTINCT p) as principles,
                       count(DISTINCT c) as choices
            """,
            params={"ps_uid": ps_uid},
            processor=_process_summary,
            operation="get_practice_summary",
        )

    @with_error_handling("practice_completeness_score", error_type="database", uid_param="ps_uid")
    async def practice_completeness_score(self, ps_uid: str) -> Result[float]:
        """
        Calculate practice completeness (0.0-1.0).

        Full practice suite (all 6 activity domains) = 1.0.
        Each domain contributes 1/6 of the score.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[float] - Practice completeness score (0.0 to 1.0)

        Example:
            result = await intelligence.practice_completeness_score("ps:functions")
            if result.is_ok:
                print(f"Practice completeness: {result.value:.0%}")
        """
        summary_result = await self.get_practice_summary(ps_uid)
        if summary_result.is_error:
            return Result.fail(summary_result)

        summary = summary_result.value
        domain_counts = [
            summary["habits"],
            summary["tasks"],
            summary["events"],
            summary["goals"],
            summary["principles"],
            summary["choices"],
        ]
        present = sum(1 for count in domain_counts if count > 0)

        score = present / len(domain_counts)
        return Result.ok(score)

    # ========================================================================
    # GUIDANCE ANALYSIS
    # ========================================================================

    @with_error_handling("calculate_guidance_strength", error_type="database", uid_param="ps_uid")
    async def calculate_guidance_strength(self, ps_uid: str) -> Result[float]:
        """
        Calculate how well this step guides the learner (0.0-1.0).

        Scoring:
        - Principles provide values-based guidance (40% max)
        - Choices provide inspiration and options (60% max)

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[float] - Guidance strength score (0.0 to 1.0)

        Example:
            result = await intelligence.calculate_guidance_strength("ps:functions")
            if result.is_ok:
                print(f"Guidance strength: {result.value:.0%}")
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return Result.fail(executor_result.error)

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
                MATCH (ps:Entity {uid: $ps_uid})
                OPTIONAL MATCH (ps)-[:GUIDED_BY_PRINCIPLE]->(p)
                OPTIONAL MATCH (ps)-[:INFORMS_CHOICE]->(c)
                RETURN count(DISTINCT p) as principle_count,
                       count(DISTINCT c) as choice_count
            """,
            params={"ps_uid": ps_uid},
            processor=_calculate_score,
            operation="calculate_guidance_strength",
        )

    # ========================================================================
    # EXISTENCE CHECKS (Compound)
    # ========================================================================

    @with_error_handling("has_prerequisites", error_type="database", uid_param="ps_uid")
    async def has_prerequisites(self, ps_uid: str) -> Result[bool]:
        """
        Check if path step has any prerequisites.

        Checks for both:
        - REQUIRES_STEP relationships (other steps)
        - REQUIRES_KNOWLEDGE relationships (KU prerequisites)

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[bool] - True if step has prerequisites

        Example:
            result = await intelligence.has_prerequisites("ps:functions")
            if result.is_ok and result.value:
                print("This step has prerequisites")
        """
        if not self.executor:
            return Result.fail(
                Errors.system(message="Query executor not available", operation="has_prerequisites")
            )

        return await self.executor.execute_exists(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                WHERE exists((ps)-[:REQUIRES_STEP]->()) OR exists((ps)-[:REQUIRES_KNOWLEDGE]->())
                RETURN ps
            """,
            params={"ps_uid": ps_uid},
            operation="has_prerequisites",
        )

    @with_error_handling("has_guidance", error_type="database", uid_param="ps_uid")
    async def has_guidance(self, ps_uid: str) -> Result[bool]:
        """
        Check if path step has guidance (principles or choices).

        Checks direct activity domain relationships.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[bool] - True if step has guidance

        Example:
            result = await intelligence.has_guidance("ps:functions")
            if result.is_ok and result.value:
                print("This step has guidance")
        """
        if not self.executor:
            return Result.fail(
                Errors.system(message="Query executor not available", operation="has_guidance")
            )

        return await self.executor.execute_exists(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                WHERE exists((ps)-[:GUIDED_BY_PRINCIPLE]->())
                   OR exists((ps)-[:INFORMS_CHOICE]->())
                RETURN ps
            """,
            params={"ps_uid": ps_uid},
            operation="has_guidance",
        )

    @with_error_handling("has_practice_opportunities", error_type="database", uid_param="ps_uid")
    async def has_practice_opportunities(self, ps_uid: str) -> Result[bool]:
        """
        Check if path step has practice opportunities.

        Checks all 6 activity domain relationships.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[bool] - True if step has practice opportunities

        Example:
            result = await intelligence.has_practice_opportunities("ps:functions")
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
                MATCH (ps:Entity {uid: $ps_uid})
                WHERE exists((ps)-[:BUILDS_HABIT]->())
                   OR exists((ps)-[:ASSIGNS_TASK]->())
                   OR exists((ps)-[:SCHEDULES_EVENT]->())
                   OR exists((ps)-[:SUPPORTS_GOAL]->())
                   OR exists((ps)-[:GUIDED_BY_PRINCIPLE]->())
                   OR exists((ps)-[:INFORMS_CHOICE]->())
                RETURN ps
            """,
            params={"ps_uid": ps_uid},
            operation="has_practice_opportunities",
        )

    # ========================================================================
    # USER SUBSTANCE & CONTEXTUAL EVALUATION (Migrated Jan 2026)
    # ========================================================================

    async def calculate_user_substance(
        self, ps_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        """
        Calculate how much a user has applied the knowledge taught by this PathStep.

        PathSteps are curriculum entities; their "substance" is derived by analyzing
        the user's application of the underlying atomic Knowledge Units (via USES_KU).
        """
        executor_result = self._require_executor()
        if executor_result.is_error:
            return Result.fail(executor_result.error)

        def _extract_ku_uids(records: list[dict]) -> list[str]:
            return [r["ku_uid"] for r in records if r.get("ku_uid")]

        # 1. Find all KUs taught by this PathStep
        ku_uids_result = await executor_result.value.execute(
            query="""
                MATCH (:Entity {uid: $ps_uid})-[:USES_KU]->(ku:Entity {entity_type: 'ku'})
                RETURN ku.uid AS ku_uid
            """,
            params={"ps_uid": ps_uid},
            processor=_extract_ku_uids,
            operation="calculate_user_substance",
        )

        if ku_uids_result.is_error:
            return Result.fail(ku_uids_result.error)

        ku_uids = ku_uids_result.value

        # 2. Evaluate UserContext across all found KUs
        total_substance = 0.0
        total_mastery = 0.0
        ku_details = []

        for ku_uid in ku_uids:
            # Replicate Knowledge Substance Philosophy weighting for each underlying KU
            task_uid_count = sum(
                1 for kus in user_context.task_knowledge_applied.values() if ku_uid in kus
            )
            habit_uid_count = sum(
                1 for kus in user_context.habit_knowledge_applied.values() if ku_uid in kus
            )
            event_uid_count = sum(
                1 for kus in user_context.event_knowledge_applied.values() if ku_uid in kus
            )
            choice_uid_count = sum(
                1 for kus in user_context.choice_knowledge_informed.values() if ku_uid in kus
            )
            principle_uid_count = sum(
                1 for kus in user_context.principle_knowledge_grounded.values() if ku_uid in kus
            )
            journal_count = 0  # not yet built in UserContext MEGA_QUERY

            task_score = min(0.25, task_uid_count * 0.05)
            habit_score = min(0.30, habit_uid_count * 0.10)
            event_score = min(0.25, event_uid_count * 0.05)
            choice_score = min(0.15, choice_uid_count * 0.07)
            principle_score = min(0.15, principle_uid_count * 0.07)
            journal_score = min(0.20, journal_count * 0.07)

            substance_score = min(
                1.0,
                task_score
                + habit_score
                + event_score
                + choice_score
                + principle_score
                + journal_score,
            )
            mastery_score = user_context.knowledge_mastery.get(ku_uid, 0.0)

            total_substance += substance_score
            total_mastery += mastery_score
            ku_details.append(
                {
                    "ku_uid": ku_uid,
                    "substance_score": round(substance_score, 3),
                    "mastery_score": round(mastery_score, 3),
                    "is_ready_to_learn": ku_uid
                    in getattr(user_context, "ready_to_learn_uids", set()),
                }
            )

        avg_substance = total_substance / len(ku_uids) if ku_uids else 0.0
        avg_mastery = total_mastery / len(ku_uids) if ku_uids else 0.0

        is_ready = bool(ku_uids and all(ku["is_ready_to_learn"] for ku in ku_details))

        if avg_substance >= 0.7:
            status = "Deeply integrated in your lifestyle."
        elif avg_substance >= 0.4:
            status = "Actively applying these concepts."
        elif avg_substance > 0:
            status = "Starting to practice this material."
        else:
            status = "Theoretical only — apply this in practice."

        return Result.ok(
            {
                "ps_uid": ps_uid,
                "user_uid": user_context.user_uid,
                "overall_substance_score": round(avg_substance, 3),
                "overall_mastery_score": round(avg_mastery, 3),
                "is_ready_to_learn": is_ready,
                "taught_kus_count": len(ku_uids),
                "underlying_kus": ku_details,
                "status_message": status,
            }
        )
