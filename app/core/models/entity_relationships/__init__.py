"""
Relationship Models - Making Entity Connections Comprehensible
==============================================================

These models capture the reasoning behind entity relationships in SKUEL.

Instead of storing just UIDs (goal links to principle X), we store:
- HOW the principle guides the goal (manifestation)
- WHY a choice created a goal (reasoning)

This makes invisible connections visible and queryable.

Key Models:
-----------
- Guidance: How a principle guides an entity (goal/habit/choice)
- Derivation: Why a choice created an entity (goal/habit)

Philosophy:
-----------
Relationships have context. When a user links a principle to a goal,
they have reasoning: "This principle guides me by limiting daily work to 4 hours."

Capturing this reasoning makes the system comprehensible and educational.
"""

from .derivation import Derivation
from .guidance import Guidance

__all__ = [
    "Derivation",
    "Guidance",
]
