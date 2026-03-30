"""
Domain-Specific Backend Classes
================================

Thin subclasses of UniversalNeo4jBackend[T] that implement domain-specific
methods declared in the domain Operations protocols.

These backends resolve the gap between UniversalNeo4jBackend's generic interface
and the domain-specific method names used by sub-services (e.g., get_habit,
list_by_user, get_user_goals).

Architecture
------------
UniversalNeo4jBackend handles generic CRUD and relationship operations via
__getattr__ delegation. Domain backends add explicit implementations for
methods that don't match the __getattr__ patterns:

    - get_<domain>(uid)        → wraps get() with NotFound check
    - list_by_user(uid, limit) → wraps get_user_entities(), extracts list
    - get_user_<domain>s(uid)  → delegates to list_by_user()
    - link_<domain>_to_*(...)  → Cypher MERGE relationship
    - archive_<domain>(uid)    → wraps update() with status="archived"
    - create_user_<domain>_relationship(...) → wraps create_user_relationship()

Usage
-----
In services_bootstrap.py, replace:
    habits_backend = UniversalNeo4jBackend[Habit](driver, NeoLabel.HABIT, Habit, ...)
With:
    habits_backend = HabitsBackend(driver, NeoLabel.HABIT, Habit, ...)

The domain backend is a drop-in replacement with the same constructor signature.

See: /docs/patterns/OWNERSHIP_VERIFICATION.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j._adaptive_mixin import _AdaptiveMixin
from adapters.persistence.neo4j._hierarchy_mixin import HierarchyConfig, _HierarchyMixin
from adapters.persistence.neo4j._knowledge_context_mixin import _KnowledgeContextMixin
from adapters.persistence.neo4j._learning_state_mixin import _LearningStateMixin
from adapters.persistence.neo4j._organizes_mixin import _OrganizesMixin
from adapters.persistence.neo4j._semantic_mixin import _SemanticMixin
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.entity import Entity
from core.models.enums import UserRole
from core.models.event.event import Event
from core.models.exercises.exercise import Exercise
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.ku.ku import Ku
from core.models.lesson.lesson import Lesson
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_step import LearningStep
from core.models.principle.principle import Principle
from core.models.relationship_names import RelationshipName
from core.models.report.activity_report import ActivityReport
from core.models.submissions.submission import Submission
from core.models.task.task import Task
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.ports.query_types import (
    ChoiceStats,
    CurriculumExerciseResult,
    EventStats,
    GoalStats,
    HabitStats,
    LsKnowledgeItemResult,
    LsKnowledgeSummaryResult,
    ParentProgressResult,
    PrincipleStats,
    RequiredKnowledgeResult,
    RevisionChainResult,
    TaskStats,
)
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.journal.je_input import JeInput  # noqa: F401
    from core.models.journal.je_output import JeOutput  # noqa: F401


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
    - add_milestone(...)     → graph MERGE operation
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

    async def add_milestone(self, goal_id: str, milestone: dict[str, Any]) -> Result[bool]:
        """
        Add a milestone to a goal.
        Creates: (Goal)-[:HAS_MILESTONE]->(Milestone)
        """
        query = """
        MATCH (g:Goal {uid: $goal_id})
        MERGE (m:Milestone {uid: $milestone_uid})
        SET m += $milestone_props
        MERGE (g)-[r:HAS_MILESTONE]->(m)
        RETURN r
        """
        milestone_uid = milestone.get("uid") or f"milestone_{goal_id}_{len(milestone)}"
        params = {
            "goal_id": goal_id,
            "milestone_uid": milestone_uid,
            "milestone_props": milestone,
        }
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Added milestone to Goal:{goal_id}")
        return Result.ok(True)

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

    async def link_goal_to_habit(self, goal_uid: str, habit_uid: str) -> Result[bool]:
        """
        Link goal to supporting habit.
        Creates: (Goal)-[:SUPPORTED_BY_HABIT]->(Habit)
        """
        query = """
        MATCH (g:Goal {uid: $goal_uid})
        MATCH (h:Habit {uid: $habit_uid})
        MERGE (g)-[r:SUPPORTED_BY_HABIT]->(h)
        RETURN r
        """
        result = await self.execute_query(query, {"goal_uid": goal_uid, "habit_uid": habit_uid})
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Goal:{goal_uid} to Habit:{habit_uid}")
        return Result.ok(True)

    async def link_goal_to_knowledge(self, goal_uid: str, knowledge_uid: str) -> Result[bool]:
        """
        Link goal to required knowledge unit.
        Creates: (Goal)-[:REQUIRES_KNOWLEDGE]->(Entity)
        """
        query = """
        MATCH (g:Goal {uid: $goal_uid})
        MATCH (k:Entity {uid: $knowledge_uid})
        MERGE (g)-[r:REQUIRES_KNOWLEDGE]->(k)
        RETURN r
        """
        result = await self.execute_query(
            query, {"goal_uid": goal_uid, "knowledge_uid": knowledge_uid}
        )
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Goal:{goal_uid} to Knowledge:{knowledge_uid}")
        return Result.ok(True)

    async def link_goal_to_principle(self, goal_uid: str, principle_uid: str) -> Result[bool]:
        """
        Link goal to guiding principle.
        Creates: (Goal)-[:GUIDED_BY_PRINCIPLE]->(Entity)
        """
        query = """
        MATCH (g:Goal {uid: $goal_uid})
        MATCH (p:Entity {uid: $principle_uid})
        MERGE (g)-[r:GUIDED_BY_PRINCIPLE]->(p)
        RETURN r
        """
        result = await self.execute_query(
            query, {"goal_uid": goal_uid, "principle_uid": principle_uid}
        )
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Goal:{goal_uid} to Principle:{principle_uid}")
        return Result.ok(True)


class TasksBackend(_HierarchyMixin, UniversalNeo4jBackend[Task]):
    """
    Domain backend for Task entities.

    Extends UniversalNeo4jBackend[Task] with:
    - _HierarchyMixin: subtask hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_task(uid)              → wraps get() with NotFound check
    - link_task_to_knowledge(…)  → Cypher MERGE REQUIRES_KNOWLEDGE
    - link_task_to_goal(…)       → Cypher MERGE CONTRIBUTES_TO_GOAL
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

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        knowledge_score_required: float = 0.8,
        is_learning_opportunity: bool = False,
    ) -> Result[bool]:
        """
        Link task to required knowledge unit.
        Creates: (Task)-[:REQUIRES_KNOWLEDGE]->(Knowledge)
        """
        query = """
        MATCH (t:Task {uid: $task_uid})
        MATCH (k:Entity {uid: $knowledge_uid})
        MERGE (t)-[r:REQUIRES_KNOWLEDGE]->(k)
        SET r.knowledge_score_required = $knowledge_score_required,
            r.is_learning_opportunity = $is_learning_opportunity
        RETURN r
        """
        params = {
            "task_uid": task_uid,
            "knowledge_uid": knowledge_uid,
            "knowledge_score_required": knowledge_score_required,
            "is_learning_opportunity": is_learning_opportunity,
        }
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Task:{task_uid} to Knowledge:{knowledge_uid}")
        return Result.ok(True)

    async def link_task_to_goal(
        self,
        task_uid: str,
        goal_uid: str,
        contribution_percentage: float = 0.1,
        milestone_uid: str | None = None,
    ) -> Result[bool]:
        """
        Link task to goal it contributes to.
        Creates: (Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)
        """
        query = """
        MATCH (t:Task {uid: $task_uid})
        MATCH (g:Goal {uid: $goal_uid})
        MERGE (t)-[r:CONTRIBUTES_TO_GOAL]->(g)
        SET r.contribution_percentage = $contribution_percentage,
            r.milestone_uid = $milestone_uid
        RETURN r
        """
        params = {
            "task_uid": task_uid,
            "goal_uid": goal_uid,
            "contribution_percentage": contribution_percentage,
            "milestone_uid": milestone_uid,
        }
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Task:{task_uid} to Goal:{goal_uid}")
        return Result.ok(True)

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

    async def link_event_to_goal(
        self, event_uid: str, goal_uid: str, contribution_weight: float = 1.0
    ) -> Result[bool]:
        """
        Link event to goal it supports.
        Creates: (Event)-[:SUPPORTS_GOAL {contribution_weight}]->(Goal)
        """
        query = """
        MATCH (e:Event {uid: $event_uid})
        MATCH (g:Goal {uid: $goal_uid})
        MERGE (e)-[r:SUPPORTS_GOAL]->(g)
        SET r.contribution_weight = $contribution_weight
        RETURN r
        """
        params = {
            "event_uid": event_uid,
            "goal_uid": goal_uid,
            "contribution_weight": contribution_weight,
        }
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Event:{event_uid} to Goal:{goal_uid}")
        return Result.ok(True)

    async def link_event_to_habit(self, event_uid: str, habit_uid: str) -> Result[bool]:
        """
        Link event to habit it reinforces.
        Creates: (Event)-[:REINFORCES_HABIT]->(Habit)
        """
        query = """
        MATCH (e:Event {uid: $event_uid})
        MATCH (h:Habit {uid: $habit_uid})
        MERGE (e)-[r:REINFORCES_HABIT]->(h)
        RETURN r
        """
        params = {"event_uid": event_uid, "habit_uid": habit_uid}
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Event:{event_uid} to Habit:{habit_uid}")
        return Result.ok(True)

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uids: list[str]
    ) -> Result[bool]:
        """
        Link event to knowledge units it reinforces.
        Creates: (Event)-[:REINFORCES_KNOWLEDGE]->(Knowledge) for each UID
        """
        query = """
        MATCH (e:Event {uid: $event_uid})
        UNWIND $knowledge_uids AS ku_uid
        MATCH (k:Entity {uid: ku_uid})
        MERGE (e)-[r:REINFORCES_KNOWLEDGE]->(k)
        RETURN count(r) as relationship_count
        """
        params = {"event_uid": event_uid, "knowledge_uids": knowledge_uids}
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        self.logger.info(f"Linked Event:{event_uid} to {len(knowledge_uids)} knowledge units")
        return Result.ok(True)


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

    async def create_user_choice_relationship(
        self, user_uid: UserUID, choice_uid: str
    ) -> Result[bool]:
        """Create User→Choice OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, choice_uid)

    async def get_principle_adherence_data(
        self, user_uid: UserUID, period_days: int
    ) -> Result[list[Neo4jProperties]]:
        """Get choices with principle alignment data for adherence analysis."""
        query = f"""
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
        return await self.execute_query(query, {"user_uid": user_uid, "period_days": period_days})

    async def get_choice_principle_conflicts(
        self, choice_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get principle alignment and conflicts for a choice."""
        query = f"""
        MATCH (c:Entity {{uid: $choice_uid, entity_type: 'choice'}})

        // Get aligned principles
        OPTIONAL MATCH (c)-[:{RelationshipName.ALIGNED_WITH_PRINCIPLE.value}]->(aligned:Entity {{entity_type: 'principle'}})

        // Get any conflicting principles
        OPTIONAL MATCH (c)-[:{RelationshipName.CONFLICTS_WITH_PRINCIPLE.value}]->(conflicting:Entity {{entity_type: 'principle'}})

        // Get user's core principles for comparison
        OPTIONAL MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(core:Entity {{entity_type: 'principle'}})
        WHERE core.strength IN ['CORE', 'STRONG']

        RETURN
            c.uid AS choice_uid,
            c.title AS choice_title,
            c.impact_level AS impact_level,
            collect(DISTINCT aligned.uid) AS aligned_uids,
            collect(DISTINCT {{
                uid: conflicting.uid,
                name: conflicting.name
            }}) AS conflicts,
            collect(DISTINCT core.uid) AS core_principle_uids
        """
        return await self.execute_query(query, {"choice_uid": choice_uid, "user_uid": user_uid})

    async def get_life_path_contribution(
        self, choice_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get life path contribution data for a choice via principles."""
        query = f"""
        MATCH (c:Entity {{uid: $choice_uid, entity_type: 'choice'}})

        // Get user's life path
        OPTIONAL MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.ULTIMATE_PATH.value}]->(lp:Entity {{entity_type: 'learning_path'}})

        // Direct contribution (if any)
        OPTIONAL MATCH (c)-[direct:{RelationshipName.SERVES_LIFE_PATH.value}]->(lp)

        // Principle-mediated contribution
        OPTIONAL MATCH (c)-[:{RelationshipName.ALIGNED_WITH_PRINCIPLE.value}]->(p:Entity {{entity_type: 'principle'}})
                       -[pserve:{RelationshipName.SERVES_LIFE_PATH.value}]->(lp)

        RETURN
            lp.uid AS life_path_uid,
            lp.title AS life_path_title,
            direct.contribution_score AS direct_score,
            collect(DISTINCT {{
                uid: p.uid,
                name: p.name,
                contribution: pserve.contribution_score
            }}) AS principle_contributions
        """
        return await self.execute_query(query, {"choice_uid": choice_uid, "user_uid": user_uid})

    async def get_historical_satisfaction_correlation(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get satisfaction scores for aligned vs unaligned choices."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(c:Entity {{entity_type: 'choice'}})
        WHERE c.satisfaction_score IS NOT NULL
        OPTIONAL MATCH (c)-[:{RelationshipName.ALIGNED_WITH_PRINCIPLE.value}]->(p:Entity {{entity_type: 'principle'}})
        WITH c, count(p) AS principle_count
        RETURN
            avg(CASE WHEN principle_count > 0 THEN c.satisfaction_score ELSE null END) AS aligned_avg,
            avg(CASE WHEN principle_count = 0 THEN c.satisfaction_score ELSE null END) AS unaligned_avg,
            count(c) AS total_choices
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_recent_conflict_count(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Count recent choices (30 days) with unresolved principle conflicts."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(c:Entity {{entity_type: 'choice'}})
        WHERE c.created_at >= datetime() - duration({{days: 30}})
        MATCH (c)-[:{RelationshipName.CONFLICTS_WITH_PRINCIPLE.value}]->(:Entity {{entity_type: 'principle'}})
        RETURN count(DISTINCT c) AS conflict_count
        """
        return await self.execute_query(query, {"user_uid": user_uid})


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

    async def create_user_principle_relationship(
        self, user_uid: UserUID, principle_uid: str
    ) -> Result[bool]:
        """Create User→Principle OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, principle_uid)


class LessonBackend(
    _OrganizesMixin,
    _LearningStateMixin,
    _SemanticMixin,
    _KnowledgeContextMixin,
    _AdaptiveMixin,
    UniversalNeo4jBackend[Lesson],
):
    """Domain backend for Lesson (unit for learning) entities.

    All methods live in focused mixins:
    - ``_OrganizesMixin`` — ORGANIZES relationship management (12 methods)
    - ``_LearningStateMixin`` — user progress tracking: VIEWED, IN_PROGRESS,
      MASTERED, BOOKMARKED, MARKED_AS_READ (13 methods)
    - ``_SemanticMixin`` — semantic relationships + graph analysis (11 methods)
    - ``_KnowledgeContextMixin`` — context, discovery, readiness (13 methods)
    - ``_AdaptiveMixin`` — practice, search, adaptive mastery tracking (10 methods)
    """

    # All methods provided by mixins — see class docstring for inventory.


class SubmissionsBackend(UniversalNeo4jBackend[Submission]):
    """
    Domain backend for Submission entities.

    Uses NeoLabel.ENTITY (not NeoLabel.SUBMISSION) because submissions span
    3 EntityTypes: SUBMISSION, JOURNAL, SUBMISSION_REPORT.

    Sharing and access control live in SharingBackend + UnifiedSharingService,
    operating across all entity types.
    """

    async def count_submissions_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[int]:
        """Count submissions by a user for a specific exercise via FULFILLS_EXERCISE."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(e:Entity {uid: $exercise_uid})
        WHERE s.entity_type IN ['exercise_submission', 'submission']
        RETURN count(s) AS count
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "exercise_uid": exercise_uid}
        )
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(record.get("count", 0))

    async def get_first_submission_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Get earliest submission's uid + created_at for a user+exercise pair."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(e:Entity {uid: $exercise_uid})
        WHERE s.entity_type IN ['exercise_submission', 'submission']
        RETURN s.uid AS uid, s.created_at AS created_at
        ORDER BY s.created_at ASC
        LIMIT 1
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "exercise_uid": exercise_uid}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0])

    async def get_exercise_for_submission(self, submission_uid: str) -> Result[str | None]:
        """Get exercise UID linked to a submission via FULFILLS_EXERCISE."""
        query = """
        MATCH (s:Entity {uid: $submission_uid})-[:FULFILLS_EXERCISE]->(e:Entity)
        RETURN e.uid AS exercise_uid
        LIMIT 1
        """
        result = await self.execute_query(query, {"submission_uid": submission_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["exercise_uid"])

    async def get_teacher_feedback_state(self, teacher_uid: str) -> Result[Neo4jProperties]:
        """Read feedback EMA state from User node for turnaround calibration."""
        query = """
        MATCH (u:User {uid: $teacher_uid})
        RETURN u.feedback_ema_hours AS feedback_ema_hours,
               u.feedback_sample_count AS feedback_sample_count,
               u.feedback_updated_at AS feedback_updated_at
        """
        result = await self.execute_query(query, {"teacher_uid": teacher_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({})
        return Result.ok(result.value[0])

    async def update_teacher_feedback_state(
        self, teacher_uid: str, properties: Neo4jProperties
    ) -> Result[bool]:
        """Write feedback EMA state to User node."""
        query = """
        MATCH (u:User {uid: $teacher_uid})
        SET u += $properties
        RETURN u.uid
        """
        result = await self.execute_query(
            query, {"teacher_uid": teacher_uid, "properties": properties}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=teacher_uid))
        return Result.ok(True)

    # ========================================================================
    # EXERCISE SUBMISSION PROCESSING
    # ========================================================================

    async def get_exercise_context(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Get exercise scope, teacher, group info for submission processing."""
        query = """
        MATCH (exercise:Entity {uid: $exercise_uid})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (exercise)-[:FOR_GROUP]->(g:Group)
        RETURN exercise.entity_type as exercise_entity_type,
               exercise.scope as scope,
               exercise.user_uid as teacher_uid,
               exercise.student_uid as student_uid,
               exercise.title as exercise_title,
               g.uid as group_uid
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_submission_owner(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Get student UID who owns a submission."""
        query = """
        MATCH (student:User)-[:OWNS]->(submission:Entity {uid: $submission_uid})
        RETURN student.uid as student_uid
        """
        return await self.execute_query(query, {"submission_uid": submission_uid})

    async def verify_student_group_membership(
        self, submission_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Check student owns submission AND is member of group."""
        query = """
        MATCH (student:User)-[:OWNS]->(submission:Entity {uid: $submission_uid})
        OPTIONAL MATCH (student)-[:MEMBER_OF]->(g:Group {uid: $group_uid})
        RETURN student.uid as student_uid, g.uid as member_of_group
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "group_uid": group_uid}
        )

    async def link_to_exercise(
        self, submission_uid: str, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FULFILLS_EXERCISE relationship."""
        query = """
        MATCH (submission:Entity {uid: $submission_uid})
        MATCH (exercise:Entity {uid: $exercise_uid})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        MERGE (submission)-[:FULFILLS_EXERCISE]->(exercise)
        RETURN true as success
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "exercise_uid": exercise_uid}
        )

    async def auto_share_with_teacher(
        self, teacher_uid: str, submission_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share submission with teacher via SHARES_WITH."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})
        MATCH (submission:Entity {uid: $submission_uid})
        MERGE (teacher)-[r:SHARES_WITH]->(submission)
        SET r.shared_at = datetime($now),
            r.role = 'teacher'
        RETURN true as success
        """
        return await self.execute_query(
            query,
            {"teacher_uid": teacher_uid, "submission_uid": submission_uid, "now": now},
        )

    # ========================================================================
    # SUBMISSION RELATIONSHIPS
    # ========================================================================

    async def create_temporal_relationship(
        self, ku_uid: str, user_uid: UserUID, entity_type: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOLLOWS relationship to most recent previous submission."""
        query = """
        MATCH (new:Entity {uid: $ku_uid})
        MATCH (prev:Entity {user_uid: $user_uid, entity_type: $entity_type})
        WHERE prev.uid <> $ku_uid
          AND prev.created_at <= new.created_at
        WITH new, prev
        ORDER BY prev.created_at DESC
        LIMIT 1
        MERGE (new)-[r:FOLLOWS]->(prev)
        RETURN count(r) as count
        """
        return await self.execute_query(
            query, {"ku_uid": ku_uid, "user_uid": user_uid, "entity_type": entity_type}
        )

    async def create_thematic_relationships(
        self, ku_uid: str, user_uid: UserUID, themes: list[str], shared_topics_str: str
    ) -> Result[list[Neo4jProperties]]:
        """Create RELATED_TO relationships for shared topics."""
        query = """
        MATCH (new:Entity {uid: $ku_uid})
        MATCH (other:Entity {user_uid: $user_uid})
        WHERE other.uid <> $ku_uid
          AND other.metadata IS NOT NULL
        WITH new, other, other.metadata.themes as other_themes
        WHERE other_themes IS NOT NULL
          AND any(topic IN $themes WHERE topic IN other_themes)
        WITH new, other
        LIMIT 5
        MERGE (new)-[r:RELATED_TO {shared_topics: $shared_topics_str}]->(other)
        RETURN count(r) as count
        """
        return await self.execute_query(
            query,
            {
                "ku_uid": ku_uid,
                "user_uid": user_uid,
                "themes": themes,
                "shared_topics_str": shared_topics_str,
            },
        )

    async def get_related_submission_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get UIDs of submissions related via RELATED_TO."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})-[:RELATED_TO]->(related:Entity)
        RETURN related.uid as uid
        ORDER BY related.uid
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_supported_goal_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get UIDs of goals supported by a submission via SUPPORTS_GOAL."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_submission_relationship_summary(
        self, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get relationship counts for a submission."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})
        OPTIONAL MATCH (a)-[:RELATED_TO]->(related)
        OPTIONAL MATCH (a)-[:SUPPORTS_GOAL]->(goal)
        OPTIONAL MATCH (a)-[:FOLLOWS]->(prev)
        RETURN count(DISTINCT related) as related_count,
               count(DISTINCT goal) as goal_count,
               count(DISTINCT prev) as follows_count
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # ASSESSMENT OPERATIONS
    # ========================================================================

    async def verify_teacher_authority(
        self, teacher_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher-student share an active group."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:OWNS]->(g:Group)
              <-[:MEMBER_OF]-(student:User {uid: $subject_uid})
        WHERE g.is_active = true
        RETURN g.uid AS group_uid LIMIT 1
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "subject_uid": subject_uid}
        )

    async def create_assessment_relationship(
        self, assessment_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create ASSESSMENT_OF relationship from assessment to user."""
        query = """
        MATCH (assessment:Entity {uid: $assessment_uid})
        MATCH (u:User {uid: $subject_uid})
        MERGE (assessment)-[:ASSESSMENT_OF]->(u)
        RETURN true AS success
        """
        return await self.execute_query(
            query, {"assessment_uid": assessment_uid, "subject_uid": subject_uid}
        )

    async def auto_share_assessment_with_student(
        self, subject_uid: str, assessment_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share assessment with student via SHARES_WITH."""
        query = """
        MATCH (student:User {uid: $subject_uid})
        MATCH (assessment:Entity {uid: $assessment_uid})
        MERGE (student)-[rel:SHARES_WITH]->(assessment)
        SET rel.shared_at = datetime($now),
            rel.role = 'student'
        RETURN true AS success
        """
        return await self.execute_query(
            query,
            {"subject_uid": subject_uid, "assessment_uid": assessment_uid, "now": now},
        )

    async def get_assessments_for_student_raw(
        self, student_uid: str, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Get assessment nodes for a student via ASSESSMENT_OF."""
        query = """
        MATCH (report:Entity)-[:ASSESSMENT_OF]->(u:User {uid: $student_uid})
        WHERE report.entity_type = 'exercise_report'
        RETURN report
        ORDER BY report.created_at DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"student_uid": student_uid, "limit": limit})

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's pending review queue (submissions shared via role='teacher')."""
        where_clauses = []
        params: dict[str, Any] = {"teacher_uid": teacher_uid}

        if status_filter:
            where_clauses.append("report.status = $status_filter")
            params["status_filter"] = status_filter

        if entity_type_filter:
            where_clauses.append("report.entity_type = $entity_type_filter")
            params["entity_type_filter"] = entity_type_filter

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[r:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(ku:Entity:Submission)
        {where_clause}
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(project:Entity:Exercise)
        OPTIONAL MATCH (fb:Entity:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(ku)
        WITH ku, student, project, r, count(fb) as feedback_count
        RETURN ku.uid as ku_uid,
               ku.title as title,
               ku.status as status,
               ku.entity_type as entity_type,
               ku.created_at as submitted_at,
               student.uid as student_uid,
               student.name as student_name,
               project.uid as project_uid,
               project.name as project_name,
               project.due_date as due_date,
               r.shared_at as shared_at,
               feedback_count
        ORDER BY ku.created_at DESC
        """
        return await self.execute_query(query, params)

    async def get_report_history(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all SUBMISSION_REPORT nodes linked to a submission via REPORT_FOR."""
        query = f"""
        MATCH (fb:Entity:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(submission:Entity:Submission {{uid: $submission_uid}})
        OPTIONAL MATCH (teacher:User)-[:{RelationshipName.OWNS.value}]->(fb)
        RETURN fb.uid as uid,
               fb.title as title,
               fb.content as content,
               fb.status as status,
               fb.created_at as created_at,
               teacher.uid as teacher_uid,
               teacher.name as teacher_name
        ORDER BY fb.created_at ASC
        """
        return await self.execute_query(query, {"submission_uid": submission_uid})

    async def create_report_node(self, params: dict[str, Any]) -> Result[list[Neo4jProperties]]:
        """Create SUBMISSION_REPORT node, link via REPORT_FOR, share with student, update submission.

        Requires ``allowed_from_statuses`` in params — a Cypher-level guard that
        ensures the submission's current status is valid for the requested transition.
        Returns empty results when the guard rejects the transition (caller already
        verified existence via _verify_teacher_access).
        """
        query = f"""
        MATCH (submission:Entity {{uid: $report_uid}})
        WHERE submission.status IN $allowed_from_statuses
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)

        SET submission.report_content = $feedback,
            submission.report_generated_at = datetime($now),
            submission.status = $submission_status,
            submission.updated_at = datetime($now)

        CREATE (fb:Entity {{
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
            user_uid: $teacher_uid,
            status: $completed_status,
            processor_type: $processor_type,
            assessment_outcome: $assessment_outcome,
            content: $feedback,
            created_by: $teacher_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        }})

        WITH submission, student, fb
        MATCH (teacher:User {{uid: $teacher_uid}})
        CREATE (teacher)-[:{RelationshipName.OWNS.value}]->(fb)
        CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

        WITH submission, student, fb
        WHERE student IS NOT NULL
        CREATE (student)-[:{RelationshipName.SHARES_WITH.value} {{shared_at: datetime($now), role: 'student'}}]->(fb)

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as report_entity_uid
        """
        return await self.execute_query(query, params)

    async def approve_and_get_linked_kus(
        self,
        report_uid: str,
        now: str,
        status: str,
        allowed_from_statuses: list[str],
    ) -> Result[list[Neo4jProperties]]:
        """Approve submission: set status and return linked KU UIDs for mastery.

        Cypher-level guard ensures the submission's current status is in
        ``allowed_from_statuses`` before mutating.  Returns empty results
        when the guard rejects the transition.

        Also traverses FULFILLS_EXERCISE to return the exercise's mastery_impact
        so TeacherReviewService can use MasteryImpact.get_teacher_score().
        """
        query = f"""
        MATCH (ku:Entity {{uid: $report_uid}})
        WHERE ku.status IN $allowed_from_statuses
        SET ku.status = $status,
            ku.updated_at = datetime($now)
        WITH ku
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(curriculum:Entity:Ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise:Entity)
        RETURN ku.uid as uid,
               ku.status as status,
               student.uid as student_uid,
               collect(curriculum.uid) as linked_ku_uids,
               exercise.mastery_impact as mastery_impact
        """
        return await self.execute_query(
            query,
            {
                "report_uid": report_uid,
                "now": now,
                "status": status,
                "allowed_from_statuses": allowed_from_statuses,
            },
        )

    async def get_submissions_for_exercise_review(
        self, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get all submissions against a specific exercise (teacher review view)."""
        query = f"""
        MATCH (s:Entity:Submission)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(e:Entity:Exercise {{uid: $exercise_uid}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (fb:Entity:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, student, count(fb) AS feedback_count
        RETURN s.uid AS uid, s.title AS title,
               s.original_filename AS original_filename, s.status AS status,
               s.created_at AS created_at, student.uid AS student_uid,
               student.name AS student_name, feedback_count
        ORDER BY s.created_at DESC
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Get students who shared work with teacher, with counts."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(ku:Entity:Submission)
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        WITH student, count(ku) AS submission_count,
             count(CASE WHEN ku.status = 'completed' THEN 1 END) AS reviewed_count
        WHERE student IS NOT NULL
        RETURN student.uid AS student_uid, student.name AS student_name,
               submission_count, reviewed_count,
               submission_count - reviewed_count AS pending_count
        ORDER BY pending_count DESC, submission_count DESC
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})

    async def get_student_submissions_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get submissions from a student that were shared with this teacher."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(ku:Entity:Submission)
        MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(ku)
        OPTIONAL MATCH (fb:Entity:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        WITH ku, count(fb) AS feedback_count, ex
        RETURN ku.uid AS uid, ku.title AS title,
               ku.original_filename AS original_filename, ku.status AS status,
               ku.created_at AS created_at,
               feedback_count, ex.uid AS exercise_uid, ex.title AS exercise_title
        ORDER BY ku.created_at DESC
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "student_uid": student_uid}
        )

    async def get_submission_detail_for_teacher(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get full submission detail for teacher review (access-checked via SHARES_WITH)."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(s:Entity:Submission {{uid: $submission_uid}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (s)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        RETURN s.uid AS uid,
               s.title AS title,
               s.content AS content,
               s.processed_content AS processed_content,
               s.original_filename AS original_filename,
               s.entity_type AS entity_type,
               s.status AS status,
               s.created_at AS created_at,
               student.uid AS student_uid,
               student.name AS student_name,
               ex.uid AS exercise_uid,
               ex.title AS exercise_title,
               ex.instructions AS exercise_instructions
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Get at-a-glance stats for the teacher dashboard."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        OPTIONAL MATCH (teacher)-[:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(ku:Entity:Submission)
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(ex:Entity:Exercise)
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(g:Group)
        RETURN
          count(CASE WHEN ku.status IN ['submitted', 'active', 'revision_requested'] THEN 1 END) AS pending_count,
          count(DISTINCT ku) AS total_submissions,
          count(DISTINCT student) AS total_students,
          count(DISTINCT ex) AS total_exercises,
          count(DISTINCT g) AS total_groups
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})

    async def verify_teacher_access(
        self, report_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher has SHARES_WITH access to the entity."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[r:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(ku:Entity {{uid: $report_uid}})
        RETURN true as has_access
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "report_uid": report_uid}
        )

    # ========================================================================
    # REPORT RELATIONSHIP QUERIES (migrated from ReportRelationshipService)
    # ========================================================================

    async def get_pending_submissions_raw(
        self, user_uid: UserUID, submission_types: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get submissions without a REPORT_FOR relationship."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
          AND NOT ()-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        RETURN submission.uid AS uid
        ORDER BY submission.created_at DESC
        LIMIT 20
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "submission_types": submission_types}
        )

    async def get_unsubmitted_exercises_raw(
        self, user_uid: UserUID, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises assigned via group with no submission yet."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF.value}]->(group:Group)
        MATCH (exercise:Entity {{entity_type: 'exercise', scope: 'assigned'}})-[:{RelationshipName.FOR_GROUP.value}]->(group)
        WHERE NOT (:Entity {{user_uid: $user_uid}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
        RETURN exercise.uid AS uid,
               exercise.title AS title,
               exercise.due_date AS due_date
        ORDER BY exercise.due_date ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def get_report_summary_raw(
        self, user_uid: UserUID, submission_types: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get report completion counts for a user's submissions."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        WITH submission, count(fb) AS report_count
        RETURN
            count(submission) AS total_submissions,
            count(CASE WHEN report_count > 0 THEN 1 END) AS with_report,
            count(CASE WHEN report_count = 0 THEN 1 END) AS without_report,
            sum(report_count) AS total_reports
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "submission_types": submission_types}
        )

    async def get_learning_loop_chain_raw(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse full learning loop chain from an exercise."""
        query = f"""
        MATCH (ex:Entity {{uid: $exercise_uid}})
        WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex)
          WHERE sub.entity_type = 'exercise_submission'
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'exercise_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN ex {{.uid, .title, .entity_type, .status, .created_at}} AS exercise,
               collect(DISTINCT sub {{.uid, .title, .status, .created_at, .user_uid}}) AS submissions,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_submission_chain_raw(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse learning loop chain from a specific submission."""
        query = f"""
        MATCH (sub:Entity {{uid: $submission_uid, entity_type: 'exercise_submission'}})
        OPTIONAL MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
          WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'exercise_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN sub {{.uid, .title, .status, .created_at, .user_uid}} AS submission,
               ex {{.uid, .title, .entity_type, .status}} AS exercise,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .student_uid, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(query, {"submission_uid": submission_uid})


class KuBackend(UniversalNeo4jBackend[Ku]):
    """Domain backend for atomic Knowledge Unit entities.

    Lightweight reference nodes with reverse-traversal methods:
    - get_lessons_using(ku_uid) — Lessons that USES_KU this Ku
    """

    async def get_lessons_using(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all Lessons that use this atomic Ku via USES_KU."""
        query = """
        MATCH (lesson:Entity)-[:USES_KU]->(ku:Entity {uid: $ku_uid})
        RETURN lesson.uid AS uid, lesson.title AS title,
               lesson.description AS description
        ORDER BY lesson.title
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_usage_summary(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count lessons (USES_KU), learning steps (TRAINS_KU), organized children."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (lesson:Entity)-[:USES_KU]->(ku)
        OPTIONAL MATCH (ls:Entity)-[:TRAINS_KU]->(ku)
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
        RETURN count(DISTINCT lesson) as lessons,
               count(DISTINCT ls) as learning_steps,
               count(DISTINCT child) as organized_children
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_trained(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if any Learning Step trains this Ku via TRAINS_KU."""
        query = """
        MATCH (ls:Entity)-[:TRAINS_KU]->(ku:Entity:Ku {uid: $ku_uid})
        RETURN count(ls) > 0 as trained
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_organized(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if this Ku has ORGANIZES children (acts as MOC)."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES]->(child:Entity)
        RETURN count(child) > 0 as organized
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_organization_depth(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get depth of the ORGANIZES tree below this Ku."""
        query = """
        MATCH path = (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES*]->(descendant:Entity)
        RETURN max(length(path)) as max_depth
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_by_namespace(self, namespace: str) -> Result[list[Neo4jProperties]]:
        """Get all Kus in a specific namespace."""
        query = """
        MATCH (ku:Entity:Ku {namespace: $namespace})
        RETURN ku
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"namespace": namespace})

    async def search_by_alias(self, alias: str) -> Result[list[Neo4jProperties]]:
        """Search Kus by alias (case-insensitive substring)."""
        query = """
        MATCH (ku:Entity:Ku)
        WHERE any(a IN ku.aliases WHERE toLower(a) CONTAINS toLower($alias))
        RETURN ku
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"alias": alias})

    # ========================================================================
    # SUBSTANCE METRICS (migrated from LessonService)
    # ========================================================================

    async def batch_increment_substance(
        self,
        ku_uids: list[str],
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for multiple KUs in one query."""
        query = f"""
        UNWIND $ku_uids AS ku_uid
        MATCH (ku:Entity {{uid: ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        RETURN count(ku) as updated_count
        """
        result = await self.execute_query(query, {"ku_uids": ku_uids, "timestamp": timestamp_str})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(records[0]["updated_count"] if records else 0)

    async def increment_substance(
        self,
        ku_uid: str,
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for a single KU."""
        query = f"""
        MATCH (ku:Entity {{uid: $ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        RETURN ku.{metric} as new_count
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid, "timestamp": timestamp_str})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(records[0]["new_count"] if records else 0)

    # ========================================================================
    # KU RELATIONSHIP QUERIES (migrated from ku_relationships.py helpers)
    # ========================================================================

    async def get_related_knowledge_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get related knowledge units (RELATED_TO relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:RELATED_TO]-(related:Entity)
        RETURN related.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_broader_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get broader concepts (HAS_BROADER relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:HAS_BROADER]->(broader:Entity)
        RETURN broader.uid as uid
        LIMIT 20
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_narrower_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get narrower concepts (HAS_NARROWER relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:HAS_NARROWER]->(narrower:Entity)
        RETURN narrower.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_learning_path_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get learning paths containing this KU."""
        query = """
        MATCH (lp:Lp)-[:CONTAINS_KNOWLEDGE|INCLUDES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN lp.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_applying_task_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get tasks applying this knowledge."""
        query = """
        MATCH (task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN task.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_practicing_event_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get events practicing this knowledge."""
        query = """
        MATCH (event:Event)-[:PRACTICES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN event.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_reinforcing_habit_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get habits reinforcing this knowledge."""
        query = """
        MATCH (habit:Habit)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN habit.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # PREREQUISITE & DEPENDENCY QUERIES (migrated from ContextRetriever)
    # ========================================================================

    async def get_unmastered_prerequisites(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get unmastered prerequisites for a knowledge unit (depth 1..3).

        Traverses REQUIRES_KNOWLEDGE chains up to 3 hops, filtering out
        prerequisites the user has already MASTERED.

        Returns:
            Single record with 'prerequisites' key containing list of
            {uid, title} dicts.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE*1..3]->(prereq:Entity)
        WHERE NOT EXISTS {
            MATCH (u:User {uid: $user_uid})-[:MASTERED]->(prereq)
        }
        RETURN collect(DISTINCT {uid: prereq.uid, title: prereq.title}) AS prerequisites
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "user_uid": user_uid})

    async def count_dependents(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count entities that depend on this knowledge unit via REQUIRES_KNOWLEDGE.

        Returns:
            Single record with 'unlocks_count' key.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)
        RETURN count(DISTINCT dependent) AS unlocks_count
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # LEARNING STATE (Ku-native — two-tier: Studying + Understood)
    # ========================================================================

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as actively being studied (IN_PROGRESS relationship)."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        MERGE (user)-[r:IN_PROGRESS]->(ku)
        ON CREATE SET
            r.started_at = datetime(),
            r.last_activity_at = datetime(),
            r.progress_score = 0.0
        ON MATCH SET
            r.last_activity_at = datetime()
        RETURN ku.uid AS uid
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def mark_mastered(
        self,
        user_uid: UserUID,
        ku_uid: str,
        mastery_score: float = 0.7,
        method: str = "self_report",
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as understood/mastered by the user."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        MERGE (user)-[r:MASTERED]->(ku)
        ON CREATE SET
            r.mastered_at = datetime(),
            r.mastery_score = $mastery_score,
            r.confidence = $mastery_score,
            r.method = $method
        ON MATCH SET
            r.mastery_score = CASE
                WHEN $mastery_score > r.mastery_score THEN $mastery_score
                ELSE r.mastery_score
            END,
            r.confidence = CASE
                WHEN $mastery_score > coalesce(r.confidence, 0) THEN $mastery_score
                ELSE r.confidence
            END,
            r.method = $method
        RETURN ku.uid AS uid
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "mastery_score": mastery_score,
                "method": method,
            },
        )

    async def get_ku_learning_state(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get user's learning state for a Ku (IN_PROGRESS, MASTERED, MARKED_AS_READ)."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        RETURN
            p IS NOT NULL AS is_studying,
            m IS NOT NULL AS is_understood,
            mr IS NOT NULL AS is_marked_as_read
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def get_user_learning_states(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all Kus with their learning state for a user."""
        query = """
        MATCH (ku:Entity:Ku)
        WHERE EXISTS { (u:User {uid: $user_uid})-[:IN_PROGRESS|MASTERED|MARKED_AS_READ]->(ku) }
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        RETURN ku.uid AS uid, ku.title AS title,
               (p IS NOT NULL OR mr IS NOT NULL) AS is_studying,
               m IS NOT NULL AS is_understood
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"user_uid": user_uid})


class LsBackend(UniversalNeo4jBackend[LearningStep]):
    """
    Domain backend for LearningStep entities.

    Extends UniversalNeo4jBackend[LearningStep] with:
    - Knowledge relationship CRUD (CONTAINS_KNOWLEDGE edges)
    - Lesson completion progress tracking
    """

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP CRUD (CONTAINS_KNOWLEDGE edges)
    # ========================================================================

    async def add_knowledge(self, ls_uid: str, ku_uid: str) -> Result[bool]:
        """MERGE CONTAINS_KNOWLEDGE relationship between LS and KU."""
        query = """
        MATCH (ls:Entity {uid: $ls_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
        SET r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """
        result = await self.execute_query(query, {"ls_uid": ls_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        success = len(result.value or []) > 0
        if success:
            self.logger.info(f"Created CONTAINS_KNOWLEDGE: {ls_uid} -> {ku_uid}")
        return Result.ok(success)

    async def remove_knowledge(self, ls_uid: str, ku_uid: str) -> Result[bool]:
        """DELETE CONTAINS_KNOWLEDGE relationship between LS and KU."""
        query = """
        MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        DELETE r
        RETURN count(r) as deleted
        """
        result = await self.execute_query(query, {"ls_uid": ls_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        deleted = records[0]["deleted"] if records else 0
        success = deleted > 0
        if success:
            self.logger.info(f"Removed CONTAINS_KNOWLEDGE: {ls_uid} -> {ku_uid}")
        return Result.ok(success)

    async def list_knowledge(self, ls_uid: str) -> Result[list[LsKnowledgeItemResult]]:
        """List CONTAINS_KNOWLEDGE relationships."""
        query = """
        MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN ku.uid as uid, ku.title as title, ku.domain as domain,
               r.created_at as created_at
        ORDER BY r.created_at, ku.title
        """
        result = await self.execute_query(query, {"ls_uid": ls_uid})
        if result.is_error:
            return Result.fail(result)
        items: list[LsKnowledgeItemResult] = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "domain": r["domain"],
                "created_at": r["created_at"],
            }
            for r in result.value or []
        ]
        return Result.ok(items)

    async def get_knowledge_summary(self, ls_uid: str) -> Result[LsKnowledgeSummaryResult]:
        """Aggregate count and UIDs of knowledge in this step."""
        query = """
        MATCH (ls:Entity {uid: $ls_uid})
        OPTIONAL MATCH (ls)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN count(r) as count, collect(ku.uid) as uids
        """
        result = await self.execute_query(query, {"ls_uid": ls_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok({"count": 0, "uids": []})
        record = records[0]
        return Result.ok(
            {
                "count": record["count"],
                "uids": [uid for uid in record["uids"] if uid],
            }
        )

    # ========================================================================
    # LESSON PROGRESS TRACKING
    # ========================================================================

    async def get_steps_containing_lesson(self, lesson_uid: str) -> Result[list[str]]:
        """
        Find all LSs that contain a Lesson via HAS_LESSON.

        Used by LsProgressService to find which LSs to update
        when a Lesson is completed.

        Args:
            lesson_uid: Lesson UID

        Returns:
            Result containing list of LS UIDs
        """
        query = """
        MATCH (ls:Entity {entity_type: 'learning_step'})-[:HAS_LESSON]->(lesson:Entity {uid: $lesson_uid})
        RETURN DISTINCT ls.uid as ls_uid
        """
        result = await self.execute_query(query, {"lesson_uid": lesson_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok([record["ls_uid"] for record in records])

    async def get_lesson_completion_progress(
        self, ls_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """
        Return total and completed Lesson counts for LS progress calculation.

        A Lesson is "completed" when all its KUs are mastered by the user.

        Args:
            ls_uid: Learning Step UID
            user_uid: User UID

        Returns:
            Result containing dict with total_lessons and completed_lessons
        """
        query = """
        MATCH (ls:Entity {uid: $ls_uid})-[:HAS_LESSON]->(lesson:Entity {entity_type: 'lesson'})
        WITH ls, collect(DISTINCT lesson) as all_lessons, count(DISTINCT lesson) as total
        UNWIND all_lessons as lesson
        OPTIONAL MATCH (lesson)-[:USES_KU]->(ku:Entity)
        WITH ls, lesson, total, collect(DISTINCT ku.uid) as ku_uids, count(DISTINCT ku) as ku_count
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
        WHERE mastered.uid IN ku_uids
        WITH ls, lesson, total, ku_count, count(DISTINCT mastered) as mastered_count
        WITH total, collect(CASE WHEN ku_count > 0 AND mastered_count = ku_count THEN lesson.uid END) as completed
        RETURN total as total_lessons,
               size([x IN completed WHERE x IS NOT NULL]) as completed_lessons
        """
        result = await self.execute_query(query, {"ls_uid": ls_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({"total_lessons": 0, "completed_lessons": 0})
        record = result.value[0]
        return Result.ok(
            {
                "total_lessons": record["total_lessons"],
                "completed_lessons": record["completed_lessons"],
            }
        )

    # ========================================================================
    # CORE CRUD QUERIES (migrated from LsCoreService)
    # ========================================================================

    async def create_step_node(
        self,
        params: dict[str, Any],
        has_knowledge: bool = False,
        path_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Create step node with conditional knowledge and path relationships."""
        query = """
        CREATE (s:Entity {
            uid: $uid,
            entity_type: 'learning_step',
            title: $title,
            intent: $intent,
            description: $description,
            learning_path_uid: $learning_path_uid,
            sequence: $sequence,
            mastery_threshold: $mastery_threshold,
            current_mastery: $current_mastery,
            estimated_hours: $estimated_hours,
            step_difficulty: $step_difficulty,
            status: $status,
            completed: $completed,
            domain: $domain
        })
        """
        if has_knowledge:
            query += """
            WITH s
            UNWIND $knowledge_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            MERGE (s)-[r:CONTAINS_KNOWLEDGE]->(ku)
            ON CREATE SET r.created_at = datetime()
            """
        if path_uid:
            query += """
            WITH s
            MATCH (p:Entity {uid: $path_uid})
            MERGE (p)-[r:HAS_STEP]->(s)
            ON CREATE SET r.sequence = $sequence
            """
        query += """
        WITH s
        RETURN s
        """
        return await self.execute_query(query, params)

    async def get_step_with_knowledge(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Get step node with CONTAINS_KNOWLEDGE relationships."""
        query = """
        MATCH (s:Entity {uid: $uid})
        OPTIONAL MATCH (s)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        return await self.execute_query(query, {"uid": uid})

    async def get_step_with_context(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Get step with comprehensive 11-part graph context in a single query."""
        query = """
        MATCH (ls:Entity {uid: $uid})

        // 1. Knowledge references
        OPTIONAL MATCH (ls)-[r_ku:CONTAINS_KNOWLEDGE]->(ku:Entity)
        WITH ls, collect({
            uid: ku.uid,
            title: ku.title,
            confidence: coalesce(r_ku.confidence, 1.0)
        }) as knowledge_rels

        // 2. Prerequisite steps
        OPTIONAL MATCH (ls)-[:REQUIRES_STEP]->(prereq_step:Entity {entity_type: 'learning_step'})
        WITH ls, knowledge_rels, collect({
            uid: prereq_step.uid,
            title: prereq_step.title,
            completed: prereq_step.completed
        }) as prereq_steps

        // 3. Prerequisite knowledge
        OPTIONAL MATCH (ls)-[:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(prereq_ku:Entity)
        WITH ls, knowledge_rels, prereq_steps, collect({
            uid: prereq_ku.uid,
            title: prereq_ku.title
        }) as prereq_knowledge

        // 4. Guiding principles (via Lessons)
        OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l4)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, collect(DISTINCT {
            uid: principle.uid,
            title: principle.title
        }) as principles

        // 5. Informed choices (via Lessons)
        OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l5)-[:INFORMS_CHOICE]->(choice:Choice)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, collect(DISTINCT {
            uid: choice.uid,
            title: choice.title
        }) as choices

        // 6. Practice opportunities: Habits (via Lessons)
        OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l6)-[:BUILDS_HABIT]->(habit:Habit)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, collect(DISTINCT {
            uid: habit.uid,
            title: habit.title,
            current_streak: habit.current_streak
        }) as habits

        // 7. Practice opportunities: Tasks (via Lessons)
        OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l7)-[:ASSIGNS_TASK]->(task:Task)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, collect(DISTINCT {
            uid: task.uid,
            title: task.title,
            status: task.status
        }) as tasks

        // 8. Practice opportunities: Events (via Lessons)
        OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l8)-[:SCHEDULES_EVENT]->(event:Event)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, collect(DISTINCT {
            uid: event.uid,
            title: event.title,
            event_date: event.event_date
        }) as events

        // 9. Practice opportunities: Goals (via Lessons)
        OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l9)-[:SUPPORTS_GOAL]->(goal:Goal)
        With ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, collect(DISTINCT {
            uid: goal.uid,
            title: goal.title,
            status: goal.status
        }) as goals

        // 10. Learning path context (if part of sequence)
        OPTIONAL MATCH (lp:Entity {entity_type: 'learning_path'})-[r_path:HAS_STEP|CONTAINS_STEP]->(ls)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, goals, {
            uid: lp.uid,
            name: lp.title,
            goal: lp.goal,
            sequence: coalesce(r_path.sequence, 0)
        } as path_context

        // 11. Dependent steps (steps that require this one)
        OPTIONAL MATCH (dependent:Entity {entity_type: 'learning_step'})-[:REQUIRES_STEP]->(ls)
        WITH ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, goals, path_context, collect({
            uid: dependent.uid,
            title: dependent.title,
            completed: dependent.completed
        }) as dependent_steps

        RETURN ls, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices,
               habits, tasks, events, goals, path_context, dependent_steps
        """
        return await self.execute_query(query, {"uid": uid})

    async def update_step_fields(
        self, _uid: str, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]:
        """Update step fields and return step with knowledge relationships."""
        query = f"""
        MATCH (s:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        WITH s
        OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        return await self.execute_query(query, params)

    async def delete_step_node(self, uid: str) -> Result[list[dict[str, Any]]]:
        """DETACH DELETE a step node and return deletion count."""
        query = """
        MATCH (s:Entity {uid: $uid})
        DETACH DELETE s
        RETURN count(s) as deleted_count
        """
        return await self.execute_query(query, {"uid": uid})

    async def list_steps_raw(
        self,
        path_uid: str | None,
        limit: int,
        offset: int,
        order_field: str,
        order_direction: str,
        user_uid: UserUID | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """List step nodes with knowledge relationships, pagination, and optional filters."""
        where_clause = "WHERE s.user_uid = $user_uid " if user_uid else ""

        if path_uid:
            query = f"""
            MATCH (p:Entity {{uid: $path_uid}})-[:HAS_STEP]->(s:Entity {{entity_type: 'learning_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
            WITH s, collect(ku.uid) as knowledge_uids
            RETURN s, knowledge_uids
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """
        else:
            query = f"""
            MATCH (s:Entity {{entity_type: 'learning_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
            WITH s, collect(ku.uid) as knowledge_uids
            RETURN s, knowledge_uids
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if path_uid:
            params["path_uid"] = path_uid
        if user_uid:
            params["user_uid"] = user_uid

        return await self.execute_query(query, params)


class LpBackend(UniversalNeo4jBackend[LearningPath]):
    """
    Domain backend for LearningPath entities.

    Extends UniversalNeo4jBackend[LearningPath] with:
    - Step management CRUD (HAS_STEP edges)
    - KU mastery progress tracking
    """

    # ========================================================================
    # STEP MANAGEMENT (HAS_STEP edges)
    # ========================================================================

    async def get_steps_raw(self, path_uid: str, depth: int = 1) -> Result[list[dict[str, Any]]]:
        """Get ordered steps in a learning path as raw dicts."""
        query = f"""
        MATCH (lp:Entity {{uid: $path_uid}})-[r:HAS_STEP*1..{depth}]->(ls:Entity {{entity_type: 'learning_step'}})
        RETURN ls, r[0].sequence as sequence
        ORDER BY sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ls"] for record in (result.value or [])])

    async def get_parent_path_raw(self, step_uid: str) -> Result[dict[str, Any] | None]:
        """Get parent learning path for a step as raw dict, or None."""
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:HAS_STEP]->(ls:Entity {uid: $step_uid})
        RETURN lp
        LIMIT 1
        """
        result = await self.execute_query(query, {"step_uid": step_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["lp"])

    async def add_step_to_path(
        self, path_uid: str, step_uid: str, sequence: int, order: int = 0
    ) -> Result[bool]:
        """Create HAS_STEP relationship between path and step (idempotent)."""
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        MATCH (ls:Entity {uid: $step_uid})
        MERGE (lp)-[r:HAS_STEP]->(ls)
        ON CREATE SET
            r.sequence = $sequence,
            r.order = $order,
            r.created_at = datetime()
        RETURN true as success
        """
        result = await self.execute_query(
            query,
            {"path_uid": path_uid, "step_uid": step_uid, "sequence": sequence, "order": order},
        )
        if result.is_error:
            return Result.fail(result)
        if result.value:
            self.logger.info(f"Added step {step_uid} to path {path_uid} at sequence {sequence}")
            return Result.ok(True)
        return Result.fail(
            Errors.database(operation="add_step_to_path", message="Failed to add step to path")
        )

    async def remove_step_from_path(self, path_uid: str, step_uid: str) -> Result[bool]:
        """Remove HAS_STEP relationship and reorder remaining steps."""
        # Delete the relationship
        delete_query = """
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(ls:Entity {uid: $step_uid})
        DELETE r
        RETURN count(r) as deleted_count
        """
        result = await self.execute_query(
            delete_query, {"path_uid": path_uid, "step_uid": step_uid}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value or result.value[0]["deleted_count"] == 0:
            return Result.ok(False)

        # Reorder remaining steps to close gaps
        reorder_query = """
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(ls:Entity {entity_type: 'learning_step'})
        WITH ls, r
        ORDER BY r.sequence
        WITH collect(ls) as steps
        UNWIND range(0, size(steps)-1) as idx
        MATCH (lp:Entity {uid: $path_uid})-[r:HAS_STEP]->(steps[idx])
        SET r.sequence = idx
        RETURN count(r) as updated
        """
        await self.execute_query(reorder_query, {"path_uid": path_uid})
        self.logger.info(f"Removed step {step_uid} from path {path_uid} and reordered")
        return Result.ok(True)

    async def reorder_steps(self, path_uid: str, step_uids: list[str]) -> Result[bool]:
        """Batch reorder all steps in a path."""
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        WITH lp
        UNWIND range(0, size($step_uids)-1) as idx
        MATCH (lp)-[r:HAS_STEP]->(ls:Entity {uid: $step_uids[idx]})
        SET r.sequence = idx
        RETURN count(r) as updated
        """
        result = await self.execute_query(query, {"path_uid": path_uid, "step_uids": step_uids})
        if result.is_error:
            return Result.fail(result)
        updated = result.value[0]["updated"] if result.value else 0
        success = updated == len(step_uids)
        if success:
            self.logger.info(f"Reordered {updated} steps in path {path_uid}")
        return Result.ok(success)

    # ========================================================================
    # KU MASTERY PROGRESS TRACKING
    # ========================================================================

    async def get_paths_containing_ku(self, ku_uid: str) -> Result[list[str]]:
        """
        Return the UIDs of all learning paths that include the given KU.

        Used by LpProgressService to find which LPs to update when a KU is mastered.

        Args:
            ku_uid: Knowledge Unit UID

        Returns:
            Result containing list of LP UIDs
        """
        query = """
        MATCH (lp:Entity {entity_type: 'learning_path'})-[:INCLUDES_KU|REQUIRES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN DISTINCT lp.uid as lp_uid
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok([record["lp_uid"] for record in records])

    async def get_ku_mastery_progress(
        self, lp_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """
        Return total and mastered KU counts for a user's progress in a learning path.

        Used by LpProgressService to calculate new progress percentage after a KU
        is mastered.

        Args:
            lp_uid: Learning Path UID
            user_uid: User UID

        Returns:
            Result containing dict with 'total_kus' and 'mastered_kus' keys,
            or empty dict if the learning path contains no KUs.
        """
        query = """
        MATCH (lp:Entity {uid: $lp_uid})-[:INCLUDES_KU|REQUIRES_KNOWLEDGE]->(ku:Entity)
        WITH count(DISTINCT ku) as total_kus
        MATCH (lp:Entity {uid: $lp_uid})-[:INCLUDES_KU|REQUIRES_KNOWLEDGE]->(ku:Entity)
        MATCH (user:User {uid: $user_uid})-[:MASTERED]->(ku)
        WITH total_kus, count(DISTINCT ku) as mastered_kus
        RETURN total_kus, mastered_kus
        """
        result = await self.execute_query(query, {"lp_uid": lp_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok({})
        return Result.ok(dict(records[0]))


class ExerciseBackend(UniversalNeo4jBackend[Exercise]):
    """
    Domain backend for Exercise entities.

    Extends UniversalNeo4jBackend[Exercise] with exercise-specific Cypher
    that was previously inline in ExerciseService.

    Methods:
    - create_owns_relationship      — MERGE OWNS (user -> exercise)
    - create_for_group_relationship — MERGE FOR_GROUP (exercise -> group)
    - get_user_exercises             — OWNS query for user's exercises
    - get_student_exercises          — MEMBER_OF + FOR_GROUP traversal
    - get_student_exercises_with_status — Above + FULFILLS_EXERCISE submission check
    - get_exercises_for_curriculum   — Reverse REQUIRES_KNOWLEDGE lookup
    - link_to_curriculum             — MERGE REQUIRES_KNOWLEDGE relationship
    - unlink_from_curriculum         — DELETE REQUIRES_KNOWLEDGE relationship
    - get_required_knowledge         — Query all KUs required by an exercise
    - get_exercise_for_submission    — FULFILLS_EXERCISE reverse lookup
    """

    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Create REQUIRES_KNOWLEDGE relationship from exercise to curriculum KU.

        Args:
            exercise_uid: Exercise UID (entity_type='exercise')
            curriculum_uid: Curriculum KU UID (entity_type='ku' or 'resource')

        Returns:
            Result[bool] - True if relationship created
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (curriculum:Entity {{uid: $curriculum_uid}})
            WHERE curriculum.entity_type IN ['ku', 'resource']
            MERGE (exercise)-[r:{RelationshipName.REQUIRES_KNOWLEDGE}]->(curriculum)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="Exercise or Curriculum KU",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Remove REQUIRES_KNOWLEDGE relationship between exercise and curriculum KU.

        Args:
            exercise_uid: Exercise UID
            curriculum_uid: Curriculum KU UID

        Returns:
            Result[bool] - True if relationship removed
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                  -[r:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            DELETE r
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REQUIRES_KNOWLEDGE relationship",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def get_required_knowledge(
        self, exercise_uid: str
    ) -> Result[list[RequiredKnowledgeResult]]:
        """
        Get all curriculum KUs required by an exercise.

        Args:
            exercise_uid: Exercise UID

        Returns:
            Result containing list of curriculum KU summaries
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity)
            RETURN curriculum.uid as uid,
                   curriculum.title as title,
                   curriculum.entity_type as entity_type,
                   curriculum.complexity as complexity,
                   curriculum.learning_level as learning_level
            ORDER BY curriculum.title
            """,
            {"exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[RequiredKnowledgeResult] = [dict(record) for record in (result.value or [])]  # type: ignore[misc]
        return Result.ok(items)

    async def create_owns_relationship(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create OWNS relationship from user to exercise.

        Args:
            user_uid: User who owns this exercise
            exercise_uid: Exercise UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (e:Entity {{uid: $exercise_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(e)
            RETURN true as success
            """,
            {"user_uid": user_uid, "exercise_uid": exercise_uid},
        )

    async def create_for_group_relationship(
        self, exercise_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOR_GROUP relationship from exercise to group.

        Args:
            exercise_uid: Exercise UID
            group_uid: Target group UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (group:Group {{uid: $group_uid}})
            MERGE (exercise)-[:{RelationshipName.FOR_GROUP}]->(group)
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "group_uid": group_uid},
        )

    async def get_user_exercises(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all exercises owned by a user via OWNS relationship.

        Args:
            user_uid: User UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Exercise)
            RETURN e
            ORDER BY e.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises for a student via MEMBER_OF -> Group <- FOR_GROUP.

        Args:
            user_uid: Student UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            RETURN exercise
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises with submission status for a student.

        Returns exercise properties enriched with has_submission flag and group_name.

        Args:
            user_uid: Student UID

        Returns:
            Result containing enriched exercise records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            RETURN exercise, sub IS NOT NULL AS has_submission, group.title AS group_name
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[CurriculumExerciseResult]]:
        """Get all exercises that require a specific curriculum KU.

        Args:
            curriculum_uid: Curriculum KU UID

        Returns:
            Result containing exercise summary records
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            RETURN exercise.uid as uid,
                   exercise.title as title,
                   exercise.scope as scope,
                   exercise.due_date as due_date,
                   exercise.status as status,
                   exercise.form_schema as form_schema
            ORDER BY exercise.created_at DESC
            """,
            {"curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[CurriculumExerciseResult] = [
            dict(record)
            for record in (result.value or [])  # type: ignore[misc]
        ]
        return Result.ok(items)

    async def get_exercise_for_submission(
        self, submission_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Get the exercise that a submission fulfills via FULFILLS_EXERCISE relationship.

        Args:
            submission_uid: Submission UID

        Returns:
            Result containing exercise summary dict or None if not linked
        """
        result = await self.execute_query(
            f"""
            MATCH (s:Entity {{uid: $uid}})-[:{RelationshipName.FULFILLS_EXERCISE}]->(ex:Entity:Exercise)
            RETURN ex.uid AS exercise_uid, ex.title AS exercise_title
            LIMIT 1
            """,
            {"uid": submission_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(dict(records[0]))

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's exercises with submission and reviewed counts."""
        query = f"""
        MATCH (user:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(exercise:Entity:Exercise)
        OPTIONAL MATCH (s:Entity:Submission)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
        WITH exercise, count(s) AS total_count,
             count(CASE WHEN s.status = 'completed' THEN 1 END) AS reviewed_count
        RETURN exercise.uid AS uid, exercise.title AS title,
               exercise.scope AS scope, exercise.created_at AS created_at,
               total_count, reviewed_count,
               total_count - reviewed_count AS pending_count
        ORDER BY exercise.created_at DESC
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})


class RevisedExerciseBackend(UniversalNeo4jBackend["RevisedExercise"]):
    """
    Domain backend for RevisedExercise entities.

    Provides relationship-specific Cypher for the five-phase learning loop:
    - verify_teacher_authority    — Check teacher review authority graph path
    - create_owns_relationship   — MERGE OWNS (teacher -> revised exercise)
    - auto_share_with_student    — MERGE SHARES_WITH (student -> revised exercise)
    - list_for_student           — Query revisions targeting a student
    - link_to_report             — MERGE RESPONDS_TO_REPORT relationship
    - link_to_exercise           — MERGE REVISES_EXERCISE relationship
    - get_revision_chain         — Query all revisions of an original exercise
    """

    async def link_to_report(self, re_uid: str, report_uid: str) -> Result[bool]:
        """Create RESPONDS_TO_REPORT relationship from revised exercise to report."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (fb:Entity {{uid: $report_uid}})
            WHERE fb.entity_type IN ['exercise_report', 'activity_report']
            MERGE (re)-[r:{RelationshipName.RESPONDS_TO_REPORT}]->(fb)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "report_uid": report_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="RESPONDS_TO_REPORT relationship",
                    identifier=f"{re_uid} -> {report_uid}",
                )
            )
        return Result.ok(True)

    async def link_to_exercise(self, re_uid: str, exercise_uid: str) -> Result[bool]:
        """Create REVISES_EXERCISE relationship from revised exercise to original exercise."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MERGE (re)-[r:{RelationshipName.REVISES_EXERCISE}]->(ex)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REVISES_EXERCISE relationship",
                    identifier=f"{re_uid} -> {exercise_uid}",
                )
            )
        return Result.ok(True)

    async def verify_teacher_authority(
        self, teacher_uid: str, report_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher has review authority over a report.

        Checks the graph path:
        - (ExerciseReport)-[:REPORT_FOR]->(Submission) exists
        - (Teacher)-[:SHARES_WITH {role:'teacher'}]->(Submission)
        - (Student)-[:OWNS]->(Submission)

        Args:
            teacher_uid: Teacher user UID
            report_uid: Report UID
            student_uid: Student user UID

        Returns:
            Result containing matching submission records (empty if no authority)
        """
        return await self.execute_query(
            """
            MATCH (fb:Entity {uid: $report_uid})-[:REPORT_FOR]->(submission:Entity)
            MATCH (teacher:User {uid: $teacher_uid})-[:SHARES_WITH {role: 'teacher'}]->(submission)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            RETURN submission.uid AS submission_uid
            """,
            {
                "report_uid": report_uid,
                "teacher_uid": teacher_uid,
                "student_uid": student_uid,
            },
        )

    async def create_owns_relationship(
        self, teacher_uid: str, re_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create OWNS relationship from teacher to revised exercise.

        Args:
            teacher_uid: Teacher user UID
            re_uid: Revised exercise UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $teacher_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(re)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "re_uid": re_uid},
        )

    async def auto_share_with_student(
        self, student_uid: str, re_uid: str, shared_at: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share revised exercise with student via SHARES_WITH.

        Same pattern as assignment auto-sharing (ADR-040).

        Args:
            student_uid: Student user UID
            re_uid: Revised exercise UID
            shared_at: ISO timestamp for the share

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (student:User {{uid: $student_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (student)-[r:{RelationshipName.SHARES_WITH.value}]->(re)
            ON CREATE SET r.shared_at = $shared_at, r.role = 'student'
            SET re.visibility = 'shared'
            RETURN true as success
            """,
            {
                "student_uid": student_uid,
                "re_uid": re_uid,
                "shared_at": shared_at,
            },
        )

    async def list_for_student(
        self, student_uid: str, teacher_uid: str | None = None
    ) -> Result[list[Neo4jProperties]]:
        """List revised exercises targeting a specific student.

        Args:
            student_uid: The student whose revisions to list
            teacher_uid: If provided, only return revisions owned by this teacher

        Returns:
            Result containing revised exercise node records
        """
        if teacher_uid:
            query = f"""
            MATCH (u:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise {{student_uid: $student_uid}})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params: dict[str, str] = {"student_uid": student_uid, "teacher_uid": teacher_uid}
        else:
            query = """
            MATCH (re:RevisedExercise {student_uid: $student_uid})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params = {"student_uid": student_uid}

        return await self.execute_query(query, params)

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[RevisionChainResult]]:
        """
        Get all revised exercises in the revision chain for an original exercise.

        Returns revisions ordered by revision_number ascending.
        """
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{entity_type: 'revised_exercise'}})
                  -[:{RelationshipName.REVISES_EXERCISE}]->
                  (ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            RETURN re.uid as uid,
                   re.title as title,
                   re.revision_number as revision_number,
                   re.student_uid as student_uid,
                   re.report_uid as report_uid,
                   re.status as status,
                   re.created_at as created_at
            ORDER BY re.revision_number ASC
            """,
            {"exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[RevisionChainResult] = [
            dict(record)
            for record in (result.value or [])  # type: ignore[misc]
        ]
        return Result.ok(items)


# Entity types that can be shared while active (not just completed)
_ACTIVITY_ENTITY_TYPES = frozenset({"task", "goal", "habit", "event", "choice", "principle"})


class SharingBackend(UniversalNeo4jBackend[Entity]):
    """
    Domain backend for cross-domain sharing operations.

    All sharing queries target :Entity nodes by UID — there are no domain-specific
    predicates. Typed to Entity (the base class) since sharing spans all entity types.

    Moves sharing Cypher from the service layer into the persistence boundary,
    following the same pattern as LessonBackend (ORGANIZES), LpBackend (progress),
    and ExerciseBackend (curriculum linking).

    See: /docs/patterns/SHARING_PATTERNS.md
    """

    async def create_share(
        self,
        entity_uid: EntityUID,
        recipient_uid: str,
        role: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create SHARES_WITH relationship from recipient to entity."""
        result = await self.execute_query(
            """
            MATCH (recipient:User {uid: $recipient_uid})
            MATCH (ku:Entity {uid: $entity_uid})
            MERGE (recipient)-[r:SHARES_WITH]->(ku)
            SET r.shared_at = datetime($shared_at),
                r.role = $role,
                r.share_version = $share_version
            RETURN true as success
            """,
            {
                "recipient_uid": recipient_uid,
                "entity_uid": entity_uid,
                "shared_at": shared_at,
                "role": role,
                "share_version": share_version,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def delete_share(
        self,
        entity_uid: EntityUID,
        recipient_uid: str,
    ) -> Result[list[Neo4jProperties]]:
        """Delete SHARES_WITH relationship between recipient and entity."""
        result = await self.execute_query(
            """
            MATCH (recipient:User {uid: $recipient_uid})-[r:SHARES_WITH]->(ku:Entity {uid: $entity_uid})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"recipient_uid": recipient_uid, "entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def update_visibility(
        self,
        entity_uid: EntityUID,
        owner_uid: str,
        visibility: str,
    ) -> Result[list[Neo4jProperties]]:
        """Set visibility property on an owned entity."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            WHERE ku.user_uid = $owner_uid
            SET ku.visibility = $visibility,
                ku.updated_at = datetime()
            RETURN ku.uid as uid
            """,
            {
                "entity_uid": entity_uid,
                "owner_uid": owner_uid,
                "visibility": visibility,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_access(
        self,
        entity_uid: EntityUID,
        user_uid: UserUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query ownership, visibility, and share relationships for access check."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            OPTIONAL MATCH (viewer:User {uid: $user_uid})-[:SHARES_WITH]->(ku)
            OPTIONAL MATCH (viewer2:User {uid: $user_uid})-[:MEMBER_OF]->(g:Group)<-[:SHARED_WITH_GROUP]-(ku)
            RETURN ku.user_uid as owner_uid,
                   ku.visibility as visibility,
                   ku.entity_type as entity_type,
                   count(viewer) > 0 as has_direct_share,
                   count(viewer2) > 0 as has_group_share
            """,
            {"entity_uid": entity_uid, "user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shareable_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query status and entity_type for shareability check."""
        result = await self.execute_query(
            """
            MATCH (ku:Entity {uid: $entity_uid})
            RETURN ku.status as status, ku.entity_type as entity_type
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_ownership_and_status(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Query ownership and status for combined ownership + shareable check."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            RETURN entity.user_uid as actual_owner,
                   entity.status as status,
                   entity.entity_type as entity_type
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_users(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Get users an entity is shared with."""
        result = await self.execute_query(
            """
            MATCH (user:User)-[r:SHARES_WITH]->(ku:Entity {uid: $entity_uid})
            RETURN user.uid as user_uid,
                   user.name as user_name,
                   r.role as role,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY r.shared_at DESC
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_me(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Get entities shared with a user via direct SHARES_WITH."""
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[r:SHARES_WITH]->(ku:Entity)
            RETURN ku,
                   r.role as role,
                   r.shared_at as shared_at,
                   r.share_version as share_version
            ORDER BY r.shared_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def create_group_share(
        self,
        entity_uid: EntityUID,
        group_uid: str,
        share_version: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create SHARED_WITH_GROUP relationship from entity to group."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            MATCH (group:Group {uid: $group_uid})
            MERGE (entity)-[r:SHARED_WITH_GROUP]->(group)
            SET r.shared_at = datetime($shared_at),
                r.share_version = $share_version
            RETURN true as success
            """,
            {
                "entity_uid": entity_uid,
                "group_uid": group_uid,
                "shared_at": shared_at,
                "share_version": share_version,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def delete_group_share(
        self,
        entity_uid: EntityUID,
        group_uid: str,
    ) -> Result[list[Neo4jProperties]]:
        """Delete SHARED_WITH_GROUP relationship."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(group:Group {uid: $group_uid})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"entity_uid": entity_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_groups_shared_with(
        self,
        entity_uid: EntityUID,
    ) -> Result[list[Neo4jProperties]]:
        """Get groups an entity is shared with."""
        result = await self.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(group:Group)
            RETURN group.uid as group_uid,
                   group.name as group_name,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY r.shared_at DESC
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def query_shared_with_me_via_groups(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Get entities shared with a user through group membership."""
        result = await self.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:MEMBER_OF]->(group:Group)
            MATCH (entity:Entity)-[r:SHARED_WITH_GROUP]->(group)
            WHERE entity.user_uid <> $user_uid
            RETURN entity,
                   group.uid as group_uid,
                   group.name as group_name,
                   r.share_version as share_version,
                   r.shared_at as shared_at
            ORDER BY entity.created_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])


class FormTemplateBackend(UniversalNeo4jBackend["FormTemplate"]):
    """
    Domain backend for FormTemplate entities.

    Provides:
    - get_forms_for_lesson — Query FormTemplates linked to a lesson via EMBEDS_FORM
    - count_submissions    — Count submissions linked to a template via RESPONDS_TO_FORM
    """

    async def count_submissions(self, template_uid: str) -> Result[int]:
        """Count submissions linked to a template via RESPONDS_TO_FORM."""
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity)-[:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft:Entity {{uid: $uid}})
            RETURN count(fs) as count
            """,
            {"uid": template_uid},
        )
        if result.is_error or not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("count", 0))

    async def get_forms_for_lesson(self, lesson_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all FormTemplates embedded in a lesson."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $lesson_uid}})
                  -[:{RelationshipName.EMBEDS_FORM}]->
                  (ft:Entity {{entity_type: 'form_template'}})
            RETURN ft
            ORDER BY ft.title ASC
            """,
            {"lesson_uid": lesson_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["ft"]) for record in (result.value or [])])

    async def link_to_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]:
        """Create EMBEDS_FORM relationship from lesson to form template."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $lesson_uid}})
            WHERE a.entity_type IN ['lesson', 'ku']
            MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
            MERGE (a)-[r:{RelationshipName.EMBEDS_FORM}]->(ft)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"lesson_uid": lesson_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="Lesson or FormTemplate",
                    identifier=f"{lesson_uid} -> {form_template_uid}",
                )
            )
        return Result.ok(True)

    async def unlink_from_lesson(self, form_template_uid: str, lesson_uid: str) -> Result[bool]:
        """Remove EMBEDS_FORM relationship."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $lesson_uid}})
                  -[r:{RelationshipName.EMBEDS_FORM}]->
                  (ft:Entity {{uid: $ft_uid}})
            DELETE r
            RETURN true as success
            """,
            {"lesson_uid": lesson_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)


class FormSubmissionBackend(UniversalNeo4jBackend["FormSubmission"]):
    """
    Domain backend for FormSubmission entities.

    Provides:
    - get_submissions_for_template — Query all submissions for a template
    - list_by_user                 — Get user's form submissions
    - find_admin_user_uid          — Find the first admin user UID
    """

    async def find_admin_user_uid(self, admin_role: UserRole) -> Result[str | None]:
        """Find the first admin user UID by role value."""
        result = await self.execute_query(
            """
            MATCH (u:User) WHERE u.role = $admin_role
            RETURN u.uid as uid LIMIT 1
            """,
            {"admin_role": admin_role.value},
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["uid"])

    async def get_submissions_for_template(
        self, form_template_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get all submissions for a form template."""
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity {{entity_type: 'form_submission'}})
                  -[:{RelationshipName.RESPONDS_TO_FORM}]->
                  (ft:Entity {{uid: $ft_uid}})
            RETURN fs
            ORDER BY fs.created_at DESC
            """,
            {"ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["fs"]) for record in (result.value or [])])

    async def create_with_relationships(
        self,
        submission: FormSubmission,
        user_uid: UserUID,
        form_template_uid: str,
    ) -> Result[FormSubmission]:
        """Atomically create node + OWNS + RESPONDS_TO_FORM in one transaction."""
        from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node

        node_data = to_neo4j_node(submission)
        node_data.update(self.default_filters)

        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
        CREATE (fs:{self._create_labels})
        SET fs = $props
        CREATE (u)-[:{RelationshipName.OWNS.value}]->(fs)
        CREATE (fs)-[r:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft)
        SET r.created_at = datetime()
        RETURN fs
        """
        result = await self.execute_query(
            query,
            {"props": node_data, "user_uid": user_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.database("create_with_relationships", "User or template not found")
            )
        return Result.ok(from_neo4j_node(dict(records[0]["fs"]), self.entity_class))

    async def list_by_user(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[dict[str, Any]]]:
        """Get a user's form submissions."""
        result = await self.execute_query(
            """
            MATCH (fs:Entity {entity_type: 'form_submission', user_uid: $user_uid})
            RETURN fs
            ORDER BY fs.created_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["fs"]) for record in (result.value or [])])


class JournalInputBackend(UniversalNeo4jBackend["JeInput"]):
    """
    Domain backend for JeInput entities (journal entry inputs).

    Standalone journal backend — NOT part of SubmissionsBackend.
    Uses NeoLabel.JE_INPUT with base_label=NeoLabel.ENTITY.
    """

    async def count_je_inputs_for_date(self, user_uid: UserUID, entry_date: str) -> Result[int]:
        """Count journal entries for a user on a specific date."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.metadata IS NOT NULL
          AND ji.metadata CONTAINS $date_str
        RETURN count(ji) AS count
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "date_str": entry_date})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(record.get("count", 0))

    async def get_ephemeral_je_inputs(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get journal entries with FIFO cleanup enabled (max_retention is not null)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.max_retention IS NOT NULL
        RETURN ji
        ORDER BY ji.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ji"] for record in (result.value or [])])

    async def get_je_inputs_by_date_range(
        self, user_uid: UserUID, start_date: str, end_date: str
    ) -> Result[list[Neo4jProperties]]:
        """Get journal entries for a user within a date range (by created_at)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.created_at >= $start_date AND ji.created_at <= $end_date
        RETURN ji
        ORDER BY ji.created_at DESC
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "start_date": start_date, "end_date": end_date},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ji"] for record in (result.value or [])])


class JournalOutputBackend(UniversalNeo4jBackend["JeOutput"]):
    """
    Domain backend for JeOutput entities (journal entry outputs).

    Standalone journal backend — NOT part of ExerciseReport infrastructure.
    Uses NeoLabel.JE_OUTPUT with base_label=NeoLabel.ENTITY.
    """

    async def get_je_output_for_input(self, je_input_uid: str) -> Result[Neo4jProperties | None]:
        """Get the je_output that transforms a specific je_input."""
        query = """
        MATCH (jo:JeOutput)-[:TRANSFORMS]->(ji:JeInput {uid: $je_input_uid})
        RETURN jo
        LIMIT 1
        """
        result = await self.execute_query(query, {"je_input_uid": je_input_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["jo"])

    async def create_with_transforms(
        self,
        properties: Neo4jProperties,
        user_uid: UserUID,
        je_input_uid: str,
    ) -> Result[Neo4jProperties]:
        """Atomically create JeOutput node with OWNS + TRANSFORMS relationships.

        Single Cypher transaction: MATCH User + JeInput, CREATE JeOutput:Entity,
        CREATE (User)-[:OWNS]->(JeOutput)-[:TRANSFORMS]->(JeInput).
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (ji:JeInput {{uid: $je_input_uid}})
        CREATE (jo:{self._create_labels})
        SET jo = $props
        CREATE (u)-[:{RelationshipName.OWNS.value}]->(jo)
        CREATE (jo)-[:{RelationshipName.TRANSFORMS.value}]->(ji)
        RETURN jo
        """
        result = await self.execute_query(
            query,
            {"props": properties, "user_uid": user_uid, "je_input_uid": je_input_uid},
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.database("create_with_transforms", "User or JeInput not found")
            )
        return Result.ok(result.value[0]["jo"])


class GroupBackend(UniversalNeo4jBackend["Group"]):
    """
    Domain backend for Group entities.

    Provides:
    - create_owns_relationship — OWNS relationship from teacher to group
    - get_user_groups          — Groups a user is a member of
    - add_member               — Create MEMBER_OF relationship
    - remove_member            — Delete MEMBER_OF relationship
    - get_members              — Query members with metadata
    - get_member_count         — Count members in a group
    """

    async def create_owns_relationship(self, teacher_uid: str, group_uid: str) -> Result[bool]:
        """Create OWNS relationship from teacher to group."""
        result = await self.execute_query(
            """
            MATCH (teacher:User {uid: $teacher_uid})
            MATCH (group:Group {uid: $group_uid})
            MERGE (teacher)-[:OWNS]->(group)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def get_user_groups(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all groups a user is a member of (via MEMBER_OF relationship)."""
        result = await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            WHERE group.is_active = true
            RETURN group
            ORDER BY group.created_at DESC
            """,
            {"user_uid": user_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["group"]) for record in (result.value or [])])

    async def add_member(
        self,
        group_uid: str,
        user_uid: UserUID,
        joined_at: str,
        role: str = "student",
    ) -> Result[list[Neo4jProperties]]:
        """Create MEMBER_OF relationship from user to group."""
        result = await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})
            MATCH (group:Group {{uid: $group_uid}})
            MERGE (user)-[r:{RelationshipName.MEMBER_OF}]->(group)
            SET r.joined_at = datetime($joined_at),
                r.role = $role
            RETURN true as success
            """,
            {
                "user_uid": user_uid,
                "group_uid": group_uid,
                "joined_at": joined_at,
                "role": role,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def remove_member(
        self, group_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Delete MEMBER_OF relationship between user and group."""
        result = await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"user_uid": user_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_members(self, group_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all members of a group with metadata."""
        result = await self.execute_query(
            f"""
            MATCH (user:User)-[r:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            RETURN user.uid as user_uid,
                   user.name as user_name,
                   r.role as role,
                   r.joined_at as joined_at
            ORDER BY r.joined_at
            """,
            {"group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_member_count(self, group_uid: str) -> Result[int]:
        """Get current member count for a group."""
        result = await self.execute_query(
            f"""
            MATCH (user:User)-[:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            RETURN count(user) as member_count
            """,
            {"group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        count = records[0]["member_count"] if records else 0
        return Result.ok(count)

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_teacher_groups_with_stats(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        OPTIONAL MATCH (member:User)-[:{RelationshipName.MEMBER_OF.value}]->(g)
        OPTIONAL MATCH (ex:Entity:Exercise)-[:{RelationshipName.FOR_GROUP.value}]->(g)
        OPTIONAL MATCH (sub:Entity:Submission)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex)
          WHERE sub.status NOT IN ['completed', 'archived']
        RETURN g.uid AS uid,
               g.name AS name,
               g.description AS description,
               g.is_active AS is_active,
               count(DISTINCT member) AS member_count,
               count(DISTINCT ex) AS exercise_count,
               count(DISTINCT sub) AS pending_count
        ORDER BY g.created_at DESC
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get members of a teacher's group with their submission progress."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group {{uid: $group_uid}})
        MATCH (member:User)-[r:{RelationshipName.MEMBER_OF.value}]->(g)
        OPTIONAL MATCH (teacher)-[:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(sub:Entity:Submission)
          WHERE (member)-[:{RelationshipName.OWNS.value}]->(sub)
        RETURN member.uid AS user_uid,
               member.name AS user_name,
               r.role AS role,
               r.joined_at AS joined_at,
               count(sub) AS submission_count,
               count(CASE WHEN sub.status = 'completed' THEN 1 END) AS reviewed_count,
               count(CASE WHEN sub.status IN ['submitted', 'active', 'revision_requested'] THEN 1 END) AS pending_count
        ORDER BY r.joined_at
        """
        return await self.execute_query(query, {"group_uid": group_uid, "teacher_uid": teacher_uid})


class ActivityReportBackend(UniversalNeo4jBackend[ActivityReport]):
    """
    Domain backend for ActivityReport entities.

    Moves inline Cypher from ActivityReportService into named backend methods.
    Methods: get_history, annotate, get_annotation, get_admin_snapshots,
    get_shares_granted, get_report_schedule.
    """

    async def get_history(self, subject_uid: str, limit: int = 20) -> Result[list[Neo4jProperties]]:
        """Get ActivityReport entities where subject_uid matches the user."""
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: 'activity_report', subject_uid: $subject_uid})
            RETURN n
            ORDER BY n.created_at DESC
            LIMIT $limit
            """,
            {"subject_uid": subject_uid, "limit": limit},
        )

    async def annotate(
        self,
        uid: str,
        user_uid: UserUID,
        annotation_mode: str,
        now: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Save annotation or revision to an owned ActivityReport."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: 'activity_report'})
            SET n.annotation_mode = $annotation_mode,
                n.annotation_updated_at = datetime($now),
                n.user_annotation = $user_annotation,
                n.user_revision = $user_revision
            RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                   n.user_annotation AS user_annotation, n.user_revision AS user_revision
            """,
            {
                "uid": uid,
                "user_uid": user_uid,
                "annotation_mode": annotation_mode,
                "now": now,
                "user_annotation": user_annotation,
                "user_revision": user_revision,
            },
        )

    async def get_annotation(self, uid: str, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get current annotation state for an owned ActivityReport."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: 'activity_report'})
            RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                   n.user_annotation AS user_annotation, n.user_revision AS user_revision,
                   n.annotation_updated_at AS annotation_updated_at
            """,
            {"uid": uid, "user_uid": user_uid},
        )

    async def get_admin_snapshots(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """Get admin-written ActivityReports received by this user (privacy audit)."""
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: 'activity_report', subject_uid: $user_uid})
            WHERE n.processor_type = 'human'
            RETURN n.created_at AS accessed_at,
                   n.user_uid AS admin_uid,
                   n.time_period AS time_period
            ORDER BY n.created_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )

    async def get_shares_granted(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get users with active SHARES_WITH access to this user's entities."""
        return await self.execute_query(
            f"""
            MATCH (accessor:User)-[sw:{RelationshipName.SHARES_WITH.value}]->(e:Entity {{user_uid: $user_uid}})
            RETURN accessor.uid AS accessor_uid,
                   e.uid AS entity_uid,
                   e.title AS entity_title,
                   sw.role AS role,
                   sw.shared_at AS shared_at
            ORDER BY sw.shared_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )

    async def get_report_schedule(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get active report schedule for user (privacy audit)."""
        return await self.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:HAS_SCHEDULE]->(s:ReportSchedule)
            WHERE s.is_active = true
            RETURN s.schedule_type AS schedule_type,
                   s.day_of_week AS day_of_week,
                   s.next_due_at AS next_due_at,
                   s.last_generated_at AS last_generated_at
            LIMIT 1
            """,
            {"user_uid": user_uid},
        )


class LateralRelationshipBackend:
    """
    Backend for lateral relationship Cypher queries.

    Lateral relationships are cross-entity-type graph operations (BLOCKS, PREREQUISITE_FOR,
    ALTERNATIVE_TO, COMPLEMENTARY_TO, SIBLING, RELATED_TO). This backend encapsulates all
    Cypher queries, keeping LateralRelationshipService free of inline queries.

    Similar to NotificationBackend — uses raw Cypher via executor rather than
    UniversalNeo4jBackend, since it manages relationships between arbitrary entity
    types rather than CRUD on a single entity type.

    See: /docs/architecture/RELATIONSHIPS_ARCHITECTURE.md
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    # ========================================================================
    # CRUD Methods (4)
    # ========================================================================

    async def create_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
        metadata: dict[str, Any],
    ) -> Result[list[Neo4jProperties]]:
        """Create a lateral relationship between two entities (idempotent)."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})
            MATCH (target {{uid: $target_uid}})
            MERGE (source)-[r:{relationship_type}]->(target)
            SET r += $metadata
            RETURN r
            """,
            {
                "source_uid": source_uid,
                "target_uid": target_uid,
                "metadata": metadata,
            },
        )

    async def delete_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
    ) -> Result[list[Neo4jProperties]]:
        """Delete a lateral relationship. Returns deleted_count."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})-[r:{relationship_type}]->(target {{uid: $target_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def create_inverse(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
        metadata: dict[str, Any],
    ) -> Result[list[Neo4jProperties]]:
        """Create inverse relationship for asymmetric types (idempotent)."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})
            MATCH (target {{uid: $target_uid}})
            MERGE (source)-[r:{relationship_type}]->(target)
            SET r += $metadata
            """,
            {
                "source_uid": source_uid,
                "target_uid": target_uid,
                "metadata": metadata,
            },
        )

    async def delete_inverse(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
    ) -> Result[list[Neo4jProperties]]:
        """Delete inverse relationship for asymmetric types."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})-[r:{relationship_type}]->(target {{uid: $target_uid}})
            DELETE r
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    # ========================================================================
    # Query Methods (6)
    # ========================================================================

    async def get_relationships(
        self,
        entity_uid: EntityUID,
        type_filter: str,
        pattern: str,
    ) -> Result[list[Neo4jProperties]]:
        """Get lateral relationships for an entity.

        Args:
            entity_uid: Entity UID
            type_filter: Pipe-separated relationship types (e.g. "BLOCKS|PREREQUISITE_FOR")
            pattern: Direction pattern — one of "outgoing", "incoming", "both"
        """
        if pattern == "outgoing":
            match_pattern = f"(entity)-[r:{type_filter}]->(related)"
        elif pattern == "incoming":
            match_pattern = f"(entity)<-[r:{type_filter}]-(related)"
        else:
            match_pattern = f"(entity)-[r:{type_filter}]-(related)"

        return await self.executor.execute_query(
            f"""
            MATCH {match_pattern}
            WHERE entity.uid = $entity_uid
            RETURN
                type(r) as relationship_type,
                related.uid as related_uid,
                related.title as related_title,
                properties(r) as metadata,
                CASE
                    WHEN startNode(r) = entity THEN 'outgoing'
                    ELSE 'incoming'
                END as direction
            ORDER BY relationship_type, related_title
            """,
            {"entity_uid": entity_uid},
        )

    async def get_siblings(self, entity_uid: EntityUID) -> Result[list[Neo4jProperties]]:
        """Get sibling entities derived from hierarchy (same parent)."""
        return await self.executor.execute_query(
            """
            MATCH (parent)-[r]->(sibling)
            WHERE (parent)-[]->(entity {uid: $entity_uid})
            AND sibling.uid != $entity_uid
            AND type(r) IN ['SUBGOAL', 'SUBHABIT', 'SUBEVENT', 'SUBPRINCIPLE',
                             'SUBCHOICE', 'CONTAINS_STEP', 'ORGANIZES']
            RETURN
                sibling.uid as sibling_uid,
                sibling.title as sibling_title,
                type(r) as hierarchy_type,
                r.order as order
            ORDER BY r.order, sibling.title
            """,
            {"entity_uid": entity_uid},
        )

    async def get_cousins(self, entity_uid: EntityUID) -> Result[list[Neo4jProperties]]:
        """Get first-cousin entities (same grandparent, different parent)."""
        return await self.executor.execute_query(
            """
            MATCH (grandparent)-[]->(parent1)-[]->(entity {uid: $entity_uid})
            MATCH (grandparent)-[]->(parent2)-[]->(cousin)
            WHERE parent1 != parent2
            AND cousin.uid != $entity_uid
            AND NOT (parent1)-[]->(cousin) // Not a sibling
            RETURN
                cousin.uid as cousin_uid,
                cousin.title as cousin_title,
                grandparent.uid as shared_ancestor_uid,
                grandparent.title as shared_ancestor_title
            ORDER BY cousin.title
            """,
            {"entity_uid": entity_uid},
        )

    async def get_blocking_chain(self, entity_uid: EntityUID) -> Result[list[Neo4jProperties]]:
        """Get transitive blocking chain with depth levels."""
        return await self.executor.execute_query(
            """
            MATCH path = (blocker)-[:BLOCKS*1..10]->(entity {uid: $uid})
            WITH blocker, path, length(path) as depth
            RETURN
                blocker.uid as uid,
                blocker.title as title,
                blocker.status as status,
                labels(blocker)[0] as entity_type,
                depth,
                size((blocker)-[:BLOCKS]->()) as blocks_count
            ORDER BY depth DESC
            """,
            {"uid": entity_uid},
        )

    async def get_alternatives_comparison(
        self, entity_uid: EntityUID
    ) -> Result[list[Neo4jProperties]]:
        """Get alternative entities with side-by-side comparison data."""
        return await self.executor.execute_query(
            """
            MATCH (entity {uid: $uid})-[r:ALTERNATIVE_TO]-(alternative)
            RETURN
                alternative.uid as uid,
                alternative.title as title,
                alternative.description as description,
                alternative.status as status,
                alternative.priority as priority,
                labels(alternative)[0] as entity_type,
                r.comparison_criteria as comparison_criteria,
                r.tradeoffs as tradeoffs,
                r.timeframe as timeframe,
                r.difficulty as difficulty,
                r.resources as resources,
                properties(alternative) as all_properties,
                properties(r) as rel_properties
            """,
            {"uid": entity_uid},
        )

    async def get_relationship_graph(
        self,
        entity_uid: EntityUID,
        type_filter: str,
        depth: int,
    ) -> Result[list[Neo4jProperties]]:
        """Get relationship graph in Vis.js Network format."""
        return await self.executor.execute_query(
            f"""
            MATCH path = (center {{uid: $uid}})-[r:{type_filter}*1..{depth}]-(related)
            WITH center, r, related, length(path) as depth_level
            RETURN DISTINCT
                center.uid as center_uid,
                center.title as center_title,
                labels(center)[0] as center_type,
                center.status as center_status,
                related.uid as related_uid,
                related.title as related_title,
                labels(related)[0] as related_type,
                related.status as related_status,
                [rel in r | {{
                    type: type(rel),
                    from: startNode(rel).uid,
                    to: endNode(rel).uid
                }}] as relationships,
                depth_level
            """,
            {"uid": entity_uid},
        )

    # ========================================================================
    # Validation Methods (4)
    # ========================================================================

    async def check_entities_exist(
        self, source_uid: str, target_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify both entities exist in the graph."""
        return await self.executor.execute_query(
            """
            MATCH (source {uid: $source_uid})
            MATCH (target {uid: $target_uid})
            RETURN count(source) as source_count, count(target) as target_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def check_same_parent(
        self, source_uid: str, target_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify entities share the same parent."""
        return await self.executor.execute_query(
            """
            MATCH (parent)-[]->(source {uid: $source_uid})
            MATCH (parent)-[]->(target {uid: $target_uid})
            RETURN count(parent) as shared_parent_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def check_same_depth(
        self, source_uid: str, target_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify entities are at the same hierarchical depth."""
        return await self.executor.execute_query(
            """
            MATCH path1 = (root)-[*]->(source {uid: $source_uid})
            WHERE NOT ()-[]->(root)
            WITH length(path1) as source_depth
            MATCH path2 = (root2)-[*]->(target {uid: $target_uid})
            WHERE NOT ()-[]->(root2)
            WITH source_depth, length(path2) as target_depth
            RETURN source_depth, target_depth
            LIMIT 1
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def check_no_cycles(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
    ) -> Result[list[Neo4jProperties]]:
        """Check that creating this relationship won't create a circular dependency."""
        return await self.executor.execute_query(
            f"""
            MATCH (target {{uid: $target_uid}})-[:{relationship_type}*1..10]->(source {{uid: $source_uid}})
            RETURN count(*) as cycle_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )


class NotificationBackend:
    """
    Backend for Notification nodes in Neo4j.

    Notifications are infrastructure, not domain entities — they use raw Cypher
    without BaseService/UniversalNeo4jBackend. This backend encapsulates all
    notification Cypher queries, keeping NotificationService free of inline queries.

    Graph pattern: (User)-[:HAS_NOTIFICATION]->(Notification)
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    async def create_notification(
        self,
        params: dict[str, Any],
    ) -> Result[list[Neo4jProperties]]:
        """Create a notification node and link to user via HAS_NOTIFICATION."""
        query = """
        MATCH (u:User {uid: $user_uid})
        CREATE (n:Notification {
            uid: $uid,
            user_uid: $user_uid,
            notification_type: $notification_type,
            title: $title,
            message: $message,
            source_uid: $source_uid,
            source_type: $source_type,
            read: false,
            created_at: datetime($now)
        })
        CREATE (u)-[:HAS_NOTIFICATION]->(n)
        RETURN n.uid as uid
        """
        return await self.executor.execute_query(query, params)

    async def get_unread_count(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get count of unread notifications for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        RETURN count(n) as count
        """
        return await self.executor.execute_query(query, {"user_uid": user_uid})

    async def get_notifications(
        self, user_uid: UserUID, limit: int, include_read: bool = True
    ) -> Result[list[Neo4jProperties]]:
        """Get notifications for a user, unread first."""
        read_filter = "" if include_read else "AND n.read = false"
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_NOTIFICATION]->(n:Notification)
        WHERE n.user_uid = $user_uid {read_filter}
        RETURN n.uid as uid,
               n.notification_type as notification_type,
               n.title as title,
               n.message as message,
               n.source_uid as source_uid,
               n.source_type as source_type,
               n.read as read,
               n.created_at as created_at
        ORDER BY n.read ASC, n.created_at DESC
        LIMIT $limit
        """
        return await self.executor.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def mark_read(
        self, notification_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Mark a single notification as read."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {uid: $notification_uid})
        SET n.read = true
        RETURN n.uid as uid
        """
        return await self.executor.execute_query(
            query, {"user_uid": user_uid, "notification_uid": notification_uid}
        )

    async def mark_all_read(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Mark all notifications as read for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        SET n.read = true
        RETURN count(n) as count
        """
        return await self.executor.execute_query(query, {"user_uid": user_uid})


__all__ = [
    "ActivityReportBackend",
    "ChoicesBackend",
    "EventsBackend",
    "ExerciseBackend",
    "FormSubmissionBackend",
    "FormTemplateBackend",
    "GoalsBackend",
    "GroupBackend",
    "HabitsBackend",
    "JournalInputBackend",
    "JournalOutputBackend",
    "KuBackend",
    "LateralRelationshipBackend",
    "LessonBackend",
    "LpBackend",
    "LsBackend",
    "NotificationBackend",
    "PrinciplesBackend",
    "RevisedExerciseBackend",
    "SharingBackend",
    "SubmissionsBackend",
    "TasksBackend",
]
