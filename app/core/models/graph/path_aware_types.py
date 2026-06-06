"""
Path-Aware Result Types for Cross-Domain Graph Intelligence

Core Principle: "Path metadata shows HOW entities are connected"

These types add graph intelligence to domain models by including:
- distance: Number of hops from source entity
- path_strength: Confidence cascade (average of all relationship confidences in path)
- via_relationships: Sequence of relationship types that form the connection

Created: 2025-11-15
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, TypeVar


class PathAwareProtocol(Protocol):
    """Structural protocol for all path-aware entity types."""

    @property
    def distance(self) -> int: ...
    @property
    def path_strength(self) -> float: ...


P = TypeVar("P", bound=PathAwareProtocol)


def _path_rank(entity: dict[str, Any]) -> tuple[float, float]:
    """Sort key for picking the strongest path to a node: lowest distance wins, then
    highest path_strength. Missing/None metadata sorts worst (a real measured path always
    beats an unmeasured one)."""
    distance = entity.get("distance")
    strength = entity.get("path_strength")
    return (
        float(distance) if distance is not None else float("inf"),
        -(float(strength) if strength is not None else 0.0),
    )


def _union_path_buckets(categorized: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    """Collect cross-domain-context bucket dicts across keys, one entry per uid (the
    strongest path).

    The config-driven cross-domain-context reader emits one bucket per
    ``context_field_name``, each a list of
    ``{"uid", "title", "distance", "path_strength", "via_relationships"}`` dicts.

    De-dup by uid serves two purposes:
    1. A single typed field may aggregate several buckets (e.g. a choice's informing
       principles span both INFORMED_BY_PRINCIPLE outgoing and GUIDES_CHOICE incoming).
    2. Even within ONE bucket the same node can recur: the producer Cypher does
       ``collect(DISTINCT {uid, distance, path_strength, ...})`` — DISTINCT over the whole
       path-metadata map, not the uid — so at ``depth>=2`` a node reachable via multiple
       distinct paths appears once per path. Without this de-dup, downstream counts,
       impact score and cascade impact would all inflate.

    When a uid recurs, the **strongest** path is kept (lowest distance, then highest
    path_strength via ``_path_rank``), NOT the first raw occurrence — the producer query
    has no ``ORDER BY``, so first-seen could be the weaker/indirect path. Order-preserving
    by first-seen uid.

    Pass one ``_union_path_buckets`` call per target field; per-field scoping is intentional
    (a uid shared across two different target fields is NOT a duplicate).
    """
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for key in keys:
        for entity in categorized.get(key) or []:
            if not isinstance(entity, dict):
                continue
            uid = entity.get("uid")
            if not uid:
                continue
            incumbent = best.get(uid)
            if incumbent is None:
                best[uid] = entity
                order.append(uid)
            elif _path_rank(entity) < _path_rank(incumbent):
                best[uid] = entity
    return [best[uid] for uid in order]


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwareGoal":
        """Build from a cross-domain-context bucket entry (uid/title/path metadata)."""
        return cls(
            uid=d["uid"],
            title=d.get("title", ""),
            distance=d["distance"],
            path_strength=d["path_strength"],
            via_relationships=d.get("via_relationships", []),
        )


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwarePrinciple":
        """Build from a cross-domain-context bucket entry (uid/title/path metadata)."""
        return cls(
            uid=d["uid"],
            title=d.get("title", ""),
            distance=d["distance"],
            path_strength=d["path_strength"],
            via_relationships=d.get("via_relationships", []),
        )


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwareKnowledge":
        """Build from a cross-domain-context bucket entry (uid/title/path metadata)."""
        return cls(
            uid=d["uid"],
            title=d.get("title", ""),
            distance=d["distance"],
            path_strength=d["path_strength"],
            via_relationships=d.get("via_relationships", []),
        )


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwareHabit":
        """Build from a cross-domain-context bucket entry (uid/title/path metadata)."""
        return cls(
            uid=d["uid"],
            title=d.get("title", ""),
            distance=d["distance"],
            path_strength=d["path_strength"],
            via_relationships=d.get("via_relationships", []),
        )


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
    - principles: What informs/guides this choice (INFORMED_BY_PRINCIPLE outgoing +
      GUIDES_CHOICE incoming)
    - supporting_goals: Goals this choice affects (AFFECTS_GOAL — polarity-free)
    - conflicting_goals: Always empty. There is NO conflicting-goal edge; the choice↔goal
      link is the single polarity-free AFFECTS_GOAL. Kept as a field (not dropped) to
      avoid cascading a model change; populate only alongside a real edge nobody writes
      yet.
    - knowledge: Knowledge informing the decision (INFORMED_BY_KNOWLEDGE)

    Each entity includes path metadata (distance, strength, path composition).
    """

    choice_uid: str
    principles: list[PathAwarePrinciple]
    supporting_goals: list[PathAwareGoal]
    conflicting_goals: list[PathAwareGoal]
    knowledge: list[PathAwareKnowledge]

    @classmethod
    def from_categorized(
        cls, source_uid: str, categorized_data: dict[str, Any]
    ) -> "ChoiceCrossContext":
        """Build the path-aware choice context from a ``get_cross_domain_context_typed``
        categorized payload (the CHOICES_CONFIG ``context_field_name`` buckets).

        This is the per-domain seam the generic factory delegates to: it SELECTs the
        choice-relevant buckets, RENAMEs them to the dataclass fields, UNIONs the two
        principle directions, and DEDUPs each field to its strongest path. One union call
        per target field (per-field scoping is intentional).

        - ``supporting_goals`` ← AFFECTS_GOAL (``affected_goals``); the edge is
          polarity-free (#214), so there is no conflicting-goal bucket — ``conflicting_goals``
          stays empty rather than reading a bucket nothing emits.
        - ``principles`` ← the union of INFORMED_BY_PRINCIPLE (outgoing,
          ``aligned_principles``) and GUIDES_CHOICE (incoming, ``guiding_principles``).
        - ``knowledge`` ← INFORMED_BY_KNOWLEDGE (``informed_by_knowledge``).
        """
        return cls(
            choice_uid=source_uid,
            principles=[
                PathAwarePrinciple.from_dict(p)
                for p in _union_path_buckets(
                    categorized_data, "aligned_principles", "guiding_principles"
                )
            ],
            supporting_goals=[
                PathAwareGoal.from_dict(g)
                for g in _union_path_buckets(categorized_data, "affected_goals")
            ],
            conflicting_goals=[],
            knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "informed_by_knowledge")
            ],
        )

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
    - goals: Goals this habit supports (SUPPORTS_GOAL → ``supported_goals``)
    - knowledge: Knowledge this habit reinforces (REINFORCES_KNOWLEDGE →
      ``reinforced_knowledge``)
    - principles: Principles this habit aligns with — union of EMBODIES_PRINCIPLE
      (outgoing, ``embodied_principles``) and INSPIRES_HABIT (incoming,
      ``inspiring_principles``)
    - prerequisites: Habits required before this one (REQUIRES_PREREQUISITE →
      ``prerequisite_habits``)

    Each entity includes path metadata (distance, strength, path composition).
    """

    habit_uid: str
    goals: list[PathAwareGoal]
    knowledge: list[PathAwareKnowledge]
    principles: list[PathAwarePrinciple]
    prerequisites: list[PathAwareHabit]

    @classmethod
    def from_categorized(
        cls, source_uid: str, categorized_data: dict[str, Any]
    ) -> "HabitCrossContext":
        """Build the path-aware habit context from a ``get_cross_domain_context_typed``
        categorized payload (the HABITS_CONFIG ``context_field_name`` buckets).

        This is the per-domain seam the generic factory delegates to: it SELECTs the
        habit-relevant buckets, RENAMEs them to the dataclass fields, UNIONs the two
        principle directions, and DEDUPs each field to its strongest path. One union call
        per target field (per-field scoping is intentional).

        - ``goals`` ← SUPPORTS_GOAL (``supported_goals``).
        - ``knowledge`` ← REINFORCES_KNOWLEDGE (``reinforced_knowledge``).
        - ``principles`` ← the union of EMBODIES_PRINCIPLE (outgoing,
          ``embodied_principles``) and INSPIRES_HABIT (incoming, ``inspiring_principles``),
          mirroring the symmetric aggregation on the UID-family
          ``HabitCrossContext.aligned_principle_uids``.
        - ``prerequisites`` ← REQUIRES_PREREQUISITE (``prerequisite_habits``).
        """
        return cls(
            habit_uid=source_uid,
            goals=[
                PathAwareGoal.from_dict(g)
                for g in _union_path_buckets(categorized_data, "supported_goals")
            ],
            knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "reinforced_knowledge")
            ],
            principles=[
                PathAwarePrinciple.from_dict(p)
                for p in _union_path_buckets(
                    categorized_data, "embodied_principles", "inspiring_principles"
                )
            ],
            prerequisites=[
                PathAwareHabit.from_dict(h)
                for h in _union_path_buckets(categorized_data, "prerequisite_habits")
            ],
        )

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return (
            len(self.goals) + len(self.knowledge) + len(self.principles) + len(self.prerequisites)
        )

    def _all_entities(
        self,
    ) -> list[PathAwareGoal | PathAwareKnowledge | PathAwarePrinciple | PathAwareHabit]:
        """All connected path-aware entities across every field."""
        return [*self.goals, *self.knowledge, *self.principles, *self.prerequisites]

    def strong_connections(self, threshold: float = 0.8) -> int:
        """Count of high-confidence connections (path_strength >= threshold)."""
        return sum(1 for e in self._all_entities() if e.path_strength >= threshold)

    def avg_strength(self) -> float:
        """Average path strength across all connections."""
        all_entities = self._all_entities()
        if not all_entities:
            return 0.0
        return sum(e.path_strength for e in all_entities) / len(all_entities)

    @property
    def direct_goals(self) -> list[PathAwareGoal]:
        """Direct goal connections (distance=1)."""
        return [g for g in self.goals if g.distance == 1]

    @property
    def direct_principles(self) -> list[PathAwarePrinciple]:
        """Direct principle connections (distance=1)."""
        return [p for p in self.principles if p.distance == 1]

    @property
    def direct_knowledge(self) -> list[PathAwareKnowledge]:
        """Direct knowledge connections (distance=1)."""
        return [k for k in self.knowledge if k.distance == 1]

    @property
    def direct_prerequisites(self) -> list[PathAwareHabit]:
        """Direct prerequisite-habit connections (distance=1)."""
        return [h for h in self.prerequisites if h.distance == 1]

    @property
    def max_path_depth(self) -> int:
        """Deepest hop across all connections (0 when there are none)."""
        return max((e.distance for e in self._all_entities()), default=0)


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


def calculate_avg_path_strength(entities: list[PathAwareProtocol]) -> float:
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


def filter_by_strength(entities: list[P], min_strength: float = 0.7) -> list[P]:
    """
    Filter entities by minimum path strength (confidence threshold).

    Args:
        entities: List of path-aware entities
        min_strength: Minimum path_strength (default 0.7 = 70% confidence)

    Returns:
        Filtered list of entities with path_strength >= min_strength
    """
    return [e for e in entities if e.path_strength >= min_strength]


def filter_by_distance(entities: list[P], max_distance: int = 2) -> list[P]:
    """
    Filter entities by maximum distance (relationship hops).

    Args:
        entities: List of path-aware entities
        max_distance: Maximum hops from source (default 2)

    Returns:
        Filtered list of entities within max_distance hops
    """
    return [e for e in entities if e.distance <= max_distance]


def get_direct_connections(entities: list[P]) -> list[P]:
    """
    Get only direct (1-hop) connections.

    Args:
        entities: List of path-aware entities

    Returns:
        Filtered list of entities with distance == 1
    """
    return filter_by_distance(entities, max_distance=1)
