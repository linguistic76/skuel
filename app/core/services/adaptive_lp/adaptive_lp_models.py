"""
Adaptive Learning Path Models
==============================

Shared dataclasses and enums for the adaptive learning path system.

These models are used across all adaptive_lp sub-services:
- AdaptiveLp: Dynamic learning path structure
- AdaptiveRecommendation: Personalized learning recommendations
- CrossDomainOpportunity: Cross-domain learning opportunities
- PersonalizedSuggestion: Application suggestions
- LpType, RecommendationType, LearningStyle: Enum types
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from core.models.enums import Domain


class LpType(str, Enum):
    """Types of learning paths that can be generated."""

    GOAL_DRIVEN = "goal_driven"  # Based on specific user goals
    GAP_FILLING = "gap_filling"  # Fills identified knowledge gaps
    CROSS_DOMAIN = "cross_domain"  # Connects knowledge across domains
    REINFORCEMENT = "reinforcement"  # Strengthens existing knowledge
    EXPLORATION = "exploration"  # Discovers new related areas
    PROJECT_BASED = "project_based"  # Organized around practical projects


class RecommendationType(str, Enum):
    """Types of adaptive recommendations."""

    NEXT_STEP = "next_step"  # Logical next learning step
    PREREQUISITE = "prerequisite"  # Missing prerequisites
    APPLICATION = "application"  # Practice/application opportunity
    REVIEW = "review"  # Reinforcement of existing knowledge
    ALTERNATIVE = "alternative"  # Different approach to same goal
    STRETCH = "stretch"  # Advanced/challenging content


class LearningStyle(str, Enum):
    """Detected user learning styles."""

    SEQUENTIAL = "sequential"  # Step-by-step, linear progression
    HOLISTIC = "holistic"  # Big picture first, then details
    PRACTICAL = "practical"  # Learn by doing, project-based
    THEORETICAL = "theoretical"  # Concepts first, application later
    SOCIAL = "social"  # Collaborative learning
    INDEPENDENT = "independent"  # Self-directed learning


@dataclass
class AdaptiveLp:
    """A dynamically generated learning path tailored to user needs."""

    path_id: str
    title: str
    description: str
    path_type: LpType

    # Goal and outcome focused
    target_goals: list[str]  # Goal UIDs this path supports
    learning_outcomes: list[str]  # Specific outcomes expected
    estimated_duration_hours: int
    difficulty_level: float  # 0-10 scale

    # Adaptive components
    knowledge_steps: list[str]  # Ordered knowledge unit UIDs
    alternative_paths: list[str]  # Alternative step sequences
    prerequisites: list[str]  # Required before starting
    unlocks: list[str]  # Knowledge unlocked upon completion

    # Personalization
    adaptation_factors: dict[str, float]  # Factors influencing adaptation
    learning_style_match: float  # How well this matches user's style
    confidence_score: float  # Confidence in path effectiveness

    # Progress tracking
    completion_percentage: float = 0.0
    current_step_index: int = 0
    mastery_checkpoints: list[int] = field(default_factory=list)
    adaptive_adjustments: list[str] = field(default_factory=list)

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)
    last_adapted: datetime = field(default_factory=datetime.now)
    adaptation_count: int = 0
    effectiveness_score: float | None = None


@dataclass
class AdaptiveRecommendation:
    """A personalized learning recommendation that adapts to user progress."""

    recommendation_id: str
    recommendation_type: RecommendationType
    title: str
    description: str

    # Content
    knowledge_uid: str
    related_goals: list[str]
    application_suggestions: list[str]

    # Scoring
    relevance_score: float  # How relevant to current state
    impact_score: float  # Expected learning impact
    confidence_score: float  # Confidence in recommendation
    urgency_score: float  # How urgent/time-sensitive

    # Adaptation factors
    gap_address_score: float  # How well it addresses gaps
    goal_alignment_score: float  # Alignment with user goals
    style_match_score: float  # Match with learning style
    difficulty_appropriateness: float  # Appropriate difficulty level

    # Context
    reasoning: str  # Why this recommendation
    prerequisites_met: bool
    estimated_time_minutes: int
    alternative_options: list[str] = field(default_factory=list)

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None


@dataclass
class CrossDomainOpportunity:
    """An opportunity to apply knowledge across different domains."""

    opportunity_id: str
    title: str
    description: str

    # Domain connections
    source_domain: Domain
    target_domain: Domain
    bridging_knowledge: list[str]  # Knowledge that connects domains

    # Opportunity details
    application_type: str  # How knowledge applies across domains
    practical_projects: list[str]  # Suggested projects to explore this
    skill_transfer_potential: float  # How much skill transfers (0-1)
    innovation_potential: float  # Potential for creative application

    # Requirements
    prerequisite_knowledge: list[str]
    source_knowledge_uids: list[str]  # KU UIDs from source domain
    target_knowledge_uids: list[str]  # KU UIDs from target domain
    estimated_difficulty: float  # 0-10 scale
    estimated_value: float  # Expected learning value

    # Evidence
    supporting_examples: list[str]  # Real-world examples
    success_patterns: list[str]  # Patterns from successful transfers
    confidence_score: float


@dataclass
class PersonalizedSuggestion:
    """A personalized knowledge application suggestion."""

    suggestion_id: str
    title: str
    description: str

    # Application context
    knowledge_to_apply: list[str]  # Knowledge UIDs to apply
    application_context: str  # Where/how to apply
    expected_outcomes: list[str]  # What user will achieve

    # Personalization
    personalization_factors: dict[str, Any]  # Why personalized to this user
    user_readiness_score: float  # How ready user is (0-1)
    timing_appropriateness: float  # How appropriate the timing is

    # Actionability
    concrete_steps: list[str]  # Specific steps to take
    resources_needed: list[str]  # Resources required
    time_investment: int  # Minutes required
    success_indicators: list[str]  # How to measure success

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)
    priority_score: float = 0.0
