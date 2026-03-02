"""
SKUEL Constants - Single Source of Truth
=========================================

Centralized numeric constants for graph operations, thresholds, and limits.
This module follows the "Dynamic Enum Pattern" philosophy from shared_enums.py
but for numeric constants rather than enumerations.

Core Principle: "Constants define behavior, services consume them"

All hardcoded magic numbers should live here, organized by concern.
When you need to tune a threshold or limit, edit this file once,
and the entire codebase updates.

Last updated: 2026-01-24
"""

from typing import Final

__version__ = "1.0.0"


# ============================================================================
# GRAPH TRAVERSAL DEPTHS
# ============================================================================


class GraphDepth:
    """
    Standard depth values for Neo4j graph traversal.

    Philosophy: Different traversal patterns require different depths.
    - Shallow (depth=1): Direct relationships only
    - Medium (depth=2): Neighborhood context
    - Default (depth=3): Rich bi-directional context (SKUEL standard)
    - Deep (depth=5): Prerequisite chains
    - Maximum (depth=10): Shortest path queries

    See: CLAUDE.md - "Pattern-Based Queries Over Property Queries"
    """

    # Direct relationships only (fast, use sparingly)
    DIRECT: Final = 1

    # Neighborhood context (moderate depth)
    NEIGHBORHOOD: Final = 2

    # Default depth for semantic queries (SKUEL standard)
    DEFAULT: Final = 3

    # Extended context (richer than default, less than full chains)
    EXTENDED: Final = 4

    # Prerequisite chains and learning paths
    PREREQUISITE_CHAIN: Final = 5

    # Maximum depth for shortest path queries
    MAXIMUM: Final = 10

    @classmethod
    def get_description(cls, depth: int) -> str:
        """Get human-readable description of depth level."""
        descriptions = {
            cls.DIRECT: "Direct relationships only (shallow)",
            cls.NEIGHBORHOOD: "Neighborhood context (moderate)",
            cls.DEFAULT: "Rich bi-directional context (default)",
            cls.EXTENDED: "Extended context (richer than default)",
            cls.PREREQUISITE_CHAIN: "Prerequisite chains (deep)",
            cls.MAXIMUM: "Shortest path (maximum allowed)",
        }
        return descriptions.get(depth, f"Custom depth ({depth} hops)")


# ============================================================================
# CONFIDENCE THRESHOLDS
# ============================================================================


class ConfidenceLevel:
    """
    Relationship confidence thresholds (0.0 - 1.0).

    Confidence indicates the strength of a semantic relationship:
    - 0.95: Very high confidence (expert knowledge)
    - 0.9: High confidence (strong connection)
    - 0.85: Good confidence (validated relationship)
    - 0.8: Standard confidence (default minimum)
    - 0.7: Medium confidence (useful but uncertain)
    - 0.6: Low confidence (exploratory)

    Usage: Filter relationships by minimum confidence level.
    """

    # Very high confidence - expert knowledge
    VERY_HIGH: Final = 0.95

    # High confidence - strong connection
    HIGH: Final = 0.9

    # Good confidence - validated relationship
    GOOD: Final = 0.85

    # Standard confidence - default minimum for most queries
    STANDARD: Final = 0.8

    # Medium confidence - useful but uncertain
    MEDIUM: Final = 0.7

    # Low confidence - exploratory relationships
    LOW: Final = 0.6

    # Minimum acceptable confidence for reliable prerequisites
    MIN_RELIABLE: Final = 0.9

    # Default for general relationship queries
    DEFAULT: Final = 0.8

    @classmethod
    def get_label(cls, confidence: float) -> str:
        """Get human-readable label for confidence value."""
        if confidence >= cls.VERY_HIGH:
            return "Very High"
        if confidence >= cls.HIGH:
            return "High"
        if confidence >= cls.GOOD:
            return "Good"
        if confidence >= cls.STANDARD:
            return "Standard"
        if confidence >= cls.MEDIUM:
            return "Medium"
        if confidence >= cls.LOW:
            return "Low"
        return "Very Low"


# ============================================================================
# MASTERY THRESHOLDS
# ============================================================================


class MasteryLevel:
    """
    Knowledge mastery thresholds (0.0 - 1.0).

    Mastery indicates how well a user has learned a knowledge unit:
    - 0.9: Expert level - can teach others
    - 0.8: Proficient - comfortable application
    - 0.7: Competent - basic understanding and application
    - 0.5: Beginner - familiar but not confident

    See: CLAUDE.md - "Knowledge Substance Philosophy"
    """

    # Expert level - can teach others
    EXPERT: Final = 0.9

    # Proficient - comfortable application
    PROFICIENT: Final = 0.8

    # Competent - basic understanding (default threshold)
    COMPETENT: Final = 0.7

    # Beginner - familiar but not confident
    BEGINNER: Final = 0.5

    # Default threshold for "mastered" status
    DEFAULT: Final = 0.7

    @classmethod
    def get_label(cls, mastery: float) -> str:
        """Get human-readable label for mastery value."""
        if mastery >= cls.EXPERT:
            return "Expert"
        if mastery >= cls.PROFICIENT:
            return "Proficient"
        if mastery >= cls.COMPETENT:
            return "Competent"
        if mastery >= cls.BEGINNER:
            return "Beginner"
        return "Novice"


# ============================================================================
# QUERY LIMITS
# ============================================================================


class QueryLimit:
    """
    Standard result set limits for database queries.

    Philosophy: Different UI contexts need different result limits.
    - PREVIEW: Quick previews (5 items)
    - SMALL: Widget displays (10 items)
    - MEDIUM: List pages (20 items)
    - STANDARD: Default pagination (50 items)
    - LARGE: Comprehensive results (100 items)
    - BULK: Bulk operations (1000 items)

    See: CLAUDE.md - "Unified Query Pattern for Meta-Services"
    """

    # Quick previews (dashboard widgets)
    PREVIEW: Final = 5

    # Small lists (sidebar, dropdowns)
    SMALL: Final = 10

    # Medium lists (search results)
    MEDIUM: Final = 20

    # Large lists (full page listings)
    LARGE: Final = 25

    # Default pagination size
    DEFAULT: Final = 50

    # Comprehensive results
    COMPREHENSIVE: Final = 100

    # Bulk operations (use with caution)
    BULK: Final = 1000

    # Maximum allowed (for admin/debug only)
    MAXIMUM: Final = 10000

    @classmethod
    def get_description(cls, limit: int) -> str:
        """Get human-readable description of limit."""
        descriptions = {
            cls.PREVIEW: "Preview (quick glance)",
            cls.SMALL: "Small list (widgets)",
            cls.MEDIUM: "Medium list (search results)",
            cls.LARGE: "Large list (full page)",
            cls.DEFAULT: "Default pagination",
            cls.COMPREHENSIVE: "Comprehensive results",
            cls.BULK: "Bulk operations",
            cls.MAXIMUM: "Maximum (admin only)",
        }
        return descriptions.get(limit, f"Custom limit ({limit} items)")


# ============================================================================
# INTELLIGENCE THRESHOLDS
# ============================================================================


class IntelligenceThreshold:
    """
    AI/ML confidence thresholds for intelligent features.

    Used by: Intelligence services, recommendations, auto-generation
    - AUTO_PUBLISH: Auto-publish threshold (0.8)
    - HIGH_CONFIDENCE: High confidence insights (0.75-0.87)
    - STYLE_MATCHING: Learning style confidence (0.6)
    - CROSS_DOMAIN: Cross-domain relationship threshold (0.6)
    """

    # Auto-publish generated content
    AUTO_PUBLISH: Final = 0.8

    # High confidence insights
    HIGH_CONFIDENCE_MIN: Final = 0.75
    HIGH_CONFIDENCE_MAX: Final = 0.87

    # Learning style matching
    STYLE_CONFIDENCE: Final = 0.6

    # Cross-domain relationships
    CROSS_DOMAIN: Final = 0.6

    # Minimum confidence for recommendations
    MIN_RECOMMENDATION: Final = 0.7


class QueryProcessorConfidence:
    """
    Confidence scoring for QueryProcessor RAG pipeline responses.

    Confidence is calculated dynamically based on:
    - Base confidence (starting point)
    - Context availability (entities found, relevant context)
    - Citation availability (source and evidence)
    - Entity extraction success

    Philosophy: Confidence reflects how much supporting data was available
    to generate the response, not a measure of correctness.

    January 2026: Added to replace hardcoded 0.85 confidence values.
    """

    # Base confidence when minimal context is available
    BASE: Final = 0.70

    # Bonus when relevant context was retrieved
    CONTEXT_BONUS: Final = 0.10

    # Bonus when citations are included
    CITATION_BONUS: Final = 0.05

    # Bonus when entities were extracted from query
    ENTITY_BONUS: Final = 0.05

    # Maximum confidence cap
    MAX: Final = 0.95

    @classmethod
    def calculate(
        cls,
        has_context: bool = False,
        has_citations: bool = False,
        has_entities: bool = False,
    ) -> float:
        """
        Calculate confidence score based on available factors.

        Args:
            has_context: Whether relevant context was retrieved
            has_citations: Whether citations were included
            has_entities: Whether entities were extracted from query

        Returns:
            Confidence score (0.70 - 0.95)
        """
        confidence = cls.BASE
        if has_context:
            confidence += cls.CONTEXT_BONUS
        if has_citations:
            confidence += cls.CITATION_BONUS
        if has_entities:
            confidence += cls.ENTITY_BONUS
        return min(confidence, cls.MAX)


# ============================================================================
# ANALYSIS PERIODS
# ============================================================================


class AnalysisPeriod:
    """
    Standard time periods for analytics and reporting.

    Philosophy: Consistent period definitions across all analytics.
    """

    # Short-term analysis
    DAILY: Final = "daily"
    WEEKLY: Final = "weekly"

    # Medium-term analysis
    MONTHLY: Final = "monthly"
    QUARTERLY: Final = "quarterly"

    # Long-term analysis
    YEARLY: Final = "yearly"
    ALL_TIME: Final = "all_time"

    # Intelligence-specific periods
    DAYS_30: Final = "30_days"
    DAYS_90: Final = "90_days"
    DAYS_180: Final = "180_days"


# ============================================================================
# GRAPH RELATIONSHIP METADATA
# ============================================================================


class RelationshipStrength:
    """
    Default confidence values for different relationship types.

    Used when creating semantic relationships with default metadata.
    """

    # Applied knowledge (task → knowledge)
    APPLIES_KNOWLEDGE: Final = 0.85

    # Practice/embodiment (event → knowledge)
    PRACTICES_KNOWLEDGE: Final = 0.9

    # Habit development (habit → knowledge)
    DEVELOPS_KNOWLEDGE: Final = 0.9

    # Default for generic relationships
    DEFAULT: Final = 0.7


# ============================================================================
# FEEDBACK TIME PERIODS
# ============================================================================


class FeedbackTimePeriod:
    """
    Valid time period strings for activity feedback and review.

    Used by: ActivityReportService, ProgressFeedbackGenerator
    Both services share the same API-facing period vocabulary ("7d", "14d", etc.)
    and the corresponding day counts for datetime arithmetic.
    """

    WEEK: Final = "7d"
    TWO_WEEKS: Final = "14d"
    MONTH: Final = "30d"
    QUARTER: Final = "90d"
    DEFAULT: Final = "7d"
    DEFAULT_DAYS: Final = 7

    DAYS: Final[dict[str, int]] = {
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "90d": 90,
    }


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example: Graph traversal depth
    print(f"Default depth: {GraphDepth.DEFAULT}")
    print(f"Description: {GraphDepth.get_description(GraphDepth.DEFAULT)}")

    # Example: Confidence filtering
    print(f"\nStandard confidence: {ConfidenceLevel.STANDARD}")
    print(f"Label: {ConfidenceLevel.get_label(0.85)}")

    # Example: Mastery levels
    print(f"\nDefault mastery: {MasteryLevel.DEFAULT}")
    print(f"Label: {MasteryLevel.get_label(0.75)}")

    # Example: Query limits
    print(f"\nPreview limit: {QueryLimit.PREVIEW}")
    print(f"Description: {QueryLimit.get_description(QueryLimit.PREVIEW)}")
