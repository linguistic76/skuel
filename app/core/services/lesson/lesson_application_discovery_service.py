"""
Lesson Application Discovery Service - Reverse Relationship Queries
====================================================================

Answers "where is this knowledge applied/required/reinforced?" by querying
reverse relationships from activity domains back to knowledge units.

8 methods covering all activity + curriculum domains:
- Events, Habits, Tasks, Goals, Choices, Principles (activity)
- Learning Steps, Learning Paths (curriculum)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class LessonApplicationDiscoveryService:
    """
    Reverse relationship queries for knowledge application discovery.

    These methods answer "where is this knowledge being used?" by traversing
    graph relationships from activity domains back to knowledge units.
    """

    def __init__(self, repo: Any = None, neo4j_adapter: Any = None) -> None:
        """
        Initialize with backend and Neo4j adapter.

        Args:
            repo: LessonOperations backend
            neo4j_adapter: Neo4j adapter for graph operations
        """
        if not repo:
            raise ValueError("KU repository is required")
        if not neo4j_adapter:
            raise ValueError("Neo4j adapter is required for application discovery")

        self.repo = repo
        self.neo4j = neo4j_adapter
        self.logger = get_logger("skuel.services.lesson.application_discovery")

    async def _verify_ku_exists(self, ku_uid: str) -> Result[None]:
        """Verify knowledge unit exists, returning NotFound error if not."""
        ku_result = await self.repo.get(ku_uid)
        if not ku_result.is_ok or not ku_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {ku_uid} not found"))
        return Result.ok(None)

    # ========================================================================
    # APPLICATION DISCOVERY (Reverse Relationship Queries)
    # ========================================================================

    @with_error_handling(
        "find_events_applying_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_events_applying_knowledge(
        self, ku_uid: str, user_uid: str, upcoming_only: bool = True
    ) -> Result[list[str]]:
        """
        Find events that apply or reinforce this knowledge.

        Graph Pattern: (Event)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(Ku)

        This is a reverse query to discover where knowledge is being practiced.
        Supports KU application discovery for UserContextIntelligence.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter events
            upcoming_only: Only return future events (default True)

        Returns:
            Result containing list of event UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build query conditions
        conditions = ["ku.uid = $ku_uid", "e.user_uid = $user_uid"]
        if upcoming_only:
            conditions.append("e.start_time >= datetime()")

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (e:Event)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Entity)
        WHERE {where_clause}
        RETURN e.uid as event_uid
        ORDER BY e.start_time ASC
        LIMIT 10
        """

        params = {"ku_uid": ku_uid, "user_uid": user_uid}

        self.logger.debug(
            f"Finding events applying knowledge {ku_uid} "
            f"(user={user_uid}, upcoming_only={upcoming_only})"
        )

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        event_uids = []
        for record in results.value:
            event_uid = record.get("event_uid")
            if event_uid:
                event_uids.append(event_uid)

        self.logger.debug(
            f"Found {len(event_uids)} events applying knowledge {ku_uid} "
            f"(upcoming_only={upcoming_only})"
        )
        return Result.ok(event_uids)

    @with_error_handling(
        "find_habits_reinforcing_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_habits_reinforcing_knowledge(
        self, ku_uid: str, user_uid: str, only_active: bool = True
    ) -> Result[list[str]]:
        """
        Find habits that reinforce this knowledge.

        Graph Pattern: (Habit)-[:REINFORCES_KNOWLEDGE]->(Ku)

        This is a reverse query to discover where knowledge is being practiced
        through habitual behavior. Supports KU application discovery.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter habits
            only_active: Only return active habits (default True)

        Returns:
            Result containing list of habit UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build query conditions
        conditions = ["ku.uid = $ku_uid", "h.user_uid = $user_uid"]
        if only_active:
            conditions.append("h.status = 'active'")

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (h:Habit)-[:REINFORCES_KNOWLEDGE]->(ku:Entity)
        WHERE {where_clause}
        RETURN h.uid as habit_uid
        ORDER BY h.created_at DESC
        LIMIT 10
        """

        params = {"ku_uid": ku_uid, "user_uid": user_uid}

        self.logger.debug(
            f"Finding habits reinforcing knowledge {ku_uid} "
            f"(user={user_uid}, only_active={only_active})"
        )

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        habit_uids = []
        for record in results.value:
            habit_uid = record.get("habit_uid")
            if habit_uid:
                habit_uids.append(habit_uid)

        self.logger.debug(
            f"Found {len(habit_uids)} habits reinforcing knowledge {ku_uid} "
            f"(only_active={only_active})"
        )
        return Result.ok(habit_uids)

    @with_error_handling(
        "find_learning_steps_containing", error_type="database", uid_param="ku_uid"
    )
    async def find_learning_steps_containing(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[str]]:
        """
        Find learning steps that contain/teach this knowledge.

        Graph Pattern: (Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)

        This is a reverse query to discover where knowledge is taught in
        the curriculum structure. Supports curriculum navigation and discovery.

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results to return (default 10)

        Returns:
            Result containing list of learning step UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ls:Ls)
        RETURN ls.uid as step_uid
        ORDER BY ls.sequence_number ASC
        LIMIT $limit
        """

        params = {"ku_uid": ku_uid, "limit": limit}

        self.logger.debug(f"Finding learning steps containing knowledge {ku_uid} (limit={limit})")

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        step_uids = []
        for record in results.value:
            step_uid = record.get("step_uid")
            if step_uid:
                step_uids.append(step_uid)

        self.logger.debug(f"Found {len(step_uids)} learning steps containing knowledge {ku_uid}")
        return Result.ok(step_uids)

    @with_error_handling("find_learning_paths_teaching", error_type="database", uid_param="ku_uid")
    async def find_learning_paths_teaching(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        """
        Find learning paths that teach this knowledge (via learning steps).

        Graph Pattern: (Lp)-[:HAS_STEP]->(Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)

        This is a 2-hop indirect relationship query that traverses the curriculum
        hierarchy to find which learning paths cover this knowledge unit.

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results to return (default 10)

        Returns:
            Result containing list of learning path UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ls:Ls)<-[:HAS_STEP]-(lp:Lp)
        RETURN DISTINCT lp.uid as path_uid
        ORDER BY lp.created_at DESC
        LIMIT $limit
        """

        params = {"ku_uid": ku_uid, "limit": limit}

        self.logger.debug(f"Finding learning paths teaching knowledge {ku_uid} (limit={limit})")

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        path_uids = []
        for record in results.value:
            path_uid = record.get("path_uid")
            if path_uid:
                path_uids.append(path_uid)

        self.logger.debug(f"Found {len(path_uids)} learning paths teaching knowledge {ku_uid}")
        return Result.ok(path_uids)

    @with_error_handling("find_tasks_applying_knowledge", error_type="database", uid_param="ku_uid")
    async def find_tasks_applying_knowledge(
        self, ku_uid: str, user_uid: str, status_filter: str | None = None
    ) -> Result[list[str]]:
        """
        Find tasks that apply this knowledge.

        Graph Pattern: (Task)-[:APPLIES_KNOWLEDGE]->(Ku)

        This is a reverse query to discover where knowledge is being applied
        in the user's task workflow. Supports knowledge application discovery.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter tasks
            status_filter: Optional status filter (e.g., "active", "completed")

        Returns:
            Result containing list of task UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build query conditions
        conditions = ["ku.uid = $ku_uid", "t.user_uid = $user_uid"]
        params: dict[str, Any] = {"ku_uid": ku_uid, "user_uid": user_uid}

        if status_filter:
            conditions.append("t.status = $status_filter")
            params["status_filter"] = status_filter

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (t:Task)-[:APPLIES_KNOWLEDGE]->(ku:Entity)
        WHERE {where_clause}
        RETURN t.uid as task_uid
        ORDER BY t.due_date ASC
        LIMIT 10
        """

        self.logger.debug(
            f"Finding tasks applying knowledge {ku_uid} "
            f"(user={user_uid}, status_filter={status_filter})"
        )

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        task_uids = []
        for record in results.value:
            task_uid = record.get("task_uid")
            if task_uid:
                task_uids.append(task_uid)

        self.logger.debug(
            f"Found {len(task_uids)} tasks applying knowledge {ku_uid} "
            f"(status_filter={status_filter})"
        )
        return Result.ok(task_uids)

    @with_error_handling(
        "find_goals_requiring_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_goals_requiring_knowledge(
        self, ku_uid: str, user_uid: str, status_filter: str | None = None
    ) -> Result[list[str]]:
        """
        Find goals that require this knowledge.

        Graph Pattern: (Goal)-[:REQUIRES_KNOWLEDGE]->(Ku)

        This is a reverse query to discover which user goals depend on
        mastering this knowledge. Supports goal-knowledge alignment analysis.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter goals
            status_filter: Optional status filter (e.g., "active", "completed")

        Returns:
            Result containing list of goal UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build query conditions
        conditions = ["ku.uid = $ku_uid", "g.user_uid = $user_uid"]
        params: dict[str, Any] = {"ku_uid": ku_uid, "user_uid": user_uid}

        if status_filter:
            conditions.append("g.status = $status_filter")
            params["status_filter"] = status_filter

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (g:Goal)-[:REQUIRES_KNOWLEDGE]->(ku:Entity)
        WHERE {where_clause}
        RETURN g.uid as goal_uid
        ORDER BY g.target_date ASC
        LIMIT 10
        """

        self.logger.debug(
            f"Finding goals requiring knowledge {ku_uid} "
            f"(user={user_uid}, status_filter={status_filter})"
        )

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        goal_uids = []
        for record in results.value:
            goal_uid = record.get("goal_uid")
            if goal_uid:
                goal_uids.append(goal_uid)

        self.logger.debug(
            f"Found {len(goal_uids)} goals requiring knowledge {ku_uid} "
            f"(status_filter={status_filter})"
        )
        return Result.ok(goal_uids)

    @with_error_handling(
        "find_choices_informed_by_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_choices_informed_by_knowledge(
        self, ku_uid: str, user_uid: str, pending_only: bool = False
    ) -> Result[list[str]]:
        """
        Find choices informed by this knowledge.

        Graph Pattern: (Choice)-[:INFORMS_CHOICE]<-(Ku)

        This is a reverse query to discover which user choices are informed
        by this knowledge. Supports decision-making intelligence.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter choices
            pending_only: Only return pending/active choices (default False)

        Returns:
            Result containing list of choice UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build query conditions
        conditions = ["ku.uid = $ku_uid", "c.user_uid = $user_uid"]
        if pending_only:
            conditions.append("c.status IN ['pending', 'active']")

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (c:Choice)-[:INFORMS_CHOICE]<-(ku:Entity)
        WHERE {where_clause}
        RETURN c.uid as choice_uid
        ORDER BY c.created_at DESC
        LIMIT 10
        """

        params = {"ku_uid": ku_uid, "user_uid": user_uid}

        self.logger.debug(
            f"Finding choices informed by knowledge {ku_uid} "
            f"(user={user_uid}, pending_only={pending_only})"
        )

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        choice_uids = []
        for record in results.value:
            choice_uid = record.get("choice_uid")
            if choice_uid:
                choice_uids.append(choice_uid)

        self.logger.debug(
            f"Found {len(choice_uids)} choices informed by knowledge {ku_uid} "
            f"(pending_only={pending_only})"
        )
        return Result.ok(choice_uids)

    @with_error_handling(
        "find_principles_embodying_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_principles_embodying_knowledge(
        self, ku_uid: str, user_uid: str, only_active: bool = True
    ) -> Result[list[str]]:
        """
        Find principles that embody/reinforce this knowledge.

        Graph Pattern: (Principle)-[:REINFORCES_KNOWLEDGE]->(Ku)

        This is a reverse query to discover which user principles are grounded
        in or reinforced by this knowledge. Supports principle-knowledge alignment.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter principles
            only_active: Only return active principles (default True)

        Returns:
            Result containing list of principle UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build query conditions
        conditions = ["ku.uid = $ku_uid", "p.user_uid = $user_uid"]
        if only_active:
            conditions.append("p.is_active = true")

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (p:Principle)-[:REINFORCES_KNOWLEDGE]->(ku:Entity)
        WHERE {where_clause}
        RETURN p.uid as principle_uid
        ORDER BY p.strength DESC
        LIMIT 10
        """

        params = {"ku_uid": ku_uid, "user_uid": user_uid}

        self.logger.debug(
            f"Finding principles embodying knowledge {ku_uid} "
            f"(user={user_uid}, only_active={only_active})"
        )

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Extract UIDs from results
        principle_uids = []
        for record in results.value:
            principle_uid = record.get("principle_uid")
            if principle_uid:
                principle_uids.append(principle_uid)

        self.logger.debug(
            f"Found {len(principle_uids)} principles embodying knowledge {ku_uid} "
            f"(only_active={only_active})"
        )
        return Result.ok(principle_uids)
