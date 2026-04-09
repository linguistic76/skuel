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
