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

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins

    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit


class HabitsBackend(UniversalNeo4jBackend["Habit"]):
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
        result = await self.get(habit_id)
        if result.is_error:
            return result
        if not result.value:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_id))
        return result  # type: ignore[return-value]

    async def list_by_user(
        self, user_uid: str, limit: int = 100
    ) -> Result[builtins.list[Habit]]:
        """List all habits for a user. Returns flat list (not paginated tuple)."""
        result = await self.get_user_entities(user_uid, limit=limit)
        if result.is_error:
            return result
        habits, _ = result.value
        return Result.ok(habits)

    async def get_user_habits(self, user_uid: str) -> Result[builtins.list[Habit]]:
        """Get all habits for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def archive_habit(self, habit_id: str) -> Result[bool]:
        """Archive a habit by transitioning its status to 'archived'."""
        result = await self.update(habit_id, {"status": "archived"})
        if result.is_error:
            return result
        return Result.ok(True)

    async def create_user_habit_relationship(
        self, user_uid: str, habit_uid: str
    ) -> bool:
        """Create User→Habit OWNS relationship in the graph."""
        result = await self.create_user_relationship(user_uid, habit_uid)
        return result.is_ok

    async def link_habit_to_knowledge(
        self, habit_uid: str, knowledge_uid: str
    ) -> bool:
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

    async def link_habit_to_principle(
        self, habit_uid: str, principle_uid: str
    ) -> bool:
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


class GoalsBackend(UniversalNeo4jBackend["Goal"]):
    """
    Domain backend for Goal entities.

    Extends UniversalNeo4jBackend[Goal] with explicit implementations of
    GoalsOperations methods that fail via __getattr__:
    - get_goal(uid)         → not matched by get_*_by_uid pattern
    - get_user_goals(uid)   → not matched by any __getattr__ pattern
    - add_milestone(...)    → graph MERGE operation
    - link_goal_to_habit    → Cypher MERGE
    - link_goal_to_knowledge → Cypher MERGE
    - link_goal_to_principle → Cypher MERGE
    - create_user_goal_relationship → wraps create_user_relationship()
    """

    async def get_goal(self, goal_id: str) -> Result[Goal]:
        """Get goal by ID. Returns error if not found (contrast with get() → None)."""
        result = await self.get(goal_id)
        if result.is_error:
            return result
        if not result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_id))
        return result  # type: ignore[return-value]

    async def get_user_goals(self, user_uid: str) -> Result[builtins.list[Goal]]:
        """Get all goals for a user. Returns flat list (not paginated tuple)."""
        result = await self.get_user_entities(user_uid)
        if result.is_error:
            return result
        goals, _ = result.value
        return Result.ok(goals)

    async def add_milestone(
        self, goal_id: str, milestone: dict[str, Any]
    ) -> Result[bool]:
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

    async def create_user_goal_relationship(
        self, user_uid: str, goal_uid: str
    ) -> Result[bool]:
        """Create User→Goal OWNS relationship in the graph."""
        return await self.create_user_relationship(user_uid, goal_uid)

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
                result = await session.run(
                    query, {"goal_uid": goal_uid, "habit_uid": habit_uid}
                )
                await result.single()
            self.logger.info(f"Linked Goal:{goal_uid} to Habit:{habit_uid}")
            return Result.ok(True)
        except Exception as e:
            self.logger.error(f"Failed to link goal to habit: {e}")
            return Result.fail(Errors.database(operation="link_goal_to_habit", message=str(e)))

    async def link_goal_to_knowledge(
        self, goal_uid: str, knowledge_uid: str
    ) -> Result[bool]:
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
            return Result.fail(
                Errors.database(operation="link_goal_to_knowledge", message=str(e))
            )

    async def link_goal_to_principle(
        self, goal_uid: str, principle_uid: str
    ) -> Result[bool]:
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
            return Result.fail(
                Errors.database(operation="link_goal_to_principle", message=str(e))
            )


__all__ = ["HabitsBackend", "GoalsBackend"]
