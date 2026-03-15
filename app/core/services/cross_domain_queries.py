"""
Cross-Domain Relationship Queries
==================================

Leverages Neo4j's strength in managing connections between domains.

PHASE 5 MIGRATION (October 3, 2025):
- Replaced APOC prerequisite traversal with CypherGenerator
- Uses semantic relationship types for type-safe queries
- Pure Cypher benefits: query planner, indexes, cache

This module provides specialized queries for domain-to-domain relationships:
- Tasks <-> Knowledge (applies_knowledge)
- Habits <-> Goals (contributes_to)
- Events <-> Knowledge (reinforces_concept)
- Finance <-> Goals (supports_financially)
- Tasks <-> Goals (advances_goal)
- Knowledge <-> Learning Paths (part_of_path)

Each relationship is bidirectional with optimized queries in both directions.
"""

from operator import attrgetter
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query import build_prerequisite_chain
from core.constants import GraphDepth
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.entity_types import ENTITY_TYPE_CLASS_MAP, CurriculumEntity
from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.finance.finance_pure import ExpensePure
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.lesson.lesson import Lesson
from core.models.task.task import Task
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor


class CrossDomainQueries:
    """
    Specialized cross-domain relationship queries.

    PHASE 5 MIGRATION: Replaced APOC with CypherGenerator.

    Leverages Neo4j relationships for fast, efficient queries that
    span multiple domains. Uses pure Cypher with semantic relationship types.
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize cross-domain query service.

        Args:
            executor: QueryExecutor for graph queries
        """
        self.executor = executor
        self.logger = get_logger("skuel.services.cross_domain_queries")

    # =========================================================================
    # Task <-> Knowledge Relationships
    # =========================================================================

    async def find_knowledge_for_task(
        self, task_uid: str, include_indirect: bool = False
    ) -> Result[list[CurriculumEntity]]:
        """
        Find knowledge units related to a task.

        PHASE 5 MIGRATION: Replaced APOC with CypherGenerator for prerequisite traversal.

        Relationship: Task -[APPLIES_KNOWLEDGE]-> Curriculum

        Args:
            task_uid: Task UID,
            include_indirect: Include indirectly related knowledge (via prerequisites)

        Returns:
            Result containing list of Knowledge objects
        """
        try:
            if include_indirect:
                # PHASE 5: Use CypherGenerator for prerequisite traversal
                # Step 1: Get directly related knowledge
                direct_cypher = """
                MATCH (t:Task {uid: $task_uid})-[:APPLIES_KNOWLEDGE]->(ku:Entity)
                RETURN collect(ku.uid) as direct_knowledge_uids, collect(ku) as direct_knowledge_nodes
                """

                direct_result = await self.executor.execute_query(
                    direct_cypher, {"task_uid": task_uid}
                )
                if direct_result.is_error:
                    return Result.fail(direct_result.expect_error())

                records = direct_result.value
                if not records:
                    return Result.ok([])

                record = records[0]
                direct_uids = record["direct_knowledge_uids"] or []
                direct_nodes = record["direct_knowledge_nodes"] or []

                # Step 2: For each direct knowledge, get prerequisites using semantic builder
                all_knowledge_nodes = list(direct_nodes)
                seen_uids = set(direct_uids)

                for ku_uid in direct_uids:
                    # Build prerequisite query using semantic types
                    _prereq_cypher, prereq_params = build_prerequisite_chain(
                        node_uid=ku_uid,
                        semantic_types=[
                            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
                            SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
                            SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
                            SemanticRelationshipType.BUILDS_ON_FOUNDATION,
                        ],
                        depth=GraphDepth.DEFAULT,
                    )

                    # Modify query to return full nodes with confidence filtering
                    prereq_query = """
                    MATCH (target {uid: $uid})
                    MATCH path = (target)<-[r:REQUIRES_THEORETICAL_UNDERSTANDING|REQUIRES_PRACTICAL_APPLICATION|REQUIRES_CONCEPTUAL_FOUNDATION|BUILDS_ON_FOUNDATION*1..3]-(prereq)
                    WHERE ALL(rel IN relationships(path) WHERE rel.confidence >= 0.7)
                    RETURN DISTINCT prereq
                    """

                    prereq_result = await self.executor.execute_query(prereq_query, prereq_params)
                    if prereq_result.is_error:
                        continue

                    prereq_records = prereq_result.value or []

                    for prereq_record in prereq_records:
                        prereq_node = prereq_record["prereq"]
                        prereq_uid = prereq_node.get("uid")
                        if prereq_uid and prereq_uid not in seen_uids:
                            all_knowledge_nodes.append(prereq_node)
                            seen_uids.add(prereq_uid)

                # Convert all nodes to Knowledge objects
                knowledge_units = []
                for node in all_knowledge_nodes:
                    ku = self._neo4j_node_to_entity(node)
                    knowledge_units.append(ku)

                # Sort by title (KnowledgeUnit always has title field)
                knowledge_units.sort(key=attrgetter("title"))

            else:
                # Direct relationships only (no change needed)
                cypher = """
                MATCH (t:Task {uid: $task_uid})-[:APPLIES_KNOWLEDGE]->(ku:Entity)
                RETURN ku AS knowledge_unit
                ORDER BY ku.title
                """

                result = await self.executor.execute_query(cypher, {"task_uid": task_uid})
                if result.is_error:
                    return Result.fail(result.expect_error())

                records = result.value or []

                knowledge_units = []
                for record in records:
                    ku_node = record["knowledge_unit"]
                    ku = self._neo4j_node_to_entity(ku_node)
                    knowledge_units.append(ku)

            self.logger.info(
                f"Found {len(knowledge_units)} knowledge units for task {task_uid} (indirect={include_indirect})"
            )

            return Result.ok(knowledge_units)

        except Exception as e:
            self.logger.error(f"Failed to find knowledge for task: {e!s}", exc_info=True)
            return Result.fail(
                Errors.database(
                    operation="find_knowledge_for_task", message=str(e), entity=task_uid
                )
            )

    @with_error_handling(
        error_type="database", operation="find_tasks_using_knowledge", uid_param="ku_uid"
    )
    async def find_tasks_using_knowledge(
        self, ku_uid: str, user_uid: str | None = None
    ) -> Result[list[Task]]:
        """
        Find tasks that apply specific knowledge.

        Relationship: Curriculum <-[APPLIES_KNOWLEDGE]- Task

        Args:
            ku_uid: Curriculum unit UID
            user_uid: Filter by user (optional)

        Returns:
            Result containing list of Task objects
        """
        if user_uid:
            cypher = """
            MATCH (ku:Entity {uid: $ku_uid})<-[:APPLIES_KNOWLEDGE]-(t:Task)
            WHERE t.user_uid = $user_uid
            RETURN t AS task
            ORDER BY t.created_at DESC
            """
            params = {"ku_uid": ku_uid, "user_uid": user_uid}
        else:
            cypher = """
            MATCH (ku:Entity {uid: $ku_uid})<-[:APPLIES_KNOWLEDGE]-(t:Task)
            RETURN t AS task
            ORDER BY t.created_at DESC
            """
            params = {"ku_uid": ku_uid}

        result = await self.executor.execute_query(cypher, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        tasks = []
        for record in records:
            task_node = record["task"]
            task = self._neo4j_node_to_task(task_node)
            tasks.append(task)

        self.logger.info(f"Found {len(tasks)} tasks using knowledge {ku_uid}")

        return Result.ok(tasks)

    # =========================================================================
    # Habit <-> Goal Relationships
    # =========================================================================

    @with_error_handling(
        error_type="database", operation="find_goals_for_habit", uid_param="habit_uid"
    )
    async def find_goals_for_habit(self, habit_uid: str) -> Result[list[Goal]]:
        """
        Find goals that a habit contributes to.

        Relationship: Habit -[CONTRIBUTES_TO]-> Goal

        Args:
            habit_uid: Habit UID

        Returns:
            Result containing list of Goal objects
        """
        cypher = """
        MATCH (h:Habit {uid: $habit_uid})-[:CONTRIBUTES_TO]->(g:Goal)
        RETURN g AS goal
        ORDER BY g.target_date
        """

        result = await self.executor.execute_query(cypher, {"habit_uid": habit_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        goals = []
        for record in records:
            goal_node = record["goal"]
            goal = self._neo4j_node_to_goal(goal_node)
            goals.append(goal)

        self.logger.info(f"Found {len(goals)} goals for habit {habit_uid}")

        return Result.ok(goals)

    @with_error_handling(
        error_type="database", operation="find_habits_for_goal", uid_param="goal_uid"
    )
    async def find_habits_for_goal(
        self, goal_uid: str, only_active: bool = True
    ) -> Result[list[Habit]]:
        """
        Find habits contributing to a goal.

        Relationship: Goal <-[CONTRIBUTES_TO]- Habit

        Args:
            goal_uid: Goal UID
            only_active: Only return active habits

        Returns:
            Result containing list of Habit objects
        """
        if only_active:
            cypher = """
            MATCH (g:Goal {uid: $goal_uid})<-[:CONTRIBUTES_TO]-(h:Habit)
            WHERE h.status = 'active'
            RETURN h AS habit
            ORDER BY h.created_at DESC
            """
        else:
            cypher = """
            MATCH (g:Goal {uid: $goal_uid})<-[:CONTRIBUTES_TO]-(h:Habit)
            RETURN h AS habit
            ORDER BY h.created_at DESC
            """

        result = await self.executor.execute_query(cypher, {"goal_uid": goal_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        habits = []
        for record in records:
            habit_node = record["habit"]
            habit = self._neo4j_node_to_habit(habit_node)
            habits.append(habit)

        self.logger.info(f"Found {len(habits)} habits for goal {goal_uid}")

        return Result.ok(habits)

    # =========================================================================
    # Event <-> Knowledge Relationships
    # =========================================================================

    @with_error_handling(
        error_type="database", operation="find_knowledge_for_event", uid_param="event_uid"
    )
    async def find_knowledge_for_event(self, event_uid: str) -> Result[list[CurriculumEntity]]:
        """
        Find knowledge reinforced by an event.

        Relationship: Event -[REINFORCES_CONCEPT]-> Curriculum

        Args:
            event_uid: Event UID

        Returns:
            Result containing list of Knowledge objects
        """
        cypher = """
        MATCH (e:Event {uid: $event_uid})-[:REINFORCES_CONCEPT]->(ku:Entity)
        RETURN ku AS knowledge_unit
        ORDER BY ku.title
        """

        result = await self.executor.execute_query(cypher, {"event_uid": event_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        knowledge_units = []
        for record in records:
            ku_node = record["knowledge_unit"]
            ku = self._neo4j_node_to_entity(ku_node)
            knowledge_units.append(ku)

        return Result.ok(knowledge_units)

    @with_error_handling(
        error_type="database", operation="find_events_reinforcing_knowledge", uid_param="ku_uid"
    )
    async def find_events_reinforcing_knowledge(
        self, ku_uid: str, user_uid: str | None = None, upcoming_only: bool = False
    ) -> Result[list[Event]]:
        """
        Find events that reinforce specific knowledge.

        Relationship: Curriculum <-[REINFORCES_CONCEPT]- Event

        Args:
            ku_uid: Curriculum unit UID
            user_uid: Filter by user (optional)
            upcoming_only: Only return future events

        Returns:
            Result containing list of Event objects
        """
        conditions = ["ku.uid = $ku_uid"]
        params: dict[str, Any] = {"ku_uid": ku_uid}

        if user_uid:
            conditions.append("e.user_uid = $user_uid")
            params["user_uid"] = user_uid

        if upcoming_only:
            conditions.append("e.start_time >= datetime()")

        where_clause = " AND ".join(conditions)

        cypher = f"""
        MATCH (ku:Entity)<-[:REINFORCES_CONCEPT]-(e:Event)
        WHERE {where_clause}
        RETURN e AS event
        ORDER BY e.start_time
        """

        result = await self.executor.execute_query(cypher, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        events = []
        for record in records:
            event_node = record["event"]
            event = self._neo4j_node_to_event(event_node)
            events.append(event)

        return Result.ok(events)

    # =========================================================================
    # Finance <-> Goal Relationships
    # =========================================================================

    @with_error_handling(
        error_type="database", operation="find_goals_supported_by_budget", uid_param="budget_uid"
    )
    async def find_goals_supported_by_budget(self, budget_uid: str) -> Result[list[Goal]]:
        """
        Find goals supported by a budget.

        Relationship: Budget -[SUPPORTS_FINANCIALLY]-> Goal

        Args:
            budget_uid: Budget UID

        Returns:
            Result containing list of Goal objects
        """
        cypher = """
        MATCH (b:Budget {uid: $budget_uid})-[:SUPPORTS_FINANCIALLY]->(g:Goal)
        RETURN g AS goal
        ORDER BY g.target_date
        """

        result = await self.executor.execute_query(cypher, {"budget_uid": budget_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        goals = []
        for record in records:
            goal_node = record["goal"]
            goal = self._neo4j_node_to_goal(goal_node)
            goals.append(goal)

        return Result.ok(goals)

    @with_error_handling(
        error_type="database", operation="find_financial_support_for_goal", uid_param="goal_uid"
    )
    async def find_financial_support_for_goal(self, goal_uid: str) -> Result[dict[str, Any]]:
        """
        Find all financial support for a goal.

        Relationships:
        - Goal <-[SUPPORTS_FINANCIALLY]- Budget
        - Goal <-[CONTRIBUTES_TO]- Expense

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing dict with budgets and expenses
        """
        cypher = """
        MATCH (g:Goal {uid: $goal_uid})
        OPTIONAL MATCH (g)<-[:SUPPORTS_FINANCIALLY]-(b:Budget)
        OPTIONAL MATCH (g)<-[:CONTRIBUTES_TO]-(e:Expense)
        RETURN
            collect(DISTINCT b) AS budgets,
            collect(DISTINCT e) AS expenses
        """

        result = await self.executor.execute_query(cypher, {"goal_uid": goal_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else {"budgets": [], "expenses": []}

        budgets = []
        for budget_node in record["budgets"]:
            if budget_node:
                budget = self._neo4j_node_to_budget(budget_node)
                budgets.append(budget)

        expenses = []
        for expense_node in record["expenses"]:
            if expense_node:
                expense = self._neo4j_node_to_expense(expense_node)
                expenses.append(expense)

        return Result.ok(
            {
                "budgets": budgets,
                "expenses": expenses,
                "total_budgeted": sum(b.amount for b in budgets),
                "total_spent": sum(e.amount for e in expenses),
            }
        )

    # =========================================================================
    # Task <-> Goal Relationships
    # =========================================================================

    @with_error_handling(
        error_type="database", operation="find_goal_for_task", uid_param="task_uid"
    )
    async def find_goal_for_task(self, task_uid: str) -> Result[Goal | None]:
        """
        Find goal that a task advances.

        Relationship: Task -[ADVANCES_GOAL]-> Goal

        Args:
            task_uid: Task UID

        Returns:
            Result containing Goal object or None
        """
        cypher = """
        MATCH (t:Task {uid: $task_uid})-[:ADVANCES_GOAL]->(g:Goal)
        RETURN g AS goal
        LIMIT 1
        """

        result = await self.executor.execute_query(cypher, {"task_uid": task_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        if records:
            goal_node = records[0]["goal"]
            goal = self._neo4j_node_to_goal(goal_node)
            return Result.ok(goal)
        else:
            return Result.ok(None)

    @with_error_handling(
        error_type="database", operation="find_tasks_for_goal", uid_param="goal_uid"
    )
    async def find_tasks_for_goal(
        self, goal_uid: str, status_filter: str | None = None
    ) -> Result[list[Task]]:
        """
        Find tasks advancing a goal.

        Relationship: Goal <-[ADVANCES_GOAL]- Task

        Args:
            goal_uid: Goal UID
            status_filter: Filter by task status (e.g., 'pending', 'completed')

        Returns:
            Result containing list of Task objects
        """
        if status_filter:
            cypher = """
            MATCH (g:Goal {uid: $goal_uid})<-[:ADVANCES_GOAL]-(t:Task)
            WHERE t.status = $status
            RETURN t AS task
            ORDER BY t.due_date, t.priority DESC
            """
            params = {"goal_uid": goal_uid, "status": status_filter}
        else:
            cypher = """
            MATCH (g:Goal {uid: $goal_uid})<-[:ADVANCES_GOAL]-(t:Task)
            RETURN t AS task
            ORDER BY t.due_date, t.priority DESC
            """
            params = {"goal_uid": goal_uid}

        result = await self.executor.execute_query(cypher, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        tasks = []
        for record in records:
            task_node = record["task"]
            task = self._neo4j_node_to_task(task_node)
            tasks.append(task)

        return Result.ok(tasks)

    # =========================================================================
    # Advanced Multi-Domain Queries
    # =========================================================================

    @with_error_handling(
        error_type="database", operation="get_complete_goal_context", uid_param="goal_uid"
    )
    async def get_complete_goal_context(
        self, goal_uid: str, user_uid: str
    ) -> Result[dict[str, Any]]:
        """
        Get complete context for a goal across all related domains.

        Finds:
        - Tasks advancing the goal
        - Habits contributing to the goal
        - Financial support (budgets and expenses)
        - Related knowledge

        Args:
            goal_uid: Goal UID,
            user_uid: User UID

        Returns:
            Result containing complete goal context
        """
        cypher = """
        MATCH (g:Goal {uid: $goal_uid, user_uid: $user_uid})

        // Get tasks
        OPTIONAL MATCH (g)<-[:ADVANCES_GOAL]-(t:Task)

        // Get habits
        OPTIONAL MATCH (g)<-[:CONTRIBUTES_TO]-(h:Habit)
        WHERE h.status = 'active'

        // Get financial support
        OPTIONAL MATCH (g)<-[:SUPPORTS_FINANCIALLY]-(b:Budget)
        OPTIONAL MATCH (g)<-[:CONTRIBUTES_TO]-(e:Expense)

        // Get related knowledge (via tasks)
        OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Entity)

        RETURN
            g AS goal,
            collect(DISTINCT t) AS tasks,
            collect(DISTINCT h) AS habits,
            collect(DISTINCT b) AS budgets,
            collect(DISTINCT e) AS expenses,
            collect(DISTINCT ku) AS knowledge_units
        """

        result = await self.executor.execute_query(
            cypher, {"goal_uid": goal_uid, "user_uid": user_uid}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        if not records:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        record = records[0]

        # Parse results
        tasks = [self._neo4j_node_to_task(n) for n in record["tasks"] if n]
        habits = [self._neo4j_node_to_habit(n) for n in record["habits"] if n]
        budgets = [self._neo4j_node_to_budget(n) for n in record["budgets"] if n]
        expenses = [self._neo4j_node_to_expense(n) for n in record["expenses"] if n]
        knowledge_units = [self._neo4j_node_to_entity(n) for n in record["knowledge_units"] if n]

        context = {
            "goal": self._neo4j_node_to_goal(record["goal"]),
            "tasks": tasks,
            "habits": habits,
            "budgets": budgets,
            "expenses": expenses,
            "knowledge_units": knowledge_units,
        }

        # Add summary statistics
        context["summary"] = {
            "total_tasks": len(tasks),
            "completed_tasks": sum(1 for t in tasks if t.status == "completed"),
            "active_habits": len(habits),
            "financial_support": sum(getattr(b, "amount", 0) for b in budgets),
            "total_spent": sum(e.amount for e in expenses),
            "knowledge_areas": len(knowledge_units),
        }

        return Result.ok(context)

    # =========================================================================
    # Helper Methods for Neo4j Node Conversion
    # =========================================================================

    def _neo4j_node_to_task(self, node) -> Task:
        """Convert Neo4j node to Task domain model."""
        from core.utils.neo4j_mapper import from_neo4j_node

        return from_neo4j_node(dict(node), Task)

    def _neo4j_node_to_event(self, node) -> Event:
        """Convert Neo4j node to Event domain model."""
        from core.utils.neo4j_mapper import from_neo4j_node

        return from_neo4j_node(dict(node), Event)

    def _neo4j_node_to_habit(self, node) -> Habit:
        """Convert Neo4j node to Habit domain model."""
        from core.utils.neo4j_mapper import from_neo4j_node

        return from_neo4j_node(dict(node), Habit)

    def _neo4j_node_to_goal(self, node) -> Goal:
        """Convert Neo4j node to Goal domain model."""
        from core.utils.neo4j_mapper import from_neo4j_node

        return from_neo4j_node(dict(node), Goal)

    def _neo4j_node_to_entity(self, node) -> CurriculumEntity:
        """Convert Neo4j node to curriculum domain model based on entity_type."""
        from core.utils.neo4j_mapper import from_neo4j_node

        node_dict = dict(node)
        entity_type_str = node_dict.get("entity_type", "lesson")
        entity_type = EntityType.from_string(entity_type_str) or EntityType.LESSON
        model_class = ENTITY_TYPE_CLASS_MAP.get(entity_type, Lesson)
        return from_neo4j_node(node_dict, model_class)  # type: ignore[return-value]

    def _neo4j_node_to_expense(self, node) -> ExpensePure:
        """Convert Neo4j node to ExpensePure domain model."""
        from core.models.finance.finance_dto import ExpenseDTO
        from core.utils.neo4j_mapper import from_neo4j_node

        dto = from_neo4j_node(dict(node), ExpenseDTO)
        return ExpensePure.from_dto(dto)

    def _neo4j_node_to_budget(self, node) -> Any:
        """Convert Neo4j node to Budget domain model."""
        from core.models.finance.finance_dto import BudgetDTO
        from core.models.finance.finance_pure import BudgetPure
        from core.utils.neo4j_mapper import from_neo4j_node

        dto = from_neo4j_node(dict(node), BudgetDTO)
        return BudgetPure.from_dto(dto)
