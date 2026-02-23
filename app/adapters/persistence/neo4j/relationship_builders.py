"""
Neo4j Relationship Builders
============================

Fluent API for creating Neo4j relationships.

This module provides a relationship-first approach to graph operations:
- RelationshipBuilder: Fluent interface for creating relationships

Philosophy: "Relationships ARE the primary API, not an afterthought"

Date: October 26, 2025
Updated: October 29, 2025 - Removed TraversalBuilder (archived, unused)
"""

from typing import Any

from neo4j import AsyncDriver

from core.utils.result_simplified import Errors, Result


class RelationshipBuilder:
    """
    Fluent interface for creating Neo4j relationships.

    Example:
        await backend.relate() \
            .from_node(task_uid) \
            .via("APPLIES_KNOWLEDGE") \
            .to_node(ku_uid) \
            .with_metadata(ConfidenceLevel.GOOD, evidence="Applied in task") \
            .create()
    """

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize relationship builder.

        Args:
            driver: Neo4j async driver
        """
        self._driver = driver
        self._from_uid: str | None = None
        self._to_uid: str | None = None
        self._relationship_type: str | None = None
        self._metadata: dict[str, Any] = {}
        self._from_labels: list[str] = []
        self._to_labels: list[str] = []

    def from_node(self, uid: str, labels: list[str] | None = None) -> "RelationshipBuilder":
        """
        Specify the source node.

        Args:
            uid: UID of the source node
            labels: Optional node labels for optimization (e.g., ["Task"])

        Returns:
            Self for chaining
        """
        self._from_uid = uid
        if labels:
            self._from_labels = labels
        return self

    def via(self, relationship_type: str) -> "RelationshipBuilder":
        """
        Specify the relationship type.

        Args:
            relationship_type: Type of relationship (e.g., "APPLIES_KNOWLEDGE")

        Returns:
            Self for chaining
        """
        self._relationship_type = relationship_type
        return self

    def to_node(self, uid: str, labels: list[str] | None = None) -> "RelationshipBuilder":
        """
        Specify the target node.

        Args:
            uid: UID of the target node
            labels: Optional node labels for optimization (e.g., ["Entity"])

        Returns:
            Self for chaining
        """
        self._to_uid = uid
        if labels:
            self._to_labels = labels
        return self

    def with_metadata(self, **properties: Any) -> "RelationshipBuilder":
        """
        Add properties to the relationship.

        Args:
            **properties: Key-value pairs for relationship properties

        Returns:
            Self for chaining
        """
        self._metadata.update(properties)
        return self

    async def create(self) -> Result[bool]:
        """
        Create the relationship in Neo4j.

        Returns:
            Result containing True if relationship was created
        """
        # Validation
        if not self._from_uid:
            return Result.fail(
                Errors.validation(message="Source node UID is required", field="from_uid")
            )
        if not self._to_uid:
            return Result.fail(
                Errors.validation(message="Target node UID is required", field="to_uid")
            )
        if not self._relationship_type:
            return Result.fail(
                Errors.validation(
                    message="Relationship type is required", field="relationship_type"
                )
            )

        # Build Cypher query
        from_pattern = self._build_node_pattern(self._from_labels, "from")
        to_pattern = self._build_node_pattern(self._to_labels, "to")

        if self._metadata:
            # Build property map
            props_str = ", ".join(f"{k}: ${k}" for k in self._metadata)
            query = f"""
                MATCH (from {from_pattern})
                MATCH (to {to_pattern})
                MERGE (from)-[r:{self._relationship_type} {{{props_str}}}]->(to)
                RETURN count(r) as created
            """
            params = {"from_uid": self._from_uid, "to_uid": self._to_uid, **self._metadata}
        else:
            query = f"""
                MATCH (from {from_pattern})
                MATCH (to {to_pattern})
                MERGE (from)-[r:{self._relationship_type}]->(to)
                RETURN count(r) as created
            """
            params = {"from_uid": self._from_uid, "to_uid": self._to_uid}

        try:
            async with self._driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()
                created = record["created"] if record else 0
                return Result.ok(created > 0)
        except Exception as e:
            return Result.fail(Errors.database(operation="create_relationship", message=str(e)))

    async def delete(self) -> Result[int]:
        """
        DETACH DELETE the relationship (if it exists).

        Returns:
            Result containing count of relationships deleted
        """
        # Validation
        if not self._from_uid:
            return Result.fail(
                Errors.validation(message="Source node UID is required", field="from_uid")
            )
        if not self._to_uid:
            return Result.fail(
                Errors.validation(message="Target node UID is required", field="to_uid")
            )
        if not self._relationship_type:
            return Result.fail(
                Errors.validation(
                    message="Relationship type is required", field="relationship_type"
                )
            )

        from_pattern = self._build_node_pattern(self._from_labels, "from")
        to_pattern = self._build_node_pattern(self._to_labels, "to")

        query = f"""
            MATCH (from {from_pattern})-[r:{self._relationship_type}]->(to {to_pattern})
            DETACH DELETE r
            RETURN count(r) as deleted
        """
        params = {"from_uid": self._from_uid, "to_uid": self._to_uid}

        try:
            async with self._driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()
                deleted = record["deleted"] if record else 0
                return Result.ok(deleted)
        except Exception as e:
            return Result.fail(Errors.database(operation="delete_relationship", message=str(e)))

    def _build_node_pattern(self, labels: list[str], var_name: str) -> str:
        """Build Cypher node pattern with optional labels."""
        label_str = ":".join(labels) if labels else ""
        if label_str:
            return f":{label_str} {{uid: ${var_name}_uid}}"
        return f"{{uid: ${var_name}_uid}}"
