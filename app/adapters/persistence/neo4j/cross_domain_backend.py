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

from core.models.enums import EntityStatus
from core.models.enums.principle_enums import AlignmentLevel
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date

    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


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

_GOALS_FOR_TASK_QUERY = f"""
MATCH (t:Entity {{uid: $task_uid, entity_type: 'task'}})
MATCH (t)-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}|{RelationshipName.FULFILLS_GOAL.value}]->(g:Entity {{entity_type: 'goal'}})
RETURN DISTINCT g.uid AS uid, g.title AS title
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
WHERE c.created_at >= datetime() - duration({{days: $period_days}})

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
  AND e.event_date >= date($start_date)
  AND e.event_date <= date($end_date)
OPTIONAL MATCH (e)-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}]->(g:Entity {{entity_type: 'goal'}})
OPTIONAL MATCH (e)-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(k:Entity {{entity_type: 'ku'}})
RETURN e.uid AS event_uid,
       count(DISTINCT g) AS goal_count,
       count(DISTINCT k) AS knowledge_count
"""

_CHOICE_CONFLICT_COUNT_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(c:Entity {{entity_type: 'choice'}})
WHERE c.created_at >= datetime() - duration({{days: 30}})
MATCH (c)-[:{RelationshipName.CONFLICTS_WITH_PRINCIPLE.value}]->(:Entity {{entity_type: 'principle'}})
RETURN count(DISTINCT c) AS conflict_count
"""

# Re-export constants needed by CrossDomainQueryService for score calculation
FULL_ALIGNMENT_CONNECTION_COUNT: float = 5.0
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

    async def upsert_financial_analytics(
        self, user_uid: str, amount: float, category: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert FinancialAnalytics node and SPENT_IN_CATEGORY edge."""
        return await self.executor.execute_query(
            """
            MERGE (analytics:FinancialAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.total_expenses = $amount,
                analytics.expense_count = 1,
                analytics.first_expense_at = datetime($occurred_at)
            ON MATCH SET
                analytics.total_expenses = analytics.total_expenses + $amount,
                analytics.expense_count = analytics.expense_count + 1,
                analytics.last_expense_at = datetime($occurred_at)

            WITH analytics
            MERGE (analytics)-[r:SPENT_IN_CATEGORY {category: $category}]->(cat:ExpenseCategory {name: $category})
            ON CREATE SET r.total_amount = $amount, r.count = 1
            ON MATCH SET r.total_amount = r.total_amount + $amount, r.count = r.count + 1
            """,
            {
                "user_uid": user_uid,
                "amount": amount,
                "category": category,
                "occurred_at": occurred_at,
            },
        )

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

    async def upsert_productivity_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert ProductivityAnalytics node for task completion tracking."""
        return await self.executor.execute_query(
            """
            MERGE (analytics:ProductivityAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.tasks_completed = 1,
                analytics.first_completion_at = datetime($occurred_at)
            ON MATCH SET
                analytics.tasks_completed = analytics.tasks_completed + 1,
                analytics.last_completion_at = datetime($occurred_at)
            """,
            {"user_uid": user_uid, "occurred_at": occurred_at},
        )

    async def upsert_habit_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert HabitAnalytics node for habit completion tracking."""
        return await self.executor.execute_query(
            """
            MERGE (analytics:HabitAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.total_completions = 1,
                analytics.first_completion_at = datetime($occurred_at)
            ON MATCH SET
                analytics.total_completions = analytics.total_completions + 1,
                analytics.last_completion_at = datetime($occurred_at)
            """,
            {"user_uid": user_uid, "occurred_at": occurred_at},
        )

    async def upsert_event_analytics(
        self, user_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:
        """Upsert EventAnalytics node for event attendance tracking."""
        return await self.executor.execute_query(
            """
            MERGE (analytics:EventAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.events_attended = 1,
                analytics.first_attendance_at = datetime($occurred_at)
            ON MATCH SET
                analytics.events_attended = analytics.events_attended + 1,
                analytics.last_attendance_at = datetime($occurred_at)
            """,
            {"user_uid": user_uid, "occurred_at": occurred_at},
        )

    async def get_learning_velocity_metrics(
        self, user_uid: str, start_date: str
    ) -> Result[list[dict[str, Any]]]:
        """Get LearningVelocity node with recent mastery records."""
        return await self.executor.execute_query(
            """
            MATCH (velocity:LearningVelocity {user_uid: $user_uid})
            OPTIONAL MATCH (velocity)<-[:HAS_VELOCITY]-(ku:MasteryRecord)
            WHERE datetime(ku.mastered_at) >= datetime($start_date)
            WITH velocity, count(ku) as recent_kus, sum(ku.time_to_mastery_hours) as total_hours
            RETURN velocity, recent_kus, total_hours
            """,
            {"user_uid": user_uid, "start_date": start_date},
        )

    async def get_spending_by_category(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get spending breakdown by category from FinancialAnalytics."""
        return await self.executor.execute_query(
            """
            MATCH (analytics:FinancialAnalytics {user_uid: $user_uid})-[r:SPENT_IN_CATEGORY]->(cat:ExpenseCategory)
            RETURN cat.name as category, r.total_amount as amount, r.count as count
            ORDER BY r.total_amount DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_journal_analytics(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get JournalAnalytics node for mood analysis."""
        return await self.executor.execute_query(
            """
            MATCH (analytics:JournalAnalytics {user_uid: $user_uid})
            RETURN analytics
            """,
            {"user_uid": user_uid},
        )

    async def get_financial_goal_with_expenses(self, goal_uid: str) -> Result[list[dict[str, Any]]]:
        """Get goal with linked expenses via SUPPORTS_GOAL."""
        return await self.executor.execute_query(
            """
            MATCH (goal:Goal {uid: $goal_uid})
            OPTIONAL MATCH (goal)<-[:SUPPORTS_GOAL]-(expense:Expense)
            WITH goal, collect(expense) as expenses, sum(expense.amount) as total
            RETURN goal, expenses, total
            """,
            {"goal_uid": goal_uid},
        )

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

    async def get_tasks_applying_knowledge(
        self, knowledge_uid: str, user_uid: str, limit: int
    ) -> Result[list[dict[str, Any]]]:
        """Find tasks engaging with a knowledge unit via APPLIES/REQUIRES_KNOWLEDGE."""
        return await self.executor.execute_query(
            _TASKS_APPLYING_KNOWLEDGE_QUERY,
            {"knowledge_uid": knowledge_uid, "user_uid": user_uid, "limit": limit},
        )

    async def get_goals_for_task(self, task_uid: str) -> Result[list[dict[str, Any]]]:
        """Find goals a task contributes to or fulfills."""
        return await self.executor.execute_query(
            _GOALS_FOR_TASK_QUERY,
            {"task_uid": task_uid},
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

    async def query_with_intent(self, query: str, uid: str) -> Result[list[dict[str, Any]]]:
        """Execute a graph context query built by graph_query_builder."""
        return await self.executor.execute_query(query, {"uid": uid})

    async def get_entity_labels(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Get an entity node and its labels for domain determination."""
        return await self.executor.execute_query(
            """
            MATCH (n {uid: $uid})
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
            OPTIONAL MATCH (u)-[:ENROLLED_IN]->(lp:Lp)
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
            MATCH (source {uid: $entity_uid})
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


__all__ = [
    "ALIGNMENT_LEVEL",
    "CrossDomainBackend",
    "FULL_ALIGNMENT_CONNECTION_COUNT",
    "HABIT_ACTIVE_STATUSES",
]
