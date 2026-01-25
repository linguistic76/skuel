"""
Query Intelligence Service
===========================

Query intelligence capabilities for search and discovery.

Renamed from BaseIntelligenceService (January 2026) to avoid collision with
the domain intelligence BaseIntelligenceService in core/services/base_intelligence_service.py.

Provides:
1. Query Intent Detection - Understand user intent (learn, practice, discover, review)
2. Facet Suggestion - Suggest filters based on query analysis
3. Result Ranking - Score and rank results by relevance
4. Insight Generation - Analyze coverage, trends, recommendations

Usage:
    query_intel = QueryIntelligenceService(
        domain="tasks",
        domain_keywords=["task", "todo", "action", "deadline"],
        intent_signals={
            "learn": ["understand", "what is", "explain"],
            "practice": ["exercise", "try", "apply"],
        }
    )

    intent = query_intel.analyze_query_intent("how to complete tasks faster")
    facets = query_intel.suggest_facets("advanced task management")
    ranked = query_intel.rank_results(results, intent, user_context)
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.utils.logging import get_logger
from core.utils.sort_functions import get_intent_score, get_result_score

# ============================================================================
# Configuration Dataclasses
# ============================================================================


@dataclass
class IntentSignals:
    """Intent detection signal keywords."""

    learn: list[str]
    practice: list[str]
    discover: list[str]
    review: list[str]


@dataclass
class DomainKeywords:
    """Domain detection keywords."""

    keywords: list[str]
    domain_name: str


# ============================================================================
# Intent Scoring
# ============================================================================


class IntentScorer:
    """
    Scores query text against intent signals.

    Configurable scoring engine for detecting user intent from natural language queries.
    """

    def __init__(self, intent_signals: IntentSignals | None = None) -> None:
        """
        Initialize intent scorer with signal keywords.

        Args:
            intent_signals: Intent detection keywords (defaults to generic signals)
        """
        self.logger = get_logger(__name__)

        # Default intent signals (generic)
        self.intent_signals = intent_signals or IntentSignals(
            learn=[
                "learn",
                "understand",
                "what is",
                "how does",
                "explain",
                "concept",
                "theory",
                "knowledge",
                "study",
            ],
            practice=[
                "practice",
                "exercise",
                "example",
                "apply",
                "do",
                "hands-on",
                "try",
                "implement",
                "build",
            ],
            discover=[
                "find",
                "search",
                "discover",
                "explore",
                "browse",
                "looking for",
                "show me",
                "list",
                "what are",
            ],
            review=[
                "review",
                "revise",
                "recap",
                "refresh",
                "summary",
                "overview",
                "remind",
                "recall",
            ],
        )

    def analyze_query_intent(self, query_text: str) -> dict[str, Any]:
        """
        Analyze query to understand user intent.

        Args:
            query_text: Search query string

        Returns:
            Dictionary with:
            - primary_intent: Main intent (learn, practice, discover, review)
            - confidence: Confidence score (0.0-1.0)
            - all_intents: All detected intents with scores > 0.3
            - query_type: Type of query (concept, action, contextual, exploration)
        """
        query_lower = query_text.lower()

        # Score each intent
        intent_scores = {
            "learn": self._score_intent(query_lower, self.intent_signals.learn),
            "practice": self._score_intent(query_lower, self.intent_signals.practice),
            "discover": self._score_intent(query_lower, self.intent_signals.discover),
            "review": self._score_intent(query_lower, self.intent_signals.review),
        }

        # Find primary intent
        primary_intent = max(intent_scores.items(), key=get_intent_score)

        # Classify query type
        query_type = self._classify_query_type(query_lower)

        return {
            "primary_intent": primary_intent[0],
            "confidence": primary_intent[1],
            "all_intents": {k: v for k, v in intent_scores.items() if v > 0.3},
            "query_type": query_type,
        }

    def _score_intent(self, query: str, signals: list[str]) -> float:
        """
        Calculate confidence score for an intent.

        Args:
            query: Lowercased query string
            signals: List of signal keywords for this intent

        Returns:
            Confidence score 0.0-1.0
        """
        matches = sum(1 for signal in signals if signal in query)
        if not matches:
            return 0.0

        # Base score from match ratio
        base_score = matches / len(signals)

        # Boost for multiple matches
        boost = min(matches * 0.2, 0.5)

        return min(base_score + boost, 1.0)

    def _classify_query_type(self, query: str) -> str:
        """
        Classify the syntactic type of query.

        Args:
            query: Lowercased query string

        Returns:
            Query type: concept, action, contextual, exploration, general
        """
        if any(q in query for q in ["what is", "what are", "define", "explain"]):
            return "concept"
        elif any(q in query for q in ["how to", "how do", "steps", "process"]):
            return "action"
        elif any(q in query for q in ["why", "when", "where", "who"]):
            return "contextual"
        elif any(q in query for q in ["list", "show", "find", "all"]):
            return "exploration"
        else:
            return "general"


# ============================================================================
# Facet Detection
# ============================================================================


class FacetDetector:
    """
    Suggests search facets based on query text analysis.

    Detects domain, learning level, and other facets from natural language.
    """

    def __init__(
        self,
        domain_keywords: list[DomainKeywords] | None = None,
        intent_scorer: IntentScorer | None = None,
    ) -> None:
        """
        Initialize facet detector.

        Args:
            domain_keywords: List of domain keyword mappings,
            intent_scorer: Intent scorer for intent-based facets
        """
        self.logger = get_logger(__name__)
        self.intent_scorer = intent_scorer or IntentScorer()

        # Default domain keywords
        self.domain_keywords = domain_keywords or [
            DomainKeywords(["learn", "study", "concept", "knowledge"], "knowledge"),
            DomainKeywords(["task", "todo", "action", "deadline"], "tasks"),
            DomainKeywords(["habit", "routine", "daily", "practice"], "habits"),
            DomainKeywords(["event", "meeting", "schedule", "calendar"], "events"),
            DomainKeywords(["goal", "objective", "target", "achieve"], "goals"),
            DomainKeywords(["expense", "budget", "money", "financial"], "finance"),
        ]

        # Learning level keywords
        self.level_keywords = {
            "beginner": ["beginner", "intro", "basic", "fundamentals", "getting started", "101"],
            "intermediate": ["intermediate", "moderate", "practical", "applied"],
            "advanced": ["advanced", "expert", "complex", "deep", "mastery"],
        }

    def suggest_facets(
        self, query_text: str, _current_facets: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Suggest facets based on query text analysis.

        Args:
            query_text: Search query string,
            current_facets: Already applied facets (optional)

        Returns:
            Dictionary of suggested facet values
        """
        query_lower = query_text.lower()
        suggestions = {}

        # Detect domain
        domain = self._detect_domain(query_lower)
        if domain:
            suggestions["domain"] = domain

        # Detect learning level
        level = self._detect_learning_level(query_lower)
        if level:
            suggestions["learning_level"] = level

        # Detect intents
        intent_analysis = self.intent_scorer.analyze_query_intent(query_text)
        if intent_analysis["confidence"] > 0.5:
            suggestions["intent"] = intent_analysis["primary_intent"]

        return suggestions

    def _detect_domain(self, query_lower: str) -> str | None:
        """Detect domain from query keywords."""
        for domain_mapping in self.domain_keywords:
            if any(keyword in query_lower for keyword in domain_mapping.keywords):
                return domain_mapping.domain_name
        return None

    def _detect_learning_level(self, query_lower: str) -> str | None:
        """Detect learning level from query keywords."""
        for level, keywords in self.level_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                return level
        return None


# ============================================================================
# Result Ranking
# ============================================================================


class ResultRanker:
    """
    Ranks search results based on relevance to query intent.

    Combines multiple scoring factors:
    - Base search score
    - Intent matching
    - Recency
    - User context personalization
    """

    def __init__(
        self,
        scoring_weights: dict[str, float] | None = None,
        custom_scorers: dict[str, Callable] | None = None,
    ) -> None:
        """
        Initialize result ranker.

        Args:
            scoring_weights: Weights for scoring factors (default: balanced),
            custom_scorers: Custom scoring functions per domain
        """
        self.logger = get_logger(__name__)

        # Default scoring weights
        self.weights = scoring_weights or {
            "base_score": 0.4,
            "intent_match": 0.3,
            "recency": 0.2,
            "personalization": 0.1,
        }

        self.custom_scorers = custom_scorers or {}

    def rank_results(
        self,
        results: list[dict[str, Any]],
        query_intent: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rank search results by relevance.

        Args:
            results: Search results to rank,
            query_intent: Query intent from IntentScorer.analyze_query_intent(),
            user_context: Optional user context for personalization

        Returns:
            Ranked list of results (highest score first)
        """
        if not results:
            return results

        # Score each result
        scored_results = []
        for result in results:
            score = self._calculate_result_score(result, query_intent, user_context)
            scored_results.append((result, score))

        # Sort by score descending
        scored_results.sort(key=get_result_score, reverse=True)

        return [result for result, score in scored_results]

    def _calculate_result_score(
        self,
        result: dict[str, Any],
        query_intent: dict[str, Any],
        user_context: dict[str, Any] | None,
    ) -> float:
        """Calculate relevance score for a single result."""
        score = 0.0

        # 1. Base score from search backend
        base_score = result.get("score", 0.5)
        score += base_score * self.weights["base_score"]

        # 2. Intent matching
        intent_score = self._score_intent_match(result, query_intent)
        score += intent_score * self.weights["intent_match"]

        # 3. Recency boost
        recency_score = self._score_recency(result)
        score += recency_score * self.weights["recency"]

        # 4. User context personalization
        if user_context:
            personalization_score = self._score_personalization(result, user_context)
            score += personalization_score * self.weights["personalization"]

        return min(score, 1.0)

    def _score_intent_match(self, result: dict[str, Any], query_intent: dict[str, Any]) -> float:
        """Score how well result matches query intent."""
        primary_intent = query_intent.get("primary_intent")
        content_type = result.get("content_type", "general")

        # Intent-content type alignment
        alignments = {
            ("learn", "concept"): 1.0,
            ("learn", "theory"): 0.9,
            ("practice", "exercise"): 1.0,
            ("practice", "example"): 0.8,
            ("discover", "overview"): 0.9,
            ("review", "summary"): 1.0,
        }

        return alignments.get((primary_intent, content_type), 0.5)

    def _score_recency(self, result: dict[str, Any]) -> float:
        """Score based on content recency."""
        created_at = result.get("created_at")
        if not created_at:
            return 0.5  # Neutral score if no date

        if not isinstance(created_at, datetime):
            return 0.5

        days_old = (datetime.now() - created_at).days
        # Decay over 365 days
        return max(0, 1 - (days_old / 365))

    def _score_personalization(self, result: dict[str, Any], user_context: dict[str, Any]) -> float:
        """
        Score based on user preferences, history, and context.

        P1 Enhanced: Now uses rich UserContext fields for personalization:
        - Domain affinity (learning_domains, learning_velocity_by_domain)
        - Skill level matching (learning_level)
        - Knowledge mastery (mastered_knowledge_uids, knowledge_mastery)
        - Goal alignment (active_goal_uids, goal_knowledge_required)
        - Prerequisite readiness (mastered prerequisites)
        """
        score = 0.0
        result_uid = result.get("uid", "")
        result_domain = result.get("domain", result.get("_domain", ""))

        # 1. Domain affinity (boost if user is actively learning in this domain)
        user_domains = user_context.get("learning_domains", [])
        learning_velocity = user_context.get("learning_velocity_by_domain", {})
        if result_domain in user_domains:
            score += 0.3
            # Extra boost if high velocity in this domain
            velocity = learning_velocity.get(result_domain, 0.5)
            if velocity > 0.7:
                score += 0.1  # Active learner bonus

        # 2. Skill level matching
        user_level = user_context.get("learning_level")
        if result.get("learning_level") == user_level:
            score += 0.2

        # 3. Prerequisite readiness (for knowledge domain)
        mastered_uids = set(user_context.get("mastered_knowledge_uids", []))
        prerequisites = result.get(
            "prerequisites", result.get("_graph_context", {}).get("prerequisites", [])
        )
        if prerequisites:
            prereq_uids = [p.get("uid") for p in prerequisites if isinstance(p, dict)]
            if prereq_uids:
                # Check how many prerequisites are mastered
                mastered_count = sum(1 for uid in prereq_uids if uid in mastered_uids)
                prereq_ratio = mastered_count / len(prereq_uids) if prereq_uids else 1.0
                if prereq_ratio >= 1.0:
                    score += 0.2  # All prerequisites met - ready to learn!
                elif prereq_ratio >= 0.5:
                    score += 0.1  # Partial readiness

        # 4. Goal alignment (boost if knowledge supports active goals)
        active_goals = user_context.get("active_goal_uids", [])
        goal_knowledge = user_context.get("goal_knowledge_required", {})
        if active_goals and result_uid:
            for goal_uid in active_goals:
                required_knowledge = goal_knowledge.get(goal_uid, [])
                if result_uid in required_knowledge:
                    score += 0.2  # Directly supports a goal
                    break

        # 5. Already mastered penalty (lower ranking for already-known content)
        if result_uid in mastered_uids:
            score -= 0.3  # Already mastered - deprioritize

        return max(0.0, min(score, 1.0))


# ============================================================================
# Query Intelligence Service
# ============================================================================


class QueryIntelligenceService:
    """
    Query intelligence service for search intent detection and result ranking.

    Combines intent scoring, facet detection, and result ranking.

    Renamed from BaseIntelligenceService (January 2026) to avoid collision with
    the domain intelligence BaseIntelligenceService in core/services/base_intelligence_service.py.
    """

    def __init__(
        self,
        domain: str,
        domain_keywords: list[str] | None = None,
        intent_signals: IntentSignals | None = None,
        scoring_weights: dict[str, float] | None = None,
    ) -> None:
        """
        Initialize base intelligence service.

        Args:
            domain: Domain name (e.g., "tasks", "knowledge"),
            domain_keywords: Keywords for domain detection,
            intent_signals: Custom intent signal keywords,
            scoring_weights: Custom scoring weights
        """
        self.domain = domain
        self.logger = get_logger(f"skuel.intelligence.{domain}")

        # Initialize components
        self.intent_scorer = IntentScorer(intent_signals)

        # Create domain keyword mapping
        domain_mappings = [DomainKeywords(domain_keywords or [], domain)]

        self.facet_detector = FacetDetector(
            domain_keywords=domain_mappings, intent_scorer=self.intent_scorer
        )

        self.result_ranker = ResultRanker(scoring_weights=scoring_weights)

    # Convenience methods that delegate to components

    def analyze_query_intent(self, query_text: str) -> dict[str, Any]:
        """Analyze query intent (delegates to IntentScorer)."""
        intent = self.intent_scorer.analyze_query_intent(query_text)

        # Add suggested facets
        facets = self.facet_detector.suggest_facets(query_text)
        intent["suggested_filters"] = facets

        return intent

    def suggest_facets(
        self, query_text: str, current_facets: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Suggest facets (delegates to FacetDetector)."""
        return self.facet_detector.suggest_facets(query_text, current_facets)

    def rank_results(
        self,
        results: list[dict[str, Any]],
        query_intent: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank results (delegates to ResultRanker)."""
        return self.result_ranker.rank_results(results, query_intent, user_context)

    def generate_search_insights(
        self, query_text: str, results: list[dict[str, Any]], facets: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate insights about search results.

        Args:
            query_text: Original search query,
            results: Search results,
            facets: Applied facets

        Returns:
            Dictionary with insights and recommendations
        """
        return {
            "result_count": len(results),
            "coverage": self._analyze_coverage(results, facets),
            "recommendations": self._generate_recommendations(query_text, results, facets),
            "trends": self._detect_trends(results),
        }

    def _analyze_coverage(
        self, results: list[dict[str, Any]], _facets: dict[str, Any]
    ) -> dict[str, Any]:
        """Analyze how well results cover the search space."""
        if not results:
            return {"status": "no_results", "message": "No results found"}

        # Count unique attributes
        domains = set(r.get("domain") for r in results if r.get("domain"))
        content_types = set(r.get("content_type") for r in results if r.get("content_type"))

        return {
            "status": "good" if len(results) > 5 else "limited",
            "domains_covered": len(domains),
            "content_types": len(content_types),
            "has_variety": len(domains) > 1 or len(content_types) > 1,
        }

    def _generate_recommendations(
        self, _query_text: str, results: list[dict[str, Any]], _facets: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Generate search recommendations."""
        recommendations = []

        # No results
        if not results:
            recommendations.append(
                {
                    "type": "broaden_search",
                    "message": "Try removing filters or using more general terms",
                }
            )
            return recommendations

        # Too many results
        if len(results) > 50:
            recommendations.append(
                {
                    "type": "narrow_search",
                    "message": "Too many results - add more specific filters",
                }
            )

        # Single domain
        domains = set(r.get("domain") for r in results if r.get("domain"))
        if len(domains) == 1:
            recommendations.append(
                {
                    "type": "explore_domains",
                    "message": "Consider exploring related content in other domains",
                }
            )

        return recommendations

    def _detect_trends(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect trends in search results."""
        if not results:
            return {}

        # Most common domain
        domains = [r.get("domain") for r in results if r.get("domain")]
        most_common_domain = max(set(domains), key=domains.count) if domains else None

        # Most common content type
        content_types = [r.get("content_type") for r in results if r.get("content_type")]
        most_common_type = (
            max(set(content_types), key=content_types.count) if content_types else None
        )

        return {
            "dominant_domain": most_common_domain,
            "dominant_content_type": most_common_type,
            "total_results": len(results),
        }
