"""
Learning State Analyzer - Learning State Assessment
====================================================

Focused service for analyzing user's current learning state.

Responsibilities:
- Analyze learning state (understanding, engagement, readiness)
- Assess learner needs and recommend guidance modes
- Build comprehensive learning analysis with vector integration
- Track progress metrics and learning velocity

This service is part of the refactored LpIntelligenceService architecture:
- LearningStateAnalyzer: Learning state assessment (THIS FILE)
- LearningRecommendationEngine: Personalized recommendations
- ContentAnalyzer: Content analysis and metadata
- ContentQualityAssessor: Quality assessment and similarity
- LpIntelligenceService: Facade coordinating all sub-services

Architecture:
- Depends on progress_backend for user progress data
- Optional embeddings_service for vector analysis
- Uses UserContext as input
"""

from datetime import datetime
from typing import Any

from core.models.enums import GuidanceMode
from core.services.embeddings_service import HuggingFaceEmbeddingsService
from core.services.lp_intelligence.types import LearningAnalysis, LearningReadiness, ProgressSummary
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


class LearningStateAnalyzer:
    """
    Analyze user's current learning state and needs.

    This service handles comprehensive learning state analysis:
    - Understanding and engagement assessment
    - Readiness determination (review, ready, consolidate, break, challenge)
    - Learning needs identification
    - Guidance mode recommendations
    - Action and focus area suggestions
    - Vector-based learning style analysis (optional)

    Architecture:
    - Requires progress_backend (optional - graceful degradation)
    - Optional embeddings_service for vector analysis
    - Uses UserContext as single source of truth
    - Returns frozen dataclass LearningAnalysis
    """

    def __init__(
        self,
        progress_backend: Any | None = None,
        embeddings_service: HuggingFaceEmbeddingsService | None = None,
    ) -> None:
        """
        Initialize learning state analyzer.

        Args:
            progress_backend: Progress backend for user progress data (optional)
            embeddings_service: Embeddings service for vector analysis (optional)
        """
        self.progress_backend = progress_backend
        self.embeddings = embeddings_service

        # Cache for user analyses
        self._analysis_cache: dict[str, LearningAnalysis] = {}

        logger.info("LearningStateAnalyzer initialized")

    # ========================================================================
    # PUBLIC API - LEARNING STATE ANALYSIS
    # ========================================================================

    @with_error_handling("analyze_learning_state", error_type="system")
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
        # Get progress summary (if backend available)
        progress = await self._get_progress_summary(user_context.user_uid)

        # Calculate base metrics
        understanding = self._assess_understanding(user_context, progress)
        engagement = self._assess_engagement(user_context, progress)
        readiness = self._determine_readiness(user_context, progress)

        # Identify needs
        needs = self._identify_learning_needs(understanding, engagement, progress)

        # Generate recommendations
        guidance = self._recommend_guidance_mode(understanding, engagement, user_context)
        actions = self._recommend_actions(readiness, needs, progress)
        focus = self._identify_focus_areas(user_context, progress, needs)

        # Vector analysis if requested
        learning_style_vector = None
        content_affinity = None

        if include_vectors and self.embeddings:
            learning_style_vector = await self._generate_learning_style_vector(user_context)
            content_affinity = await self._calculate_content_affinities(
                user_context, learning_style_vector
            )

        # Create analysis using builder
        analysis = self._build_learning_analysis(
            user_context=user_context,
            understanding=understanding,
            engagement=engagement,
            readiness=readiness,
            needs=needs,
            guidance=guidance,
            actions=actions,
            focus=focus,
            learning_style_vector=learning_style_vector,
            content_affinity=content_affinity,
        )

        # Cache analysis
        self._analysis_cache[user_context.user_uid] = analysis

        logger.info(
            f"Learning analysis complete for {user_context.user_uid}: readiness={readiness.value}"
        )
        return Result.ok(analysis)

    # ========================================================================
    # ASSESSMENT METHODS (Private)
    # ========================================================================

    def _assess_understanding(
        self, user_context: UserContext, progress: ProgressSummary | None
    ) -> float:
        """
        Assess user's understanding level (0-1).

        Args:
            user_context: User context
            progress: Progress summary (optional)

        Returns:
            Understanding level (0-1)
        """
        base_understanding = 0.5

        # Factor in mastery
        if user_context.mastery_average:
            base_understanding = user_context.mastery_average

        # Adjust based on progress
        if progress and progress.learning_mastery_average > 0:
            base_understanding = (base_understanding + progress.learning_mastery_average) / 2

        return min(1.0, base_understanding)

    def _assess_engagement(
        self, _user_context: UserContext, progress: ProgressSummary | None
    ) -> float:
        """
        Assess user's engagement level (0-1).

        Args:
            _user_context: User context (unused - for future use)
            progress: Progress summary (optional)

        Returns:
            Engagement level (0-1)
        """
        base_engagement = 0.5

        # Check recent activity
        if progress:
            # High momentum = high engagement
            base_engagement = progress.overall_momentum_score

            # Boost for consistent habits
            if progress.habits_consistency_rate > 70:
                base_engagement = min(1.0, base_engagement + 0.2)

        return base_engagement

    def _determine_readiness(
        self, user_context: UserContext, progress: ProgressSummary | None
    ) -> LearningReadiness:
        """
        Determine user's learning readiness.

        Args:
            user_context: User context
            progress: Progress summary (optional)

        Returns:
            LearningReadiness enum value
        """
        # Check for review needs
        if len(user_context.concepts_needing_review) > 3:
            return LearningReadiness.REVIEW_NEEDED

        # Check for break needs
        if progress and progress.learning_time_minutes > 120:
            return LearningReadiness.TAKE_BREAK

        # Check mastery level
        if user_context.mastery_average < 0.6:
            return LearningReadiness.CONSOLIDATE

        # Check for challenge readiness
        if (
            user_context.mastery_average > 0.8
            and progress
            and progress.overall_momentum_score > 0.7
        ):
            return LearningReadiness.CHALLENGE_READY

        return LearningReadiness.READY_FOR_NEW

    def _identify_learning_needs(
        self, understanding: float, engagement: float, progress: ProgressSummary | None
    ) -> dict[str, bool]:
        """
        Identify specific learning needs.

        Args:
            understanding: Understanding level
            engagement: Engagement level
            progress: Progress summary (optional)

        Returns:
            Dict of need flags
        """
        return {
            "encouragement": understanding < 0.4 or engagement < 0.3,
            "clarification": understanding < 0.6,
            "challenge": understanding > 0.8 and engagement > 0.7,
            "break": engagement < 0.3
            or (progress is not None and progress.learning_time_minutes > 90),
        }

    def _recommend_guidance_mode(
        self, understanding: float, engagement: float, user_context: UserContext
    ) -> GuidanceMode:
        """
        Recommend pedagogical guidance mode.

        Args:
            understanding: Understanding level
            engagement: Engagement level
            user_context: User context

        Returns:
            GuidanceMode enum value
        """
        # High understanding + high engagement = minimal guidance (exploration)
        if understanding > 0.7 and engagement > 0.7:
            return GuidanceMode.MINIMAL

        # Low understanding = balanced/guided
        if understanding < 0.4:
            return GuidanceMode.BALANCED

        # Medium understanding + preferences (uses conversation_preferences.preferred_guidance_mode)
        if 0.4 <= understanding <= 0.7:
            # Use conversation_preferences property if available
            conv_prefs = getattr(user_context, "conversation_preferences", {})
            if conv_prefs and isinstance(conv_prefs, dict):
                guidance = conv_prefs.get("preferred_guidance_mode")
                if guidance:
                    return guidance

        return GuidanceMode.BALANCED

    def _recommend_actions(
        self, readiness: LearningReadiness, needs: dict[str, bool], progress: ProgressSummary | None
    ) -> list[str]:
        """
        Generate recommended actions.

        Args:
            readiness: Learning readiness
            needs: Learning needs dict
            progress: Progress summary (optional)

        Returns:
            List of recommended actions (max 3)
        """
        actions = []

        if readiness == LearningReadiness.REVIEW_NEEDED:
            actions.append("Review fundamental concepts")
            actions.append("Complete spaced repetition exercises")

        elif readiness == LearningReadiness.CHALLENGE_READY:
            actions.append("Try advanced practice problems")
            actions.append("Start a challenging project")

        elif readiness == LearningReadiness.TAKE_BREAK:
            actions.append("Take a 15-minute break")
            actions.append("Do light review instead of new content")

        if needs["encouragement"]:
            actions.append("Celebrate recent achievements")

        if progress and progress.habits_consistency_rate < 70:
            actions.append("Focus on habit consistency")

        return actions[:3]  # Top 3 actions

    def _identify_focus_areas(
        self,
        user_context: UserContext,
        progress: ProgressSummary | None,
        needs: dict[str, bool],
    ) -> list[str]:
        """
        Identify focus areas for improvement.

        Args:
            user_context: User context
            progress: Progress summary (optional)
            needs: Learning needs dict

        Returns:
            List of focus areas (max 3)
        """
        focus = []

        if user_context.concepts_needing_review:
            focus.append(f"Review: {', '.join(user_context.concepts_needing_review[:2])}")

        if progress:
            if progress.habits_consistency_rate < 70:
                focus.append("Improve daily practice consistency")

            if progress.goals_at_risk > 0:
                focus.append(f"Address {progress.goals_at_risk} at-risk goals")

        if needs["clarification"]:
            focus.append("Clarify foundational concepts")

        return focus[:3]

    def _calculate_confidence(self, understanding: float, engagement: float) -> float:
        """
        Calculate confidence score for analysis.

        Args:
            understanding: Understanding level
            engagement: Engagement level

        Returns:
            Confidence score (0-1)
        """
        # Higher understanding and engagement = higher confidence
        return understanding * 0.6 + engagement * 0.4

    def _build_learning_analysis(
        self,
        user_context: UserContext,
        understanding: float,
        engagement: float,
        readiness: LearningReadiness,
        needs: dict[str, bool],
        guidance: GuidanceMode,
        actions: list[str],
        focus: list[str],
        learning_style_vector: list[float] | None,
        content_affinity: dict[str, float] | None,
    ) -> LearningAnalysis:
        """
        Build complete learning analysis object.

        Args:
            user_context: User context
            understanding: Understanding level
            engagement: Engagement level
            readiness: Learning readiness
            needs: Learning needs dict
            guidance: Recommended guidance mode
            actions: Recommended actions
            focus: Focus areas
            learning_style_vector: Optional learning style vector
            content_affinity: Optional content affinity scores

        Returns:
            Complete LearningAnalysis object
        """
        return LearningAnalysis(
            user_uid=user_context.user_uid,
            timestamp=datetime.now(),
            # Current state
            learning_level=user_context.learning_level.value
            if user_context.learning_level
            else "intermediate",
            mastery_average=user_context.mastery_average,
            concepts_mastered=len(user_context.mastered_knowledge_uids),
            concepts_in_progress=len(user_context.in_progress_knowledge_uids),
            concepts_needing_review=list(user_context.prerequisites_needed.keys())[:5],
            # Assessment
            readiness=readiness,
            confidence_score=self._calculate_confidence(understanding, engagement),
            # Pedagogical
            understanding_level=understanding,
            engagement_level=engagement,
            needs_encouragement=needs["encouragement"],
            needs_clarification=needs["clarification"],
            needs_challenge=needs["challenge"],
            needs_break=needs["break"],
            # Recommendations
            recommended_guidance=guidance,
            recommended_actions=actions,
            focus_areas=focus,
            # Vector analysis (optional)
            learning_style_vector=learning_style_vector,
            content_affinity_scores=content_affinity,
        )

    # ========================================================================
    # VECTOR ANALYSIS (Optional - requires embeddings_service)
    # ========================================================================

    async def _generate_learning_style_vector(
        self, user_context: UserContext
    ) -> list[float] | None:
        """
        Generate learning style vector from user's learning history.

        Args:
            user_context: User context

        Returns:
            Learning style vector or None if no mastered knowledge

        Raises:
            ValueError if embeddings service not configured
        """
        # Fail-fast: embeddings service is required
        if not self.embeddings:
            raise ValueError(
                "EmbeddingsService is required for learning style analysis - "
                "ensure OPENAI_API_KEY is configured"
            )

        try:
            # Combine mastered knowledge UIDs into learning profile text
            mastered_uids = list(user_context.mastered_knowledge_uids)[:20]  # Top 20
            profile_text = " ".join(mastered_uids)

            if not profile_text:
                return None

            # Generate embedding
            embedding_result = await self.embeddings.create_embedding(profile_text)
            if embedding_result.is_error:
                logger.warning(f"Failed to create embedding: {embedding_result.error}")
                return None
            return embedding_result.value

        except Exception as e:
            logger.warning(f"Failed to generate learning style vector: {e}")
            return None

    async def _calculate_content_affinities(
        self, user_context: UserContext, learning_style_vector: list[float] | None
    ) -> dict[str, float] | None:
        """
        Calculate user's affinity scores for different content types.

        Args:
            user_context: User context
            learning_style_vector: Learning style vector

        Returns:
            Dict of content type affinities or None if no learning style vector

        Raises:
            ValueError if embeddings service not configured
        """
        # Fail-fast: embeddings service is required
        if not self.embeddings:
            raise ValueError(
                "EmbeddingsService is required for content affinity analysis - "
                "ensure OPENAI_API_KEY is configured"
            )

        if not learning_style_vector:
            return None

        try:
            # Placeholder for content affinity calculation
            # In real implementation, this would compare learning_style_vector
            # against content type embeddings
            return {
                "technical": 0.8
                if "programming" in str(user_context.mastered_knowledge_uids)
                else 0.5,
                "conceptual": 0.7,
                "practical": 0.6,
            }

        except Exception as e:
            logger.warning(f"Failed to calculate content affinities: {e}")
            return None

    # ========================================================================
    # HELPERS (Private)
    # ========================================================================

    async def _get_progress_summary(self, user_uid: str) -> ProgressSummary | None:
        """
        Get user progress summary from backend.

        Args:
            user_uid: User identifier

        Returns:
            ProgressSummary or None on error

        Raises:
            ValueError if progress backend not configured
        """
        # Fail-fast: progress backend is required for accurate learning analysis
        if not self.progress_backend:
            raise ValueError(
                "ProgressBackend is required for learning state analysis - "
                "ensure backend is properly configured"
            )

        try:
            progress_result = await self.progress_backend.get_user_progress_summary(user_uid)
            return progress_result.value if progress_result.is_ok else None
        except Exception as e:
            logger.warning(f"Progress backend unavailable: {e}")
            return None
