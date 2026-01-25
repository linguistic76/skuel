"""
Path-Aware Result Types for Cross-Domain Graph Intelligence

Core Principle: "Path metadata shows HOW entities are connected"

These types add graph intelligence to domain models by including:
- distance: Number of hops from source entity
- path_strength: Confidence cascade (average of all relationship confidences in path)
- via_relationships: Sequence of relationship types that form the connection

Created: 2025-11-15 (Phase 1 of Graph Intelligence Enhancement)
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class PathAwareTask:
    """
    Task with path metadata showing HOW it's connected to source entity.

    Example:
        Goal → Task (direct FULFILLS_GOAL, distance=1, strength=0.95)
        Goal → Principle → Task (indirect, distance=2, strength=0.82)
    """

    uid: str
    title: str
    distance: int  # Hops from source entity
    path_strength: float  # Confidence cascade (0-1)
    via_relationships: list[str]  # Path composition
    # Core task fields
    status: str | None = None
    priority: str | None = None
    due_date: date | None = None


@dataclass(frozen=True)
class PathAwareGoal:
    """
    Goal with path metadata showing HOW it's connected to source entity.

    Example:
        Choice → Goal (direct SUPPORTS_GOAL, distance=1, strength=0.90)
        Choice → Principle → Goal (indirect INFORMED_BY→GUIDES, distance=2, strength=0.78)
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core goal fields
    status: str | None = None
    target_date: date | None = None
    progress: float | None = None


@dataclass(frozen=True)
class PathAwarePrinciple:
    """
    Principle with path metadata showing HOW it informs/guides source entity.

    Example:
        Choice → Principle (direct INFORMED_BY, distance=1, strength=0.93)
        Goal → Choice → Principle (indirect, distance=2, strength=0.81)
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core principle fields
    description: str | None = None


@dataclass(frozen=True)
class PathAwareKnowledge:
    """
    Knowledge unit with path metadata showing HOW it relates to source entity.

    Example:
        Task → KnowledgeUnit (direct APPLIES_KNOWLEDGE, distance=1, strength=0.88)
        Task → KU1 → KU2 (prerequisite chain, distance=2, strength=0.75)
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core knowledge fields
    domain: str | None = None
    mastery_level: float | None = None


@dataclass(frozen=True)
class PathAwareHabit:
    """
    Habit with path metadata showing HOW it connects to source entity.

    Example:
        Goal → Habit (direct SUPPORTS_GOAL, distance=1, strength=0.91)
        Goal → Principle → Habit (indirect GUIDES→ALIGNED_WITH, distance=2, strength=0.79)
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core habit fields
    frequency: str | None = None
    current_streak: int | None = None


@dataclass(frozen=True)
class PathAwareEvent:
    """
    Event with path metadata showing HOW it connects to source entity.

    Example:
        Goal → Event (direct SUPPORTS_GOAL, distance=1, strength=0.87)
        Habit → Event (direct REINFORCES_HABIT, distance=1, strength=0.92)
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core event fields
    event_date: datetime | None = None
    event_type: str | None = None


@dataclass(frozen=True)
class PathAwareChoice:
    """
    Choice with path metadata showing HOW it connects to source entity.

    Example:
        Principle → Choice (direct INFORMS, distance=1, strength=0.89)
        Goal → Choice (direct INSPIRED_BY, distance=1, strength=0.86)
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core choice fields
    decision_date: date | None = None
    resolution: str | None = None


# Domain-Specific Context Types (Grouped by Relationship Semantic)


@dataclass(frozen=True)
class ChoiceCrossContext:
    """
    Choice decision-making context with path-aware intelligence.

    Groups related entities by relationship semantic meaning:
    - principles: What informs this choice (INFORMED_BY_PRINCIPLE)
    - supporting_goals: What this choice supports (SUPPORTS_GOAL)
    - conflicting_goals: What this choice conflicts with (CONFLICTS_WITH_GOAL)
    - knowledge: What knowledge this choice requires (REQUIRES_KNOWLEDGE)

    Each entity includes path metadata (distance, strength, path composition).
    """

    choice_uid: str
    principles: list[PathAwarePrinciple]
    supporting_goals: list[PathAwareGoal]
    conflicting_goals: list[PathAwareGoal]
    knowledge: list[PathAwareKnowledge]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return (
            len(self.principles)
            + len(self.supporting_goals)
            + len(self.conflicting_goals)
            + len(self.knowledge)
        )

    def strong_connections(self, threshold: float = 0.8) -> int:
        """Count of high-confidence connections (path_strength >= threshold)."""
        all_entities: list[PathAwarePrinciple | PathAwareGoal | PathAwareKnowledge] = [
            *self.principles,
            *self.supporting_goals,
            *self.conflicting_goals,
            *self.knowledge,
        ]
        return sum(1 for e in all_entities if e.path_strength >= threshold)

    def avg_strength(self) -> float:
        """Average path strength across all connections."""
        all_entities: list[PathAwarePrinciple | PathAwareGoal | PathAwareKnowledge] = [
            *self.principles,
            *self.supporting_goals,
            *self.conflicting_goals,
            *self.knowledge,
        ]
        if not all_entities:
            return 0.0
        return sum(e.path_strength for e in all_entities) / len(all_entities)

    @property
    def all_goals(self) -> list[PathAwareGoal]:
        """All goals (supporting + conflicting)."""
        return self.supporting_goals + self.conflicting_goals

    @property
    def direct_goals(self) -> list[PathAwareGoal]:
        """Direct goal connections (distance=1)."""
        return [g for g in self.all_goals if g.distance == 1]

    @property
    def direct_principles(self) -> list[PathAwarePrinciple]:
        """Direct principle connections (distance=1)."""
        return [p for p in self.principles if p.distance == 1]


@dataclass(frozen=True)
class GoalCrossContext:
    """
    Goal achievement context with path-aware intelligence.

    Groups related entities by relationship semantic:
    - tasks: Tasks fulfilling this goal (FULFILLS_GOAL)
    - habits: Habits supporting this goal (SUPPORTS_GOAL)
    - knowledge: Knowledge required for this goal (REQUIRES_KNOWLEDGE)
    - subgoals: Child goals (SUBGOAL_OF)
    - parent_goal: Parent goal if this is a subgoal (SUBGOAL_OF)
    - principles: Principles guiding this goal (GUIDED_BY_PRINCIPLE)
    """

    goal_uid: str
    tasks: list[PathAwareTask]
    habits: list[PathAwareHabit]
    knowledge: list[PathAwareKnowledge]
    subgoals: list[PathAwareGoal]
    parent_goal: PathAwareGoal | None
    principles: list[PathAwarePrinciple]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return (
            len(self.tasks)
            + len(self.habits)
            + len(self.knowledge)
            + len(self.subgoals)
            + (1 if self.parent_goal else 0)
            + len(self.principles)
        )


@dataclass(frozen=True)
class PrincipleCrossContext:
    """
    Principle influence context with path-aware intelligence.

    Groups related entities by relationship semantic:
    - goals: Goals guided by this principle (GUIDED_BY_PRINCIPLE)
    - choices: Choices informed by this principle (INFORMED_BY_PRINCIPLE)
    - knowledge: Knowledge grounding this principle (GROUNDED_IN_KNOWLEDGE)
    - habits: Habits aligned with this principle (ALIGNED_WITH_PRINCIPLE)
    """

    principle_uid: str
    goals: list[PathAwareGoal]
    choices: list[PathAwareChoice]
    knowledge: list[PathAwareKnowledge]
    habits: list[PathAwareHabit]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return len(self.goals) + len(self.choices) + len(self.knowledge) + len(self.habits)


@dataclass(frozen=True)
class TaskCrossContext:
    """
    Task execution context with path-aware intelligence.

    Groups related entities by relationship semantic:
    - prerequisites: Tasks that must be completed first (DEPENDS_ON)
    - dependents: Tasks that depend on this one (DEPENDS_ON reversed)
    - required_knowledge: Knowledge needed to complete task (REQUIRES_KNOWLEDGE)
    - applied_knowledge: Knowledge this task applies (APPLIES_KNOWLEDGE)
    - contributing_goals: Goals this task fulfills (FULFILLS_GOAL)
    """

    task_uid: str
    prerequisites: list[PathAwareTask]
    dependents: list[PathAwareTask]
    required_knowledge: list[PathAwareKnowledge]
    applied_knowledge: list[PathAwareKnowledge]
    contributing_goals: list[PathAwareGoal]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return (
            len(self.prerequisites)
            + len(self.dependents)
            + len(self.required_knowledge)
            + len(self.applied_knowledge)
            + len(self.contributing_goals)
        )


@dataclass(frozen=True)
class HabitCrossContext:
    """
    Habit sustainability context with path-aware intelligence.

    Groups related entities by relationship semantic:
    - goals: Goals this habit supports (SUPPORTS_GOAL)
    - knowledge: Knowledge this habit practices/develops (PRACTICES_KNOWLEDGE, DEVELOPS_SKILL)
    - principles: Principles this habit aligns with (ALIGNED_WITH_PRINCIPLE)
    - prerequisites: Habits required before this one (REQUIRES_PREREQUISITE)
    """

    habit_uid: str
    goals: list[PathAwareGoal]
    knowledge: list[PathAwareKnowledge]
    principles: list[PathAwarePrinciple]
    prerequisites: list[PathAwareHabit]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return (
            len(self.goals) + len(self.knowledge) + len(self.principles) + len(self.prerequisites)
        )


@dataclass(frozen=True)
class EventCrossContext:
    """
    Event context with path-aware intelligence.

    Groups related entities by relationship semantic:
    - goals: Goals this event supports (SUPPORTS_GOAL)
    - habits: Habits this event reinforces (REINFORCES_HABIT)
    - knowledge: Knowledge this event practices (REINFORCES_KNOWLEDGE)
    """

    event_uid: str
    goals: list[PathAwareGoal]
    habits: list[PathAwareHabit]
    knowledge: list[PathAwareKnowledge]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return len(self.goals) + len(self.habits) + len(self.knowledge)


# Helper Functions for Path Analysis


def calculate_avg_path_strength(entities: list) -> float:
    """
    Calculate average path strength across multiple entities.

    Args:
        entities: List of path-aware entities (any type with path_strength attribute)

    Returns:
        Average path strength (0-1), or 0.0 if no entities
    """
    if not entities:
        return 0.0
    return sum(e.path_strength for e in entities) / len(entities)


def filter_by_strength(entities: list, min_strength: float = 0.7) -> list:
    """
    Filter entities by minimum path strength (confidence threshold).

    Args:
        entities: List of path-aware entities
        min_strength: Minimum path_strength (default 0.7 = 70% confidence)

    Returns:
        Filtered list of entities with path_strength >= min_strength
    """
    return [e for e in entities if e.path_strength >= min_strength]


def filter_by_distance(entities: list, max_distance: int = 2) -> list:
    """
    Filter entities by maximum distance (relationship hops).

    Args:
        entities: List of path-aware entities
        max_distance: Maximum hops from source (default 2)

    Returns:
        Filtered list of entities within max_distance hops
    """
    return [e for e in entities if e.distance <= max_distance]


def get_direct_connections(entities: list) -> list:
    """
    Get only direct (1-hop) connections.

    Args:
        entities: List of path-aware entities

    Returns:
        Filtered list of entities with distance == 1
    """
    return filter_by_distance(entities, max_distance=1)
