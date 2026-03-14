"""
Mastery & Learning Intelligence Models
=======================================

Persistent entities for learning intelligence across the curriculum domain.
Mastery applies to both Lessons (teaching compositions) and atomic Kus
(reference nodes) — the class names are entity-agnostic by design.

See: /docs/architecture/FOUR_PHASED_LEARNING_LOOP.md
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from core.models.enums import Domain


class MasteryLevel(StrEnum):
    """Knowledge mastery progression levels."""

    UNAWARE = "unaware"  # No exposure
    INTRODUCED = "introduced"  # Basic awareness
    FAMILIAR = "familiar"  # Some understanding
    PROFICIENT = "proficient"  # Can apply effectively
    ADVANCED = "advanced"  # Deep understanding
    EXPERT = "expert"  # Can teach others
    MASTERED = "mastered"  # Complete mastery


class LearningVelocity(StrEnum):
    """Learning speed patterns for different content types."""

    VERY_SLOW = "very_slow"  # Needs extra time and repetition
    SLOW = "slow"  # Below average learning speed
    MODERATE = "moderate"  # Average learning speed
    FAST = "fast"  # Above average learning speed
    VERY_FAST = "very_fast"  # Rapid comprehension and retention


class ContentPreference(StrEnum):
    """Preferred content presentation types."""

    VISUAL = "visual"  # Diagrams, charts, images
    TEXTUAL = "textual"  # Written explanations
    INTERACTIVE = "interactive"  # Hands-on exercises
    VIDEO = "video"  # Video content
    AUDIO = "audio"  # Podcasts, audio explanations
    PRACTICAL = "practical"  # Real-world examples
    THEORETICAL = "theoretical"  # Abstract concepts


@dataclass(frozen=True)
class Mastery:
    """
    Persistent Knowledge Mastery Intelligence.

    Tracks individual user mastery of specific knowledge units with
    sophisticated learning analytics that improve recommendations
    and personalization over time.
    """

    uid: str
    user_uid: str
    knowledge_uid: str

    # Core mastery metrics
    mastery_level: MasteryLevel
    confidence_score: float  # 0.0 - 1.0, how confident in this mastery assessment
    mastery_score: float  # 0.0 - 1.0, detailed mastery measurement

    # Learning analytics
    learning_velocity: LearningVelocity
    time_to_mastery_hours: float | None
    review_frequency_days: int | None

    # Evidence and validation
    mastery_evidence: list[str]  # Types of evidence supporting mastery
    last_reviewed: datetime
    last_practiced: datetime | None

    # Context and metadata
    learning_path_context: str | None  # Which learning path led to mastery
    difficulty_experienced: str | None  # How difficult user found this
    preferred_learning_method: ContentPreference | None

    # Temporal tracking
    created_at: datetime
    updated_at: datetime

    def is_current_mastery(self) -> bool:
        """Check if mastery assessment is current (not stale)."""
        days_since_review = (datetime.now() - self.last_reviewed).days

        if self.mastery_level in [MasteryLevel.EXPERT, MasteryLevel.MASTERED]:
            return days_since_review <= 90  # Expert knowledge stays fresh longer
        elif self.mastery_level in [MasteryLevel.PROFICIENT, MasteryLevel.ADVANCED]:
            return days_since_review <= 60
        else:
            return days_since_review <= 30

    def needs_review(self) -> bool:
        """Determine if this knowledge needs review based on mastery level."""
        if not self.is_current_mastery():
            return True

        if self.mastery_level in [MasteryLevel.INTRODUCED, MasteryLevel.FAMILIAR]:
            return (datetime.now() - self.last_reviewed).days >= 7
        elif self.mastery_level == MasteryLevel.PROFICIENT:
            return (datetime.now() - self.last_reviewed).days >= 30
        else:
            return (datetime.now() - self.last_reviewed).days >= 90

    def get_mastery_strength(self) -> float:
        """Calculate overall mastery strength combining level and confidence."""
        level_scores = {
            MasteryLevel.UNAWARE: 0.0,
            MasteryLevel.INTRODUCED: 0.2,
            MasteryLevel.FAMILIAR: 0.4,
            MasteryLevel.PROFICIENT: 0.6,
            MasteryLevel.ADVANCED: 0.8,
            MasteryLevel.EXPERT: 0.9,
            MasteryLevel.MASTERED: 1.0,
        }

        base_score = level_scores.get(self.mastery_level, 0.0)
        return base_score * self.confidence_score

    def can_teach_others(self) -> bool:
        """Determine if user can help others learn this knowledge."""
        return (
            self.mastery_level in [MasteryLevel.EXPERT, MasteryLevel.MASTERED]
            and self.confidence_score >= 0.8
            and self.is_current_mastery()
        )

    def suggests_aptitude(self) -> bool:
        """Check if mastery pattern suggests user has aptitude in this area."""
        return (
            self.learning_velocity in [LearningVelocity.FAST, LearningVelocity.VERY_FAST]
            and self.mastery_score >= 0.7
            and self.time_to_mastery_hours is not None
            and self.time_to_mastery_hours < 20  # Learned quickly
        )


@dataclass(frozen=True)
class LearningPreference:
    """
    Persistent Learning Preference Intelligence.

    Captures and evolves user learning preferences based on successful
    learning patterns, enabling highly personalized knowledge recommendations
    and learning path optimization.
    """

    uid: str
    user_uid: str

    # Content preferences
    preferred_content_types: list[ContentPreference]
    preferred_difficulty_progression: str  # "gradual", "steep", "mixed"
    preferred_learning_pace: str  # "self_paced", "structured", "intensive"

    # Learning patterns that work for this user
    successful_learning_patterns: dict[str, float]  # pattern_name -> success_rate
    effective_review_intervals: dict[MasteryLevel, int]  # mastery_level -> days

    # Domain-specific preferences
    domain_preferences: dict[Domain, dict[str, Any]]

    # Temporal and contextual preferences
    preferred_learning_times: list[str]  # ["morning", "evening", etc.]
    preferred_session_duration_minutes: int
    prefers_spaced_repetition: bool
    prefers_interleaved_practice: bool

    # Learning style insights
    learns_better_with_examples: bool
    prefers_bottom_up_or_top_down: str  # "bottom_up", "top_down", "mixed"
    benefits_from_analogies: bool
    needs_immediate_application: bool

    # Analytics
    total_learning_sessions: int
    successful_mastery_count: int
    average_time_to_mastery_hours: float

    # Metadata
    created_at: datetime
    updated_at: datetime

    def get_learning_efficiency_score(self) -> float:
        """Calculate overall learning efficiency based on patterns."""
        if self.total_learning_sessions == 0:
            return 0.5  # Default

        success_rate = self.successful_mastery_count / self.total_learning_sessions

        # Factor in learning speed
        speed_factor = 1.0
        if self.average_time_to_mastery_hours < 10:
            speed_factor = 1.3
        elif self.average_time_to_mastery_hours > 30:
            speed_factor = 0.8

        return min(success_rate * speed_factor, 1.0)

    def get_optimal_review_interval(self, mastery_level: MasteryLevel) -> int:
        """Get optimal review interval for this user and mastery level."""
        if mastery_level in self.effective_review_intervals:
            return self.effective_review_intervals[mastery_level]

        # Default intervals based on mastery level
        defaults = {
            MasteryLevel.INTRODUCED: 3,
            MasteryLevel.FAMILIAR: 7,
            MasteryLevel.PROFICIENT: 21,
            MasteryLevel.ADVANCED: 45,
            MasteryLevel.EXPERT: 90,
            MasteryLevel.MASTERED: 180,
        }
        return defaults.get(mastery_level, 14)

    def recommends_content_type(self, domain: Domain) -> list[ContentPreference]:
        """Get recommended content types for specific domain."""
        if domain in self.domain_preferences:
            domain_prefs = self.domain_preferences[domain]
            if "preferred_content_types" in domain_prefs:
                return domain_prefs["preferred_content_types"]

        return self.preferred_content_types

    def should_use_spaced_repetition(self) -> bool:
        """Determine if spaced repetition is effective for this user."""
        return self.prefers_spaced_repetition and self.get_learning_efficiency_score() > 0.6


@dataclass(frozen=True)
class LearningRecommendation:
    """
    Intelligent Knowledge Recommendation.

    Generated through relationship intelligence rather than static algorithms.
    Learns and improves based on user interaction and success patterns.
    """

    uid: str
    user_uid: str
    knowledge_uid: str

    # Recommendation intelligence
    recommendation_score: float
    learning_value: float
    personalization_score: float

    # Context and reasoning
    recommendation_type: str  # "prerequisite_gap", "natural_progression", "related_interest"
    reasoning: str
    supporting_evidence: list[str]

    # Integration context
    learning_path_context: str | None
    search_context: str | None
    goal_context: str | None

    # Timing and priority
    urgency_score: float
    optimal_timing: str  # "immediate", "short_term", "long_term"
    estimated_effort_hours: float | None

    # Tracking
    presented_to_user: bool = False
    user_action: str | None = None  # "accepted", "dismissed", "deferred"
    success_outcome: bool | None = None
    created_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())

    def is_high_value_recommendation(self) -> bool:
        """Determine if this is a high-value recommendation."""
        return (
            self.recommendation_score >= 0.8
            and self.learning_value >= 0.7
            and self.personalization_score >= 0.6
        )

    def should_prioritize(self) -> bool:
        """Determine if this recommendation should be prioritized."""
        return (
            self.urgency_score >= 0.7
            and self.is_high_value_recommendation()
            and self.optimal_timing in ["immediate", "short_term"]
        )

    def get_presentation_context(self) -> dict[str, Any]:
        """Get context for presenting this recommendation to user."""
        return {
            "reasoning": self.reasoning,
            "value_proposition": f"Learning value: {self.learning_value:.0%}",
            "effort_estimate": f"{self.estimated_effort_hours:.1f} hours"
            if self.estimated_effort_hours
            else "Quick",
            "timing": self.optimal_timing,
            "connections": len(self.supporting_evidence),
        }


# Factory functions for creating intelligence entities


def create_mastery(
    user_uid: str,
    knowledge_uid: str,
    initial_level: MasteryLevel = MasteryLevel.INTRODUCED,
    evidence: list[str] | None = None,
) -> Mastery:
    """Create initial mastery tracking for a Lesson or atomic Ku."""
    mastery_uid = f"mastery_{user_uid}_{knowledge_uid}"

    return Mastery(
        uid=mastery_uid,
        user_uid=user_uid,
        knowledge_uid=knowledge_uid,
        mastery_level=initial_level,
        confidence_score=0.5,  # Start with medium confidence
        mastery_score=0.2 if initial_level == MasteryLevel.INTRODUCED else 0.0,
        learning_velocity=LearningVelocity.MODERATE,  # Will be updated based on observation
        time_to_mastery_hours=None,
        review_frequency_days=None,
        mastery_evidence=evidence or [],
        last_reviewed=datetime.now(),
        last_practiced=None,
        learning_path_context=None,
        difficulty_experienced=None,
        preferred_learning_method=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def create_learning_preference(user_uid: str) -> LearningPreference:
    """Create initial learning preference profile."""
    preference_uid = f"learning_pref_{user_uid}"

    return LearningPreference(
        uid=preference_uid,
        user_uid=user_uid,
        preferred_content_types=[ContentPreference.TEXTUAL, ContentPreference.PRACTICAL],
        preferred_difficulty_progression="gradual",
        preferred_learning_pace="self_paced",
        successful_learning_patterns={},
        effective_review_intervals={},
        domain_preferences={},
        preferred_learning_times=["morning", "evening"],
        preferred_session_duration_minutes=45,
        prefers_spaced_repetition=True,
        prefers_interleaved_practice=False,
        learns_better_with_examples=True,
        prefers_bottom_up_or_top_down="bottom_up",
        benefits_from_analogies=True,
        needs_immediate_application=False,
        total_learning_sessions=0,
        successful_mastery_count=0,
        average_time_to_mastery_hours=25.0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
