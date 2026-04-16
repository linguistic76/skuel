"""Activity Domain backends: Habits, Goals, Tasks, Events, Choices, Principles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j._hierarchy_mixin import HierarchyConfig, _HierarchyMixin
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    ChoiceStats,
    EventStats,
    GoalStats,
    HabitStats,
    ParentProgressResult,
    PrincipleStats,
    TaskStats,
)
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from datetime import date

    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


class HabitsBackend(_HierarchyMixin, UniversalNeo4jBackend[Habit]):
    """
    Domain backend for Habit entities.

    Extends UniversalNeo4jBackend[Habit] with:
    - _HierarchyMixin: subhabit hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_habit(uid)          → not matched by get_*_by_uid pattern
    - list_by_user(uid, limit) → not matched by list_*s pattern
    - get_user_habits(uid)    → not matched by any __getattr__ pattern
    - archive_habit(uid)      → status transition (not just delete)
    - get_stats_for_user(uid) → habit count stats (total/active/streaks)
    - link_habit_to_knowledge → Cypher MERGE
    - link_habit_to_principle → Cypher MERGE
    - create_user_habit_relationship → wraps create_user_relationship()
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBHABIT.value,
        inverse_rel=RelationshipName.SUBHABIT_OF.value,
        node_label="Habit",
        domain_name="subhabit",
    )

    async def get_habit(self, habit_id: str) -> Result[Habit]:
        """Get habit by ID. Returns error if not found (contrast with get() → None)."""
        get_result: Result[Habit | None] = await self.get(habit_id)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Habit]]:
        """List all habits for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Habit], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result)
        habits, _ = page_result.value
        return Result.ok(habits)

    async def get_user_habits(self, user_uid: UserUID) -> Result[list[Habit]]:
        """Get all habits for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def archive_habit(self, habit_id: str) -> Result[bool]:
        """Archive a habit by transitioning its status to 'archived'."""
        update_result: Result[Habit] = await self.update(habit_id, {"status": "archived"})
        if update_result.is_error:
            return Result.fail(update_result)
        return Result.ok(True)

    async def create_user_habit_relationship(
        self, user_uid: UserUID, habit_uid: str
    ) -> Result[bool]:
        """Create User→Habit OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, habit_uid)

    async def get_active_habits_prioritized(
        self,
        user_uid: UserUID,
        terminal_statuses: list[str],
        limit: int = 20,
    ) -> Result[list[Neo4jProperties]]:
        """Get active habits for a user, pre-sorted for prioritization.

        Fetches habits not in terminal statuses, sorted by streak-at-risk
        first, then by streak length and recency.

        Args:
            user_uid: Owner of the habits.
            terminal_statuses: Status values to exclude.
            limit: Maximum results.

        Returns:
            Result containing list of habit node properties.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(h:Habit)
        WHERE NOT h.status IN $terminal_statuses
        RETURN h
        ORDER BY
            CASE WHEN h.current_streak > 0 AND h.last_completed < date() THEN 0 ELSE 1 END,
            h.current_streak DESC,
            h.created_at DESC
        LIMIT $fetch_limit
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "terminal_statuses": terminal_statuses,
                "fetch_limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["h"] for record in result.value])

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[HabitStats]:
        """Count habit stats: total, active, streaks."""
        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'habit'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.status = 'active' THEN 1 END) AS active,
            count(CASE WHEN n.current_streak > 0 THEN 1 END) AS streaks
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "active": record.get("active", 0),
                "streaks": record.get("streaks", 0),
            }
        )

    async def link_habit_to_knowledge(self, habit_uid: str, knowledge_uid: str) -> Result[bool]:
        """
        Link habit to knowledge it practices.
        Creates: (Habit)-[:REINFORCES_KNOWLEDGE]->(Entity)
        """
        try:
            query = """
            MATCH (h:Habit {uid: $habit_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (h)-[r:REINFORCES_KNOWLEDGE]->(k)
            RETURN r
            """
            result = await self.execute_query(
                query, {"habit_uid": habit_uid, "knowledge_uid": knowledge_uid}
            )
            if result.is_error:
                return Result.fail(result)
            self.logger.info(f"Linked Habit:{habit_uid} to Knowledge:{knowledge_uid}")
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link habit to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_habit_to_knowledge", message=str(e)))

    async def get_user_badges(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all badges earned by a user via EARNED_BADGE relationships."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.EARNED_BADGE.value}]->(badge:Achievement)
        RETURN badge.badge_id as badge_id,
               badge.name as badge_name,
               badge.description as description,
               badge.tier as tier,
               r.earned_at as earned_at,
               r.streak_length as streak_length,
               r.habit_uid as habit_uid
        ORDER BY r.earned_at DESC
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return result
        return Result.ok(result.value or [])

    async def get_habit_badges(self, habit_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all badges unlocked by a specific habit via UNLOCKED_ACHIEVEMENT."""
        query = f"""
        MATCH (habit:Habit {{uid: $habit_uid}})-[:{RelationshipName.UNLOCKED_ACHIEVEMENT.value}]->(badge:Achievement)
        RETURN badge.badge_id as badge_id,
               badge.name as badge_name,
               badge.description as description,
               badge.tier as tier
        ORDER BY badge.tier
        """
        result = await self.execute_query(query, {"habit_uid": habit_uid})
        if result.is_error:
            return result
        return Result.ok(result.value or [])

    async def check_badge_already_earned(
        self, user_uid: UserUID, habit_uid: str, badge_id: str
    ) -> Result[bool]:
        """Check if user has already earned this badge for this habit."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.EARNED_BADGE.value}]->(badge:Achievement {{badge_id: $badge_id}})
        WHERE r.habit_uid = $habit_uid
        RETURN count(r) > 0 as already_earned
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "habit_uid": habit_uid, "badge_id": badge_id},
        )
        if result.is_error or not result.value:
            return Result.ok(False)
        return Result.ok(result.value[0].get("already_earned", False))

    async def award_badge(
        self,
        user_uid: UserUID,
        habit_uid: str,
        badge_id: str,
        badge_name: str,
        badge_description: str,
        badge_tier: str,
        streak_length: int,
        occurred_at: str,
    ) -> Result[bool]:
        """Create achievement record and link to user and habit."""
        query = f"""
        // Get or create achievement badge
        MERGE (badge:Achievement {{badge_id: $badge_id}})
        ON CREATE SET
            badge.name = $badge_name,
            badge.description = $badge_description,
            badge.tier = $badge_tier,
            badge.created_at = datetime()

        // Get user and habit
        WITH badge
        MATCH (user:User {{uid: $user_uid}})
        MATCH (habit:Habit {{uid: $habit_uid}})

        // Idempotent EARNED_BADGE relationship
        MERGE (user)-[r:{RelationshipName.EARNED_BADGE.value} {{
            habit_uid: $habit_uid
        }}]->(badge)
        ON CREATE SET
            r.earned_at = datetime($occurred_at),
            r.streak_length = $streak_length

        // Also link achievement to the habit for context
        MERGE (habit)-[:{RelationshipName.UNLOCKED_ACHIEVEMENT.value}]->(badge)

        RETURN badge.badge_id as badge_id
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "habit_uid": habit_uid,
                "badge_id": badge_id,
                "badge_name": badge_name,
                "badge_description": badge_description,
                "badge_tier": badge_tier,
                "streak_length": streak_length,
                "occurred_at": occurred_at,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def check_user_badge_earned(self, user_uid: UserUID, badge_id: str) -> Result[bool]:
        """Check if user has earned a badge (cross-habit, no habit_uid filter)."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.EARNED_BADGE.value}]->(badge:Achievement {{badge_id: $badge_id}})
        RETURN count(*) > 0 as already_earned
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "badge_id": badge_id})
        if result.is_error or not result.value:
            return Result.ok(False)
        return Result.ok(result.value[0].get("already_earned", False))

    async def award_user_badge(
        self,
        user_uid: UserUID,
        badge_id: str,
        badge_name: str,
        badge_description: str,
        badge_tier: str,
        badge_category: str,
        threshold_value: int,
        occurred_at: str,
    ) -> Result[bool]:
        """Create achievement record linked to user only (cross-habit badges)."""
        query = f"""
        MERGE (badge:Achievement {{badge_id: $badge_id}})
        ON CREATE SET
            badge.name = $badge_name,
            badge.description = $badge_description,
            badge.tier = $badge_tier,
            badge.category = $badge_category,
            badge.created_at = datetime()

        WITH badge
        MATCH (user:User {{uid: $user_uid}})

        MERGE (user)-[r:{RelationshipName.EARNED_BADGE.value} {{
            badge_category: $badge_category
        }}]->(badge)
        ON CREATE SET
            r.earned_at = datetime($occurred_at),
            r.threshold_value = $threshold_value

        RETURN badge.badge_id as badge_id
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "badge_id": badge_id,
                "badge_name": badge_name,
                "badge_description": badge_description,
                "badge_tier": badge_tier,
                "badge_category": badge_category,
                "threshold_value": threshold_value,
                "occurred_at": occurred_at,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def get_user_badge_stats(self, user_uid: UserUID) -> Result[Neo4jProperties]:
        """Get aggregated habit stats for badge evaluation in a single query.

        Returns:
            Dict with total_completions, high_quality_completions,
            max_identity_votes, established_identity_count.
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[:OWNS]->(h:Habit:Entity)
        WITH user,
             sum(coalesce(h.total_completions, 0)) AS total_completions,
             max(CASE WHEN h.is_identity_habit = true
                 THEN coalesce(h.identity_votes_cast, 0) ELSE 0 END) AS max_identity_votes,
             sum(CASE WHEN h.is_identity_habit = true
                 AND coalesce(h.identity_votes_cast, 0) >= 50 THEN 1 ELSE 0 END
             ) AS established_identity_count
        OPTIONAL MATCH (user)-[:OWNS]->(hc:HabitCompletion)
        WHERE hc.quality IS NOT NULL AND hc.quality >= 4
        RETURN total_completions,
               count(hc) AS high_quality_completions,
               max_identity_votes,
               established_identity_count
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(
                {
                    "total_completions": 0,
                    "high_quality_completions": 0,
                    "max_identity_votes": 0,
                    "established_identity_count": 0,
                }
            )
        return Result.ok(result.value[0])

    async def link_habit_to_principle(self, habit_uid: str, principle_uid: str) -> Result[bool]:
        """
        Link habit to principle it embodies.
        Creates: (Habit)-[:EMBODIES_PRINCIPLE]->(Entity)
        """
        try:
            query = """
            MATCH (h:Habit {uid: $habit_uid})
            MATCH (p:Entity {uid: $principle_uid})
            MERGE (h)-[r:EMBODIES_PRINCIPLE]->(p)
            RETURN r
            """
            result = await self.execute_query(
                query, {"habit_uid": habit_uid, "principle_uid": principle_uid}
            )
            if result.is_error:
                return Result.fail(result)
            self.logger.info(f"Linked Habit:{habit_uid} to Principle:{principle_uid}")
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link habit to principle: {e}")
            return Result.fail(Errors.database(operation="link_habit_to_principle", message=str(e)))


class GoalsBackend(_HierarchyMixin, UniversalNeo4jBackend[Goal]):
    """
    Domain backend for Goal entities.

    Extends UniversalNeo4jBackend[Goal] with:
    - _HierarchyMixin: subgoal hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_goal(uid)          → not matched by get_*_by_uid pattern
    - list_by_user(uid, limit) → not matched by list_*s pattern
    - get_user_goals(uid)    → delegates to list_by_user()
    - get_stats_for_user(uid) → goal count stats (total/active/completed)
    - link_goal_to_habit    → Cypher MERGE
    - link_goal_to_knowledge → Cypher MERGE
    - link_goal_to_principle → Cypher MERGE
    - create_user_goal_relationship → wraps create_user_relationship()
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBGOAL.value,
        inverse_rel=RelationshipName.SUBGOAL_OF.value,
        node_label="Entity",
        domain_name="subgoal",
    )

    async def get_goal(self, goal_id: str) -> Result[Goal]:
        """Get goal by ID. Returns error if not found (contrast with get() → None)."""
        get_result: Result[Goal | None] = await self.get(goal_id)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_id))
        return Result.ok(get_result.value)

    async def get_user_goals(self, user_uid: UserUID) -> Result[list[Goal]]:
        """Get all goals for a user. Returns flat list (not paginated tuple)."""
        return await self.list_by_user(user_uid)

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Goal]]:
        """List all goals for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Goal], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result)
        goals, _ = page_result.value
        return Result.ok(goals)

    async def create_user_goal_relationship(self, user_uid: UserUID, goal_uid: str) -> Result[bool]:
        """Create User→Goal OWNS relationship in the graph."""
        rel_result: Result[bool] = await self.create_user_relationship(user_uid, goal_uid)
        return rel_result

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[GoalStats]:
        """Count goal stats: total, active, completed."""
        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'goal'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.status = 'active' THEN 1 END) AS active,
            count(CASE WHEN n.status = 'completed' THEN 1 END) AS completed
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "active": record.get("active", 0),
                "completed": record.get("completed", 0),
            }
        )

    async def find_linked_goals_for_task(
        self, task_uid: str, user_uid: UserUID
    ) -> Result[list[str]]:
        """Find goal UIDs linked to a task via SUPPORTS_GOAL."""
        query = f"""
        MATCH (goal:Entity {{entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(task:Entity {{uid: $task_uid, entity_type: 'task'}})
        WHERE goal.user_uid = $user_uid
        RETURN goal.uid as goal_uid
        """
        result = await self.execute_query(query, {"task_uid": task_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["goal_uid"] for record in (result.value or [])])

    async def count_linked_tasks(self, goal_uid: str, user_uid: UserUID) -> Result[dict[str, int]]:
        """Count total and completed tasks linked to a goal via SUPPORTS_GOAL."""
        query = f"""
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(task:Entity {{entity_type: 'task'}})
        WHERE task.user_uid = $user_uid
        WITH count(task) as total_tasks
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(completed:Entity {{entity_type: 'task'}})
        WHERE completed.user_uid = $user_uid
          AND completed.status = 'completed'
        RETURN total_tasks, count(completed) as completed_tasks
        """
        result = await self.execute_query(query, {"goal_uid": goal_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total_tasks": record.get("total_tasks", 0),
                "completed_tasks": record.get("completed_tasks", 0),
            }
        )

    async def find_linked_goals_for_habit(
        self, habit_uid: str, user_uid: UserUID
    ) -> Result[list[str]]:
        """Find goal UIDs linked to a habit via SUPPORTS_GOAL."""
        query = f"""
        MATCH (goal:Entity {{entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{uid: $habit_uid, entity_type: 'habit'}})
        WHERE goal.user_uid = $user_uid
        RETURN goal.uid as goal_uid
        """
        result = await self.execute_query(query, {"habit_uid": habit_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["goal_uid"] for record in (result.value or [])])

    async def count_linked_habits_avg_streak(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[dict[str, Any]]:
        """Count habits linked to a goal and compute their average streak."""
        query = f"""
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{entity_type: 'habit'}})
        WHERE habit.user_uid = $user_uid
        WITH count(habit) as total_habits
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{entity_type: 'habit'}})
        WHERE habit.user_uid = $user_uid
        RETURN total_habits, avg(COALESCE(habit.current_streak, 0)) as avg_streak
        """
        result = await self.execute_query(query, {"goal_uid": goal_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total_habits": record.get("total_habits", 0),
                "avg_streak": record.get("avg_streak", 0),
            }
        )

    async def get_achievement_context(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Fetch goal properties and related entities for recommendation generation.

        Returns goal domain/type/timeframe plus related knowledge units, habits,
        and principles — all the context needed to generate next-step recommendations
        after a GoalAchieved event.

        Args:
            goal_uid: UID of the achieved goal
            user_uid: Owner of the goal

        Returns:
            Result containing a list with one record (or empty list if not found)
        """
        query = f"""
        MATCH (goal:Entity {{uid: $goal_uid, user_uid: $user_uid, entity_type: 'goal'}})

        OPTIONAL MATCH (goal)-[:{RelationshipName.REQUIRES_KNOWLEDGE.value}]->(ku:Entity)
        WHERE ku.entity_type = 'knowledge_unit'
        WITH goal, collect(DISTINCT {{uid: ku.uid, title: ku.title, domain: ku.domain}}) as knowledge_units

        OPTIONAL MATCH (goal)-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{entity_type: 'habit'}})
        WITH goal, knowledge_units, collect(DISTINCT {{uid: habit.uid, title: habit.title}}) as habits

        OPTIONAL MATCH (goal)-[:{RelationshipName.GUIDED_BY_PRINCIPLE.value}]->(principle:Entity {{entity_type: 'principle'}})
        WITH goal, knowledge_units, habits, collect(DISTINCT {{uid: principle.uid, title: principle.title}}) as principles

        RETURN goal.uid as uid,
               goal.title as title,
               goal.domain as domain,
               goal.goal_type as goal_type,
               goal.timeframe as timeframe,
               knowledge_units,
               habits,
               principles
        """
        return await self.execute_query(query, {"goal_uid": goal_uid, "user_uid": user_uid})


class TasksBackend(_HierarchyMixin, UniversalNeo4jBackend[Task]):
    """
    Domain backend for Task entities.

    Extends UniversalNeo4jBackend[Task] with:
    - _HierarchyMixin: subtask hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_task(uid)              → wraps get() with NotFound check
    - get_stats_for_user(…)      → task count stats (total/completed/overdue)
    - auto_complete_parent_if_ready(…) → auto-complete parent when all subtasks done
    - calculate_parent_progress(…) → weighted subtask completion percentage
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBTASK.value,
        inverse_rel=RelationshipName.SUBTASK_OF.value,
        node_label="Entity",
        domain_name="subtask",
    )

    async def get_task(self, task_id: str) -> Result[Task]:
        """Get task by ID. Returns error if not found (contrast with get() → None)."""
        get_result: Result[Task | None] = await self.get(task_id)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Task]]:
        """List all tasks for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Task], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result)
        tasks, _ = page_result.value
        return Result.ok(tasks)

    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """Get all tasks for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    # ========================================================================
    # LEARNING LOOP METHODS (ADR-048)
    # ========================================================================

    async def get_user_learning_state(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Get learning state properties from User node for duration calibration."""
        query = """
        MATCH (u:User {uid: $user_uid})
        RETURN u.task_duration_ratio AS task_duration_ratio,
               u.task_completion_count AS task_completion_count,
               u.task_duration_updated_at AS task_duration_updated_at
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({})
        return Result.ok(result.value[0])

    async def update_user_learning_state(
        self, user_uid: UserUID, properties: dict[str, Any]
    ) -> Result[bool]:
        """Update learning state properties on User node."""
        query = """
        MATCH (u:User {uid: $user_uid})
        SET u += $properties
        RETURN u.uid
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "properties": properties})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
        return Result.ok(True)

    # ========================================================================
    # HIERARCHY EXTENSIONS (Task-specific)
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[TaskStats]:
        """Count task stats via Cypher COUNT — no entity deserialization."""
        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'task'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.status = 'completed' THEN 1 END) AS completed,
            count(CASE WHEN n.due_date IS NOT NULL
                       AND n.due_date < date()
                       AND n.status <> 'completed'
                  THEN 1 END) AS overdue
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "completed": record.get("completed", 0),
                "overdue": record.get("overdue", 0),
            }
        )

    async def auto_complete_parent_if_ready(self, completed_task_uid: str) -> Result[list[str]]:
        """Auto-complete parent task if all its subtasks are completed.

        Returns list of parent UIDs that were auto-completed (0 or 1 element).
        The service layer handles recursive grandparent checking.
        """
        query = f"""
        MATCH (completed:Entity {{uid: $task_uid}})
        MATCH (parent:Entity)-[:{RelationshipName.HAS_SUBTASK.value}]->(completed)

        // Get all subtasks of this parent
        MATCH (parent)-[:{RelationshipName.HAS_SUBTASK.value}]->(sibling:Entity)

        // Check if all siblings are complete
        WITH parent,
             count(sibling) as total_subtasks,
             count(CASE WHEN sibling.status = 'completed' THEN 1 END) as completed_subtasks

        WHERE total_subtasks = completed_subtasks
          AND parent.status <> 'completed'  // Don't update if already complete

        // Auto-complete parent
        SET parent.status = 'completed',
            parent.completed_at = datetime(),
            parent.auto_completed = true

        RETURN parent.uid as parent_uid
        """

        result = await self.execute_query(query, {"task_uid": completed_task_uid})

        if result.is_error:
            return Result.fail(result)

        parent_uids = []
        if result.value:
            for record in result.value:
                parent_uids.append(record["parent_uid"])
                self.logger.info(
                    f"Auto-completed parent task: {record['parent_uid']} (all subtasks complete)"
                )
        return Result.ok(parent_uids)

    async def get_assigned_tasks(
        self,
        user_uid: UserUID,
        include_completed: bool = False,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get tasks assigned to a user via ASSIGNED_TO relationship.

        Args:
            user_uid: Target user UID.
            include_completed: Whether to include completed tasks.
            limit: Maximum results.

        Returns:
            Result containing list of task node properties.
        """
        status_filter = "" if include_completed else "AND t.status <> 'completed'"
        query = f"""
        MATCH (t:Entity)-[:{RelationshipName.ASSIGNED_TO.value}]->(u:User {{uid: $user_uid}})
        WHERE t.uid IS NOT NULL {status_filter}
        RETURN t
        ORDER BY t.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["t"] for record in result.value])

    async def calculate_parent_progress(self, parent_uid: str) -> Result[ParentProgressResult]:
        """Calculate parent task progress based on weighted subtask completion."""
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})
        MATCH (parent)-[r:{RelationshipName.HAS_SUBTASK.value}]->(child:Entity)

        WITH parent,
             count(child) as total_subtasks,
             count(CASE WHEN child.status = 'completed' THEN 1 END) as completed_subtasks,
             sum(r.progress_weight) as total_weight,
             sum(
               CASE WHEN child.status = 'completed'
               THEN r.progress_weight
               ELSE 0
               END
             ) as completed_weight

        RETURN
          total_subtasks,
          completed_subtasks,
          total_weight,
          completed_weight,
          CASE WHEN total_weight > 0
            THEN (completed_weight / total_weight) * 100.0
            ELSE 0.0
          END as progress_percentage
        """

        result = await self.execute_query(query, {"parent_uid": parent_uid})

        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(
                {
                    "total_weight": 0.0,
                    "completed_weight": 0.0,
                    "progress_percentage": 0.0,
                    "total_subtasks": 0,
                    "completed_subtasks": 0,
                }
            )

        record = result.value[0]
        return Result.ok(
            {
                "total_weight": record["total_weight"] or 0.0,
                "completed_weight": record["completed_weight"] or 0.0,
                "progress_percentage": record["progress_percentage"] or 0.0,
                "total_subtasks": record["total_subtasks"],
                "completed_subtasks": record["completed_subtasks"],
            }
        )

    async def get_transitive_dependencies(
        self, task_uid: str, rel_type: str, max_depth: int
    ) -> Result[list[str]]:
        """Get transitive dependency UIDs via variable-length path traversal."""
        safe_depth = max(1, min(max_depth, 10))
        query = f"""
        MATCH (root:Entity {{uid: $task_uid}})-[:{rel_type}*1..{safe_depth}]->(dep:Entity)
        WHERE dep.uid <> $task_uid
        RETURN DISTINCT dep.uid AS uid
        """
        result = await self.execute_query(query, {"task_uid": task_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["uid"] for record in result.value])


class EventsBackend(_HierarchyMixin, UniversalNeo4jBackend[Event]):
    """
    Domain backend for Event entities.

    Extends UniversalNeo4jBackend[Event] with:
    - _HierarchyMixin: subevent hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_event(uid)             → wraps get() with NotFound check
    - list_by_user(uid, limit)   → wraps get_user_entities(), extracts list
    - get_user_events(uid)       → alias for list_by_user()
    - get_stats_for_user(uid)    → event count stats (total/scheduled/today)
    - link_event_to_goal(…)      → Cypher MERGE SUPPORTS_GOAL
    - link_event_to_habit(…)     → Cypher MERGE REINFORCES_HABIT
    - link_event_to_knowledge(…) → Cypher MERGE REINFORCES_KNOWLEDGE (batch)
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBEVENT.value,
        inverse_rel=RelationshipName.SUBEVENT_OF.value,
        node_label="Entity",
        domain_name="subevent",
    )

    async def get_event(self, event_id: str) -> Result[Event]:
        """Get event by ID. Returns error if not found (contrast with get() → None)."""
        get_result: Result[Event | None] = await self.get(event_id)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Event]]:
        """List all events for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Event], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result)
        events, _ = page_result.value
        return Result.ok(events)

    async def get_user_events(self, user_uid: UserUID) -> Result[list[Event]]:
        """Get all events for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_events_in_range(
        self,
        start_date: str,
        end_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get events within a date range.

        Args:
            start_date: ISO date string (inclusive).
            end_date: ISO date string (inclusive).
            user_uid: Optional user filter.
            limit: Maximum results.

        Returns:
            Result containing list of event node properties.
        """
        user_clause = "AND e.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (e:Entity)
        WHERE e.event_date >= date($start_date)
          AND e.event_date <= date($end_date)
          {user_clause}
        RETURN e
        ORDER BY e.event_date ASC, e.start_time ASC
        LIMIT $limit
        """
        params: dict[str, object] = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_recurring_events(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get events with a recurrence pattern.

        Args:
            user_uid: Optional user filter.
            limit: Maximum results.

        Returns:
            Result containing list of recurring event node properties.
        """
        user_clause = "AND e.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (e:Entity)
        WHERE e.recurrence_pattern IS NOT NULL
          {user_clause}
        RETURN e
        ORDER BY e.event_date ASC
        LIMIT $limit
        """
        params: dict[str, object] = {"limit": limit}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_events_on_date(
        self, event_date: str, user_uid: UserUID, exclude_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get events on a specific date for a user, excluding one event.

        Used for conflict detection.

        Args:
            event_date: ISO date string.
            user_uid: Owner of the events.
            exclude_uid: Event UID to exclude from results.

        Returns:
            Result containing list of event node properties.
        """
        query = """
        MATCH (e:Entity)
        WHERE e.event_date = date($event_date)
          AND e.user_uid = $user_uid
          AND e.uid <> $event_uid
          AND e.status NOT IN ['cancelled']
        RETURN e
        """
        result = await self.execute_query(
            query,
            {
                "event_date": event_date,
                "user_uid": user_uid,
                "event_uid": exclude_uid,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_completed_events_in_range(
        self,
        user_uid: UserUID,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get completed events within a date range, newest first.

        Args:
            user_uid: Owner of the events.
            start_date: ISO date string (inclusive).
            end_date: ISO date string (inclusive).
            limit: Maximum results.

        Returns:
            Result containing list of completed event node properties.
        """
        query = """
        MATCH (e:Entity)
        WHERE e.user_uid = $user_uid
          AND e.event_date >= date($start_date)
          AND e.event_date <= date($today)
          AND e.status = 'completed'
        RETURN e
        ORDER BY e.event_date DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "start_date": start_date,
                "today": end_date,
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[EventStats]:
        """Count event stats: total, scheduled, today."""
        from datetime import date

        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'event'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.status = 'scheduled' THEN 1 END) AS scheduled,
            count(CASE WHEN n.start_time IS NOT NULL
                       AND substring(toString(n.start_time), 0, 10) = $today
                  THEN 1 END) AS today
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "today": date.today().isoformat()}
        )
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "scheduled": record.get("scheduled", 0),
                "today": record.get("today", 0),
            }
        )

    async def count_recent_reschedules(self, user_uid: UserUID) -> Result[int]:
        """Count events rescheduled in last 30 days."""
        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event'})
        WHERE e.rescheduled_at IS NOT NULL
          AND date(e.rescheduled_at) >= date() - duration('P30D')
        RETURN count(e) as reschedule_count
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        row = result.value[0] if result.value else {}
        return Result.ok(row.get("reschedule_count", 0) if isinstance(row, dict) else 0)

    async def count_events_in_date_range(
        self, user_uid: UserUID, start_date: str, end_date: str
    ) -> Result[int]:
        """Count events in a date range."""
        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event'})
        WHERE e.event_date >= $start_date AND e.event_date <= $end_date
        RETURN count(e) as event_count
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "start_date": start_date, "end_date": end_date}
        )
        if result.is_error:
            return Result.fail(result)
        row = result.value[0] if result.value else {}
        return Result.ok(row.get("event_count", 0) if isinstance(row, dict) else 0)


class ChoicesBackend(_HierarchyMixin, UniversalNeo4jBackend[Choice]):
    """
    Domain backend for Choice entities.

    Extends UniversalNeo4jBackend[Choice] with:
    - _HierarchyMixin: subchoice hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_choice(uid)                      → wraps get() with NotFound check
    - list_by_user(uid, limit)             → wraps get_user_entities(), extracts list
    - get_user_choices(uid)                → alias for list_by_user()
    - get_stats_for_user(uid)              → choice count stats (total/pending/decided)
    - create_user_choice_relationship(...) → wraps create_user_relationship()
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBCHOICE.value,
        inverse_rel=RelationshipName.SUBCHOICE_OF.value,
        node_label="Entity",
        domain_name="subchoice",
        node_filter=", entity_type: 'choice'",
    )

    async def get_choice(self, choice_id: str) -> Result[Choice]:
        """Get choice by ID. Returns error if not found (contrast with get() → None)."""
        get_result: Result[Choice | None] = await self.get(choice_id)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Choice]]:
        """List all choices for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Choice], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result)
        choices, _ = page_result.value
        return Result.ok(choices)

    async def get_user_choices(self, user_uid: UserUID) -> Result[list[Choice]]:
        """Get all choices for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[ChoiceStats]:
        """Count choice stats: total, pending, decided."""
        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'choice'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.status = 'pending' THEN 1 END) AS pending,
            count(CASE WHEN n.status = 'decided' THEN 1 END) AS decided
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "pending": record.get("pending", 0),
                "decided": record.get("decided", 0),
            }
        )

    async def get_pending_choices(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get pending/undecided choices for a user.

        Args:
            user_uid: Owner of the choices.
            limit: Maximum results.

        Returns:
            Result containing list of choice node properties.
        """
        query = """
        MATCH (c:Entity {entity_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND c.status IN ['draft', 'active', 'scheduled']
        RETURN c
        ORDER BY c.decision_deadline ASC, c.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["c"] for record in result.value])

    async def get_choices_needing_decision(
        self, user_uid: UserUID, end_date: str
    ) -> Result[list[Neo4jProperties]]:
        """Get choices that need a decision by a deadline.

        Args:
            user_uid: Owner of the choices.
            end_date: ISO date string — choices with deadline <= this date.

        Returns:
            Result containing list of choice node properties.
        """
        query = """
        MATCH (c:Entity {entity_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND c.decision_deadline <= date($end_date)
          AND c.status NOT IN ['completed', 'decided', 'cancelled', 'archived']
        RETURN c
        ORDER BY c.decision_deadline ASC
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "end_date": end_date})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["c"] for record in result.value])

    async def create_user_choice_relationship(
        self, user_uid: UserUID, choice_uid: str
    ) -> Result[bool]:
        """Create User→Choice OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, choice_uid)


class PrinciplesBackend(_HierarchyMixin, UniversalNeo4jBackend[Principle]):
    """
    Domain backend for Principle entities.

    Extends UniversalNeo4jBackend[Principle] with:
    - _HierarchyMixin: subprinciple hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_principle(uid)                        → wraps get() with NotFound check
    - list_by_user(uid, limit)                  → wraps get_user_entities(), extracts list
    - get_user_principles(uid)                  → alias for list_by_user()
    - get_stats_for_user(uid)                   → principle count stats (total/core/active)
    - create_user_principle_relationship(...)   → wraps create_user_relationship()
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBPRINCIPLE.value,
        inverse_rel=RelationshipName.SUBPRINCIPLE_OF.value,
        node_label="Principle",
        domain_name="subprinciple",
    )

    async def get_principle(self, principle_uid: str) -> Result[Principle]:
        """Get principle by ID. Returns error if not found (contrast with get() → None)."""
        get_result: Result[Principle | None] = await self.get(principle_uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Principle]]:
        """List all principles for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Principle], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result)
        principles, _ = page_result.value
        return Result.ok(principles)

    async def get_user_principles(self, user_uid: UserUID) -> Result[list[Principle]]:
        """Get all principles for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[PrincipleStats]:
        """Count principle stats: total, core, active."""
        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'principle'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.strength = 'core' THEN 1 END) AS core,
            count(CASE WHEN n.is_active = true THEN 1 END) AS active
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "core": record.get("core", 0),
                "active": record.get("active", 0),
            }
        )

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[Principle]]:
        """Get principles adopted within a date range.

        Principles use is_active (bool) instead of a status enum, so
        build_user_activity_query — which filters on n.status — does not apply.
        This method is the correct home for that Cypher.

        Args:
            user_uid: Owner of the principles.
            start_date: Lower bound on adopted_date (inclusive).
            end_date: Upper bound on adopted_date (inclusive).
            include_completed: When True, inactive (is_active=False) principles are included.

        Returns:
            Result containing principles adopted in the given range.
        """
        query = """
        MATCH (n:Principle)
        WHERE n.user_uid = $user_uid
          AND n.adopted_date >= date($start_date)
          AND n.adopted_date <= date($end_date)
        """
        if not include_completed:
            query += "  AND n.is_active = true\n"
        query += """
        RETURN n
        ORDER BY n.created_at DESC
        LIMIT $limit
        """
        params: dict[str, object] = {
            "user_uid": user_uid,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "limit": 1000,
        }
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        principles = []
        for record in result.value:
            principle_data = record.get("n")
            if principle_data:
                dto = PrincipleDTO.from_dict(principle_data)
                principles.append(Principle.from_dto(dto))
        return Result.ok(principles)

    async def get_principles_needing_review(
        self,
        cutoff_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
        prioritize_never_reviewed: bool = False,
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles whose last_review_date is before cutoff.

        Args:
            cutoff_date: ISO date string — principles reviewed before this are included.
            user_uid: Optional user filter.
            limit: Maximum results.
            prioritize_never_reviewed: If True, never-reviewed principles sort first.

        Returns:
            Result containing list of principle node properties.
        """
        user_clause = "AND p.user_uid = $user_uid" if user_uid else ""
        if prioritize_never_reviewed:
            order_clause = """
            ORDER BY
                CASE WHEN p.last_review_date IS NULL THEN 0 ELSE 1 END,
                p.last_review_date ASC
            """
        else:
            order_clause = "ORDER BY p.last_review_date ASC"

        query = f"""
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(p.last_review_date) < date($cutoff_date))
          {user_clause}
        RETURN p
        {order_clause}
        LIMIT $limit
        """
        params: dict[str, object] = {"cutoff_date": cutoff_date, "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["p"] for record in result.value])

    async def get_principles_due_for_review(
        self,
        cutoff_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles due for review (last_review_date <= cutoff).

        Unlike get_principles_needing_review (strict <), this uses <= for
        "due soon" semantics.

        Args:
            cutoff_date: ISO date string.
            user_uid: Optional user filter.
            limit: Maximum results.

        Returns:
            Result containing list of principle node properties.
        """
        user_clause = "AND p.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(p.last_review_date) <= date($cutoff_date))
          {user_clause}
        RETURN p
        ORDER BY p.last_review_date ASC
        LIMIT $limit
        """
        params: dict[str, object] = {"cutoff_date": cutoff_date, "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["p"] for record in result.value])

    async def get_related_principles_by_traversal(
        self, uid: str, depth: int, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Get principles related via RELATED_TO traversal up to given depth.

        Args:
            uid: Source principle UID.
            depth: Maximum traversal depth (clamped 1-5).
            limit: Maximum results.

        Returns:
            Result containing list of related principle node properties.
        """
        depth = max(1, min(depth, 5))
        query = f"""
        MATCH (source:Principle {{uid: $uid}})
        OPTIONAL MATCH (source)-[:{RelationshipName.RELATED_TO.value}*1..{depth}]-(related:Principle)
        WHERE related.is_active = true AND related.uid <> $uid
        WITH DISTINCT related
        WHERE related IS NOT NULL
        RETURN related
        ORDER BY related.strength DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"uid": uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["related"] for record in result.value if record.get("related")])

    async def get_principles_by_category(
        self, category: str, exclude_uid: str, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles in a category, excluding one UID.

        Args:
            category: Category value string.
            exclude_uid: UID to exclude from results.
            limit: Maximum results.

        Returns:
            Result containing list of principle node properties.
        """
        query = """
        MATCH (p:Principle)
        WHERE p.category = $category
          AND p.uid <> $uid
          AND p.is_active = true
        RETURN p
        ORDER BY p.strength DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query, {"category": category, "uid": exclude_uid, "limit": limit}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["p"] for record in result.value])

    async def create_user_principle_relationship(
        self, user_uid: UserUID, principle_uid: str
    ) -> Result[bool]:
        """Create User→Principle OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, principle_uid)

    async def get_choice_influence_stats(
        self, principle_uid: str, user_uid: UserUID, period_days: int
    ) -> Result[Neo4jProperties]:
        """Get stats on how a principle has influenced choices."""
        query = f"""
        MATCH (p:Principle {{uid: $principle_uid}})-[:{RelationshipName.GUIDES_CHOICE.value}]->(c:Choice)
        WHERE c.user_uid = $user_uid
          AND c.created_at >= datetime() - duration({{days: $period_days}})

        RETURN
            count(c) AS total_choices,
            avg(c.satisfaction_score) AS avg_satisfaction,
            sum(CASE WHEN c.satisfaction_score >= 4 THEN 1 ELSE 0 END) AS positive_outcomes
        """
        result = await self.execute_query(
            query,
            {"principle_uid": principle_uid, "user_uid": user_uid, "period_days": period_days},
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({})
        return Result.ok(dict(result.value[0]))
