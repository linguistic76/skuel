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
- One Cypher per call. No N+1.
- Return a typed result dataclass from ``cross_domain_types``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.cross_domain_backend import FULL_ALIGNMENT_CONNECTION_COUNT
from core.models.enums.principle_enums import AlignmentLevel
from core.models.type_hints import EntityUID, UserUID
from core.services.cross_domain.cross_domain_types import (
    ActiveTaskCount,
    AlignedEntity,
    ChoiceAlignmentDetail,
    ChoicePrincipleAdherence,
    ChoicePrincipleConflictCount,
    EventImpactBatch,
    EventImpactRow,
    HabitKnowledgeReinforcement,
    KnowledgeApplyingTask,
    PrincipleAlignmentEvidence,
    TasksForKnowledge,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date

    from core.ports.cross_domain_protocols import CrossDomainBackendOperations


class CrossDomainQueryService:
    """Cross-domain read queries — one Cypher per call, typed results."""

    def __init__(self, backend: CrossDomainBackendOperations) -> None:
        self.backend = backend
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
        result = await self.backend.get_principle_alignment_evidence(
            principle_uid=principle_uid, user_uid=user_uid
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
        score = min(1.0, total / FULL_ALIGNMENT_CONNECTION_COUNT) if total else 0.0
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
        result = await self.backend.get_tasks_applying_knowledge(
            knowledge_uid=knowledge_uid, user_uid=user_uid, limit=limit
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

    async def get_goals_for_tasks_batch(
        self, task_uids: list[str]
    ) -> Result[dict[str, tuple[AlignedEntity, ...]]]:
        """
        Batch-fetch goals each task contributes to or fulfills via
        ``CONTRIBUTES_TO_GOAL`` or ``FULFILLS_GOAL`` edges.

        One Cypher round-trip for N tasks — replaces the per-task N+1 pattern
        in ``TasksPlanningService.get_task_dependencies_for_user``. Returns a
        ``{task_uid: (AlignedEntity, ...)}`` map; tasks with no goal edges map
        to an empty tuple, and task UIDs missing from the graph are absent
        from the result. Empty input returns an empty map without hitting
        Neo4j.
        """
        if not task_uids:
            return Result.ok({})

        result = await self.backend.get_goals_for_tasks_batch(task_uids=list(task_uids))
        if result.is_error:
            return Result.fail(result)

        goals_by_task: dict[str, tuple[AlignedEntity, ...]] = {}
        for row in result.value or []:
            task_uid = row.get("task_uid")
            if not task_uid:
                continue
            goals_by_task[task_uid] = tuple(
                AlignedEntity(uid=g["uid"], title=g.get("title") or "")
                for g in (row.get("goals") or [])
                if g and g.get("uid")
            )
        return Result.ok(goals_by_task)

    async def count_active_tasks_for_goal(self, goal_uid: EntityUID) -> Result[ActiveTaskCount]:
        """
        Count tasks linked to ``goal_uid`` via ``FULFILLS_GOAL`` whose status is
        non-terminal (ACTIVE / SCHEDULED / BLOCKED / PAUSED).

        One Cypher round-trip. Used by the goal-abandonment guard in
        ``GoalsCoreService.update`` to block cancelling a goal that still has
        active tasks underneath it. Empty result → ``count=0``.
        """
        result = await self.backend.count_active_tasks_for_goal(goal_uid=goal_uid)
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
        result = await self.backend.get_habit_knowledge_reinforcement(user_uid=user_uid)
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

    async def get_choice_principle_adherence(
        self, user_uid: UserUID, period_days: int = 90
    ) -> Result[ChoicePrincipleAdherence]:
        """
        Fetch aggregate principle-adherence data for a user's choices over
        ``period_days``.

        One Cypher round-trip. Returns ``total_choices``, ``aligned_count``,
        and per-choice detail (choice UID, aligned principle UIDs,
        satisfaction score). Rows with empty ``principle_uids`` are kept
        because the adherence calculation needs to count total choices vs
        aligned choices.

        Used by ``_BehavioralSignalsMixin.analyze_principle_adherence`` and
        ``get_zpd_behavioral_signals`` for the ZPD behavioral readiness bridge.
        """
        result = await self.backend.get_choice_principle_adherence(
            user_uid=user_uid, period_days=period_days
        )
        if result.is_error:
            return Result.fail(result)

        rows = result.value or []
        if not rows:
            return Result.ok(
                ChoicePrincipleAdherence(total_choices=0, aligned_count=0, choice_details=())
            )

        record = rows[0]
        details = tuple(
            ChoiceAlignmentDetail(
                choice_uid=d["choice_uid"],
                principle_uids=tuple(uid for uid in (d.get("principles") or []) if uid),
                satisfaction=d.get("satisfaction"),
            )
            for d in (record.get("choice_details") or [])
            if d and d.get("choice_uid")
        )

        return Result.ok(
            ChoicePrincipleAdherence(
                total_choices=int(record.get("total_choices") or 0),
                aligned_count=int(record.get("aligned_count") or 0),
                choice_details=details,
            )
        )

    async def get_choice_conflict_count(
        self, user_uid: UserUID
    ) -> Result[ChoicePrincipleConflictCount]:
        """
        Count recent choices (last 30 days) with unresolved principle
        conflicts for ``user_uid``.

        One Cypher round-trip. Used by ``get_zpd_behavioral_signals`` to
        surface active principle tensions to ZPDService.
        """
        result = await self.backend.get_choice_conflict_count(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        rows = result.value or []
        count = int(rows[0]["conflict_count"]) if rows else 0
        return Result.ok(ChoicePrincipleConflictCount(conflict_count=count))

    async def get_event_impact_batch(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
    ) -> Result[EventImpactBatch]:
        """
        Batch-fetch goal + knowledge counts for every non-terminal event owned
        by ``user_uid`` in ``[start_date, end_date]``.

        One Cypher round-trip. Replaces the 2N ``get_cross_domain_context`` +
        ``get_related_uids`` loop in ``EventsIntelligenceService.analyze_upcoming_events``.
        Callers build a ``dict[uid, EventImpactRow]`` and do O(1) lookups per event.
        """
        result = await self.backend.get_event_impact_batch(
            user_uid=user_uid, start_date=start_date, end_date=end_date
        )
        if result.is_error:
            return Result.fail(result)

        rows = tuple(
            EventImpactRow(
                event_uid=record["event_uid"],
                goal_count=int(record.get("goal_count") or 0),
                knowledge_count=int(record.get("knowledge_count") or 0),
            )
            for record in (result.value or [])
            if record and record.get("event_uid")
        )
        return Result.ok(EventImpactBatch(rows=rows))
