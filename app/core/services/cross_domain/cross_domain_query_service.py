"""
CrossDomainQueryService
=======================

Read-side cross-domain queries. Each method touches 2+ domain labels and runs
exactly one Cypher query. Returns typed dataclasses, never ``dict[str, Any]``.

Why this exists
---------------
The existing pattern across the Activity Domains was: fetch every Goal for
the user via the goals backend, fetch every Habit for the user via the habits
backend, then loop in Python and try to discover relationships by string
matching. That ignored the graph entirely. This service replaces those
fan-out-and-loop call sites with single Cypher queries that walk the
relationships the graph already encodes.

Rules for additions
-------------------
- Methods MUST touch 2+ domain labels (otherwise it belongs in a domain service).
- Methods take only the ``QueryExecutor``, never per-domain backends.
- One Cypher per call. No N+1.
- Return a typed result dataclass from ``cross_domain_types``.
- Methods are named after the question, not the domain pair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums.principle_enums import AlignmentLevel
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.services.cross_domain.cross_domain_types import (
    AlignedEntity,
    KnowledgeApplyingTask,
    PrincipleAlignmentEvidence,
    TasksForKnowledge,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor


# Cypher: find Goals and Habits owned by ``user_uid`` that are connected to
# Principle ``principle_uid`` via any of the explicit alignment relationships.
# One round-trip; CALL subqueries keep the two domain matches independent so
# an empty match in one branch never zeros out the other.
_PRINCIPLE_ALIGNMENT_EVIDENCE_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(p:Entity {{uid: $principle_uid, entity_type: 'principle'}})

CALL {{
  WITH p, u
  MATCH (u)-[:{RelationshipName.OWNS.value}]->(g:Entity {{entity_type: 'goal'}})
  WHERE (p)-[:{RelationshipName.GUIDES_GOAL.value}]->(g)
     OR (g)-[:{RelationshipName.GUIDED_BY_PRINCIPLE.value}]->(p)
     OR (g)-[:{RelationshipName.EMBODIES_PRINCIPLE.value}]->(p)
  RETURN collect(DISTINCT {{uid: g.uid, title: g.title}}) AS aligned_goals
}}

CALL {{
  WITH p, u
  MATCH (u)-[:{RelationshipName.OWNS.value}]->(h:Entity {{entity_type: 'habit'}})
  WHERE (p)-[:{RelationshipName.INSPIRES_HABIT.value}]->(h)
     OR (h)-[:{RelationshipName.EMBODIES_PRINCIPLE.value}]->(p)
  RETURN collect(DISTINCT {{uid: h.uid, title: h.title}}) AS aligned_habits
}}

RETURN aligned_goals, aligned_habits
"""

# Score conversion: each connected entity contributes 1/5 to the score, capped
# at 1.0. Five direct alignments is treated as a fully aligned principle.
_FULL_ALIGNMENT_CONNECTION_COUNT: float = 5.0


# Cypher: find tasks owned by ``user_uid`` that apply or require the given
# knowledge unit. Ownership is scoped via (:User)-[:OWNS]->(:task) — the
# canonical user→entity edge for Activity Domains.
_TASKS_APPLYING_KNOWLEDGE_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(t:Entity {{entity_type: 'task'}})
MATCH (t)-[r:{RelationshipName.APPLIES_KNOWLEDGE.value}|{RelationshipName.REQUIRES_KNOWLEDGE.value}]->(:Entity {{uid: $knowledge_uid}})
RETURN t.uid AS uid, t.title AS title, type(r) AS rel
LIMIT $limit
"""


# Cypher: find goals this task contributes to or fulfills. Distinct to avoid
# double-counting if both edges exist between the same task/goal pair.
_GOALS_FOR_TASK_QUERY = f"""
MATCH (t:Entity {{uid: $task_uid, entity_type: 'task'}})
MATCH (t)-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}|{RelationshipName.FULFILLS_GOAL.value}]->(g:Entity {{entity_type: 'goal'}})
RETURN DISTINCT g.uid AS uid, g.title AS title
"""


class CrossDomainQueryService:
    """Cross-domain read queries — one Cypher per call, typed results."""

    def __init__(self, executor: QueryExecutor) -> None:
        self.executor = executor
        self.logger = get_logger("skuel.services.cross_domain")

    async def get_principle_alignment_evidence(
        self, principle_uid: EntityUID, user_uid: UserUID
    ) -> Result[PrincipleAlignmentEvidence]:
        """
        Find goals and habits the user owns that are connected to ``principle_uid``
        via explicit alignment edges (``GUIDES_GOAL``, ``GUIDED_BY_PRINCIPLE``,
        ``INSPIRES_HABIT``, ``EMBODIES_PRINCIPLE``).

        Returns the connected entities plus a graph-derived alignment score:
        the score is ``min(1.0, total_connections / 5.0)``, with the
        ``AlignmentLevel`` derived via ``AlignmentLevel.from_score``. A
        principle with no graph connections returns score ``0.0`` and level
        ``UNKNOWN`` — which is the honest answer the graph gives, in
        contrast to the previous string-overlap heuristic.
        """
        result = await self.executor.execute_query(
            _PRINCIPLE_ALIGNMENT_EVIDENCE_QUERY,
            {"principle_uid": principle_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)

        rows = result.value
        if not rows:
            # Principle not found, or not owned by this user.
            return Result.ok(
                PrincipleAlignmentEvidence(
                    principle_uid=principle_uid,
                    user_uid=user_uid,
                    aligned_goals=(),
                    aligned_habits=(),
                    score=0.0,
                    alignment_level=AlignmentLevel.UNKNOWN,
                )
            )

        row = rows[0]
        aligned_goals = tuple(
            AlignedEntity(uid=g["uid"], title=g.get("title") or "")
            for g in (row.get("aligned_goals") or [])
            if g and g.get("uid")
        )
        aligned_habits = tuple(
            AlignedEntity(uid=h["uid"], title=h.get("title") or "")
            for h in (row.get("aligned_habits") or [])
            if h and h.get("uid")
        )

        total = len(aligned_goals) + len(aligned_habits)
        score = min(1.0, total / _FULL_ALIGNMENT_CONNECTION_COUNT) if total else 0.0
        level = AlignmentLevel.from_score(score)

        return Result.ok(
            PrincipleAlignmentEvidence(
                principle_uid=principle_uid,
                user_uid=user_uid,
                aligned_goals=aligned_goals,
                aligned_habits=aligned_habits,
                score=score,
                alignment_level=level,
            )
        )

    async def get_tasks_applying_knowledge(
        self,
        knowledge_uid: EntityUID,
        user_uid: UserUID,
        limit: int = 20,
    ) -> Result[TasksForKnowledge]:
        """
        Find tasks the user owns that engage with a given knowledge unit via
        ``APPLIES_KNOWLEDGE`` or ``REQUIRES_KNOWLEDGE`` edges.

        One Cypher round-trip. Ownership is scoped via ``(:User)-[:OWNS]->(:task)``
        rather than a ``t.user_uid`` property filter — the graph edge is the
        source of truth for ownership on Activity Domains.
        """
        result = await self.executor.execute_query(
            _TASKS_APPLYING_KNOWLEDGE_QUERY,
            {
                "knowledge_uid": knowledge_uid,
                "user_uid": user_uid,
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)

        tasks = tuple(
            KnowledgeApplyingTask(
                uid=row["uid"],
                title=row.get("title") or "",
                relationship=row.get("rel") or "",
            )
            for row in (result.value or [])
            if row and row.get("uid")
        )

        return Result.ok(
            TasksForKnowledge(
                knowledge_uid=knowledge_uid,
                user_uid=user_uid,
                tasks=tasks,
            )
        )

    async def get_goals_for_task(self, task_uid: EntityUID) -> Result[tuple[AlignedEntity, ...]]:
        """
        Find goals this task contributes to or fulfills via
        ``CONTRIBUTES_TO_GOAL`` or ``FULFILLS_GOAL`` edges.

        One Cypher query. Used by task dependency enrichment to populate
        goal alignment scoring on ``ContextualTask`` — previously stubbed as
        an empty list, which silently zeroed goal-alignment scores.
        """
        result = await self.executor.execute_query(
            _GOALS_FOR_TASK_QUERY,
            {"task_uid": task_uid},
        )
        if result.is_error:
            return Result.fail(result)

        goals = tuple(
            AlignedEntity(uid=row["uid"], title=row.get("title") or "")
            for row in (result.value or [])
            if row and row.get("uid")
        )
        return Result.ok(goals)
