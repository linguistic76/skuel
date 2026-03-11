"""
Curriculum Enums - Learning Path and Step Classification
=========================================================

Enums for learning path types and step difficulty levels.
"""

from enum import StrEnum


class LpType(StrEnum):
    """
    Type of Learning Path.

    Determines path behavior: adaptive vs. fixed, exploratory vs. directed.
    """

    STRUCTURED = "structured"
    ADAPTIVE = "adaptive"
    EXPLORATORY = "exploratory"
    REMEDIAL = "remedial"
    ACCELERATED = "accelerated"


class StepDifficulty(StrEnum):
    """Difficulty level of a learning step."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"
    ADVANCED = "advanced"
