"""
Neo4j Schema Service
===================

Service for introspecting Neo4j database schema and providing
cached schema context for query optimization and validation.

Follows SKUEL principles:
- Clean error messages instead of graceful degradation
- Schema-aware query building
- Cached results for performance
"""

__version__ = "1.0"


import hashlib
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from core.infrastructure.database.schema import (
    Neo4jConstraint,
    Neo4jIndex,
    NodeLabelInfo,
    RelationshipTypeInfo,
    SchemaContext,
)
from core.models.query.schema_ddl import (
    build_create_constraint_ddl,
    build_create_index_ddl,
    build_drop_constraint_ddl,
    build_drop_index_ddl,
)

# Import protocol interface
from core.services.protocols.infrastructure_protocols import SchemaOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


class Neo4jSchemaService:
    """
    Service for Neo4j schema introspection and caching.

    Provides live schema information for query optimization,
    validation, and intelligent query building.


    Source Tag: "schema_service_explicit"
    - Format: "schema_service_explicit" for user-created relationships
    - Format: "schema_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from schema metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture (Pure Cypher by Default):
    - Uses Pure Cypher for ALL schema introspection (use_apoc=False default)
    - Uses native Neo4j procedures (db.labels(), db.relationshipTypes(), etc.)
    - APOC support available via use_apoc=True for enhanced metadata (optional)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    - Maximum portability across Neo4j Desktop, Aura, and Docker

    """

    def __init__(
        self, neo4j_adapter: SchemaOperations, cache_ttl_minutes: int = 30, use_apoc: bool = False
    ) -> None:
        """
        Initialize schema service with Neo4j adapter.

        Args:
            neo4j_adapter: Schema operations (protocol-based)
            cache_ttl_minutes: How long to cache schema before refresh
            use_apoc: Whether to use APOC for optimized schema introspection (default: False for portability)
        """
        if not neo4j_adapter:
            raise ValueError("Schema operations adapter is required")
        self.neo4j_adapter = neo4j_adapter
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.use_apoc = use_apoc
        self.logger = get_logger("skuel.schema.service")

        # Cache management
        self._cached_schema: SchemaContext | None = None
        self._last_introspection: datetime | None = None
        self._apoc_available: bool | None = None  # Cache APOC availability check

    @with_error_handling("get_schema_context", error_type="database")
    async def get_schema_context(self, force_refresh: bool = False) -> Result[SchemaContext]:
        """
        Get current schema context, using cache if available.

        Args:
            force_refresh: Force new introspection even if cache is valid

        Returns:
            Result[SchemaContext] with complete schema information
        """
        # Check if cache is valid
        if not force_refresh and self._is_cache_valid():
            self.logger.debug("Using cached schema context")
            # Type safety: _is_cache_valid ensures _cached_schema is not None
            assert self._cached_schema is not None
            return Result.ok(self._cached_schema)

        # Perform fresh introspection
        self.logger.info("🔍 Performing Neo4j schema introspection")
        introspection_result = await self._introspect_schema()

        if introspection_result.is_error:
            return introspection_result

        schema_context = introspection_result.value

        # Update cache
        self._cached_schema = schema_context
        self._last_introspection = datetime.now()

        self.logger.info(
            "✅ Schema introspection completed",
            node_labels=len(schema_context.node_labels),
            relationship_types=len(schema_context.relationship_types),
            indexes=len(schema_context.indexes),
            constraints=len(schema_context.constraints),
        )

        return Result.ok(schema_context)

    def _is_cache_valid(self) -> bool:
        """Check if current cache is still valid"""
        if not self._cached_schema or not self._last_introspection:
            return False

        age = datetime.now() - self._last_introspection
        return age < self.cache_ttl

    @with_error_handling("_introspect_schema", error_type="database")
    async def _introspect_schema(self) -> Result[SchemaContext]:
        """
        Perform comprehensive Neo4j schema introspection.

        Returns:
            Result[SchemaContext] with all schema information
        """
        # Collect all schema information in parallel queries
        node_labels_result = await self._get_node_labels()
        if node_labels_result.is_error:
            return Result.fail(node_labels_result)

        relationship_types_result = await self._get_relationship_types()
        if relationship_types_result.is_error:
            return Result.fail(relationship_types_result)

        indexes_result = await self._get_indexes()
        if indexes_result.is_error:
            return Result.fail(indexes_result)

        constraints_result = await self._get_constraints()
        if constraints_result.is_error:
            return Result.fail(constraints_result)

        # Get detailed information for each label and relationship type
        node_label_info: dict[str, NodeLabelInfo] = {}
        for label in node_labels_result.value:
            node_info_result = await self._get_node_label_info(label)
            if node_info_result.is_ok:
                node_label_info[label] = node_info_result.value

        relationship_type_info: dict[str, RelationshipTypeInfo] = {}
        for rel_type in relationship_types_result.value:
            rel_info_result = await self._get_relationship_type_info(rel_type)
            if rel_info_result.is_ok:
                relationship_type_info[rel_type] = rel_info_result.value

        # Build property mappings
        all_properties: set[str] = (set(),)
        indexed_properties: dict[str, list[Neo4jIndex]] = {}
        unique_properties: dict[str, list[Neo4jConstraint]] = {}

        # Collect properties from node labels
        for info in node_label_info.values():
            all_properties.update(info.properties)

        # Map indexes to properties
        for index in indexes_result.value:
            for prop in index.properties:
                if prop not in indexed_properties:
                    indexed_properties[prop] = []
                indexed_properties[prop].append(index)
                all_properties.add(prop)

        # Map constraints to properties
        for constraint in constraints_result.value:
            for prop in constraint.properties:
                if constraint.type == "UNIQUE":
                    if prop not in unique_properties:
                        unique_properties[prop] = []
                    unique_properties[prop].append(constraint)
                all_properties.add(prop)

        # Create schema hash for change detection
        schema_data = {
            "node_labels": sorted(node_labels_result.value),
            "relationship_types": sorted(relationship_types_result.value),
            "indexes": [f"{idx.name}:{idx.type}" for idx in indexes_result.value],
            "constraints": [f"{c.name}:{c.type}" for c in constraints_result.value],
        }
        schema_hash = hashlib.md5(str(schema_data).encode()).hexdigest()

        # Build complete schema context
        schema_context = SchemaContext(
            node_labels=node_labels_result.value,
            relationship_types=relationship_types_result.value,
            indexes=indexes_result.value,
            constraints=constraints_result.value,
            node_label_info=node_label_info,
            relationship_type_info=relationship_type_info,
            property_names=all_properties,
            indexed_properties=indexed_properties,
            unique_properties=unique_properties,
            introspection_timestamp=datetime.now(),
            schema_hash=schema_hash,
        )

        return Result.ok(schema_context)

    @with_error_handling("_get_node_labels", error_type="database")
    async def _get_node_labels(self) -> Result[list[str]]:
        """Get all node labels in the database"""
        # Use native db.labels() - works on all Neo4j deployments
        query = "CALL db.labels() YIELD label RETURN collect(label) as labels"
        result = await self.neo4j_adapter.execute_query(query)

        if not result:
            return Result.ok([])

        # Neo4j returns Record objects, need to access by key
        labels = result[0]["labels"] if result[0]["labels"] else []
        return Result.ok(labels)

    @with_error_handling("_get_relationship_types", error_type="database")
    async def _get_relationship_types(self) -> Result[list[str]]:
        """Get all relationship types in the database"""
        # Use native db.relationshipTypes() - works on all Neo4j deployments
        query = "CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) as types"
        result = await self.neo4j_adapter.execute_query(query)

        if not result:
            return Result.ok([])

        types = result[0]["types"] if result[0]["types"] else []
        return Result.ok(types)

    @with_error_handling("_get_indexes", error_type="database")
    async def _get_indexes(self) -> Result[list[Neo4jIndex]]:
        """Get all indexes in the database"""
        query = """
        SHOW INDEXES
        YIELD name, type, entityType, labelsOrTypes, properties, state
        RETURN name, type, entityType, labelsOrTypes, properties, state
        """
        result = await self.neo4j_adapter.execute_query(query)

        indexes = []
        for record in result:
            # Neo4j Record objects support dictionary-like access
            index = Neo4jIndex(
                name=record["name"] or "",
                type=record["type"] or "",
                entity_type=record["entityType"] or "",
                labels=record["labelsOrTypes"] or [],
                properties=record["properties"] or [],
                state=record["state"] or "",
            )
            indexes.append(index)

        return Result.ok(indexes)

    @with_error_handling("_get_constraints", error_type="database")
    async def _get_constraints(self) -> Result[list[Neo4jConstraint]]:
        """Get all constraints in the database"""
        query = """
        SHOW CONSTRAINTS
        YIELD name, type, entityType, labelsOrTypes, properties
        RETURN name, type, entityType, labelsOrTypes, properties
        """
        result = await self.neo4j_adapter.execute_query(query)

        constraints = []
        for record in result:
            constraint = Neo4jConstraint(
                name=record["name"] or "",
                type=record["type"] or "",
                entity_type=record["entityType"] or "",
                labels=record["labelsOrTypes"] or [],
                properties=record["properties"] or [],
            )
            constraints.append(constraint)

        return Result.ok(constraints)

    @with_error_handling("_get_node_label_info", error_type="database", uid_param="label")
    async def _get_node_label_info(self, label: str) -> Result[NodeLabelInfo]:
        """Get detailed information about a specific node label"""
        # Use pure Cypher - works on all Neo4j deployments
        query = f"""
        MATCH (n:`{label}`)
        WITH count(n) as count, collect(keys(n))[0..100] as sample_keys, n
        LIMIT 100
        RETURN count,
               reduce(props = [], keys_list IN sample_keys | props + keys_list) as all_props,
               collect(properties(n))[0] as sample_props
        """
        result = await self.neo4j_adapter.execute_query(query)

        if not result:
            return Result.ok(
                NodeLabelInfo(label=label, count=0, properties=set(), sample_properties={})
            )

        record = result[0]
        # Handle potentially nested lists in all_props
        all_props_raw = record["all_props"] if record["all_props"] else []
        # Flatten the list in case it contains nested lists
        all_props = []
        for item in all_props_raw:
            if isinstance(item, list):
                all_props.extend(item)
            else:
                all_props.append(item)
        properties = set(all_props)
        sample_properties = record["sample_props"] or {}
        count = record["count"] if record["count"] else 0

        info = NodeLabelInfo(
            label=label, count=count, properties=properties, sample_properties=sample_properties
        )

        return Result.ok(info)

    @with_error_handling("_get_relationship_type_info", error_type="database", uid_param="rel_type")
    async def _get_relationship_type_info(self, rel_type: str) -> Result[RelationshipTypeInfo]:
        """Get detailed information about a specific relationship type"""
        query = f"""
        MATCH ()-[r:`{rel_type}`]-()
        WITH count(r) as count, collect(keys(r))[0..100] as sample_keys, r
        LIMIT 100
        RETURN count,
               reduce(props = [], keys_list IN sample_keys | props + keys_list) as all_props,
               collect(properties(r))[0] as sample_props
        """
        result = await self.neo4j_adapter.execute_query(query)

        if not result:
            return Result.ok(
                RelationshipTypeInfo(type=rel_type, count=0, properties=set(), sample_properties={})
            )

        record = result[0]
        # Handle potentially nested lists in all_props
        all_props_raw = record["all_props"] if record["all_props"] else []
        # Flatten the list in case it contains nested lists
        all_props = []
        for item in all_props_raw:
            if isinstance(item, list):
                all_props.extend(item)
            else:
                all_props.append(item)
        properties = set(all_props)
        sample_properties = record["sample_props"] or {}
        count = record["count"] if record["count"] else 0

        info = RelationshipTypeInfo(
            type=rel_type,
            count=count,
            properties=properties,
            sample_properties=sample_properties,
        )

        return Result.ok(info)

    async def _check_apoc_available(self) -> bool:
        """
        Check if APOC procedures are available in the database.

        Returns:
            bool - True if APOC is available, False otherwise
        """
        if self._apoc_available is not None:
            return self._apoc_available

        if not self.use_apoc:
            self._apoc_available = False
            return False

        try:
            # Check if APOC is installed by calling a simple APOC function
            query = "CALL apoc.version() YIELD version RETURN version"
            result = await self.neo4j_adapter.execute_query(query)
            self._apoc_available = bool(result)
            if self._apoc_available:
                self.logger.info(
                    f"APOC available: {result[0]['version'] if result else 'unknown version'}"
                )
            return self._apoc_available
        except Exception as e:
            self._apoc_available = False
            self.logger.debug(
                f"APOC not available ({e.__class__.__name__}), using standard queries"
            )
            return False

    @with_error_handling("get_schema_stats", error_type="database")
    async def get_schema_stats(self) -> Result[dict[str, Any]]:
        """
        Get schema statistics using pure Cypher.

        Returns:
            Result[dict] with schema statistics
        """
        # Get counts for each label using pure Cypher
        labels_result = await self._get_node_labels()
        if labels_result.is_error:
            return Result.fail(labels_result.expect_error())

        stats: dict[str, Any] = {"labels": {}, "relationshipTypes": {}}

        # Count nodes per label
        for label in labels_result.value:
            count_query = f"MATCH (n:`{label}`) RETURN count(n) as count"
            result = await self.neo4j_adapter.execute_query(count_query)
            if result:
                stats["labels"][label] = result[0]["count"]

        # Get relationship type counts
        rel_types_result = await self._get_relationship_types()
        if rel_types_result.is_error:
            return Result.fail(rel_types_result.expect_error())

        for rel_type in rel_types_result.value:
            count_query = f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) as count"
            result = await self.neo4j_adapter.execute_query(count_query)
            if result:
                stats["relationshipTypes"][rel_type] = result[0]["count"]

        return Result.ok(stats)

    @with_error_handling("generate_schema_migration", error_type="database")
    async def generate_schema_migration(self, target_schema: SchemaContext) -> Result[list[str]]:
        """
        Generate Pure Cypher DDL migration queries to transform current schema to target.

        Uses native Neo4j DDL - no APOC dependency required.

        Args:
            target_schema: The desired schema state

        Returns:
            Result[list[str]] - List of Pure Cypher DDL queries for migration
        """
        current_result = await self.get_schema_context()
        if current_result.is_error:
            return Result.fail(current_result)

        current = current_result.value
        queries = []

        # Generate index creation using Pure Cypher DDL
        for index in target_schema.indexes:
            if index not in current.indexes:
                # Create index using native Neo4j DDL
                query = build_create_index_ddl(
                    name=index.name,
                    labels=index.labels,
                    properties=index.properties,
                    index_type=index.type,
                )
                queries.append(query)

        # Generate constraint creation using Pure Cypher DDL
        for constraint in target_schema.constraints:
            if constraint not in current.constraints:
                query = build_create_constraint_ddl(
                    name=constraint.name,
                    labels=constraint.labels,
                    properties=constraint.properties,
                    constraint_type=constraint.type,
                )
                queries.append(query)

        # Remove indexes not in target
        queries.extend(
            [
                build_drop_index_ddl(index.name)
                for index in current.indexes
                if index not in target_schema.indexes
            ]
        )

        # Remove constraints not in target
        queries.extend(
            [
                build_drop_constraint_ddl(constraint.name)
                for constraint in current.constraints
                if constraint not in target_schema.constraints
            ]
        )

        return Result.ok(queries)

    async def invalidate_cache(self) -> Result[None]:
        """Force cache invalidation on next schema access"""
        self._cached_schema = None
        self._last_introspection = None
        self._apoc_available = None  # Reset APOC availability check
        self.logger.info("Schema cache invalidated")
        return Result.ok(None)

    async def has_schema_changed(self) -> Result[bool]:
        """
        Check if schema has changed since last introspection.

        Returns:
            Result[bool] - True if schema changed, False otherwise
        """
        if not self._cached_schema:
            return Result.ok(True)  # No cached schema = changed

        fresh_result = await self._introspect_schema()
        if fresh_result.is_error:
            return Result.fail(fresh_result)

        fresh_schema = fresh_result.value
        changed = fresh_schema.schema_hash != self._cached_schema.schema_hash

        return Result.ok(changed)

    @with_error_handling("get_comprehensive_schema", error_type="database")
    async def get_comprehensive_schema(self) -> Result[dict[str, Any]]:
        """
        Get complete schema information using pure Cypher.

        Returns:
            Result[dict] with comprehensive schema information
        """
        # Get schema context
        context_result = await self.get_schema_context()
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        # Get stats
        stats_result = await self.get_schema_stats()
        stats = stats_result.value if stats_result.is_ok else {}

        # Build comprehensive schema
        schema_data = asdict(context_result.value)
        schema_data["statistics"] = stats

        return Result.ok(schema_data)
