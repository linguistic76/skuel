"""
Cross-Domain Backend
====================

Read-only backend for cross-domain analytics, queries, and graph intelligence.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Three services migrate here:
- CrossDomainAnalyticsService (12 execute_query calls → 12 methods)
- CrossDomainQueryService (8 execute_query calls → 8 methods)
- GraphIntelligenceService (7 execute_query calls → 7 methods)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query import build_domain_context_with_paths
from core.models.enums import EntityStatus
from core.models.enums.principle_enums import AlignmentLevel
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date, datetime

    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.query_types import QueryIntent


# Explicit-intent edge lenses, keyed by QueryIntent value. Lifted verbatim from the
# retired per-intent hard-coded clauses in graph_context_query_builder (direction-aware
# bucketing fold) so an explicit-intent caller (e.g. Tasks "dependencies"→PREREQUISITE,
# "practice"→PRACTICE) keeps its exact edge slice over the shared producer. A generic
# intent (RELATIONSHIP/EXPLORATORY/SPECIFIC/AGGREGATION) is absent here → empty set →
# the producer traverses every edge type. Registry-sourced callers bypass this map.
_INTENT_EDGE_SETS: dict[str, list[str]] = {
    "hierarchical": ["HAS_CHILD", "PARENT_OF", "CHILD_OF"],
    "prerequisite": ["REQUIRES_KNOWLEDGE", "PREREQUISITE_FOR", "ENABLES"],
    # "practice" used to read ["PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"].
    # Neither of the first two is a RelationshipName member nor exists in the
    # live graph — PRACTICES was the writer-less Event→Ku edge retired in the
    # 2026-07-10 audit — so any alternation built from the old list matched only
    # its third arm. This is a Python list rather than a Cypher string, so
    # SKUEL030 cannot see it and it carried no baseline pair (findings §13).
    #
    # REINFORCES repoints to REINFORCES_KNOWLEDGE, NOT REINFORCES_HABIT. Both
    # are registered and live, but they are different edges: REINFORCES_HABIT is
    # (Task|Event)->Habit, while REINFORCES_KNOWLEDGE is Habit->Ku — the
    # knowledge-practice edge HABITS_CONFIG maps and link_habit_to_knowledge
    # writes. This lens finds practice context FOR knowledge, so it must pair
    # with APPLIES_KNOWLEDGE exactly as the canonical
    # `APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE` alternation does elsewhere
    # (user_context_queries.py:280, curriculum_backends.py:272). Picking the
    # habit arm would have omitted reinforcing habits while pulling in unrelated
    # task/event→habit links (Codex P2 on #737).
    "practice": ["REINFORCES_KNOWLEDGE", "APPLIES_KNOWLEDGE"],
    "goal_achievement": [
        "FULFILLS_GOAL",
        "SUPPORTS_GOAL",
        "REQUIRES_KNOWLEDGE",
        "SUBGOAL_OF",
        "GUIDED_BY_PRINCIPLE",
        "CONTRIBUTES_TO_GOAL",
    ],
}


# ============================================================================
# MODULE-LEVEL CYPHER CONSTANTS (moved from CrossDomainQueryService)
# ============================================================================

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

_TASKS_APPLYING_KNOWLEDGE_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(t:Entity {{entity_type: 'task'}})
MATCH (t)-[r:{RelationshipName.APPLIES_KNOWLEDGE.value}|{RelationshipName.REQUIRES_KNOWLEDGE.value}]->(:Entity {{uid: $knowledge_uid}})
RETURN t.uid AS uid, t.title AS title, type(r) AS rel
LIMIT $limit
"""

_GOALS_FOR_TASKS_BATCH_QUERY = f"""
UNWIND $task_uids AS task_uid
MATCH (t:Entity {{uid: task_uid, entity_type: 'task'}})
OPTIONAL MATCH (t)-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}|{RelationshipName.FULFILLS_GOAL.value}]->(g:Entity {{entity_type: 'goal'}})
WITH task_uid, collect(DISTINCT g) AS goal_nodes
RETURN task_uid AS task_uid,
       [x IN goal_nodes WHERE x IS NOT NULL | {{uid: x.uid, title: x.title}}] AS goals
"""

_ACTIVE_TASK_STATUSES: list[str] = [
    EntityStatus.ACTIVE.value,
    EntityStatus.SCHEDULED.value,
    EntityStatus.BLOCKED.value,
    EntityStatus.PAUSED.value,
]

_COUNT_ACTIVE_TASKS_FOR_GOAL_QUERY = f"""
MATCH (t:Entity {{entity_type: 'task'}})-[:{RelationshipName.FULFILLS_GOAL.value}]->(g:Entity {{uid: $goal_uid, entity_type: 'goal'}})
WHERE t.status IN $active_statuses
RETURN count(t) AS count
"""

_HABIT_ACTIVE_STATUSES: list[str] = [
    EntityStatus.ACTIVE.value,
    "pending",
]

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

_CHOICE_PRINCIPLE_ADHERENCE_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(c:Entity {{entity_type: 'choice'}})
WHERE datetime(c.created_at) >= datetime() - duration({{days: $period_days}})

OPTIONAL MATCH (c)-[:{RelationshipName.ALIGNED_WITH_PRINCIPLE.value}]->(p:Entity {{entity_type: 'principle'}})

WITH c,
     collect(DISTINCT p.uid) AS principle_uids,
     CASE WHEN count(p) > 0 THEN 1 ELSE 0 END AS is_aligned

RETURN
    count(c) AS total_choices,
    sum(is_aligned) AS aligned_count,
    collect({{
        choice_uid: c.uid,
        principles: principle_uids,
        satisfaction: c.satisfaction_score
    }}) AS choice_details
"""

_EVENT_IMPACT_BATCH_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity {{entity_type: 'event'}})
WHERE e.status IN ['scheduled', 'active']
  AND date(e.event_date) >= date($start_date)
  AND date(e.event_date) <= date($end_date)
OPTIONAL MATCH (e)-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}]->(g:Entity {{entity_type: 'goal'}})
OPTIONAL MATCH (e)-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(k:Entity {{entity_type: 'ku'}})
RETURN e.uid AS event_uid,
       count(DISTINCT g) AS goal_count,
       count(DISTINCT k) AS knowledge_count
"""

_CHOICE_CONFLICT_COUNT_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(c:Entity {{entity_type: 'choice'}})
WHERE datetime(c.created_at) >= datetime() - duration({{days: 30}})
MATCH (c)-[:{RelationshipName.CONFLICTS_WITH_PRINCIPLE.value}]->(:Entity {{entity_type: 'principle'}})
RETURN count(DISTINCT c) AS conflict_count
"""

# Rolling 7-day embodiment rate per principle: for each supplied principle UID,
# find the user-owned habits that EMBODY it, then count HabitCompletions in
# the cutoff window. Return raw counts so the service layer computes the rate
# and clamps to [0, 1]. Principles with no embodying habits are dropped from
# the result (caller should default to 0.0).
_EMBODIMENT_RATES_7D_QUERY = f"""
UNWIND $principle_uids AS pid
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(h:Habit)
      -[:{RelationshipName.EMBODIES_PRINCIPLE.value}]->(p:Principle {{uid: pid}})
WITH pid, collect(DISTINCT h.uid) AS habit_uids
OPTIONAL MATCH (hc:HabitCompletion)
WHERE hc.habit_uid IN habit_uids
  AND datetime(hc.completed_at) >= $cutoff
RETURN pid AS principle_uid,
       size(habit_uids) AS habit_count,
       count(hc) AS completion_count
"""

# Local aliases for enum / status tuples used within this backend's queries.
# (FULL_ALIGNMENT_CONNECTION_COUNT moved to core.constants.CrossDomainImpactScore —
# a magic number belongs in core, not re-exported up across the boundary; SKUEL022.)
ALIGNMENT_LEVEL = AlignmentLevel
HABIT_ACTIVE_STATUSES = _HABIT_ACTIVE_STATUSES


class CrossDomainBackend:
    """
    Read-only cross-domain backend for analytics, queries, and graph intelligence.

    Does NOT extend UniversalNeo4jBackend — these are cross-entity queries
    that touch 2+ domain labels and don't fit the single-entity-type model.

    One instance is shared by CrossDomainAnalyticsService,
    CrossDomainQueryService, and GraphIntelligenceService.
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    # ====================================================================
    # ANALYTICS — CrossDomainAnalyticsService methods
    # ====================================================================

    # NOTE: upsert_financial_analytics removed (ADR-052 Phase 5) — native expense
    # module demolished; no FinancialAnalytics / SPENT_IN_CATEGORY nodes are built.

    async def upsert_learning_velocity(
        self, user_uid: str, mastery_score: float, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert LearningVelocity node for knowledge mastery tracking."""
        return await self.executor.execute_query(
            """
            MERGE (velocity:LearningVelocity {user_uid: $user_uid})
            ON CREATE SET
                velocity.kus_mastered = 1,
                velocity.total_mastery_score = $mastery_score,
                velocity.first_mastery_at = datetime($occurred_at)
            ON MATCH SET
                velocity.kus_mastered = velocity.kus_mastered + 1,
                velocity.total_mastery_score = velocity.total_mastery_score + $mastery_score,
                velocity.last_mastery_at = datetime($occurred_at)
            """,
            {
                "user_uid": user_uid,
                "mastery_score": mastery_score,
                "occurred_at": occurred_at,
            },
        )

    async def increment_paths_completed(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Increment paths_completed counter on LearningVelocity node."""
        return await self.executor.execute_query(
            """
            MERGE (velocity:LearningVelocity {user_uid: $user_uid})
            SET velocity.paths_completed = coalesce(velocity.paths_completed, 0) + 1
            """,
            {"user_uid": user_uid},
        )

    async def _upsert_counter_analytics(
        self,
        label: str,
        counter: str,
        first_prop: str,
        last_prop: str,
        user_uid: str,
        occurred_at: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Upsert a per-user counter-analytics node (init-to-1 / increment).

        THE shared body of the productivity/habit/event analytics upserts —
        they differ only in node label and property names, all of which are
        backend-internal literals (injection-safe).
        """
        return await self.executor.execute_query(
            f"""
            MERGE (analytics:{label} {{user_uid: $user_uid}})
            ON CREATE SET
                analytics.{counter} = 1,
                analytics.{first_prop} = datetime($occurred_at)
            ON MATCH SET
                analytics.{counter} = analytics.{counter} + 1,
                analytics.{last_prop} = datetime($occurred_at)
            """,
            {"user_uid": user_uid, "occurred_at": occurred_at},
        )

    async def upsert_productivity_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert ProductivityAnalytics node for task completion tracking."""
        return await self._upsert_counter_analytics(
            "ProductivityAnalytics",
            "tasks_completed",
            "first_completion_at",
            "last_completion_at",
            user_uid,
            occurred_at,
        )

    async def upsert_habit_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert HabitAnalytics node for habit completion tracking."""
        return await self._upsert_counter_analytics(
            "HabitAnalytics",
            "total_completions",
            "first_completion_at",
            "last_completion_at",
            user_uid,
            occurred_at,
        )

    async def upsert_event_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert EventAnalytics node for event attendance tracking."""
        return await self._upsert_counter_analytics(
            "EventAnalytics",
            "events_attended",
            "first_attendance_at",
            "last_attendance_at",
            user_uid,
            occurred_at,
        )

    async def get_learning_velocity_metrics(
        self, user_uid: str, start_date: str
    ) -> Result[list[dict[str, Any]]]:
        """Get LearningVelocity node with recent masteries.

        The LearningVelocity node itself is live (upserted by
        `upsert_learning_velocity`); only its `<-[:HAS_VELOCITY]-(:MasteryRecord)`
        satellites were writer-less. Recent masteries now come from the user's
        own MASTERED edges — the live record of the same event.

        The "when was this mastered" stamp is coalesced across the four MASTERED
        writers, which disagree on its name. Creation stamps come first
        (`mastered_at` / `achieved_at` / `created_at`) — all ON CREATE for the
        same event, and exactly one writer creates any given edge, so coalesce
        picks the only non-null rather than hiding a newer one.

        `last_practiced` is the deliberate LAST fallback, and it is required:
        `UserBackend.record_knowledge_mastery` — the writer behind the pathways
        progress route — stamps NO creation timestamp at all, only
        `last_practiced`. Without this arm its edges read as undated and drop
        out of every velocity window (Codex P2 on #737). Ordering it last keeps
        it from overriding a real creation stamp on the writers that set both.

        `time_to_mastery_hours` is written by just one writer; sum() ignores the
        nulls from the others.

        **`total_kus` is counted here rather than read off the node.** The
        node's `velocity.kus_mastered` is an EVENT-driven counter — only
        `upsert_learning_velocity`, behind the `KnowledgeMastered` handler,
        increments it — while `recent_kus` counts MASTERED edges from all four
        writers. Mixing the two let the service compute
        `previous = total - recent` as a NEGATIVE number whenever a mastery
        landed through a non-event path such as the pathways progress route
        (Codex P2 on #737). Both totals now come from the same source, so the
        subtraction is well-founded by construction. `paths_completed` still
        comes off the node — it has its own counter and no edge equivalent.

        **Anchored on the User; the velocity node is OPTIONAL.** Requiring
        `MATCH (velocity:LearningVelocity ...)` meant a user whose masteries all
        came through non-event writers — no `KnowledgeMastered` event, so no
        node was ever upserted — produced zero rows and reported `no_data`
        despite having live MASTERED edges (Codex P2 on #737). That is the same
        mandatory-match trap as the totals bug above, one clause higher up: the
        edges are now the primary source, so the node must not gate them.
        Callers must treat `velocity` as nullable.
        """
        return await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (velocity:LearningVelocity {user_uid: $user_uid})
            OPTIONAL MATCH (u)-[m:MASTERED]->(:Entity)
            WITH velocity, m,
                 coalesce(m.mastered_at, m.achieved_at, m.created_at, m.last_practiced)
                     AS mastered_when
            WITH velocity,
                 count(m) AS total_kus,
                 count(CASE WHEN mastered_when >= datetime($start_date) THEN 1 END)
                     AS recent_kus,
                 sum(CASE WHEN mastered_when >= datetime($start_date)
                          THEN m.time_to_mastery_hours END) AS total_hours
            RETURN velocity, total_kus, recent_kus, total_hours
            """,
            {"user_uid": user_uid, "start_date": start_date},
        )

    # NOTE: get_spending_by_category removed (ADR-052 Phase 5) — native expense
    # module demolished; no FinancialAnalytics nodes to read.

    # NOTE: get_journal_analytics removed (SKUEL030 tranche 3) — it read a
    # JournalAnalytics node whose upsert writer went away with ADR-054's
    # journal/submissions consolidation, unlike its three sibling analytics
    # nodes (Learning/Productivity/Habit), which each still have one. It had
    # matched zero rows ever since, so `get_mood_analysis` and the
    # /api/analytics/mood-analysis endpoint it backed returned placeholder
    # constants for every user; both went with it.

    # NOTE: get_financial_goal_with_expenses removed (ADR-052 Phase 5) — native
    # expense module demolished; no Expense nodes link to goals.

    async def get_productivity_analytics(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get ProductivityAnalytics node for task completion metrics."""
        return await self.executor.execute_query(
            """
            MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
            RETURN analytics
            """,
            {"user_uid": user_uid},
        )

    async def get_habit_analytics(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get HabitAnalytics node for habit consistency metrics."""
        return await self.executor.execute_query(
            """
            MATCH (analytics:HabitAnalytics {user_uid: $user_uid})
            RETURN analytics
            """,
            {"user_uid": user_uid},
        )

    # ====================================================================
    # CROSS-DOMAIN QUERIES — CrossDomainQueryService methods
    # ====================================================================

    async def get_principle_alignment_evidence(
        self, principle_uid: str, user_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Find goals and habits aligned with a principle via explicit edges."""
        return await self.executor.execute_query(
            _PRINCIPLE_ALIGNMENT_EVIDENCE_QUERY,
            {"principle_uid": principle_uid, "user_uid": user_uid},
        )

    async def get_embodiment_rates_7d(
        self, principle_uids: list[str], user_uid: str, cutoff: datetime
    ) -> Result[list[dict[str, Any]]]:
        """Per-principle habit-completion counts over the window ending now."""
        return await self.executor.execute_query(
            _EMBODIMENT_RATES_7D_QUERY,
            {"principle_uids": principle_uids, "user_uid": user_uid, "cutoff": cutoff},
        )

    async def get_tasks_applying_knowledge(
        self, knowledge_uid: str, user_uid: str, limit: int
    ) -> Result[list[dict[str, Any]]]:
        """Find tasks engaging with a knowledge unit via APPLIES/REQUIRES_KNOWLEDGE."""
        return await self.executor.execute_query(
            _TASKS_APPLYING_KNOWLEDGE_QUERY,
            {"knowledge_uid": knowledge_uid, "user_uid": user_uid, "limit": limit},
        )

    async def get_goals_for_tasks_batch(self, task_uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Find goals each task contributes to or fulfills — one round-trip for N tasks."""
        return await self.executor.execute_query(
            _GOALS_FOR_TASKS_BATCH_QUERY,
            {"task_uids": task_uids},
        )

    async def count_active_tasks_for_goal(self, goal_uid: str) -> Result[list[dict[str, Any]]]:
        """Count non-terminal tasks linked to a goal via FULFILLS_GOAL."""
        return await self.executor.execute_query(
            _COUNT_ACTIVE_TASKS_FOR_GOAL_QUERY,
            {"goal_uid": goal_uid, "active_statuses": _ACTIVE_TASK_STATUSES},
        )

    async def get_habit_knowledge_reinforcement(
        self, user_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Fetch active habits with their reinforced KUs."""
        return await self.executor.execute_query(
            _HABIT_KNOWLEDGE_REINFORCEMENT_QUERY,
            {"user_uid": user_uid, "active_statuses": _HABIT_ACTIVE_STATUSES},
        )

    async def get_choice_principle_adherence(
        self, user_uid: str, period_days: int
    ) -> Result[list[dict[str, Any]]]:
        """Get choice-principle adherence data over a period."""
        return await self.executor.execute_query(
            _CHOICE_PRINCIPLE_ADHERENCE_QUERY,
            {"user_uid": user_uid, "period_days": period_days},
        )

    async def get_choice_conflict_count(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Count recent choices with principle conflicts."""
        return await self.executor.execute_query(
            _CHOICE_CONFLICT_COUNT_QUERY,
            {"user_uid": user_uid},
        )

    async def get_event_impact_batch(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[list[dict[str, Any]]]:
        """Batch-fetch goal + knowledge counts for events in a date range."""
        return await self.executor.execute_query(
            _EVENT_IMPACT_BATCH_QUERY,
            {
                "user_uid": user_uid,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

    # ====================================================================
    # GRAPH INTELLIGENCE — GraphIntelligenceService methods
    # ====================================================================

    async def find_knowledge_hubs(
        self,
        domain_filter: str,
        params: dict[str, Any],
    ) -> Result[list[dict[str, Any]]]:
        """Find highly connected knowledge units using degree centrality."""
        query = f"""
        MATCH (ku:Entity)
        {domain_filter}
        OPTIONAL MATCH (ku)-[r WHERE coalesce(r.confidence, 1.0) >= $min_confidence]-()
        WITH ku, count(r) as total_connections
        WHERE total_connections >= $min_connections

        // Count incoming and outgoing separately
        OPTIONAL MATCH (ku)<-[r_in WHERE coalesce(r_in.confidence, 1.0) >= $min_confidence]-()
        WITH ku, total_connections, count(r_in) as incoming_count
        OPTIONAL MATCH (ku)-[r_out WHERE coalesce(r_out.confidence, 1.0) >= $min_confidence]->()
        WITH ku, total_connections, incoming_count, count(r_out) as outgoing_count

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               total_connections,
               incoming_count,
               outgoing_count,
               toFloat(total_connections) as centrality_score
        ORDER BY total_connections DESC
        LIMIT $limit
        """
        return await self.executor.execute_query(query, params)

    async def find_similar_knowledge(
        self, uid: str, min_similarity: float, limit: int
    ) -> Result[list[dict[str, Any]]]:
        """Find similar knowledge units via Jaccard similarity on shared neighbors."""
        return await self.executor.execute_query(
            """
            // Find shared neighbors (any relationship direction)
            MATCH (ku1:Entity {uid: $uid})-[]-(shared)-[]-(ku2:Entity)
            WHERE ku1 <> ku2
            WITH ku1, ku2, count(DISTINCT shared) as shared_count

            // Count ku1's total neighbors
            MATCH (ku1)-[]-(ku1_neighbor)
            WITH ku1, ku2, shared_count, count(DISTINCT ku1_neighbor) as ku1_degree

            // Count ku2's total neighbors
            MATCH (ku2)-[]-(ku2_neighbor)
            WITH ku1, ku2, shared_count, ku1_degree,
                 count(DISTINCT ku2_neighbor) as ku2_degree

            // Calculate Jaccard similarity
            WITH ku2, shared_count, ku1_degree, ku2_degree,
                 toFloat(shared_count) / (ku1_degree + ku2_degree - shared_count) as similarity

            WHERE similarity >= $min_similarity

            RETURN ku2.uid as uid,
                   ku2.title as title,
                   ku2.domain as domain,
                   similarity,
                   shared_count,
                   (ku1_degree + ku2_degree - shared_count) as total_neighbors
            ORDER BY similarity DESC
            LIMIT $limit
            """,
            {"uid": uid, "min_similarity": min_similarity, "limit": limit},
        )

    async def analyze_prerequisite_depth(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Analyze prerequisite chain depth and complexity for a knowledge unit."""
        return await self.executor.execute_query(
            """
            // Find all prerequisite paths
            MATCH path = (end:Entity {uid: $uid})<-[:REQUIRES_KNOWLEDGE*]-(start)
            WHERE NOT (start)<-[:REQUIRES_KNOWLEDGE]-()

            WITH path,
                 length(path) as depth,
                 [node in nodes(path) | node.uid] as path_uids

            // Aggregate statistics
            WITH collect(DISTINCT path) as all_paths,
                 max(depth) as max_depth,
                 avg(depth) as avg_depth,
                 collect(DISTINCT path_uids[size(path_uids)-1]) as root_uids

            RETURN max_depth,
                   avg_depth,
                   size(all_paths) as total_paths,
                   root_uids,
                   max_depth * size(all_paths) as complexity_score
            """,
            {"uid": uid},
        )

    async def find_learning_clusters(
        self,
        domain_filter: str,
        params: dict[str, Any],
    ) -> Result[list[dict[str, Any]]]:
        """Find tightly connected knowledge clusters via triangle density."""
        query = f"""
        // Find knowledge units with neighbors
        MATCH (ku:Entity)
        {domain_filter}
        MATCH (ku)-[r]-(neighbor:Entity)
        WITH ku, count(DISTINCT neighbor) as neighbor_count
        WHERE neighbor_count >= 2

        // Count triangles (ku-n1-n2-ku closed patterns)
        MATCH (ku)-[]-(n1:Entity)-[]-(n2:Entity)-[]-(ku)
        WHERE n1 <> n2 AND id(n1) < id(n2)
        WITH ku, neighbor_count, count(*) as triangles

        // Calculate clustering coefficient (density)
        WITH ku, neighbor_count, triangles,
             toFloat(triangles) / (neighbor_count * (neighbor_count - 1) / 2) as density

        WHERE density >= $min_density

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               neighbor_count,
               triangles,
               density
        ORDER BY density DESC, neighbor_count DESC
        LIMIT $limit
        """
        return await self.executor.execute_query(query, params)

    async def calculate_knowledge_importance(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Calculate composite importance score for a knowledge unit."""
        return await self.executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})

            // Metric 1: Degree centrality
            OPTIONAL MATCH (ku)-[r]-()
            WITH ku, count(r) as degree,
                 avg(coalesce(r.confidence, 1.0)) as avg_confidence

            // Metric 2: Prerequisite importance (how many depend on this)
            OPTIONAL MATCH (ku)<-[:REQUIRES_KNOWLEDGE*]-(dependent)
            WITH ku, degree, avg_confidence, count(DISTINCT dependent) as dependents

            // Metric 3: Clustering coefficient
            OPTIONAL MATCH (ku)-[]-(n1)-[]-(n2)-[]-(ku)
            WHERE n1 <> n2 AND id(n1) < id(n2)
            WITH ku, degree, avg_confidence, dependents, count(*) as triangles

            // Calculate composite score
            WITH ku,
                 degree,
                 dependents,
                 triangles,
                 avg_confidence,
                 CASE WHEN degree >= 2
                      THEN toFloat(triangles) / (degree * (degree - 1) / 2)
                      ELSE 0.0
                 END as clustering

            RETURN toFloat(degree) as degree_centrality,
                   toFloat(dependents) as prerequisite_importance,
                   clustering as cluster_coefficient,
                   avg_confidence,
                   (degree * 0.3 + dependents * 0.4 + clustering * 10 * 0.3) as importance_score
            """,
            {"uid": uid},
        )

    async def query_with_intent(
        self,
        intent: QueryIntent,
        depth: int,
        uid: str,
        relationship_types: list[str] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Build an intent graph-context traversal over the shared producer and run it.

        Direction-aware bucketing (Convergence Phase 2): the intent path now runs the SAME
        incident-edge-attributed producer (``build_domain_context_with_paths``) as the
        bucketed cross-domain-context reader — no parallel flat Cypher. The edge vocabulary
        is registry-sourced (``relationship_types``, mechanism B) when supplied; otherwise
        the intent selects a slice from ``_INTENT_EDGE_SETS`` (the explicit-intent lenses
        lifted verbatim from the retired hard-coded clauses), and a generic intent
        (``RELATIONSHIP``/``EXPLORATORY``/…) → empty set → every edge type.

        The pre-aggregation ``limit=100`` is applied **only on the registry-sourced path**
        (``relationship_types`` supplied) — the sole branch the retired builder genuinely
        capped (``_build_filtered_context_query``). The explicit-intent branches
        (HIERARCHICAL/PREREQUISITE/PRACTICE/GOAL_ACHIEVEMENT) had NO cap, and the generic
        branch's trailing LIMIT was a post-aggregation no-op (effectively unbounded), so
        capping them here would silently drop nodes for explicit-intent callers on dense
        graphs (the regression Codex caught on PR #243). Faithful = cap only what was
        capped.

        Returns one record ``{center_uid, domain_context}``; ``domain_context`` is the
        attributed node list the service-layer transformer de-dups into a ``GraphContext``.
        See: /docs/roadmap/intent-traversal-registry-convergence.md
        """
        from core.ports import get_enum_value

        registry_sourced = bool(relationship_types)
        edge_set = relationship_types or _INTENT_EDGE_SETS.get(get_enum_value(intent), [])
        query, params = build_domain_context_with_paths(
            node_uid=uid,
            node_label=None,
            relationship_types=edge_set,
            depth=depth,
            min_confidence=0.0,
            bidirectional=True,
            limit=100 if registry_sourced else None,
        )
        return await self.executor.execute_query(query, params)

    async def get_entity_labels(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Get an entity node and its labels for domain determination."""
        # :Entity — a :Content shadow shares its entity's uid; unlabeled, this
        # would return two rows and label reads become ambiguous (G13).
        return await self.executor.execute_query(
            """
            MATCH (n:Entity {uid: $uid})
            RETURN n, labels(n) as labels
            """,
            {"uid": uid},
        )

    async def get_ku_titles_and_tags(self) -> Result[list[dict[str, Any]]]:
        """Get all Ku titles and tags for skill vocabulary derivation."""
        return await self.executor.execute_query(
            """
            MATCH (k:Ku:Entity)
            RETURN k.title AS title, k.tags AS tags
            """,
            {},
        )

    async def get_prerequisite_graph(self, ku_uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Get prerequisite edges between a set of KUs for topological sorting."""
        return await self.executor.execute_query(
            """
            UNWIND $ku_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WHERE prereq.uid IN $ku_uids
            RETURN ku.uid AS uid, collect(prereq.uid) AS prerequisites
            """,
            {"ku_uids": ku_uids},
        )

    async def get_user_learning_state(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get mastered KUs and enrolled learning paths for a user."""
        return await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[:MASTERED]->(ku:Entity)
            WITH u, collect(DISTINCT ku.uid) as mastered
            OPTIONAL MATCH (u)-[:ENROLLED_IN]->(lp:LearningPath)
            OPTIONAL MATCH (lp)-[:CONTAINS]->(step:PathStep)
            WITH u, mastered, lp, count(DISTINCT step) AS total_steps
            WITH u, mastered,
                 collect(DISTINCT {
                     path_uid: lp.uid,
                     total_steps: total_steps,
                     title: lp.title
                 }) as paths
            RETURN mastered, paths
            """,
            {"user_uid": user_uid},
        )

    async def get_knowledge_patterns(self, entity_uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Analyze knowledge patterns across a set of entities."""
        return await self.executor.execute_query(
            """
            MATCH (e)
            WHERE e.uid IN $entity_uids
            OPTIONAL MATCH (e)-[:APPLIES_KNOWLEDGE|REQUIRES_KNOWLEDGE]->(ku:Entity)
            WITH ku, count(DISTINCT e) as usage_count
            WHERE ku IS NOT NULL
            RETURN
                collect({
                    uid: ku.uid,
                    title: ku.title,
                    usage_count: usage_count,
                    domain: ku.domain
                }) as knowledge_units
            """,
            {"entity_uids": entity_uids},
        )

    async def find_cross_domain_connections(
        self, entity_uid: str, target_domains: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Find connections from an entity to targets in specified domain labels."""
        return await self.executor.execute_query(
            """
            MATCH (source:Entity {uid: $entity_uid})
            MATCH (source)-[r]-(target)
            WHERE any(label IN labels(target) WHERE label IN $target_domains)
            RETURN
                collect({
                    target_uid: target.uid,
                    target_labels: labels(target),
                    relationship_type: type(r),
                    properties: properties(target)
                }) as connections
            """,
            {"entity_uid": entity_uid, "target_domains": target_domains},
        )

    # ========================================================================
    # ADMIN STATS — System-wide aggregation queries (from AdminStatsService)
    # ========================================================================

    async def get_entity_system_metrics(self) -> Result[list[dict[str, Any]]]:
        """System-wide learning metrics: entity totals and interaction counts."""
        return await self.executor.execute_query(
            """
            OPTIONAL MATCH (ku:Entity)
            WITH count(DISTINCT ku) AS total_kus
            OPTIONAL MATCH (:User)-[v:VIEWED]->(:Entity)
            WITH total_kus, count(v) AS total_viewed
            OPTIONAL MATCH (:User)-[:IN_PROGRESS]->(:Entity)
            WITH total_kus, total_viewed, count(*) AS total_in_progress
            OPTIONAL MATCH (:User)-[:MASTERED]->(:Entity)
            WITH total_kus, total_viewed, total_in_progress, count(*) AS total_mastered
            OPTIONAL MATCH (:User)-[:BOOKMARKED]->(:Entity)
            WITH total_kus, total_viewed, total_in_progress, total_mastered,
                 count(*) AS total_bookmarked
            OPTIONAL MATCH (u:User)
                WHERE EXISTS { (u)-[:VIEWED|IN_PROGRESS|MASTERED|BOOKMARKED]->(:Entity) }
            RETURN total_kus, total_viewed, total_in_progress, total_mastered,
                   total_bookmarked, count(DISTINCT u) AS users_with_progress
            """
        )

    async def get_all_users_progress(self) -> Result[list[dict[str, Any]]]:
        """Per-user KU progress summary for admin dashboard."""
        return await self.executor.execute_query(
            """
            MATCH (u:User)
            WHERE u.uid <> 'user_system'
            OPTIONAL MATCH (u)-[:VIEWED]->(ku1:Entity)
            WITH u, count(DISTINCT ku1) AS viewed_count
            OPTIONAL MATCH (u)-[:IN_PROGRESS]->(ku2:Entity)
            WITH u, viewed_count, count(DISTINCT ku2) AS in_progress_count
            OPTIONAL MATCH (u)-[:MASTERED]->(ku3:Entity)
            WITH u, viewed_count, in_progress_count, count(DISTINCT ku3) AS mastered_count
            OPTIONAL MATCH (u)-[:BOOKMARKED]->(ku4:Entity)
            WITH u, viewed_count, in_progress_count, mastered_count,
                 count(DISTINCT ku4) AS bookmarked_count
            RETURN u.uid AS uid,
                   u.display_name AS display_name,
                   u.title AS username,
                   u.role AS role,
                   viewed_count,
                   in_progress_count,
                   mastered_count,
                   bookmarked_count,
                   (viewed_count + in_progress_count + mastered_count) AS total_interactions
            ORDER BY total_interactions DESC
            """
        )

    async def get_user_ku_detail(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Detailed KU progress for one user."""
        return await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            OPTIONAL MATCH (u)-[v:VIEWED]->(vku:Entity)
            WITH u, collect(DISTINCT {
                uid: vku.uid, title: vku.title,
                view_count: v.view_count,
                first_viewed_at: toString(v.first_viewed_at),
                last_viewed_at: toString(v.last_viewed_at)
            }) AS viewed_kus

            OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(pku:Entity)
            WITH u, viewed_kus, collect(DISTINCT {
                uid: pku.uid, title: pku.title,
                started_at: toString(p.started_at),
                progress_score: p.progress_score
            }) AS progress_kus

            OPTIONAL MATCH (u)-[m:MASTERED]->(mku:Entity)
            WITH u, viewed_kus, progress_kus, collect(DISTINCT {
                uid: mku.uid, title: mku.title,
                mastered_at: toString(m.mastered_at),
                mastery_score: m.mastery_score,
                method: m.method
            }) AS mastered_kus

            OPTIONAL MATCH (u)-[b:BOOKMARKED]->(bku:Entity)
            WITH viewed_kus, progress_kus, mastered_kus, collect(DISTINCT {
                uid: bku.uid, title: bku.title,
                bookmarked_at: toString(b.bookmarked_at)
            }) AS bookmarked_kus

            RETURN viewed_kus, progress_kus, mastered_kus, bookmarked_kus
            """,
            {"user_uid": user_uid},
        )

    async def get_user_submissions_detail(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Exercise submissions for a user with linked exercise and report count."""
        return await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:OWNS]->(sub:Entity:UserEntry)
            WHERE EXISTS { (sub)-[:FULFILLS_EXERCISE|FULFILLS_REVISED_EXERCISE]->() }
            OPTIONAL MATCH (sub)-[:FULFILLS_EXERCISE]->(ex:Entity)
            OPTIONAL MATCH (report:Entity {entity_type: 'entry_report'})-[:REPORT_FOR]->(sub)
            RETURN sub.uid AS submission_uid,
                   sub.title AS title,
                   sub.status AS status,
                   toString(sub.created_at) AS submitted_at,
                   ex.uid AS exercise_uid,
                   ex.title AS exercise_title,
                   count(report) AS report_count
            ORDER BY sub.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_user_detail_stats(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Cross-domain activity stats for a specific user."""
        return await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
            WITH u, count(DISTINCT t) AS tasks_total
            OPTIONAL MATCH (u)-[:OWNS]->(tc:Task)
                WHERE tc.status IN ['completed', 'done']
            WITH u, tasks_total, count(DISTINCT tc) AS tasks_completed

            OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
            WITH u, tasks_total, tasks_completed, count(DISTINCT g) AS goals_total
            OPTIONAL MATCH (u)-[:OWNS]->(ga:Goal)
                WHERE ga.status IN ['active', 'in_progress']
            With u, tasks_total, tasks_completed, goals_total,
                 count(DISTINCT ga) AS goals_active

            OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 count(DISTINCT h) AS habits_total
            OPTIONAL MATCH (u)-[:OWNS]->(ha:Habit)
                WHERE ha.status IN ['active', 'in_progress']
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, count(DISTINCT ha) AS habits_active

            OPTIONAL MATCH (u)-[:OWNS]->(e:Event)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, count(DISTINCT e) AS events_total

            OPTIONAL MATCH (u)-[:OWNS]->(c:Choice)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total,
                 count(DISTINCT c) AS choices_total

            OPTIONAL MATCH (u)-[:OWNS]->(p:Principle)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 count(DISTINCT p) AS principles_total

            OPTIONAL MATCH (u)-[:VIEWED]->(kv:Entity)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, count(DISTINCT kv) AS ku_viewed
            OPTIONAL MATCH (u)-[:IN_PROGRESS]->(kp:Entity)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed,
                 count(DISTINCT kp) AS ku_in_progress
            OPTIONAL MATCH (u)-[:MASTERED]->(km:Entity)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed, ku_in_progress,
                 count(DISTINCT km) AS ku_mastered

            OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed, ku_in_progress, ku_mastered,
                 count(DISTINCT s) AS session_count
            OPTIONAL MATCH (u)-[:HAD_AUTH_EVENT]->(ae:AuthEvent)
                WHERE ae.event_type = 'LOGIN_SUCCESS'
            RETURN tasks_total, tasks_completed, goals_total, goals_active,
                   habits_total, habits_active, events_total, choices_total,
                   principles_total, ku_viewed, ku_in_progress, ku_mastered,
                   session_count, count(DISTINCT ae) AS login_count
            """,
            {"user_uid": user_uid},
        )

    async def get_activity_entity_counts(self) -> Result[list[dict[str, Any]]]:
        """System-wide entity counts for admin analytics dashboard."""
        return await self.executor.execute_query(
            """
            OPTIONAL MATCH (t:Task)
            WITH count(t) AS tasks_created
            OPTIONAL MATCH (h:Habit)
            WITH tasks_created, count(h) AS habits_active
            OPTIONAL MATCH (g:Goal)
            RETURN tasks_created, habits_active, count(g) AS goals_active
            """
        )

    async def get_user_role_counts(self) -> Result[list[dict[str, Any]]]:
        """User counts grouped by role."""
        return await self.executor.execute_query(
            """
            MATCH (u:User)
            WHERE u.uid <> 'user_system'
            RETURN u.role AS role, count(u) AS cnt
            """
        )

    async def get_users_with_activity_counts(
        self, where_str: str, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]:
        """Users list with entity counts for admin table.

        Args:
            where_str: Pre-built WHERE clause (parameterized, no user input interpolation)
            params: Query parameters for the WHERE clause
        """
        return await self.executor.execute_query(
            f"""
            MATCH (u:User)
            WHERE {where_str}

            OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
            WITH u, count(DISTINCT t) AS task_count
            OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
            With u, task_count, count(DISTINCT g) AS goal_count
            OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
            WITH u, task_count, goal_count, count(DISTINCT h) AS habit_count
            OPTIONAL MATCH (u)-[:MASTERED]->(km:Entity)
            WITH u, task_count, goal_count, habit_count,
                 count(DISTINCT km) AS ku_mastered

            RETURN u.uid AS uid,
                   u.title AS username,
                   u.display_name AS display_name,
                   u.email AS email,
                   u.role AS role,
                   u.is_active AS is_active,
                   u.updated_at AS last_login_at,
                   task_count, goal_count, habit_count, ku_mastered
            ORDER BY u.title
            """,
            params,
        )

    async def get_recent_activities(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Recent activities across tasks, knowledge, and goals for a user."""
        return await self.executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            // Recent completed tasks
            OPTIONAL MATCH (u)-[:HAS_TASK]->(t:Task {status: 'completed'})
            WHERE t.completed_at IS NOT NULL
            WITH u, collect({
                type: 'task',
                action: 'completed',
                entity_uid: t.uid,
                entity_title: t.title,
                timestamp: t.completed_at
            })[0..5] as task_activities

            // Recent mastered knowledge
            OPTIONAL MATCH (u)-[m:MASTERED]->(ku:Entity)
            WHERE m.mastered_at IS NOT NULL
            WITH u, task_activities, collect({
                type: 'knowledge',
                action: 'mastered',
                entity_uid: ku.uid,
                entity_title: ku.title,
                timestamp: m.mastered_at
            })[0..5] as knowledge_activities

            // Recent completed goals
            OPTIONAL MATCH (u)-[:HAS_GOAL]->(g:Goal {status: 'completed'})
            WHERE g.completed_at IS NOT NULL
            With task_activities, knowledge_activities, collect({
                type: 'goal',
                action: 'completed',
                entity_uid: g.uid,
                entity_title: g.title,
                timestamp: g.completed_at
            })[0..5] as goal_activities

            // Combine and sort by timestamp
            UNWIND (task_activities + knowledge_activities + goal_activities) as activity
            RETURN activity
            ORDER BY activity.timestamp DESC
            LIMIT 20
            """,
            {"user_uid": user_uid},
        )

    async def get_journal_entries_in_range(
        self,
        user_uid: str,
        start_datetime: str,
        end_datetime: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get journal source entries within a date range.

        After ADR-054 the former `:JeInput` nodes are `:UserEntry` with
        `pipeline='transcribe_and_structure'` — the audio source of the
        journal flow. The LLM-structured child (pipeline='none', linked via
        TRANSFORMS) is intentionally not included here: analytics consumes
        the source's `processed_content` (transcript) plus the metadata
        fields the migration preserved on the source node.
        """
        return await self.executor.execute_query(
            """
            MATCH (j:UserEntry {user_uid: $user_uid})
            WHERE j.pipeline = 'transcribe_and_structure'
              AND datetime(j.created_at) >= datetime($start_datetime)
              AND datetime(j.created_at) <= datetime($end_datetime)
            RETURN j.uid as uid,
                   coalesce(j.processed_content, j.content) as processed_content,
                   {title: j.title, summary: j.summary, themes: j.key_topics} as metadata,
                   j.created_at as created_at
            ORDER BY j.created_at DESC
            """,
            {
                "user_uid": user_uid,
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
            },
        )


__all__ = [
    "ALIGNMENT_LEVEL",
    "CrossDomainBackend",
    "HABIT_ACTIVE_STATUSES",
]
