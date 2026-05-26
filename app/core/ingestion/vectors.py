"""
Vector value object for directional change and trajectories.

Vectors represent direction + magnitude in conceptual spaces, useful for modeling
learning paths, goal progress, and life strategies. This module is pure (no Neo4j,
no driver) — the graph-backed operations live below the hexagonal boundary in
``adapters/persistence/neo4j/vector_operations.py`` (ADR-044).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


class VectorSpace(StrEnum):
    """Conceptual spaces where vectors operate."""

    LIFE_STRATEGY = "life-strategy"
    LEARNING = "learning"
    GOALS = "goals"
    HABITS = "habits"
    WELLBEING = "wellbeing"
    CAREER = "career"
    FINANCE = "finance"


@dataclass(frozen=True)
class Vector:
    """
    A vector in a conceptual space.

    Vectors can be:
    1. First-class nodes - Named trajectories that can be referenced
    2. Edge properties - Transitions between states
    """

    uid: str
    title: str
    space: VectorSpace
    components: dict[str, float]  # Named axes with magnitudes
    magnitude: float | None = None  # Computed or provided
    origin: str | None = None  # Starting state/node UID
    target: str | None = None  # Target state/node UID
    timeframe_start: date | None = None
    timeframe_end: date | None = None
    notes: str | None = None
    connections: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute magnitude if not provided."""
        if self.magnitude is None and self.components:
            # Calculate Euclidean magnitude
            sum_squares = sum(v**2 for v in self.components.values())
            object.__setattr__(self, "magnitude", sum_squares**0.5)

    def dot_product(self, other: Vector) -> float:
        """
        Calculate dot product with another vector.

        Useful for finding alignment between vectors.
        """
        if self.space != other.space:
            raise ValueError(
                f"Cannot compute dot product across different spaces: {self.space} vs {other.space}"
            )

        result = 0.0
        for axis, value in self.components.items():
            if axis in other.components:
                result += value * other.components[axis]
        return result

    def add(self, other: Vector) -> Vector:
        """
        Add two vectors to get resultant direction.

        Useful for combining multiple influences.
        """
        if self.space != other.space:
            raise ValueError(
                f"Cannot add vectors from different spaces: {self.space} vs {other.space}"
            )

        # Combine components
        combined = dict(self.components)
        for axis, value in other.components.items():
            combined[axis] = combined.get(axis, 0.0) + value

        return Vector(
            uid=f"{self.uid}+{other.uid}",
            title=f"{self.title} + {other.title}",
            space=self.space,
            components=combined,
            notes=f"Resultant of {self.uid} and {other.uid}",
        )

    def scale(self, factor: float) -> Vector:
        """Scale vector by a factor."""
        scaled_components = {k: v * factor for k, v in self.components.items()}

        return Vector(
            uid=f"{self.uid}*{factor}",
            title=f"{self.title} (scaled {factor}x)",
            space=self.space,
            components=scaled_components,
            notes=f"Scaled version of {self.uid}",
        )

    def normalize(self) -> Vector:
        """Create unit vector (magnitude = 1)."""
        if not self.magnitude or self.magnitude == 0:
            return self

        return self.scale(1.0 / self.magnitude)
