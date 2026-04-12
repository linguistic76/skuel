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

from typing import TYPE_CHECKING, Any, cast

from adapters.persistence.neo4j._adaptive_mixin import _AdaptiveMixin
from adapters.persistence.neo4j._hierarchy_mixin import HierarchyConfig, _HierarchyMixin
from adapters.persistence.neo4j._knowledge_context_mixin import _KnowledgeContextMixin
from adapters.persistence.neo4j._learning_state_mixin import _LearningStateMixin
from adapters.persistence.neo4j._lp_intelligence_mixin import _LpIntelligenceMixin
from adapters.persistence.neo4j._lp_progress_mixin import _LpProgressMixin
from adapters.persistence.neo4j._lp_step_mixin import _LpStepMixin
from adapters.persistence.neo4j._organizes_mixin import _OrganizesMixin
from adapters.persistence.neo4j._semantic_mixin import _SemanticMixin
from adapters.persistence.neo4j._submission_assessment_mixin import (
    _SubmissionAssessmentMixin,
)
from adapters.persistence.neo4j._submission_content_mixin import _SubmissionContentMixin
from adapters.persistence.neo4j._submission_crud_mixin import _SubmissionCrudMixin
from adapters.persistence.neo4j._submission_lifecycle_mixin import (
    _SubmissionLifecycleMixin,
)
from adapters.persistence.neo4j._submission_report_query_mixin import (
    _SubmissionReportQueryMixin,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.entity import Entity
from core.models.enums import UserRole
from core.models.event.event import Event
from core.models.exercises.exercise import Exercise
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.ku.ku import Ku
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.relationship_names import RelationshipName
from core.models.report.activity_report import ActivityReport
from core.models.report.exercise_report import ExerciseReport
from core.models.submissions.submission import Submission
from core.models.task.task import Task
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.ports.query_types import (
    ChoiceStats,
    CurriculumExerciseResult,
    EventStats,
    GoalStats,
    HabitStats,
    ParentProgressResult,
    PrincipleStats,
    PsDeleteStepRow,
    PsKnowledgeItemResult,
    PsKnowledgeSummaryResult,
    PsStandaloneStepRow,
    PsStepWithContextRow,
    PsStepWithKnowledgeRow,
    RequiredKnowledgeResult,
    RevisionChainResult,
    TaskStats,
)
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from datetime import date

    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.journal.je_input import JeInput  # noqa: F401
    from core.models.journal.je_output import JeOutput  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401
    from core.models.submissions.report_schedule import ReportSchedule  # noqa: F401


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


class SubmissionsBackend(  # type: ignore[misc]  # Mixin MRO overrides are intentional
    _SubmissionCrudMixin,
    _SubmissionLifecycleMixin,
    _SubmissionAssessmentMixin,
    _SubmissionReportQueryMixin,
    _SubmissionContentMixin,
    UniversalNeo4jBackend[Submission],
):
    """
    Domain backend for Submission entities.

    Uses NeoLabel.ENTITY (not NeoLabel.SUBMISSION) because submissions span
    2 EntityTypes: SUBMISSION and EXERCISE_REPORT (via SubmissionsBackend).

    All behavior lives in the 5 mixins above:
        * _SubmissionCrudMixin       — content search, feedback counts, teacher EMA state
        * _SubmissionLifecycleMixin  — exercise-processing + FULFILLS/temporal/thematic rels
        * _SubmissionAssessmentMixin — assessment scoring + teacher-review workflow
        * _SubmissionReportQueryMixin — learning-loop chain + report cross-joins
        * _SubmissionContentMixin    — journal processing context + exercise-instruction reads

    Sharing and access control live in SharingBackend + UnifiedSharingService,
    operating across all entity types.
    """
class KuBackend(UniversalNeo4jBackend[Ku]):
    """Domain backend for atomic Knowledge Unit entities.

    Lightweight reference nodes with reverse-traversal methods:
    - get_path_steps_using(ku_uid) — PathSteps that USES_KU this Ku
    """

    async def get_path_steps_using(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all PathSteps that use this atomic Ku via USES_KU."""
        query = """
        MATCH (ps:Entity)-[:USES_KU]->(ku:Entity {uid: $ku_uid})
        RETURN ps.uid AS uid, ps.title AS title,
               ps.description AS description
        ORDER BY ps.title
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_usage_summary(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count path steps using (USES_KU), training (TRAINS_KU), and organized children."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (uses:Entity)-[:USES_KU]->(ku)
        OPTIONAL MATCH (trains:Entity)-[:TRAINS_KU]->(ku)
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
        RETURN count(DISTINCT uses) as path_steps_using,
               count(DISTINCT trains) as path_steps_training,
               count(DISTINCT child) as organized_children
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_trained(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if any PathStep trains this Ku via TRAINS_KU."""
        query = """
        MATCH (ps:Entity)-[:TRAINS_KU]->(ku:Entity:Ku {uid: $ku_uid})
        RETURN count(ps) > 0 as trained
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
    # SUBSTANCE METRICS
    # ========================================================================

    async def batch_increment_substance(
        self,
        ku_uids: list[str],
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for multiple KUs and connected PathSteps."""
        query = f"""
        UNWIND $ku_uids AS ku_uid
        MATCH (ku:Entity {{uid: ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        WITH ku
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
        WITH ps WHERE ps IS NOT NULL
        SET ps.{metric} = COALESCE(ps.{metric}, 0) + 1,
            ps.{timestamp_field} = datetime($timestamp),
            ps._substance_cache_timestamp = NULL
        RETURN count(ps) as updated_count
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
        """Atomically increment a substance metric for a single KU and connected PathSteps."""
        query = f"""
        MATCH (ku:Entity {{uid: $ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        WITH ku
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
        WITH ku, ps WHERE ps IS NOT NULL
        SET ps.{metric} = COALESCE(ps.{metric}, 0) + 1,
            ps.{timestamp_field} = datetime($timestamp),
            ps._substance_cache_timestamp = NULL
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

    async def count_studying_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Count Kus the user has marked as studying (IN_PROGRESS or MARKED_AS_READ)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS|MARKED_AS_READ]->(ku:Entity:Ku)
        RETURN count(ku) AS cnt
        """
        return await self.execute_query(query, {"user_uid": user_uid})

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


class PsBackend(
    _OrganizesMixin,
    _LearningStateMixin,
    _SemanticMixin,
    _KnowledgeContextMixin,
    _AdaptiveMixin,
    UniversalNeo4jBackend[PathStep],
):
    """Domain backend for PathStep entities.

    Extends UniversalNeo4jBackend[PathStep] with:
    - Knowledge relationship CRUD (CONTAINS_KNOWLEDGE / USES_KU edges)
    - KU completion progress tracking
    - ``_OrganizesMixin`` — ORGANIZES relationship management (12 methods)
    - ``_LearningStateMixin`` — user progress tracking: VIEWED, IN_PROGRESS,
      MASTERED, BOOKMARKED, MARKED_AS_READ (13 methods)
    - ``_SemanticMixin`` — semantic relationships + graph analysis (11 methods)
    - ``_KnowledgeContextMixin`` — context, discovery, readiness (13 methods)
    - ``_AdaptiveMixin`` — practice, search, adaptive mastery tracking (10 methods)
    """

    # ========================================================================
    # STEP SEQUENCE (for attach_step_to_path)
    # ========================================================================

    async def get_next_step_sequence(self, path_uid: str) -> Result[int]:
        """Get the next available sequence number for a path's steps."""
        query = """
        MATCH (p:Entity {uid: $path_uid})-[r:HAS_STEP]->()
        RETURN coalesce(max(r.sequence), -1) + 1 as next_sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("next_sequence", 0))

    # ========================================================================
    # KNOWLEDGE RELATIONSHIP CRUD (CONTAINS_KNOWLEDGE edges)
    # ========================================================================

    async def add_knowledge(self, ps_uid: str, ku_uid: str) -> Result[bool]:
        """MERGE CONTAINS_KNOWLEDGE relationship between PS and KU."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (ps)-[r:CONTAINS_KNOWLEDGE]->(ku)
        SET r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        success = len(result.value or []) > 0
        if success:
            self.logger.info(f"Created CONTAINS_KNOWLEDGE: {ps_uid} -> {ku_uid}")
        return Result.ok(success)

    async def remove_knowledge(self, ps_uid: str, ku_uid: str) -> Result[bool]:
        """DELETE CONTAINS_KNOWLEDGE relationship between PS and KU."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        DELETE r
        RETURN count(r) as deleted
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        deleted = records[0]["deleted"] if records else 0
        success = deleted > 0
        if success:
            self.logger.info(f"Removed CONTAINS_KNOWLEDGE: {ps_uid} -> {ku_uid}")
        return Result.ok(success)

    async def list_knowledge(self, ps_uid: str) -> Result[list[PsKnowledgeItemResult]]:
        """List CONTAINS_KNOWLEDGE relationships."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN ku.uid as uid, ku.title as title, ku.domain as domain,
               r.created_at as created_at
        ORDER BY r.created_at, ku.title
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
        if result.is_error:
            return Result.fail(result)
        items: list[PsKnowledgeItemResult] = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "domain": r["domain"],
                "created_at": r["created_at"],
            }
            for r in result.value or []
        ]
        return Result.ok(items)

    async def get_knowledge_summary(self, ps_uid: str) -> Result[PsKnowledgeSummaryResult]:
        """Aggregate count and UIDs of knowledge in this step."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})
        OPTIONAL MATCH (ps)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN count(r) as count, collect(ku.uid) as uids
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
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
    # KU COMPLETION PROGRESS TRACKING
    # ========================================================================

    async def get_ku_completion_progress(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """Return total and mastered KU counts for PathStep progress calculation.

        Progress = mastered_kus / total_kus (via USES_KU + CONTAINS_KNOWLEDGE).

        Args:
            ps_uid: PathStep UID
            user_uid: User UID

        Returns:
            Result containing dict with total_kus and mastered_kus
        """
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity)
        WITH collect(DISTINCT ku) as all_kus, count(DISTINCT ku) as total
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
        WHERE mastered IN all_kus
        RETURN total as total_kus, count(DISTINCT mastered) as mastered_kus
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({"total_kus": 0, "mastered_kus": 0})
        record = result.value[0]
        return Result.ok(
            {
                "total_kus": record["total_kus"],
                "mastered_kus": record["mastered_kus"],
            }
        )

    # ========================================================================
    # KU → PATHSTEP LOOKUP (for progress tracking)
    # ========================================================================

    async def find_path_steps_for_ku(self, ku_uid: str) -> Result[list[str]]:
        """Find all PathStep UIDs that contain a given KU via USES_KU or CONTAINS_KNOWLEDGE."""
        query = """
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN ps.uid as ps_uid
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ps_uid"] for record in (result.value or [])])

    # ========================================================================
    # CORE CRUD QUERIES (migrated from PsCoreService)
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
            entity_type: 'path_step',
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

    async def get_step_with_knowledge(self, uid: str) -> Result[list[PsStepWithKnowledgeRow]]:
        """Get step node with CONTAINS_KNOWLEDGE relationships."""
        query = """
        MATCH (s:Entity {uid: $uid})
        OPTIONAL MATCH (s)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        return cast(
            "Result[list[PsStepWithKnowledgeRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

    async def get_step_with_context(self, uid: str) -> Result[list[PsStepWithContextRow]]:
        """Get step with comprehensive 11-part graph context in a single query."""
        query = """
        MATCH (ps:Entity {uid: $uid})

        // 1. Knowledge references
        OPTIONAL MATCH (ps)-[r_ku:CONTAINS_KNOWLEDGE]->(ku:Entity)
        WITH ps, collect({
            uid: ku.uid,
            title: ku.title,
            confidence: coalesce(r_ku.confidence, 1.0)
        }) as knowledge_rels

        // 2. Prerequisite steps
        OPTIONAL MATCH (ps)-[:REQUIRES_STEP]->(prereq_step:Entity {entity_type: 'path_step'})
        WITH ps, knowledge_rels, collect({
            uid: prereq_step.uid,
            title: prereq_step.title,
            completed: prereq_step.completed
        }) as prereq_steps

        // 3. Prerequisite knowledge
        OPTIONAL MATCH (ps)-[:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(prereq_ku:Entity)
        WITH ps, knowledge_rels, prereq_steps, collect({
            uid: prereq_ku.uid,
            title: prereq_ku.title
        }) as prereq_knowledge

        // 4. Guiding principles (direct on PathStep)
        OPTIONAL MATCH (ps)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, collect(DISTINCT {
            uid: principle.uid,
            title: principle.title
        }) as principles

        // 5. Informed choices (direct on PathStep)
        OPTIONAL MATCH (ps)-[:INFORMS_CHOICE]->(choice:Choice)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, collect(DISTINCT {
            uid: choice.uid,
            title: choice.title
        }) as choices

        // 6. Practice opportunities: Habits (direct on PathStep)
        OPTIONAL MATCH (ps)-[:BUILDS_HABIT]->(habit:Habit)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, collect(DISTINCT {
            uid: habit.uid,
            title: habit.title,
            current_streak: habit.current_streak
        }) as habits

        // 7. Practice opportunities: Tasks (direct on PathStep)
        OPTIONAL MATCH (ps)-[:ASSIGNS_TASK]->(task:Task)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, collect(DISTINCT {
            uid: task.uid,
            title: task.title,
            status: task.status
        }) as tasks

        // 8. Practice opportunities: Events (direct on PathStep)
        OPTIONAL MATCH (ps)-[:SCHEDULES_EVENT]->(event:Event)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, collect(DISTINCT {
            uid: event.uid,
            title: event.title,
            event_date: event.event_date
        }) as events

        // 9. Practice opportunities: Goals (direct on PathStep)
        OPTIONAL MATCH (ps)-[:SUPPORTS_GOAL]->(goal:Goal)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, collect(DISTINCT {
            uid: goal.uid,
            title: goal.title,
            status: goal.status
        }) as goals

        // 10. Learning path context (if part of sequence)
        OPTIONAL MATCH (lp:Entity {entity_type: 'learning_path'})-[r_path:HAS_STEP|CONTAINS_STEP]->(ps)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, goals, {
            uid: lp.uid,
            name: lp.title,
            goal: lp.goal,
            sequence: coalesce(r_path.sequence, 0)
        } as path_context

        // 11. Dependent steps (steps that require this one)
        OPTIONAL MATCH (dependent:Entity {entity_type: 'path_step'})-[:REQUIRES_STEP]->(ps)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, goals, path_context, collect({
            uid: dependent.uid,
            title: dependent.title,
            completed: dependent.completed
        }) as dependent_steps

        RETURN ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices,
               habits, tasks, events, goals, path_context, dependent_steps
        """
        return cast(
            "Result[list[PsStepWithContextRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

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

    async def delete_step_node(self, uid: str) -> Result[list[PsDeleteStepRow]]:
        """DETACH DELETE a step node and return deletion count."""
        query = """
        MATCH (s:Entity {uid: $uid})
        DETACH DELETE s
        RETURN count(s) as deleted_count
        """
        return cast(
            "Result[list[PsDeleteStepRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

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
            MATCH (p:Entity {{uid: $path_uid}})-[:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
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
            MATCH (s:Entity {{entity_type: 'path_step'}})
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

    # ========================================================================
    # SEARCH QUERIES (migrated from PsSearchService)
    # ========================================================================

    async def get_steps_for_learning_path(
        self, path_uid: str, limit: int = 100
    ) -> Result[list[dict[str, Any]]]:
        """Get PathStep nodes belonging to a learning path, ordered by sequence.

        Args:
            path_uid: Learning path UID
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (lp:Entity {uid: $path_uid})-[:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})
        RETURN ps
        ORDER BY ps.sequence ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"path_uid": path_uid, "limit": limit})

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[PsStandaloneStepRow]]:
        """Get PathStep nodes not belonging to any learning path.

        Args:
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (ps:Entity {entity_type: 'path_step'})
        WHERE NOT (ps)<-[:HAS_STEP]-(:Entity {entity_type: 'learning_path'})
        RETURN ps
        ORDER BY ps.updated_at DESC
        LIMIT $limit
        """
        return cast(
            "Result[list[PsStandaloneStepRow]]",
            await self.execute_query(query, {"limit": limit}),
        )

    async def get_steps_using_ku(
        self, ku_uid: str, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """Get PathStep nodes that contain/teach a knowledge unit.

        Graph Pattern: (PS)-[:CONTAINS_KNOWLEDGE]->(Ku)

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ps:Entity {entity_type: 'path_step'})
        RETURN ps
        ORDER BY ps.sequence ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "limit": limit})

    async def get_prioritized_steps(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """Get PathStep nodes prioritized by user context.

        Prioritization order: in-progress first, then by status, then by priority,
        then by recency.

        Args:
            user_uid: User UID for personalization
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (ps:Entity {entity_type: 'path_step'})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[progress:STUDYING]->(ps)
        RETURN ps, progress
        ORDER BY
            CASE
                WHEN progress IS NOT NULL THEN 0
                ELSE 1
            END,
            CASE ps.status
                WHEN 'in_progress' THEN 0
                WHEN 'not_started' THEN 1
                ELSE 2
            END,
            CASE ps.priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            ps.updated_at DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"user_uid": user_uid, "limit": limit})


class LpBackend(
    _LpStepMixin,
    _LpProgressMixin,
    _LpIntelligenceMixin,
    UniversalNeo4jBackend[LearningPath],
):
    """Domain backend for LearningPath entities.

    Extends UniversalNeo4jBackend[LearningPath] with:
    - ``_LpStepMixin`` — step management CRUD + path CRUD (14 methods)
    - ``_LpProgressMixin`` — KU mastery progress + search queries (6 methods)
    - ``_LpIntelligenceMixin`` — intelligence + adaptive learning (8 methods)
    """


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
        """Get assigned exercises with submission + report status for a student.

        Returns exercise properties enriched with:
        - has_submission: bool
        - submission_uid: str | None (most recent submission)
        - submission_status: str | None
        - has_report: bool
        - report_uid: str | None (most recent report)
        - report_outcome: str | None (assessment_outcome on the report)
        - group_name: str

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
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, group, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise, group,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   group.title AS group_name
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_enrolled_ps_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get personal exercises linked to PathSteps the user is enrolled in.

        Returns the same shape as get_student_exercises_with_status() so results
        can be merged at the service layer. Exercises are discovered via:
            (user)-[:IN_PROGRESS]->(ps)-[:RELATED_TO]->(exercise {scope: 'personal'})

        Args:
            user_uid: Student UID

        Returns:
            Result containing enriched exercise records (group_name is empty string)
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.IN_PROGRESS}]->(ps:Entity)
            MATCH (ps)-[:{RelationshipName.RELATED_TO}]->(exercise:Entity {{entity_type: 'exercise'}})
            WHERE exercise.scope = 'personal'
            WITH DISTINCT user, exercise
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   '' AS group_name
            ORDER BY exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_ps_exercises_with_status(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises linked to a specific PathStep with submission/feedback status.

        Scoped version of get_enrolled_ps_exercises_with_status() — returns the same
        shape (compatible with ExerciseStatusRow) but for a single PathStep.
        """
        return await self.execute_query(
            f"""
            MATCH (ps:Entity {{uid: $ps_uid}})-[:{RelationshipName.RELATED_TO}]->(exercise:Entity {{entity_type: 'exercise'}})
            OPTIONAL MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   '' AS group_name
            ORDER BY exercise.title
            """,
            {"ps_uid": ps_uid, "user_uid": user_uid},
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

    async def get_exercises_for_path_steps(
        self, ps_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises associated with a list of PathStep UIDs.

        Traverses PathStep -[:USES_KU|CONTAINS_KNOWLEDGE]-> Ku <-[:REQUIRES_KNOWLEDGE]- Exercise
        to find exercises that practice knowledge from those PathSteps.

        Args:
            ps_uids: List of PathStep UIDs

        Returns:
            Result containing distinct exercise property dicts
        """
        if not ps_uids:
            return Result.ok([])

        result = await self.execute_query(
            f"""
            MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity)
                  <-[:{RelationshipName.REQUIRES_KNOWLEDGE}]-(ex:Entity {{entity_type: 'exercise'}})
            WHERE ps.uid IN $ps_uids
            RETURN DISTINCT ex.uid AS uid,
                   ex.title AS title,
                   ex.scope AS scope,
                   ex.description AS description,
                   ex.status AS status
            ORDER BY ex.title
            """,
            {"ps_uids": ps_uids},
        )
        if result.is_error:
            return Result.fail(result)
        items = [dict(record) for record in (result.value or [])]
        return Result.ok(items)

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's exercises with submission and reviewed counts."""
        query = f"""
        MATCH (user:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(exercise:Entity:Exercise)
        OPTIONAL MATCH (s:Entity {{entity_type: 'exercise_submission'}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
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

        Checks the graph path (OWNS-based, per ADR-040):
        - (ExerciseReport)-[:REPORT_FOR]->(Submission) exists
        - (Student)-[:OWNS]->(Submission)
        - Teacher identity is role-gated at the route level (@require_role)

        teacher_uid is retained for audit logging and future per-teacher scoping.

        Args:
            teacher_uid: Teacher user UID (for audit; access is role-gated at route)
            report_uid: Report UID
            student_uid: Student user UID

        Returns:
            Result containing matching submission records (empty if no authority)
        """
        return await self.execute_query(
            """
            MATCH (fb:Entity {uid: $report_uid})-[:REPORT_FOR]->(submission:Entity)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            WHERE submission.entity_type = 'exercise_submission'
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

    async def get_by_report_uid(self, report_uid: str) -> Result[list[Neo4jProperties]]:
        """Look up a RevisedExercise by the report it responds to."""
        query = """
        MATCH (re:RevisedExercise {report_uid: $report_uid})
        RETURN re
        LIMIT 1
        """
        return await self.execute_query(query, {"report_uid": report_uid})

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

    async def get_for_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """
        List all RevisedExercises created by a teacher, ordered by most recent.

        Traverses OWNS relationship from teacher to revised exercises for
        authoritative ownership lookup. Includes student and exercise context
        for teacher dashboard display.

        Args:
            teacher_uid: The teacher's user UID
            limit: Maximum records to return (default 50)

        Returns:
            Result containing revised exercise records with student/exercise context
        """
        return await self.execute_query(
            f"""
            MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise)
            OPTIONAL MATCH (re)-[:{RelationshipName.REVISES_EXERCISE.value}]->(ex:Entity {{entity_type: 'exercise'}})
            RETURN re.uid AS uid,
                   re.title AS title,
                   re.revision_number AS revision_number,
                   re.student_uid AS student_uid,
                   re.report_uid AS report_uid,
                   re.status AS status,
                   re.created_at AS created_at,
                   ex.uid AS exercise_uid,
                   ex.title AS exercise_title
            ORDER BY re.created_at DESC
            LIMIT $limit
            """,
            {"teacher_uid": teacher_uid, "limit": limit},
        )


class ExerciseReportBackend(UniversalNeo4jBackend[ExerciseReport]):
    """
    Domain backend for ExerciseReport entities.

    Provides relationship-specific Cypher for the five-phase learning loop:
    - get_report_for_submission     — REPORT_FOR reverse lookup
    - get_reports_for_student_exercise — all reports for a student on an exercise
    - get_reports_by_teacher        — all reports created by a teacher (user_uid)
    - create_ai_report_node         — atomic create + OWNS + REPORT_FOR + submission update
    """

    async def get_report_for_submission(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """
        Find the ExerciseReport linked to a submission via REPORT_FOR.

        Returns the most recent report first (there may be multiple — one per
        review round). Includes teacher name for display.

        Args:
            submission_uid: The ExerciseSubmission UID

        Returns:
            Result containing report records ordered by created_at DESC
        """
        return await self.execute_query(
            f"""
            MATCH (report:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity {{uid: $submission_uid}})
            OPTIONAL MATCH (teacher:User {{uid: report.user_uid}})
            RETURN report.uid AS uid,
                   report.title AS title,
                   report.report_content AS report_content,
                   report.status AS status,
                   report.processor_type AS processor_type,
                   report.assessment_outcome AS assessment_outcome,
                   report.assessment_score AS assessment_score,
                   report.created_at AS created_at,
                   report.user_uid AS teacher_uid,
                   teacher.username AS teacher_name
            ORDER BY report.created_at DESC
            """,
            {"submission_uid": submission_uid},
        )

    async def get_reports_for_student_exercise(
        self, student_uid: str, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """
        Find all ExerciseReports for a student's submissions on a given exercise.

        Traverses: (Student)-[:OWNS]->(Submission)-[:FULFILLS_EXERCISE]->(Exercise)
                   (Report)-[:REPORT_FOR]->(Submission)

        Useful for reviewing the full feedback history on a student's work
        on a specific exercise across all revision rounds.

        Args:
            student_uid: The student's user UID
            exercise_uid: The Exercise UID

        Returns:
            Result containing report records with submission context, ordered by created_at DESC
        """
        return await self.execute_query(
            f"""
            MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity)
            MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (report:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
            OPTIONAL MATCH (teacher:User {{uid: report.user_uid}})
            RETURN report.uid AS uid,
                   report.title AS title,
                   report.report_content AS report_content,
                   report.status AS status,
                   report.processor_type AS processor_type,
                   report.assessment_outcome AS assessment_outcome,
                   report.assessment_score AS assessment_score,
                   report.created_at AS created_at,
                   report.user_uid AS teacher_uid,
                   teacher.username AS teacher_name,
                   sub.uid AS submission_uid,
                   sub.title AS submission_title
            ORDER BY report.created_at DESC
            """,
            {"student_uid": student_uid, "exercise_uid": exercise_uid},
        )

    async def get_reports_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """
        List all ExerciseReports created by a teacher, ordered by most recent.

        Uses user_uid field (denormalized on creation) for O(1) lookup.
        Includes submission and student context for dashboard display.

        Args:
            teacher_uid: The teacher's user UID
            limit: Maximum records to return (default 50)

        Returns:
            Result containing report records with student/submission context
        """
        return await self.execute_query(
            f"""
            MATCH (report:ExerciseReport {{user_uid: $teacher_uid}})
            OPTIONAL MATCH (report)-[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
            OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
            RETURN report.uid AS uid,
                   report.title AS title,
                   report.status AS status,
                   report.processor_type AS processor_type,
                   report.assessment_outcome AS assessment_outcome,
                   report.assessment_score AS assessment_score,
                   report.created_at AS created_at,
                   sub.uid AS submission_uid,
                   sub.title AS submission_title,
                   student.uid AS student_uid,
                   student.username AS student_name
            ORDER BY report.created_at DESC
            LIMIT $limit
            """,
            {"teacher_uid": teacher_uid, "limit": limit},
        )

    async def create_ai_report_node(self, params: dict[str, str]) -> Result[list[Neo4jProperties]]:
        """
        Atomically create an AI-generated ExerciseReport entity in Neo4j.

        Single transaction creates:
        - :Entity:ExerciseReport node with all report fields
        - (creator)-[:OWNS]->(report) relationship
        - (report)-[:REPORT_FOR]->(submission) relationship
        - Denormalised report_content + report_generated_at on the submission

        Args:
            params: Dict with keys: submission_uid, report_uid, user_uid,
                    feedback_text, title, entity_type, completed_status,
                    processor_type, assessment_outcome, now

        Returns:
            Result containing record with report_uid on success
        """
        return await self.execute_query(
            f"""
            MATCH (submission:Entity {{uid: $submission_uid}})
            OPTIONAL MATCH (creator:User {{uid: $user_uid}})

            SET submission.report_content = $feedback_text,
                submission.report_generated_at = datetime($now),
                submission.updated_at = datetime($now)

            CREATE (fb:Entity:ExerciseReport {{
                uid: $report_uid,
                title: $title,
                entity_type: $entity_type,
                user_uid: $user_uid,
                status: $completed_status,
                processor_type: $processor_type,
                assessment_outcome: $assessment_outcome,
                content: $feedback_text,
                report_content: $feedback_text,
                report_generated_at: datetime($now),
                subject_uid: $submission_uid,
                created_by: $user_uid,
                created_at: datetime($now),
                updated_at: datetime($now)
            }})

            WITH submission, creator, fb
            CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

            WITH submission, creator, fb
            WHERE creator IS NOT NULL
            CREATE (creator)-[:{RelationshipName.OWNS.value}]->(fb)

            RETURN fb.uid AS report_uid
            """,
            params,
        )

    async def get_linked_ku_and_student(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """
        Get Ku UIDs and student UID linked to a submission via APPLIES_KNOWLEDGE.

        Used by mastery propagation after AI report generation.

        Returns:
            Records with ku_uid and student_uid fields
        """
        return await self.execute_query(
            f"""
            MATCH (submission:Entity {{uid: $submission_uid}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku:Entity {{entity_type: 'ku'}})
            OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
            RETURN ku.uid AS ku_uid, student.uid AS student_uid
            """,
            {"submission_uid": submission_uid},
        )


# Entity types that can be shared while active (not just completed)
_ACTIVITY_ENTITY_TYPES = frozenset({"task", "goal", "habit", "event", "choice", "principle"})


class SharingBackend(UniversalNeo4jBackend[Entity]):
    """
    Domain backend for cross-domain sharing operations.

    All sharing queries target :Entity nodes by UID — there are no domain-specific
    predicates. Typed to Entity (the base class) since sharing spans all entity types.

    Moves sharing Cypher from the service layer into the persistence boundary,
    following the same pattern as PsBackend (ORGANIZES), LpBackend (progress),
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
    - get_forms_for_path_step — Query FormTemplates linked to a path step via EMBEDS_FORM
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

    async def get_forms_for_path_step(self, ps_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all FormTemplates embedded in a path step."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $ps_uid}})
                  -[:{RelationshipName.EMBEDS_FORM}]->
                  (ft:Entity {{entity_type: 'form_template'}})
            RETURN ft
            ORDER BY ft.title ASC
            """,
            {"ps_uid": ps_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["ft"]) for record in (result.value or [])])

    async def link_to_path_step(self, form_template_uid: str, ps_uid: str) -> Result[bool]:
        """Create EMBEDS_FORM relationship from path step to form template."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $ps_uid}})
            WHERE a.entity_type IN ['path_step', 'ku']
            MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
            MERGE (a)-[r:{RelationshipName.EMBEDS_FORM}]->(ft)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"ps_uid": ps_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="PathStep or FormTemplate",
                    identifier=f"{ps_uid} -> {form_template_uid}",
                )
            )
        return Result.ok(True)

    async def unlink_from_path_step(self, form_template_uid: str, ps_uid: str) -> Result[bool]:
        """Remove EMBEDS_FORM relationship."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $ps_uid}})
                  -[r:{RelationshipName.EMBEDS_FORM}]->
                  (ft:Entity {{uid: $ft_uid}})
            DELETE r
            RETURN true as success
            """,
            {"ps_uid": ps_uid, "ft_uid": form_template_uid},
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
        """Get all submissions for a form template, including submitter info."""
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity {{entity_type: 'form_submission'}})
                  -[:{RelationshipName.RESPONDS_TO_FORM}]->
                  (ft:Entity {{uid: $ft_uid}})
            OPTIONAL MATCH (u:User)-[:{RelationshipName.OWNS}]->(fs)
            RETURN fs, u.uid AS user_uid, u.display_name AS user_name
            ORDER BY fs.created_at DESC
            """,
            {"ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows: list[dict[str, Any]] = []
        for record in result.value or []:
            row = dict(record["fs"])
            row["user_uid"] = record.get("user_uid")
            row["user_name"] = record.get("user_name")
            rows.append(row)
        return Result.ok(rows)

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
        OPTIONAL MATCH (sub:Entity {{entity_type: 'exercise_submission'}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex)
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
        OPTIONAL MATCH (teacher)-[:{RelationshipName.SHARES_WITH.value} {{role: 'teacher'}}]->(sub:Entity {{entity_type: 'exercise_submission'}})
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

    async def get_or_create_default_group(
        self, teacher_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE the admin's default group, creating it if it doesn't exist.

        Returns a record with group_uid.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MERGE (teacher)-[:{RelationshipName.OWNS.value}]->(g:Group {{uid: 'group_default_' + $teacher_uid}})
        ON CREATE SET g.name = 'Default Group',
                      g.description = 'Auto-created default group',
                      g.is_active = true,
                      g.created_at = datetime($now)
        RETURN g.uid AS group_uid
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid, "now": now})

    async def ensure_group_member(
        self, user_uid: UserUID, group_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE MEMBER_OF relationship — idempotent student enrolment in a group."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})
        MATCH (group:Group {{uid: $group_uid}})
        MERGE (user)-[r:{RelationshipName.MEMBER_OF.value}]->(group)
        ON CREATE SET r.joined_at = datetime($now), r.role = 'student'
        RETURN true AS success
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "group_uid": group_uid, "now": now}
        )


class ActivityReportBackend(UniversalNeo4jBackend[ActivityReport]):
    """
    Domain backend for ActivityReport entities.

    Moves inline Cypher from ActivityReportService into named backend methods.
    Methods: get_history, annotate, get_annotation, get_admin_snapshots,
    get_shares_granted, get_report_schedule.
    """

    async def get_by_uid(self, uid: str, user_uid: str) -> Result[list[Neo4jProperties]]:
        """Get a single ActivityReport by UID, scoped to the owning user."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: 'activity_report'})
            RETURN n
            """,
            {"uid": uid, "user_uid": user_uid},
        )

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
                COUNT { (blocker)-[:BLOCKS]->() } as blocks_count
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


class ResourceBackend(UniversalNeo4jBackend["Resource"]):
    """
    Domain backend for Resource entities (books, talks, films, podcasts).

    Resource is admin-curated shared content (ContentOrigin.CURATED).
    Inherits full CRUD + list from UniversalNeo4jBackend — no custom Cypher needed
    for basic library browsing. Query via NeoLabel.RESOURCE label.
    """


class InteractionBackend(UniversalNeo4jBackend["Interaction"]):
    """
    Domain backend for Interaction entities (User Interaction Contract).

    Records situated learning-loop events: who submitted what, while studying
    which PathStep, within which LearningPath.

    Inherits full CRUD + list from UniversalNeo4jBackend — no custom Cypher
    needed in Phase 1. Future ZPD integration will add traversal queries here.
    """


class ReportScheduleBackend(UniversalNeo4jBackend["ReportSchedule"]):
    """
    Domain backend for ReportSchedule entities.

    Extends UniversalNeo4jBackend with schedule-specific queries:
    - create_user_schedule_relationship: HAS_SCHEDULE link
    - get_due_schedules: Active schedules past their next_due_at
    """

    async def create_user_schedule_relationship(
        self, user_uid: str, schedule_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create HAS_SCHEDULE relationship between User and ReportSchedule."""
        return await self.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (s:ReportSchedule {uid: $schedule_uid})
            MERGE (u)-[:HAS_SCHEDULE]->(s)
            RETURN true AS success
            """,
            {"user_uid": user_uid, "schedule_uid": schedule_uid},
        )

    async def get_due_schedules(self, min_interval_hours: int) -> Result[list[Neo4jProperties]]:
        """
        Get all active schedules that are due for generation.

        Enforces a minimum interval between automatic report generations.
        """
        return await self.execute_query(
            """
            MATCH (s:ReportSchedule)
            WHERE s.is_active = true
              AND s.next_due_at <= datetime()
              AND (
                s.last_generated_at IS NULL
                OR s.last_generated_at <= datetime() - duration({hours: $min_interval_hours})
              )
            RETURN s
            ORDER BY s.next_due_at ASC
            """,
            {"min_interval_hours": min_interval_hours},
        )


class ReviewQueueBackend:
    """
    Backend for ReviewRequest node CRUD.

    ReviewRequest is a lightweight workflow marker — not an Entity subclass,
    not managed by UniversalNeo4jBackend. Uses raw Cypher via executor.

    See: /docs/architecture/REPORT_ARCHITECTURE.md
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    async def create_review_request(
        self,
        user_uid: str,
        uid: str,
        time_period: str,
        domains: list[str],
        message: str,
        now: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create a ReviewRequest node linked to the user via REQUESTED."""
        return await self.executor.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            CREATE (r:ReviewRequest {{
                uid: $uid,
                user_uid: $user_uid,
                time_period: $time_period,
                domains: $domains,
                message: $message,
                status: 'pending',
                created_at: datetime($now)
            }})
            CREATE (u)-[:{RelationshipName.REQUESTED.value}]->(r)
            RETURN r.uid AS uid, r.status AS status
            """,
            {
                "user_uid": user_uid,
                "uid": uid,
                "time_period": time_period,
                "domains": domains,
                "message": message,
                "now": now,
            },
        )

    async def get_pending_reviews(self, limit: int = 20) -> Result[list[Neo4jProperties]]:
        """Get pending review requests with user context, ordered by created_at ASC."""
        return await self.executor.execute_query(
            f"""
            MATCH (u:User)-[:{RelationshipName.REQUESTED.value}]->(r:ReviewRequest {{status: 'pending'}})
            RETURN r.uid AS uid, r.user_uid AS user_uid, r.time_period AS time_period,
                   r.domains AS domains, r.message AS message, r.created_at AS created_at,
                   u.username AS username
            ORDER BY r.created_at ASC
            LIMIT $limit
            """,
            {"limit": limit},
        )


class ActivityReportGeneratorBackend:
    """
    Backend for ProgressReportGenerator queries.

    Encapsulates cooldown check and previous-annotation fetch queries.
    Uses raw Cypher via executor — these are cross-entity queries not
    suited for UniversalNeo4jBackend.
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    async def check_cooldown(
        self, user_uid: str, cooldown_minutes: int
    ) -> Result[list[Neo4jProperties]]:
        """Check if an ActivityReport was generated within cooldown_minutes."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
            WHERE ar.entity_type = 'activity_report'
              AND ar.created_at >= datetime() - duration({minutes: $cooldown_minutes})
            RETURN count(ar) AS recent_count
            """,
            {"user_uid": user_uid, "cooldown_minutes": cooldown_minutes},
        )

    async def get_previous_annotation(
        self, user_uid: str, period_start: str
    ) -> Result[list[Neo4jProperties]]:
        """Get the most recent user_annotation from a prior ActivityReport."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
            WHERE ar.entity_type = 'activity_report'
              AND (ar.user_annotation IS NOT NULL OR ar.user_revision IS NOT NULL)
              AND ar.period_end < datetime($period_start)
            RETURN COALESCE(ar.user_annotation, ar.user_revision) AS annotation
            ORDER BY ar.period_end DESC
            LIMIT 1
            """,
            {"user_uid": user_uid, "period_start": period_start},
        )


__all__ = [
    "ActivityReportBackend",
    "ActivityReportGeneratorBackend",
    "ChoicesBackend",
    "EventsBackend",
    "ExerciseBackend",
    "ExerciseReportBackend",
    "FormSubmissionBackend",
    "FormTemplateBackend",
    "GoalsBackend",
    "GroupBackend",
    "HabitsBackend",
    "InteractionBackend",
    "JournalInputBackend",
    "JournalOutputBackend",
    "KuBackend",
    "LateralRelationshipBackend",
    "LpBackend",
    "PsBackend",
    "NotificationBackend",
    "PrinciplesBackend",
    "ReportScheduleBackend",
    "ResourceBackend",
    "ReviewQueueBackend",
    "RevisedExerciseBackend",
    "SharingBackend",
    "SubmissionsBackend",
    "TasksBackend",
]
