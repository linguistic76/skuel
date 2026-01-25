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
- Analysis methods: analyze_path_knowledge_scope, identify_practice_gaps
- Adaptive methods: find_learning_sequence, get_next_adaptive_step, get_recommended_learning_steps
- Context methods: get_path_with_context

Architecture (January 2026 - Unified Pattern):
- Extends BaseIntelligenceService[Any, Any] for standardization
- Delegates learning state/content operations to sub-services
- Provides validation, analysis, adaptive, and context methods directly
- Acts as single entry point for ALL learning intelligence operations
- Standalone service (not created by LpService facade)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.graph_context import GraphContext
from core.models.lp import Lp
from core.models.lp.lp_dto import LpDTO
from core.models.query import QueryIntent
from core.models.shared_enums import Domain
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import GraphContextOrchestrator
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
from core.services.protocols.content_protocols import ContentAdapter
from core.services.user import UserContext
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class LpIntelligenceService(BaseAnalyticsService[Any, Lp]):
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
    - Analysis: Knowledge scope, practice gaps
    - Adaptive: Learning sequences, next step, recommendations
    - Context: Path with full graph context

    Architecture:
    - Extends BaseAnalyticsService[Any, Lp] for standardized infrastructure
    - Delegates state/content ops to 4 focused sub-services
    - Implements validation/analysis/adaptive/context directly
    - Single entry point for ALL learning intelligence
    - Standalone service (not created by LpService facade)
    - NO embeddings_service or llm_service (ADR-030)

    Source Tag: "lp_intelligence_explicit"
    - Format: "lp_intelligence_explicit" for user-created relationships
    - Format: "lp_intelligence_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    # Service name for hierarchical logging
    _service_name = "lp.intelligence"

    def __init__(
        self,
        backend: Any | None = None,  # Primary backend (learning_backend for compatibility)
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        # LP-specific dependencies
        progress_backend: Any | None = None,
        learning_backend: Any | None = None,  # Duplicate of backend for backward compatibility
        event_bus: Any | None = None,
        user_service: Any | None = None,
        driver: AsyncDriver | None = None,  # January 2026: For adaptive/validation operations
    ) -> None:
        """
        Initialize unified intelligence service.

        Args:
            backend: Primary backend for BaseAnalyticsService (optional for backward compat)
            graph_intelligence_service: GraphIntelligenceService - REQUIRED for validation/context
            relationship_service: UnifiedRelationshipService (optional)
            progress_backend: Progress backend (LP-specific)
            learning_backend: Learning backend (LP-specific, also mapped to backend)
            event_bus: Event bus for publishing events
            user_service: UserService for UserContext
            driver: Neo4j async driver - REQUIRED for adaptive operations (January 2026)

        NOTE: No embeddings_service or llm_service parameters (ADR-030).
        """
        # Use learning_backend as primary backend if backend not provided
        primary_backend = backend if backend is not None else learning_backend

        # Initialize BaseAnalyticsService (no AI dependencies)
        super().__init__(
            backend=primary_backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # Store LP-specific dependencies
        self.progress_backend = progress_backend
        self.learning_backend = learning_backend or primary_backend
        self.user_service = user_service

        # January 2026: Store driver and graph_intel for consolidated methods
        self.driver = driver
        self.graph_intel = graph_intelligence_service

        # Initialize all sub-services (no AI dependencies - ADR-030)
        self.state_analyzer = LearningStateAnalyzer(
            progress_backend=progress_backend,
            embeddings_service=None,  # ADR-030: No AI dependencies
        )

        self.recommendation_engine = LearningRecommendationEngine(
            state_analyzer=self.state_analyzer,
            learning_backend=self.learning_backend,
            event_bus=event_bus,  # Phase 4: Enable event-driven recommendations
            user_service=user_service,  # Phase 4: Enable UserContext access
        )

        self.content_analyzer = ContentAnalyzer(
            embeddings_service=None,  # ADR-030: No AI dependencies
        )

        self.quality_assessor = ContentQualityAssessor(
            content_analyzer=self.content_analyzer,
        )

        # Initialize GraphContextOrchestrator for get_with_context pattern
        if graph_intelligence_service and self.learning_backend:
            self.orchestrator = GraphContextOrchestrator[Lp, LpDTO](
                service=self,
                backend_get_method="get",
                dto_class=LpDTO,
                model_class=Lp,
                domain=Domain.LEARNING,
            )

        self.logger.info(
            "LpIntelligenceService initialized with consolidated validation/analysis/adaptive methods"
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Lp, GraphContext]]:
        """
        Get learning path with full graph context.

        Protocol method: Uses GraphContextOrchestrator for generic pattern.
        Used by IntelligenceRouteFactory for GET /api/learning-paths/context route.

        Args:
            uid: Learning Path UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Lp, GraphContext) tuple
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
        Get learning path analytics for a user.

        Protocol method: Aggregates learning path metrics.
        Used by IntelligenceRouteFactory for GET /api/learning-paths/analytics route.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict

        Note: Learning Paths are shared curriculum content (no user ownership).
        This returns overall LP statistics rather than user-specific data.
        """
        # LP is shared content - get overall stats
        if not self.learning_backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend required for analytics",
                    operation="get_performance_analytics",
                )
            )

        lp_result = await self.learning_backend.find_by()
        if lp_result.is_error:
            return Result.fail(lp_result.expect_error())

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
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a learning path.

        Protocol method: Provides LP-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/learning-paths/insights route.

        Args:
            uid: Learning Path UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict with validation and analysis
        """
        if not self.learning_backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend required for insights",
                    operation="get_domain_insights",
                )
            )

        # Get learning path
        lp_result = await self.learning_backend.get(uid)
        if lp_result.is_error:
            return Result.fail(lp_result.expect_error())

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

    def _build_prerequisite_query(self, knowledge_var: str = "k", depth: int = 3) -> str:
        """
        Build pure Cypher prerequisite subquery using semantic relationships.

        Args:
            knowledge_var: Variable name for knowledge node in query
            depth: Maximum prerequisite depth

        Returns:
            Cypher subquery fragment for prerequisite discovery
        """
        prerequisite_types = [
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
            SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
            SemanticRelationshipType.BUILDS_ON_FOUNDATION,
        ]

        rel_pattern = "|".join([st.to_neo4j_name() for st in prerequisite_types])

        return f"""
        OPTIONAL MATCH ({knowledge_var})<-[:{rel_pattern}*1..{depth}]-(prereq:Ku)
        WITH {knowledge_var}, collect(DISTINCT prereq) as prereqs
        """

    @requires_graph_intelligence("validate_path_prerequisites")
    @with_error_handling("validate_path_prerequisites", error_type="database", uid_param="path_uid")
    async def validate_path_prerequisites(self, path_uid: str) -> Result[dict[str, Any]]:
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
        cypher_query = f"""
        MATCH (path:Lp {{uid: $path_uid}})
        MATCH (path)-[r:HAS_STEP]->(step:Ls)
        MATCH (k:Ku {{uid: step.knowledge_uid}})

        // Get all prerequisites using pure Cypher
        {self._build_prerequisite_query("k", 3)}

        // Check if prerequisites are in earlier steps
        WITH path, step, k, r.sequence as step_seq, prereqs
        MATCH (path)-[r2:HAS_STEP]->(earlier:Ls)
        WHERE r2.sequence < step_seq

        WITH step, k, step_seq, prereqs,
             collect(earlier.knowledge_uid) as earlier_knowledge

        // Find unmet prerequisites
        WITH step, k, step_seq,
             [p IN prereqs WHERE NOT p.uid IN earlier_knowledge | p.uid] as unmet_prereqs

        RETURN {{
            step_uid: step.uid,
            knowledge_uid: k.uid,
            sequence: step_seq,
            unmet_prerequisites: unmet_prereqs,
            has_issues: size(unmet_prereqs) > 0
        }} as validation
        ORDER BY step_seq
        """

        # Type narrowing for MyPy (decorator ensures graph_intel is not None)
        assert self.graph_intel is not None
        result = await self.graph_intel.execute_query(
            cypher_query, {"path_uid": path_uid}, query_intent=QueryIntent.PREREQUISITE
        )

        if result.is_error:
            return result

        validations = result.value.get("validation", [])

        # Analyze validation results
        issues = [v for v in validations if v.get("has_issues")]
        is_valid = len(issues) == 0

        recommendations = []
        if issues:
            recommendations.append("Reorder steps to ensure prerequisites are met")
            for issue in issues[:3]:  # Top 3 issues
                unmet = issue.get("unmet_prerequisites", [])
                recommendations.append(f"Step {issue['sequence']}: Add prerequisites {unmet[:2]}")

        validation_result = {
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

    @requires_graph_intelligence("identify_path_blockers")
    @with_error_handling("identify_path_blockers", error_type="database", uid_param="path_uid")
    async def identify_path_blockers(self, path_uid: str, user_uid: str) -> Result[dict[str, Any]]:
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
        cypher_query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (path:Lp {{uid: $path_uid}})

        // Get user's mastered knowledge
        OPTIONAL MATCH (u)-[m:MASTERED]->(mastered:Ku)
        WITH u, path, collect(mastered.uid) as mastered_uids

        // Get path steps
        MATCH (path)-[r:HAS_STEP]->(step:Ls)
        MATCH (k:Ku {{uid: step.knowledge_uid}})

        // Check prerequisites
        {self._build_prerequisite_query("k", 2)}

        WITH step, k, r.sequence as seq, mastered_uids, prereqs,
             [p IN prereqs WHERE NOT p.uid IN mastered_uids] as blocking_prereqs

        // Identify blockers
        WITH step, k, seq,
             blocking_prereqs,
             size(blocking_prereqs) > 0 as is_blocked

        ORDER BY seq

        // Find first blocker
        WITH collect({{
            step: step,
            knowledge: k,
            sequence: seq,
            is_blocked: is_blocked,
            blocking_prerequisites: blocking_prereqs
        }}) as all_steps

        WITH all_steps,
             [s IN all_steps WHERE s.is_blocked][0] as first_blocker

        RETURN {{
            total_steps: size(all_steps),
            blocked_steps: [s IN all_steps WHERE s.is_blocked],
            first_blocker: first_blocker,
            can_progress: first_blocker IS NULL
        }} as blocker_analysis
        """

        # Type narrowing for MyPy (decorator ensures graph_intel is not None)
        assert self.graph_intel is not None
        result = await self.graph_intel.execute_query(
            cypher_query,
            {"path_uid": path_uid, "user_uid": user_uid},
            query_intent=QueryIntent.PREREQUISITE,
        )

        if result.is_error:
            return result

        analysis = result.value.get("blocker_analysis", {})

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

        enhanced_analysis = {
            **analysis,
            "recommendations": recommendations,
            "status": "blocked" if blocked_count > 0 else "ready",
            "blocker_count": blocked_count,
            "analyzed_at": datetime.now().isoformat(),
        }

        self.logger.info(f"Blocker analysis for {path_uid}: {blocked_count} blockers")
        return Result.ok(enhanced_analysis)

    @requires_graph_intelligence("get_optimal_path_recommendation")
    @with_error_handling(
        "get_optimal_path_recommendation", error_type="database", uid_param="user_uid"
    )
    async def get_optimal_path_recommendation(
        self, user_uid: str, goal_domain: str | None = None
    ) -> Result[dict[str, Any]]:
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
        domain_filter = "AND path.domain = $domain" if goal_domain else ""

        cypher_query = f"""
        MATCH (u:User {{uid: $user_uid}})

        // Get user's mastered knowledge
        OPTIONAL MATCH (u)-[m:MASTERED]->(mastered:Ku)
        WITH u, collect(mastered.uid) as mastered_uids

        // Get available paths
        MATCH (path:Lp)
        WHERE NOT (u)-[:COMPLETED]->(path) {domain_filter}

        // Calculate path readiness
        MATCH (path)-[:HAS_STEP]->(step:Ls)
        MATCH (k:Ku {{uid: step.knowledge_uid}})

        // Get prerequisites
        {self._build_prerequisite_query("k", 2)}

        WITH path, mastered_uids,
             size([p IN prereqs WHERE p.uid IN mastered_uids]) as met,
             size(prereqs) as total

        WITH path,
             CASE WHEN total = 0 THEN 1.0
                  ELSE toFloat(met) / total
             END as readiness_score

        // Get path with best readiness
        WITH path, readiness_score
        ORDER BY readiness_score DESC, path.estimated_hours ASC
        LIMIT 5

        RETURN {{
            recommended_paths: collect({{
                path: path,
                readiness_score: readiness_score,
                estimated_hours: path.estimated_hours,
                reason: CASE
                    WHEN readiness_score > 0.8 THEN "High readiness - prerequisites mostly met"
                    WHEN readiness_score > 0.5 THEN "Moderate readiness - some prerequisites needed"
                    ELSE "Low readiness - build foundations first"
                END
            }})
        }} as recommendations
        """

        params: dict[str, Any] = {"user_uid": user_uid}
        if goal_domain:
            params["domain"] = goal_domain

        # Type narrowing for MyPy (decorator ensures graph_intel is not None)
        assert self.graph_intel is not None
        result = await self.graph_intel.execute_query(
            cypher_query, params, query_intent=QueryIntent.EXPLORATORY
        )

        if result.is_error:
            return result

        recommendations = result.value.get("recommendations", {}).get("recommended_paths", [])

        # Format recommendation
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

        Uses Lp model methods to provide comprehensive curriculum analysis.

        Args:
            path_uid: Learning path identifier

        Returns:
            Knowledge scope analysis including coverage, complexity, practice
        """
        if not self.learning_backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend not available",
                    operation="analyze_path_knowledge_scope",
                )
            )

        # Get the path using backend
        path_result = await self.learning_backend.get(path_uid)
        if path_result.is_error:
            return path_result

        path = path_result.value
        if not path:
            return Result.fail(Errors.not_found(resource="Lp", identifier=path_uid))

        # Use model methods for analysis
        scope_summary = path.get_knowledge_scope_summary()
        all_knowledge_uids = path.get_all_knowledge_uids()
        primary_knowledge = path.get_primary_knowledge_uids()
        supporting_knowledge = path.get_supporting_knowledge_uids()

        analysis = {
            **scope_summary,
            "all_knowledge_uids": list(all_knowledge_uids),
            "primary_knowledge_uids": list(primary_knowledge),
            "supporting_knowledge_uids": list(supporting_knowledge),
            "knowledge_complexity": path.knowledge_complexity_score(),
            "practice_coverage": path.practice_coverage_score(),
            "analysis_timestamp": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Knowledge scope analysis for {path_uid}: {analysis['total_unique_knowledge_units']} units"
        )
        return Result.ok(analysis)

    async def identify_practice_gaps(self, path_uid: str) -> Result[dict[str, Any]]:
        """
        Identify learning steps that lack complete practice opportunities.

        Phase 3 Graph-Native: This method requires LsRelationships.fetch() to check
        practice relationships (BUILDS_HABIT, ASSIGNS_TASK, SCHEDULES_EVENT).
        Currently returns placeholder analysis - needs relationship service injection.

        Args:
            path_uid: Learning path identifier

        Returns:
            Practice gap analysis with recommendations
        """
        if not self.learning_backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend not available", operation="identify_practice_gaps"
                )
            )

        # Get the path using backend
        path_result = await self.learning_backend.get(path_uid)
        if path_result.is_error:
            return path_result

        path = path_result.value
        if not path:
            return Result.fail(Errors.not_found(resource="Lp", identifier=path_uid))

        # Phase 3 Graph-Native: Practice relationship fields (task_uids, habit_uids,
        # event_template_uids) are NOT on Ls model. They require LsRelationships.fetch()
        # which needs UnifiedRelationshipService injected into this service.
        #
        # For now, return placeholder analysis indicating all steps need review.
        # Full implementation requires:
        # 1. Inject ls_relationships_service into LpIntelligenceService
        # 2. For each step: rels = await LsRelationships.fetch(step.uid, service)
        # 3. Check rels.habit_uids, rels.task_uids, rels.event_template_uids
        gaps = [
            {
                "step_uid": step.uid,
                "step_title": step.title,
                "practice_completeness": 0.0,  # Placeholder - needs relationship query
                "missing_elements": ["requires_relationship_query"],
            }
            for step in path.steps
        ]

        analysis = {
            "path_uid": path_uid,
            "total_steps": len(path.steps),
            "steps_with_gaps": len(gaps),
            "overall_practice_coverage": 0.0,  # Placeholder
            "gaps": gaps,
            "recommendations": [
                "Practice gap analysis requires LsRelationships integration (Phase 3 Graph-Native)"
            ],
            "analyzed_at": datetime.now().isoformat(),
            "_note": "Graph-native migration incomplete - needs UnifiedRelationshipService",
        }

        self.logger.info(
            f"Practice gap analysis for {path_uid}: placeholder (needs relationship service)"
        )
        return Result.ok(analysis)

    # ========================================================================
    # ADAPTIVE OPERATIONS (January 2026 - Consolidated from LpAdaptiveService)
    # ========================================================================

    @with_error_handling("find_learning_sequence", error_type="database", uid_param="start_uid")
    async def find_learning_sequence(
        self, start_uid: str, goal_uid: str, _user_uid: str | None = None
    ) -> Result[list[str]]:
        """
        Find optimal learning path from start to goal using graph traversal.

        Uses Phase 4 edge metadata:
        - typical_learning_order for sequencing
        - semantic_distance for related knowledge discovery

        Args:
            start_uid: Starting knowledge UID
            goal_uid: Goal knowledge UID
            _user_uid: Optional user UID for personalization

        Returns:
            Result containing list of knowledge UIDs in optimal sequence
        """
        if not self.driver:
            return Result.fail(
                Errors.system("Neo4j driver not available", operation="find_learning_sequence")
            )

        query = """
        MATCH path = shortestPath(
            (start:Ku {uid: $start_uid})-[:ENABLES|PREREQUISITE*]-(goal:Ku {uid: $goal_uid})
        )
        WITH path, relationships(path) as rels

        // Sort by typical_learning_order if available (Phase 4 edge metadata)
        UNWIND rels as r
        WITH path, r
        ORDER BY coalesce(r.typical_learning_order, 999)

        RETURN [node IN nodes(path) | node.uid] as sequence
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"start_uid": start_uid, "goal_uid": goal_uid})
            record = await result.single()

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
        user_uid: str,
        _user_performance: dict[str, float] | None = None,
    ) -> Result[str | None]:
        """
        Get next learning step based on adaptive intelligence.

        Uses Phase 4 edge metadata:
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
        if not self.driver:
            return Result.fail(
                Errors.system("Neo4j driver not available", operation="get_next_adaptive_step")
            )

        query = """
        MATCH (current:Ku {uid: $current_uid})-[r:ENABLES]->(next:Ku)

        // Get user progress for prerequisites (Phase 4 user progress tracking)
        OPTIONAL MATCH (next)<-[:PREREQUISITE]-(prereq)
        OPTIONAL MATCH (prereq)<-[:HAS_PROGRESS]-(up:UserProgress {user_uid: $user_uid})

        WITH next, r,
             count(prereq) as total_prereqs,
             count(CASE WHEN up.mastery_level >= 0.7 THEN 1 END) as completed_prereqs,
             avg(coalesce(r.confidence, 1.0)) as avg_confidence,
             avg(coalesce(r.strength, 1.0)) as avg_strength,
             avg(coalesce(r.difficulty_gap, 0.3)) as avg_difficulty

        // Calculate prerequisite readiness
        WITH next,
             CASE
                 WHEN total_prereqs = 0 THEN 1.0
                 ELSE toFloat(completed_prereqs) / total_prereqs
             END as prerequisite_readiness,
             avg_confidence,
             avg_strength,
             avg_difficulty

        // Filter to ready steps (80% of prerequisites complete)
        WHERE prerequisite_readiness >= 0.8

        // Score by confidence (60%) and strength (40%) - Phase 4 metadata
        WITH next,
             (avg_confidence * 0.6 + avg_strength * 0.4) as readiness_score,
             avg_difficulty,
             prerequisite_readiness
        ORDER BY readiness_score DESC, avg_difficulty ASC

        RETURN next.uid as next_uid,
               readiness_score,
               avg_difficulty,
               prerequisite_readiness
        LIMIT 1
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"current_uid": current_step_uid, "user_uid": user_uid}
            )
            record = await result.single()

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

    @with_error_handling(
        "get_recommended_learning_steps", error_type="database", uid_param="user_uid"
    )
    async def get_recommended_learning_steps(
        self, user_uid: str, max_difficulty: float = 0.5, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """
        Get recommended learning steps for a user based on their progress.

        Uses Phase 4 intelligence:
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
        if not self.driver:
            return Result.fail(
                Errors.system(
                    "Neo4j driver not available", operation="get_recommended_learning_steps"
                )
            )

        query = """
        // Find knowledge units user has mastered
        MATCH (mastered:Ku)<-[:HAS_PROGRESS]-(up:UserProgress {user_uid: $user_uid})
        WHERE up.mastery_level >= 0.7

        // Find next steps enabled by mastered knowledge
        MATCH (mastered)-[r:ENABLES]->(next:Ku)

        // Check if user hasn't started this yet
        WHERE NOT exists((next)<-[:HAS_PROGRESS]-(:UserProgress {user_uid: $user_uid}))

        // Check prerequisite readiness
        OPTIONAL MATCH (next)<-[:PREREQUISITE]-(prereq)
        OPTIONAL MATCH (prereq)<-[:HAS_PROGRESS]-(prereq_progress:UserProgress {user_uid: $user_uid})

        WITH next, r,
             count(prereq) as total_prereqs,
             count(CASE WHEN prereq_progress.mastery_level >= 0.7 THEN 1 END) as completed_prereqs

        // Calculate readiness
        WITH next, r,
             CASE
                 WHEN total_prereqs = 0 THEN 1.0
                 ELSE toFloat(completed_prereqs) / total_prereqs
             END as prerequisite_readiness

        // Filter by readiness and difficulty (Phase 4 metadata)
        WHERE prerequisite_readiness >= 0.8
          AND coalesce(r.difficulty_gap, 0.3) <= $max_difficulty

        // Return recommendations with metadata
        RETURN DISTINCT next.uid as uid,
               next.title as title,
               next.domain as domain,
               coalesce(r.confidence, 1.0) as confidence,
               coalesce(r.strength, 1.0) as strength,
               coalesce(r.difficulty_gap, 0.3) as difficulty_gap,
               coalesce(r.semantic_distance, 0.5) as semantic_distance,
               prerequisite_readiness

        ORDER BY (confidence * 0.4 + strength * 0.3 + prerequisite_readiness * 0.3) DESC,
                 difficulty_gap ASC

        LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"user_uid": user_uid, "max_difficulty": max_difficulty, "limit": limit}
            )

            recommendations = [
                {
                    "uid": record["uid"],
                    "title": record["title"],
                    "domain": record["domain"],
                    "confidence": record["confidence"],
                    "strength": record["strength"],
                    "difficulty_gap": record["difficulty_gap"],
                    "semantic_distance": record["semantic_distance"],
                    "prerequisite_readiness": record["prerequisite_readiness"],
                }
                async for record in result
            ]

            self.logger.info(f"Found {len(recommendations)} recommended steps for {user_uid}")
            return Result.ok(recommendations)

    # ========================================================================
    # CONTEXT OPERATIONS (January 2026 - Consolidated from LpContextService)
    # ========================================================================

    @requires_graph_intelligence("get_path_with_context")
    @with_error_handling("get_path_with_context", error_type="database", uid_param="path_uid")
    async def get_path_with_context(
        self, path_uid: str, user_uid: str | None = None, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get learning path with complete graph context.

        Single query retrieves:
        - Path steps with knowledge details
        - Prerequisite chains for each step
        - User mastery state (if user_uid provided)
        - Blocking prerequisites
        - Related learning paths

        Args:
            path_uid: Learning path identifier
            user_uid: Optional user for mastery context
            depth: Graph traversal depth

        Returns:
            Complete path with graph context
        """
        # Build query with optional user context
        user_match = "MATCH (u:User {uid: $user_uid})" if user_uid else ""
        mastery_check = (
            """
            OPTIONAL MATCH (u)-[m:MASTERED]->(k)
            WITH path, step, k, m.level as mastery
        """
            if user_uid
            else "WITH path, step, k, null as mastery"
        )

        cypher_query = f"""
        MATCH (path:Lp {{uid: $path_uid}})
        {user_match}

        // Get all steps with knowledge
        MATCH (path)-[r:HAS_STEP]->(step:Ls)
        MATCH (k:Ku {{uid: step.knowledge_uid}})

        // Get prerequisites using pure Cypher
        {self._build_prerequisite_query("k", depth)}

        {mastery_check}

        // Calculate step readiness
        WITH path, step, k, mastery, prereqs,
             size([p IN prereqs WHERE {("p.uid IN u.mastered_uids" if user_uid else "false")}]) as met_prereqs,
             size(prereqs) as total_prereqs
        WITH path, step, k, mastery,
             CASE WHEN total_prereqs = 0 THEN 1.0
                  ELSE toFloat(met_prereqs) / total_prereqs
             END as readiness

        // Get related paths
        OPTIONAL MATCH (path)-[:SIMILAR_TO]-(related:Lp)

        WITH path, collect({{
            step: step,
            knowledge: k,
            mastery: mastery,
            readiness: readiness,
            is_blocking: mastery IS NULL OR mastery < 0.7
        }}) as steps, collect(DISTINCT related) as related_paths

        RETURN {{
            path: path,
            steps: steps,
            related_paths: related_paths,
            total_steps: size(steps),
            completed_steps: size([s IN steps WHERE s.mastery >= 0.8]),
            blocking_steps: [s IN steps WHERE s.is_blocking | s.step.uid]
        }} as path_context
        """

        # Execute query
        params: dict[str, Any] = {"path_uid": path_uid}
        if user_uid:
            params["user_uid"] = user_uid

        # Type narrowing for MyPy (decorator ensures graph_intel is not None)
        assert self.graph_intel is not None
        result = await self.graph_intel.execute_query(
            cypher_query, params, query_intent=QueryIntent.HIERARCHICAL
        )

        if result.is_error:
            return result

        context = result.value.get("path_context", {})

        # Calculate progress
        total = context.get("total_steps", 0)
        completed = context.get("completed_steps", 0)
        progress = (completed / total * 100) if total > 0 else 0

        # Generate insights
        blocking = context.get("blocking_steps", [])
        insights = []
        if blocking:
            insights.append(f"{len(blocking)} step(s) blocked by prerequisites")
        if progress > 80:
            insights.append("Nearly complete - final push!")
        elif progress > 50:
            insights.append("Over halfway - maintain momentum")

        enhanced_context = {
            **context,
            "progress_percentage": progress,
            "insights": insights,
            "timestamp": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Path context for {path_uid}: {progress:.1f}% complete, {len(blocking)} blockers"
        )
        return Result.ok(enhanced_context)


# ============================================================================
# FACTORY FUNCTION (Bootstrap Compatibility)
# ============================================================================


def create_lp_intelligence_service(
    progress_backend: Any | None = None,
    learning_backend: Any | None = None,
    graph_intelligence_service: Any = None,
    driver: Any = None,  # January 2026: For consolidated adaptive/validation methods
) -> LpIntelligenceService:
    """
    Factory function to create LpIntelligenceService instance.

    NOTE: No embeddings_service parameter (ADR-030).

    Args:
        progress_backend: Progress backend (Universal Backend pattern)
        learning_backend: Learning backend (Universal Backend pattern)
        graph_intelligence_service: GraphIntelligenceService
        driver: Neo4j async driver (January 2026 - for consolidated methods)

    Returns:
        LpIntelligenceService: Configured service instance (facade pattern)
    """
    return LpIntelligenceService(
        progress_backend=progress_backend,
        learning_backend=learning_backend,
        graph_intelligence_service=graph_intelligence_service,
        driver=driver,
    )
