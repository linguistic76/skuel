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

from adapters.persistence.neo4j._hierarchy_mixin import HierarchyConfig, _HierarchyMixin
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.entity import Entity
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
from core.models.submissions.submission import Submission
from core.models.task.task import Task
from core.models.type_hints import Neo4jProperties
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate  # noqa: F401
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
            return Result.fail(get_result.expect_error())
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: str, limit: int = 100) -> Result[list[Habit]]:
        """List all habits for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Habit], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result.expect_error())
        habits, _ = page_result.value
        return Result.ok(habits)

    async def get_user_habits(self, user_uid: str) -> Result[list[Habit]]:
        """Get all habits for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def archive_habit(self, habit_id: str) -> Result[bool]:
        """Archive a habit by transitioning its status to 'archived'."""
        update_result: Result[Habit] = await self.update(habit_id, {"status": "archived"})
        if update_result.is_error:
            return Result.fail(update_result.expect_error())
        return Result.ok(True)

    async def create_user_habit_relationship(self, user_uid: str, habit_uid: str) -> bool:
        """Create User→Habit OWNS relationship in the graph."""
        rel_result: Result[bool] = await self.create_user_relationship(user_uid, habit_uid)
        return rel_result.is_ok

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
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

    async def link_habit_to_knowledge(self, habit_uid: str, knowledge_uid: str) -> bool:
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
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"habit_uid": habit_uid, "knowledge_uid": knowledge_uid}
                )
                await result.single()
            self.logger.info(f"Linked Habit:{habit_uid} to Knowledge:{knowledge_uid}")
            return True
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link habit to knowledge: {e}")
            return False

    async def link_habit_to_principle(self, habit_uid: str, principle_uid: str) -> bool:
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
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"habit_uid": habit_uid, "principle_uid": principle_uid}
                )
                await result.single()
            self.logger.info(f"Linked Habit:{habit_uid} to Principle:{principle_uid}")
            return True
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link habit to principle: {e}")
            return False


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
            return Result.fail(get_result.expect_error())
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_id))
        return Result.ok(get_result.value)

    async def get_user_goals(self, user_uid: str) -> Result[list[Goal]]:
        """Get all goals for a user. Returns flat list (not paginated tuple)."""
        return await self.list_by_user(user_uid)

    async def list_by_user(self, user_uid: str, limit: int = 100) -> Result[list[Goal]]:
        """List all goals for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Goal], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result.expect_error())
        goals, _ = page_result.value
        return Result.ok(goals)

    async def add_milestone(self, goal_id: str, milestone: dict[str, Any]) -> Result[bool]:
        """
        Add a milestone to a goal.
        Creates: (Goal)-[:HAS_MILESTONE]->(Milestone)
        """
        try:
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
            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()
            self.logger.info(f"Added milestone to Goal:{goal_id}")
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to add milestone: {e}")
            return Result.fail(Errors.database(operation="add_milestone", message=str(e)))

    async def create_user_goal_relationship(self, user_uid: str, goal_uid: str) -> Result[bool]:
        """Create User→Goal OWNS relationship in the graph."""
        rel_result: Result[bool] = await self.create_user_relationship(user_uid, goal_uid)
        return rel_result

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
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

    async def link_goal_to_habit(self, goal_uid: str, habit_uid: str) -> Result[bool]:
        """
        Link goal to supporting habit.
        Creates: (Goal)-[:SUPPORTED_BY_HABIT]->(Habit)
        """
        try:
            query = """
            MATCH (g:Goal {uid: $goal_uid})
            MATCH (h:Habit {uid: $habit_uid})
            MERGE (g)-[r:SUPPORTED_BY_HABIT]->(h)
            RETURN r
            """
            async with self.driver.session() as session:
                result = await session.run(query, {"goal_uid": goal_uid, "habit_uid": habit_uid})
                await result.single()
            self.logger.info(f"Linked Goal:{goal_uid} to Habit:{habit_uid}")
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link goal to habit: {e}")
            return Result.fail(Errors.database(operation="link_goal_to_habit", message=str(e)))

    async def link_goal_to_knowledge(self, goal_uid: str, knowledge_uid: str) -> Result[bool]:
        """
        Link goal to required knowledge unit.
        Creates: (Goal)-[:REQUIRES_KNOWLEDGE]->(Entity)
        """
        try:
            query = """
            MATCH (g:Goal {uid: $goal_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (g)-[r:REQUIRES_KNOWLEDGE]->(k)
            RETURN r
            """
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"goal_uid": goal_uid, "knowledge_uid": knowledge_uid}
                )
                await result.single()
            self.logger.info(f"Linked Goal:{goal_uid} to Knowledge:{knowledge_uid}")
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link goal to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_goal_to_knowledge", message=str(e)))

    async def link_goal_to_principle(self, goal_uid: str, principle_uid: str) -> Result[bool]:
        """
        Link goal to guiding principle.
        Creates: (Goal)-[:GUIDED_BY_PRINCIPLE]->(Entity)
        """
        try:
            query = """
            MATCH (g:Goal {uid: $goal_uid})
            MATCH (p:Entity {uid: $principle_uid})
            MERGE (g)-[r:GUIDED_BY_PRINCIPLE]->(p)
            RETURN r
            """
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"goal_uid": goal_uid, "principle_uid": principle_uid}
                )
                await result.single()
            self.logger.info(f"Linked Goal:{goal_uid} to Principle:{principle_uid}")
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link goal to principle: {e}")
            return Result.fail(Errors.database(operation="link_goal_to_principle", message=str(e)))


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
            return Result.fail(get_result.expect_error())
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
        try:
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

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Task:{task_uid} to Knowledge:{knowledge_uid}")
            return Result.ok(True)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link task to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_task_to_knowledge", message=str(e)))

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
        try:
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

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Task:{task_uid} to Goal:{goal_uid}")
            return Result.ok(True)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link task to goal: {e}")
            return Result.fail(Errors.database(operation="link_task_to_goal", message=str(e)))

    # ========================================================================
    # LEARNING LOOP METHODS (ADR-048)
    # ========================================================================

    async def get_user_learning_state(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get learning state properties from User node for duration calibration."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            RETURN u.task_duration_ratio AS task_duration_ratio,
                   u.task_completion_count AS task_completion_count,
                   u.task_duration_updated_at AS task_duration_updated_at
            """
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                record = await result.single()
                if not record:
                    return Result.ok({})
                return Result.ok(dict(record))
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to get user learning state: {e}")
            return Result.fail(Errors.database(operation="get_user_learning_state", message=str(e)))

    async def update_user_learning_state(
        self, user_uid: str, properties: dict[str, Any]
    ) -> Result[bool]:
        """Update learning state properties on User node."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            SET u += $properties
            RETURN u.uid
            """
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "properties": properties})
                record = await result.single()
                if not record:
                    return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
                return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to update user learning state: {e}")
            return Result.fail(
                Errors.database(operation="update_user_learning_state", message=str(e))
            )

    # ========================================================================
    # HIERARCHY EXTENSIONS (Task-specific)
    # ========================================================================

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
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

    async def calculate_parent_progress(self, parent_uid: str) -> Result[dict[str, Any]]:
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
            return Result.fail(get_result.expect_error())
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: str, limit: int = 100) -> Result[list[Event]]:
        """List all events for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Event], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result.expect_error())
        events, _ = page_result.value
        return Result.ok(events)

    async def get_user_events(self, user_uid: str) -> Result[list[Event]]:
        """Get all events for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
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
        try:
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

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Event:{event_uid} to Goal:{goal_uid}")
            return Result.ok(True)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link event to goal: {e}")
            return Result.fail(Errors.database(operation="link_event_to_goal", message=str(e)))

    async def link_event_to_habit(self, event_uid: str, habit_uid: str) -> Result[bool]:
        """
        Link event to habit it reinforces.
        Creates: (Event)-[:REINFORCES_HABIT]->(Habit)
        """
        try:
            query = """
            MATCH (e:Event {uid: $event_uid})
            MATCH (h:Habit {uid: $habit_uid})
            MERGE (e)-[r:REINFORCES_HABIT]->(h)
            RETURN r
            """
            params = {"event_uid": event_uid, "habit_uid": habit_uid}

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Event:{event_uid} to Habit:{habit_uid}")
            return Result.ok(True)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link event to habit: {e}")
            return Result.fail(Errors.database(operation="link_event_to_habit", message=str(e)))

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uids: list[str]
    ) -> Result[bool]:
        """
        Link event to knowledge units it reinforces.
        Creates: (Event)-[:REINFORCES_KNOWLEDGE]->(Knowledge) for each UID
        """
        try:
            query = """
            MATCH (e:Event {uid: $event_uid})
            UNWIND $knowledge_uids AS ku_uid
            MATCH (k:Entity {uid: ku_uid})
            MERGE (e)-[r:REINFORCES_KNOWLEDGE]->(k)
            RETURN count(r) as relationship_count
            """
            params = {"event_uid": event_uid, "knowledge_uids": knowledge_uids}

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Event:{event_uid} to {len(knowledge_uids)} knowledge units")
            return Result.ok(True)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to link event to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_event_to_knowledge", message=str(e)))


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
            return Result.fail(get_result.expect_error())
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_id))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: str, limit: int = 100) -> Result[list[Choice]]:
        """List all choices for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Choice], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result.expect_error())
        choices, _ = page_result.value
        return Result.ok(choices)

    async def get_user_choices(self, user_uid: str) -> Result[list[Choice]]:
        """Get all choices for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
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

    async def create_user_choice_relationship(self, user_uid: str, choice_uid: str) -> Result[bool]:
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
            return Result.fail(get_result.expect_error())
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))
        return Result.ok(get_result.value)

    async def list_by_user(self, user_uid: str, limit: int = 100) -> Result[list[Principle]]:
        """List all principles for a user. Returns flat list (not paginated tuple)."""
        page_result: Result[tuple[list[Principle], int]] = await self.get_user_entities(
            user_uid, limit=limit
        )
        if page_result.is_error:
            return Result.fail(page_result.expect_error())
        principles, _ = page_result.value
        return Result.ok(principles)

    async def get_user_principles(self, user_uid: str) -> Result[list[Principle]]:
        """Get all principles for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
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
        self, user_uid: str, principle_uid: str
    ) -> Result[bool]:
        """Create User→Principle OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, principle_uid)


class LessonBackend(UniversalNeo4jBackend[Lesson]):
    """
    Domain backend for Lesson (unit for learning) entities.

    Extends UniversalNeo4jBackend[Lesson] with explicit implementations of
    ORGANIZES relationship operations previously handled by QueryExecutor
    in LessonOrganizationService:
    - is_organizer(lesson_uid)                     → check ORGANIZES existence
    - organize(parent_uid, child_uid, order)       → MERGE ORGANIZES relationship
    - unorganize(parent_uid, child_uid)            → DELETE ORGANIZES relationship
    - reorder(parent_uid, child_uid, new_order)    → SET r.order on ORGANIZES
    - get_organized_children(parent_uid, limit)   → fetch direct ORGANIZES children
    - find_organizers(lesson_uid)                  → find parent Lessons
    - list_root_organizers(limit)                  → Lessons not organized by anyone
    """

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        """Check if a Lesson has organized children. Returns error if not found."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
        RETURN ku IS NOT NULL AS ku_exists, count(child) > 0 AS is_organizer
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"ku_uid": ku_uid})
                records = await result.data()
            if not records:
                return Result.fail(Errors.not_found(resource="Lesson", identifier=ku_uid))
            record = records[0]
            if not record["ku_exists"]:
                return Result.fail(Errors.not_found(resource="Lesson", identifier=ku_uid))
            return Result.ok(record["is_organizer"])
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed is_organizer check for {ku_uid}: {e}")
            return Result.fail(Errors.database(operation="is_organizer", message=str(e)))

    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        """Create ORGANIZES relationship between two Lessons."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})
        MATCH (child:Entity {uid: $child_uid})
        MERGE (parent)-[r:ORGANIZES]->(child)
        SET r.order = $order
        RETURN true AS success
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {"parent_uid": parent_uid, "child_uid": child_uid, "order": order},
                )
                records = await result.data()
            success = bool(records and records[0]["success"])
            if success:
                self.logger.info(
                    f"Organized Lesson {child_uid} under {parent_uid} at position {order}"
                )
            return Result.ok(success)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed organize {child_uid} under {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="organize", message=str(e)))

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove ORGANIZES relationship between two Lessons."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity {uid: $child_uid})
        DELETE r
        RETURN true AS success
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {"parent_uid": parent_uid, "child_uid": child_uid},
                )
                records = await result.data()
            success = bool(records and records[0]["success"])
            if success:
                self.logger.info(f"Removed organization of {child_uid} from {parent_uid}")
            return Result.ok(success)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed unorganize {child_uid} from {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="unorganize", message=str(e)))

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child Lesson within its parent organizer."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity {uid: $child_uid})
        SET r.order = $new_order
        RETURN true AS success
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "parent_uid": parent_uid,
                        "child_uid": child_uid,
                        "new_order": new_order,
                    },
                )
                records = await result.data()
            return Result.ok(bool(records and records[0]["success"]))
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed reorder {child_uid} under {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="reorder", message=str(e)))

    async def get_organized_children(
        self, parent_uid: str, limit: int | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Get direct ORGANIZES children of a Lesson, ordered by position."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity)
        RETURN child.uid AS uid, child.title AS title, r.order AS order
        ORDER BY r.order ASC
        """
        params: dict[str, Any] = {"parent_uid": parent_uid}
        if limit is not None:
            query += "\nLIMIT $limit"
            params["limit"] = limit
        try:
            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = await result.data()
            children = [
                {"uid": r["uid"], "title": r["title"], "order": r["order"]} for r in records
            ]
            return Result.ok(children)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_organized_children for {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="get_organized_children", message=str(e)))

    async def find_organizers(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Find all parent Lessons that organize the given Lesson."""
        query = """
        MATCH (parent:Entity)-[r:ORGANIZES]->(ku:Entity {uid: $ku_uid})
        RETURN parent.uid AS uid, parent.title AS title, r.order AS order
        ORDER BY parent.title
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"ku_uid": ku_uid})
                records = await result.data()
            organizers = [
                {"uid": r["uid"], "title": r["title"], "order": r["order"]} for r in records
            ]
            return Result.ok(organizers)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed find_organizers for {ku_uid}: {e}")
            return Result.fail(Errors.database(operation="find_organizers", message=str(e)))

    async def list_root_organizers(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """List Kus that organize others but are not themselves organized (root organizers)."""
        query = """
        MATCH (root:Entity)-[:ORGANIZES]->(:Entity)
        WHERE NOT EXISTS((:Entity)-[:ORGANIZES]->(root))
        WITH DISTINCT root
        OPTIONAL MATCH (root)-[:ORGANIZES]->(child:Entity)
        RETURN root.uid AS uid, root.title AS title, count(child) AS child_count
        ORDER BY root.title
        LIMIT $limit
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"limit": limit})
                records = await result.data()
            roots = [
                {"uid": r["uid"], "title": r["title"], "child_count": r["child_count"]}
                for r in records
            ]
            return Result.ok(roots)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed list_root_organizers: {e}")
            return Result.fail(Errors.database(operation="list_root_organizers", message=str(e)))

    async def link_to_ku(self, lesson_uid: str, ku_uid: str) -> Result[bool]:
        """Create USES_KU relationship from Lesson to atomic Ku."""
        query = """
        MATCH (lesson:Entity {uid: $lesson_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (lesson)-[r:USES_KU]->(ku)
        RETURN true AS success
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"lesson_uid": lesson_uid, "ku_uid": ku_uid})
                records = await result.data()
            if not records:
                return Result.fail(
                    Errors.not_found(resource="Lesson or Ku", identifier=f"{lesson_uid} / {ku_uid}")
                )
            return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed link_to_ku {lesson_uid} -> {ku_uid}: {e}")
            return Result.fail(Errors.database(operation="link_to_ku", message=str(e)))

    async def get_used_kus(self, lesson_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all atomic Kus used by a Lesson via USES_KU."""
        query = """
        MATCH (lesson:Entity {uid: $lesson_uid})-[:USES_KU]->(ku:Entity)
        RETURN ku.uid AS uid, ku.title AS title, ku.namespace AS namespace,
               ku.ku_category AS ku_category
        ORDER BY ku.title
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"lesson_uid": lesson_uid})
                records = await result.data()
            return Result.ok(records)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_used_kus for {lesson_uid}: {e}")
            return Result.fail(Errors.database(operation="get_used_kus", message=str(e)))


class SubmissionsBackend(UniversalNeo4jBackend[Submission]):
    """
    Domain backend for Submission entities.

    Uses NeoLabel.ENTITY (not NeoLabel.SUBMISSION) because submissions span
    3 EntityTypes: SUBMISSION, JOURNAL, SUBMISSION_REPORT.

    Sharing and access control live in SharingBackend + UnifiedSharingService,
    operating across all entity types.
    """

    async def count_submissions_for_exercise(self, user_uid: str, exercise_uid: str) -> Result[int]:
        """Count submissions by a user for a specific exercise via FULFILLS_EXERCISE."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(e:Entity {uid: $exercise_uid})
        WHERE s.entity_type IN ['exercise_submission', 'submission']
        RETURN count(s) AS count
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"user_uid": user_uid, "exercise_uid": exercise_uid}
                )
                record = await result.single()
                return Result.ok(record["count"] if record else 0)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed count_submissions_for_exercise: {e}")
            return Result.fail(
                Errors.database(operation="count_submissions_for_exercise", message=str(e))
            )

    async def get_first_submission_for_exercise(
        self, user_uid: str, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Get earliest submission's uid + created_at for a user+exercise pair."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(e:Entity {uid: $exercise_uid})
        WHERE s.entity_type IN ['exercise_submission', 'submission']
        RETURN s.uid AS uid, s.created_at AS created_at
        ORDER BY s.created_at ASC
        LIMIT 1
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"user_uid": user_uid, "exercise_uid": exercise_uid}
                )
                record = await result.single()
                if not record:
                    return Result.ok(None)
                return Result.ok(dict(record))
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_first_submission_for_exercise: {e}")
            return Result.fail(
                Errors.database(operation="get_first_submission_for_exercise", message=str(e))
            )

    async def get_exercise_for_submission(self, submission_uid: str) -> Result[str | None]:
        """Get exercise UID linked to a submission via FULFILLS_EXERCISE."""
        query = """
        MATCH (s:Entity {uid: $submission_uid})-[:FULFILLS_EXERCISE]->(e:Entity)
        RETURN e.uid AS exercise_uid
        LIMIT 1
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"submission_uid": submission_uid})
                record = await result.single()
                if not record:
                    return Result.ok(None)
                return Result.ok(record["exercise_uid"])
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_exercise_for_submission: {e}")
            return Result.fail(
                Errors.database(operation="get_exercise_for_submission", message=str(e))
            )

    async def get_teacher_feedback_state(self, teacher_uid: str) -> Result[Neo4jProperties]:
        """Read feedback EMA state from User node for turnaround calibration."""
        query = """
        MATCH (u:User {uid: $teacher_uid})
        RETURN u.feedback_ema_hours AS feedback_ema_hours,
               u.feedback_sample_count AS feedback_sample_count,
               u.feedback_updated_at AS feedback_updated_at
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"teacher_uid": teacher_uid})
                record = await result.single()
                if not record:
                    return Result.ok({})
                return Result.ok(dict(record))
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_teacher_feedback_state: {e}")
            return Result.fail(
                Errors.database(operation="get_teacher_feedback_state", message=str(e))
            )

    async def update_teacher_feedback_state(
        self, teacher_uid: str, properties: Neo4jProperties
    ) -> Result[bool]:
        """Write feedback EMA state to User node."""
        query = """
        MATCH (u:User {uid: $teacher_uid})
        SET u += $properties
        RETURN u.uid
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query, {"teacher_uid": teacher_uid, "properties": properties}
                )
                record = await result.single()
                if not record:
                    return Result.fail(Errors.not_found(resource="User", identifier=teacher_uid))
                return Result.ok(True)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed update_teacher_feedback_state: {e}")
            return Result.fail(
                Errors.database(operation="update_teacher_feedback_state", message=str(e))
            )


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
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"ku_uid": ku_uid})
                records = await result.data()
            return Result.ok(records)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_lessons_using for {ku_uid}: {e}")
            return Result.fail(Errors.database(operation="get_lessons_using", message=str(e)))


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

    async def add_knowledge(
        self, ls_uid: str, ku_uid: str, knowledge_type: str = "primary"
    ) -> Result[bool]:
        """MERGE CONTAINS_KNOWLEDGE relationship between LS and KU."""
        query = """
        MATCH (ls:Entity {uid: $ls_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
        SET r.type = $knowledge_type,
            r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """
        result = await self.execute_query(
            query, {"ls_uid": ls_uid, "ku_uid": ku_uid, "knowledge_type": knowledge_type}
        )
        if result.is_error:
            return Result.fail(result)
        success = len(result.value or []) > 0
        if success:
            self.logger.info(
                f"Created CONTAINS_KNOWLEDGE: {ls_uid} -> {ku_uid} (type={knowledge_type})"
            )
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

    async def list_knowledge(
        self, ls_uid: str, knowledge_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """List CONTAINS_KNOWLEDGE relationships, optionally filtered by type."""
        if knowledge_type:
            query = """
            MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE {type: $knowledge_type}]->(ku:Entity)
            RETURN ku.uid as uid, ku.title as title, ku.domain as domain,
                   r.type as type, r.created_at as created_at
            ORDER BY r.created_at, ku.title
            """
            params: dict[str, Any] = {"ls_uid": ls_uid, "knowledge_type": knowledge_type}
        else:
            query = """
            MATCH (ls:Entity {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
            RETURN ku.uid as uid, ku.title as title, ku.domain as domain,
                   r.type as type, r.created_at as created_at
            ORDER BY r.type, r.created_at, ku.title
            """
            params = {"ls_uid": ls_uid}

        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "uid": r["uid"],
                    "title": r["title"],
                    "domain": r["domain"],
                    "type": r["type"],
                    "created_at": r["created_at"],
                }
                for r in result.value or []
            ]
        )

    async def get_knowledge_summary(self, ls_uid: str) -> Result[dict[str, Any]]:
        """Aggregate counts and UIDs of primary vs supporting knowledge."""
        query = """
        MATCH (ls:Entity {uid: $ls_uid})
        OPTIONAL MATCH (ls)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        WITH ls, r, ku
        RETURN
            count(CASE WHEN r.type = 'primary' THEN 1 END) as primary_count,
            count(CASE WHEN r.type = 'supporting' THEN 1 END) as supporting_count,
            count(r) as total_count,
            collect(CASE WHEN r.type = 'primary' THEN ku.uid END) as primary_uids,
            collect(CASE WHEN r.type = 'supporting' THEN ku.uid END) as supporting_uids
        """
        result = await self.execute_query(query, {"ls_uid": ls_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "primary_count": 0,
                    "supporting_count": 0,
                    "total_count": 0,
                    "primary_uids": [],
                    "supporting_uids": [],
                }
            )
        record = records[0]
        return Result.ok(
            {
                "primary_count": record["primary_count"],
                "supporting_count": record["supporting_count"],
                "total_count": record["total_count"],
                "primary_uids": [uid for uid in record["primary_uids"] if uid],
                "supporting_uids": [uid for uid in record["supporting_uids"] if uid],
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
            return Result.fail(result.expect_error())
        records = result.value or []
        return Result.ok([record["ls_uid"] for record in records])

    async def get_lesson_completion_progress(
        self, ls_uid: str, user_uid: str
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
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok({"total_lessons": 0, "completed_lessons": 0})
        record = result.value[0]
        return Result.ok(
            {
                "total_lessons": record["total_lessons"],
                "completed_lessons": record["completed_lessons"],
            }
        )


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
        """Create HAS_STEP relationship between path and step."""
        query = """
        MATCH (lp:Entity {uid: $path_uid})
        MATCH (ls:Entity {uid: $step_uid})
        CREATE (lp)-[:HAS_STEP {
            sequence: $sequence,
            order: $order,
            created_at: datetime()
        }]->(ls)
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
            return Result.fail(result.expect_error())
        records = result.value or []
        return Result.ok([record["lp_uid"] for record in records])

    async def get_ku_mastery_progress(self, lp_uid: str, user_uid: str) -> Result[Neo4jProperties]:
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
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.ok({})
        return Result.ok(dict(records[0]))


class ExerciseBackend(UniversalNeo4jBackend[Exercise]):
    """
    Domain backend for Exercise entities.

    Extends UniversalNeo4jBackend[Exercise] with curriculum-linking operations
    that were previously executed via raw execute_query calls in ExerciseService.

    Methods:
    - link_to_curriculum     — MERGE REQUIRES_KNOWLEDGE relationship
    - unlink_from_curriculum — DELETE REQUIRES_KNOWLEDGE relationship
    - get_required_knowledge — Query all KUs required by an exercise
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
            return Result.fail(result.expect_error())
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
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REQUIRES_KNOWLEDGE relationship",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def get_required_knowledge(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
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
            return Result.fail(result.expect_error())
        return Result.ok([dict(record) for record in (result.value or [])])

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
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(dict(records[0]))


class RevisedExerciseBackend(UniversalNeo4jBackend["RevisedExercise"]):
    """
    Domain backend for RevisedExercise entities.

    Provides relationship-specific Cypher for the five-phase learning loop:
    - link_to_report     — MERGE RESPONDS_TO_REPORT relationship
    - link_to_exercise   — MERGE REVISES_EXERCISE relationship
    - get_revision_chain — Query all revisions of an original exercise
    """

    async def link_to_report(self, re_uid: str, report_uid: str) -> Result[bool]:
        """Create RESPONDS_TO_REPORT relationship from revised exercise to report."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (fb:Entity {{uid: $report_uid}})
            WHERE fb.entity_type IN ['submission_feedback', 'activity_report']
            MERGE (re)-[r:{RelationshipName.RESPONDS_TO_REPORT}]->(fb)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "report_uid": report_uid},
        )
        if result.is_error:
            return Result.fail(result.expect_error())
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
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REVISES_EXERCISE relationship",
                    identifier=f"{re_uid} -> {exercise_uid}",
                )
            )
        return Result.ok(True)

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
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
            return Result.fail(result.expect_error())
        return Result.ok([dict(record) for record in (result.value or [])])


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
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def delete_share(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def update_visibility(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_access(
        self,
        entity_uid: str,
        user_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_shareable_status(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_ownership_and_status(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_shared_with_users(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_shared_with_me(
        self,
        user_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def create_group_share(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def delete_group_share(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_groups_shared_with(
        self,
        entity_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    async def query_shared_with_me_via_groups(
        self,
        user_uid: str,
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
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])


class FormTemplateBackend(UniversalNeo4jBackend["FormTemplate"]):
    """
    Domain backend for FormTemplate entities.

    Provides:
    - get_forms_for_lesson — Query FormTemplates linked to a lesson via EMBEDS_FORM
    """

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
            return Result.fail(result.expect_error())
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
            return Result.fail(result.expect_error())
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
            return Result.fail(result.expect_error())
        return Result.ok(True)


class FormSubmissionBackend(UniversalNeo4jBackend["FormSubmission"]):
    """
    Domain backend for FormSubmission entities.

    Provides:
    - get_submissions_for_template — Query all submissions for a template
    - list_by_user                 — Get user's form submissions
    """

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
            return Result.fail(result.expect_error())
        return Result.ok([dict(record["fs"]) for record in (result.value or [])])

    async def create_with_relationships(
        self,
        submission: FormSubmission,
        user_uid: str,
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
            return Result.fail(result.expect_error())
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.database("create_with_relationships", "User or template not found")
            )
        return Result.ok(from_neo4j_node(dict(records[0]["fs"]), self.entity_class))

    async def list_by_user(self, user_uid: str, limit: int = 50) -> Result[list[dict[str, Any]]]:
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
            return Result.fail(result.expect_error())
        return Result.ok([dict(record["fs"]) for record in (result.value or [])])


class JournalInputBackend(UniversalNeo4jBackend["JeInput"]):
    """
    Domain backend for JeInput entities (journal entry inputs).

    Standalone journal backend — NOT part of SubmissionsBackend.
    Uses NeoLabel.JE_INPUT with base_label=NeoLabel.ENTITY.
    """

    async def count_je_inputs_for_date(self, user_uid: str, entry_date: str) -> Result[int]:
        """Count journal entries for a user on a specific date."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.metadata IS NOT NULL
          AND ji.metadata CONTAINS $date_str
        RETURN count(ji) AS count
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "date_str": entry_date})
                record = await result.single()
                return Result.ok(record["count"] if record else 0)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed count_je_inputs_for_date: {e}")
            return Result.fail(
                Errors.database(operation="count_je_inputs_for_date", message=str(e))
            )

    async def get_ephemeral_je_inputs(
        self, user_uid: str, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get journal entries with FIFO cleanup enabled (max_retention is not null)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.max_retention IS NOT NULL
        RETURN ji
        ORDER BY ji.created_at DESC
        LIMIT $limit
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "limit": limit})
                records = [record async for record in result]
                return Result.ok([dict(record["ji"]) for record in records])
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_ephemeral_je_inputs: {e}")
            return Result.fail(Errors.database(operation="get_ephemeral_je_inputs", message=str(e)))

    async def get_je_inputs_by_date_range(
        self, user_uid: str, start_date: str, end_date: str
    ) -> Result[list[Neo4jProperties]]:
        """Get journal entries for a user within a date range (by created_at)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.created_at >= $start_date AND ji.created_at <= $end_date
        RETURN ji
        ORDER BY ji.created_at DESC
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {"user_uid": user_uid, "start_date": start_date, "end_date": end_date},
                )
                records = [record async for record in result]
                return Result.ok([dict(record["ji"]) for record in records])
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_je_inputs_by_date_range: {e}")
            return Result.fail(
                Errors.database(operation="get_je_inputs_by_date_range", message=str(e))
            )


class JournalOutputBackend(UniversalNeo4jBackend["JeOutput"]):
    """
    Domain backend for JeOutput entities (journal entry outputs).

    Standalone journal backend — NOT part of SubmissionReport infrastructure.
    Uses NeoLabel.JE_OUTPUT with base_label=NeoLabel.ENTITY.
    """

    async def get_je_output_for_input(self, je_input_uid: str) -> Result[Neo4jProperties | None]:
        """Get the je_output that transforms a specific je_input."""
        query = """
        MATCH (jo:JeOutput)-[:TRANSFORMS]->(ji:JeInput {uid: $je_input_uid})
        RETURN jo
        LIMIT 1
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"je_input_uid": je_input_uid})
                record = await result.single()
                if not record:
                    return Result.ok(None)
                return Result.ok(dict(record["jo"]))
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed get_je_output_for_input: {e}")
            return Result.fail(Errors.database(operation="get_je_output_for_input", message=str(e)))

    async def create_with_transforms(
        self,
        properties: Neo4jProperties,
        user_uid: str,
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
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {"props": properties, "user_uid": user_uid, "je_input_uid": je_input_uid},
                )
                record = await result.single()
                if not record:
                    return Result.fail(
                        Errors.database("create_with_transforms", "User or JeInput not found")
                    )
                return Result.ok(dict(record["jo"]))
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed create_with_transforms: {e}")
            return Result.fail(Errors.database(operation="create_with_transforms", message=str(e)))


__all__ = [
    "ChoicesBackend",
    "EventsBackend",
    "ExerciseBackend",
    "FormSubmissionBackend",
    "FormTemplateBackend",
    "GoalsBackend",
    "HabitsBackend",
    "JournalInputBackend",
    "JournalOutputBackend",
    "LessonBackend",
    "KuBackend",
    "LpBackend",
    "PrinciplesBackend",
    "SharingBackend",
    "SubmissionsBackend",
    "TasksBackend",
]
