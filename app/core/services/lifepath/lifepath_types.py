"""
LifePath Service Types
======================

Frozen dataclasses used by LifePath services.

These are service-layer types (not stored entities):
- LifePathDesignation: View over Ku + ULTIMATE_PATH data
- VisionTheme, VisionCapture: Vision capture types
- LpRecommendation: LP recommendation type
- WordActionAlignment: Word-action gap analysis type (staged — see
  LifePathService.check_word_action_alignment)

Relocated from core/models/lifepath/ during Ku unification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.models.enums.lifepath_enums import ThemeCategory
from core.models.enums.principle_enums import AlignmentLevel
from core.models.type_hints import UserUID


@dataclass(frozen=True)
class LifePathDesignation:
    """
    LifePath bridges user's VISION (words) with ACTIONS (behavior).

    This is NOT a stored entity — it's computed from:
    1. User's vision statement (their own words, stored on User node)
    2. Designated LP (an ordinary LearningPath, identified by ULTIMATE_PATH)
    3. Alignment scores (stored on ULTIMATE_PATH relationship)
    4. UserContext (actual behavior tracked across all domains)

    Philosophy:
        "The user's vision is understood via the words user uses
        to communicate, the UserContext is determined via user's actions."
    """

    user_uid: UserUID

    # THE VISION (user's own words, stored on User node)
    vision_statement: str
    vision_themes: tuple[str, ...] = field(default_factory=tuple)
    vision_captured_at: datetime | None = None

    # THE DESIGNATION (carried by the ULTIMATE_PATH edge alone)
    life_path_uid: str | None = None
    designated_at: datetime | None = None

    # THE MEASUREMENT (vision -> action alignment, stored on ULTIMATE_PATH)
    # Per-dimension scores live on the ULTIMATE_PATH edge (written by
    # LifePathCoreService.update_alignment_score); only the overall score is
    # read back into this view. Fresh dimension breakdowns come from
    # LifePathAlignmentService.calculate_alignment.
    alignment_score: float = 0.0
    alignment_level: AlignmentLevel = AlignmentLevel.EXPLORING

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

    user_uid: UserUID
    vision_statement: str
    themes: tuple[VisionTheme, ...] = field(default_factory=tuple)
    captured_at: datetime = field(default_factory=datetime.now)

    llm_model: str | None = None
    processing_time_ms: int = 0

    @property
    def theme_keywords(self) -> list[str]:
        """Get just the theme keywords as a list."""
        return [t.theme for t in self.themes]


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


@dataclass(frozen=True)
class WordActionAlignment:
    """
    Measures alignment between user's stated WORDS and actual ACTIONS.

    This is the bridge that answers:
    "Are you LIVING what you SAID?"
    """

    user_uid: UserUID

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
