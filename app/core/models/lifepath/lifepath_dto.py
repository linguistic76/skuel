"""
LifePath DTO (Tier 2 - Transfer)
================================

Mutable data transfer objects for LifePath domain.
Used for inter-layer communication and database operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class LifePathDesignationDTO:
    """
    Mutable DTO for LifePathDesignation.

    Used for:
    - Database read/write operations
    - Service layer communication
    - Converting to/from domain model
    """

    user_uid: str
    vision_statement: str = ""
    vision_themes: list[str] = field(default_factory=list)
    vision_captured_at: datetime | None = None
    life_path_uid: str | None = None
    designated_at: datetime | None = None
    alignment_score: float = 0.0
    word_action_gap: float = 0.0
    alignment_level: str = "exploring"

    # Dimension scores
    knowledge_alignment: float = 0.0
    activity_alignment: float = 0.0
    goal_alignment: float = 0.0
    principle_alignment: float = 0.0
    momentum: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "user_uid": self.user_uid,
            "vision_statement": self.vision_statement,
            "vision_themes": self.vision_themes,
            "vision_captured_at": self.vision_captured_at.isoformat()
            if self.vision_captured_at
            else None,
            "life_path_uid": self.life_path_uid,
            "designated_at": self.designated_at.isoformat() if self.designated_at else None,
            "alignment_score": self.alignment_score,
            "word_action_gap": self.word_action_gap,
            "alignment_level": self.alignment_level,
            "knowledge_alignment": self.knowledge_alignment,
            "activity_alignment": self.activity_alignment,
            "goal_alignment": self.goal_alignment,
            "principle_alignment": self.principle_alignment,
            "momentum": self.momentum,
        }


@dataclass
class VisionCaptureDTO:
    """Mutable DTO for VisionCapture."""

    user_uid: str
    vision_statement: str
    themes: list[dict] = field(default_factory=list)  # List of theme dicts
    captured_at: datetime | None = None
    llm_model: str | None = None
    processing_time_ms: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "user_uid": self.user_uid,
            "vision_statement": self.vision_statement,
            "themes": self.themes,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "llm_model": self.llm_model,
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass
class WordActionAlignmentDTO:
    """Mutable DTO for WordActionAlignment."""

    user_uid: str
    vision_themes: list[str] = field(default_factory=list)
    action_themes: list[str] = field(default_factory=list)
    alignment_score: float = 0.0
    matched_themes: list[str] = field(default_factory=list)
    missing_in_actions: list[str] = field(default_factory=list)
    unexpected_actions: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    calculated_at: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "user_uid": self.user_uid,
            "vision_themes": self.vision_themes,
            "action_themes": self.action_themes,
            "alignment_score": self.alignment_score,
            "matched_themes": self.matched_themes,
            "missing_in_actions": self.missing_in_actions,
            "unexpected_actions": self.unexpected_actions,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
        }
