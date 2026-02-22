"""
LifePath Alignment Service
===========================

Calculates alignment between user's life path and actual behavior.

This service answers: "Am I living my life path?"

All queries use the unified Ku model with ku_type discriminator:
- Life path: Ku {ku_type: 'life_path'}
- Learning steps: Ku {ku_type: 'learning_step'}
- Knowledge: Ku {ku_type: 'curriculum'}
- Tasks: Ku {ku_type: 'task'}
- Habits: Ku {ku_type: 'habit'}
- Goals: Ku {ku_type: 'goal'}
- Principles: Ku {ku_type: 'principle'}

Core Philosophy: "Everything flows toward the life path"
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums.ku_enums import AlignmentLevel
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor
    from core.services.ku_service import KuService
    from core.services.lp_service import LpService
    from core.services.user_service import UserService

logger = get_logger(__name__)


class LifePathAlignmentService:
    """
    Service for calculating life path alignment.

    Measures how well user's actual behavior (tracked in UserContext)
    aligns with their designated life path.

    Alignment Dimensions (5):
    1. Knowledge Alignment (25%): Mastery of life path knowledge
    2. Activity Alignment (25%): Tasks/habits supporting life path
    3. Goal Alignment (20%): Active goals contributing to life path
    4. Principle Alignment (15%): Values supporting life path direction
    5. Momentum (15%): Recent activity trend toward life path
    """

    def __init__(
        self,
        executor: QueryExecutor | None = None,
        lp_service: LpService | None = None,
        ku_service: KuService | None = None,
        user_service: UserService | None = None,
    ) -> None:
        """
        Initialize alignment service.

        Args:
            executor: QueryExecutor for database operations
            lp_service: LP service for path details
            ku_service: KU service for knowledge substance
            user_service: User service for context
        """
        self.executor = executor
        self.lp_service = lp_service
        self.ku_service = ku_service
        self.user_service = user_service
        logger.info("LifePathAlignmentService initialized")

    async def calculate_alignment(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate comprehensive life path alignment.

        This is THE most important metric in SKUEL - measures whether
        user is LIVING their life path or just learning about it.

        Args:
            user_uid: User identifier

        Returns:
            Result containing comprehensive alignment analysis
        """
        logger.info(f"Calculating life path alignment for user {user_uid}")

        # Get user's life path
        life_path_uid = await self._get_user_life_path(user_uid)
        if not life_path_uid:
            return Result.ok(self._no_designation_response())

        # Get life path details
        lp_details = await self._get_life_path_details(life_path_uid)

        # Calculate each dimension
        knowledge_score = await self._calculate_knowledge_alignment(user_uid, life_path_uid)
        activity_score = await self._calculate_activity_alignment(user_uid, life_path_uid)
        goal_score = await self._calculate_goal_alignment(user_uid, life_path_uid)
        principle_score = await self._calculate_principle_alignment(user_uid, life_path_uid)
        momentum_score = await self._calculate_momentum(user_uid, life_path_uid)

        # Calculate weighted overall score
        overall_score = (
            knowledge_score * 0.25
            + activity_score * 0.25
            + goal_score * 0.20
            + principle_score * 0.15
            + momentum_score * 0.15
        )

        alignment_level = AlignmentLevel.from_score(overall_score)

        # Get knowledge substance stats
        knowledge_stats = await self._get_knowledge_substance_stats(user_uid, life_path_uid)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            knowledge_score=knowledge_score,
            activity_score=activity_score,
            goal_score=goal_score,
            principle_score=principle_score,
            momentum_score=momentum_score,
        )

        result = {
            "life_path_uid": life_path_uid,
            "life_path_title": lp_details.get("title", "Unknown"),
            "alignment_score": round(overall_score, 3),
            "alignment_level": alignment_level.value,
            "dimensions": {
                "knowledge": round(knowledge_score, 3),
                "activity": round(activity_score, 3),
                "goal": round(goal_score, 3),
                "principle": round(principle_score, 3),
                "momentum": round(momentum_score, 3),
            },
            "knowledge_stats": knowledge_stats,
            "recommendations": recommendations,
            "calculated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Alignment calculated for {user_uid}: {overall_score:.2f} ({alignment_level.value})"
        )

        return Result.ok(result)

    async def _get_user_life_path(self, user_uid: str) -> str | None:
        """Get user's designated life path UID."""
        if not self.executor:
            return None

        query = """
        MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Ku {ku_type: 'life_path'})
        RETURN lp.uid AS life_path_uid
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            logger.error(
                "Failed to get life path - returning None",
                extra={
                    "user_uid": user_uid,
                    "error_message": str(result.error),
                },
            )
            return None

        records = result.value or []
        if records:
            return records[0].get("life_path_uid")
        return None

    async def _get_life_path_details(self, life_path_uid: str) -> dict[str, Any]:
        """Get life path title and metadata."""
        if self.lp_service:
            lp_result = await self.lp_service.core.get(life_path_uid)
            if lp_result.is_ok and lp_result.value:
                return {
                    "title": lp_result.value.title,
                    "description": lp_result.value.description,
                }
        return {"title": "Unknown", "description": ""}

    async def _calculate_knowledge_alignment(self, user_uid: str, life_path_uid: str) -> float:
        """
        Calculate knowledge dimension (25% weight).

        Measures mastery of knowledge units in the life path.
        Uses Knowledge Substance Philosophy - applied knowledge > theory.
        """
        if not self.executor:
            return 0.0

        query = """
        MATCH (lp:Ku {uid: $life_path_uid, ku_type: 'life_path'})-[:HAS_STEP]->(ls:Ku {ku_type: 'learning_step'})-[:CONTAINS]->(ku:Ku {ku_type: 'curriculum'})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)
        WITH ku, m,
             CASE WHEN m IS NOT NULL THEN m.mastery_level ELSE 0 END AS mastery

        // Get substance from knowledge applications
        OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(task:Ku {ku_type: 'task', user_uid: $user_uid})
        OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(habit:Ku {ku_type: 'habit', user_uid: $user_uid})

        WITH ku, mastery,
             count(DISTINCT task) AS task_count,
             count(DISTINCT habit) AS habit_count

        // Calculate substance-weighted mastery
        WITH ku,
             mastery * 0.6 + (task_count * 0.05) + (habit_count * 0.10) AS weighted_mastery

        RETURN avg(CASE WHEN weighted_mastery > 1.0 THEN 1.0 ELSE weighted_mastery END) AS knowledge_alignment
        """

        result = await self.executor.execute_query(
            query,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )
        if result.is_error:
            logger.error(
                "Knowledge alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("knowledge_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_activity_alignment(self, user_uid: str, life_path_uid: str) -> float:
        """
        Calculate activity dimension (25% weight).

        Measures how tasks and habits support the life path.
        """
        if not self.executor:
            return 0.0

        query = """
        // Get life path knowledge
        MATCH (lp:Ku {uid: $life_path_uid, ku_type: 'life_path'})-[:HAS_STEP]->(ls:Ku {ku_type: 'learning_step'})-[:CONTAINS]->(ku:Ku {ku_type: 'curriculum'})
        WITH collect(ku.uid) AS lp_knowledge

        // Count aligned activities
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[:OWNS]->(task:Ku {ku_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku:Ku)
        WHERE ku.uid IN lp_knowledge
        WITH lp_knowledge, count(DISTINCT task) AS aligned_tasks

        OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(habit:Ku {ku_type: 'habit'})-[:APPLIES_KNOWLEDGE]->(ku:Ku)
        WHERE ku.uid IN lp_knowledge
        WITH aligned_tasks, count(DISTINCT habit) AS aligned_habits

        // Also count total activities
        OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(all_task:Ku {ku_type: 'task'})
        WITH aligned_tasks, aligned_habits, count(DISTINCT all_task) AS total_tasks

        OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(all_habit:Ku {ku_type: 'habit'})
        WITH aligned_tasks, aligned_habits, total_tasks, count(DISTINCT all_habit) AS total_habits

        WITH aligned_tasks, aligned_habits, total_tasks, total_habits,
             CASE WHEN total_tasks = 0 THEN 0.5
                  ELSE toFloat(aligned_tasks) / total_tasks END AS task_ratio,
             CASE WHEN total_habits = 0 THEN 0.5
                  ELSE toFloat(aligned_habits) / total_habits END AS habit_ratio

        // Habits weighted more heavily
        RETURN (task_ratio * 0.4 + habit_ratio * 0.6) AS activity_alignment
        """

        result = await self.executor.execute_query(
            query,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )
        if result.is_error:
            logger.error(
                "Activity alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("activity_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_goal_alignment(self, user_uid: str, life_path_uid: str) -> float:
        """
        Calculate goal dimension (20% weight).

        Measures if active goals contribute to life path.
        """
        if not self.executor:
            return 0.0

        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(g:Ku {ku_type: 'goal'})
        WHERE g.status IN ['active', 'in_progress']

        // Check for SERVES_LIFE_PATH relationship
        OPTIONAL MATCH (g)-[:SERVES_LIFE_PATH]->(lp:Ku {uid: $life_path_uid, ku_type: 'life_path'})

        WITH count(g) AS total_goals, count(lp) AS aligned_goals

        RETURN CASE WHEN total_goals = 0 THEN 0.5
                    ELSE toFloat(aligned_goals) / total_goals END AS goal_alignment
        """

        result = await self.executor.execute_query(
            query,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )
        if result.is_error:
            logger.error(
                "Goal alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("goal_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_principle_alignment(self, user_uid: str, life_path_uid: str) -> float:
        """
        Calculate principle dimension (15% weight).

        Measures if user's principles support the life path direction.
        """
        if not self.executor:
            return 0.0

        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(p:Ku {ku_type: 'principle'})
        WHERE p.status = 'active'

        // Check for alignment with life path
        OPTIONAL MATCH (p)-[:SERVES_LIFE_PATH]->(lp:Ku {uid: $life_path_uid, ku_type: 'life_path'})

        WITH count(p) AS total_principles, count(lp) AS aligned_principles

        RETURN CASE WHEN total_principles = 0 THEN 0.5
                    ELSE toFloat(aligned_principles) / total_principles END AS principle_alignment
        """

        result = await self.executor.execute_query(
            query,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )
        if result.is_error:
            logger.error(
                "Principle alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("principle_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_momentum(self, user_uid: str, life_path_uid: str) -> float:
        """
        Calculate momentum dimension (15% weight).

        Measures recent activity trend toward life path.
        Compares last 7 days vs previous 7 days.
        """
        if not self.executor:
            return 0.0

        now = datetime.now()
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)

        query = """
        MATCH (lp:Ku {uid: $life_path_uid, ku_type: 'life_path'})-[:HAS_STEP]->(ls:Ku {ku_type: 'learning_step'})-[:CONTAINS]->(ku:Ku {ku_type: 'curriculum'})
        WITH collect(ku.uid) AS lp_knowledge

        // Recent week activities
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(task:Ku {ku_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku:Ku)
        WHERE ku.uid IN lp_knowledge
          AND task.created_at >= $seven_days_ago
        WITH lp_knowledge, count(task) AS recent_tasks

        // Previous week activities
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(task:Ku {ku_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku:Ku)
        WHERE ku.uid IN lp_knowledge
          AND task.created_at >= $fourteen_days_ago
          AND task.created_at < $seven_days_ago
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
        """

        result = await self.executor.execute_query(
            query,
            {
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "seven_days_ago": seven_days_ago.isoformat(),
                "fourteen_days_ago": fourteen_days_ago.isoformat(),
            },
        )
        if result.is_error:
            logger.error(
                "Momentum calculation failed - returning 0.5",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.5

        records = result.value or []
        if records:
            score = records[0].get("momentum")
            return float(score) if score else 0.5
        return 0.5

    async def _get_knowledge_substance_stats(
        self, user_uid: str, life_path_uid: str
    ) -> dict[str, int]:
        """Get counts of embodied vs theoretical knowledge."""
        if not self.executor:
            return {"total": 0, "embodied": 0, "theoretical": 0}

        query = """
        MATCH (lp:Ku {uid: $life_path_uid, ku_type: 'life_path'})-[:HAS_STEP]->(ls:Ku {ku_type: 'learning_step'})-[:CONTAINS]->(ku:Ku {ku_type: 'curriculum'})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(ku)

        WITH ku, COALESCE(m.substance_score, 0) AS substance

        RETURN count(ku) AS total,
               sum(CASE WHEN substance >= 0.7 THEN 1 ELSE 0 END) AS embodied,
               sum(CASE WHEN substance < 0.5 THEN 1 ELSE 0 END) AS theoretical
        """

        result = await self.executor.execute_query(
            query,
            {"user_uid": user_uid, "life_path_uid": life_path_uid},
        )
        if result.is_error:
            logger.error(
                "Knowledge stats query failed - returning defaults",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return {"total": 0, "embodied": 0, "theoretical": 0}

        records = result.value or []
        if records:
            r = records[0]
            return {
                "total": int(r.get("total") or 0),
                "embodied": int(r.get("embodied") or 0),
                "theoretical": int(r.get("theoretical") or 0),
            }
        return {"total": 0, "embodied": 0, "theoretical": 0}

    def _generate_recommendations(
        self,
        knowledge_score: float,
        activity_score: float,
        goal_score: float,
        principle_score: float,
        momentum_score: float,
    ) -> list[str]:
        """Generate actionable recommendations based on dimension scores."""
        recommendations = []

        if knowledge_score < 0.5:
            recommendations.append("Focus on mastering the knowledge units in your life path")

        if activity_score < 0.5:
            recommendations.append("Create habits that apply your life path knowledge daily")

        if goal_score < 0.5:
            recommendations.append("Set goals that directly contribute to your life path")

        if principle_score < 0.5:
            recommendations.append(
                "Align your principles more closely with your life path direction"
            )

        if momentum_score < 0.5:
            recommendations.append("Increase your daily activities toward your life path")

        if not recommendations:
            recommendations.append("Great work! Continue your current trajectory")

        return recommendations

    def _no_designation_response(self) -> dict[str, Any]:
        """Response when user hasn't designated a life path."""
        return {
            "life_path_uid": None,
            "life_path_title": None,
            "alignment_score": 0.0,
            "alignment_level": "undefined",
            "dimensions": {
                "knowledge": 0.0,
                "activity": 0.0,
                "goal": 0.0,
                "principle": 0.0,
                "momentum": 0.0,
            },
            "knowledge_stats": {"total": 0, "embodied": 0, "theoretical": 0},
            "recommendations": [
                "Express your vision to get started!",
                "Use the vision capture to articulate your life goals",
            ],
            "message": "No life path designated. Express your vision to begin.",
        }
