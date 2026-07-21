"""
Learning Intelligence Service Facade - Coordination Layer
==========================================================

Facade coordinating all learning intelligence sub-services.

This service is part of the refactored LpIntelligenceService architecture:
- LearningStateAnalyzer: Learning state assessment
- LearningRecommendationEngine: Personalized recommendations
- ContentAnalyzer: Content analysis and metadata
- ContentQualityAssessor: Quality assessment and similarity
- LpIntelligenceService: Facade coordinating all sub-services (THIS FILE)

**January 2026 - LP Consolidation (ADR-031):**
This service now includes methods previously in standalone sub-services:
- Validation methods: validate_path_prerequisites, identify_path_blockers, get_optimal_path_recommendation
- Analysis methods: analyze_path_knowledge_scope
- Adaptive methods: find_learning_sequence, get_next_adaptive_step, get_recommended_path_steps

Architecture (January 2026 - Unified Pattern):
- Extends BaseIntelligenceService[Any, Any] for standardization
- Delegates learning state/content operations to sub-services
- Provides validation, analysis, adaptive, and context methods directly
- Acts as single entry point for ALL learning intelligence operations
- Standalone service (not created by LpService facade)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.constants import LpKnowledgeScopeComplexity
from core.models.pathways.learning_path import LearningPath
from core.models.type_hints import UserUID
from core.ports.content_protocols import ContentAdapter
from core.ports.query_types import (
    LpBlockerAnalysis,
    LpDomainInsights,
    LpPathRecommendation,
    LpPerformanceAnalytics,
    LpPracticeGap,
    LpPracticeGapAnalysis,
    LpPrerequisiteValidation,
    LpRecommendedStep,
)
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import _CoreIntelligenceMixin
from core.services.lp_intelligence.content_analyzer import ContentAnalyzer
from core.services.lp_intelligence.content_quality_assessor import ContentQualityAssessor
from core.services.lp_intelligence.learning_recommendation_engine import (
    LearningRecommendationEngine,
)
from core.services.lp_intelligence.learning_state_analyzer import LearningStateAnalyzer
from core.services.lp_intelligence.types import (
    ContentAnalysisResult,
    ContentMetadata,
    ContentRecommendation,
    LearningAnalysis,
    LearningIntervention,
)
from core.services.ps.ps_intelligence_service import (
    PsIntelligenceService,
    missing_practice_domains,
    practice_completeness_from_summary,
)
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result


def _structural_complexity_score(total_unique_kus: int, max_prerequisite_depth: int) -> float:
    """Blend a path's KU breadth and prerequisite depth into a 0.0-1.0 score.

    A v1 STRUCTURAL score (see `LpKnowledgeScopeComplexity`): each axis
    saturates, then the two combine by weight. Deliberately uses only graph
    facts — no authored difficulty field, no importance weighting (both
    deferred). Interpreting the raw scope facts belongs here at the service
    layer, not in the measuring backend query.
    """
    c = LpKnowledgeScopeComplexity
    breadth = min(total_unique_kus / c.KU_BREADTH_SATURATION, 1.0)
    depth = min(max_prerequisite_depth / c.PREREQUISITE_DEPTH_SATURATION, 1.0)
    return round(breadth * c.BREADTH_WEIGHT + depth * c.DEPTH_WEIGHT, 4)


def _build_practice_recommendations(total_steps: int, gaps: list[LpPracticeGap]) -> list[str]:
    """Human-facing summary of a path's practice gaps.

    Same shape as the validation/blocker analyses: a headline count plus a
    callout for any step that has no practice at all (the worst case — a pure
    reading step). Empty gaps yields a single "all complete" line.
    """
    if not gaps:
        if total_steps == 0:
            return ["Path has no steps to analyze for practice."]
        return [f"All {total_steps} steps have complete practice opportunities."]

    recommendations = [f"{len(gaps)} of {total_steps} steps lack complete practice opportunities."]
    recommendations.extend(
        f"{gap['step_title']} has no practice at all — add a task or habit."
        for gap in gaps
        if gap["practice_completeness"] == 0.0
    )
    return recommendations


class LpIntelligenceService(
    _CoreIntelligenceMixin[LearningPath],
    BaseAnalyticsService[Any, LearningPath],
):
    """
    Unified Learning Path Intelligence Service.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Extends BaseAnalyticsService to follow unified analytics architecture
    pattern (January 2026 - ADR-024, ADR-030).

    **January 2026 - LP Consolidation (ADR-031):**
    This service consolidates ALL learning path intelligence operations:
    - Learning state analysis (via LearningStateAnalyzer sub-service)
    - Content recommendations (via LearningRecommendationEngine sub-service)
    - Content analysis (via ContentAnalyzer/ContentQualityAssessor sub-services)
    - Validation: Prerequisites, blockers, optimal path recommendations
    - Analysis: Knowledge scope
    - Adaptive: Learning sequences, next step, recommendations
    - Context: Path with full graph context

    Architecture:
    - Extends BaseAnalyticsService[Any, LearningPath] for standardized infrastructure
    - Inherits `get_with_context()` from `_CoreIntelligenceMixin[LearningPath]`
    - Delegates state/content ops to 4 focused sub-services
    - Implements validation/analysis/adaptive/context directly
    - Single entry point for ALL learning intelligence
    - Standalone service (not created by LpService facade)
    - NO embeddings_service or llm_service (ADR-030)
    """

    # Service name for hierarchical logging
    _service_name = "lp.intelligence"

    def __init__(
        self,
        backend: Any,
        graph_intel: Any | None = None,
        relationship_service: Any | None = None,
        # LP-specific dependencies
        progress_backend: Any | None = None,
        event_bus: Any | None = None,
        user_service: Any | None = None,
        ps_intelligence: PsIntelligenceService | None = None,
    ) -> None:
        """
        Initialize unified intelligence service.

        Args:
            backend: Primary backend for BaseAnalyticsService and LP operations
            graph_intel: GraphIntelligenceService - gates graph-context retrieval (mechanism B)
            relationship_service: UnifiedRelationshipService (optional)
            progress_backend: Progress backend (LP-specific)
            event_bus: Event bus for publishing events
            user_service: UserService for UserContext
            ps_intelligence: PsIntelligenceService — per-step practice reads for
                path-level practice-gap analysis (identify_practice_gaps). Wired
                from the owning PsService (ps_service.intelligence) at composition.

        NOTE: No embeddings_service or llm_service parameters (ADR-030).
        """
        # Initialize BaseAnalyticsService (no AI dependencies)
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # Store LP-specific dependencies
        self.progress_backend = progress_backend
        self.user_service = user_service
        self.ps_intelligence = ps_intelligence

        # Initialize all sub-services (no AI dependencies - ADR-030)
        self.state_analyzer = LearningStateAnalyzer(
            progress_backend=progress_backend,
            embeddings_service=None,  # ADR-030: No AI dependencies
        )

        self.recommendation_engine = LearningRecommendationEngine(
            state_analyzer=self.state_analyzer,
            learning_backend=self.backend,
            event_bus=event_bus,  # Enable event-driven recommendations
            user_service=user_service,  # Enable UserContext access
        )

        self.content_analyzer = ContentAnalyzer(
            embeddings_service=None,  # ADR-030: No AI dependencies
        )

        self.quality_assessor = ContentQualityAssessor(
            content_analyzer=self.content_analyzer,
        )

        self.logger.info(
            "LpIntelligenceService initialized with consolidated validation/analysis/adaptive methods"
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory. `get_with_context()` is inherited from
    # `_CoreIntelligenceMixin[LearningPath]` — typed return, one delegation.
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[LpPerformanceAnalytics]:
        """
        Get learning path analytics for a user.

        Protocol method: Aggregates learning path metrics.
        Used by IntelligenceRouteFactory for GET /api/learning-paths/analytics route.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data

        Note: Learning Paths are shared curriculum content (no user ownership).
        This returns overall LP statistics rather than user-specific data.
        """
        # LP is shared content - get overall stats
        if not self.backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend required for analytics",
                    operation="get_performance_analytics",
                )
            )

        lp_result = await self.backend.find_by()
        if lp_result.is_error:
            return Result.fail(lp_result)

        all_paths = lp_result.value or []
        total_paths = len(all_paths)

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_learning_paths": total_paths,
                "analytics": {
                    "total": total_paths,
                    "note": "Learning Paths are shared curriculum content",
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[LpDomainInsights]:
        """
        Get domain-specific insights for a learning path.

        Protocol method: Provides LP-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/learning-paths/insights route.

        Args:
            uid: Learning Path UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data with validation and analysis
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend required for insights",
                    operation="get_domain_insights",
                )
            )

        # Get learning path
        lp_result = await self.backend.get(uid)
        if lp_result.is_error:
            return Result.fail(lp_result)

        lp = lp_result.value
        if not lp:
            return Result.fail(Errors.not_found(resource="LearningPath", identifier=uid))

        steps = getattr(lp, "steps", None) or ()
        return Result.ok(
            {
                "lp_uid": uid,
                "lp_title": lp.title,
                "lp_domain": lp.domain.value if lp.domain else None,
                "total_steps": len(steps),
                "min_confidence": min_confidence,
            }
        )

    # ========================================================================
    # LEARNING STATE ANALYSIS (Delegate to LearningStateAnalyzer)
    # ========================================================================

    async def analyze_learning_state(
        self, user_context: UserContext, include_vectors: bool = False
    ) -> Result[LearningAnalysis]:
        """
        Comprehensive analysis of user's learning state.

        Consolidates:
        - Understanding and engagement assessment
        - Readiness determination
        - Learning needs identification
        - Guidance mode and action recommendations
        - Vector-based learning style analysis (if enabled)

        Args:
            user_context: User's current context
            include_vectors: Whether to include vector analysis

        Returns:
            Result[LearningAnalysis]: Complete learning analysis
        """
        return await self.state_analyzer.analyze_learning_state(user_context, include_vectors)

    # ========================================================================
    # RECOMMENDATIONS (Delegate to LearningRecommendationEngine)
    # ========================================================================

    async def recommend_content(
        self, user_context: UserContext, content_pool: list[Any], limit: int = 10
    ) -> Result[list[ContentRecommendation]]:
        """
        Generate intelligent content recommendations.

        Replaces VectorLearningService.get_personalized_recommendations()

        Args:
            user_context: User context
            content_pool: Available content
            limit: Maximum recommendations

        Returns:
            Result[list[ContentRecommendation]]: Ranked content recommendations
        """
        return await self.recommendation_engine.recommend_content(user_context, content_pool, limit)

    async def recommend_learning_paths(
        self, user_context: UserContext, goal: str | None = None
    ) -> Result[list[Any]]:
        """
        Recommend learning paths with intelligence.

        Enhanced version of path recommendations with pedagogical insight.

        Args:
            user_context: User context
            goal: Optional learning goal

        Returns:
            Result[list]: Intelligent path recommendations
        """
        return await self.recommendation_engine.recommend_learning_paths(user_context, goal)

    async def detect_interventions(
        self, user_context: UserContext, recent_activity: dict[str, Any] | None = None
    ) -> Result[list[LearningIntervention]]:
        """
        Detect needed learning interventions.

        Replaces PedagogicalService.should_intervene()

        Args:
            user_context: User context
            recent_activity: Recent learning activity (optional)

        Returns:
            Result[list[LearningIntervention]]: List of recommended interventions
        """
        return await self.recommendation_engine.detect_interventions(user_context, recent_activity)

    async def optimize_learning_session(
        self, user_context: UserContext, available_time_minutes: int
    ) -> Result[dict[str, Any]]:
        """
        Optimize a learning session based on time and state.

        Args:
            user_context: User context
            available_time_minutes: Time available

        Returns:
            Result[dict]: Optimized session plan
        """
        return await self.recommendation_engine.optimize_learning_session(
            user_context, available_time_minutes
        )

    # ========================================================================
    # CONTENT ANALYSIS (Delegate to ContentAnalyzer & ContentQualityAssessor)
    # ========================================================================

    async def analyze_content(self, content: ContentAdapter) -> Result[ContentAnalysisResult]:
        """
        Perform comprehensive content analysis.

        Replaces ContentAnalysisService.analyze_content()

        Args:
            content: Content to analyze (wrapped in ContentAdapter)

        Returns:
            Result[ContentAnalysisResult]: Complete content analysis with quality metrics
        """
        return await self.quality_assessor.analyze_content(content)

    async def extract_content_metadata(self, content: ContentAdapter) -> Result[ContentMetadata]:
        """
        Extract comprehensive metadata from content.

        Args:
            content: Content to analyze (ContentAdapter protocol)

        Returns:
            Result[ContentMetadata] with extracted features and metrics
        """
        return await self.content_analyzer.extract_content_metadata(content)

    async def find_similar_content(
        self, content: ContentAdapter, content_pool: list[ContentAdapter], limit: int = 5
    ) -> Result[list[tuple[ContentAdapter, float]]]:
        """
        Find similar content based on various similarity metrics.

        Args:
            content: Reference content
            content_pool: Pool of content to search
            limit: Maximum results

        Returns:
            Result[list[tuple[ContentAdapter, float]]]: List of (content, similarity_score) tuples
        """
        return await self.quality_assessor.find_similar_content(content, content_pool, limit)

    async def search_by_content_features(
        self,
        has_code: bool | None = None,
        has_images: bool | None = None,
        has_links: bool | None = None,
        has_exercises: bool | None = None,
        min_reading_time: int | None = None,
        max_reading_time: int | None = None,
        keywords: list[str] | None = None,
        content_pool: list[ContentAdapter] | None = None,
    ) -> Result[list[ContentAdapter]]:
        """
        Search content by specific features.

        Args:
            has_code: Filter by code presence
            has_images: Filter by image presence
            has_links: Filter by link presence
            has_exercises: Filter by exercise presence
            min_reading_time: Minimum reading time (minutes)
            max_reading_time: Maximum reading time (minutes)
            keywords: Required keywords
            content_pool: Pool to search in

        Returns:
            Result[list[ContentAdapter]]: Matching content
        """
        return await self.quality_assessor.search_by_content_features(
            has_code=has_code,
            has_images=has_images,
            has_links=has_links,
            has_exercises=has_exercises,
            min_reading_time=min_reading_time,
            max_reading_time=max_reading_time,
            keywords=keywords,
            content_pool=content_pool,
        )

    # ========================================================================
    # VALIDATION OPERATIONS (January 2026 - Consolidated from LpValidationService)
    # ========================================================================

    @with_error_handling("validate_path_prerequisites", error_type="database", uid_param="path_uid")
    async def validate_path_prerequisites(self, path_uid: str) -> Result[LpPrerequisiteValidation]:
        """
        Validate prerequisite ordering in learning path.

        Ensures:
        - Each step's prerequisites are met by earlier steps
        - No circular dependencies
        - Optimal step ordering
        - Knowledge prerequisite alignment

        Args:
            path_uid: Learning path identifier

        Returns:
            Validation results with issues and recommendations
        """
        result = await self.backend.validate_path_prerequisites(path_uid)

        if result.is_error:
            return result

        records = result.value or []
        validations = [r["validation"] for r in records]

        # Analyze validation results
        issues = [v for v in validations if v.get("has_issues")]
        is_valid = len(issues) == 0

        recommendations = []
        if issues:
            recommendations.append("Reorder steps to ensure prerequisites are met")
            for issue in issues[:3]:  # Top 3 issues
                unmet = issue.get("unmet_prerequisites", [])
                recommendations.append(f"Step {issue['sequence']}: Add prerequisites {unmet[:2]}")

        validation_result: LpPrerequisiteValidation = {
            "path_uid": path_uid,
            "is_valid": is_valid,
            "total_steps": len(validations),
            "steps_with_issues": len(issues),
            "issues": issues,
            "recommendations": recommendations,
            "validated_at": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Path validation for {path_uid}: {'VALID' if is_valid else 'INVALID'} ({len(issues)} issues)"
        )
        return Result.ok(validation_result)

    @with_error_handling("identify_path_blockers", error_type="database", uid_param="path_uid")
    async def identify_path_blockers(
        self, path_uid: str, user_uid: UserUID
    ) -> Result[LpBlockerAnalysis]:
        """
        Identify blockers in learning path for a specific user.

        Finds:
        - Steps blocked by unmet prerequisites
        - Knowledge gaps preventing progress
        - Recommended next actions
        - Alternative learning paths

        Args:
            path_uid: Learning path identifier
            user_uid: User identifier

        Returns:
            Blocker analysis with recommendations
        """
        result = await self.backend.identify_path_blockers(path_uid, user_uid)

        if result.is_error:
            return result

        records = result.value or []
        record = records[0] if records else None
        if not record:
            return Result.ok(
                {
                    "recommendations": [],
                    "status": "ready",
                    "blocker_count": 0,
                    "analyzed_at": datetime.now().isoformat(),
                }
            )
        analysis = record["blocker_analysis"]

        # Generate recommendations
        recommendations = []
        first_blocker = analysis.get("first_blocker")

        if first_blocker:
            blocking_prereqs = first_blocker.get("blocking_prerequisites", [])
            if blocking_prereqs:
                recommendations.append(f"Focus on mastering: {blocking_prereqs[0]}")
                recommendations.append(f"This will unblock step {first_blocker['sequence']}")
        else:
            recommendations.append("No blockers - continue with next step!")

        blocked_count = len(analysis.get("blocked_steps", []))

        enhanced_analysis: LpBlockerAnalysis = {
            **analysis,
            "recommendations": recommendations,
            "status": "blocked" if blocked_count > 0 else "ready",
            "blocker_count": blocked_count,
            "analyzed_at": datetime.now().isoformat(),
        }

        self.logger.info(f"Blocker analysis for {path_uid}: {blocked_count} blockers")
        return Result.ok(enhanced_analysis)

    @with_error_handling(
        "get_optimal_path_recommendation", error_type="database", uid_param="user_uid"
    )
    async def get_optimal_path_recommendation(
        self, user_uid: UserUID, goal_domain: str | None = None
    ) -> Result[LpPathRecommendation]:
        """
        Get optimal learning path recommendation for a user.

        Analyzes:
        - User's current knowledge state
        - Available learning paths
        - Prerequisite readiness
        - Goal alignment
        - Estimated completion time

        Args:
            user_uid: User identifier
            goal_domain: Optional domain filter

        Returns:
            Optimal path recommendation
        """
        result = await self.backend.get_optimal_path_recommendations(user_uid, goal_domain)

        if result.is_error:
            return result

        records = result.value or []
        record = records[0] if records else None
        recommendations = record["recommendations"]["recommended_paths"] if record else []

        # Format recommendation
        recommendation: LpPathRecommendation
        if recommendations:
            top_rec = recommendations[0]
            recommendation = {
                "recommended_path_uid": top_rec["path"]["uid"],
                "path_name": top_rec["path"]["name"],
                "readiness_score": top_rec["readiness_score"],
                "estimated_hours": top_rec["estimated_hours"],
                "reason": top_rec["reason"],
                "alternatives": recommendations[1:3],  # Top 3 alternatives
                "recommended_at": datetime.now().isoformat(),
            }
        else:
            recommendation = {
                "recommended_path_uid": None,
                "reason": "No suitable paths found - consider creating a custom path",
                "alternatives": [],
            }

        self.logger.info(
            f"Path recommendation for {user_uid}: {recommendation.get('path_name', 'None')}"
        )
        return Result.ok(recommendation)

    # ========================================================================
    # ANALYSIS OPERATIONS (January 2026 - Consolidated from LpAnalysisService)
    # ========================================================================

    async def analyze_path_knowledge_scope(self, path_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze the knowledge scope of a learning path.

        Aggregates the path's KU coverage from the graph: the distinct KUs it
        teaches across the ``HAS_STEP`` → ``USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU``
        fan-out, how they distribute across steps, and a structural
        ``complexity_score`` blending KU breadth with prerequisite depth.
        Knowledge scope is core LP identity, not an add-on — this fills the
        ``LpOperations`` KNOWLEDGE AGGREGATION contract.

        Backend: LpBackend.get_knowledge_scope_summary + get_all_knowledge_uids.

        Args:
            path_uid: Learning path identifier

        Returns:
            Result[dict]: total_steps, total_unique_kus, kus_per_step,
            max_prerequisite_depth, complexity_score, all_knowledge_uids,
            practice_coverage.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend not available",
                    operation="analyze_path_knowledge_scope",
                )
            )

        # Existence guard — a nonexistent path is not-found, not empty scope.
        path_result = await self.backend.get(path_uid)
        if path_result.is_error:
            return Result.fail(path_result)
        if not path_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        # Backend measures the graph facts; the service interprets them.
        summary_result = await self.backend.get_knowledge_scope_summary(path_uid)
        if summary_result.is_error:
            return Result.fail(summary_result)
        summary = summary_result.value

        uids_result = await self.backend.get_all_knowledge_uids(path_uid)
        if uids_result.is_error:
            return Result.fail(uids_result)

        analysis = {
            **summary,
            "path_uid": path_uid,
            "all_knowledge_uids": sorted(uids_result.value),
            "complexity_score": _structural_complexity_score(
                summary["total_unique_kus"], summary["max_prerequisite_depth"]
            ),
            "practice_coverage": await self._practice_coverage(path_uid),
            "analysis_timestamp": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Knowledge scope analysis for {path_uid}: "
            f"{summary['total_unique_kus']} KUs across {summary['total_steps']} steps"
        )
        return Result.ok(analysis)

    async def _practice_coverage(self, path_uid: str) -> float | None:
        """Path-level mean practice completeness, or None if unavailable.

        Practice coverage is independent of the KU/complexity facts, so it must
        not fail the whole scope: if practice intelligence is unwired or the
        rollup errors, this degrades to None rather than propagating.
        """
        gaps_result = await self.identify_practice_gaps(path_uid)
        if gaps_result.is_error:
            self.logger.warning(
                f"practice_coverage unavailable for {path_uid}: "
                f"{gaps_result.expect_error().message}"
            )
            return None
        return gaps_result.value["overall_practice_coverage"]

    async def identify_practice_gaps(self, path_uid: str) -> Result[LpPracticeGapAnalysis]:
        """Find which steps of a learning path lack complete practice.

        Every step is scored by the canonical PS measure — the fraction of the
        six activity-domain practice edges (``BUILDS_HABIT``, ``ASSIGNS_TASK``,
        ``SCHEDULES_EVENT``, ``SUPPORTS_GOAL``, ``GUIDED_BY_PRINCIPLE``,
        ``INFORMS_CHOICE``) present on it. A step below 1.0 is a *practice gap*:
        the learner can read the concept but has an incomplete set of structured
        ways to embody it. Reuses ``PsIntelligenceService.get_practice_summary``
        per step so LP never forks a competing practice definition (One Path
        Forward); the path-level mean feeds ``practice_coverage`` in
        analyze_path_knowledge_scope.

        Backend: LpBackend.get_steps_raw (ordered steps) +
        PsIntelligenceService per-step practice reads.

        Args:
            path_uid: Learning path identifier

        Returns:
            Result[LpPracticeGapAnalysis]: total_steps, steps_with_gaps,
            overall_practice_coverage, gaps, recommendations.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend not available",
                    operation="identify_practice_gaps",
                )
            )
        if self.ps_intelligence is None:
            return Result.fail(
                Errors.system(
                    message="PathStep intelligence not available for practice analysis",
                    operation="identify_practice_gaps",
                )
            )

        # Existence guard — a nonexistent path is not-found, not empty gaps.
        path_result = await self.backend.get(path_uid)
        if path_result.is_error:
            return Result.fail(path_result)
        if not path_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        steps_result = await self.backend.get_steps_raw(path_uid)
        if steps_result.is_error:
            return Result.fail(steps_result)
        steps = steps_result.value or []

        gaps: list[LpPracticeGap] = []
        completeness_scores: list[float] = []
        for step in steps:
            summary_result = await self.ps_intelligence.get_practice_summary(step.uid)
            if summary_result.is_error:
                return Result.fail(summary_result)
            summary = summary_result.value

            completeness = practice_completeness_from_summary(summary)
            completeness_scores.append(completeness)
            if completeness < 1.0:
                gaps.append(
                    LpPracticeGap(
                        step_uid=step.uid,
                        step_title=step.title or step.uid,
                        practice_completeness=round(completeness, 4),
                        missing_types=missing_practice_domains(summary),
                    )
                )

        overall = (
            round(sum(completeness_scores) / len(completeness_scores), 4)
            if completeness_scores
            else 0.0
        )

        analysis: LpPracticeGapAnalysis = {
            "path_uid": path_uid,
            "total_steps": len(steps),
            "steps_with_gaps": len(gaps),
            "overall_practice_coverage": overall,
            "gaps": gaps,
            "recommendations": _build_practice_recommendations(len(steps), gaps),
            "analysis_timestamp": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Practice gap analysis for {path_uid}: "
            f"{len(gaps)}/{len(steps)} steps with practice gaps"
        )
        return Result.ok(analysis)

    # ========================================================================
    # ADAPTIVE OPERATIONS (January 2026 - Consolidated from LpAdaptiveService)
    # ========================================================================

    @with_error_handling("find_learning_sequence", error_type="database", uid_param="start_uid")
    async def find_learning_sequence(
        self, start_uid: str, goal_uid: str, _user_uid: UserUID | None = None
    ) -> Result[list[str]]:
        """
        Find optimal learning path from start to goal using graph traversal.

        Uses edge metadata:
        - typical_learning_order for sequencing
        - semantic_distance for related knowledge discovery

        Args:
            start_uid: Starting knowledge UID
            goal_uid: Goal knowledge UID
            _user_uid: Optional user UID for personalization

        Returns:
            Result containing list of knowledge UIDs in optimal sequence
        """
        result = await self.backend.find_learning_sequence(start_uid, goal_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record:
            self.logger.info(f"No learning path found from {start_uid} to {goal_uid}")
            return Result.ok([])  # No path found

        sequence = record["sequence"]
        self.logger.info(
            f"Found learning sequence from {start_uid} to {goal_uid}: {len(sequence)} steps"
        )
        return Result.ok(sequence)

    @with_error_handling(
        "get_next_adaptive_step", error_type="database", uid_param="current_step_uid"
    )
    async def get_next_adaptive_step(
        self,
        current_step_uid: str,
        user_uid: UserUID,
        _user_performance: dict[str, float] | None = None,
    ) -> Result[str | None]:
        """
        Get next path step based on adaptive intelligence.

        Uses edge metadata:
        - strength: How strongly concepts are related
        - confidence: How confident we are in the relationship
        - difficulty_gap: Expected difficulty increase

        Args:
            current_step_uid: Current knowledge UID
            user_uid: User UID for personalization
            _user_performance: Optional dict of performance metrics

        Returns:
            Result containing next step UID, or empty string if no ready steps
        """
        result = await self.backend.get_next_adaptive_step(current_step_uid, user_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record:
            self.logger.info(
                f"No ready next step found after {current_step_uid} for user {user_uid}"
            )
            return Result.ok("")  # Empty string instead of None

        next_uid = record["next_uid"]
        readiness = record["readiness_score"]
        difficulty = record["avg_difficulty"]

        self.logger.info(
            f"Next adaptive step for {user_uid}: {next_uid} "
            f"(readiness: {readiness:.2f}, difficulty_gap: {difficulty:.2f})"
        )

        return Result.ok(next_uid)

    @with_error_handling("get_recommended_path_steps", error_type="database", uid_param="user_uid")
    async def get_recommended_path_steps(
        self, user_uid: UserUID, max_difficulty: float = 0.5, limit: int = 5
    ) -> Result[list[LpRecommendedStep]]:
        """
        Get recommended path steps for a user based on their progress.

        Uses intelligence:
        - Semantic distance for related knowledge
        - Edge confidence for relationship quality
        - User progress for readiness assessment

        Args:
            user_uid: User UID
            max_difficulty: Maximum difficulty gap to recommend
            limit: Maximum number of recommendations

        Returns:
            Result containing list of recommendations with metadata
        """
        result = await self.backend.get_recommended_path_steps(user_uid, max_difficulty, limit)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []

        recommendations: list[LpRecommendedStep] = [
            LpRecommendedStep(
                uid=record["uid"],
                title=record["title"],
                domain=record["domain"],
                confidence=record["confidence"],
                strength=record["strength"],
                difficulty_gap=record["difficulty_gap"],
                semantic_distance=record["semantic_distance"],
                prerequisite_readiness=record["prerequisite_readiness"],
            )
            for record in records
        ]

        self.logger.info(f"Found {len(recommendations)} recommended steps for {user_uid}")
        return Result.ok(recommendations)
