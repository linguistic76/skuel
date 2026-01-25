"""
Vision Models - Core types for vision capture and word-action alignment.
========================================================================

These models support the vision capture flow:
1. User expresses vision in their own words
2. LLM extracts themes from the vision
3. System recommends Learning Paths based on themes
4. System measures alignment between stated vision and actual behavior

Philosophy:
    "The user's vision is understood via the words user uses to communicate,
    the UserContext is determined via user's actions."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ThemeCategory(str, Enum):
    """
    Categories for extracted vision themes.

    Maps to SKUEL's domain structure for LP recommendation.
    """

    PERSONAL_GROWTH = "personal_growth"  # Self-improvement, mindfulness
    CAREER = "career"  # Professional development, leadership
    HEALTH = "health"  # Physical and mental wellbeing
    RELATIONSHIPS = "relationships"  # Family, community, social
    FINANCIAL = "financial"  # Wealth, security, independence
    CREATIVE = "creative"  # Art, expression, innovation
    SPIRITUAL = "spiritual"  # Purpose, meaning, transcendence
    INTELLECTUAL = "intellectual"  # Knowledge, learning, mastery
    IMPACT = "impact"  # Contribution, legacy, making a difference
    LIFESTYLE = "lifestyle"  # Work-life balance, freedom, adventure


@dataclass(frozen=True)
class VisionTheme:
    """
    An extracted theme from user's vision statement.

    Themes are keywords/concepts extracted by LLM that represent
    core aspirations in the user's stated vision.
    """

    theme: str  # The theme keyword (e.g., "leadership", "mindfulness")
    category: ThemeCategory  # Category for LP matching
    confidence: float = 1.0  # LLM confidence in extraction (0.0-1.0)
    context: str | None = None  # Original phrase this was extracted from

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
    vision_statement: str  # Original user input
    themes: tuple[VisionTheme, ...] = field(default_factory=tuple)
    captured_at: datetime = field(default_factory=datetime.now)

    # LLM analysis metadata
    llm_model: str | None = None  # Model used for extraction
    processing_time_ms: int = 0  # Time taken for extraction

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
    match_score: float  # How well LP matches vision (0.0-1.0)
    matching_themes: tuple[str, ...] = field(default_factory=tuple)  # Which themes matched
    lp_domain: str | None = None  # LP's domain (TECH, HEALTH, etc.)

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

    Philosophy:
        - vision_themes: What user SAID they want
        - action_themes: What user's behavior SHOWS they prioritize
        - alignment_score: How well these match
    """

    user_uid: str

    # What user SAID (vision)
    vision_themes: tuple[str, ...] = field(default_factory=tuple)

    # What user DOES (derived from UserContext)
    action_themes: tuple[str, ...] = field(default_factory=tuple)

    # Alignment measurement
    alignment_score: float = 0.0  # 0.0-1.0 overall match
    matched_themes: tuple[str, ...] = field(default_factory=tuple)  # Themes present in both
    missing_in_actions: tuple[str, ...] = field(
        default_factory=tuple
    )  # Vision themes not in actions
    unexpected_actions: tuple[str, ...] = field(
        default_factory=tuple
    )  # Action themes not in vision

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
    """
    Track changes in user's vision over time.

    Visions can evolve - this tracks that journey.
    """

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
