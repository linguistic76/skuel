"""
Curriculum Enums - Learning Path and Step Classification
=========================================================

Enums for learning path types and step difficulty levels.
"""

from enum import Enum


class LpType(str, Enum):
    """
    Type of Learning Path.

    Determines path behavior: adaptive vs. fixed, exploratory vs. directed.
    """

    STRUCTURED = "structured"
    ADAPTIVE = "adaptive"
    EXPLORATORY = "exploratory"
    REMEDIAL = "remedial"
    ACCELERATED = "accelerated"


class StepDifficulty(str, Enum):
    """Difficulty level of a learning step."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"
    ADVANCED = "advanced"
