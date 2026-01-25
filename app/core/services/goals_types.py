"""
Goals Service Statistics Types
================================

Frozen dataclasses for goals service operation results.
Follows Pattern 3C: dict[str, Any] → frozen dataclasses

Pattern:
- Frozen (immutable after construction)
- Type-safe field access
- Self-documenting structure
- Follows user_stats_types.py pattern
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PathProgressData:
    """
    Progress data for a single learning path supporting a goal.

    Attributes:
        path: Learning path name
        support_score: How well this path supports the goal (0.0-1.0)
        progress: Progress through the path (0.0-1.0)
        completed_steps: Number of steps completed
        total_steps: Total number of steps in path
    """

    path: str
    support_score: float
    progress: float
    completed_steps: int
    total_steps: int


@dataclass(frozen=True)
class GoalLearningProgress:
    """
    Complete learning progress tracking for a goal.

    Tracks how goal progress relates to learning path advancement.

    Attributes:
        goal_uid: Goal UID
        goal_title: Goal title
        goal_progress: Current goal progress percentage
        learning_contribution: Learning contribution score (0.0-1.0)
        supporting_paths_progress: Progress data for supporting paths
        knowledge_advancement: List of knowledge advancements
        learning_milestones_achieved: List of achieved milestones
        next_learning_actions: Suggested next actions
    """

    goal_uid: str
    goal_title: str
    goal_progress: float
    learning_contribution: float
    supporting_paths_progress: list[PathProgressData] = field(default_factory=list)
    knowledge_advancement: list[Any] = field(default_factory=list)
    learning_milestones_achieved: list[Any] = field(default_factory=list)
    next_learning_actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GoalFeasibilityAssessment:
    """
    Feasibility assessment for a goal based on user context.

    Assesses whether a goal is achievable given:
    - Knowledge prerequisites
    - Habit support
    - Current workload

    Attributes:
        is_feasible: Whether the goal is feasible to pursue now
        confidence: Confidence score in the assessment (0.0-1.0)
        blockers: List of blocking factors
        enablers: List of enabling factors
        estimated_completion_date: Estimated completion date (if feasible)
    """

    is_feasible: bool
    confidence: float
    blockers: list[str] = field(default_factory=list)
    enablers: list[str] = field(default_factory=list)
    estimated_completion_date: date | None = None
