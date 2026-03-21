"""
Lesson Application Discovery Service - Reverse Relationship Queries
====================================================================

Answers "where is this knowledge applied/required/reinforced?" by querying
reverse relationships from activity domains back to knowledge units.

Generic method `find_activities_connected_to_knowledge()` handles all 6 activity
domains. Thin wrappers preserve the existing API for callers.

2 curriculum methods (Learning Steps, Learning Paths) remain separate as they
don't follow the same user-owned activity pattern.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from core.models.relationship_names import RelationshipName
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
    # GENERIC ACTIVITY DISCOVERY
    # ========================================================================

    @with_error_handling(
        "find_activities_connected_to_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_activities_connected_to_knowledge(
        self,
        ku_uid: str,
        user_uid: str,
        node_label: str,
        relationship_types: list[str],
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        limit: int = 10,
        reverse_direction: bool = False,
    ) -> Result[list[str]]:
        """
        Find activity entities connected to a knowledge unit via graph relationships.

        Generic method that replaces 6 structurally identical per-domain methods.

        Args:
            ku_uid: Knowledge unit UID
            user_uid: User UID to filter activities
            node_label: Neo4j node label (e.g., "Task", "Goal", "Habit")
            relationship_types: Relationship types to traverse (e.g., ["APPLIES_KNOWLEDGE"])
            filters: Optional domain-specific conditions as {cypher_fragment: params_dict}
                     e.g., {"n.status = $status_filter": {"status_filter": "active"}}
            order_by: Property to order results by (default "created_at")
            limit: Maximum results to return (default 10)
            reverse_direction: If True, use (n)<-[:REL]-(ku) instead of (n)-[:REL]->(ku)

        Returns:
            Result containing list of entity UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return verify  # type: ignore[return-value]

        # Build relationship pattern
        rel_pattern = "|".join(relationship_types)
        if reverse_direction:
            match_clause = f"MATCH (n:{node_label})-[:{rel_pattern}]<-(ku:Entity)"
        else:
            match_clause = f"MATCH (n:{node_label})-[:{rel_pattern}]->(ku:Entity)"

        # Build conditions
        conditions = ["ku.uid = $ku_uid", "n.user_uid = $user_uid"]
        params: dict[str, Any] = {"ku_uid": ku_uid, "user_uid": user_uid}

        if filters:
            for condition_fragment, filter_params in filters.items():
                conditions.append(condition_fragment)
                params.update(filter_params)

        where_clause = " AND ".join(conditions)

        query = f"""
        {match_clause}
        WHERE {where_clause}
        RETURN n.uid as entity_uid
        ORDER BY n.{order_by} DESC
        LIMIT {limit}
        """

        self.logger.debug(
            f"Finding {node_label} entities connected to knowledge {ku_uid} "
            f"via {rel_pattern} (user={user_uid})"
        )

        results = await self.neo4j.execute_query(query, params)

        if results.is_error:
            return Result.fail(results.expect_error())

        entity_uids = [record["entity_uid"] for record in results.value if record.get("entity_uid")]

        self.logger.debug(
            f"Found {len(entity_uids)} {node_label} entities connected to knowledge {ku_uid}"
        )
        return Result.ok(entity_uids)

    # ========================================================================
    # ACTIVITY DOMAIN WRAPPERS (delegate to generic method)
    # ========================================================================

    async def find_events_applying_knowledge(
        self, ku_uid: str, user_uid: str, upcoming_only: bool = True
    ) -> Result[list[str]]:
        """Find events that apply or reinforce this knowledge."""
        filters: dict[str, Any] | None = None
        if upcoming_only:
            filters = {"n.start_time >= datetime()": {}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label="Event",
            relationship_types=[
                RelationshipName.APPLIES_KNOWLEDGE.value,
                RelationshipName.REINFORCES_KNOWLEDGE.value,
            ],
            filters=filters,
            order_by="start_time",
        )

    async def find_habits_reinforcing_knowledge(
        self, ku_uid: str, user_uid: str, only_active: bool = True
    ) -> Result[list[str]]:
        """Find habits that reinforce this knowledge."""
        filters: dict[str, Any] | None = None
        if only_active:
            filters = {"n.status = $status_val": {"status_val": "active"}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label="Habit",
            relationship_types=[RelationshipName.REINFORCES_KNOWLEDGE.value],
            filters=filters,
            order_by="created_at",
        )

    async def find_tasks_applying_knowledge(
        self, ku_uid: str, user_uid: str, status_filter: str | None = None
    ) -> Result[list[str]]:
        """Find tasks that apply this knowledge."""
        filters: dict[str, Any] | None = None
        if status_filter:
            filters = {"n.status = $status_val": {"status_val": status_filter}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label="Task",
            relationship_types=[RelationshipName.APPLIES_KNOWLEDGE.value],
            filters=filters,
            order_by="due_date",
        )

    async def find_goals_requiring_knowledge(
        self, ku_uid: str, user_uid: str, status_filter: str | None = None
    ) -> Result[list[str]]:
        """Find goals that require this knowledge."""
        filters: dict[str, Any] | None = None
        if status_filter:
            filters = {"n.status = $status_val": {"status_val": status_filter}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label="Goal",
            relationship_types=[RelationshipName.REQUIRES_KNOWLEDGE.value],
            filters=filters,
            order_by="target_date",
        )

    async def find_choices_informed_by_knowledge(
        self, ku_uid: str, user_uid: str, pending_only: bool = False
    ) -> Result[list[str]]:
        """Find choices informed by this knowledge."""
        filters: dict[str, Any] | None = None
        if pending_only:
            filters = {"n.status IN ['pending', 'active']": {}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label="Choice",
            relationship_types=["INFORMS_CHOICE"],
            filters=filters,
            order_by="created_at",
            reverse_direction=True,
        )

    async def find_principles_embodying_knowledge(
        self, ku_uid: str, user_uid: str, only_active: bool = True
    ) -> Result[list[str]]:
        """Find principles that embody/reinforce this knowledge."""
        filters: dict[str, Any] | None = None
        if only_active:
            filters = {"n.is_active = true": {}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label="Principle",
            relationship_types=[RelationshipName.REINFORCES_KNOWLEDGE.value],
            filters=filters,
            order_by="strength",
        )

    # ========================================================================
    # CURRICULUM DISCOVERY (non-activity, no user_uid)
    # ========================================================================

    @with_error_handling(
        "find_learning_steps_containing", error_type="database", uid_param="ku_uid"
    )
    async def find_learning_steps_containing(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[str]]:
        """
        Find learning steps that contain/teach this knowledge.

        Graph Pattern: (Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)
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

        if results.is_error:
            return Result.fail(results.expect_error())

        step_uids = [record["step_uid"] for record in results.value if record.get("step_uid")]

        self.logger.debug(f"Found {len(step_uids)} learning steps containing knowledge {ku_uid}")
        return Result.ok(step_uids)

    @with_error_handling("find_learning_paths_teaching", error_type="database", uid_param="ku_uid")
    async def find_learning_paths_teaching(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        """
        Find learning paths that teach this knowledge (via learning steps).

        Graph Pattern: (Lp)-[:HAS_STEP]->(Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)
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

        if results.is_error:
            return Result.fail(results.expect_error())

        path_uids = [record["path_uid"] for record in results.value if record.get("path_uid")]

        self.logger.debug(f"Found {len(path_uids)} learning paths teaching knowledge {ku_uid}")
        return Result.ok(path_uids)
