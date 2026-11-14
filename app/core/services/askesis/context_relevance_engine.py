"""
Context Relevance Engine - UserContext → Knowledge Discovery
============================================================

Finds the published knowledge (Ku, PathStep) relevant to the user's current
activities across all six activity domains. THE bridge between UserContext
awareness and knowledge recommendations.

A sub-service of the AskesisService facade beside ``context_retriever`` /
``user_state_analyzer``: activity aggregation, the two-ring knowledge read,
relevance scoring and prerequisite-first ordering.

Architecture:
    UserContext → Current activities (goals, habits, choices, tasks, ...)
    ContextRelevanceEngine → Knowledge that supports those activities

Status: staged (PLANNED) — ``find_relevant_from_user_context`` is the unwired
UserContext→relevant-KU discovery entry point; see ``scripts/detect_bloat.py``
(_ASKESIS_CONTEXT_ORCHESTRATION). The scoring is provisional and planned to
evolve: /docs/roadmap/relevance-engine-scoring.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.constants import GraphDepth
from core.models.enums import Domain, EntityType, KuComplexity, RelevanceRing
from core.models.type_hints import EntityUID
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext, GraphNode
    from core.ports.query_types import (
        RelevanceReason,
        RelevantKnowledgeResult,
        RelevantKnowledgeRow,
    )
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.user import UserContext

logger = get_logger(__name__)

_COMPLEXITY_VALUES: frozenset[str] = frozenset(level.value for level in KuComplexity)


@dataclass(frozen=True)
class _ReachedKnowledge:
    """A published knowledge node one edge from a center, and that edge."""

    node: GraphNode
    relationship: str
    outgoing: bool  # the edge points from the center to the node


class ContextRelevanceEngine:
    """
    Relevance engine mapping a user's current activities to supporting knowledge.

    Knowledge is read in two rings around each activity, and every reason names its ring:

    - ``DIRECT``: the knowledge the activity links itself, by any edge.
    - ``ADJACENT``: the knowledge one edge from a ``DIRECT`` unit (its prerequisite,
      a PathStep that uses it). The second ring grows out of knowledge only, never
      out of another activity — a goal's knowledge is the goal's, credited to the
      goal when the goal is among the activities asked about.

    Only published curriculum is returned (``GraphContext.get_published_knowledge_nodes``).
    """

    def __init__(self, graph_intel: GraphIntelligenceService) -> None:
        """
        Args:
            graph_intel: Graph intelligence service (entity context + prerequisite
                graph). The engine is constructed only by AskesisService, which is
                FULL-tier gated.
        """
        self.graph_intel = graph_intel

    async def find_relevant_for_context(
        self,
        active_goals: list[str] | None = None,
        current_habits: list[str] | None = None,
        recent_choices: list[str] | None = None,
        pending_tasks: list[str] | None = None,
        active_principles: list[str] | None = None,
        upcoming_events: list[str] | None = None,
        max_results: int = 10,
        min_relevance_score: float = 0.5,
    ) -> Result[RelevantKnowledgeResult]:
        """
        Find knowledge units relevant to the user's current activities.

        The activity uids are read as given: this method does not know who is asking,
        so its caller must already have checked that the asking user owns each one —
        ``find_relevant_from_user_context`` takes them from the user's own context.

        An activity that no longer exists contributes nothing; any other failed read
        fails the call, so an unreachable graph is never reported as "no knowledge".

        Scoring is provisional (planned to evolve, see the module docstring): each
        reason adds 0.2 (capped at 1.0) and each activity kind reaching the unit 0.15,
        so at the default ``min_relevance_score`` a unit needs two reasons to appear.

        Args:
            active_goals: UIDs of user's active goals
            current_habits: UIDs of habits user is tracking
            recent_choices: UIDs of pending or recent choices
            pending_tasks: UIDs of actionable tasks
            active_principles: UIDs of user's core principles
            upcoming_events: UIDs of upcoming events
            max_results: Maximum knowledge units to return
            min_relevance_score: Minimum relevance score (0.0-1.0)
        """
        activities: list[tuple[str, EntityType]] = []
        for uids, activity_type in (
            (active_goals, EntityType.GOAL),
            (current_habits, EntityType.HABIT),
            (recent_choices, EntityType.CHOICE),
            (pending_tasks, EntityType.TASK),
            (active_principles, EntityType.PRINCIPLE),
            (upcoming_events, EntityType.EVENT),
        ):
            activities.extend((uid, activity_type) for uid in uids or [])

        knowledge: dict[str, RelevantKnowledgeRow] = {}
        reasons: dict[str, list[RelevanceReason]] = {}
        coverage: dict[str, list[EntityType]] = {}
        # A unit linked by several activities has its own neighbourhood read once.
        neighbourhoods: dict[str, list[_ReachedKnowledge]] = {}

        def credit(reached: _ReachedKnowledge, reason: RelevanceReason) -> None:
            uid = reached.node.uid
            if uid not in knowledge:
                knowledge[uid] = _knowledge_row(reached.node)
                reasons[uid] = []
                coverage[uid] = []
            reasons[uid].append(reason)
            if reason["activity_type"] not in coverage[uid]:
                coverage[uid].append(reason["activity_type"])

        for activity_uid, activity_type in activities:
            direct_result = await self._published_knowledge_around(activity_uid)
            if direct_result.is_error:
                return Result.fail(direct_result)
            direct = direct_result.value
            direct_uids = {reached.node.uid for reached in direct}

            for reached in direct:
                credit(
                    reached,
                    {
                        "activity_uid": activity_uid,
                        "activity_type": activity_type,
                        "ring": RelevanceRing.DIRECT,
                        "via_uid": None,
                        "relationship": reached.relationship,
                        "outgoing": reached.outgoing,
                    },
                )

            for via in direct:
                via_uid = via.node.uid
                if via_uid not in neighbourhoods:
                    around = await self._published_knowledge_around(via_uid)
                    if around.is_error:
                        return Result.fail(around)
                    neighbourhoods[via_uid] = around.value
                for reached in neighbourhoods[via_uid]:
                    if reached.node.uid in direct_uids:
                        continue  # already credited to this activity directly
                    credit(
                        reached,
                        {
                            "activity_uid": activity_uid,
                            "activity_type": activity_type,
                            "ring": RelevanceRing.ADJACENT,
                            "via_uid": via_uid,
                            "relationship": reached.relationship,
                            "outgoing": reached.outgoing,
                        },
                    )

        scores: dict[str, float] = {
            uid: min(1.0, min(1.0, len(unit_reasons) * 0.2) + len(coverage[uid]) * 0.15)
            for uid, unit_reasons in reasons.items()
        }

        from core.utils.sort_functions import make_dict_score_getter

        ranked = sorted(
            (uid for uid in knowledge if scores[uid] >= min_relevance_score),
            key=make_dict_score_getter(scores, default=0.0),
            reverse=True,
        )[:max_results]

        order_result = await self._order_by_prerequisites(ranked)
        if order_result.is_error:
            return Result.fail(order_result)

        return Result.ok(
            {
                "knowledge_units": [knowledge[uid] for uid in ranked],
                "relevance_scores": {uid: scores[uid] for uid in ranked},
                "relevance_reasons": {uid: reasons[uid] for uid in ranked},
                "domain_coverage": {uid: coverage[uid] for uid in ranked},
                "recommended_order": order_result.value,
            }
        )

    async def find_relevant_from_user_context(
        self,
        user_context: UserContext,
        max_results: int = 10,
        min_relevance_score: float = 0.5,
    ) -> Result[RelevantKnowledgeResult]:
        """
        Convenience method that extracts activity UIDs from UserContext.

        This is the primary entry point for the UserContext + Askesis
        integration (staged — see module docstring).

        Args:
            user_context: Complete UserContext snapshot
            max_results: Maximum knowledge units to return
            min_relevance_score: Minimum relevance score (0.0-1.0)

        Returns:
            Same as find_relevant_for_context()
        """
        return await self.find_relevant_for_context(
            active_goals=user_context.active_goal_uids,
            current_habits=list(user_context.habit_streaks.keys()),
            recent_choices=user_context.pending_choice_uids,
            pending_tasks=user_context.active_task_uids,
            active_principles=user_context.core_principle_uids,
            upcoming_events=user_context.upcoming_event_uids,
            max_results=max_results,
            min_relevance_score=min_relevance_score,
        )

    async def _published_knowledge_around(self, center_uid: str) -> Result[list[_ReachedKnowledge]]:
        """The published knowledge one edge from a center, each with that edge.

        A center that does not exist (deleted since its uid was read) has none.
        Backend: GraphIntelligenceService.get_entity_context (every edge type, both
        directions, the center owner's nodes and shared content only).
        """
        context_result = await self.graph_intel.get_entity_context(
            EntityUID(center_uid), GraphDepth.DIRECT
        )
        if context_result.is_error:
            if context_result.expect_error().category is ErrorCategory.NOT_FOUND:
                logger.debug("Relevance read skipped a missing center: %s", center_uid)
                return Result.ok([])
            return Result.fail(context_result)
        context = context_result.value
        edges = _edges_to_center(context)
        return Result.ok(
            [
                _ReachedKnowledge(
                    node=node, relationship=edges[node.uid][0], outgoing=edges[node.uid][1]
                )
                for node in context.get_published_knowledge_nodes()
            ]
        )

    async def _order_by_prerequisites(self, ku_uids: list[str]) -> Result[list[str]]:
        """Order knowledge units so every prerequisite comes before what requires it.

        Backend: CrossDomainBackend.get_prerequisite_graph (``REQUIRES_KNOWLEDGE``
        among the given units).
        """
        if not ku_uids:
            return Result.ok([])
        rows = await self.graph_intel.backend.get_prerequisite_graph(ku_uids=ku_uids)
        if rows.is_error:
            return Result.fail(rows)
        return Result.ok(
            prerequisites_first(ku_uids, {row["uid"]: row["prerequisites"] for row in rows.value})
        )


def prerequisites_first(uids: list[str], requires: dict[str, list[str]]) -> list[str]:
    """Topologically order ``uids`` so each comes after every uid it requires (Kahn).

    Only requirements inside ``uids`` count. Ties keep the input order, so a
    relevance-ranked input stays ranked among units that are equally ready. Units on a
    requirement cycle — and those that wait on one — follow in input order.
    """
    members = set(uids)
    waiting = {uid: {p for p in requires.get(uid, []) if p in members and p != uid} for uid in uids}
    ready = [uid for uid in uids if not waiting[uid]]
    placed: list[str] = []
    while ready:
        current = ready.pop(0)
        placed.append(current)
        for uid in uids:
            if current in waiting[uid]:
                waiting[uid].discard(current)
                if not waiting[uid]:
                    ready.append(uid)
    placed_set = set(placed)
    return placed + [uid for uid in uids if uid not in placed_set]


def _edges_to_center(context: GraphContext) -> dict[str, tuple[str, bool]]:
    """Each neighbour's edge to the center: its type, and whether it points away from it.

    The context holds one edge per neighbour, and at depth 1 that edge joins it to the
    center. A neighbour joined by two edges (a task that applies and requires one Ku)
    keeps the one the context kept.
    """
    edges: dict[str, tuple[str, bool]] = {}
    for edge in context.all_relationships:
        if edge.start_node_uid == context.origin_uid:
            edges[edge.end_node_uid] = (edge.type, True)
        else:
            edges[edge.start_node_uid] = (edge.type, False)
    return edges


def _knowledge_row(node: GraphNode) -> RelevantKnowledgeRow:
    """What the engine reports about one knowledge node: what its file authored."""
    properties = node.properties
    return {
        "uid": node.uid,
        "title": str(properties.get("title") or node.uid),
        "entity_type": EntityType(properties["entity_type"]),
        "domain": _subject_area(properties.get("domain")),
        "complexity": _authored_complexity(properties.get("complexity")),
    }


def _subject_area(value: object) -> Domain | None:
    """The stored ``domain`` when it names a subject area; ``None`` otherwise."""
    domain = Domain.from_string(value) if isinstance(value, str) else None
    return domain if domain is not None and domain.is_subject_area() else None


def _authored_complexity(value: object) -> KuComplexity | None:
    """The stored ``complexity`` as a level; ``None`` when absent or not a level."""
    return KuComplexity(value) if isinstance(value, str) and value in _COMPLEXITY_VALUES else None
