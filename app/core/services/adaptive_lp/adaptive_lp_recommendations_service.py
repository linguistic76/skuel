"""
Adaptive Learning Path Recommendations Service
==============================================

Handles adaptive recommendations based on knowledge gaps and user context.

Focuses on:
- Knowledge gap identification
- Reinforcement recommendations
- Exploration recommendations
- Recommendation scoring and ranking
"""

from datetime import datetime
from operator import attrgetter
from typing import Any

from core.models.enums import EntityStatus
from core.models.goal.goal_dto import GoalDTO
from core.models.task.task_dto import TaskDTO

# Import dataclasses from shared models module (breaks circular dependency)
from core.services.adaptive_lp.adaptive_lp_models import (
    AdaptiveRecommendation,
    LearningStyle,
    RecommendationType,
)
from core.services.adaptive_lp_types import KnowledgeState

# NOTE (November 2025): Removed HasTargetDate - Goal model is well-typed
# - Goal.target_date: date | None (direct access)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator


class AdaptiveLpRecommendationsService:
    """
    Service for generating adaptive learning recommendations.

    Focuses on:
    - Comprehensive knowledge gap identification
    - Gap-filling recommendations
    - Reinforcement recommendations for existing knowledge
    - Exploration recommendations for new areas


    Source Tag: "adaptive_lp_recommendations_service_explicit"
    - Format: "adaptive_lp_recommendations_service_explicit" for user-created relationships
    - Format: "adaptive_lp_recommendations_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from adaptive_lp_recommendations metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self, ku_service=None, goals_service=None, tasks_service=None, ku_generation_service=None
    ) -> None:
        """
        Initialize the recommendations service.

        Args:
            ku_service: For accessing knowledge units,
            goals_service: For user goals and progress,
            tasks_service: For task completion patterns,
            ku_generation_service: For pattern analysis
        """
        self.ku_service = ku_service
        self.goals_service = goals_service
        self.tasks_service = tasks_service
        self.ku_generation_service = ku_generation_service
        self.logger = get_logger("skuel.adaptive_lp_recommendations")

    @with_error_handling(error_type="system", uid_param="user_uid")
    async def generate_adaptive_recommendations(
        self,
        user_uid: str,
        knowledge_state: KnowledgeState,
        learning_style: LearningStyle,
        context: dict[str, Any] | None = None,
    ) -> Result[list[AdaptiveRecommendation]]:
        """
        Generate adaptive recommendations based on knowledge gaps and user context.

        Args:
            user_uid: User to generate recommendations for,
            knowledge_state: Current knowledge state analysis,
            learning_style: User's detected learning style,
            context: Additional context for personalization

        Returns:
            Result containing list of AdaptiveRecommendation objects
        """
        # Identify knowledge gaps
        gaps_result = await self._identify_comprehensive_knowledge_gaps(user_uid, knowledge_state)
        if gaps_result.is_error:
            return Result.fail(gaps_result.expect_error())

        knowledge_gaps = gaps_result.value

        # Generate recommendations for each gap
        recommendations = []

        for gap in knowledge_gaps[:10]:  # Limit to top 10 gaps
            recommendation = await self._create_gap_filling_recommendation(
                gap, user_uid, knowledge_state, learning_style, context
            )
            if recommendation:
                recommendations.append(recommendation)

        # Add reinforcement recommendations
        reinforcement_recs = await self._generate_reinforcement_recommendations(
            user_uid, knowledge_state, learning_style
        )
        recommendations.extend(reinforcement_recs)

        # Add exploration recommendations
        exploration_recs = await self._generate_exploration_recommendations(
            user_uid, knowledge_state, learning_style
        )
        recommendations.extend(exploration_recs)

        # Score and rank all recommendations
        scored_recommendations = await self._score_and_rank_recommendations(
            recommendations, user_uid, knowledge_state
        )

        self.logger.info(
            f"Generated {len(scored_recommendations)} adaptive recommendations for user {user_uid}"
        )

        return Result.ok(scored_recommendations[:20])  # Return top 20

    @with_error_handling(error_type="system", uid_param="user_uid")
    async def _identify_comprehensive_knowledge_gaps(
        self, user_uid: str, knowledge_state: KnowledgeState
    ) -> Result[list[str]]:
        """Identify comprehensive knowledge gaps across all user goals and interests."""
        gaps = set()

        # Get user's goals
        if self.goals_service:
            goals_result = await self.goals_service.get_user_goals(user_uid)
            if goals_result.is_ok:
                for goal in goals_result.value:
                    goal_gaps_result = await self._identify_goal_knowledge_gaps(
                        goal, knowledge_state
                    )
                    if goal_gaps_result.is_ok:
                        gaps.update(goal_gaps_result.value)

        # Analyze task patterns to infer additional gaps
        if self.tasks_service:
            tasks_result = await self.tasks_service.get_user_tasks(user_uid)
            if tasks_result.is_ok:
                task_gaps = await self._infer_gaps_from_task_patterns(
                    tasks_result.value, knowledge_state
                )
                gaps.update(task_gaps)

        # Use knowledge generation service to identify pattern-based gaps
        if self.ku_generation_service:
            try:
                patterns_result = await self.ku_generation_service.analyze_task_completion_patterns(
                    [t for t in tasks_result.value if t.status == EntityStatus.COMPLETED]
                    if tasks_result.is_ok
                    else []
                )
                if patterns_result.is_ok:
                    pattern_gaps = await self._extract_gaps_from_patterns(
                        patterns_result.value, knowledge_state
                    )
                    gaps.update(pattern_gaps)
            except Exception as e:
                self.logger.debug(f"Pattern-based gap analysis failed: {e}")

        return Result.ok(list(gaps))

    @with_error_handling(error_type="system")
    async def _identify_goal_knowledge_gaps(
        self, goal: GoalDTO, knowledge_state: KnowledgeState
    ) -> Result[list[str]]:
        """Identify knowledge gaps preventing goal achievement."""
        gaps = []

        # Analyze goal requirements (this would normally query a knowledge graph)
        # For now, use heuristic based on goal content
        goal_text = f"{goal.title} {goal.description}".lower()

        # Map common goal keywords to knowledge areas
        knowledge_mappings = {
            "python": ["ku.programming.python", "ku.programming.basics"],
            "web development": ["ku.web.html", "ku.web.css", "ku.web.javascript"],
            "data analysis": ["ku.data.analysis", "ku.data.visualization", "ku.statistics"],
            "machine learning": [
                "ku.ml.fundamentals",
                "ku.ml.algorithms",
                "ku.data.preprocessing",
            ],
            "api": ["ku.api.rest", "ku.api.design", "ku.programming.http"],
            "database": ["ku.database.sql", "ku.database.design", "ku.database.optimization"],
            "testing": ["ku.testing.unit", "ku.testing.integration", "ku.testing.automation"],
            "deployment": ["ku.devops.docker", "ku.devops.ci_cd", "ku.cloud.basics"],
        }

        # Find required knowledge for goal
        required_knowledge = set()
        for keyword, knowledge_uids in knowledge_mappings.items():
            if keyword in goal_text:
                required_knowledge.update(knowledge_uids)

        # Compare with user's current knowledge
        mastered = knowledge_state.mastered_knowledge
        applied = knowledge_state.applied_knowledge
        current_knowledge = mastered.union(applied)

        # Identify gaps
        gaps = list(required_knowledge - current_knowledge)

        self.logger.debug(f"Identified {len(gaps)} knowledge gaps for goal '{goal.title}': {gaps}")

        return Result.ok(gaps)

    # DEFERRED: DEFERRED-ARG-001 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
    async def _infer_gaps_from_task_patterns(
        self, tasks: list[TaskDTO], knowledge_state: KnowledgeState
    ) -> list[str]:
        """
        Infer knowledge gaps from task completion patterns and difficulties.

        DEFERRED IMPLEMENTATION (Graph-Native):
        ==================================
        Parameters accepted but unused pending TasksRelationshipService wiring.

        Why Deferred:
        - Service already works via other gap detection strategies (goal-based, pattern-based)
        - This is 1 of 3 gap identification methods - not critical path
        - Wiring TasksRelationshipService requires bootstrap changes
        - Better ROI focusing on other refactorings first

        Future Implementation:
        1. Wire TasksRelationshipService into this service's __init__
        2. Fetch TaskRelationships for each task
        3. Analyze rels.prerequisite_knowledge_uids for missing prerequisites
        4. Analyze rels.applies_knowledge_uids for foundation gaps

        Args:
            tasks: User tasks (currently unused - see deferral note above)
            knowledge_state: Current knowledge state (currently unused - see deferral note above)

        Returns:
            Empty list (graceful degradation - other gap strategies still work)
        """
        # DEFERRED: Relationship-based gap analysis
        # For now, return empty - other gap detection methods still functional

        # Original logic commented out until relationship fetching is implemented:
        # incomplete_tasks = [t for t in tasks if t.status not in [EntityStatus.COMPLETED, EntityStatus.CANCELLED]]
        # for task in incomplete_tasks:
        # if task.prerequisite_knowledge_uids: # Field doesn't exist anymore
        # user_knowledge = knowledge_state.get('applied_knowledge', set())
        # missing_prereqs = set(task.prerequisite_knowledge_uids) - user_knowledge
        # gaps.extend(missing_prereqs)
        #
        # completed_tasks = [t for t in tasks if t.status == EntityStatus.COMPLETED]
        # for task in completed_tasks:
        # if task.actual_minutes and task.duration_minutes and task.actual_minutes > task.duration_minutes * 1.5:

        return []

    async def _extract_gaps_from_patterns(
        self, _patterns: list, knowledge_state: KnowledgeState
    ) -> list[str]:
        """Extract knowledge gaps from detected task patterns.

        Note: patterns parameter reserved for future implementation when pattern analysis is added.
        """
        gaps = []

        # This would analyze patterns from the knowledge generation service
        # For now, return simplified gap inference
        user_domains = set()
        applied_knowledge = knowledge_state.applied_knowledge

        for ku_uid in applied_knowledge:
            if "." in ku_uid:
                user_domains.add(ku_uid.split(".")[1])

        # Suggest complementary domains
        if "programming" in user_domains:
            gaps.extend(["ku.testing.fundamentals", "ku.database.basics"])

        if "web" in user_domains:
            gaps.extend(["ku.security.web", "ku.performance.optimization"])

        return gaps

    async def _create_gap_filling_recommendation(
        self,
        knowledge_gap: str,
        user_uid: str,
        knowledge_state: KnowledgeState,
        learning_style: LearningStyle,
        _context: dict[str, Any] | None,
    ) -> AdaptiveRecommendation | None:
        """Create a recommendation to fill a specific knowledge gap."""
        try:
            # Create knowledge-focused recommendation
            return AdaptiveRecommendation(
                recommendation_id=UIDGenerator.generate_random_uid("adaptive_rec"),
                recommendation_type=RecommendationType.PREREQUISITE,
                title=f"Learn {knowledge_gap.split('.')[-1].title()}",
                description=f"Master {knowledge_gap} to strengthen your foundation",
                knowledge_uid=knowledge_gap,
                related_goals=await self._find_goals_needing_knowledge(user_uid, knowledge_gap),
                application_suggestions=await self._generate_application_suggestions(
                    knowledge_gap, knowledge_state
                ),
                relevance_score=await self._calculate_gap_relevance(knowledge_gap, knowledge_state),
                impact_score=await self._calculate_gap_impact(knowledge_gap, user_uid),
                confidence_score=0.8,  # High confidence for gap-filling
                urgency_score=await self._calculate_gap_urgency(knowledge_gap, user_uid),
                gap_address_score=1.0,  # Directly addresses gap
                goal_alignment_score=await self._calculate_goal_alignment(knowledge_gap, user_uid),
                style_match_score=await self._calculate_style_match_for_knowledge(
                    knowledge_gap, learning_style
                ),
                difficulty_appropriateness=await self._assess_difficulty_appropriateness(
                    knowledge_gap, knowledge_state
                ),
                reasoning="This knowledge is essential for your current goals and fills an identified gap in your learning journey",
                prerequisites_met=await self._check_prerequisites_met(
                    knowledge_gap, knowledge_state
                ),
                estimated_time_minutes=await self._estimate_learning_time(knowledge_gap),
            )

        except Exception as e:
            self.logger.warning(
                f"Failed to create gap-filling recommendation for {knowledge_gap}: {e}"
            )
            return None

    async def _generate_reinforcement_recommendations(
        self, _user_uid: str, knowledge_state: KnowledgeState, _learning_style: LearningStyle
    ) -> list[AdaptiveRecommendation]:
        """Generate recommendations to reinforce existing knowledge."""
        recommendations = []

        # Find knowledge that could benefit from reinforcement
        applied_knowledge = knowledge_state.applied_knowledge
        mastery_levels = knowledge_state.mastery_levels

        for ku_uid in applied_knowledge:
            mastery = mastery_levels.get(ku_uid, 0.5)

            # Recommend reinforcement for knowledge with medium mastery (room for improvement)
            if 0.3 <= mastery < 0.8:
                recommendation = AdaptiveRecommendation(
                    recommendation_id=UIDGenerator.generate_random_uid("reinforce_rec"),
                    recommendation_type=RecommendationType.REVIEW,
                    title=f"Strengthen {ku_uid.split('.')[-1].title()} Skills",
                    description=f"Deepen your understanding and application of {ku_uid}",
                    knowledge_uid=ku_uid,
                    related_goals=[],
                    application_suggestions=[
                        f"Practice advanced {ku_uid} techniques",
                        f"Build a project showcasing {ku_uid} mastery",
                        f"Teach someone else about {ku_uid}",
                    ],
                    relevance_score=0.7,
                    impact_score=mastery * 0.8,  # Impact based on current mastery
                    confidence_score=0.9,  # High confidence for reinforcement
                    urgency_score=0.3,  # Lower urgency for reinforcement
                    gap_address_score=0.0,  # Doesn't address gaps
                    goal_alignment_score=0.6,
                    style_match_score=0.7,
                    difficulty_appropriateness=0.8,
                    reasoning=f"Strengthening your existing {ku_uid} knowledge will improve overall competency",
                    prerequisites_met=True,
                    estimated_time_minutes=90,
                )
                recommendations.append(recommendation)

        return recommendations[:3]  # Limit reinforcement recommendations

    async def _generate_exploration_recommendations(
        self, _user_uid: str, knowledge_state: KnowledgeState, _learning_style: LearningStyle
    ) -> list[AdaptiveRecommendation]:
        """Generate recommendations for exploring new knowledge areas."""
        recommendations = []

        # Find domains user is active in
        applied_knowledge = knowledge_state.applied_knowledge
        user_domains = set()
        for ku_uid in applied_knowledge:
            if "." in ku_uid:
                user_domains.add(ku_uid.split(".")[1])

        # Suggest exploration in adjacent domains
        domain_adjacencies = {
            "programming": ["testing", "devops", "architecture"],
            "web": ["mobile", "api", "security"],
            "data": ["ml", "visualization", "engineering"],
            "testing": ["automation", "performance", "security"],
            "devops": ["cloud", "monitoring", "security"],
        }

        for user_domain in user_domains:
            adjacent_domains = domain_adjacencies.get(user_domain, [])
            for adj_domain in adjacent_domains[:2]:  # Limit exploration suggestions
                knowledge_uid = f"ku.{adj_domain}.introduction"

                recommendation = AdaptiveRecommendation(
                    recommendation_id=UIDGenerator.generate_random_uid("explore_rec"),
                    recommendation_type=RecommendationType.ALTERNATIVE,
                    title=f"Explore {adj_domain.title()}",
                    description=f"Discover how {adj_domain} connects to your {user_domain} expertise",
                    knowledge_uid=knowledge_uid,
                    related_goals=[],
                    application_suggestions=[
                        f"Learn how {adj_domain} enhances {user_domain}",
                        f"Explore career opportunities combining {user_domain} and {adj_domain}",
                        "Build a project that integrates both domains",
                    ],
                    relevance_score=0.6,
                    impact_score=0.7,
                    confidence_score=0.6,
                    urgency_score=0.2,  # Low urgency for exploration
                    gap_address_score=0.0,
                    goal_alignment_score=0.4,
                    style_match_score=0.6,
                    difficulty_appropriateness=0.7,
                    reasoning=f"Exploring {adj_domain} will broaden your perspective and create new opportunities",
                    prerequisites_met=True,
                    estimated_time_minutes=120,
                )
                recommendations.append(recommendation)

        return recommendations[:2]  # Limit exploration recommendations

    async def _score_and_rank_recommendations(
        self,
        recommendations: list[AdaptiveRecommendation],
        _user_uid: str,
        _knowledge_state: KnowledgeState,
    ) -> list[AdaptiveRecommendation]:
        """Score and rank recommendations by overall value to user."""
        for rec in recommendations:
            # Calculate composite score
            rec.relevance_score = (
                rec.gap_address_score * 0.3
                + rec.goal_alignment_score * 0.25
                + rec.style_match_score * 0.2
                + rec.difficulty_appropriateness * 0.15
                + rec.urgency_score * 0.1
            )

            # Adjust for recommendation type
            type_multipliers = {
                RecommendationType.PREREQUISITE: 1.0,
                RecommendationType.NEXT_STEP: 0.9,
                RecommendationType.APPLICATION: 0.8,
                RecommendationType.REVIEW: 0.6,
                RecommendationType.ALTERNATIVE: 0.5,
                RecommendationType.STRETCH: 0.4,
            }

            multiplier = type_multipliers.get(rec.recommendation_type, 0.7)
            rec.relevance_score *= multiplier

        # Sort by relevance score (highest first)
        recommendations.sort(key=attrgetter("relevance_score"), reverse=True)

        return recommendations

    # Helper methods for recommendation scoring
    async def _find_goals_needing_knowledge(self, user_uid: str, knowledge_uid: str) -> list[str]:
        """Find user goals that would benefit from this knowledge."""
        goals = []

        if self.goals_service:
            goals_result = await self.goals_service.get_user_goals(user_uid)
            if goals_result.is_ok:
                for goal in goals_result.value:
                    # Simple heuristic: check if knowledge domain relates to goal
                    if "." in knowledge_uid:
                        domain = knowledge_uid.split(".")[1]
                        goal_text = f"{goal.title} {goal.description}".lower()
                        if domain in goal_text:
                            goals.append(goal.uid)

        return goals

    async def _generate_application_suggestions(
        self, knowledge_uid: str, _knowledge_state: KnowledgeState
    ) -> list[str]:
        """Generate specific suggestions for applying this knowledge."""
        suggestions = []

        if "." in knowledge_uid:
            domain = knowledge_uid.split(".")[1]
            topic = knowledge_uid.split(".")[-1]

            # Domain-specific suggestions
            if domain == "programming":
                suggestions = [
                    f"Build a small project using {topic}",
                    f"Solve coding challenges related to {topic}",
                    f"Contribute to open source projects using {topic}",
                ]
            elif domain == "web":
                suggestions = [
                    f"Create a web page demonstrating {topic}",
                    f"Build a responsive website using {topic}",
                    f"Optimize an existing site with {topic}",
                ]
            elif domain == "data":
                suggestions = [
                    f"Analyze a dataset using {topic}",
                    f"Create visualizations with {topic}",
                    f"Build a data pipeline incorporating {topic}",
                ]
            else:
                suggestions = [
                    f"Practice {topic} through hands-on exercises",
                    f"Apply {topic} to a real-world problem",
                    f"Teach {topic} to reinforce your learning",
                ]

        return suggestions[:3]  # Limit suggestions

    async def _calculate_gap_relevance(
        self, knowledge_uid: str, knowledge_state: KnowledgeState
    ) -> float:
        """Calculate how relevant this gap is to the user's current trajectory."""
        # Check if it's related to user's current knowledge
        applied_knowledge = knowledge_state.applied_knowledge

        if not applied_knowledge:
            return 0.5  # Medium relevance if no current knowledge

        # Check domain overlap
        if "." in knowledge_uid:
            gap_domain = knowledge_uid.split(".")[1]
            user_domains = set()
            for ku_uid in applied_knowledge:
                if "." in ku_uid:
                    user_domains.add(ku_uid.split(".")[1])

            if gap_domain in user_domains:
                return 0.9  # High relevance if same domain

            # Check for related domains
            related_domains = {
                "programming": ["testing", "devops"],
                "web": ["programming", "api"],
                "data": ["programming", "ml"],
            }

            for domain in user_domains:
                if gap_domain in related_domains.get(domain, []):
                    return 0.7  # Good relevance if related domain

        return 0.4  # Lower relevance if unrelated

    async def _calculate_gap_impact(self, knowledge_uid: str, _user_uid: str) -> float:
        """Calculate the potential impact of learning this knowledge."""
        # Simplified impact calculation
        impact = 0.5  # Base impact

        # Higher impact for foundational knowledge
        if any(term in knowledge_uid for term in ["basics", "fundamentals", "introduction"]):
            impact += 0.2

        # Higher impact for practical knowledge
        if any(term in knowledge_uid for term in ["programming", "web", "api", "database"]):
            impact += 0.3

        # Lower impact for very specialized knowledge
        if any(term in knowledge_uid for term in ["advanced", "expert", "specialized"]):
            impact -= 0.1

        return min(1.0, impact)

    async def _calculate_gap_urgency(self, _knowledge_uid: str, user_uid: str) -> float:
        """Calculate how urgently this gap should be addressed."""
        # Check if this knowledge is needed for upcoming goals
        urgency = 0.3  # Base urgency

        if self.goals_service:
            goals_result = await self.goals_service.get_user_goals(user_uid)
            if goals_result.is_ok:
                for goal in goals_result.value:
                    # Check if goal has near-term target date
                    if goal.target_date:
                        days_to_target = (goal.target_date - datetime.now().date()).days
                        if days_to_target <= 30:  # Within 30 days
                            urgency += 0.5
                            break

        return min(1.0, urgency)

    async def _calculate_goal_alignment(self, knowledge_uid: str, user_uid: str) -> float:
        """Calculate how well this knowledge aligns with user goals."""
        alignment = 0.5  # Base alignment

        if self.goals_service and "." in knowledge_uid:
            domain = knowledge_uid.split(".")[1]
            goals_result = await self.goals_service.get_user_goals(user_uid)
            if goals_result.is_ok:
                goal_texts = [f"{g.title} {g.description}".lower() for g in goals_result.value]
                goal_text = " ".join(goal_texts)

                # Check if domain is mentioned in goals
                if domain in goal_text:
                    alignment += 0.4

        return min(1.0, alignment)

    async def _calculate_style_match_for_knowledge(
        self, knowledge_uid: str, learning_style: LearningStyle
    ) -> float:
        """Calculate how well this knowledge matches the user's learning style."""
        base_match = 0.5

        # Practical learners prefer hands-on knowledge
        if learning_style == LearningStyle.PRACTICAL:
            if any(term in knowledge_uid for term in ["programming", "web", "api", "database"]):
                base_match += 0.3
            elif any(term in knowledge_uid for term in ["theory", "mathematics"]):
                base_match -= 0.2

        # Theoretical learners prefer conceptual knowledge
        elif learning_style == LearningStyle.THEORETICAL:
            if any(term in knowledge_uid for term in ["theory", "principles", "fundamentals"]):
                base_match += 0.3
            elif any(term in knowledge_uid for term in ["implementation", "practical"]):
                base_match -= 0.1

        return min(1.0, max(0.1, base_match))

    async def _assess_difficulty_appropriateness(
        self, knowledge_uid: str, knowledge_state: KnowledgeState
    ) -> float:
        """Assess if the difficulty level is appropriate for the user."""
        # Estimate knowledge difficulty
        difficulty = 0.5  # Medium difficulty default

        if any(term in knowledge_uid for term in ["basics", "introduction", "fundamentals"]):
            difficulty = 0.3  # Easy
        elif any(term in knowledge_uid for term in ["advanced", "expert"]):
            difficulty = 0.8  # Hard
        elif any(term in knowledge_uid for term in ["intermediate"]):
            difficulty = 0.6  # Medium-hard

        # Estimate user skill level in domain
        if "." in knowledge_uid:
            domain = knowledge_uid.split(".")[1]
            applied_knowledge = knowledge_state.applied_knowledge
            domain_knowledge = [ku for ku in applied_knowledge if f".{domain}." in ku]

            # More domain knowledge = can handle higher difficulty
            user_level = len(domain_knowledge) * 0.1  # Rough estimate
            user_level = min(1.0, user_level)

            # Appropriate if difficulty is close to user level
            difficulty_gap = abs(difficulty - user_level)
            appropriateness = 1.0 - difficulty_gap

            return max(0.1, appropriateness)

        return 0.7  # Default appropriateness

    async def _check_prerequisites_met(
        self, knowledge_uid: str, knowledge_state: KnowledgeState
    ) -> bool:
        """Check if prerequisites for this knowledge are met."""
        applied_knowledge = knowledge_state.applied_knowledge

        # Simple prerequisite rules
        if "." in knowledge_uid:
            domain = knowledge_uid.split(".")[1]
            topic = knowledge_uid.split(".")[-1]

            # Advanced topics require basics
            if topic in ["advanced", "expert"]:
                basic_knowledge = f"ku.{domain}.basics"
                return basic_knowledge in applied_knowledge

            # Domain-specific prerequisites
            if domain == "ml":
                return any("programming" in ku for ku in applied_knowledge)
            elif domain == "web" and topic != "html":
                return "ku.web.html" in applied_knowledge

        return True  # Default: prerequisites met

    async def _estimate_learning_time(self, knowledge_uid: str) -> int:
        """Estimate time needed to learn this knowledge in minutes."""
        # Base time by complexity
        if any(term in knowledge_uid for term in ["basics", "introduction"]):
            return 90  # 1.5 hours
        elif any(term in knowledge_uid for term in ["intermediate"]):
            return 180  # 3 hours
        elif any(term in knowledge_uid for term in ["advanced", "expert"]):
            return 300  # 5 hours
        else:
            return 120  # 2 hours default
