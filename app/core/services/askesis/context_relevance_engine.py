"""
Context Relevance Engine - UserContext → Knowledge Discovery
============================================================

Finds knowledge units relevant to the user's current activities across all
six activity domains. THE bridge between UserContext awareness and knowledge
recommendations.

Extracted from the AskesisService facade (Tier 6): the facade coordinates
sub-services and holds zero business logic; this ~350-line relevance engine
(activity aggregation, graph-context knowledge extraction, relevance scoring,
prerequisite-aware ordering) is a sub-service beside ``context_retriever`` /
``user_state_analyzer``, not facade code.

Architecture:
    UserContext → Current activities (goals, habits, choices, tasks, ...)
    ContextRelevanceEngine → Knowledge that supports those activities

Status: staged (PLANNED) — ``find_relevant_from_user_context`` is the unwired
UserContext→relevant-KU discovery entry point; see ``scripts/detect_bloat.py``
(_ASKESIS_CONTEXT_ORCHESTRATION).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user import UserContext

logger = get_logger(__name__)


class ContextRelevanceEngine:
    """
    Relevance engine mapping a user's current activities to supporting knowledge.

    **Relevance Scoring:**
    - Goal alignment: Knowledge required or useful for active goals
    - Habit support: Knowledge that reinforces habit formation
    - Choice inform: Knowledge that helps make pending decisions
    - Task enablement: Knowledge that unblocks pending tasks
    - Principle grounding: Knowledge that supports core principles
    - Event preparation: Knowledge useful for upcoming events
    """

    def __init__(self, graph_intel: Any) -> None:
        """
        Args:
            graph_intel: Graph intelligence service (semantic context +
                prerequisite graph access). Required — the engine is only
                constructed by AskesisService, which is FULL-tier gated.
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
    ) -> Result[dict[str, Any]]:
        """
        Find knowledge units relevant to the user's current activities.

        Args:
            active_goals: UIDs of user's active goals
            current_habits: UIDs of habits user is tracking
            recent_choices: UIDs of pending or recent choices
            pending_tasks: UIDs of actionable tasks
            active_principles: UIDs of user's core principles
            upcoming_events: UIDs of upcoming events
            max_results: Maximum knowledge units to return
            min_relevance_score: Minimum relevance score (0.0-1.0)

        Returns:
            Result[dict[str, Any]]: {
                "knowledge_units": [...], # Relevant KU data
                "relevance_scores": {...}, # UID -> score mapping
                "relevance_reasons": {...}, # UID -> list of reasons
                "domain_coverage": {...}, # Which domains each KU helps
                "recommended_order": [...], # Optimal learning order
            }
        """
        if not self.graph_intel:
            return Result.fail(
                Errors.system(
                    message="Graph intelligence service not available",
                    operation="find_relevant_for_context",
                )
            )

        # Aggregate all activity UIDs
        all_activity_uids: list[str] = []
        domain_sources: dict[str, str] = {}  # uid -> domain

        for uids, domain in (
            (active_goals, "goal"),
            (current_habits, "habit"),
            (recent_choices, "choice"),
            (pending_tasks, "task"),
            (active_principles, "principle"),
            (upcoming_events, "event"),
        ):
            if uids:
                all_activity_uids.extend(uids)
                for uid in uids:
                    domain_sources[uid] = domain

        if not all_activity_uids:
            # No activities to match against
            return Result.ok(
                {
                    "knowledge_units": [],
                    "relevance_scores": {},
                    "relevance_reasons": {},
                    "domain_coverage": {},
                    "recommended_order": [],
                }
            )

        # Query graph for knowledge connected to these activities
        relevant_knowledge: dict[str, dict[str, Any]] = {}
        relevance_reasons: dict[str, list[str]] = {}
        domain_coverage: dict[str, list[str]] = {}

        # Query knowledge for each activity type
        for activity_uid in all_activity_uids:
            domain = domain_sources[activity_uid]

            # Get knowledge connected to this activity
            ku_result = await self._find_knowledge_for_activity(activity_uid=activity_uid)

            if ku_result.is_ok and ku_result.value:
                for ku_data in ku_result.value:
                    ku_uid = ku_data.get("uid", "")
                    if not ku_uid:
                        continue

                    # Accumulate knowledge
                    if ku_uid not in relevant_knowledge:
                        relevant_knowledge[ku_uid] = ku_data
                        relevance_reasons[ku_uid] = []
                        domain_coverage[ku_uid] = []

                    # Track why it's relevant
                    reason = f"Supports {domain}: {activity_uid}"
                    if reason not in relevance_reasons[ku_uid]:
                        relevance_reasons[ku_uid].append(reason)

                    # Track domain coverage
                    if domain not in domain_coverage[ku_uid]:
                        domain_coverage[ku_uid].append(domain)

        # Calculate relevance scores
        relevance_scores: dict[str, float] = {}
        for ku_uid, reasons in relevance_reasons.items():
            # Base score from number of connections
            base_score = min(1.0, len(reasons) * 0.2)

            # Bonus for multi-domain coverage
            domain_bonus = len(domain_coverage[ku_uid]) * 0.15

            # Calculate final score
            score = min(1.0, base_score + domain_bonus)
            relevance_scores[ku_uid] = score

        # Filter by minimum score
        filtered_knowledge = {
            uid: data
            for uid, data in relevant_knowledge.items()
            if relevance_scores.get(uid, 0) >= min_relevance_score
        }

        # Sort by relevance score
        from core.utils.sort_functions import make_dict_score_getter

        sort_by_relevance = make_dict_score_getter(relevance_scores, default=0.0)
        sorted_uids = sorted(
            filtered_knowledge.keys(),
            key=sort_by_relevance,
            reverse=True,
        )[:max_results]

        # Build recommended order (consider prerequisites)
        recommended_order = await self._order_by_prerequisites(sorted_uids)

        return Result.ok(
            {
                "knowledge_units": [filtered_knowledge[uid] for uid in sorted_uids],
                "relevance_scores": {uid: relevance_scores[uid] for uid in sorted_uids},
                "relevance_reasons": {uid: relevance_reasons[uid] for uid in sorted_uids},
                "domain_coverage": {uid: domain_coverage[uid] for uid in sorted_uids},
                "recommended_order": recommended_order,
            }
        )

    async def find_relevant_from_user_context(
        self,
        user_context: UserContext,
        max_results: int = 10,
        min_relevance_score: float = 0.5,
    ) -> Result[dict[str, Any]]:
        """
        Convenience method that extracts activity UIDs from UserContext.

        This is the primary entry point for the UserContext + Askesis
        integration (staged — see module docstring).

        Args:
            user_context: Complete UserContext snapshot
            max_results: Maximum knowledge units to return
            min_relevance_score: Minimum relevance score (0.0-1.0)

        Returns:
            Result[dict[str, Any]]: Same as find_relevant_for_context()
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

    async def _find_knowledge_for_activity(
        self,
        activity_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find knowledge units connected to a specific activity.

        Extracts Entity/KnowledgeUnit nodes from the activity's semantic
        graph context (depth 2), regardless of relationship type.
        """
        if not self.graph_intel:
            return Result.ok([])

        try:
            # Use graph intelligence for semantic context
            context_result = await self.graph_intel.get_semantic_context(
                entity_uid=activity_uid,
                depth=2,
            )

            if context_result.is_error:
                return Result.ok([])

            context = context_result.value or {}

            # Extract knowledge nodes from context
            knowledge_units = []
            nodes = context.get("nodes", [])

            for node in nodes:
                if node.get("label") in ["Entity", "KnowledgeUnit"]:
                    knowledge_units.append(
                        {
                            "uid": node.get("uid", ""),
                            "title": node.get("title", node.get("name", "")),
                            "domain": node.get("domain", ""),
                            "complexity": node.get("complexity", 0.5),
                        }
                    )

            return Result.ok(knowledge_units)

        except NEO4J_EXCEPTIONS as e:
            logger.warning(f"Failed to find knowledge for {activity_uid}: {e}")
            return Result.ok([])
        except Exception as e:  # safety-net: catch unexpected errors
            logger.warning(f"Failed to find knowledge for {activity_uid} ({type(e).__name__}): {e}")
            return Result.ok([])

    async def _order_by_prerequisites(
        self,
        ku_uids: list[str],
    ) -> list[str]:
        """
        Order knowledge units by prerequisite dependencies using topological sort.

        Returns UIDs in order that respects prerequisites
        (learn A before B if B requires A).

        Uses Kahn's algorithm for topological sorting with cycle detection.
        """
        if not ku_uids or not self.graph_intel:
            return ku_uids

        try:
            # Step 1: Build dependency graph from Neo4j
            result = await self.graph_intel.backend.get_prerequisite_graph(ku_uids=ku_uids)

            if result.is_error or not result.value:
                return ku_uids

            # Step 2: Build adjacency map (ku -> its prerequisites)
            prereq_map: dict[str, list[str]] = {uid: [] for uid in ku_uids}
            for record in result.value:
                uid = record.get("uid", "")
                prerequisites = record.get("prerequisites", [])
                if uid in prereq_map:
                    prereq_map[uid] = [p for p in prerequisites if p]

            # Step 3: Topological sort (Kahn's algorithm)
            # in_degree counts how many things depend on each uid
            in_degree: dict[str, int] = {uid: 0 for uid in ku_uids}
            for prereqs in prereq_map.values():
                for prereq in prereqs:
                    if prereq in in_degree:
                        in_degree[prereq] += 1

            # Start with nodes that nothing depends on (leaves in dependency tree)
            # These are the "foundational" knowledge that should be learned first
            queue = [uid for uid, degree in in_degree.items() if degree == 0]
            sorted_uids: list[str] = []

            while queue:
                current = queue.pop(0)
                sorted_uids.append(current)

                # Reduce in-degree for things that had current as prerequisite
                for uid, prereqs in prereq_map.items():
                    if current in prereqs:
                        in_degree[uid] -= 1
                        if in_degree[uid] == 0 and uid not in sorted_uids:
                            queue.append(uid)

            # Add any remaining nodes (handles cycles gracefully)
            remaining = [uid for uid in ku_uids if uid not in sorted_uids]
            sorted_uids.extend(remaining)

            return sorted_uids

        except NEO4J_EXCEPTIONS as e:
            logger.warning("Prerequisite ordering failed, returning original order: %s", e)
            return ku_uids
        except Exception as e:  # safety-net: catch unexpected errors
            logger.warning(
                "Prerequisite ordering failed (%s), returning original order: %s",
                type(e).__name__,
                e,
            )
            return ku_uids
