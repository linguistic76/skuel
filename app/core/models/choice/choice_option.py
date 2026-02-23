"""
ChoiceOption — Decision Alternative
=====================================

A single option in a Choice. Options are evaluated on multiple
dimensions for decision-making.

Stored as a tuple on the Choice: `options: tuple[ChoiceOption, ...]`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChoiceOption:
    """
    A single option in a Choice.

    Fields:
        uid: Unique identifier within the choice
        title: Short option name
        description: Detailed description
        feasibility_score: How feasible (0.0-1.0)
        risk_level: Risk level (0.0-1.0)
        potential_impact: Expected impact (0.0-1.0)
        resource_requirement: Resources needed (0.0-1.0)
        estimated_duration: Expected duration in minutes (optional)
        dependencies: UIDs of entities this option depends on
        tags: Classification tags
    """

    uid: str
    title: str
    description: str = ""
    feasibility_score: float = 0.5
    risk_level: float = 0.5
    potential_impact: float = 0.5
    resource_requirement: float = 0.5
    estimated_duration: int | None = None
    dependencies: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
