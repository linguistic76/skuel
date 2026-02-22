"""
Learning Recommendation Engine - Personalized Recommendations
==============================================================

Focused service for generating personalized learning recommendations.

Responsibilities:
- Content recommendations based on learning state
- Learning path recommendations with pedagogical insight
- Intervention detection (encouragement, clarification, challenge, breaks)
- Session optimization based on available time and readiness

This service is part of the refactored LpIntelligenceService architecture:
- LearningStateAnalyzer: Learning state assessment
- LearningRecommendationEngine: Personalized recommendations (THIS FILE)
- ContentAnalyzer: Content analysis and metadata
- ContentQualityAssessor: Quality assessment and similarity
- LpIntelligenceService: Facade coordinating all sub-services

Architecture:
- Depends on LearningStateAnalyzer for learning state analysis
- Optional learning_backend for path data
- Returns Result[T] for error handling
- Uses UserContext as input
"""

from typing import Any

from core.events import LearningPathCompleted, publish_event
from core.ports.content_protocols import ContentAdapter, ensure_content_protocol
from core.services.lp_intelligence.learning_state_analyzer import LearningStateAnalyzer
from core.services.lp_intelligence.types import (
    ContentRecommendation,
    LearningAnalysis,
    LearningIntervention,
    LearningReadiness,
)
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_intervention_priority, get_relevance_score

logger = get_logger(__name__)


class LearningRecommendationEngine:
    """
    Generate personalized learning recommendations and interventions.

    This service handles intelligent recommendation generation:
    - Content recommendations (relevance, readiness, difficulty matching)
    - Learning path recommendations (pedagogically enhanced)
    - Intervention detection (encouragement, clarification, challenge, breaks)
    - Session optimization (time-based learning plans)

    Architecture:
    - Requires LearningStateAnalyzer for learning state
    - Optional learning_backend for path data (graceful degradation)
    - Uses ContentAdapter protocol for content
    - Returns frozen dataclasses for recommendations
    """

    def __init__(
        self,
        state_analyzer: LearningStateAnalyzer,
        learning_backend: Any | None = None,
        event_bus: Any | None = None,
        user_service: Any | None = None,
    ) -> None:
        """
        Initialize learning recommendation engine.

        Args:
            state_analyzer: LearningStateAnalyzer for learning state
            learning_backend: Learning backend for path data (optional)
            event_bus: Event bus for publishing recommendation events (Phase 4)
            user_service: UserService for getting UserContext (Phase 4)
        """
        self.state_analyzer = state_analyzer
        self.learning_backend = learning_backend
        self.event_bus = event_bus
        self.user_service = user_service

        logger.info("LearningRecommendationEngine initialized")

    # ========================================================================
    # EVENT HANDLERS (Phase 4: Event-Driven Architecture)
    # ========================================================================

    async def handle_learning_path_completed(self, event: LearningPathCompleted) -> None:
        """
        Generate learning path recommendations when user completes a path.

        Event-driven handler that triggers intelligent next-path recommendations
        based on the completed learning path.

        Args:
            event: LearningPathCompleted event containing path completion details

        Phase 4 Integration:
        - Subscribes to: LearningPathCompleted
        - Publishes: LearningRecommendationGenerated (via event bus)
        """
        try:
            from core.events.learning_events import LearningRecommendationGenerated

            logger.info(
                f"Learning path completed: {event.path_uid} by user {event.user_uid} "
                f"({event.kus_mastered} KUs mastered)"
            )

            # Check dependencies
            if not self.user_service:
                logger.warning(
                    "No user_service available - cannot generate intelligent recommendations"
                )
                return

            if not self.learning_backend:
                logger.warning("No learning_backend available for path recommendations")
                return

            # Get full UserContext from UserService
            context_result = await self.user_service.get_user_context(event.user_uid)
            if context_result.is_error:
                logger.error(
                    f"Failed to get user context for {event.user_uid}: {context_result.error}"
                )
                return

            user_context = context_result.value

            # Generate intelligent learning path recommendations using full context
            recommendations_result = await self.recommend_learning_paths(
                user_context=user_context, _goal=None
            )

            if recommendations_result.is_error:
                logger.error(f"Failed to generate recommendations: {recommendations_result.error}")
                return

            recommended_path_uids = recommendations_result.value

            # Determine recommendation reason based on completion metrics
            reason = "next_in_sequence"
            if event.completed_ahead_of_schedule:
                reason = "accelerated_learner"
            elif event.average_mastery_score >= 0.9:
                reason = "high_mastery"

            # Publish recommendation event
            rec_event = LearningRecommendationGenerated(
                user_uid=event.user_uid,
                occurred_at=event.occurred_at,
                recommended_ku_uids=recommended_path_uids,
                recommendation_reason=reason,
            )
            await publish_event(self.event_bus, rec_event, logger)
            logger.info(
                f"Published {len(recommended_path_uids)} learning path recommendations "
                f"for user {event.user_uid} (reason: {reason})"
            )

        except Exception as e:
            # Best-effort: Log error but don't raise (prevent blocking completion flow)
            logger.error(f"Error handling learning_path_completed event: {e}")

    async def handle_knowledge_mastered(self, event: Any) -> None:
        """
        Generate content recommendations when user masters a knowledge unit.

        Event-driven handler that triggers intelligent next-topic recommendations
        based on the mastered knowledge unit.

        Args:
            event: KnowledgeMastered event containing mastery details

        Phase 4 Integration:
        - Subscribes to: KnowledgeMastered
        - Publishes: LearningRecommendationGenerated (via event bus)
        """
        try:
            from core.events.learning_events import LearningRecommendationGenerated

            logger.info(
                f"Knowledge unit mastered: {event.ku_uid} by user {event.user_uid} "
                f"(mastery score: {event.mastery_score:.2f})"
            )

            # Determine recommendation strategy based on mastery score
            if event.mastery_score >= 0.9:
                # High mastery - recommend advanced/challenging content
                reason = "advanced_topics"
                logger.debug(
                    f"High mastery ({event.mastery_score:.2f}) - recommending advanced topics"
                )
            elif event.mastery_score >= 0.7:
                # Good mastery - recommend related/parallel topics
                reason = "related_topics"
                logger.debug(
                    f"Good mastery ({event.mastery_score:.2f}) - recommending related topics"
                )
            else:
                # Minimal mastery - recommend reinforcement
                reason = "reinforcement"
                logger.debug(
                    f"Minimal mastery ({event.mastery_score:.2f}) - recommending reinforcement"
                )

            # Generate and publish recommendations
            # In real implementation, would:
            # 1. Query related KUs based on semantic similarity
            # 2. Check prerequisite chains for next logical steps
            # 3. Consider learning path context if available

            recommended_ku_uids: list[str] = []  # Placeholder for actual recommendations

            rec_event = LearningRecommendationGenerated(
                user_uid=event.user_uid,
                occurred_at=event.occurred_at,
                recommended_ku_uids=recommended_ku_uids,
                recommendation_reason=reason,
            )
            await publish_event(self.event_bus, rec_event, logger)
            logger.info(f"Published KU recommendations for user {event.user_uid}: {reason}")

        except Exception as e:
            # Best-effort: Log error but don't raise (prevent blocking mastery flow)
            logger.error(f"Error handling knowledge_mastered event: {e}")

    # ========================================================================
    # PUBLIC API - CONTENT RECOMMENDATIONS
    # ========================================================================

    @with_error_handling("recommend_content", error_type="system")
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
        # Get learning analysis (with vectors for better recommendations)
        analysis_result = await self.state_analyzer.analyze_learning_state(
            user_context, include_vectors=True
        )
        if analysis_result.is_error:
            return Result.fail(
                Errors.system(
                    message="Failed to analyze learning state for content recommendations",
                    operation="recommend_content",
                )
            )
        analysis = analysis_result.value

        recommendations = []

        for raw_content in content_pool:
            # Ensure content conforms to protocol
            content = ensure_content_protocol(raw_content)

            # Calculate scores
            relevance = await self._calculate_relevance(content, user_context, analysis)
            readiness = self._calculate_readiness_score(content, analysis)
            difficulty_match = self._calculate_difficulty_match(content, analysis)

            # Check prerequisites
            prereqs_met = self._check_prerequisites(content, user_context)

            # Determine learning impact
            impact = self._determine_learning_impact(content, analysis)

            # Generate reason
            reason = self._generate_recommendation_reason(
                relevance, readiness, difficulty_match, impact
            )

            # Calculate confidence score (weighted combination)
            confidence_score = relevance * 0.4 + readiness * 0.3 + difficulty_match * 0.3

            rec = ContentRecommendation(
                content_uid=content.uid,
                content_type=content.content_type,
                title=content.title,
                relevance_score=relevance,
                difficulty_match=difficulty_match,
                prerequisites_met=prereqs_met,
                learning_impact=impact,
                recommendation_reason=reason,
                confidence_score=confidence_score,
            )

            recommendations.append(rec)

        # Sort by confidence score (descending)
        from core.utils.sort_functions import get_confidence_score_attr

        recommendations.sort(key=get_confidence_score_attr, reverse=True)

        return Result.ok(recommendations[:limit])

    @with_error_handling("recommend_learning_paths", error_type="system")
    async def recommend_learning_paths(
        self, user_context: UserContext, _goal: str | None = None
    ) -> Result[list[Any]]:
        """
        Recommend learning paths with intelligence.

        Enhanced version of path recommendations with pedagogical insight.

        Args:
            user_context: User context
            _goal: Optional learning goal (unused - for future use)

        Returns:
            Result[list]: Intelligent path recommendations
        """
        # Get analysis
        analysis_result = await self.state_analyzer.analyze_learning_state(user_context)
        if analysis_result.is_error:
            return Result.fail(
                Errors.system(
                    message="Failed to analyze learning state for path recommendations",
                    operation="recommend_learning_paths",
                    user_uid=user_context.user_uid,
                )
            )
        analysis = analysis_result.value

        # Get available paths from learning backend (if available)
        if self.learning_backend:
            try:
                paths_result = await self.learning_backend.find_paths_for_user(
                    user_context.user_uid, user_context
                )
                if paths_result.is_error:
                    return Result.fail(
                        Errors.system(
                            message="Failed to retrieve learning paths from backend",
                            operation="recommend_learning_paths",
                            user_uid=user_context.user_uid,
                        )
                    )

                recommendations = paths_result.value

                # Enhance recommendations with intelligence
                for rec in recommendations:
                    # Adjust relevance based on analysis
                    if analysis.readiness == LearningReadiness.REVIEW_NEEDED and (
                        "review" in rec.path.tags or "fundamentals" in rec.path.tags
                    ):
                        # Boost review-focused paths
                        rec.relevance_score *= 1.5

                    elif (
                        analysis.readiness == LearningReadiness.CHALLENGE_READY
                        and rec.path.difficulty_level == "advanced"
                    ):
                        # Boost advanced paths
                        rec.relevance_score *= 1.3

                    # Add pedagogical reason
                    rec.reason = self._enhance_path_reason(rec.reason, analysis)

                # Re-sort with enhanced scores
                recommendations.sort(key=get_relevance_score, reverse=True)

                return Result.ok(recommendations)

            except Exception as e:
                logger.warning(f"Learning backend unavailable: {e}")

        return Result.ok([])

    # ========================================================================
    # PUBLIC API - INTERVENTION DETECTION
    # ========================================================================

    @with_error_handling("detect_interventions", error_type="system")
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
        # Step 1: Get learning analysis
        analysis_result = await self.state_analyzer.analyze_learning_state(user_context)
        if analysis_result.is_error:
            return Result.fail(
                Errors.system(
                    message="Failed to analyze learning state for intervention detection",
                    operation="detect_interventions",
                    user_uid=user_context.user_uid,
                )
            )
        analysis = analysis_result.value

        interventions = []

        # Step 2: Check for basic learning needs
        if analysis.needs_encouragement:
            interventions.append(self._create_encouragement_intervention())

        if analysis.needs_clarification:
            interventions.append(self._create_clarification_intervention())

        if analysis.needs_challenge:
            interventions.append(self._create_challenge_intervention())

        if analysis.needs_break:
            interventions.append(self._create_break_intervention())

        # Step 3: Check recent activity patterns
        if recent_activity:
            additional = self._detect_activity_interventions(recent_activity, analysis)
            interventions.extend(additional)

        # Step 4: Sort by priority
        interventions.sort(key=get_intervention_priority, reverse=True)

        logger.info(f"Detected {len(interventions)} interventions for {user_context.user_uid}")
        return Result.ok(interventions)

    # ========================================================================
    # PUBLIC API - SESSION OPTIMIZATION
    # ========================================================================

    @with_error_handling("optimize_learning_session", error_type="system")
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
        # Step 1: Get learning analysis
        analysis_result = await self.state_analyzer.analyze_learning_state(user_context)
        if analysis_result.is_error:
            return Result.fail(
                Errors.system(
                    message="Failed to analyze learning state for session optimization",
                    operation="optimize_learning_session",
                    user_uid=user_context.user_uid,
                    available_time_minutes=available_time_minutes,
                )
            )
        analysis = analysis_result.value

        # Step 2: Build base session plan
        session_plan = {
            "total_time": available_time_minutes,
            "segments": [],
            "focus": analysis.recommended_guidance.value,
            "objectives": [],
        }

        remaining_time = available_time_minutes

        # Step 3: Add review segment if needed
        if analysis.readiness == LearningReadiness.REVIEW_NEEDED:
            remaining_time = self._add_review_segment(session_plan, remaining_time, analysis)

        # Step 4: Add learning segment if ready for new content
        if remaining_time > 0 and analysis.readiness in [
            LearningReadiness.READY_FOR_NEW,
            LearningReadiness.CHALLENGE_READY,
        ]:
            remaining_time = self._add_learning_segment(session_plan, remaining_time, analysis)

        # Step 5: Add practice segment with remaining time
        if remaining_time > 0:
            remaining_time = self._add_practice_segment(session_plan, remaining_time)

        # Step 6: Add break recommendations for long sessions
        if available_time_minutes > 45:
            session_plan["break_after"] = 25
            session_plan["break_duration"] = 5

        logger.info(
            f"Session optimized for {user_context.user_uid}: {len(session_plan['segments'])} segments"
        )
        return Result.ok(session_plan)

    # ========================================================================
    # CONTENT SCORING (Private)
    # ========================================================================

    async def _calculate_relevance(
        self, content: Any, user_context: UserContext, analysis: LearningAnalysis
    ) -> float:
        """
        Calculate content relevance score.

        Args:
            content: Content to score
            user_context: User context
            analysis: Learning analysis

        Returns:
            Relevance score (0-1)
        """
        relevance = 0.5

        # Check topic match
        content_tags = set(content.tags)
        user_interests = set(user_context.get_top_facets("tags", n=10))
        if content_tags & user_interests:
            relevance += 0.2

        # Check vector similarity if available
        if analysis.content_affinity_scores:
            content_type = content.content_type
            if content_type in analysis.content_affinity_scores:
                relevance += analysis.content_affinity_scores[content_type] * 0.3

        return min(1.0, relevance)

    def _calculate_readiness_score(
        self, content: ContentAdapter, analysis: LearningAnalysis
    ) -> float:
        """
        Calculate readiness score for content.

        Args:
            content: Content to score
            analysis: Learning analysis

        Returns:
            Readiness score (0-1)
        """
        if analysis.readiness == LearningReadiness.REVIEW_NEEDED:
            # Prefer review content
            if content.content_type == "review":
                return 1.0
            return 0.5

        elif analysis.readiness == LearningReadiness.CHALLENGE_READY:
            # Prefer challenging content
            if content.difficulty == "advanced":
                return 1.0
            return 0.6

        return 0.7  # Neutral readiness

    def _calculate_difficulty_match(
        self, content: ContentAdapter, analysis: LearningAnalysis
    ) -> float:
        """
        Calculate difficulty match score.

        Args:
            content: Content to score
            analysis: Learning analysis

        Returns:
            Difficulty match score (0-1)
        """
        content_difficulty = content.difficulty
        user_level = analysis.learning_level

        # Perfect match
        if content_difficulty == user_level:
            return 1.0

        # One level difference
        level_map = {"beginner": 1, "intermediate": 2, "advanced": 3}
        content_num = level_map.get(content_difficulty, 2)
        user_num = level_map.get(user_level, 2)

        if abs(content_num - user_num) == 1:
            return 0.7

        return 0.3  # Too far apart

    def _check_prerequisites(self, content: ContentAdapter, user_context: UserContext) -> bool:
        """
        Check if prerequisites are met.

        Args:
            content: Content to check
            user_context: User context

        Returns:
            True if prerequisites met, False otherwise
        """
        return all(
            prereq in user_context.mastered_knowledge_uids for prereq in content.prerequisites
        )

    def _determine_learning_impact(
        self, content: ContentAdapter, analysis: LearningAnalysis
    ) -> str:
        """
        Determine learning impact type.

        Args:
            content: Content to assess
            analysis: Learning analysis

        Returns:
            Impact type ("foundational", "progressive", "advanced")
        """
        if analysis.readiness == LearningReadiness.REVIEW_NEEDED:
            return "foundational"

        if content.difficulty == "advanced":
            return "advanced"

        return "progressive"

    def _generate_recommendation_reason(
        self, relevance: float, readiness: float, difficulty: float, impact: str
    ) -> str:
        """
        Generate human-readable recommendation reason.

        Args:
            relevance: Relevance score
            readiness: Readiness score
            difficulty: Difficulty match score
            impact: Learning impact type

        Returns:
            Human-readable reason string
        """
        reasons = []

        if relevance > 0.7:
            reasons.append("Highly relevant to your interests")

        if readiness > 0.8:
            reasons.append("Perfect timing for your learning journey")

        if difficulty > 0.8:
            reasons.append("Matches your skill level")

        if impact == "foundational":
            reasons.append("Strengthens fundamental knowledge")
        elif impact == "advanced":
            reasons.append("Challenges you to grow")

        return "; ".join(reasons) if reasons else "Recommended for you"

    def _enhance_path_reason(self, original_reason: str, analysis: LearningAnalysis) -> str:
        """
        Enhance path recommendation reason with pedagogical insight.

        Args:
            original_reason: Original recommendation reason
            analysis: Learning analysis

        Returns:
            Enhanced reason string
        """
        additions = []

        if analysis.needs_encouragement:
            additions.append("Great for building confidence")

        if analysis.readiness == LearningReadiness.CHALLENGE_READY:
            additions.append("Perfect challenge for your level")

        if analysis.understanding_level > 0.7:
            additions.append("Ready to explore advanced concepts")

        if additions:
            return f"{original_reason}; {'; '.join(additions)}"

        return original_reason

    # ========================================================================
    # INTERVENTION CREATION (Private)
    # ========================================================================

    def _create_encouragement_intervention(self) -> LearningIntervention:
        """Create encouragement intervention."""
        return LearningIntervention(
            intervention_type="encouragement",
            priority=0.9,
            message="You're making progress! Every step counts.",
            suggested_action="Review your achievements this week",
            estimated_impact="Boost motivation and engagement",
        )

    def _create_clarification_intervention(self) -> LearningIntervention:
        """Create clarification intervention."""
        return LearningIntervention(
            intervention_type="clarification",
            priority=0.8,
            message="Let's clarify some concepts before moving forward.",
            suggested_action="Review fundamentals with examples",
            estimated_impact="Improve understanding by 30%",
        )

    def _create_challenge_intervention(self) -> LearningIntervention:
        """Create challenge intervention."""
        return LearningIntervention(
            intervention_type="challenge",
            priority=0.7,
            message="You're ready for more advanced content!",
            suggested_action="Try an advanced practice project",
            estimated_impact="Accelerate mastery development",
        )

    def _create_break_intervention(self) -> LearningIntervention:
        """Create break intervention."""
        return LearningIntervention(
            intervention_type="break",
            priority=0.95,
            message="Time for a break to consolidate learning.",
            suggested_action="Take a 15-minute break or switch to review",
            estimated_impact="Prevent burnout, improve retention",
        )

    def _detect_activity_interventions(
        self, activity: dict[str, Any], _analysis: LearningAnalysis
    ) -> list[LearningIntervention]:
        """
        Detect interventions from recent activity patterns.

        Args:
            activity: Recent activity data
            _analysis: Learning analysis (unused - for future use)

        Returns:
            List of activity-based interventions
        """
        interventions = []

        # Check for struggling pattern
        if activity.get("failures", 0) > 3:
            interventions.append(
                LearningIntervention(
                    intervention_type="support",
                    priority=0.85,
                    message="Let's try a different approach",
                    suggested_action="Switch to guided practice mode",
                    estimated_impact="Reduce frustration, improve success rate",
                )
            )

        # Check for rapid completion (might be too easy)
        if activity.get("completion_speed", 0) > 2:  # 2x normal speed
            interventions.append(
                LearningIntervention(
                    intervention_type="acceleration",
                    priority=0.6,
                    message="You're mastering this quickly!",
                    suggested_action="Skip to more advanced content",
                    estimated_impact="Maintain engagement, accelerate progress",
                )
            )

        return interventions

    # ========================================================================
    # SESSION OPTIMIZATION HELPERS (Private)
    # ========================================================================

    def _add_review_segment(
        self, session_plan: dict[str, Any], remaining_time: int, analysis: LearningAnalysis
    ) -> int:
        """
        Add review segment to session plan.

        Args:
            session_plan: Session plan dictionary
            remaining_time: Remaining time in minutes
            analysis: Learning analysis

        Returns:
            Updated remaining time
        """
        review_time = min(remaining_time, 20)
        session_plan["segments"].append(
            {
                "type": "review",
                "duration": review_time,
                "content": analysis.concepts_needing_review[:3],
                "approach": "spaced_repetition",
            }
        )
        session_plan["objectives"].append("Strengthen fundamentals")
        return remaining_time - review_time

    def _add_learning_segment(
        self, session_plan: dict[str, Any], remaining_time: int, analysis: LearningAnalysis
    ) -> int:
        """
        Add learning segment to session plan.

        Args:
            session_plan: Session plan dictionary
            remaining_time: Remaining time in minutes
            analysis: Learning analysis

        Returns:
            Updated remaining time
        """
        learn_time = min(remaining_time, 25)
        session_plan["segments"].append(
            {
                "type": "learn",
                "duration": learn_time,
                "difficulty": "advanced"
                if analysis.readiness == LearningReadiness.CHALLENGE_READY
                else "appropriate",
                "approach": analysis.recommended_guidance.value,
            }
        )
        session_plan["objectives"].append("Master new concepts")
        return remaining_time - learn_time

    def _add_practice_segment(self, session_plan: dict[str, Any], remaining_time: int) -> int:
        """
        Add practice segment to session plan.

        Args:
            session_plan: Session plan dictionary
            remaining_time: Remaining time in minutes

        Returns:
            Updated remaining time (should be 0)
        """
        session_plan["segments"].append(
            {
                "type": "practice",
                "duration": remaining_time,
                "focus": "application",
                "approach": "hands_on",
            }
        )
        session_plan["objectives"].append("Apply knowledge")
        return 0
