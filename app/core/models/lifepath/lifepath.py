"""
LifePath Domain Model (Tier 3 - Core)
=====================================

Immutable domain model for LifePath - Domain #14: The Destination.

LifePath bridges the gap between:
- User's VISION (expressed in their own words)
- User's ACTIONS (tracked via UserContext)

Philosophy:
    "The user's vision is understood via the words user uses to communicate,
    the UserContext is determined via user's actions."

LifePath is NOT a stored entity - it's a DESIGNATION that elevates a
Learning Path (LP) to life path status, combined with the user's vision statement.

Three-tier position:
- External: lifepath_request.py (Pydantic validation)
- Transfer: lifepath_dto.py (mutable DTOs)
- Core: lifepath.py (this file, frozen domain model)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AlignmentLevel(str, Enum):
    """
    Overall life path alignment classification.

    Based on the gap between declared vision and actual behavior.
    """

    FLOURISHING = "flourishing"  # 0.9+ - Life purpose deeply integrated
    ALIGNED = "aligned"  # 0.7-0.9 - Consistent alignment with life path
    EXPLORING = "exploring"  # 0.4-0.7 - Making progress, some drift
    DRIFTING = "drifting"  # <0.4 - Significant misalignment

    @classmethod
    def from_score(cls, score: float) -> AlignmentLevel:
        """Convert alignment score to level."""
        if score >= 0.9:
            return cls.FLOURISHING
        elif score >= 0.7:
            return cls.ALIGNED
        elif score >= 0.4:
            return cls.EXPLORING
        else:
            return cls.DRIFTING

    def get_description(self) -> str:
        """Human-readable description of the alignment level."""
        descriptions = {
            self.FLOURISHING: "Your actions deeply reflect your stated vision",
            self.ALIGNED: "You're consistently living your declared path",
            self.EXPLORING: "Making progress, but some areas need attention",
            self.DRIFTING: "Your actions may not match your stated vision",
        }
        return descriptions.get(self, "Unknown alignment level")


@dataclass(frozen=True)
class LifePathDesignation:
    """
    LifePath bridges user's VISION (words) with ACTIONS (behavior).

    This is NOT a stored entity - it's computed from:
    1. User's vision statement (their own words)
    2. Designated LP (the learning path that embodies that vision)
    3. UserContext (actual behavior tracked across all domains)

    Philosophy:
        "The user's vision is understood via the words user uses
        to communicate, the UserContext is determined via user's actions."

    Attributes:
        user_uid: The user this designation belongs to
        vision_statement: User's expressed vision in their own words
        vision_themes: Extracted themes from the vision statement
        vision_captured_at: When the vision was captured
        life_path_uid: Points to the designated LP (None if not yet matched)
        designated_at: When the LP was designated as life path
        alignment_score: Overall alignment (0.0-1.0)
        word_action_gap: How far actions drift from stated vision
        alignment_level: Classification of overall alignment
    """

    user_uid: str

    # THE VISION (user's own words)
    vision_statement: str
    vision_themes: tuple[str, ...] = field(default_factory=tuple)
    vision_captured_at: datetime | None = None

    # THE DESIGNATION (LP that embodies vision)
    life_path_uid: str | None = None
    designated_at: datetime | None = None

    # THE MEASUREMENT (vision -> action alignment)
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
        # Frozen dataclasses require object.__setattr__ for dynamic defaults
        if self.vision_captured_at is None:
            object.__setattr__(self, "vision_captured_at", datetime.now())

        # Compute alignment level from score
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
