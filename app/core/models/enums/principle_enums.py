"""
Principle Enums - Principle Classification and Alignment
=========================================================

Enums for principle categories, sources, strength levels,
and the unified alignment spectrum (principles + life path).
"""

from __future__ import annotations

from enum import Enum


class PrincipleCategory(str, Enum):
    """Life domain classification for principles."""

    SPIRITUAL = "spiritual"
    ETHICAL = "ethical"
    RELATIONAL = "relational"
    PERSONAL = "personal"
    PROFESSIONAL = "professional"
    INTELLECTUAL = "intellectual"
    HEALTH = "health"
    CREATIVE = "creative"


class PrincipleSource(str, Enum):
    """Origin/tradition of a principle."""

    PHILOSOPHICAL = "philosophical"
    RELIGIOUS = "religious"
    CULTURAL = "cultural"
    PERSONAL = "personal"
    SCIENTIFIC = "scientific"
    MENTOR = "mentor"
    LITERATURE = "literature"


class PrincipleStrength(str, Enum):
    """How deeply held/practiced a principle is."""

    CORE = "core"
    STRONG = "strong"
    MODERATE = "moderate"
    DEVELOPING = "developing"
    EXPLORING = "exploring"


class AlignmentLevel(str, Enum):
    """
    Alignment measurement for principles and life path.

    Unified spectrum from FLOURISHING (highest) to UNKNOWN (unassessed).

    Used by:
        Principles: current_alignment, alignment_history[].alignment_level
        Life Path: alignment_level (overall life direction alignment)
    """

    FLOURISHING = "flourishing"
    ALIGNED = "aligned"
    MOSTLY_ALIGNED = "mostly_aligned"
    EXPLORING = "exploring"
    PARTIAL = "partial"
    DRIFTING = "drifting"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"

    def to_score(self) -> float:
        """Convert alignment level to numeric score (0.0-1.0)."""
        return _ALIGNMENT_SCORES[self]

    @classmethod
    def from_score(cls, score: float) -> AlignmentLevel:
        """Derive alignment level from numeric score."""
        if score >= 0.9:
            return cls.FLOURISHING
        if score >= 0.75:
            return cls.ALIGNED
        if score >= 0.6:
            return cls.MOSTLY_ALIGNED
        if score >= 0.45:
            return cls.EXPLORING
        if score >= 0.3:
            return cls.PARTIAL
        if score >= 0.15:
            return cls.DRIFTING
        if score >= 0.0:
            return cls.MISALIGNED
        return cls.UNKNOWN


_ALIGNMENT_SCORES: dict[AlignmentLevel, float] = {
    AlignmentLevel.FLOURISHING: 1.0,
    AlignmentLevel.ALIGNED: 0.85,
    AlignmentLevel.MOSTLY_ALIGNED: 0.7,
    AlignmentLevel.EXPLORING: 0.5,
    AlignmentLevel.PARTIAL: 0.35,
    AlignmentLevel.DRIFTING: 0.2,
    AlignmentLevel.MISALIGNED: 0.1,
    AlignmentLevel.UNKNOWN: 0.0,
}
