"""
LP Intelligence Types - Shared Data Structures
===============================================

Shared dataclasses and enums for LP Intelligence services.

This module contains type definitions used across all LP Intelligence sub-services:
- LearningStateAnalyzer
- LearningRecommendationEngine
- ContentAnalyzer
- ContentQualityAssessor
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.models.shared_enums import GuidanceMode

# ============================================================================
# ENUMS
# ============================================================================


class LearningReadiness(Enum):
    """User's readiness for new learning."""

    REVIEW_NEEDED = "review_needed"
    READY_FOR_NEW = "ready_for_new"
    CONSOLIDATE = "consolidate"
    TAKE_BREAK = "take_break"
    CHALLENGE_READY = "challenge_ready"


# ============================================================================
# LEARNING STATE ANALYSIS
# ============================================================================


@dataclass
class LearningAnalysis:
    """Comprehensive learning state analysis."""

    user_uid: str
    timestamp: datetime

    # Current state
    learning_level: str
    mastery_average: float
    concepts_mastered: int
    concepts_in_progress: int
    concepts_needing_review: list[str]

    # Readiness assessment
    readiness: LearningReadiness
    confidence_score: float

    # Pedagogical analysis
    understanding_level: float  # 0-1
    engagement_level: float  # 0-1
    needs_encouragement: bool
    needs_clarification: bool
    needs_challenge: bool
    needs_break: bool

    # Recommendations
    recommended_guidance: GuidanceMode
    recommended_actions: list[str]
    focus_areas: list[str]

    # Vector analysis (if available)
    learning_style_vector: list[float] | None = None
    content_affinity_scores: dict[str, float] | None = None


@dataclass
class ProgressSummary:
    """Summary of user progress across domains."""

    learning_mastery_average: float = 0.0
    overall_momentum_score: float = 0.0
    habits_consistency_rate: float = 0.0
    learning_time_minutes: int = 0
    goals_at_risk: int = 0


# ============================================================================
# CONTENT RECOMMENDATIONS
# ============================================================================


@dataclass
class ContentRecommendation:
    """Intelligent content recommendation."""

    content_uid: str
    content_type: str
    title: str
    relevance_score: float
    difficulty_match: float
    prerequisites_met: bool
    learning_impact: str
    recommendation_reason: str
    confidence_score: float


# ============================================================================
# LEARNING INTERVENTIONS
# ============================================================================


@dataclass
class LearningIntervention:
    """Suggested intervention based on analysis."""

    intervention_type: str  # "encouragement", "clarification", "challenge", "break"
    priority: float  # 0-1
    message: str
    suggested_action: str
    estimated_impact: str


# ============================================================================
# CONTENT ANALYSIS
# ============================================================================


@dataclass
class ContentMetadata:
    """
    Metadata extracted from content analysis.

    This replaces the old ContentAnalysisService metadata extraction.
    """

    content_uid: str

    # Text analysis
    keywords: list[str]
    summary: str | None
    reading_time_minutes: int
    complexity_score: float  # 0-1, where 1 is most complex

    # Content features
    has_code: bool
    has_images: bool
    has_links: bool
    has_exercises: bool

    # Educational metrics
    concept_density: float  # concepts per 100 words
    example_count: int
    definition_count: int

    # Similarity features
    embedding_vector: list[float] | None = None
    topic_categories: list[str] | None = None


@dataclass
class ContentAnalysisResult:
    """Result of comprehensive content analysis."""

    metadata: ContentMetadata
    quality_score: float  # 0-1
    completeness_score: float  # 0-1
    educational_value: str  # "high", "medium", "low"
    recommended_improvements: list[str]
