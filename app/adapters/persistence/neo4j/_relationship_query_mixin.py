"""
Relationship Query Mixin
========================

Graph-native relationship query methods, rich edge metadata,
and fluent/convenience relationship API.

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
    relate: Fluent RelationshipBuilder API
    get_prerequisites, get_enables, get_related, get_children, get_parent,
    get_depends_on, get_blocks: Convenience wrappers

Requires on concrete class:
    driver, logger, label, entity_class, default_filters,
    _default_filter_clause, _default_filter_params,
    _build_direction_pattern (provided by _RelationshipCrudMixin via MRO)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.relationship_builders import RelationshipBuilder
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import FilterParams
from core.utils.error_boundary import safe_backend_operation
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from core.models.semantic import EdgeMetadata
    from core.ports.base_protocols import Direction, RelationshipMetadata


class _RelationshipQueryMixin[T: DomainModelProtocol]:
    """
    Relationship query methods — reads, edge metadata, fluent API, convenience wrappers.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        label: str
        entity_class: type[T]
        default_filters: FilterParams
        _default_filter_clause: method
        _default_filter_params: method
        _build_direction_pattern: provided by _RelationshipCrudMixin via MRO
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: logging.Logger
        label: str
        entity_class: type[T]
        default_filters: FilterParams

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> FilterParams: ...

        def _build_direction_pattern(
            self,
            relationship_type: str,
            direction: Direction,
            source_var: str = "n",
            target_var: str = "related",
            rel_var: str | None = None,
            target_label: str | None = None,
        ) -> Result[str]: ...

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP QUERIES
    # ============================================================================
    # Added: October 6, 2025
    # See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
    #
    # These methods query relationships from graph edges, not node properties.
    # This enables removing relationship fields from domain models.

    @safe_backend_operation("get_related_entities")
    async def get_related_entities(
        self,
        uid: str,
        relationship_type: RelationshipName | str,
        direction: str = "outgoing",
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """
        Get related entities via graph edges.

        Args:
            uid: Source entity UID,
            relationship_type: Neo4j relationship type (enum preferred, str validated),
            direction: Traversal direction - "outgoing", "incoming", or "both",
            limit: Max results to return

        Returns:
            Result[List[T]] of related entities

        Example:
            # Get all prerequisites for a knowledge unit
            result = await backend.get_related_entities(
                uid="ku:python-basics",
                relationship_type=RelationshipName.REQUIRES_PREREQUISITE,
                direction="incoming"
            )
        """
        # Extract string value — _build_direction_pattern validates it
        rel_type = (
            relationship_type.value
            if isinstance(relationship_type, RelationshipName)
            else relationship_type
        )

        # Build Cypher pattern using helper
        pattern_result = self._build_direction_pattern(
            relationship_type=rel_type,
            direction=direction,
            target_label=self.label,
        )
        if pattern_result.is_error:
            return Result.fail(pattern_result)
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

    @safe_backend_operation("get_related_uids")
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
        # Extract string value for Cypher query
        rel_type = relationship_type.value

        # Build Cypher pattern using helper (with named relationship variable for property access)
        pattern_result = self._build_direction_pattern(
            relationship_type=rel_type,
            direction=direction,
            rel_var="r",
        )
        if pattern_result.is_error:
            return Result.fail(pattern_result)
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

    @safe_backend_operation("get_relationship_metadata")
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

    @safe_backend_operation("update_relationship_properties")
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

    @safe_backend_operation("get_relationships_batch")
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
        from core.infrastructure.batch import BatchCypherBuilder

        if not relationships:
            return Result.ok([])

        # Use BatchCypherBuilder for query generation
        query_result = BatchCypherBuilder.build_relationship_properties_query(relationships)

        async with self.driver.session() as session:
            result = await session.run(query_result.query, query_result.params)
            records = [record async for record in result]

            # Convert to list of dicts (empty dict if None)
            metadata_list = [dict(record["props"]) if record["props"] else {} for record in records]

            self.logger.debug(
                f"Fetched metadata for {len(metadata_list)} relationships ({len(relationships)} requested)"
            )
            return Result.ok(metadata_list)

    @safe_backend_operation("count_relationships_batch")
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
        from core.infrastructure.batch import BatchCypherBuilder

        if not requests:
            return Result.ok({})

        counts: dict[tuple[str, str, str], int] = {}

        # Use BatchCypherBuilder to generate optimized queries by direction
        query_results = BatchCypherBuilder.build_multi_direction_count_queries(requests)

        async with self.driver.session() as session:
            # Execute each direction's query
            for direction, query_result in query_results.items():
                result = await session.run(query_result.query, query_result.params)
                async for record in result:
                    counts[(record["uid"], record["rel_type"], direction)] = record["count"]

            # Fill in zeros for requests that had no results
            for uid, rel_type, req_direction in requests:
                resolved_direction: str = req_direction if req_direction is not None else "outgoing"
                key = (uid, rel_type, resolved_direction)
                if key not in counts:
                    counts[key] = 0

            self.logger.debug(f"Batch counted {len(counts)} relationship patterns")
            return Result.ok(counts)

    # ============================================================================
    # RICH EDGE PROPERTIES
    # ============================================================================
    # Added: October 6, 2025
    # See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
    #
    # These methods provide typed access to rich edge metadata.

    @safe_backend_operation("get_edge_metadata")
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

        props_result = await self.get_relationship_metadata(from_uid, to_uid, relationship_type)

        if not props_result.is_ok:
            return Result.fail(props_result)

        if props_result.value is None:
            return Result.ok(None)

        # Convert dict to EdgeMetadata
        metadata = EdgeMetadata.from_neo4j_properties(props_result.value)
        return Result.ok(metadata)

    @safe_backend_operation("update_edge_metadata")
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

    @safe_backend_operation("increment_traversal_count")
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

    # ============================================================================
    # ORDERED RELATIONSHIP QUERIES
    # ============================================================================
    # Used by UnifiedRelationshipService's OrderedRelationshipsMixin.
    # Config-driven: entity_label, relationship type, direction, ordering
    # come from DomainRelationshipConfig specs.

    @safe_backend_operation("get_ordered_related_uids")
    async def get_ordered_related_uids(
        self,
        entity_label: str,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        order_by_property: str | None = None,
        order_direction: str = "ASC",
    ) -> Result[builtins.list[str]]:
        """
        Get related entity UIDs ordered by an edge property.

        Args:
            entity_label: Label of the source entity node
            entity_uid: UID of the source entity
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            order_by_property: Edge property to order by (None = unordered)
            order_direction: "ASC" or "DESC"

        Returns:
            Result[list[str]] of related UIDs in order
        """
        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        order_clause = ""
        if order_by_property:
            order_clause = f"ORDER BY r.{order_by_property} {order_direction}"

        query = f"""
        MATCH (e:{entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"entity_uid": entity_uid, "relationship_type": relationship_type},
            )
            records = [dict(record) async for record in result]

        return Result.ok([str(r["uid"]) for r in records if r.get("uid")])

    @safe_backend_operation("get_related_with_metadata")
    async def get_related_with_metadata(
        self,
        entity_label: str,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        edge_properties: builtins.list[str] | None = None,
        order_by_property: str | None = None,
        order_direction: str = "ASC",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get related entities WITH edge property metadata.

        Args:
            entity_label: Label of the source entity node
            entity_uid: UID of the source entity
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            edge_properties: Specific edge properties to return (None = all)
            order_by_property: Edge property to order by (None = unordered)
            order_direction: "ASC" or "DESC"

        Returns:
            Result[list[dict]] with structure:
            [{"uid": "ps:1", "title": "...", "edge": {"sequence": 0, ...}}, ...]
        """
        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        if edge_properties:
            edge_props_clause = ", ".join(f"{p}: r.{p}" for p in edge_properties)
            edge_return = f"{{{edge_props_clause}}}"
        else:
            edge_return = "properties(r)"

        order_clause = ""
        if order_by_property:
            order_clause = f"ORDER BY r.{order_by_property} {order_direction}"

        query = f"""
        MATCH (e:{entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid,
               related.title AS title,
               {edge_return} AS edge
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"entity_uid": entity_uid, "relationship_type": relationship_type},
            )
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": r.get("title"),
                    "edge": dict(r.get("edge", {})) if r.get("edge") else {},
                }
                for r in records
                if r.get("uid")
            ]
        )

    @safe_backend_operation("reorder_relationships")
    async def reorder_relationships(
        self,
        entity_label: str,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        target_uid_sequence: builtins.list[str],
        sequence_property: str = "sequence",
    ) -> Result[int]:
        """
        Reorder relationships by updating edge sequence properties.

        Args:
            entity_label: Label of the source entity node
            entity_uid: Source entity UID
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            target_uid_sequence: List of target UIDs in desired order
            sequence_property: Edge property name for sequence (default: "sequence")

        Returns:
            Result[int] with count of relationships updated
        """
        if not target_uid_sequence:
            return Result.ok(0)

        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        ordering_data = [{"uid": uid, "seq": idx} for idx, uid in enumerate(target_uid_sequence)]

        query = f"""
        UNWIND $ordering AS item
        MATCH (e:{entity_label} {{uid: $entity_uid}}){direction_clause}(target {{uid: item.uid}})
        WHERE type(r) = $relationship_type
        SET r.{sequence_property} = item.seq
        RETURN count(*) AS updated_count
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "entity_uid": entity_uid,
                    "ordering": ordering_data,
                    "relationship_type": relationship_type,
                },
            )
            records = [dict(record) async for record in result]

        updated = sum(r.get("updated_count", 0) for r in records)
        return Result.ok(updated)

    @safe_backend_operation("create_relationship_with_properties")
    async def create_relationship_with_properties(
        self,
        entity_uid: str,
        target_uid: str,
        relationship_type: str,
        direction: str,
        edge_properties: dict[str, Any],
    ) -> Result[bool]:
        """
        Create a relationship with specific edge properties.

        Args:
            entity_uid: Source entity UID
            target_uid: Target entity UID
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            edge_properties: Properties to set on the relationship edge

        Returns:
            Result[bool] indicating success
        """
        if direction == "outgoing":
            merge_clause = f"MERGE (from)-[r:{relationship_type}]->(to)"
        elif direction == "incoming":
            merge_clause = f"MERGE (from)<-[r:{relationship_type}]-(to)"
        else:
            merge_clause = f"MERGE (from)-[r:{relationship_type}]-(to)"

        query = f"""
        MATCH (from {{uid: $from_uid}})
        MATCH (to {{uid: $to_uid}})
        {merge_clause}
        SET r += $properties
        RETURN r IS NOT NULL AS success
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "from_uid": entity_uid,
                    "to_uid": target_uid,
                    "properties": edge_properties,
                },
            )
            record = await result.single()

        success = record["success"] if record else False
        return Result.ok(success)

    @safe_backend_operation("get_hierarchical_children_single")
    async def get_hierarchical_children_single(
        self,
        entity_label: str,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        target_label: str,
        order_by_property: str | None = None,
        order_direction: str = "ASC",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Single-level hierarchical traversal returning children with edge metadata.

        Args:
            entity_label: Label of the source entity node
            entity_uid: Root entity UID
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            target_label: Label of the target nodes
            order_by_property: Edge property to order by (None = unordered)
            order_direction: "ASC" or "DESC"

        Returns:
            Result[list[dict]] with structure:
            [{"uid": "...", "title": "...", "edge": {...}, "children": []}, ...]
        """
        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        order_clause = ""
        if order_by_property:
            order_clause = f"ORDER BY r.{order_by_property} {order_direction}"

        query = f"""
        MATCH (root:{entity_label} {{uid: $entity_uid}}){direction_clause}(child:{target_label})
        WHERE type(r) = $rel_type
        RETURN child.uid AS uid,
               child.title AS title,
               properties(r) AS edge
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"entity_uid": entity_uid, "rel_type": relationship_type}
            )
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": r.get("title"),
                    "edge": dict(r.get("edge", {})) if r.get("edge") else {},
                    "children": [],
                }
                for r in records
                if r.get("uid")
            ]
        )

    @safe_backend_operation("get_hierarchical_children_two_level")
    async def get_hierarchical_children_two_level(
        self,
        entity_label: str,
        entity_uid: str,
        rel_type1: str,
        dir1: str,
        target_label1: str,
        rel_type2: str,
        dir2: str,
        target_label2: str,
        order_by_property1: str | None = None,
        order_direction1: str = "ASC",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Two-level hierarchical traversal (e.g., LP -> PS -> KU).

        Args:
            entity_label: Label of the root entity node
            entity_uid: Root entity UID
            rel_type1: First relationship type
            dir1: First direction ("outgoing", "incoming", "both")
            target_label1: Label of first-level targets
            rel_type2: Second relationship type
            dir2: Second direction
            target_label2: Label of second-level targets
            order_by_property1: Edge property to order first level
            order_direction1: Order direction for first level

        Returns:
            Result[list[dict]] with nested children structure
        """
        dir1_clause = "-[r1]->" if dir1 == "outgoing" else "<-[r1]-"
        dir2_clause = "-[r2]->" if dir2 == "outgoing" else "<-[r2]-"

        order1 = f"r1.{order_by_property1}" if order_by_property1 else "n1.uid"

        query = f"""
        MATCH (root:{entity_label} {{uid: $entity_uid}}){dir1_clause}(n1:{target_label1})
        WHERE type(r1) = $rel_type1
        OPTIONAL MATCH (n1){dir2_clause}(n2:{target_label2})
        WHERE type(r2) = $rel_type2
        WITH n1, r1, collect({{uid: n2.uid, title: n2.title, edge: properties(r2)}}) AS children
        RETURN n1.uid AS uid,
               n1.title AS title,
               properties(r1) AS edge,
               children
        ORDER BY {order1} {order_direction1}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "entity_uid": entity_uid,
                    "rel_type1": rel_type1,
                    "rel_type2": rel_type2,
                },
            )
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": r.get("title"),
                    "edge": dict(r.get("edge", {})) if r.get("edge") else {},
                    "children": [
                        {
                            "uid": str(c["uid"]) if c.get("uid") else None,
                            "title": c.get("title"),
                            "edge": dict(c.get("edge", {})) if c.get("edge") else {},
                        }
                        for c in (r.get("children") or [])
                        if c.get("uid")
                    ],
                }
                for r in records
                if r.get("uid")
            ]
        )

    @safe_backend_operation("get_hierarchical_children_deep")
    async def get_hierarchical_children_deep(
        self,
        entity_label: str,  # noqa: ARG002 — kept for API consistency with sibling methods
        entity_uid: str,
        match_pattern: str,
        rel_type_params: dict[str, str],
        return_parts: builtins.list[str],
        order_expression: str | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Multi-level (3+) hierarchical traversal with dynamic query construction.

        Args:
            entity_label: Label of the root entity node (unused — embedded in match_pattern)
            entity_uid: Root entity UID
            match_pattern: Pre-built MATCH pattern string
            rel_type_params: Parameter dict mapping rel_type0/1/... to relationship type strings
            return_parts: List of RETURN clause expressions
            order_expression: Optional ORDER BY expression

        Returns:
            Result[list[dict]] with flat results keyed by uid0, title0, edge0
        """
        where_clauses = " AND ".join(
            f"type(r{idx}) = $rel_type{idx}" for idx in range(len(rel_type_params))
        )
        order_clause = f"ORDER BY {order_expression}" if order_expression else ""

        query = f"""
        MATCH {match_pattern}
        WHERE {where_clauses}
        WITH *, {return_parts[0]} AS uid0
        RETURN {", ".join(return_parts)}
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"entity_uid": entity_uid, **rel_type_params})
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r.get("uid0", "")),
                    "title": r.get("title0"),
                    "edge": dict(r.get("edge0", {})) if r.get("edge0") else {},
                    "children": [],
                }
                for r in records
                if r.get("uid0")
            ]
        )

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

        Convenience method for get_related_entities(relationship_type=RELATED_TO, direction="both")
        """
        return await self.get_related_entities(uid, RelationshipName.RELATED_TO, direction="both")

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
            return Result.fail(result)

        entities = result.value
        return Result.ok(entities[0] if entities else None)

    async def get_depends_on(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this depends on.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(
            uid, RelationshipName.DEPENDS_ON, direction="outgoing"
        )

    async def get_blocks(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this blocks.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(uid, RelationshipName.BLOCKS, direction="outgoing")
