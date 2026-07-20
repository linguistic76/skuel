"""
LifePath Backend
================

Backend for life path designation, alignment, and related graph operations.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 12 execute_query calls:
- LifePathAlignmentService (7 calls)
- LifePathCoreService (5 calls)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class LifePathBackend:
    """Backend for life path designation and alignment operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # Core Service — Designation CRUD
    # ========================================================================

    async def get_designation(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's life path designation and vision data."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[r:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            RETURN u.vision_statement AS vision_statement,
                   u.vision_themes AS vision_themes,
                   u.vision_captured_at AS vision_captured_at,
                   lp.uid AS life_path_uid,
                   r.designated_at AS designated_at,
                   r.alignment_score AS alignment_score
            """,
            {"user_uid": user_uid},
        )

    async def save_vision(
        self,
        user_uid: str,
        vision_statement: str,
        vision_themes: list[str],
        captured_at: str,
    ) -> Result[list[dict[str, Any]]]:
        """Save vision statement and themes on User node."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            SET u.vision_statement = $vision_statement,
                u.vision_themes = $vision_themes,
                u.vision_captured_at = $captured_at
            RETURN u.uid AS user_uid
            """,
            {
                "user_uid": user_uid,
                "vision_statement": vision_statement,
                "vision_themes": vision_themes,
                "captured_at": captured_at,
            },
        )

    async def designate_life_path(
        self,
        user_uid: str,
        life_path_uid: str,
        designated_at: str,
    ) -> Result[list[dict[str, Any]]]:
        """Designate LP as life path: remove old designation, create new ULTIMATE_PATH."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'learning_path'})

            // Revert previous designation's entity_type back to learning_path
            OPTIONAL MATCH (u)-[old:ULTIMATE_PATH]->(old_lp:Entity {entity_type: 'life_path'})
            SET old_lp.entity_type = 'learning_path'
            DELETE old

            // Create new designation and promote entity_type
            WITH u, lp
            CREATE (u)-[r:ULTIMATE_PATH {designated_at: $designated_at}]->(lp)
            SET lp.entity_type = 'life_path'

            RETURN u.vision_statement AS vision_statement,
                   u.vision_themes AS vision_themes,
                   u.vision_captured_at AS vision_captured_at,
                   lp.uid AS life_path_uid,
                   r.designated_at AS designated_at
            """,
            {
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "designated_at": designated_at,
            },
        )

    async def remove_designation(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Remove ULTIMATE_PATH and revert entity_type to learning_path."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            SET lp.entity_type = 'learning_path'
            DELETE r
            RETURN count(r) > 0 AS removed
            """,
            {"user_uid": user_uid},
        )

    async def update_alignment_score(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Update alignment scores on the ULTIMATE_PATH relationship."""
        # Build query dynamically based on whether dimension scores are provided
        has_dimensions = "knowledge_alignment" in params

        query = """
        MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
        SET r.alignment_score = $alignment_score,
            r.alignment_level = $alignment_level,
            r.alignment_updated_at = datetime()
        """

        if has_dimensions:
            query += """,
            r.knowledge_alignment = $knowledge_alignment,
            r.activity_alignment = $activity_alignment,
            r.goal_alignment = $goal_alignment,
            r.principle_alignment = $principle_alignment,
            r.momentum = $momentum
            """

        query += "\nRETURN r.alignment_score AS score"

        return await self._executor.execute_query(query, params)

    async def record_alignment_snapshot(
        self, user_uid: str, score: float
    ) -> Result[list[dict[str, Any]]]:
        """Record today's alignment score as a daily snapshot (idempotent per day)."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            MERGE (u)-[r:ALIGNMENT_SNAPSHOT {date: date()}]->(lp)
            ON CREATE SET r.score = $score, r.recorded_at = datetime()
            ON MATCH SET r.score = $score, r.recorded_at = datetime()
            RETURN r.score AS score, toString(r.date) AS date_str
            """,
            {"user_uid": user_uid, "score": score},
        )

    async def get_alignment_snapshots(
        self, user_uid: str, days: int = 31
    ) -> Result[list[dict[str, Any]]]:
        """Get daily alignment snapshots for trend analysis, newest first."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            MATCH (u)-[r:ALIGNMENT_SNAPSHOT]->(lp)
            WHERE r.recorded_at >= datetime() - duration({days: $days})
            RETURN r.score AS score, toString(r.date) AS date_str
            ORDER BY r.recorded_at DESC
            """,
            {"user_uid": user_uid, "days": days},
        )

    # ========================================================================
    # Alignment Service — Graph Queries
    # ========================================================================

    async def get_user_life_path(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's designated life path UID."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            RETURN lp.uid AS life_path_uid
            """,
            {"user_uid": user_uid},
        )

    async def calculate_knowledge_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Calculate knowledge dimension alignment score."""
        return await self._executor.execute_query(
            """
            MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'life_path'})-[:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {entity_type: 'ku'})
            OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)
            // `mastery_level` is NOT a number: _AdaptiveMixin is its only writer
            // and sets the strings 'introduced'/'proficient'. `mastery_score` is
            // the continuous 0-1 signal the other four MASTERED writers set —
            // and an _AdaptiveMixin edge, which carries no score, still means
            // mastered, so its existence scores 1.0.
            WITH ku, m,
                 CASE WHEN m IS NULL THEN 0.0
                      ELSE coalesce(m.mastery_score, 1.0) END AS mastery

            // Get substance from knowledge applications
            OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(task:Entity {entity_type: 'task', user_uid: $user_uid})
            OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(habit:Entity {entity_type: 'habit', user_uid: $user_uid})

            WITH ku, mastery,
                 count(DISTINCT task) AS task_count,
                 count(DISTINCT habit) AS habit_count

            // Calculate substance-weighted mastery
            WITH ku,
                 mastery * 0.6 + (task_count * 0.05) + (habit_count * 0.10) AS weighted_mastery

            RETURN avg(CASE WHEN weighted_mastery > 1.0 THEN 1.0 ELSE weighted_mastery END) AS knowledge_alignment
            """,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )

    async def calculate_activity_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Calculate activity dimension alignment score."""
        return await self._executor.execute_query(
            """
            // Get life path knowledge
            MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'life_path'})-[:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {entity_type: 'ku'})
            WITH collect(ku.uid) AS lp_knowledge

            // Count aligned activities
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[:OWNS]->(task:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku:Entity)
            WHERE ku.uid IN lp_knowledge
            WITH lp_knowledge, count(DISTINCT task) AS aligned_tasks

            OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(habit:Entity {entity_type: 'habit'})-[:APPLIES_KNOWLEDGE]->(ku:Entity)
            WHERE ku.uid IN lp_knowledge
            WITH aligned_tasks, count(DISTINCT habit) AS aligned_habits

            // Also count total activities
            OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(all_task:Entity {entity_type: 'task'})
            WITH aligned_tasks, aligned_habits, count(DISTINCT all_task) AS total_tasks

            OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(all_habit:Entity {entity_type: 'habit'})
            WITH aligned_tasks, aligned_habits, total_tasks, count(DISTINCT all_habit) AS total_habits

            WITH aligned_tasks, aligned_habits, total_tasks, total_habits,
                 CASE WHEN total_tasks = 0 THEN 0.5
                      ELSE toFloat(aligned_tasks) / total_tasks END AS task_ratio,
                 CASE WHEN total_habits = 0 THEN 0.5
                      ELSE toFloat(aligned_habits) / total_habits END AS habit_ratio

            // Habits weighted more heavily
            RETURN (task_ratio * 0.4 + habit_ratio * 0.6) AS activity_alignment
            """,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )

    async def calculate_goal_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Calculate goal dimension alignment score."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:OWNS]->(g:Entity {entity_type: 'goal'})
            WHERE g.status IN ['active', 'in_progress']

            // Check for SERVES_LIFE_PATH relationship
            OPTIONAL MATCH (g)-[:SERVES_LIFE_PATH]->(lp:Entity {uid: $life_path_uid, entity_type: 'life_path'})

            WITH count(g) AS total_goals, count(lp) AS aligned_goals

            RETURN CASE WHEN total_goals = 0 THEN 0.5
                        ELSE toFloat(aligned_goals) / total_goals END AS goal_alignment
            """,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )

    async def calculate_principle_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Calculate principle dimension alignment score."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:OWNS]->(p:Entity {entity_type: 'principle'})
            WHERE p.status = 'active'

            // Check for alignment with life path
            OPTIONAL MATCH (p)-[:SERVES_LIFE_PATH]->(lp:Entity {uid: $life_path_uid, entity_type: 'life_path'})

            WITH count(p) AS total_principles, count(lp) AS aligned_principles

            RETURN CASE WHEN total_principles = 0 THEN 0.5
                        ELSE toFloat(aligned_principles) / total_principles END AS principle_alignment
            """,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )

    async def calculate_momentum(
        self,
        user_uid: str,
        life_path_uid: str,
        seven_days_ago: str,
        fourteen_days_ago: str,
    ) -> Result[list[dict[str, Any]]]:
        """Calculate momentum dimension (recent vs previous week activity)."""
        return await self._executor.execute_query(
            """
            MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'life_path'})-[:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {entity_type: 'ku'})
            WITH collect(ku.uid) AS lp_knowledge

            // Recent week activities. OPTIONAL: a user whose aligned activity
            // dropped to zero must score as declining, not collapse the query to
            // no rows — which the service reads back as the 0.5 "no data"
            // default, the opposite signal.
            OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(task:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku:Entity)
            WHERE ku.uid IN lp_knowledge
              AND datetime(task.created_at) >= datetime($seven_days_ago)
            WITH lp_knowledge, count(task) AS recent_tasks

            // Previous week activities
            OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(task:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku:Entity)
            WHERE ku.uid IN lp_knowledge
              AND datetime(task.created_at) >= datetime($fourteen_days_ago)
              AND datetime(task.created_at) < datetime($seven_days_ago)
            WITH recent_tasks, count(task) AS previous_tasks

            // Calculate momentum (positive if increasing, negative if decreasing)
            WITH recent_tasks, previous_tasks,
                 CASE WHEN previous_tasks = 0 THEN
                      CASE WHEN recent_tasks > 0 THEN 0.8 ELSE 0.5 END
                      ELSE toFloat(recent_tasks) / previous_tasks END AS ratio

            RETURN CASE WHEN ratio >= 1.5 THEN 1.0
                        WHEN ratio >= 1.0 THEN 0.7
                        WHEN ratio >= 0.5 THEN 0.5
                        ELSE 0.3 END AS momentum
            """,
            {
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "seven_days_ago": seven_days_ago,
                "fourteen_days_ago": fourteen_days_ago,
            },
        )

    async def get_knowledge_substance_stats(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get counts of embodied vs theoretical knowledge."""
        return await self._executor.execute_query(
            """
            MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'life_path'})-[:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {entity_type: 'ku'})
            OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)

            // No MASTERED writer has ever set `substance_score`, so this read
            // classified every Ku as theoretical. Mastery stands in as the
            // substance proxy, matching PsContextService.  A true ADR-046
            // Ku-grain substance rollup is roadmap work, not a backlog fix.
            WITH ku, CASE WHEN m IS NULL THEN 0.0
                          ELSE coalesce(m.mastery_score, 1.0) END AS substance

            RETURN count(ku) AS total,
                   sum(CASE WHEN substance >= 0.7 THEN 1 ELSE 0 END) AS embodied,
                   sum(CASE WHEN substance < 0.5 THEN 1 ELSE 0 END) AS theoretical
            """,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )
