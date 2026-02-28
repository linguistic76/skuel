"""
User Mixin
==========

User-entity relationship tracking and UserOperations protocol compliance.

Provides:
    create_user_relationship: Create (User)-[rel]->(Entity) edge
    get_user_entities: Get user's entities via relationship traversal
    count_user_entities: Count user's entities
    update_relationship_access: Increment access_count + last_accessed
    delete_user_relationship: Remove user-entity relationship
    get_user_by_username, create_user, get_user_by_uid, update_user,
    delete_user, update_user_progress, record_knowledge_mastery,
    record_knowledge_progress, enroll_in_learning_path,
    complete_learning_path_graph, express_interest_in_knowledge,
    bookmark_knowledge, update_user_activity, add_conversation_message,
    get_active_learners: UserOperations protocol methods
    link_task_to_knowledge, link_task_to_goal, link_event_to_goal,
    link_event_to_habit, link_event_to_knowledge, link_expense_to_goal,
    link_expense_to_knowledge, link_expense_to_project,
    get_expense_cross_domain_context: Domain link methods

Requires on concrete class:
    driver, logger, label, entity_class, _inject_default_filters,
    get, create, update, delete
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.utils.error_boundary import safe_backend_operation
from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver


class _UserMixin[T: DomainModelProtocol]:
    """
    User-entity tracking and UserOperations protocol compliance.

    Requires on concrete class:
        driver: AsyncDriver
        logger: Any
        label: str
        entity_class: type[T]
        _inject_default_filters: method (from shell)
        get: async method (from _CrudMixin)
        create: async method (from _CrudMixin)
        update: async method (from _CrudMixin)
        delete: async method (from _CrudMixin)
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: Any
        label: str
        entity_class: type[T]

        def _inject_default_filters(
            self,
            where_clauses: builtins.list[str],
            params: dict[str, Any],
            node_var: str = "n",
        ) -> None: ...

        async def get(self, uid: str) -> Result[T | None]: ...

        async def create(self, entity: T) -> Result[T]: ...

        async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]: ...

        async def delete(self, uid: str, cascade: bool = False) -> Result[bool]: ...

    # ============================================================================
    # USER-ENTITY RELATIONSHIP TRACKING (October 16, 2025)
    # ============================================================================
    # Complete User Tracking Across All Domains
    #
    # These methods enable tracking of user-entity relationships for ALL domains:
    # tasks, events, habits, goals, choices, principles, journals, finance, etc.
    #
    # Auto-creates (User)-[:HAS_X]->(Entity) when entities are created with user_uid.
    # Provides query methods for user-specific entity filtering and statistics.

    @safe_backend_operation("create_user_relationship")
    async def create_user_relationship(
        self,
        user_uid: str,
        entity_uid: str,
        relationship_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create user-entity relationship.

        This method is called automatically when entities are created with user_uid.
        Can also be called manually to create additional relationship types.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Neo4j relationship type. Defaults to "OWNS".
            metadata: Optional edge properties (created_at, last_accessed, priority, etc.)

        Returns:
            Result[bool] indicating success

        Example:
            # Automatically called by create() when entity has user_uid
            await backend.create_user_relationship(
                user_uid="user_123",
                entity_uid="task_456",
                relationship_type="OWNS",
                metadata={"priority": "high", "created_at": datetime.now().isoformat()}
            )
        """
        try:
            # Default relationship type: OWNS (domain-first architecture)
            if not relationship_type:
                relationship_type = "OWNS"

            # Default metadata
            default_metadata = {
                "created_at": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "access_count": 0,
                "is_active": True,
            }

            # Merge with provided metadata
            props = {**default_metadata, **(metadata or {})}

            query = f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (e:{self.label} {{uid: $entity_uid}})
            MERGE (u)-[r:{relationship_type}]->(e)
            SET r = $props
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"user_uid": user_uid, "entity_uid": entity_uid, "props": props}
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "create_user_relationship",
                            f"Failed to create relationship: User {user_uid} or {self.label} {entity_uid} not found",
                        )
                    )

                self.logger.info(
                    f"Created user relationship: {user_uid} --[{relationship_type}]-> {entity_uid}"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to create user relationship: {e}")
            return Result.fail(Errors.database("create_user_relationship", str(e)))

    @safe_backend_operation("get_user_entities")
    async def get_user_entities(
        self,
        user_uid: str,
        relationship_type: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> Result[tuple[builtins.list[T], int]]:
        """
        Get all entities for a user via relationship traversal.

        This is the PRIMARY method for user-specific entity queries.
        Replaces property-based filtering with graph relationship traversal.

        Args:
            user_uid: User UID,
            relationship_type: Optional relationship type filter (e.g., "HAS_TASK")
                              If None, uses default "HAS_{LABEL}" pattern
            filters: Optional filters on entity properties (status, priority, etc.),
            limit: Max results,
            offset: Pagination offset,
            sort_by: Field to sort by (default: created_at),
            sort_order: "asc" or "desc" (default: desc)

        Returns:
            Result[tuple[list[T], int]]: Tuple of (entities, total_count) for pagination

        Example:
            # Get all user's tasks
            result = await tasks_backend.get_user_entities("user_123")

            # Get only active tasks, sorted by due date
            result = await tasks_backend.get_user_entities(
                "user_123",
                filters={"status": "active"},
                sort_by="due_date",
                sort_order="asc"
            )

            # Get user's high-priority goals
            result = await goals_backend.get_user_entities(
                "user_123",
                filters={"priority": "high"}, limit=QueryLimit.PREVIEW
            )
        """
        try:
            # Default relationship type: OWNS (domain-first architecture)
            if not relationship_type:
                relationship_type = "OWNS"

            # Build filter clause
            filter_clauses: builtins.list[str] = []
            params: dict[str, Any] = {"user_uid": user_uid, "limit": limit, "offset": offset}

            # Inject default_filters for Ku-type discrimination
            self._inject_default_filters(filter_clauses, params, node_var="e")

            if filters:
                for key, value in filters.items():
                    filter_clauses.append(f"e.{key} = ${key}")
                    params[key] = value

            where_clause = f"WHERE {' AND '.join(filter_clauses)}" if filter_clauses else ""

            # Default sort field
            if not sort_by:
                sort_by = "created_at"

            # Sort direction
            order_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[:{relationship_type}]->(e:{self.label})
            {where_clause}
            RETURN e
            ORDER BY e.{sort_by} {order_direction}
            SKIP $offset
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = [record async for record in result]

                entities = []
                for record in records:
                    entity = from_neo4j_node(record["e"], self.entity_class)
                    entities.append(entity)

                # Get total count for pagination
                count_result = await self.count_user_entities(user_uid, relationship_type, filters)
                if count_result.is_error:
                    return Result.fail(count_result.expect_error())

                total_count = count_result.value

                self.logger.debug(
                    f"Found {len(entities)} entities for user {user_uid} (total: {total_count})"
                )
                return Result.ok((entities, total_count))

        except Exception as e:
            self.logger.error(f"Failed to get user entities: {e}")
            return Result.fail(Errors.database("get_user_entities", str(e)))

    @safe_backend_operation("count_user_entities")
    async def count_user_entities(
        self,
        user_uid: str,
        relationship_type: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Result[int]:
        """
        Count entities for a user.

        Args:
            user_uid: User UID,
            relationship_type: Optional relationship type filter,
            filters: Optional filters on entity properties

        Returns:
            Result[int] count of entities

        Example:
            # Count all user's tasks
            count_result = await tasks_backend.count_user_entities("user_123")

            # Count completed tasks
            count_result = await tasks_backend.count_user_entities(
                "user_123",
                filters={"status": "completed"}
            )
        """
        try:
            # Default relationship type: OWNS (domain-first architecture)
            if not relationship_type:
                relationship_type = "OWNS"

            # Build filter clause
            filter_clauses: builtins.list[str] = []
            params: dict[str, Any] = {"user_uid": user_uid}

            # Inject default_filters for Ku-type discrimination
            self._inject_default_filters(filter_clauses, params, node_var="e")

            if filters:
                for key, value in filters.items():
                    filter_clauses.append(f"e.{key} = ${key}")
                    params[key] = value

            where_clause = f"WHERE {' AND '.join(filter_clauses)}" if filter_clauses else ""

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[:{relationship_type}]->(e:{self.label})
            {where_clause}
            RETURN count(e) as count
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()

                count = record["count"] if record else 0
                return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to count user entities: {e}")
            return Result.fail(Errors.database("count_user_entities", str(e)))

    @safe_backend_operation("update_relationship_access")
    async def update_relationship_access(
        self, user_uid: str, entity_uid: str, relationship_type: str | None = None
    ) -> Result[bool]:
        """
        Update relationship metadata when user accesses an entity.

        Increments access_count and updates last_accessed timestamp.
        Use this to track user engagement with entities.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Optional relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Track when user views a task
            await backend.update_relationship_access(
                user_uid="user_123",
                entity_uid="task_456"
            )
        """
        try:
            if not relationship_type:
                relationship_type = "OWNS"

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[r:{relationship_type}]->(e:{self.label} {{uid: $entity_uid}})
            SET r.access_count = coalesce(r.access_count, 0) + 1,
                r.last_accessed = $now
            RETURN r.access_count as count
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "entity_uid": entity_uid,
                        "now": datetime.now().isoformat(),
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            "relationship",
                            f"User {user_uid} --[{relationship_type}]-> {self.label} {entity_uid}",
                        )
                    )

                self.logger.debug(
                    f"Updated access for {user_uid} -> {entity_uid} (count: {record['count']})"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update relationship access: {e}")
            return Result.fail(Errors.database("update_relationship_access", str(e)))

    @safe_backend_operation("delete_user_relationship")
    async def delete_user_relationship(
        self, user_uid: str, entity_uid: str, relationship_type: str | None = None
    ) -> Result[bool]:
        """
        DETACH DELETE user-entity relationship.

        Use this when transferring entity ownership or removing user access.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Optional relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Remove user's access to a shared goal
            await backend.delete_user_relationship(
                user_uid="user_123",
                entity_uid="goal_456"
            )
        """
        try:
            if not relationship_type:
                relationship_type = "OWNS"

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[r:{relationship_type}]->(e:{self.label} {{uid: $entity_uid}})
            DETACH DELETE r
            RETURN count(r) as deleted
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "entity_uid": entity_uid})
                record = await result.single()

                deleted = (record and record["deleted"] > 0) if record else False

                if deleted:
                    (
                        self.logger.info(
                            f"Deleted user relationship: {user_uid} --[{relationship_type}]-> {entity_uid}"
                        ),
                    )
                else:
                    self.logger.warning(
                        f"No relationship found to delete: {user_uid} -> {entity_uid}"
                    )

                return Result.ok(deleted)

        except Exception as e:
            self.logger.error(f"Failed to delete user relationship: {e}")
            return Result.fail(Errors.database("delete_user_relationship", str(e)))

    # ============================================================================
    # USER PROTOCOL COMPLIANCE
    # ============================================================================

    @safe_backend_operation("get_user_by_username")
    async def get_user_by_username(self, username: str) -> Result[T | None]:
        """Get user by username - required by UserOperations protocol."""
        query = f"""
        MATCH (n:{self.label} {{username: $username}})
        RETURN n
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"username": username})
            record = await result.single()

            if not record:
                return Result.ok(None)

            entity = from_neo4j_node(dict(record["n"]), self.entity_class)
            return Result.ok(entity)

    async def create_user(self, user: T) -> Result[T]:
        """Create user - required by UserOperations protocol."""
        return await self.create(user)  # type: ignore[no-any-return]

    async def get_user_by_uid(self, user_uid: str) -> Result[T | None]:
        """Get user by UID - required by UserOperations protocol."""
        return await self.get(user_uid)  # type: ignore[no-any-return]

    async def update_user(self, user: T) -> Result[T]:
        """Update user - required by UserOperations protocol."""
        # Convert user to dict for updates
        user_dict = to_neo4j_node(user)
        # Extract UID for update
        uid = user_dict.get("uid")
        if not uid:
            return Result.fail(Errors.validation("User must have uid field", field="uid"))
        # Remove uid from updates (it's used as the match key)
        updates = {k: v for k, v in user_dict.items() if k != "uid"}
        return await self.update(uid, updates)  # type: ignore[no-any-return]

    async def delete_user(self, user_uid: str) -> Result[bool]:
        """Delete user - required by UserOperations protocol."""
        return await self.delete(user_uid, cascade=True)  # type: ignore[no-any-return]

    async def update_user_progress(
        self, user_uid: str, progress_updates: dict[str, Any]
    ) -> Result[bool]:
        """Update user's learning progress - required by UserOperations protocol."""
        # Update the user's progress fields
        update_result = await self.update(user_uid, progress_updates)
        if update_result.is_error:
            return Result.fail(update_result.error)
        return Result.ok(True)

    async def record_knowledge_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[bool]:
        """Record user's mastery level for a knowledge unit - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:MASTERED]->(k)
            SET r.mastery_score = $mastery_score,
                r.practice_count = $practice_count,
                r.confidence_level = $confidence_level,
                r.mastered_at = datetime(),
                r.last_practiced = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "mastery_score": mastery_score,
                        "practice_count": practice_count,
                        "confidence_level": confidence_level,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "record_knowledge_mastery",
                            f"Failed to record mastery: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to record knowledge mastery: {e}")
            return Result.fail(Errors.database("record_knowledge_mastery", str(e)))

    async def record_knowledge_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """Record user's progress on a knowledge unit - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:IN_PROGRESS]->(k)
            SET r.progress = $progress,
                r.time_invested_minutes = coalesce(r.time_invested_minutes, 0) + $time_invested_minutes,
                r.difficulty_rating = $difficulty_rating,
                r.last_updated = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "progress": progress,
                        "time_invested_minutes": time_invested_minutes,
                        "difficulty_rating": difficulty_rating,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "record_knowledge_progress",
                            f"Failed to record progress: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to record knowledge progress: {e}")
            return Result.fail(Errors.database("record_knowledge_progress", str(e)))

    async def enroll_in_learning_path(
        self,
        user_uid: str,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """Enroll user in a learning path - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (lp:Lp {uid: $learning_path_uid})
            MERGE (u)-[r:ENROLLED]->(lp)
            SET r.enrolled_at = datetime(),
                r.target_completion = $target_completion,
                r.weekly_time_commitment = $weekly_time_commitment,
                r.motivation_note = $motivation_note,
                r.progress = 0.0
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "learning_path_uid": learning_path_uid,
                        "target_completion": target_completion,
                        "weekly_time_commitment": weekly_time_commitment,
                        "motivation_note": motivation_note,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "enroll_in_learning_path",
                            f"Failed to enroll: User {user_uid} or LearningPath {learning_path_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to enroll in learning path: {e}")
            return Result.fail(Errors.database("enroll_in_learning_path", str(e)))

    async def complete_learning_path_graph(
        self,
        user_uid: str,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """Mark a learning path as completed in the graph - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[e:ENROLLED]->(lp:Lp {uid: $learning_path_uid})
            DETACH DELETE e
            WITH u, lp
            CREATE (u)-[c:COMPLETED]->(lp)
            SET c.completed_at = datetime(),
                c.completion_score = $completion_score,
                c.feedback_rating = $feedback_rating
            RETURN c
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "learning_path_uid": learning_path_uid,
                        "completion_score": completion_score,
                        "feedback_rating": feedback_rating,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "complete_learning_path_graph",
                            f"Failed to complete: User {user_uid} or LearningPath {learning_path_uid} not found or not enrolled",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to complete learning path: {e}")
            return Result.fail(Errors.database("complete_learning_path_graph", str(e)))

    async def express_interest_in_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """Record user's interest in a knowledge unit - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:INTERESTED_IN]->(k)
            SET r.interest_score = $interest_score,
                r.interest_source = $interest_source,
                r.priority = $priority,
                r.notes = $notes,
                r.created_at = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "interest_score": interest_score,
                        "interest_source": interest_source,
                        "priority": priority,
                        "notes": notes,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "express_interest_in_knowledge",
                            f"Failed to record interest: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to express interest in knowledge: {e}")
            return Result.fail(Errors.database("express_interest_in_knowledge", str(e)))

    async def bookmark_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: builtins.list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """Bookmark a knowledge unit for later review - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:BOOKMARKED]->(k)
            SET r.bookmark_reason = $bookmark_reason,
                r.tags = $tags,
                r.reminder_date = $reminder_date,
                r.created_at = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "bookmark_reason": bookmark_reason,
                        "tags": tags,
                        "reminder_date": reminder_date,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "bookmark_knowledge",
                            f"Failed to bookmark: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to bookmark knowledge: {e}")
            return Result.fail(Errors.database("bookmark_knowledge", str(e)))

    async def update_user_activity(
        self, user_uid: str, activity_data: dict[str, Any]
    ) -> Result[bool]:
        """Update user's activity tracking data - required by UserOperations protocol."""
        # Update user node with activity data
        update_result = await self.update(user_uid, activity_data)
        if update_result.is_error:
            return Result.fail(update_result.error)
        return Result.ok(True)

    async def add_conversation_message(
        self, user_uid: str, role: str, _content: str, _metadata: dict[str, Any] | None = None
    ) -> Result[bool]:
        """Add a conversation message to user's history - required by UserOperations protocol."""
        # For now, this is a simplified implementation
        # In the future, this could create ConversationMessage nodes
        self.logger.info(f"Adding conversation message for user {user_uid} (role: {role})")
        return Result.ok(True)

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[builtins.list[T]]:
        """Get list of active learners - required by UserOperations protocol."""
        try:
            from datetime import datetime, timedelta

            cutoff_time = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

            query = f"""
            MATCH (n:{self.label})
            WHERE n.last_active >= $cutoff_time
            RETURN n
            ORDER BY n.last_active DESC
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"cutoff_time": cutoff_time, "limit": limit})
                records = await result.data()

                entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]
                return Result.ok(entities)

        except Exception as e:
            self.logger.error(f"Failed to get active learners: {e}")
            return Result.fail(Errors.database("get_active_learners", str(e)))

    # ============================================================================
    # PROTOCOL COMPLIANCE - AUTOMATIC VIA __GETATTR__
    # ============================================================================
    # Simple CRUD methods (create_task, get_task_by_uid, update_task, delete_task, list_tasks)
    # are now handled automatically by __getattr__ above.
    #
    # Only domain-specific methods remain below (link_X_to_Y, get_X_cross_domain_context, etc.)

    # ========================================================================
    # TASKS RELATIONSHIP METHODS
    # ========================================================================

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

    # Events Protocol compliance
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
        self, event_uid: str, knowledge_uids: builtins.list[str]
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

    # REMOVED: get_event_cross_domain_context()
    # Use EventsRelationshipService.get_event_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # Finance Protocol compliance - Relationship methods
    async def link_expense_to_goal(
        self, expense_uid: str, goal_uid: str, contribution_type: str = "investment"
    ) -> Result[bool]:
        """
        Link expense to goal it supports.
        Creates: (Expense)-[:SUPPORTS_GOAL {contribution_type}]->(Goal)
        """
        try:
            query = """
            MATCH (e:Expense {uid: $expense_uid})
            MATCH (g:Goal {uid: $goal_uid})
            MERGE (e)-[r:SUPPORTS_GOAL]->(g)
            SET r.contribution_type = $contribution_type
            RETURN r
            """
            params = {
                "expense_uid": expense_uid,
                "goal_uid": goal_uid,
                "contribution_type": contribution_type,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Expense:{expense_uid} to Goal:{goal_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link expense to goal: {e}")
            return Result.fail(Errors.database(operation="link_expense_to_goal", message=str(e)))

    async def link_expense_to_knowledge(
        self, expense_uid: str, knowledge_uid: str, learning_investment: bool = True
    ) -> Result[bool]:
        """
        Link expense to knowledge unit it invests in.
        Creates: (Expense)-[:INVESTS_IN_KNOWLEDGE {learning_investment}]->(Knowledge)
        """
        try:
            query = """
            MATCH (e:Expense {uid: $expense_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (e)-[r:INVESTS_IN_KNOWLEDGE]->(k)
            SET r.learning_investment = $learning_investment
            RETURN r
            """
            params = {
                "expense_uid": expense_uid,
                "knowledge_uid": knowledge_uid,
                "learning_investment": learning_investment,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Expense:{expense_uid} to Knowledge:{knowledge_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link expense to knowledge: {e}")
            return Result.fail(
                Errors.database(operation="link_expense_to_knowledge", message=str(e))
            )

    async def link_expense_to_project(
        self, expense_uid: str, project_uid: str, allocation_percentage: float = 100.0
    ) -> Result[bool]:
        """
        Link expense to project/task it funds.
        Creates: (Expense)-[:FUNDS_PROJECT {allocation_percentage}]->(Task)
        """
        try:
            query = """
            MATCH (e:Expense {uid: $expense_uid})
            MATCH (t:Task {uid: $project_uid})
            MERGE (e)-[r:FUNDS_PROJECT]->(t)
            SET r.allocation_percentage = $allocation_percentage
            RETURN r
            """
            params = {
                "expense_uid": expense_uid,
                "project_uid": project_uid,
                "allocation_percentage": allocation_percentage,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Expense:{expense_uid} to Project:{project_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link expense to project: {e}")
            return Result.fail(Errors.database(operation="link_expense_to_project", message=str(e)))

    async def get_expense_cross_domain_context(
        self, expense_uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get complete cross-domain context for an expense.

        Args:
            expense_uid: Expense UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop)

        Returns relationships to:
        - Goals (SUPPORTS_GOAL)
        - Knowledge units (INVESTS_IN_KNOWLEDGE)
        - Projects/Tasks (FUNDS_PROJECT)
        """
        try:
            # Use variable-length patterns to support depth parameter
            max_depth = max(1, depth)  # Ensure at least 1-hop
            query = f"""
            MATCH (e:Expense {{uid: $expense_uid}})
            OPTIONAL MATCH (e)-[sg:SUPPORTS_GOAL*1..{max_depth}]->(g:Goal)
            OPTIONAL MATCH (e)-[ik:INVESTS_IN_KNOWLEDGE*1..{max_depth}]->(k:Entity)
            OPTIONAL MATCH (e)-[fp:FUNDS_PROJECT*1..{max_depth}]->(t:Task)
            RETURN
                e,
                collect(DISTINCT {{goal: g, contribution_type: COALESCE(sg[0].contribution_type, 'general')}}) as goals,
                collect(DISTINCT {{knowledge: k, learning_investment: COALESCE(ik[0].learning_investment, true)}}) as knowledge,
                collect(DISTINCT {{project: t, allocation_percentage: COALESCE(fp[0].allocation_percentage, 100.0)}}) as projects
            """
            params = {"expense_uid": expense_uid}

            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()

                if not record:
                    return Result.fail(Errors.not_found(resource="Expense", identifier=expense_uid))

                context = {
                    "expense_uid": expense_uid,
                    "goals": [
                        {
                            "uid": g["goal"]["uid"],
                            "title": g["goal"].get("title"),
                            "contribution_type": g.get("contribution_type", "investment"),
                        }
                        for g in record["goals"]
                        if g["goal"] is not None
                    ],
                    "knowledge": [
                        {
                            "uid": k["knowledge"]["uid"],
                            "title": k["knowledge"].get("title"),
                            "learning_investment": k.get("learning_investment", True),
                        }
                        for k in record["knowledge"]
                        if k["knowledge"] is not None
                    ],
                    "projects": [
                        {
                            "uid": p["project"]["uid"],
                            "title": p["project"].get("title"),
                            "allocation_percentage": p.get("allocation_percentage", 100.0),
                        }
                        for p in record["projects"]
                        if p["project"] is not None
                    ],
                }

            return Result.ok(context)

        except Exception as e:
            self.logger.error(f"Failed to get expense cross-domain context: {e}")
            return Result.fail(
                Errors.database(operation="get_expense_cross_domain_context", message=str(e))
            )

    # REMOVED: get_habit_cross_domain_context()
    # Use HabitsRelationshipService.get_habit_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # REMOVED: get_goal_cross_domain_context()
    # Use GoalsRelationshipService.get_goal_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # REMOVED: get_principle_cross_domain_context()
    # Use PrinciplesRelationshipService.get_principle_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # REMOVED: get_choice_cross_domain_context()
    # Use ChoicesRelationshipService.get_choice_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.
