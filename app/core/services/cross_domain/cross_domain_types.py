"""Typed result dataclasses for CrossDomainQueryService.

Frozen dataclasses only — these are immutable transfer objects between the
cross-domain service and its callers.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.enums.principle_enums import AlignmentLevel
from core.models.type_hints import EntityUID, UserUID


@dataclass(frozen=True)
class AlignedEntity:
    """Minimal projection of an entity that the graph reports as aligned."""

    uid: EntityUID
    title: str


@dataclass(frozen=True)
class PrincipleAlignmentEvidence:
    """
    Graph-derived evidence for how a principle is being lived out.

    Each item in ``aligned_goals`` / ``aligned_habits`` is connected to the
    principle by an explicit relationship in the graph (GUIDES_GOAL,
    GUIDED_BY_PRINCIPLE, INSPIRES_HABIT, EMBODIES_PRINCIPLE). The edge IS
    the alignment signal — there is no string-overlap heuristic here.
    """

    principle_uid: EntityUID
    user_uid: UserUID
    aligned_goals: tuple[AlignedEntity, ...]
    aligned_habits: tuple[AlignedEntity, ...]
    score: float
    alignment_level: AlignmentLevel

    @property
    def total_connections(self) -> int:
        return len(self.aligned_goals) + len(self.aligned_habits)


@dataclass(frozen=True)
class KnowledgeApplyingTask:
    """A task connected to a knowledge unit by an APPLIES/REQUIRES edge."""

    uid: EntityUID
    title: str
    relationship: str  # "APPLIES_KNOWLEDGE" | "REQUIRES_KNOWLEDGE"


@dataclass(frozen=True)
class TasksForKnowledge:
    """Tasks a user owns that engage with a specific knowledge unit."""

    knowledge_uid: EntityUID
    user_uid: UserUID
    tasks: tuple[KnowledgeApplyingTask, ...]


@dataclass(frozen=True)
class ActiveTaskCount:
    """Count of non-terminal tasks linked to a goal via FULFILLS_GOAL."""

    goal_uid: EntityUID
    count: int


@dataclass(frozen=True)
class ChoiceAlignmentDetail:
    """One choice's principle alignment from the adherence query."""

    choice_uid: EntityUID
    principle_uids: tuple[EntityUID, ...]
    satisfaction: float | None


@dataclass(frozen=True)
class ChoicePrincipleAdherence:
    """Aggregate principle adherence data for a user's choices."""

    total_choices: int
    aligned_count: int
    choice_details: tuple[ChoiceAlignmentDetail, ...]


@dataclass(frozen=True)
class ChoicePrincipleConflictCount:
    """Count of recent choices with unresolved principle conflicts."""

    conflict_count: int


@dataclass(frozen=True)
class HabitKnowledgeReinforcement:
    """One habit's relationship to the KUs it reinforces, raw rows from Neo4j.

    Raw signal rows used by ``HabitsIntelligenceService.get_zpd_knowledge_signals``
    to compute strength blending + at-risk status. ``ku_uids`` is always non-empty
    at the boundary — rows with no reinforcing KU are dropped upstream.
    """

    habit_uid: EntityUID
    current_streak: int
    success_rate: float
    status: str
    ku_uids: tuple[EntityUID, ...]
