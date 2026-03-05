"""
Search Intelligence Service
============================

Intelligence service for advanced search capabilities using QueryIntelligenceService.

Features (delegated to QueryIntelligenceService):
- Facet suggestion based on query analysis
- Query intent detection
- Result ranking and personalization
- Search analytics and insights

Additional search-specific features:
- SEL category detection (social-emotional learning)
- Search-specific domain keywords

Architecture:
- Composition over inheritance - uses QueryIntelligenceService
- Pure intelligence/domain logic - no CRUD operations
- Stateless - all context passed in method calls
"""

from typing import Any

from core.services.intelligence.query_intelligence_service import QueryIntelligenceService
from core.utils.logging import get_logger
from core.utils.sort_functions import get_result_score


class SearchIntelligenceService:
    """
    Intelligence service for advanced search features.

    Uses QueryIntelligenceService for core intelligence capabilities,
    adding search-specific enhancements like SEL category detection.
    """

    def __init__(self) -> None:
        """Initialize search intelligence service with base intelligence."""
        self.logger = get_logger(__name__)

        # Initialize base intelligence service with search-optimized configuration
        self.base_intelligence = QueryIntelligenceService(
            domain="search",
            domain_keywords=[
                "knowledge",
                "learn",
                "study",
                "concept",
                "understand",
                "theory",
                "task",
                "todo",
                "action",
                "complete",
                "deadline",
                "project",
                "habit",
                "routine",
                "daily",
                "weekly",
                "practice",
                "consistency",
                "event",
                "meeting",
                "appointment",
                "schedule",
                "calendar",
                "goal",
                "objective",
                "target",
                "achieve",
                "milestone",
                "finance",
                "expense",
                "budget",
                "money",
                "spending",
                "financial",
            ],
        )

    # ========================================================================
    # FACET SUGGESTION INTELLIGENCE (Delegated to QueryIntelligenceService)
    # ========================================================================

    def suggest_facets(
        self,
        query_text: str,
        current_facets: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Suggest facets based on query text analysis and user context.

        P3: Now incorporates UserContext for personalized facet suggestions.

        Delegates to QueryIntelligenceService and adds:
        - SEL category detection (social-emotional learning)
        - User-aware facet boosting based on active domains and learning level

        Args:
            query_text: Search query string
            current_facets: Already applied facets (optional)
            user_context: UserContext dict for personalization (optional)

        Returns:
            Dictionary of suggested facet values with user-aware prioritization
        """
        # Get base suggestions from QueryIntelligenceService
        suggestions = self.base_intelligence.suggest_facets(query_text, current_facets)

        # Add search-specific SEL category detection
        query_lower = query_text.lower()
        sel_category = self._detect_sel_category(query_lower)
        if sel_category:
            suggestions["sel_category"] = sel_category

        # P3: Add user-aware facet suggestions
        if user_context:
            suggestions = self._enhance_facets_with_user_context(suggestions, user_context)

        return suggestions

    def _enhance_facets_with_user_context(
        self, suggestions: dict[str, Any], user_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Enhance facet suggestions based on user context.

        P3: Personalizes facet suggestions using UserContext data.

        Enhancements:
        1. Suggest user's active domains as primary filters
        2. Suggest user's learning level if not already applied
        3. Prioritize facets that align with active goals
        4. Flag facets that match at-risk areas (habits at risk, etc.)
        """
        enhanced = dict(suggestions)

        # 1. Suggest domains user is actively learning in
        learning_domains = user_context.get("learning_domains", [])
        if learning_domains and "domain" not in enhanced:
            # Suggest most active domain
            velocity = user_context.get("learning_velocity_by_domain", {})
            if velocity:
                sorted_domains = sorted(velocity.items(), key=get_result_score, reverse=True)
                enhanced["suggested_domain"] = sorted_domains[0][0] if sorted_domains else None
            elif learning_domains:
                enhanced["suggested_domain"] = learning_domains[0]

        # 2. Suggest user's learning level
        user_level = user_context.get("learning_level")
        if user_level and "learning_level" not in enhanced:
            enhanced["suggested_learning_level"] = user_level

        # 3. Add goal-aware suggestions
        active_goals = user_context.get("active_goal_uids", [])
        if active_goals:
            enhanced["has_active_goals"] = True
            enhanced["active_goal_count"] = len(active_goals)
            # Suggest enabling goal-support filter
            enhanced["suggest_supports_goals"] = True

        # 4. Add at-risk awareness
        at_risk_habits = user_context.get("at_risk_habits", [])
        if at_risk_habits:
            enhanced["has_at_risk_habits"] = True
            enhanced["at_risk_habit_count"] = len(at_risk_habits)

        # 5. Add workload awareness
        workload_score = user_context.get("current_workload_score", 0.5)
        if workload_score > 0.8:
            enhanced["workload_warning"] = "high"
            enhanced["suggest_quick_content"] = True
        elif workload_score < 0.3:
            enhanced["workload_warning"] = "low"
            enhanced["suggest_deep_content"] = True

        # 6. Add energy-level awareness
        energy_level = user_context.get("current_energy_level")
        if energy_level:
            enhanced["current_energy"] = energy_level
            if energy_level in ["low", "very_low"]:
                enhanced["suggest_easy_content"] = True

        # 7. Add mastery-based suggestions
        mastered_count = len(user_context.get("mastered_knowledge_uids", []))
        if mastered_count > 0:
            enhanced["mastered_knowledge_count"] = mastered_count
            enhanced["suggest_next_logical_step"] = True

        return enhanced

    def _detect_sel_category(self, query_lower: str) -> str | None:
        """Detect SEL category from query keywords."""
        sel_keywords = {
            "self_awareness": ["self-aware", "mindful", "reflection", "emotions", "feelings"],
            "self_management": ["manage", "control", "discipline", "focus", "productivity"],
            "social_awareness": ["empathy", "understand others", "perspective", "social"],
            "relationship_skills": ["communication", "collaborate", "relationships", "connect"],
            "responsible_decision_making": ["decide", "choice", "judgment", "reasoning"],
        }

        for category, keywords in sel_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                return category

        return None

    # ========================================================================
    # QUERY UNDERSTANDING (Delegated to QueryIntelligenceService)
    # ========================================================================

    def analyze_query_intent(self, query_text: str) -> dict[str, Any]:
        """
        Analyze query to understand user intent.

        Delegates to QueryIntelligenceService which provides:
        - primary_intent: Main intent (learn, practice, discover, review)
        - confidence: Confidence score (0.0-1.0)
        - suggested_filters: Recommended filters
        - query_type: Type of query (concept, action, exploration)
        """
        # Delegate to base intelligence service
        # QueryIntelligenceService already adds suggested_filters via suggest_facets
        return self.base_intelligence.analyze_query_intent(query_text)

    # ========================================================================
    # RESULT RANKING INTELLIGENCE (Delegated to QueryIntelligenceService)
    # ========================================================================

    def rank_results(
        self,
        results: list[dict[str, Any]],
        query_intent: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rank search results based on relevance to query intent.

        Delegates to QueryIntelligenceService for ranking logic.

        Args:
            results: Search results to rank,
            query_intent: Query intent analysis from analyze_query_intent(),
            user_context: Optional user context for personalization

        Returns:
            Ranked list of results
        """
        return self.base_intelligence.rank_results(results, query_intent, user_context)

    # ========================================================================
    # SEARCH INSIGHTS (Delegated to QueryIntelligenceService)
    # ========================================================================

    def generate_search_insights(
        self, query_text: str, results: list[dict[str, Any]], facets: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate insights about search results.

        Delegates to QueryIntelligenceService for insight generation.

        Args:
            query_text: Original search query,
            results: Search results,
            facets: Applied facets

        Returns:
            Dictionary with insights and recommendations
        """
        return self.base_intelligence.generate_search_insights(query_text, results, facets)


# Singleton instance for easy access
_search_intelligence = None


def get_search_intelligence() -> SearchIntelligenceService:
    """Get or create singleton SearchIntelligenceService instance."""
    global _search_intelligence
    if _search_intelligence is None:
        _search_intelligence = SearchIntelligenceService()
    return _search_intelligence
