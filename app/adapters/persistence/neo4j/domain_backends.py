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

from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.curriculum.ku import Ku
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.utils.result_simplified import Errors, Result


class HabitsBackend(UniversalNeo4jBackend[Habit]):
    """
    Domain backend for Habit entities.

    Extends UniversalNeo4jBackend[Habit] with explicit implementations of
    HabitsOperations methods that fail via __getattr__:
    - get_habit(uid)          → not matched by get_*_by_uid pattern
    - list_by_user(uid, limit) → not matched by list_*s pattern
    - get_user_habits(uid)    → not matched by any __getattr__ pattern
    - archive_habit(uid)      → status transition (not just delete)
    - link_habit_to_knowledge → Cypher MERGE
    - link_habit_to_principle → Cypher MERGE
    - create_user_habit_relationship → wraps create_user_relationship()
    """

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
        except Exception as e:
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
        except Exception as e:
            self.logger.error(f"Failed to link habit to principle: {e}")
            return False


class GoalsBackend(UniversalNeo4jBackend[Goal]):
    """
    Domain backend for Goal entities.

    Extends UniversalNeo4jBackend[Goal] with explicit implementations of
    GoalsOperations methods that fail via __getattr__:
    - get_goal(uid)          → not matched by get_*_by_uid pattern
    - list_by_user(uid, limit) → not matched by list_*s pattern
    - get_user_goals(uid)    → delegates to list_by_user()
    - add_milestone(...)     → graph MERGE operation
    - link_goal_to_habit    → Cypher MERGE
    - link_goal_to_knowledge → Cypher MERGE
    - link_goal_to_principle → Cypher MERGE
    - create_user_goal_relationship → wraps create_user_relationship()
    """

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
        except Exception as e:
            self.logger.error(f"Failed to add milestone: {e}")
            return Result.fail(Errors.database(operation="add_milestone", message=str(e)))

    async def create_user_goal_relationship(self, user_uid: str, goal_uid: str) -> Result[bool]:
        """Create User→Goal OWNS relationship in the graph."""
        rel_result: Result[bool] = await self.create_user_relationship(user_uid, goal_uid)
        return rel_result

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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            self.logger.error(f"Failed to link goal to principle: {e}")
            return Result.fail(Errors.database(operation="link_goal_to_principle", message=str(e)))


class TasksBackend(UniversalNeo4jBackend[Task]):
    """
    Domain backend for Task entities.

    Extends UniversalNeo4jBackend[Task] with explicit implementations of
    TasksOperations methods that require domain-specific Cypher:
    - get_task(uid)              → wraps get() with NotFound check
    - link_task_to_knowledge(…)  → Cypher MERGE REQUIRES_KNOWLEDGE
    - link_task_to_goal(…)       → Cypher MERGE CONTRIBUTES_TO_GOAL
    """

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

        except Exception as e:
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

        except Exception as e:
            self.logger.error(f"Failed to link task to goal: {e}")
            return Result.fail(Errors.database(operation="link_task_to_goal", message=str(e)))


class EventsBackend(UniversalNeo4jBackend[Event]):
    """
    Domain backend for Event entities.

    Extends UniversalNeo4jBackend[Event] with explicit implementations of
    EventsOperations methods that require domain-specific Cypher:
    - get_event(uid)             → wraps get() with NotFound check
    - list_by_user(uid, limit)   → wraps get_user_entities(), extracts list
    - get_user_events(uid)       → alias for list_by_user()
    - link_event_to_goal(…)      → Cypher MERGE SUPPORTS_GOAL
    - link_event_to_habit(…)     → Cypher MERGE REINFORCES_HABIT
    - link_event_to_knowledge(…) → Cypher MERGE REINFORCES_KNOWLEDGE (batch)
    """

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

        except Exception as e:
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

        except Exception as e:
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

        except Exception as e:
            self.logger.error(f"Failed to link event to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_event_to_knowledge", message=str(e)))


class ChoicesBackend(UniversalNeo4jBackend[Choice]):
    """
    Domain backend for Choice entities.

    Extends UniversalNeo4jBackend[Choice] with explicit implementations of
    ChoicesOperations methods that don't resolve via __getattr__:
    - get_choice(uid)                      → wraps get() with NotFound check
    - list_by_user(uid, limit)             → wraps get_user_entities(), extracts list
    - get_user_choices(uid)                → alias for list_by_user()
    - create_user_choice_relationship(...) → wraps create_user_relationship()
    """

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

    async def create_user_choice_relationship(self, user_uid: str, choice_uid: str) -> Result[bool]:
        """Create User→Choice OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, choice_uid)


class PrinciplesBackend(UniversalNeo4jBackend[Principle]):
    """
    Domain backend for Principle entities.

    Extends UniversalNeo4jBackend[Principle] with explicit implementations of
    PrinciplesOperations methods that don't resolve via __getattr__:
    - get_principle(uid)                        → wraps get() with NotFound check
    - list_by_user(uid, limit)                  → wraps get_user_entities(), extracts list
    - get_user_principles(uid)                  → alias for list_by_user()
    - create_user_principle_relationship(...)   → wraps create_user_relationship()
    """

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

    async def create_user_principle_relationship(
        self, user_uid: str, principle_uid: str
    ) -> Result[bool]:
        """Create User→Principle OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, principle_uid)


class KuBackend(UniversalNeo4jBackend[Ku]):
    """
    Domain backend for Ku (Knowledge Unit) entities.

    Extends UniversalNeo4jBackend[Ku] with explicit implementations of
    ORGANIZES relationship operations previously handled by QueryExecutor
    in KuOrganizationService:
    - is_organizer(ku_uid)                        → check ORGANIZES existence + ku_exists
    - organize(parent_uid, child_uid, order)       → MERGE ORGANIZES relationship
    - unorganize(parent_uid, child_uid)            → DELETE ORGANIZES relationship
    - reorder(parent_uid, child_uid, new_order)    → SET r.order on ORGANIZES
    - get_organized_children(parent_uid, limit)   → fetch direct ORGANIZES children
    - find_organizers(ku_uid)                      → find parent Kus
    - list_root_organizers(limit)                  → Kus not organized by anyone
    """

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        """Check if a Ku has organized children. Returns error if Ku not found."""
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
                return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))
            record = records[0]
            if not record["ku_exists"]:
                return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))
            return Result.ok(record["is_organizer"])
        except Exception as e:
            self.logger.error(f"Failed is_organizer check for {ku_uid}: {e}")
            return Result.fail(Errors.database(operation="is_organizer", message=str(e)))

    async def organize(
        self, parent_uid: str, child_uid: str, order: int = 0
    ) -> Result[bool]:
        """Create ORGANIZES relationship between two Kus."""
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
                    f"Organized Ku {child_uid} under {parent_uid} at position {order}"
                )
            return Result.ok(success)
        except Exception as e:
            self.logger.error(f"Failed organize {child_uid} under {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="organize", message=str(e)))

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove ORGANIZES relationship between two Kus."""
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
        except Exception as e:
            self.logger.error(f"Failed unorganize {child_uid} from {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="unorganize", message=str(e)))

    async def reorder(
        self, parent_uid: str, child_uid: str, new_order: int
    ) -> Result[bool]:
        """Change the order of a child Ku within its parent organizer."""
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
        except Exception as e:
            self.logger.error(f"Failed reorder {child_uid} under {parent_uid}: {e}")
            return Result.fail(Errors.database(operation="reorder", message=str(e)))

    async def get_organized_children(
        self, parent_uid: str, limit: int | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Get direct ORGANIZES children of a Ku, ordered by position."""
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
                {"uid": r["uid"], "title": r["title"], "order": r["order"]}
                for r in records
            ]
            return Result.ok(children)
        except Exception as e:
            self.logger.error(f"Failed get_organized_children for {parent_uid}: {e}")
            return Result.fail(
                Errors.database(operation="get_organized_children", message=str(e))
            )

    async def find_organizers(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Find all parent Kus that organize the given Ku."""
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
                {"uid": r["uid"], "title": r["title"], "order": r["order"]}
                for r in records
            ]
            return Result.ok(organizers)
        except Exception as e:
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
        except Exception as e:
            self.logger.error(f"Failed list_root_organizers: {e}")
            return Result.fail(
                Errors.database(operation="list_root_organizers", message=str(e))
            )


__all__ = [
    "ChoicesBackend",
    "EventsBackend",
    "GoalsBackend",
    "HabitsBackend",
    "KuBackend",
    "PrinciplesBackend",
    "TasksBackend",
]
