"""
Prerequisite & Progress Mixin
=============================

Prerequisite / hierarchy query + user progress operations (April 2026).

Provides:
    prerequisite_traversal_raw: Traverse prerequisite relationships
    hierarchy_query_raw: Get parents + children
    user_progress_raw: User's progress/mastery for an entity
    update_user_mastery_rel: Create/update user mastery relationship
    user_curriculum_raw: Entities user is studying or has mastered

Requires on concrete class:
    driver, label
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.models.type_hints import EntityUID, UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver

    from core.ports.base_protocols import Direction


class _PrereqProgressMixin[T: DomainModelProtocol]:
    """
    Prerequisite/hierarchy + user progress operations.

    Requires on concrete class:
        driver: AsyncDriver
        label: str
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: str

    @safe_backend_operation("prerequisite_traversal_raw")
    async def prerequisite_traversal_raw(
        self,
        uid: str,
        relationship_types: builtins.list[str],
        depth: int = 3,
        direction: Direction = "outgoing",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Traverse prerequisite relationships and return raw records.

        Args:
            uid: Entity UID to start from
            relationship_types: Prerequisite relationship type strings
            depth: Maximum traversal depth
            direction: "outgoing" for prerequisites, "incoming" for enables

        Returns:
            Result[list[dict]]: Raw Neo4j records with node key "n"
        """
        from adapters.persistence.neo4j.query.cypher import build_prerequisite_traversal_query

        cypher_query, params = build_prerequisite_traversal_query(
            label=self.label,
            uid=uid,
            relationship_types=relationship_types,
            depth=depth,
            direction=direction,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("hierarchy_query_raw")
    async def hierarchy_query_raw(
        self,
        uid: str,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get hierarchical structure (parents + children) for an entity.

        Args:
            uid: Entity UID

        Returns:
            Result[list[dict]]: Records with "parents" and "children" keys
        """
        from adapters.persistence.neo4j.query.cypher import build_hierarchy_query

        cypher_query, params = build_hierarchy_query(
            label=self.label,
            uid=uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("user_progress_raw")
    async def user_progress_raw(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        mastery_threshold: float,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get user's progress/mastery for an entity.

        Args:
            user_uid: User identifier
            entity_uid: Entity identifier
            mastery_threshold: Threshold for mastery classification

        Returns:
            Result[list[dict]]: Records with "progress" key
        """
        from adapters.persistence.neo4j.query.cypher import build_user_progress_query

        cypher_query, params = build_user_progress_query(
            label=self.label,
            user_uid=user_uid,
            entity_uid=entity_uid,
            mastery_threshold=mastery_threshold,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("update_user_mastery_rel")
    async def update_user_mastery_rel(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        mastery_level: float,
        rel_type: str,
    ) -> Result[bool]:
        """
        Create/update a user mastery relationship on an entity.

        Args:
            user_uid: User identifier
            entity_uid: Entity identifier
            mastery_level: Mastery level (0.0-1.0)
            rel_type: Relationship type ("MASTERED" or "STUDYING")

        Returns:
            Result[bool]: True if successful
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (e:{self.label} {{uid: $entity_uid}})
        MERGE (u)-[r:{rel_type}]->(e)
        SET r.level = $mastery_level,
            r.last_accessed = datetime(),
            r.updated_at = datetime()
        RETURN true as success
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "user_uid": user_uid,
                    "entity_uid": entity_uid,
                    "mastery_level": mastery_level,
                },
            )
            await result.consume()
            return Result.ok(True)

    @safe_backend_operation("user_curriculum_raw")
    async def user_curriculum_raw(
        self,
        user_uid: UserUID,
        include_completed: bool = False,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get entities the user is studying or has mastered.

        Args:
            user_uid: User identifier
            include_completed: Include mastered entities

        Returns:
            Result[list[dict]]: Raw Neo4j records with node key "n"
        """
        from adapters.persistence.neo4j.query.cypher import build_user_curriculum_query

        cypher_query, params = build_user_curriculum_query(
            label=self.label,
            user_uid=user_uid,
            include_completed=include_completed,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())
