"""
Relationship Mixin
==================

Relationship protocol implementations:
    RelationshipCrudOperations, RelationshipMetadataOperations,
    RelationshipQueryOperations, plus fluent relate() API.

Provides:
    get_related_entities: Get related entities via graph edges
    get_related_uids: Get UIDs of related entities
    get_relationship_metadata: Get typed relationship edge properties
    update_relationship_properties: Update specific relationship properties
    get_relationships_batch: Batch relationship metadata query
    count_relationships_batch: Batch relationship counting
    get_edge_metadata: Get typed EdgeMetadata for a relationship
    update_edge_metadata: Update full edge metadata
    increment_traversal_count: Efficient traversal count increment
    _extract_label_from_uid: Fast UID-to-label mapping
    _build_direction_pattern: Build directional Cypher patterns
    _get_node_labels: Query node labels from database
    create_relationship: Create/update a graph relationship (with validation)
    delete_relationship: Delete a relationship
    delete_relationships_batch: Batch relationship deletion
    has_relationship: Check relationship existence
    count_related: Count related entities without loading them
    create_relationships_batch: Batch relationship creation (with validation)
    relate: Fluent RelationshipBuilder API
    get_prerequisites, get_enables, get_related, get_children, get_parent,
    get_depends_on, get_blocks: Convenience wrappers

Requires on concrete class:
    driver, logger, label, entity_class, default_filters,
    _default_filter_clause, _default_filter_params
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.relationship_builders import RelationshipBuilder
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from core.models.semantic import EdgeMetadata
    from core.ports.base_protocols import Direction, RelationshipMetadata


class _RelationshipMixin[T: DomainModelProtocol]:
    """
    Relationship protocol methods — Crud, Metadata, Query, fluent API.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        label: str
        entity_class: type[T]
        default_filters: dict[str, Any]
        _default_filter_clause: method
        _default_filter_params: method
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: logging.Logger
        label: str
        entity_class: type[T]
        default_filters: dict[str, Any]

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> dict[str, Any]: ...

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP QUERIES
    # ============================================================================
    # Added: October 6, 2025
    # See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
    #
    # These methods query relationships from graph edges, not node properties.
    # This enables removing relationship fields from domain models.

    async def get_related_entities(
        self, uid: str, relationship_type: str, direction: str = "outgoing", limit: int = 100
    ) -> Result[builtins.list[T]]:
        """
        Get related entities via graph edges.

        Args:
            uid: Source entity UID,
            relationship_type: Neo4j relationship type (e.g., "PREREQUISITE", "ENABLES"),
            direction: Traversal direction - "outgoing", "incoming", or "both",
            limit: Max results to return

        Returns:
            Result[List[T]] of related entities

        Example:
            # Get all prerequisites for a knowledge unit
            result = await backend.get_related_entities(
                uid="ku:python-basics",
                relationship_type="PREREQUISITE",
                direction="incoming"
            )
        """
        try:
            # Build Cypher pattern using helper
            pattern_result = self._build_direction_pattern(
                relationship_type=relationship_type,
                direction=direction,
                target_label=self.label,
            )
            if pattern_result.is_error:
                return Result.fail(pattern_result.expect_error())
            pattern = pattern_result.value

            df_clause = self._default_filter_clause()
            where_line = f"WHERE {df_clause}" if df_clause else ""

            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            MATCH {pattern}
            RETURN related
            LIMIT $limit
            """

            params: dict[str, Any] = {"uid": uid, "limit": limit}
            params.update(self._default_filter_params())

            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = [record async for record in result]

                entities = []
                for record in records:
                    node = record["related"]
                    entity = from_neo4j_node(node, self.entity_class)
                    entities.append(entity)

                self.logger.debug(f"Found {len(entities)} related entities via {relationship_type}")
                return Result.ok(entities)

        except Exception as e:
            self.logger.error(f"Failed to get related entities: {e}")
            return Result.fail(
                Errors.database(operation="get_related_entities", message=str(e), entity=self.label)
            )

    async def get_related_uids(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        limit: int = 100,
        properties: dict[str, Any] | None = None,
    ) -> Result[builtins.list[str]]:
        """
        Get UIDs of related entities via graph edge traversal.

        GRAPH-NATIVE QUERY: Traverses Neo4j edges, NOT node properties.
        This method queries actual graph relationships, enabling:
        - Multi-hop traversal (can be extended with depth parameter)
        - Relationship metadata access (if edges have properties)
        - Bidirectional queries (direction="both")
        - True graph analytics (compatible with APOC algorithms)

        Faster than get_related_entities() when you only need UIDs (no node property loading).

        Args:
            uid: Source entity UID,
            relationship_type: Neo4j relationship type (e.g., "PREREQUISITE", "ENABLES"),
            direction: Traversal direction
                - "outgoing": (n)-[:TYPE]->(related) - What this enables/points to
                - "incoming": (n)<-[:TYPE]-(related) - What requires/points to this
                - "both": (n)-[:TYPE]-(related) - All connections regardless of direction,
            limit: Max results to return (default 100)
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[List[str]] of related entity UIDs from graph traversal

        Graph Traversal Examples:
            # Get UIDs of knowledge units this enables (outgoing ENABLES edges)
            result = await backend.get_related_uids(
                uid="ku:python-basics",
                relationship_type="ENABLES",
                direction="outgoing"
            )
            # Cypher: MATCH (n {uid: $uid})-[:ENABLES]->(related) RETURN related.uid

            # Get UIDs of prerequisites (incoming PREREQUISITE edges)
            result = await backend.get_related_uids(
                uid="ku:advanced-oop",
                relationship_type="PREREQUISITE",
                direction="incoming"
            )
            # Cypher: MATCH (n {uid: $uid})<-[:PREREQUISITE]-(related) RETURN related.uid

            # Get all related topics (bidirectional RELATED_TO edges)
            result = await backend.get_related_uids(
                uid="ku:lists",
                relationship_type="RELATED_TO",
                direction="both"
            )
            # Cypher: MATCH (n {uid: $uid})-[:RELATED_TO]-(related) RETURN related.uid

            # Get habits with property filtering (e.g., essentiality="essential")
            result = await backend.get_related_uids(
                uid="goal:fitness",
                relationship_type="REQUIRES_HABIT",
                direction="outgoing",
                properties={"essentiality": "essential"}
            )
            # Cypher: MATCH (n {uid: $uid})-[r:REQUIRES_HABIT]->(related)
            # WHERE r.essentiality = $prop_essentiality
            # RETURN related.uid

        Edge Direction Semantics:
            - PREREQUISITE: Use "incoming" for requirements
              (n)<-[:PREREQUISITE]-(prereq) means "prereq is required by n"
            - ENABLES: Use "outgoing" for what this unlocks
              (n)-[:ENABLES]->(next) means "n enables/unlocks next"
            - RELATED_TO: Use "both" for bidirectional relationships
              (n)-[:RELATED_TO]-(other) means "n and other are related"

        Performance Notes:
            - Uses index on uid for O(1) node lookup
            - Returns UIDs only (no property loading) - fast for large graphs
            - For full entities with properties, use get_related_entities()
            - Compatible with APOC path expansion for multi-hop queries

        See: /docs/architecture/GRAPH_NATIVE_ANALYSIS.md for architecture details
        """
        try:
            # Extract string value for Cypher query
            rel_type = relationship_type.value

            # Build Cypher pattern using helper (with named relationship variable for property access)
            pattern_result = self._build_direction_pattern(
                relationship_type=rel_type,
                direction=direction,
                rel_var="r",
            )
            if pattern_result.is_error:
                return Result.fail(pattern_result.expect_error())
            pattern = pattern_result.value

            # Build WHERE clause for property filtering
            where_clauses = []
            params = {"uid": uid, "limit": limit}

            if properties:
                for key, value in properties.items():
                    param_name = f"prop_{key}"
                    where_clauses.append(f"r.{key} = ${param_name}")
                    params[param_name] = value

            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
            MATCH (n {{uid: $uid}})
            MATCH {pattern}
            {where_clause}
            RETURN related.uid as uid
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = [record async for record in result]
                uids = [record["uid"] for record in records if record["uid"]]

                self.logger.debug(f"Found {len(uids)} related UIDs via {relationship_type}")
                return Result.ok(uids)

        except Exception as e:
            self.logger.error(f"Failed to get related UIDs: {e}")
            return Result.fail(Errors.database(operation="get_related_uids", message=str(e)))

    async def get_relationship_metadata(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[RelationshipMetadata | None]:
        """
        Get relationship edge properties as typed metadata.

        Returns properties like strength, confidence, semantic_distance.
        Uses RelationshipMetadata TypedDict for ~80% type coverage of common fields.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type

        Returns:
            Result[Optional[Dict]] with relationship properties, or None if not found

        Example:
            # Get metadata for a prerequisite relationship
            result = await backend.get_relationship_metadata(
                from_uid="ku:programming-101",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE
            )
        """
        try:
            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            RETURN properties(r) as props
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                # Cast to RelationshipMetadata for type safety
                # TypedDict is structural - Neo4j properties map naturally
                props: RelationshipMetadata = dict(record["props"])  # type: ignore[assignment]
                return Result.ok(props)

        except Exception as e:
            self.logger.error(f"Failed to get relationship metadata: {e}")
            return Result.fail(
                Errors.database(operation="get_relationship_metadata", message=str(e))
            )

    async def update_relationship_properties(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any],
    ) -> Result[bool]:
        """
        Update specific properties on a relationship edge.

        Updates only the specified properties using SET +=, leaving others unchanged.
        More flexible than update_edge_metadata() which replaces all properties.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Neo4j relationship type
            properties: Dict of properties to update

        Returns:
            Result[bool] indicating success

        Example:
            # Update confidence and last_verified
            await backend.update_relationship_properties(
                from_uid="ku:python",
                to_uid="ku:advanced-python",
                relationship_type=RelationshipName.ENABLES_KNOWLEDGE,
                properties={"confidence": 0.95, "last_verified": datetime.now().isoformat()}
            )
        """
        try:
            if not properties:
                return Result.ok(True)  # Nothing to update

            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            SET r += $properties
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"from_uid": from_uid, "to_uid": to_uid, "properties": properties}
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            resource="Relationship",
                            identifier=f"{from_uid} --[{rel_type}]-> {to_uid}",
                        )
                    )

                self.logger.debug(
                    f"Updated {len(properties)} properties on {from_uid} --[{rel_type}]-> {to_uid}"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update relationship properties: {e}")
            return Result.fail(
                Errors.database(operation="update_relationship_properties", message=str(e))
            )

    async def get_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get metadata for multiple relationships in a single query.

        More efficient than N individual get_relationship_metadata() calls.
        Returns metadata in same order as input (empty dict if edge doesn't exist).

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            Result[List[Dict]] with metadata for each relationship

        Example:
            relationships = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = await backend.get_relationships_batch(relationships)
        """
        from core.infrastructure.batch import BatchOperationHelper

        try:
            if not relationships:
                return Result.ok([])

            # Use BatchOperationHelper for query generation
            query_result = BatchOperationHelper.build_relationship_properties_query(relationships)

            async with self.driver.session() as session:
                result = await session.run(query_result.query, query_result.params)
                records = [record async for record in result]

                # Convert to list of dicts (empty dict if None)
                metadata_list = [
                    dict(record["props"]) if record["props"] else {} for record in records
                ]

                self.logger.debug(
                    f"Fetched metadata for {len(metadata_list)} relationships ({len(relationships)} requested)"
                )
                return Result.ok(metadata_list)

        except Exception as e:
            self.logger.error(f"Failed to get relationships batch: {e}")
            return Result.fail(Errors.database(operation="get_relationships_batch", message=str(e)))

    async def count_relationships_batch(
        self, requests: builtins.list[tuple[str, str, str | None]]
    ) -> Result[dict[tuple[str, str, str], int]]:
        """
        Count multiple relationship patterns in a single query.

        More efficient than N individual count_related() calls.

        Args:
            requests: List of (uid, relationship_type, direction) tuples
                     direction: "outgoing", "incoming", or "both"

        Returns:
            Result[Dict] mapping (uid, rel_type, direction) -> count

        Example:
            requests = [
                ("task:123", "APPLIES_KNOWLEDGE", "outgoing"),
                ("task:456", "REQUIRES_KNOWLEDGE", "outgoing"),
            ]
            result = await backend.count_relationships_batch(requests)
        """
        from core.infrastructure.batch import BatchOperationHelper

        try:
            if not requests:
                return Result.ok({})

            counts: dict[tuple[str, str, str], int] = {}

            # Use BatchOperationHelper to generate optimized queries by direction
            query_results = BatchOperationHelper.build_multi_direction_count_queries(requests)

            async with self.driver.session() as session:
                # Execute each direction's query
                for direction, query_result in query_results.items():
                    result = await session.run(query_result.query, query_result.params)
                    async for record in result:
                        counts[(record["uid"], record["rel_type"], direction)] = record["count"]

                # Fill in zeros for requests that had no results
                for uid, rel_type, direction in requests:
                    key = (uid, rel_type, direction or "outgoing")
                    if key not in counts:
                        counts[key] = 0

                self.logger.debug(f"Batch counted {len(counts)} relationship patterns")
                return Result.ok(counts)

        except Exception as e:
            self.logger.error(f"Failed to count relationships batch: {e}")
            return Result.fail(
                Errors.database(operation="count_relationships_batch", message=str(e))
            )

    # ============================================================================
    # RICH EDGE PROPERTIES
    # ============================================================================
    # Added: October 6, 2025
    # See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
    #
    # These methods provide typed access to rich edge metadata.

    async def get_edge_metadata(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[EdgeMetadata | None]:
        """
        Get typed EdgeMetadata for a relationship.

        Returns EdgeMetadata with confidence, strength, semantic_distance,
        learning properties, temporal tracking, etc.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type

        Returns:
            Result[Optional[EdgeMetadata]] or None if relationship doesn't exist

        Example:
            result = await backend.get_edge_metadata(
                from_uid="ku:programming-101",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE
            )
            if result.is_ok and result.value:
                metadata = result.value
                print(f"Confidence: {metadata.confidence}")
                print(f"Strength: {metadata.strength}")
                print(f"Traversed {metadata.traversal_count} times")
        """
        from core.models.semantic import EdgeMetadata

        try:
            props_result = await self.get_relationship_metadata(from_uid, to_uid, relationship_type)

            if not props_result.is_ok:
                return Result.fail(props_result.expect_error())

            if props_result.value is None:
                return Result.ok(None)

            # Convert dict to EdgeMetadata
            metadata = EdgeMetadata.from_neo4j_properties(props_result.value)
            return Result.ok(metadata)

        except Exception as e:
            self.logger.error(f"Failed to get edge metadata: {e}")
            return Result.fail(Errors.database(operation="get_edge_metadata", message=str(e)))

    async def update_edge_metadata(
        self, from_uid: str, to_uid: str, relationship_type: str, edge_metadata: EdgeMetadata
    ) -> Result[bool]:
        """
        Update edge metadata properties.

        Replaces all edge properties with new EdgeMetadata.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type,
            edge_metadata: New metadata to set

        Returns:
            Result[bool] indicating success

        Example:
            # Increment traversal count
            metadata_result = await backend.get_edge_metadata(from_uid, to_uid, "PREREQUISITE")
            if metadata_result.is_ok and metadata_result.value:
                updated = metadata_result.value.increment_traversal()
                await backend.update_edge_metadata(from_uid, to_uid, "PREREQUISITE", updated)
        """

        try:
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{relationship_type}]->(b {{uid: $to_uid}})
            SET r = $metadata
            RETURN r
            """

            metadata_props = edge_metadata.to_neo4j_properties()

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"from_uid": from_uid, "to_uid": to_uid, "metadata": metadata_props}
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            f"Relationship not found: {from_uid} --[{relationship_type}]-> {to_uid}"
                        )
                    )

                self.logger.debug(f"Updated edge metadata for {from_uid} -> {to_uid}")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update edge metadata: {e}")
            return Result.fail(Errors.database(operation="update_edge_metadata", message=str(e)))

    async def increment_traversal_count(
        self, from_uid: str, to_uid: str, relationship_type: str
    ) -> Result[bool]:
        """
        Increment traversal count for a relationship.

        Updates traversal_count and last_traversed timestamp.
        More efficient than fetching + updating full metadata.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Track relationship usage
            await backend.increment_traversal_count(
                from_uid="ku:programming-101",
                to_uid="ku:python-basics",
                relationship_type="PREREQUISITE"
            )
        """
        try:
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{relationship_type}]->(b {{uid: $to_uid}})
            SET r.traversal_count = coalesce(r.traversal_count, 0) + 1,
                r.last_traversed = datetime()
            RETURN r.traversal_count as count
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            f"Relationship not found: {from_uid} --[{relationship_type}]-> {to_uid}"
                        )
                    )

                new_count = record["count"]
                self.logger.debug(
                    f"Incremented traversal count to {new_count} for {from_uid} -> {to_uid}"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to increment traversal count: {e}")
            return Result.fail(
                Errors.database(operation="increment_traversal_count", message=str(e))
            )

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP API (October 26, 2025)
    # ============================================================================
    # Generic relationship methods for pure graph operations.
    # These eliminate the need for denormalized UID lists in domain models.

    def _extract_label_from_uid(self, uid: str) -> str | None:
        """
        Extract label from UID pattern (e.g., 'task:123' → 'Task').

        SKUEL uses consistent UID patterns: {domain}:{id}
        Fast pattern matching, no DB query needed.

        Args:
            uid: Entity UID (e.g., "task:123", "ku.python-basics")

        Returns:
            Label string if pattern matches, None otherwise (requires DB fallback)

        Examples:
            >>> backend._extract_label_from_uid("task:123")
            "Task"
            >>> backend._extract_label_from_uid("ku.python-basics")
            "Entity"
            >>> backend._extract_label_from_uid("unknown:xyz")
            None
        """
        # Common UID patterns in SKUEL
        patterns = {
            "task:": "Task",
            "event:": "Event",
            "habit:": "Habit",
            "goal:": "Goal",
            "principle:": "Principle",
            "choice:": "Choice",
            "ku.": "Entity",  # Knowledge uses dots
            "user.": "User",
            "expense:": "Expense",
        }

        for prefix, label in patterns.items():
            if uid.startswith(prefix):
                return label

        return None  # Fallback to DB query

    def _build_direction_pattern(
        self,
        relationship_type: str,
        direction: Direction,
        source_var: str = "n",
        target_var: str = "related",
        rel_var: str | None = None,
        target_label: str | None = None,
    ) -> Result[str]:
        """
        Build Cypher pattern for directional relationship traversal.

        Consolidates repeated pattern building across:
        - get_related_entities() (with target label)
        - get_related_uids() (with relationship variable)
        - count_related() (with relationship variable)

        Args:
            relationship_type: The relationship type (e.g., "PREREQUISITE", "OWNS")
            direction: Traversal direction ("outgoing", "incoming", or "both")
            source_var: Variable name for source node (default: "n")
            target_var: Variable name for target node (default: "related")
            rel_var: Optional relationship variable name (e.g., "r" for property access)
            target_label: Optional label constraint on target node

        Returns:
            Result[str] containing the Cypher pattern or validation error

        Examples:
            >>> backend._build_direction_pattern("OWNS", "outgoing")
            Result.ok("(n)-[:OWNS]->(related)")

            >>> backend._build_direction_pattern("PREREQUISITE", "incoming", rel_var="r")
            Result.ok("(n)<-[r:PREREQUISITE]-(related)")

            >>> backend._build_direction_pattern("OWNS", "outgoing", target_label="Task")
            Result.ok("(n)-[:OWNS]->(related:Task)")
        """
        # Build relationship part: [r:TYPE] or [:TYPE]
        rel_part = f"[{rel_var}:{relationship_type}]" if rel_var else f"[:{relationship_type}]"

        # Build target part: (related) or (related:Label)
        target_part = f"({target_var}:{target_label})" if target_label else f"({target_var})"

        # Build pattern based on direction
        match direction:
            case "outgoing":
                return Result.ok(f"({source_var})-{rel_part}->{target_part}")
            case "incoming":
                return Result.ok(f"({source_var})<-{rel_part}-{target_part}")
            case "both":
                return Result.ok(f"({source_var})-{rel_part}-{target_part}")
            case _:
                return Result.fail(
                    Errors.validation(
                        message=f"Invalid direction: {direction}. Valid options: outgoing, incoming, both",
                        field="direction",
                        value=direction,
                    )
                )

    async def _get_node_labels(
        self, from_uid: str, to_uid: str
    ) -> Result[tuple[builtins.list[str], builtins.list[str]]]:
        """
        Query database for node labels (single efficient query).

        Gets labels for both source and target nodes in ONE transaction.
        Used for validation when UID pattern matching fails.

        Args:
            from_uid: Source node UID
            to_uid: Target node UID

        Returns:
            Result containing tuple of (source_labels, target_labels)
            Returns error if either node doesn't exist

        Example:
            >>> result = await backend._get_node_labels("task:123", "ku.python")
            >>> source_labels, target_labels = result.value
            >>> print(source_labels)  # ["Task"]
            >>> print(target_labels)  # ["Entity", "Entity"]
        """
        try:
            query = """
            MATCH (a {uid: $from_uid})
            MATCH (b {uid: $to_uid})
            RETURN labels(a) as source_labels, labels(b) as target_labels
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            resource="Node",
                            identifier=f"{from_uid} or {to_uid}",
                        )
                    )

                source_labels = record.get("source_labels", [])
                target_labels = record.get("target_labels", [])

                return Result.ok((source_labels, target_labels))

        except Exception as e:
            self.logger.error(f"Failed to get node labels: {e}")
            return Result.fail(
                Errors.database(
                    operation="get_node_labels",
                    message=str(e),
                    details={"from_uid": from_uid, "to_uid": to_uid},
                )
            )

    async def create_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create or update a graph relationship between two entities.


        - Validates relationship type for source domain (hard failure)
        - Validates target node label matches registry spec (hard failure)
        - Uses UID parsing + DB fallback for label extraction
        - Ensures semantic correctness of graph relationships

        GRAPH-NATIVE: Creates pure Neo4j relationship edges, not node properties.
        This is the foundation for eliminating UID list fields from domain models.

        Uses MERGE to be idempotent - if relationship exists, updates properties.
        This prevents duplicate relationships and allows safe retry logic.

        Args:
            from_uid: Source entity UID (must exist in database)
            to_uid: Target entity UID (must exist in database)
            relationship_type: Neo4j relationship type (e.g., "APPLIES_KNOWLEDGE", "DEPENDS_ON")
                              MUST match RelationshipRegistry for source domain
            properties: Optional relationship properties (metadata). Common properties:
                       - confidence: float (0.0-1.0) - relationship confidence score
                       - strength: float - relationship strength
                       - created_at: datetime - when relationship was created
                       - Any domain-specific metadata

        Returns:
            Result[bool]: Success with True if created/updated
            Result[Error]: Validation failure or database error

        Validation Errors:
            - Invalid relationship type for source domain
            - Invalid target node label (doesn't match registry spec)
            - Source or target node doesn't exist

        Examples:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Valid relationship - passes validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="ku.python-basics",
                relationship_type="APPLIES_KNOWLEDGE",
            )
            # ✅ Task -> Knowledge is valid per registry

            # Invalid relationship - fails validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="habit:exercise",
                relationship_type="APPLIES_KNOWLEDGE",
            )
            # ❌ Error: APPLIES_KNOWLEDGE expects Knowledge target, not Habit
            ```

        Note:
            - Both entities must exist before creating relationship
            - MERGE makes this idempotent (safe to call multiple times)
            - RelationshipRegistry validation is AUTOMATIC (no manual checks needed)
            - For batch operations, use create_relationships_batch() for better performance
            - Relationship properties are optional but recommended for graph analytics

        See Also:
            - delete_relationship(): Remove relationships
            - has_relationship(): Check if relationship exists
            - get_relationship_metadata(): Retrieve relationship properties
            - RelationshipRegistry: Valid relationship types per domain
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        # ========================================================================
        # C: VALIDATION (Hard Failures)
        # ========================================================================

        # Step 1: Extract source label (fast UID parsing first)
        source_label = self._extract_label_from_uid(from_uid)

        # Step 2: Get node labels from database (needed for target validation)
        labels_result = await self._get_node_labels(from_uid, to_uid)
        if labels_result.is_error:
            return Result.fail(labels_result.expect_error())  # Nodes don't exist

        source_labels: builtins.list[str]
        target_labels: builtins.list[str]
        source_labels, target_labels = labels_result.value

        # Use DB label if UID parsing failed
        if not source_label and source_labels:
            source_label = source_labels[0]

        if not source_label:
            return Result.fail(
                Errors.validation(
                    message=f"Unable to determine source label for UID: {from_uid}",
                    field="from_uid",
                    value=from_uid,
                )
            )

        # Step 3: Validate relationship type for source domain
        if not validate_relationship(source_label, relationship_type):
            valid_rels = get_valid_relationships(source_label)
            from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

            return Result.fail(
                ErrorContext(
                    category=ErrorCategory.VALIDATION,
                    code="VALIDATION_FIELD_RELATIONSHIP_TYPE",
                    message=(
                        f"Invalid relationship type '{relationship_type}' for {source_label}. "
                        f"Valid types: {list(valid_rels.keys())}"
                    ),
                    severity=ErrorSeverity.LOW,
                    details={
                        "field": "relationship_type",
                        "value": relationship_type,
                        "source_label": source_label,
                        "source_uid": from_uid,
                        "valid_relationship_types": list(valid_rels.keys()),
                    },
                    user_message=f"Invalid relationship type '{relationship_type}'",
                    source_location=ErrorContext.capture_current_location(),
                )
            )

        # Step 4: Validate target node label
        spec = get_relationship_metadata(source_label, relationship_type)
        if spec and spec.target_labels:
            primary_target_label = target_labels[0] if target_labels else "Unknown"

            # Check if any of the node's labels match the spec
            valid_target = any(label in spec.target_labels for label in target_labels)

            if not valid_target:
                from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

                return Result.fail(
                    ErrorContext(
                        category=ErrorCategory.VALIDATION,
                        code="VALIDATION_FIELD_TARGET_LABEL",
                        message=(
                            f"Invalid target label for relationship: "
                            f"{source_label} --[{relationship_type}]-> {primary_target_label}. "
                            f"Expected target labels: {spec.target_labels}"
                        ),
                        severity=ErrorSeverity.LOW,
                        details={
                            "field": "target_label",
                            "value": primary_target_label,
                            "source_label": source_label,
                            "target_labels": target_labels,
                            "expected_target_labels": spec.target_labels,
                            "relationship_type": relationship_type,
                        },
                        user_message=f"Invalid target type for {relationship_type} relationship",
                        source_location=ErrorContext.capture_current_location(),
                    )
                )

        # Note: Property validation and cardinality constraints were removed in January 2026
        # during the RelationshipRegistry migration. The new registry focuses on
        # essential validation (relationship type + target labels). Add cardinality
        # constraints to UnifiedRelationshipDefinition if needed in the future.

        # ========================================================================
        # RELATIONSHIP CREATION (All Validation Passed)
        # ========================================================================

        try:
            props = properties or {}

            query = f"""
            MATCH (a {{uid: $from_uid}})
            MATCH (b {{uid: $to_uid}})
            MERGE (a)-[r:{relationship_type}]->(b)
            SET r += $properties
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"from_uid": from_uid, "to_uid": to_uid, "properties": props}
                )
                await result.single()

            self.logger.debug(
                f"Created relationship: {from_uid} --[{relationship_type}]-> {to_uid}"
            )
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to create relationship: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_relationship",
                    message=str(e),
                    details={
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": relationship_type,
                    },
                )
            )

    async def delete_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        DETACH DELETE a graph relationship between two entities.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Neo4j relationship type

        Returns:
            Result[bool] indicating success (True even if relationship didn't exist)

        Example:
            await backend.delete_relationship(
                from_uid="task:123",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE
            )
        """
        try:
            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            DETACH DELETE r
            RETURN count(r) as deleted_count
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()
                deleted_count = record["deleted_count"] if record else 0

            self.logger.debug(
                f"Deleted {deleted_count} relationship(s): {from_uid} --[{rel_type}]-> {to_uid}"
            )
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to delete relationship: {e}")
            return Result.fail(Errors.database(operation="delete_relationship", message=str(e)))

    async def delete_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> Result[int]:
        """
        Delete multiple relationships in a single transaction.

        Symmetric with create_relationships_batch() for efficient bulk deletion.
        Idempotent - no error if relationships don't exist.

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            Result[int] with count of relationships deleted

        Example:
            relationships = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = await backend.delete_relationships_batch(relationships)
            print(f"Deleted {result.value} relationships")
        """
        from core.infrastructure.batch import BatchOperationHelper

        try:
            if not relationships:
                return Result.ok(0)

            # Use BatchOperationHelper for query generation
            query_result = BatchOperationHelper.build_relationship_delete_query(relationships)

            async with self.driver.session() as session:
                result = await session.run(query_result.query, query_result.params)
                record = await result.single()
                deleted_count = record["deleted_count"] if record else 0

            self.logger.debug(
                f"Batch deleted {deleted_count} relationships ({len(relationships)} requested)"
            )
            return Result.ok(deleted_count)

        except Exception as e:
            self.logger.error(f"Failed to batch delete relationships: {e}")
            return Result.fail(
                Errors.database(operation="delete_relationships_batch", message=str(e))
            )

    async def has_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        Check if a graph relationship exists between two entities.

        Efficient existence check - returns True/False without loading properties or entities.
        Much faster than get_relationship_metadata() when you only need to check existence.

        Args:
            from_uid: Source entity UID (must exist)
            to_uid: Target entity UID (must exist)
            relationship_type: Neo4j relationship type (exact match, case-sensitive)

        Returns:
            Result[bool]: Success with True if relationship exists, False if not,
                         or Failure if database error

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Check before creating to avoid duplicates
            exists = await backend.has_relationship(
                from_uid="task:123",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            )

            if not exists.value:
                await backend.create_relationship(
                    from_uid="task:123",
                    to_uid="ku:python-basics",
                    relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                )
            ```

        Performance:
            - O(1) lookup using relationship index
            - No property loading (very fast)
            - Use for existence checks before mutations

        Note:
            - Checks exact relationship type (case-sensitive)
            - Direction matters: (from)-[:TYPE]->(to) is different from (to)-[:TYPE]->(from)
            - For bidirectional check, call twice with swapped UIDs
            - Returns False if either entity doesn't exist

        See Also:
            - create_relationship(): Create new relationships
            - get_relationship_metadata(): Get relationship properties
            - count_related(): Count all relationships of a type
        """
        try:
            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            RETURN count(r) > 0 as exists
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()
                exists = record["exists"] if record else False

            return Result.ok(exists)

        except Exception as e:
            self.logger.error(f"Failed to check relationship existence: {e}")
            return Result.fail(Errors.database(operation="has_relationship", message=str(e)))

    async def count_related(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        properties: dict[str, Any] | None = None,
    ) -> Result[int]:
        """
        Count related entities without loading them.

        Efficient for checking relationship counts (e.g., "How many prerequisites?").
        Use this instead of `len(await get_related_uids())` for better performance.

        Args:
            uid: Entity UID
            relationship_type: Neo4j relationship type
            direction: "outgoing", "incoming", or "both"
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[int] with relationship count

        Examples:
            # Count how many knowledge units this task applies
            count_result = await backend.count_related(
                uid="task:123",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                direction="outgoing"
            )
            print(f"Task applies {count_result.value} knowledge units")

            # Count prerequisites
            prereq_count = await backend.count_related(
                uid="ku:advanced-python",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing"
            )

            # Count essential habits (with property filtering)
            essential_count = await backend.count_related(
                uid="goal:fitness",
                relationship_type=RelationshipName.REQUIRES_HABIT,
                direction="outgoing",
                properties={"essentiality": "essential"}
            )
            print(f"Goal has {essential_count.value} essential habits")
        """
        try:
            # Extract string value for Cypher query
            rel_type = relationship_type.value

            # Build Cypher pattern using helper (with named relationship variable for property access)
            pattern_result = self._build_direction_pattern(
                relationship_type=rel_type,
                direction=direction,
                rel_var="r",
            )
            if pattern_result.is_error:
                return Result.fail(pattern_result.expect_error())
            pattern = pattern_result.value

            # Build WHERE clause for property filtering
            where_clauses = []
            params = {"uid": uid}

            if properties:
                for key, value in properties.items():
                    param_name = f"prop_{key}"
                    where_clauses.append(f"r.{key} = ${param_name}")
                    params[param_name] = value

            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
            MATCH (n {{uid: $uid}})
            MATCH {pattern}
            {where_clause}
            RETURN count(related) as count
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()
                count = record["count"] if record else 0

            return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to count related entities: {e}")
            return Result.fail(Errors.database(operation="count_related", message=str(e)))

    async def create_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str, dict[str, Any] | None]]
    ) -> Result[int]:
        """
        Create multiple relationships in a single transaction.


        - Validates ALL relationships BEFORE creating ANY (transaction integrity)
        - Returns detailed errors for invalid relationships
        - Uses efficient batch validation with single DB query

        Efficient batch operation for creating many relationships at once.
        Uses UNWIND for optimal performance.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples

        Returns:
            Result[int] with count of relationships created
            Result[Error] if ANY relationship fails validation (creates NONE)

        Validation:
            - All relationship types must be valid for their source domains
            - All target labels must match registry specs
            - Validates ALL before creating ANY (transaction integrity)

        Example:
            # Create multiple task -> knowledge relationships
            rels = [
                ("task:123", "ku.python-basics", "APPLIES_KNOWLEDGE", {"confidence": 0.9}),
                ("task:123", "ku.functions", "APPLIES_KNOWLEDGE", {"confidence": 0.8}),
                ("task:123", "ku.loops", "APPLIES_KNOWLEDGE", {"confidence": 0.7})
            ]
            result = await backend.create_relationships_batch(rels)
            print(f"Created {result.value} relationships") # All or nothing
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        if not relationships:
            return Result.ok(0)

        # ========================================================================
        # C: BATCH VALIDATION (Validate ALL before creating ANY)
        # ========================================================================

        validation_errors = []

        for idx, (from_uid, to_uid, rel_type, _props) in enumerate(relationships):
            # Step 1: Extract source label (fast UID parsing)
            # Note: _props intentionally unused - property validation not yet implemented
            source_label = self._extract_label_from_uid(from_uid)

            # Step 2: Get node labels from database
            labels_result = await self._get_node_labels(from_uid, to_uid)
            if labels_result.is_error:
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": "Nodes not found",
                        "details": labels_result.expect_error().message,
                    }
                )
                continue

            source_labels: builtins.list[str]
            target_labels: builtins.list[str]
            source_labels, target_labels = labels_result.value

            # Use DB label if UID parsing failed
            if not source_label and source_labels:
                source_label = source_labels[0]

            if not source_label:
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "error": "Unable to determine source label",
                    }
                )
                continue

            # Step 3: Validate relationship type for source domain
            if not validate_relationship(source_label, rel_type):
                valid_rels = get_valid_relationships(source_label)
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": f"Invalid relationship type '{rel_type}' for {source_label}",
                        "valid_types": list(valid_rels.keys()),
                    }
                )
                continue

            # Step 4: Validate target node label
            spec = get_relationship_metadata(source_label, rel_type)
            if spec and spec.target_labels:
                # Check if any of the node's labels match the spec
                valid_target = any(label in spec.target_labels for label in target_labels)

                if not valid_target:
                    primary_target_label = target_labels[0] if target_labels else "Unknown"
                    validation_errors.append(
                        {
                            "index": idx,
                            "from_uid": from_uid,
                            "to_uid": to_uid,
                            "relationship_type": rel_type,
                            "error": (
                                f"Invalid target: {source_label} --[{rel_type}]-> {primary_target_label}"
                            ),
                            "expected_targets": spec.target_labels,
                            "actual_target": primary_target_label,
                        }
                    )
                    continue

        # If ANY validation failed, return errors without creating relationships
        if validation_errors:
            from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

            return Result.fail(
                ErrorContext(
                    category=ErrorCategory.VALIDATION,
                    code="VALIDATION_FIELD_RELATIONSHIPS",
                    message=f"Batch validation failed: {len(validation_errors)} invalid relationships",
                    severity=ErrorSeverity.LOW,
                    details={
                        "field": "relationships",
                        "total_relationships": len(relationships),
                        "validation_errors": validation_errors,
                        "error_count": len(validation_errors),
                    },
                    user_message="Invalid relationships in batch",
                    source_location=ErrorContext.capture_current_location(),
                )
            )

        # ========================================================================
        # BATCH CREATION (All validations passed)
        # ========================================================================
        # Uses BatchOperationHelper for pure Cypher query generation
        from core.infrastructure.batch import BatchOperationHelper

        try:
            # Generate queries grouped by relationship type
            queries = BatchOperationHelper.build_relationship_create_queries(relationships)

            total_created = 0
            async with self.driver.session() as session:
                for query, rels_data in queries:
                    result = await session.run(query, {"rels": rels_data})
                    record = await result.single()
                    total_created += record["created_count"] if record else 0

            self.logger.info(f"Created {total_created} relationships in batch")
            return Result.ok(total_created)

        except Exception as e:
            self.logger.error(f"Failed to create relationships batch: {e}")
            return Result.fail(
                Errors.database(operation="create_relationships_batch", message=str(e))
            )

    # ============================================================================
    # RELATIONSHIP-FIRST API - FLUENT INTERFACE
    # ============================================================================

    def relate(self) -> RelationshipBuilder:
        """
        Create a fluent relationship builder for creating Neo4j relationships.

        This is the relationship-first API - relationships are the primary interface.

        Example:
            await backend.relate() \\
                .from_node(task_uid) \\
                .via("APPLIES_KNOWLEDGE") \\
                .to_node(ku_uid) \\
                .with_metadata(ConfidenceLevel.GOOD, evidence="Applied in task") \\
                .create()

        Returns:
            RelationshipBuilder instance for method chaining
        """
        return RelationshipBuilder(self.driver)

    # Convenience methods for common relationship patterns

    async def get_prerequisites(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all prerequisites for an entity.

        Convenience method for get_related_entities(relationship_type="PREREQUISITE", direction="incoming")
        """
        return await self.get_related_entities(uid, "PREREQUISITE", direction="incoming")

    async def get_enables(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this enables.

        Convenience method for get_related_entities(relationship_type="ENABLES", direction="outgoing")
        """
        return await self.get_related_entities(uid, "ENABLES", direction="outgoing")

    async def get_related(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all related entities (bidirectional).

        Convenience method for get_related_entities(relationship_type="RELATED_TO", direction="both")
        """
        return await self.get_related_entities(uid, "RELATED_TO", direction="both")

    async def get_children(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all child entities.

        Convenience method for get_related_entities(relationship_type="CHILD_OF", direction="incoming")
        """
        return await self.get_related_entities(uid, "CHILD_OF", direction="incoming")

    async def get_parent(self, uid: str) -> Result[T | None]:
        """
        Get parent entity.

        Convenience method for get_related_entities(relationship_type="CHILD_OF", direction="outgoing", limit=1)
        """
        result = await self.get_related_entities(uid, "CHILD_OF", direction="outgoing", limit=1)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = result.value
        return Result.ok(entities[0] if entities else None)

    async def get_depends_on(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this depends on.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(uid, "DEPENDS_ON", direction="outgoing")

    async def get_blocks(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this blocks.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(uid, "BLOCKS", direction="outgoing")
