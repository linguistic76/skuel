"""
LifePath Service Types
======================

Frozen dataclasses used by LifePath services.

These are service-layer types (not stored entities):
- LifePathDesignation: View over Ku + ULTIMATE_PATH data
- VisionTheme, VisionCapture, VisionHistory: Vision capture types
- LpRecommendation: LP recommendation type
- WordActionAlignment: Word-action gap analysis type

Relocated from core/models/lifepath/ during Phase 5 Ku unification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.models.enums.ku_enums import AlignmentLevel, ThemeCategory


@dataclass(frozen=True)
class LifePathDesignation:
    """
    LifePath bridges user's VISION (words) with ACTIONS (behavior).

    This is NOT a stored entity — it's computed from:
    1. User's vision statement (their own words, stored on User node)
    2. Designated LP (a Ku with ku_type='life_path', via ULTIMATE_PATH)
    3. Alignment scores (stored on ULTIMATE_PATH relationship)
    4. UserContext (actual behavior tracked across all domains)

    Philosophy:
        "The user's vision is understood via the words user uses
        to communicate, the UserContext is determined via user's actions."
    """

    user_uid: str

    # THE VISION (user's own words, stored on User node)
    vision_statement: str
    vision_themes: tuple[str, ...] = field(default_factory=tuple)
    vision_captured_at: datetime | None = None

    # THE DESIGNATION (Ku with ku_type='life_path', via ULTIMATE_PATH)
    life_path_uid: str | None = None
    designated_at: datetime | None = None

    # THE MEASUREMENT (vision -> action alignment, stored on ULTIMATE_PATH)
    alignment_score: float = 0.0
    word_action_gap: float = 0.0
    alignment_level: AlignmentLevel = AlignmentLevel.EXPLORING

    # Dimension scores (5-dimensional alignment)
    knowledge_alignment: float = 0.0  # Mastery of life path knowledge (25%)
    activity_alignment: float = 0.0  # Tasks/habits supporting life path (25%)
    goal_alignment: float = 0.0  # Active goals contributing to life path (20%)
    principle_alignment: float = 0.0  # Values supporting life path direction (15%)
    momentum: float = 0.0  # Recent activity trend toward life path (15%)

    def __post_init__(self) -> None:
        """Compute derived fields after initialization."""
        if self.vision_captured_at is None:
            object.__setattr__(self, "vision_captured_at", datetime.now())

        level = AlignmentLevel.from_score(self.alignment_score)
        object.__setattr__(self, "alignment_level", level)

    @property
    def has_designation(self) -> bool:
        """Check if user has designated a life path."""
        return self.life_path_uid is not None

    @property
    def has_vision(self) -> bool:
        """Check if user has expressed a vision."""
        return bool(self.vision_statement)

    @property
    def is_aligned(self) -> bool:
        """Check if user is at least 'aligned' level."""
        return self.alignment_level in (AlignmentLevel.FLOURISHING, AlignmentLevel.ALIGNED)

    def get_weakest_dimension(self) -> str:
        """Identify the dimension needing most attention."""
        dimensions = {
            "knowledge": self.knowledge_alignment,
            "activity": self.activity_alignment,
            "goal": self.goal_alignment,
            "principle": self.principle_alignment,
            "momentum": self.momentum,
        }
        return min(dimensions, key=dimensions.get)

    def get_dimension_insights(self) -> dict[str, str]:
        """Generate insights for each alignment dimension."""
        insights = {}

        if self.knowledge_alignment < 0.5:
            insights["knowledge"] = "Focus on mastering knowledge in your life path"
        if self.activity_alignment < 0.5:
            insights["activity"] = "Your daily activities could better support your vision"
        if self.goal_alignment < 0.5:
            insights["goal"] = "Set goals that directly contribute to your life path"
        if self.principle_alignment < 0.5:
            insights["principle"] = "Align your principles more closely with your vision"
        if self.momentum < 0.5:
            insights["momentum"] = "Recent activity shows drift from your life path"

        return insights

    def calculate_weighted_score(self) -> float:
        """
        Calculate weighted alignment score from 5 dimensions.

        Weights:
        - Knowledge: 25%
        - Activity: 25%
        - Goal: 20%
        - Principle: 15%
        - Momentum: 15%
        """
        return (
            self.knowledge_alignment * 0.25
            + self.activity_alignment * 0.25
            + self.goal_alignment * 0.20
            + self.principle_alignment * 0.15
            + self.momentum * 0.15
        )


@dataclass(frozen=True)
class VisionTheme:
    """
    An extracted theme from user's vision statement.

    Themes are keywords/concepts extracted by LLM that represent
    core aspirations in the user's stated vision.
    """

    theme: str
    category: ThemeCategory
    confidence: float = 1.0
    context: str | None = None

    def __post_init__(self) -> None:
        """Normalize theme to lowercase."""
        object.__setattr__(self, "theme", self.theme.lower().strip())


@dataclass(frozen=True)
class VisionCapture:
    """
    Result of capturing and analyzing a user's vision statement.

    Flow:
    1. User types: "I want to become a mindful technical leader"
    2. LLM extracts: themes, categories, and confidence scores
    3. This model holds the structured result
    """

    user_uid: str
    vision_statement: str
    themes: tuple[VisionTheme, ...] = field(default_factory=tuple)
    captured_at: datetime = field(default_factory=datetime.now)

    llm_model: str | None = None
    processing_time_ms: int = 0

    @property
    def theme_keywords(self) -> list[str]:
        """Get just the theme keywords as a list."""
        return [t.theme for t in self.themes]

    @property
    def categories(self) -> set[ThemeCategory]:
        """Get unique categories present in themes."""
        return {t.category for t in self.themes}

    def get_themes_by_category(self, category: ThemeCategory) -> list[VisionTheme]:
        """Get all themes in a specific category."""
        return [t for t in self.themes if t.category == category]

    def to_search_query(self) -> str:
        """Convert themes to a search query for LP matching."""
        return " ".join(self.theme_keywords)


@dataclass(frozen=True)
class LpRecommendation:
    """
    A Learning Path recommendation based on vision themes.

    When user expresses vision, system recommends LPs that match
    the extracted themes.
    """

    lp_uid: str
    lp_name: str
    match_score: float
    matching_themes: tuple[str, ...] = field(default_factory=tuple)
    lp_domain: str | None = None

    @property
    def is_strong_match(self) -> bool:
        """Check if this is a strong recommendation."""
        return self.match_score >= 0.7


@dataclass(frozen=True)
class WordActionAlignment:
    """
    Measures alignment between user's stated WORDS and actual ACTIONS.

    This is the bridge that answers:
    "Are you LIVING what you SAID?"
    """

    user_uid: str

    # What user SAID (vision)
    vision_themes: tuple[str, ...] = field(default_factory=tuple)

    # What user DOES (derived from UserContext)
    action_themes: tuple[str, ...] = field(default_factory=tuple)

    # Alignment measurement
    alignment_score: float = 0.0
    matched_themes: tuple[str, ...] = field(default_factory=tuple)
    missing_in_actions: tuple[str, ...] = field(default_factory=tuple)
    unexpected_actions: tuple[str, ...] = field(default_factory=tuple)

    # Insights
    insights: tuple[str, ...] = field(default_factory=tuple)
    recommendations: tuple[str, ...] = field(default_factory=tuple)

    calculated_at: datetime = field(default_factory=datetime.now)

    @property
    def has_gap(self) -> bool:
        """Check if there's a meaningful gap between words and actions."""
        return self.alignment_score < 0.7

    @property
    def biggest_gap(self) -> str | None:
        """Get the most significant missing theme."""
        return self.missing_in_actions[0] if self.missing_in_actions else None

    def get_gap_summary(self) -> str:
        """Generate a human-readable summary of the word-action gap."""
        if not self.has_gap:
            return "Your actions align well with your stated vision!"

        if self.missing_in_actions:
            missing = ", ".join(self.missing_in_actions[:3])
            return f"Your vision mentions {missing}, but these aren't reflected in your activities."

        return "Some aspects of your vision could be better reflected in your daily activities."


@dataclass(frozen=True)
class VisionHistory:
    """Track changes in user's vision over time."""

    user_uid: str
    visions: tuple[VisionCapture, ...] = field(default_factory=tuple)

    @property
    def current_vision(self) -> VisionCapture | None:
        """Get the most recent vision."""
        return self.visions[-1] if self.visions else None

    @property
    def has_evolved(self) -> bool:
        """Check if vision has changed over time."""
        return len(self.visions) > 1

    def get_theme_evolution(self) -> dict[str, list[datetime]]:
        """Track when each theme appeared/disappeared."""
        evolution: dict[str, list[datetime]] = {}
        for vision in self.visions:
            for theme in vision.theme_keywords:
                if theme not in evolution:
                    evolution[theme] = []
                evolution[theme].append(vision.captured_at)
        return evolution
