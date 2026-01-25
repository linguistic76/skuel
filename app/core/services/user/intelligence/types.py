"""
Intelligence Data Types
========================

Data classes used by UserContextIntelligence for return types.

These are the structured outputs from intelligence methods:
- LifePathAlignment: Life path alignment analysis
- CrossDomainSynergy: Cross-domain synergy detection
- LearningStep: Learning step recommendation
- DailyWorkPlan: Daily work plan
- ScheduleAwareRecommendation: Schedule-aware recommendations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.context_types import (
        ContextualGoal,
        ContextualHabit,
        ContextualKnowledge,
        ContextualTask,
    )


@dataclass
class LifePathAlignment:
    """
    Comprehensive life path alignment analysis.

    **Philosophy:** "Everything flows toward the life path"

    This analysis measures how well a user's daily activities, knowledge,
    habits, goals, and principles align with their ultimate life path.

    **Alignment Dimensions:**
    1. Knowledge Alignment: Mastery of life path knowledge
    2. Activity Alignment: Tasks/habits supporting life path goals
    3. Goal Alignment: Active goals contributing to life path
    4. Principle Alignment: Values supporting life path direction
    5. Momentum: Recent activity trend toward life path

    **Score Scale:**
    - 0.0-0.3: Drifting (significant misalignment)
    - 0.4-0.6: Exploring (some alignment, room for growth)
    - 0.7-0.8: Aligned (actively living the path)
    - 0.9-1.0: Flourishing (fully integrated, embodied)
    """

    # Overall score
    overall_score: float  # 0.0-1.0
    alignment_level: str  # "drifting", "exploring", "aligned", "flourishing"

    # Dimension scores (0.0-1.0 each)
    knowledge_score: float  # Mastery of life path knowledge
    activity_score: float  # Tasks/habits supporting life path
    goal_score: float  # Goals contributing to life path
    principle_score: float  # Values supporting life path
    momentum_score: float  # Recent trend toward life path

    # Insights
    strengths: list[str]  # What's working well
    gaps: list[str]  # Where alignment is lacking
    recommendations: list[str]  # Actionable next steps

    # Supporting data
    life_path_uid: str | None
    life_path_milestones_completed: int
    life_path_milestones_total: int
    aligned_goals: list[str]  # Goal UIDs aligned with life path
    supporting_habits: list[str]  # Habit UIDs supporting life path
    knowledge_gaps: list[str]  # KU UIDs needing more application


@dataclass
class CrossDomainSynergy:
    """
    A detected synergy between entities across different domains.

    **Examples:**
    - Habit->Goal: "Morning meditation" supports "Mental clarity", "Reduce stress", "Better focus"
    - Task->Habit: "Write journal entry" builds "Daily journaling" habit
    - Knowledge->Task: "Python async programming" enables multiple coding tasks
    - Principle->Choice: "Growth mindset" informs career decisions

    **Synergy Score:**
    - 0.0-0.3: Weak synergy (single connection)
    - 0.4-0.6: Moderate synergy (multiple connections)
    - 0.7-1.0: Strong synergy (hub entity, high leverage)
    """

    source_uid: str  # The entity creating synergy
    source_domain: str  # "habit", "task", "knowledge", "principle"
    target_uids: list[str]  # Entities benefiting from this
    target_domain: str  # "goal", "habit", "task", "choice"
    synergy_type: str  # "supports", "enables", "builds", "informs"
    synergy_score: float  # 0.0-1.0 (higher = more leverage)
    rationale: str  # Human-readable explanation
    recommendations: list[str]  # Actionable suggestions


@dataclass
class LearningStep:
    """A recommended learning step with full context."""

    ku_uid: str
    title: str
    rationale: str
    prerequisites_met: bool
    aligns_with_goals: list[str]  # Goal UIDs this helps with
    unlocks_count: int  # How many items this unlocks
    estimated_time_minutes: int
    priority_score: float  # 0.0-1.0
    application_opportunities: dict[str, list[str]]  # Where can this be applied?


@dataclass
class DailyWorkPlan:
    """Comprehensive plan for what to work on today."""

    # Domain-specific items
    learning: list[str] = field(default_factory=list)  # KU UIDs to learn
    tasks: list[str] = field(default_factory=list)  # Task UIDs to complete
    habits: list[str] = field(default_factory=list)  # Habit UIDs to maintain
    events: list[str] = field(default_factory=list)  # Event UIDs to attend
    goals: list[str] = field(default_factory=list)  # Goal UIDs to advance
    choices: list[str] = field(default_factory=list)  # Choice UIDs to consider
    principles: list[str] = field(default_factory=list)  # Principle UIDs to embody

    # Contextual items (enriched with user context)
    contextual_tasks: list[ContextualTask] = field(default_factory=list)
    contextual_habits: list[ContextualHabit] = field(default_factory=list)
    contextual_goals: list[ContextualGoal] = field(default_factory=list)
    contextual_knowledge: list[ContextualKnowledge] = field(default_factory=list)

    # Plan metadata
    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0  # 0.0-1.0

    rationale: str = ""  # Why this plan?
    priorities: list[str] = field(default_factory=list)  # Ordered priority list
    warnings: list[str] = field(default_factory=list)  # Capacity warnings, conflicts


@dataclass
class ScheduleAwareRecommendation:
    """
    A recommendation that considers the user's schedule and capacity.

    **Phase 4 Addition:** Schedule-aware recommendations take into account:
    - Current events and scheduled activities
    - Energy levels and preferred times
    - Available time slots
    - Workload and capacity limits
    - Event conflicts and constraints

    **Recommendation Types:**
    - "learn": Knowledge unit to study
    - "task": Task to complete
    - "habit": Habit to maintain
    - "goal": Goal to advance
    - "rest": Rest recommendation (capacity exceeded)
    - "reschedule": Reschedule suggestion for conflicts
    """

    uid: str  # Entity UID (task_uid, ku_uid, habit_uid, etc.)
    entity_type: str  # "task", "habit", "goal", "knowledge", "event"
    recommendation_type: str  # "learn", "task", "habit", "goal", "rest", "reschedule"
    title: str  # Human-readable title
    rationale: str  # Why this is recommended NOW

    # Schedule context
    suggested_time_slot: str  # "morning", "afternoon", "evening", "now", "later"
    estimated_duration_minutes: int = 30
    fits_available_time: bool = True
    conflicts_with: list[str] = field(default_factory=list)  # Event UIDs that conflict

    # Scoring (why this is optimal for this time)
    schedule_fit_score: float = 0.0  # 0.0-1.0 (how well it fits schedule)
    energy_match_score: float = 0.0  # 0.0-1.0 (matches current energy)
    priority_score: float = 0.0  # 0.0-1.0 (urgency/importance)
    overall_score: float = 0.0  # Weighted combination

    # Context for decision making
    deadline: str | None = None  # Due date if applicable
    streak_at_risk: bool = False  # For habits: is streak at risk?
    blocks_other_work: bool = False  # Does completing this unblock others?
    life_path_aligned: bool = False  # Aligned with life path?

    # Actionable guidance
    preparation_needed: list[str] = field(default_factory=list)  # What to prepare
    alternatives: list[str] = field(default_factory=list)  # Alternative recommendations


__all__ = [
    "CrossDomainSynergy",
    "DailyWorkPlan",
    "LearningStep",
    "LifePathAlignment",
    "ScheduleAwareRecommendation",
]
