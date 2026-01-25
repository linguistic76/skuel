"""
Calendar Optimization Strategy Types (Pattern 3C Migration)
=============================================================

TypedDict definitions for calendar optimization strategy returns.
Replaces dict[str, Any] with strongly-typed structures for internal strategies.

Pattern 3C Phase 2: Internal Analytics Types (Calendar Strategies)
"""

from typing import Any, TypedDict


class CognitiveBalancedStrategy(TypedDict):
    """Result of cognitive load balancing strategy."""

    strategy: str  # "cognitive_balanced"
    schedule: dict[str, Any]  # task_uid -> slot assignment with cognitive_load and match_score
    utilization: float  # Slot utilization ratio (0.0-1.0)
    average_match_score: float  # Average cognitive capacity match score


class EnergyAlignedStrategy(TypedDict):
    """Result of energy-aligned scheduling strategy."""

    strategy: str  # "energy_aligned"
    schedule: dict[str, Any]  # task_uid -> slot assignment with energy_match
    energy_efficiency: float  # Energy match efficiency (0.0-1.0)


class KnowledgeFocusedStrategy(TypedDict):
    """Result of knowledge-focused scheduling strategy."""

    strategy: str  # "knowledge_focused"
    schedule: dict[
        str, Any
    ]  # task_uid -> slot assignment with learning_effectiveness and task_type
    learning_optimization: float  # Average learning effectiveness score


class DeadlineDrivenStrategy(TypedDict):
    """Result of deadline-driven scheduling strategy."""

    strategy: str  # "deadline_driven"
    schedule: dict[str, Any]  # task_uid -> slot assignment with urgency_rank and productivity_score
    deadline_coverage: float  # Percentage of tasks with deadlines covered


class SpacedRepetitionStrategy(TypedDict):
    """Result of spaced repetition optimization strategy."""

    strategy: str  # "spaced_repetition"
    schedule: dict[str, Any]  # task_uid -> slot assignment with spacing_interval and task_type
    spacing_quality: float  # Quality of spacing distribution


class HourLoadInfo(TypedDict):
    """Load information for a specific hour category."""

    max_load: float  # Maximum cognitive load for this hour category
    recommended_tasks: int  # Recommended number of tasks


class OptimalLoadDistribution(TypedDict):
    """Optimal cognitive load distribution across hour categories."""

    peak_hours: HourLoadInfo
    high_hours: HourLoadInfo
    medium_hours: HourLoadInfo
    low_hours: HourLoadInfo
    total_capacity: float  # Total daily cognitive capacity
    utilization_target: float  # Target utilization (0.0-1.0)
