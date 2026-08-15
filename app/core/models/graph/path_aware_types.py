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
from typing import Any


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwareTask":
        """Build from a cross-domain-context bucket entry (uid/title/path metadata)."""
        return cls(
            uid=d["uid"],
            title=d.get("title", ""),
            distance=d["distance"],
            path_strength=d["path_strength"],
            via_relationships=d.get("via_relationships", []),
        )


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
class PathAwareLearningPath:
    """
    Learning path with path metadata showing HOW it aligns with the source entity.

    Example:
        Goal → LearningPath (direct ALIGNED_WITH_PATH, distance=1, strength=0.86)
        Goal → LearningPath (REQUIRES_PATH_COMPLETION, distance=1, strength=0.90)

    Mirrors :class:`PathAwareKnowledge` (an Entity-labelled curriculum node reached
    via path-aware edges). NOTE: there are 0 LearningPath nodes live, so the
    ``learning_paths`` bucket is empty in practice — the type exists for the consumer
    contract's type-correctness.
    """

    uid: str
    title: str
    distance: int
    path_strength: float
    via_relationships: list[str]
    # Core learning-path fields
    status: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwareLearningPath":
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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PathAwareChoice":
        """Build from a cross-domain-context bucket entry (uid/title/path metadata)."""
        return cls(
            uid=d["uid"],
            title=d.get("title", ""),
            distance=d["distance"],
            path_strength=d["path_strength"],
            via_relationships=d.get("via_relationships", []),
        )


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
    - tasks: Tasks fulfilling this goal (FULFILLS_GOAL → ``contributing_tasks``)
    - habits: Habits supporting this goal — union of the SUPPORTS_GOAL-incoming
      essentiality tiers (``contributing_habits`` + ``essential_habits`` +
      ``critical_habits`` + ``optional_habits``)
    - knowledge: Knowledge required for this goal (REQUIRES_KNOWLEDGE →
      ``required_knowledge``)
    - subgoals: Child goals (SUBGOAL_OF incoming → ``sub_goals``)
    - parent_goal: Parent goal if this is a subgoal (SUBGOAL_OF outgoing →
      ``parent_goal``, single)
    - principles: Principles guiding this goal — union of GUIDED_BY_PRINCIPLE
      (outgoing, ``aligned_principles``) and GUIDES_GOAL (incoming,
      ``guiding_principles_incoming``)
    - learning_paths: Learning paths aligned with this goal — union of
      ALIGNED_WITH_PATH (``aligned_paths``) and REQUIRES_PATH_COMPLETION
      (``required_paths``)

    Each entity includes path metadata (distance, strength, path composition).
    """

    goal_uid: str
    tasks: list[PathAwareTask]
    habits: list[PathAwareHabit]
    knowledge: list[PathAwareKnowledge]
    subgoals: list[PathAwareGoal]
    parent_goal: PathAwareGoal | None
    principles: list[PathAwarePrinciple]
    learning_paths: list[PathAwareLearningPath]

    @classmethod
    def from_categorized(
        cls, source_uid: str, categorized_data: dict[str, Any]
    ) -> "GoalCrossContext":
        """Build the path-aware goal context from a ``get_cross_domain_context_typed``
        categorized payload (the GOALS_CONFIG ``context_field_name`` buckets).

        This is the per-domain seam the generic factory delegates to: it SELECTs the
        goal-relevant buckets, RENAMEs them to the dataclass fields, UNIONs the multi-tier
        / bidirectional buckets, and DEDUPs each field to its strongest path. One union
        call per target field (per-field scoping is intentional).

        - ``tasks`` ← FULFILLS_GOAL (``contributing_tasks``).
        - ``habits`` ← the union of the four SUPPORTS_GOAL-incoming essentiality tiers
          (``contributing_habits`` + ``essential_habits`` + ``critical_habits`` +
          ``optional_habits``).
        - ``knowledge`` ← REQUIRES_KNOWLEDGE (``required_knowledge``).
        - ``subgoals`` ← SUBGOAL_OF incoming (``sub_goals``).
        - ``parent_goal`` ← SUBGOAL_OF outgoing (``parent_goal``, single); the strongest
          of the (typically one) entries, or ``None`` when absent.
        - ``principles`` ← the union of GUIDED_BY_PRINCIPLE (outgoing,
          ``aligned_principles``) and GUIDES_GOAL (incoming,
          ``guiding_principles_incoming``).
        - ``learning_paths`` ← the union of ALIGNED_WITH_PATH (``aligned_paths``) and
          REQUIRES_PATH_COMPLETION (``required_paths``). Empty in practice (0 LearningPath
          nodes live) but populated for the consumer contract.
        """
        parents = [
            PathAwareGoal.from_dict(g) for g in _union_path_buckets(categorized_data, "parent_goal")
        ]
        return cls(
            goal_uid=source_uid,
            tasks=[
                PathAwareTask.from_dict(t)
                for t in _union_path_buckets(categorized_data, "contributing_tasks")
            ],
            habits=[
                PathAwareHabit.from_dict(h)
                for h in _union_path_buckets(
                    categorized_data,
                    "contributing_habits",
                    "essential_habits",
                    "critical_habits",
                    "optional_habits",
                )
            ],
            knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "required_knowledge")
            ],
            subgoals=[
                PathAwareGoal.from_dict(g)
                for g in _union_path_buckets(categorized_data, "sub_goals")
            ],
            parent_goal=parents[0] if parents else None,
            principles=[
                PathAwarePrinciple.from_dict(p)
                for p in _union_path_buckets(
                    categorized_data, "aligned_principles", "guiding_principles_incoming"
                )
            ],
            learning_paths=[
                PathAwareLearningPath.from_dict(lp)
                for lp in _union_path_buckets(categorized_data, "aligned_paths", "required_paths")
            ],
        )

    def _all_entities(
        self,
    ) -> list[
        PathAwareTask
        | PathAwareHabit
        | PathAwareKnowledge
        | PathAwareGoal
        | PathAwarePrinciple
        | PathAwareLearningPath
    ]:
        """All connected path-aware entities across every field (incl. parent_goal)."""
        entities: list[
            PathAwareTask
            | PathAwareHabit
            | PathAwareKnowledge
            | PathAwareGoal
            | PathAwarePrinciple
            | PathAwareLearningPath
        ] = [
            *self.tasks,
            *self.habits,
            *self.knowledge,
            *self.subgoals,
            *self.principles,
            *self.learning_paths,
        ]
        if self.parent_goal:
            entities.append(self.parent_goal)
        return entities

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return len(self._all_entities())

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
    def direct_tasks(self) -> list[PathAwareTask]:
        """Direct task connections (distance=1)."""
        return [t for t in self.tasks if t.distance == 1]

    @property
    def direct_habits(self) -> list[PathAwareHabit]:
        """Direct habit connections (distance=1)."""
        return [h for h in self.habits if h.distance == 1]

    @property
    def direct_knowledge(self) -> list[PathAwareKnowledge]:
        """Direct knowledge connections (distance=1)."""
        return [k for k in self.knowledge if k.distance == 1]

    @property
    def direct_principles(self) -> list[PathAwarePrinciple]:
        """Direct principle connections (distance=1)."""
        return [p for p in self.principles if p.distance == 1]

    @property
    def direct_learning_paths(self) -> list[PathAwareLearningPath]:
        """Direct learning-path connections (distance=1)."""
        return [lp for lp in self.learning_paths if lp.distance == 1]

    @property
    def max_path_depth(self) -> int:
        """Deepest hop across all connections (0 when there are none)."""
        return max((e.distance for e in self._all_entities()), default=0)


@dataclass(frozen=True)
class PrincipleCrossContext:
    """
    Principle influence context with path-aware intelligence.

    Groups related entities by relationship semantic:
    - goals: Goals guided by this principle (GUIDES_GOAL → ``guided_goals``)
    - choices: Choices informed by this principle (GUIDES_CHOICE → ``guided_choices``)
    - knowledge: Knowledge grounding this principle (GROUNDED_IN_KNOWLEDGE →
      ``grounding_knowledge``)
    - habits: Habits aligned with this principle — union of INSPIRES_HABIT (outgoing,
      ``inspired_habits``) and EMBODIES_PRINCIPLE (incoming, ``embodying_habits``)

    Each entity includes path metadata (distance, strength, path composition).
    """

    principle_uid: str
    goals: list[PathAwareGoal]
    choices: list[PathAwareChoice]
    knowledge: list[PathAwareKnowledge]
    habits: list[PathAwareHabit]

    @classmethod
    def from_categorized(
        cls, source_uid: str, categorized_data: dict[str, Any]
    ) -> "PrincipleCrossContext":
        """Build the path-aware principle context from a ``get_cross_domain_context_typed``
        categorized payload (the PRINCIPLES_CONFIG ``context_field_name`` buckets).

        This is the per-domain seam the generic factory delegates to: it SELECTs the
        principle-relevant buckets, RENAMEs them to the dataclass fields, UNIONs the two
        habit directions, and DEDUPs each field to its strongest path. One union call per
        target field (per-field scoping is intentional).

        - ``goals`` ← GUIDES_GOAL (``guided_goals``).
        - ``choices`` ← GUIDES_CHOICE (``guided_choices``).
        - ``knowledge`` ← GROUNDED_IN_KNOWLEDGE (``grounding_knowledge``).
        - ``habits`` ← the union of INSPIRES_HABIT (outgoing, ``inspired_habits``) and
          EMBODIES_PRINCIPLE (incoming, ``embodying_habits``).

        Every PRINCIPLES_CONFIG bucket mapped here is a list (no ``single=True`` field is
        surfaced — ``life_path`` is single but is not part of this context).
        """
        return cls(
            principle_uid=source_uid,
            goals=[
                PathAwareGoal.from_dict(g)
                for g in _union_path_buckets(categorized_data, "guided_goals")
            ],
            choices=[
                PathAwareChoice.from_dict(c)
                for c in _union_path_buckets(categorized_data, "guided_choices")
            ],
            knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "grounding_knowledge")
            ],
            habits=[
                PathAwareHabit.from_dict(h)
                for h in _union_path_buckets(
                    categorized_data, "inspired_habits", "embodying_habits"
                )
            ],
        )

    def _all_entities(
        self,
    ) -> list[PathAwareGoal | PathAwareChoice | PathAwareKnowledge | PathAwareHabit]:
        """All connected path-aware entities across every field."""
        return [*self.goals, *self.choices, *self.knowledge, *self.habits]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return len(self._all_entities())

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
    def direct_choices(self) -> list[PathAwareChoice]:
        """Direct choice connections (distance=1)."""
        return [c for c in self.choices if c.distance == 1]

    @property
    def direct_knowledge(self) -> list[PathAwareKnowledge]:
        """Direct knowledge connections (distance=1)."""
        return [k for k in self.knowledge if k.distance == 1]

    @property
    def direct_habits(self) -> list[PathAwareHabit]:
        """Direct habit connections (distance=1)."""
        return [h for h in self.habits if h.distance == 1]

    @property
    def max_path_depth(self) -> int:
        """Deepest hop across all connections (0 when there are none)."""
        return max((e.distance for e in self._all_entities()), default=0)


@dataclass(frozen=True)
class TaskCrossContext:
    """
    Task execution context with path-aware intelligence.

    Groups CROSS-DOMAIN related entities by relationship semantic:
    - required_knowledge: Knowledge needed to complete task (REQUIRES_KNOWLEDGE →
      ``required_knowledge``)
    - applied_knowledge: Knowledge this task applies (APPLIES_KNOWLEDGE →
      ``applied_knowledge``)
    - contributing_goals: Goals this task fulfills/contributes to — union of
      CONTRIBUTES_TO_GOAL (``contributing_goals``) and the single FULFILLS_GOAL
      (``goal_context``)

    Same-domain task→task dependencies (DEPENDS_ON prerequisites / dependents) are NOT
    part of cross-domain context — they are owned by the lateral-relationships system
    (BlockingChainView) and ZPD. They were dropped from this type during the typed-reader
    convergence; restore only alongside a real consumer that needs them here.

    Each entity includes path metadata (distance, strength, path composition).
    """

    task_uid: str
    required_knowledge: list[PathAwareKnowledge]
    applied_knowledge: list[PathAwareKnowledge]
    contributing_goals: list[PathAwareGoal]

    @classmethod
    def from_categorized(
        cls, source_uid: str, categorized_data: dict[str, Any]
    ) -> "TaskCrossContext":
        """Build the path-aware task context from a ``get_cross_domain_context_typed``
        categorized payload (the TASKS_CONFIG ``context_field_name`` buckets).

        This is the per-domain seam the generic factory delegates to: it SELECTs the
        task-relevant cross-domain buckets, RENAMEs them to the dataclass fields, UNIONs the
        two goal-link directions, and DEDUPs each field to its strongest path. One union call
        per target field (per-field scoping is intentional).

        - ``required_knowledge`` ← REQUIRES_KNOWLEDGE (``required_knowledge``).
        - ``applied_knowledge`` ← APPLIES_KNOWLEDGE (``applied_knowledge``).
        - ``contributing_goals`` ← the union of CONTRIBUTES_TO_GOAL (``contributing_goals``)
          and the single FULFILLS_GOAL (``goal_context``).
        """
        return cls(
            task_uid=source_uid,
            required_knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "required_knowledge")
            ],
            applied_knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "applied_knowledge")
            ],
            contributing_goals=[
                PathAwareGoal.from_dict(g)
                for g in _union_path_buckets(categorized_data, "contributing_goals", "goal_context")
            ],
        )

    def _all_entities(self) -> list[PathAwareKnowledge | PathAwareGoal]:
        """All connected path-aware entities across every field."""
        return [*self.required_knowledge, *self.applied_knowledge, *self.contributing_goals]

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return len(self._all_entities())

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
    def direct_knowledge(self) -> list[PathAwareKnowledge]:
        """Direct required-knowledge connections (distance=1)."""
        return [k for k in self.required_knowledge if k.distance == 1]

    @property
    def direct_applied_knowledge(self) -> list[PathAwareKnowledge]:
        """Direct applied-knowledge connections (distance=1)."""
        return [k for k in self.applied_knowledge if k.distance == 1]

    @property
    def direct_goals(self) -> list[PathAwareGoal]:
        """Direct goal connections (distance=1)."""
        return [g for g in self.contributing_goals if g.distance == 1]

    @property
    def max_path_depth(self) -> int:
        """Deepest hop across all connections (0 when there are none)."""
        return max((e.distance for e in self._all_entities()), default=0)


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
          ``embodied_principles``) and INSPIRES_HABIT (incoming, ``inspiring_principles``) —
          symmetric aggregation across both principle directions.
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

    @classmethod
    def from_categorized(
        cls, source_uid: str, categorized_data: dict[str, Any]
    ) -> "EventCrossContext":
        """Build the path-aware event context from a ``get_cross_domain_context_typed``
        categorized payload (the EVENTS_CONFIG ``context_field_name`` buckets).

        This is the per-domain seam the generic factory delegates to: it SELECTs the
        event-relevant buckets, RENAMEs them to the dataclass fields, UNIONs the two
        goal/habit directions, and DEDUPs each field to its strongest path. One union call
        per target field (per-field scoping is intentional).

        - ``goals`` ← union of CONTRIBUTES_TO_GOAL (``supported_goals``) and the milestone
          CELEBRATES_GOAL (``celebrated_goals``).
        - ``habits`` ← union of the outgoing REINFORCES_HABIT (``reinforced_habits``) and the
          incoming PRACTICED_AT_EVENT (``practiced_habits``).
        - ``knowledge`` ← APPLIES_KNOWLEDGE (``applied_knowledge``).
        """
        return cls(
            event_uid=source_uid,
            goals=[
                PathAwareGoal.from_dict(g)
                for g in _union_path_buckets(
                    categorized_data, "supported_goals", "celebrated_goals"
                )
            ],
            habits=[
                PathAwareHabit.from_dict(h)
                for h in _union_path_buckets(
                    categorized_data, "reinforced_habits", "practiced_habits"
                )
            ],
            knowledge=[
                PathAwareKnowledge.from_dict(k)
                for k in _union_path_buckets(categorized_data, "applied_knowledge")
            ],
        )

    @property
    def total_connections(self) -> int:
        """Total number of connected entities."""
        return len(self.goals) + len(self.habits) + len(self.knowledge)

    def _all_entities(
        self,
    ) -> list[PathAwareGoal | PathAwareHabit | PathAwareKnowledge]:
        """All connected path-aware entities across every field."""
        return [*self.goals, *self.habits, *self.knowledge]

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
    def direct_habits(self) -> list[PathAwareHabit]:
        """Direct habit connections (distance=1)."""
        return [h for h in self.habits if h.distance == 1]

    @property
    def direct_knowledge(self) -> list[PathAwareKnowledge]:
        """Direct knowledge connections (distance=1)."""
        return [k for k in self.knowledge if k.distance == 1]

    @property
    def max_path_depth(self) -> int:
        """Deepest hop across all connections (0 when there are none)."""
        return max((e.distance for e in self._all_entities()), default=0)
