"""Enums for cross-domain relationship properties."""

from enum import StrEnum


class ProficiencyLevel(StrEnum):
    """Proficiency level for knowledge/skill relationships."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class KnowledgeRelevance(StrEnum):
    """How a principle or goal relates to a knowledge unit."""

    FUNDAMENTAL = "fundamental"
    SUPPORTING = "supporting"
    CONTEXTUAL = "contextual"
