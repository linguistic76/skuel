"""
Curriculum Enums - Learning Path and Step Classification
=========================================================

Enums for learning path types and step difficulty levels.
"""

from __future__ import annotations

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


class PublicationState(StrEnum):
    """Whether authored curriculum content is finished enough to face an audience.

    Orthogonal to ``EntityStatus`` — which in this codebase means *lifecycle*
    (``DRAFT`` there is counted as OPEN by the MEGA-QUERY's
    ``open_ps_statuses``, i.e. "in progress", not "unpublished"). Reusing
    ``status`` for a publication gate would collide with that meaning, so the
    line gets its own field.

    Authored per-file in vault frontmatter (``publication_state: draft``), so a
    draft stays a draft when the file moves between folders — a directory name
    is not a status.

    ``PUBLISHED`` is the default and the tolerant reading: ingestion never
    writes absent frontmatter keys, so the entire pre-existing corpus carries
    no ``publication_state`` property at all and MUST keep reading as
    published. Every reader predicate is NULL-tolerant for that reason.
    """

    DRAFT = "draft"
    PUBLISHED = "published"

    def is_public(self) -> bool:
        """Whether content in this state may face a learner audience."""
        return self is PublicationState.PUBLISHED


class StepDifficulty(StrEnum):
    """Difficulty level of a path step."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"
    ADVANCED = "advanced"

    def sort_order(self) -> int:
        """Sort position for lists (TRIVIAL first = 0, ADVANCED last = 4)."""
        return _STEP_DIFFICULTY_SORT_ORDERS[self]

    @classmethod
    def from_value(cls, value: object) -> StepDifficulty:
        """Normalize enum/string inputs to a step difficulty, defaulting to MODERATE."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            for difficulty in cls:
                if difficulty.value == value_lower or difficulty.name.lower() == value_lower:
                    return difficulty
        return cls.MODERATE


_STEP_DIFFICULTY_SORT_ORDERS: dict[StepDifficulty, int] = {
    StepDifficulty.TRIVIAL: 0,
    StepDifficulty.EASY: 1,
    StepDifficulty.MODERATE: 2,
    StepDifficulty.CHALLENGING: 3,
    StepDifficulty.ADVANCED: 4,
}
