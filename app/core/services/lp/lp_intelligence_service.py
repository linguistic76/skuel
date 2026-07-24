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

**July 2026 - Path-analysis decomposition:**
The directly-implemented validation + analysis block now lives in
`_PathAnalysisMixin` (`_path_analysis_mixin.py`); this file is the shell —
__init__, protocol methods, sub-service delegation, and the adaptive block.
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md

Architecture (January 2026 - Unified Pattern):
- Extends BaseIntelligenceService[Any, Any] for standardization
- Delegates learning state/content operations to sub-services
- Provides validation, analysis, adaptive, and context methods directly
- Acts as single entry point for ALL learning intelligence operations
- Standalone service (not created by LpService facade)
"""

from __future__ import annotations

from typing import Any

from core.models.pathways.learning_path import LearningPath
from core.models.type_hints import UserUID
from core.ports.content_protocols import ContentAdapter
from core.ports.query_types import (
    LpDomainInsights,
    LpPerformanceAnalytics,
    LpRecommendedStep,
)
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import _CoreIntelligenceMixin
from core.services.lp._path_analysis_mixin import _PathAnalysisMixin
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
from core.services.ps.ps_intelligence_service import PsIntelligenceService
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result


class LpIntelligenceService(
    _CoreIntelligenceMixin[LearningPath],
    _PathAnalysisMixin,
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
    - Inherits validation/analysis methods from `_PathAnalysisMixin`
    - Delegates state/content ops to 4 focused sub-services
    - Implements adaptive/context methods directly
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
