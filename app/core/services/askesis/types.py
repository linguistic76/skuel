"""
Askesis Services - Shared Type Definitions
===========================================

Frozen dataclasses and enums shared across all Askesis sub-services.

This module was created on 2025-11-05 by refactoring EnhancedAskesisService
to follow Single Responsibility Principle.

Architecture:
- All dataclasses are frozen (immutable)
- Shared across UserStateAnalyzer, ActionRecommendationEngine, QueryProcessor,
  EntityExtractor, and ContextRetriever
- Enum types define insight categories, recommendation types, and query intent
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

    from core.models.enums import Domain, Priority
    from core.models.zpd.zpd_assessment import ZPDAssessment

# ============================================================================
# ENUMS - INSIGHT & RECOMMENDATION TYPES
# ============================================================================


class InsightType(Enum):
    """Types of insights Askesis can provide."""

    PATTERN = "pattern"  # Behavioral patterns
    OPPORTUNITY = "opportunity"  # Growth opportunities
    RISK = "risk"  # Potential risks
    RECOMMENDATION = "recommendation"  # Action recommendations
    CORRELATION = "correlation"  # Relationship insights
    PREDICTION = "prediction"  # Future state predictions
    OPTIMIZATION = "optimization"  # Efficiency improvements


class RecommendationCategory(Enum):
    """Categories of recommendations."""

    IMMEDIATE = "immediate"  # Do now
    SHORT_TERM = "short_term"  # This week
    LONG_TERM = "long_term"  # This month+
    STRATEGIC = "strategic"  # Overall approach
    PREVENTIVE = "preventive"  # Avoid problems
    RECOVERY = "recovery"  # Fix issues


# ============================================================================
# DATACLASSES - CORE ANALYSIS TYPES
# ============================================================================


@dataclass(frozen=True)
class AskesisInsight:
    """
    A single insight from Askesis analysis.

    Insights identify patterns, opportunities, risks, or correlations
    across user's domains and activities.

    Attributes:
        type: Category of insight (pattern, opportunity, risk, etc.)
        title: Short descriptive title
        description: Detailed explanation of the insight
        confidence: Confidence score (0.0 to 1.0)
        impact: Impact level ("low", "medium", "high", "critical")
        domains_affected: List of domains this insight touches
        entities_involved: Dict mapping entity types to UIDs (e.g., {"task": ["task_1"]})
        recommended_actions: List of actionable steps to respond to insight
        supporting_data: Additional data backing the insight
        expires_at: Optional expiration time for time-sensitive insights
    """

    type: InsightType
    title: str
    description: str
    confidence: float  # 0.0 to 1.0
    impact: str  # "low", "medium", "high", "critical"
    domains_affected: list[Domain]
    entities_involved: dict[str, list[str]]  # type -> UIDs
    recommended_actions: list[dict[str, Any]]
    supporting_data: dict[str, Any]
    expires_at: datetime | None = None


@dataclass(frozen=True)
class AskesisRecommendation:
    """
    A recommendation from Askesis for user action.

    Recommendations are prioritized, actionable suggestions based on
    user's current state and patterns.

    Attributes:
        category: Type of recommendation (immediate, short-term, strategic, etc.)
        title: Short action title
        rationale: Explanation for why this is recommended
        action_type: Type of action ("create", "complete", "modify", "review")
        target_entity: Tuple of (entity_type, entity_uid)
        priority: Priority level (from shared_enums.Priority)
        estimated_time_minutes: Expected time to complete
        expected_outcome: What will be achieved
        prerequisites: List of prerequisite UIDs that must be satisfied
        confidence: Confidence in recommendation (0.0 to 1.0)
        alternative_actions: List of alternative approaches
    """

    category: RecommendationCategory
    title: str
    rationale: str
    action_type: str  # "create", "complete", "modify", "review", etc.
    target_entity: tuple[str, str]  # (type, uid)
    priority: Priority
    estimated_time_minutes: int
    expected_outcome: str
    prerequisites: list[str]
    confidence: float
    alternative_actions: list[dict[str, Any]]


@dataclass(frozen=True)
class AskesisAnalysis:
    """
    Complete comprehensive analysis from Askesis.

    Combines insights, recommendations, health metrics, risk assessment,
    and optimization opportunities into a unified analysis.

    Attributes:
        user_uid: User identifier
        generated_at: Timestamp of analysis
        context_summary: High-level summary of user's current context
        insights: List of identified insights
        recommendations: List of recommended actions
        health_metrics: Health scores across domains
        risk_assessment: Assessment of current risks
        optimization_opportunities: Identified optimization opportunities
    """

    user_uid: str
    generated_at: datetime
    context_summary: dict[str, Any]
    insights: list[AskesisInsight]
    recommendations: list[AskesisRecommendation]
    health_metrics: dict[str, float]
    risk_assessment: dict[str, Any]
    optimization_opportunities: list[dict[str, Any]]
    # ZPD snapshot (March 2026) — None when ZPDService is not wired or
    # curriculum graph has fewer than 3 KUs.
    # See: core/services/zpd/zpd_service.py — ZPDService.assess_zone()
    zpd_assessment: ZPDAssessment | None = None


# ============================================================================
# DATACLASSES - QUERY PROCESSING TYPES
# ============================================================================


@dataclass(frozen=True)
class QueryResult:
    """
    Result of processing a user query.

    Contains the answer, confidence, supporting entities, and suggested actions.

    Attributes:
        query: Original user query
        answer: Generated answer text
        confidence: Confidence in the answer (0.0 to 1.0)
        entities_referenced: Dict mapping entity types to UIDs used in answer
        supporting_context: Context data that informed the answer
        suggested_actions: Follow-up actions user might take
        related_queries: Related queries user might ask
    """

    query: str
    answer: str
    confidence: float
    entities_referenced: dict[str, list[str]]
    supporting_context: dict[str, Any]
    suggested_actions: list[dict[str, Any]]
    related_queries: list[str]


@dataclass(frozen=True)
class EntityExtractionResult:
    """
    Result of extracting entities from natural language query.

    Attributes:
        knowledge_uids: Extracted knowledge unit UIDs
        task_uids: Extracted task UIDs
        goal_uids: Extracted goal UIDs
        habit_uids: Extracted habit UIDs
        event_uids: Extracted event UIDs
        confidence_scores: Confidence per entity type
    """

    knowledge_uids: list[str]
    task_uids: list[str]
    goal_uids: list[str]
    habit_uids: list[str]
    event_uids: list[str]
    confidence_scores: dict[str, float]  # entity_type -> confidence


# ============================================================================
# DATACLASSES - PATTERN & OPTIMIZATION TYPES
# ============================================================================


@dataclass(frozen=True)
class PatternDetection:
    """
    Detected behavioral or activity pattern.

    Attributes:
        pattern_type: Type of pattern detected ("habit_correlation", "learning_velocity", etc.)
        description: Human-readable description
        confidence: Confidence in pattern detection (0.0 to 1.0)
        entities_involved: UIDs of entities participating in pattern
        supporting_data: Data points supporting the pattern
        recommendations: Actions to leverage or address pattern
    """

    pattern_type: str
    description: str
    confidence: float
    entities_involved: list[str]
    supporting_data: dict[str, Any]
    recommendations: list[str]


@dataclass(frozen=True)
class OptimizationOpportunity:
    """
    Identified opportunity for workflow or learning optimization.

    Attributes:
        title: Short title for opportunity
        description: Detailed explanation
        impact: Expected impact level ("low", "medium", "high")
        effort: Required effort level ("low", "medium", "high")
        affected_domains: Domains that would benefit
        implementation_steps: Steps to implement optimization
        estimated_benefit: Quantified benefit (if calculable)
    """

    title: str
    description: str
    impact: str  # "low", "medium", "high"
    effort: str  # "low", "medium", "high"
    affected_domains: list[Domain]
    implementation_steps: list[str]
    estimated_benefit: dict[str, Any]


# ============================================================================
# DATACLASSES - CONTEXT & STATE TYPES
# ============================================================================


@dataclass(frozen=True)
class StateSnapshot:
    """
    Snapshot of user state at a point in time.

    Used for predictions and comparisons.

    Attributes:
        timestamp: When snapshot was taken
        momentum: Overall momentum score
        health_score: Overall health score
        domain_balance: Balance across domains (0.0 to 1.0)
        active_counts: Count of active items per domain
        key_blockers: UIDs of blocking entities
        risk_factors: Identified risks
    """

    timestamp: datetime
    momentum: float
    health_score: float
    domain_balance: float
    active_counts: dict[str, int]  # domain -> count
    key_blockers: list[str]
    risk_factors: list[str]


@dataclass(frozen=True)
class LearningContext:
    """
    Complete learning context for a user.

    Includes current knowledge state, learning paths, and knowledge gaps.

    Attributes:
        user_uid: User identifier
        current_knowledge: List of mastered knowledge unit UIDs
        in_progress_learning: Knowledge units currently being learned
        learning_paths: Active learning path UIDs
        knowledge_gaps: Identified gaps (prerequisite chains)
        recommended_next_steps: Suggested next learning actions
        depth: Depth of context retrieval
    """

    user_uid: str
    current_knowledge: list[str]
    in_progress_learning: list[str]
    learning_paths: list[str]
    knowledge_gaps: list[dict[str, Any]]
    recommended_next_steps: list[dict[str, Any]]
    depth: int
