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

from core.models.enums import EntityStatus
from core.models.enums.principle_enums import AlignmentLevel
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.services.cross_domain.cross_domain_types import (
    ActiveTaskCount,
    AlignedEntity,
    HabitKnowledgeReinforcement,
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


# Non-terminal task statuses — used by the goal-abandonment guard. A goal can
# only be cancelled when no task linked via FULFILLS_GOAL is still active in
# one of these states. Built from the enum so a status rename can't drift.
_ACTIVE_TASK_STATUSES: list[str] = [
    EntityStatus.ACTIVE.value,
    EntityStatus.SCHEDULED.value,
    EntityStatus.BLOCKED.value,
    EntityStatus.PAUSED.value,
]


# Cypher: count tasks that FULFILL the given goal and are still in a
# non-terminal state. One round-trip; the WHERE clause uses an IN-list against
# ``$active_statuses`` so the enum stays the source of truth.
_COUNT_ACTIVE_TASKS_FOR_GOAL_QUERY = f"""
MATCH (t:Entity {{entity_type: 'task'}})-[:{RelationshipName.FULFILLS_GOAL.value}]->(g:Entity {{uid: $goal_uid, entity_type: 'goal'}})
WHERE t.status IN $active_statuses
RETURN count(t) AS count
"""


# Active habit statuses — habits that should contribute to ZPD knowledge
# reinforcement signals. ``"pending"`` is a legacy alias that maps to DRAFT
# via ``EntityStatus._MISSING_`` but is preserved as a literal here so
# historical rows keep matching (see ``entity_enums.py:631``).
_HABIT_ACTIVE_STATUSES: list[str] = [
    EntityStatus.ACTIVE.value,
    "pending",
]


# Cypher: find every active habit the user owns plus the KUs it reinforces via
# REINFORCES_KNOWLEDGE. One round-trip; OPTIONAL MATCH preserves habits with
# no KU links (filtered at the Python boundary).
_HABIT_KNOWLEDGE_REINFORCEMENT_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(h:Entity {{entity_type: 'habit'}})
WHERE h.status IN $active_statuses
OPTIONAL MATCH (h)-[:{RelationshipName.REINFORCES_KNOWLEDGE.value}]->(ku:Entity {{entity_type: 'ku'}})
RETURN h.uid AS habit_uid,
       h.current_streak AS current_streak,
       h.success_rate AS success_rate,
       h.status AS status,
       collect(ku.uid) AS ku_uids
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

    async def count_active_tasks_for_goal(self, goal_uid: EntityUID) -> Result[ActiveTaskCount]:
        """
        Count tasks linked to ``goal_uid`` via ``FULFILLS_GOAL`` whose status is
        non-terminal (ACTIVE / SCHEDULED / BLOCKED / PAUSED).

        One Cypher round-trip. Used by the goal-abandonment guard in
        ``GoalsCoreService.update`` to block cancelling a goal that still has
        active tasks underneath it. Empty result → ``count=0``.
        """
        result = await self.executor.execute_query(
            _COUNT_ACTIVE_TASKS_FOR_GOAL_QUERY,
            {"goal_uid": goal_uid, "active_statuses": _ACTIVE_TASK_STATUSES},
        )
        if result.is_error:
            return Result.fail(result)

        rows = result.value or []
        count = int(rows[0]["count"]) if rows else 0
        return Result.ok(ActiveTaskCount(goal_uid=goal_uid, count=count))

    async def get_habit_knowledge_reinforcement(
        self, user_uid: UserUID
    ) -> Result[tuple[HabitKnowledgeReinforcement, ...]]:
        """
        Fetch every active habit the user owns together with the KUs it
        reinforces via ``REINFORCES_KNOWLEDGE``.

        One Cypher round-trip. Rows with no reinforcing KUs are dropped at
        the boundary so callers only see habits that actually contribute to
        ZPD reinforcement signals. Used by
        ``HabitsIntelligenceService.get_zpd_knowledge_signals`` to feed
        ``ZPDService.assess_zone``.
        """
        result = await self.executor.execute_query(
            _HABIT_KNOWLEDGE_REINFORCEMENT_QUERY,
            {"user_uid": user_uid, "active_statuses": _HABIT_ACTIVE_STATUSES},
        )
        if result.is_error:
            return Result.fail(result)

        rows = []
        for record in result.value or []:
            ku_uids = tuple(uid for uid in (record.get("ku_uids") or []) if uid)
            if not ku_uids:
                continue
            rows.append(
                HabitKnowledgeReinforcement(
                    habit_uid=record["habit_uid"],
                    current_streak=int(record.get("current_streak") or 0),
                    success_rate=float(record.get("success_rate") or 0.0),
                    status=record.get("status") or "",
                    ku_uids=ku_uids,
                )
            )
        return Result.ok(tuple(rows))
