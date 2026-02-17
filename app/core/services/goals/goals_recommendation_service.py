"""
Goal Recommendation Service
============================

Handles intelligent goal recommendations based on achievements and patterns.

Responsibilities:
- Recommend next goals when current goals are achieved
- Suggest progressive goals based on domain/type
- Identify goal sequences and learning paths
- Publish recommendation events for UI display
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.goal_events import GoalAchieved, GoalRecommendationsGenerated
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations


class GoalsRecommendationService:
    """
    Intelligent goal recommendation service for event-driven suggestions.

    Handles automatic goal recommendations when goals are achieved,
    using graph analysis to suggest progressive, related goals.

    Event-Driven Architecture (Phase 4):
    - Subscribes to GoalAchieved events
    - Analyzes achieved goal context (domain, knowledge, habits)
    - Generates smart recommendations
    - Publishes GoalRecommendationsGenerated events


    Source Tag: "goal_recommendation_explicit"
    - Format: "goal_recommendation_explicit" for user-created relationships
    - Format: "goal_recommendation_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        backend: "BackendOperations[Any] | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize goal recommendation service.

        Args:
            backend: Backend for executing graph queries
            event_bus: Optional event bus for publishing recommendation events
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.goals.recommendations")

    # ========================================================================
    # EVENT HANDLERS (Phase 4: Event-Driven Architecture)
    # ========================================================================

    async def handle_goal_achieved(self, event: GoalAchieved) -> None:
        """
        Generate goal recommendations when a goal is achieved.

        This handler implements event-driven goal recommendations,
        creating intelligent suggestions for next goals based on:
        1. Same domain, progressive difficulty
        2. Related knowledge that was applied
        3. Habits that were built
        4. Similar successful goal patterns

        When a goal is achieved:
        1. Analyze achieved goal context (domain, type, relationships)
        2. Query graph for related entities (knowledge, habits, principles)
        3. Generate 3-5 recommended next goals
        4. Publish GoalRecommendationsGenerated event

        Args:
            event: GoalAchieved event containing goal_uid and user_uid

        Note:
            Errors are logged but not raised - recommendations are best-effort
            to prevent goal achievement from failing if recommendation fails.
        """
        try:
            if not self.backend:
                self.logger.warning("No backend available for Goal→Recommendations integration")
                return

            self.logger.info(f"Generating recommendations for achieved goal {event.goal_uid}")

            # Get achieved goal context from Neo4j
            goal_context = await self._get_goal_context(event.goal_uid, event.user_uid)
            if not goal_context:
                self.logger.warning(f"Goal {event.goal_uid} not found, skipping recommendations")
                return

            # Generate recommendations based on goal context
            recommendations = await self._generate_recommendations(goal_context, event.user_uid)

            if not recommendations:
                self.logger.info(f"No recommendations generated for goal {event.goal_uid}")
                return

            self.logger.info(
                f"Generated {len(recommendations)} recommendations for goal {event.goal_uid}"
            )

            # Publish GoalRecommendationsGenerated event
            recommendation_event = GoalRecommendationsGenerated(
                goal_uid=event.goal_uid,
                user_uid=event.user_uid,
                occurred_at=datetime.now(),
                recommendations=recommendations,
                triggered_by_achievement=True,
            )
            await publish_event(self.event_bus, recommendation_event, self.logger)

        except Exception as e:
            # Best-effort: Log error but don't raise (prevent goal achievement failure)
            self.logger.error(f"Error handling goal_achieved event: {e}")

    async def _get_goal_context(self, goal_uid: str, user_uid: str) -> dict | None:
        """
        Get achieved goal context from Neo4j for recommendation generation.

        Retrieves:
        - Goal properties (domain, type, timeframe)
        - Related knowledge units (REQUIRES_KNOWLEDGE)
        - Related habits (SUPPORTS_GOAL)
        - Related principles (GUIDED_BY_PRINCIPLE)

        Args:
            goal_uid: Achieved goal UID
            user_uid: User who achieved the goal

        Returns:
            Goal context dict with properties and relationships, or None if not found
        """
        if not self.backend:
            self.logger.warning("No backend available for goal context retrieval")
            return None

        query = """
        MATCH (goal:Ku {uid: $goal_uid, user_uid: $user_uid, ku_type: 'goal'})

        // Get related knowledge
        OPTIONAL MATCH (goal)-[:REQUIRES_KNOWLEDGE]->(ku:Ku)
        WHERE ku.ku_type = 'knowledge_unit'
        WITH goal, collect(DISTINCT {uid: ku.uid, title: ku.title, domain: ku.domain}) as knowledge_units

        // Get related habits
        OPTIONAL MATCH (goal)-[:SUPPORTS_GOAL]->(habit:Ku {ku_type: 'habit'})
        WITH goal, knowledge_units, collect(DISTINCT {uid: habit.uid, title: habit.title}) as habits

        // Get guiding principles
        OPTIONAL MATCH (goal)-[:GUIDED_BY_PRINCIPLE]->(principle:Ku {ku_type: 'principle'})
        WITH goal, knowledge_units, habits, collect(DISTINCT {uid: principle.uid, title: principle.title}) as principles

        RETURN goal.uid as uid,
               goal.title as title,
               goal.domain as domain,
               goal.goal_type as goal_type,
               goal.timeframe as timeframe,
               knowledge_units,
               habits,
               principles
        """

        result = await self.backend.execute_query(
            query, {"goal_uid": goal_uid, "user_uid": user_uid}
        )
        if result.is_error:
            self.logger.error(f"Failed to get goal context for {goal_uid}: {result.error}")
            return None

        if not result.value:
            return None

        return result.value[0]

    async def _generate_recommendations(self, goal_context: dict, user_uid: str) -> list[dict]:
        """
        Generate goal recommendations based on achieved goal context.

        Recommendation strategies:
        1. **Domain progression**: Similar goals in same domain
        2. **Knowledge expansion**: Goals requiring related knowledge
        3. **Habit reinforcement**: Goals supported by established habits
        4. **Principle alignment**: Goals guided by same principles

        Args:
            goal_context: Context from achieved goal (domain, knowledge, habits, principles)
            user_uid: User receiving recommendations

        Returns:
            List of recommendation dicts with title, description, rationale, confidence
        """
        recommendations = []
        domain = goal_context.get("domain", "KNOWLEDGE")
        goal_type = goal_context.get("goal_type", "OUTCOME")
        knowledge_units = goal_context.get("knowledge_units", [])
        habits = goal_context.get("habits", [])
        principles = goal_context.get("principles", [])

        # Strategy 1: Domain progression (same domain, different focus)
        domain_recommendation = self._recommend_domain_progression(domain, goal_type, user_uid)
        if domain_recommendation:
            recommendations.append(domain_recommendation)

        # Strategy 2: Knowledge expansion (apply knowledge in new context)
        if knowledge_units:
            knowledge_recommendation = self._recommend_knowledge_expansion(
                knowledge_units, domain, user_uid
            )
            if knowledge_recommendation:
                recommendations.append(knowledge_recommendation)

        # Strategy 3: Habit reinforcement (leverage established habits)
        if habits:
            habit_recommendation = self._recommend_habit_reinforcement(habits, domain, user_uid)
            if habit_recommendation:
                recommendations.append(habit_recommendation)

        # Strategy 4: Principle alignment (goals aligned with principles)
        if principles:
            principle_recommendation = self._recommend_principle_alignment(
                principles, domain, user_uid
            )
            if principle_recommendation:
                recommendations.append(principle_recommendation)

        # Limit to top 5 recommendations
        return recommendations[:5]

    # FUTURE-IMPL: FUTURE-IMPL-001 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
    def _recommend_domain_progression(
        self, domain: str, goal_type: str, user_uid: str
    ) -> dict | None:
        """
        Recommend a progressive goal in the same domain.

        For example:
        - After "Learn Python Basics" → "Build Python Project"
        - After "Run 5K" → "Run 10K"
        - After "Read 10 Books" → "Read 20 Books"

        Args:
            domain: Domain of achieved goal
            goal_type: Type of achieved goal
            user_uid: User receiving recommendation

        Returns:
            Recommendation dict or None
        """
        # Map domains to progressive goal suggestions
        domain_progressions = {
            "TECH": {
                "LEARNING": "Apply your knowledge by building a real project",
                "OUTCOME": "Share your expertise by teaching or mentoring others",
                "PROJECT": "Expand the project with advanced features",
            },
            "HEALTH": {
                "OUTCOME": "Set a more challenging fitness milestone",
                "PROCESS": "Establish a sustainable long-term health routine",
                "MILESTONE": "Participate in a competition or group challenge",
            },
            "PERSONAL": {
                "LEARNING": "Apply this learning to improve a life area",
                "OUTCOME": "Set a transformational personal development goal",
                "PROCESS": "Build a daily practice around this skill",
            },
            "BUSINESS": {
                "PROJECT": "Scale this project to reach more people",
                "OUTCOME": "Mentor others in this business area",
                "LEARNING": "Apply this knowledge to start a new venture",
            },
        }

        suggestion = domain_progressions.get(domain, {}).get(
            goal_type, "Set a more ambitious goal in this area"
        )

        return {
            "title": f"Next Level: {domain.title()} Goal",
            "description": suggestion,
            "rationale": f"You've mastered a {domain.lower()} goal - time to level up!",
            "confidence": 0.85,
            "recommendation_type": "domain_progression",
            "suggested_domain": domain,
            "suggested_goal_type": goal_type,
        }

    # FUTURE-IMPL: FUTURE-IMPL-002 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md

    def _recommend_knowledge_expansion(
        self, knowledge_units: list[dict], domain: str, user_uid: str
    ) -> dict | None:
        """
        Recommend a goal that applies mastered knowledge in a new context.

        Args:
            knowledge_units: Knowledge units from achieved goal
            domain: Domain of achieved goal
            user_uid: User receiving recommendation

        Returns:
            Recommendation dict or None
        """
        # Filter out any None values from empty relationships
        knowledge_units = [ku for ku in knowledge_units if ku.get("uid") is not None]

        if not knowledge_units:
            return None

        ku_titles = ", ".join([ku["title"] for ku in knowledge_units[:3]])

        return {
            "title": "Apply Your Knowledge",
            "description": f"Create a project or goal that applies: {ku_titles}",
            "rationale": "You've learned these concepts - now make something with them!",
            "confidence": 0.80,
            "recommendation_type": "knowledge_expansion",
            "related_knowledge": [ku["uid"] for ku in knowledge_units],
            # FUTURE-IMPL: FUTURE-IMPL-004 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
        }

    def _recommend_habit_reinforcement(
        self, habits: list[dict], domain: str, user_uid: str
    ) -> dict | None:
        """
        Recommend a goal that leverages established habits.

        Args:
            habits: Habits from achieved goal
            domain: Domain of achieved goal
            user_uid: User receiving recommendation

        Returns:
            Recommendation dict or None
        """
        # Filter out any None values from empty relationships
        habits = [h for h in habits if h.get("uid") is not None]

        if not habits:
            return None

        habit_titles = ", ".join([h["title"] for h in habits[:2]])

        return {
            "title": "Leverage Your Habits",
            "description": f"Your established habits ({habit_titles}) can support a bigger goal",
            "rationale": "You've built strong habits - use them to achieve something greater!",
            "confidence": 0.75,
            "recommendation_type": "habit_reinforcement",
            # FUTURE-IMPL: FUTURE-IMPL-006 - See docs/reference/DEFERRED_IMPLEMENTATIONS.md
            "related_habits": [h["uid"] for h in habits],
        }

    def _recommend_principle_alignment(
        self, principles: list[dict], domain: str, user_uid: str
    ) -> dict | None:
        """
        Recommend a goal aligned with guiding principles.

        Args:
            principles: Principles from achieved goal
            domain: Domain of achieved goal
            user_uid: User receiving recommendation

        Returns:
            Recommendation dict or None
        """
        # Filter out any None values from empty relationships
        principles = [p for p in principles if p.get("uid") is not None]

        if not principles:
            return None

        principle_titles = ", ".join([p["title"] for p in principles[:2]])

        return {
            "title": "Stay Aligned with Your Principles",
            "description": f"Set a goal that furthers: {principle_titles}",
            "rationale": "Your principles guided this success - let them guide your next goal!",
            "confidence": 0.90,
            "recommendation_type": "principle_alignment",
            "related_principles": [p["uid"] for p in principles],
        }
