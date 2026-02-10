"""
Neo4j Repository Adapter
========================

Implements the repository port for Neo4j.
This can be swapped for any other graph database.
"""

__version__ = "1.0"


import logging
from datetime import datetime
from typing import Any

from adapters.persistence.neo4j.neo4j_connection import get_connection

# Protocols
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# No longer using GraphRepositoryPort - Neo4jAdapter is a standalone concrete class

logger = logging.getLogger(__name__)

try:
    from neo4j import Record  # noqa: F401 - imported for availability check

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.warning("Neo4j driver not available")


class Neo4jSessionContext:
    """Async context manager for Neo4j sessions with proper resource cleanup"""

    def __init__(self, driver: Any) -> None:
        self.driver = driver
        self.session = None

    async def __aenter__(self) -> Any:
        """Create and return a Neo4j session"""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        self.session = self.driver.session()
        return self.session

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the session with proper cleanup"""
        if self.session:
            await self.session.close()
            self.session = None

        if exc_type:
            logger.error(f"Neo4j session context exit with exception: {exc_val}")


class Neo4jAdapter:
    """
    Neo4j adapter for graph database operations.
    Standalone implementation without legacy port inheritance.
    """

    def __init__(
        self, _uri: str | None = None, _user: str | None = None, _password: str | None = None
    ) -> None:
        # Use Neo4jConnection for consistency
        self.connection: Any = None
        self.driver: Any = None  # Will be set from connection
        self._schema_service: Any = None
        self._query_validator: Any = None
        self._enhanced_templates: Any = None
        # Initialize logger
        from core.utils.logging import get_logger

        self.logger = get_logger("neo4j_adapter")

    async def connect(self) -> None:
        """Establish connection to Neo4j using Neo4jConnection"""
        if not NEO4J_AVAILABLE:
            raise RuntimeError("Neo4j driver not installed. Please install with: pip install neo4j")

        # Get the singleton connection
        self.connection = await get_connection()
        self.driver = self.connection.driver

        # Test connection
        connected = await self.connection.test_connection()
        if not connected:
            raise RuntimeError("Failed to connect to Neo4j")
        logger.info(f"Connected to Neo4j at {self.connection.uri}")

    def get_driver(self) -> Any:
        """Get the Neo4j driver instance"""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized. Call connect() first.")
        return self.driver

    def get_schema_service(self) -> Any:
        """Get schema service instance for database introspection"""
        if not self._schema_service:
            from core.services.schema_service import Neo4jSchemaService

            self._schema_service = Neo4jSchemaService(self)
        return self._schema_service

    def get_query_builder(self) -> Any:
        """Get unified query builder instance"""
        if not getattr(self, "_query_builder", None):
            from core.services.query_builder import QueryBuilder

            schema_service = self.get_schema_service()
            self._query_builder = QueryBuilder(schema_service)
        return self._query_builder

    # Removed deprecated methods - use get_query_builder() directly

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        """Execute a Cypher query using Neo4jConnection"""
        if not self.connection:
            await self.connect()

        # Use the connection's execute_query which returns Record objects
        records = await self.connection.execute_query(query, params)
        if records is None:
            raise RuntimeError(f"Query execution failed: {query[:100]}...")
        return list(records)

    async def save_node(self, label: str, properties: dict[str, Any]) -> str:
        """Save a node to the graph"""
        # Generate ID if not provided
        if "id" not in properties:
            import uuid

            properties["id"] = str(uuid.uuid4())

        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $properties
        RETURN n.id as id
        """

        params = {"id": properties["id"], "properties": properties}

        records = await self.execute_query(query, params)
        if not records:
            # This should not happen with MERGE, but handle defensively
            raise RuntimeError(f"Failed to save node with label {label}")
        node_id: str = dict(records[0])["id"]
        return node_id

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by ID"""
        query = """
        MATCH (n {id: $id})
        RETURN n
        """

        records = await self.execute_query(query, {"id": node_id})
        return dict(records[0]["n"]) if records else None

    async def create_relationship(
        self, from_id: str, to_id: str, rel_type: str, properties: dict[str, Any] | None = None
    ) -> bool:
        """Create a relationship between nodes"""
        properties = properties or {}

        query = f"""
        MATCH (a {{id: $from_id}})
        MATCH (b {{id: $to_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $properties
        RETURN r
        """

        params = {"from_id": from_id, "to_id": to_id, "properties": properties}

        try:
            records = await self.execute_query(query, params)
            return len(records) > 0
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False

    async def bootstrap_indexes(self, _force: bool = False) -> Result[dict[str, Any]]:
        """
        Standardized Neo4j index and constraint creation.

        This function ensures all required indexes and constraints exist
        for optimal SKUEL performance. Safe to call multiple times.

        Args:
            _force: Reserved for future use (prefixed with _ as currently unused).
                    Database initialization always runs when this method is called.

        Returns:
            Result[Dict] with initialization details and statistics
        """
        platform_logger = get_logger("skuel.neo4j.bootstrap")

        try:
            # Database init is always enabled - bootstrap runs when called
            platform_logger.info("🔧 Starting Neo4j bootstrap_indexes()")
            start_time = datetime.now()

            # Define essential constraints
            constraints = [
                "CREATE CONSTRAINT knowledge_unit_id_unique IF NOT EXISTS FOR (ku:Ku) REQUIRE ku.id IS UNIQUE",
                "CREATE CONSTRAINT task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE",
                "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
                "CREATE CONSTRAINT conversation_id_unique IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
            ]

            # Define essential indexes for performance
            indexes = [
                # Full-text search indexes
                "CREATE FULLTEXT INDEX knowledge_fulltext IF NOT EXISTS FOR (ku:Ku) ON EACH [ku.title, ku.description, ku.summary]",
                "CREATE FULLTEXT INDEX tasks_fulltext IF NOT EXISTS FOR (t:Task) ON EACH [t.title, t.description, t.notes]",
                "CREATE FULLTEXT INDEX journals_fulltext IF NOT EXISTS FOR (d:Document) ON EACH [d.title, d.description, d.content]",
                # Legacy property indexes for filtering and sorting
                "CREATE INDEX knowledge_type_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.type)",
                "CREATE INDEX knowledge_created_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.created_at)",
                "CREATE INDEX knowledge_updated_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.updated_at)",
                # Hierarchical KnowledgeUnit indexes
                "CREATE INDEX ku_knowledge_domain_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.knowledge_domain)",
                "CREATE INDEX ku_knowledge_subdomain_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.knowledge_subdomain)",
                "CREATE INDEX ku_md_heading_level_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.md_heading_level)",
                "CREATE INDEX ku_parent_id_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.parent_knowledge_unit_id)",
                "CREATE INDEX ku_depth_level_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.depth_level)",
                "CREATE INDEX ku_root_domain_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.root_domain_id)",
                "CREATE INDEX ku_knowledge_path_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.knowledge_path)",
                "CREATE INDEX ku_source_file_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.source_md_file)",
                "CREATE INDEX ku_schema_version_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.schema_version)",
                # Combined indexes for common hierarchical query patterns
                "CREATE INDEX ku_domain_level_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.knowledge_domain, ku.md_heading_level)",
                "CREATE INDEX ku_parent_level_idx IF NOT EXISTS FOR (ku:Ku) ON (ku.parent_knowledge_unit_id, ku.depth_level)",
                # Task management indexes
                "CREATE INDEX task_status_idx IF NOT EXISTS FOR (t:Task) ON (t.status)",
                "CREATE INDEX task_priority_idx IF NOT EXISTS FOR (t:Task) ON (t.priority)",
                "CREATE INDEX task_due_date_idx IF NOT EXISTS FOR (t:Task) ON (t.due_date)",
            ]

            # Execute constraints first
            constraint_results: dict[str, list[str]] = {"created": [], "existing": [], "failed": []}
            for constraint in constraints:
                try:
                    await self.execute_query(constraint)
                    name = constraint.split()[2]  # Extract name
                    constraint_results["created"].append(name)
                    platform_logger.debug(f"✅ Constraint: {name}")
                except Exception as e:
                    name = constraint.split()[2] if len(constraint.split()) > 2 else "unknown"
                    if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                        constraint_results["existing"].append(name)
                    else:
                        constraint_results["failed"].append(name)
                        platform_logger.warning(f"❌ Constraint failed: {name} - {e}")

            # Execute indexes
            index_results: dict[str, list[str]] = {"created": [], "existing": [], "failed": []}
            for index in indexes:
                try:
                    await self.execute_query(index)
                    name = index.split()[3]  # Extract name
                    index_results["created"].append(name)
                    platform_logger.debug(f"✅ Index: {name}")
                except Exception as e:
                    name = index.split()[3] if len(index.split()) > 3 else "unknown"
                    if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                        index_results["existing"].append(name)
                    else:
                        index_results["failed"].append(name)
                        platform_logger.warning(f"❌ Index failed: {name} - {e}")

            # Calculate results
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            results = {
                "status": "success",
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "duration_seconds": duration,
                "constraints": constraint_results,
                "indexes": index_results,
                "total_constraints": len(constraint_results["created"])
                + len(constraint_results["existing"]),
                "total_indexes": len(index_results["created"]) + len(index_results["existing"]),
                "total_failed": len(constraint_results["failed"]) + len(index_results["failed"]),
            }

            platform_logger.info(
                f"✅ Neo4j bootstrap_indexes() completed in {duration:.2f}s",
                total_constraints=results["total_constraints"],
                total_indexes=results["total_indexes"],
                total_failed=results["total_failed"],
            )

            return Result.ok(results)

        except Exception as e:
            platform_logger.error(f"❌ Neo4j bootstrap_indexes() failed: {e}", exc_info=True)
            return Result.fail(
                Errors.database(
                    operation="bootstrap_indexes",
                    message=f"Neo4j index initialization failed: {e!s}",
                )
            )

    async def close(self) -> None:
        """Close the Neo4j connection"""
        if self.connection:
            await self.connection.close()
            logger.info("Neo4j connection closed")

    async def __aenter__(self) -> "Neo4jAdapter":
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit with automatic cleanup"""
        await self.close()
        if exc_type:
            logger.error(f"Neo4j adapter context exit with exception: {exc_val}")

    def session_context(self) -> Any:
        """Get an async context manager for Neo4j sessions"""
        return Neo4jSessionContext(self.driver) if self.driver else None

    # Schema Service Methods
    async def get_schema_context(self, force_refresh: bool = False) -> Any:
        """Get current schema context for query optimization"""
        schema_service = self.get_schema_service()
        return await schema_service.get_schema_context(force_refresh)

    async def validate_query_schema(
        self,
        node_labels: list[str] | None = None,
        relationship_types: list[str] | None = None,
        properties: dict[str, list[str]] | None = None,
    ):
        """
        Validate that query elements exist in the current schema.

        Args:
            node_labels: List of node labels to validate,
            relationship_types: List of relationship types to validate,
            properties: Dict of label -> properties to validate

        Returns:
            Result with validation details and clear error messages
        """
        schema_result = await self.get_schema_context()
        if schema_result.is_error:
            return schema_result

        schema = schema_result.value
        errors = []

        # Validate node labels
        if node_labels:
            errors.extend(
                [
                    f"Node label '{label}' does not exist in database"
                    for label in node_labels
                    if not schema.validate_node_label(label)
                ]
            )

        # Validate relationship types
        if relationship_types:
            errors.extend(
                [
                    f"Relationship type '{rel_type}' does not exist in database"
                    for rel_type in relationship_types
                    if not schema.validate_relationship_type(rel_type)
                ]
            )

        # Validate properties on labels
        if properties:
            for label, props in properties.items():
                if not schema.validate_node_label(label):
                    errors.append(f"Cannot validate properties for unknown label '{label}'")
                    continue
                errors.extend(
                    [
                        f"Property '{prop}' does not exist on label '{label}'"
                        for prop in props
                        if not schema.validate_property_on_label(label, prop)
                    ]
                )

        if errors:
            error_message = "; ".join(errors)
            return Result.fail(
                Errors.validation(
                    message=f"Query validation failed: {error_message}", field="schema_elements"
                )
            )

        return Result.ok({"status": "valid", "message": "All query elements exist in schema"})

    # Query Validation Methods
    async def validate_query(self, cypher: str, strict_mode: bool = True) -> Any:
        """
        Validate a Cypher query against the current schema.

        Args:
            cypher: The Cypher query to validate
            strict_mode: If True, treat warnings as errors

        Returns:
            Result[ValidationResult] with detailed validation feedback
        """
        builder = self.get_index_aware_builder()
        return await builder.validate_only(cypher, strict_mode)

    async def execute_validated_query(
        self, query: str, params: dict[str, Any] | None = None, validate: bool = True
    ) -> Result[list[dict[str, Any]]]:
        """
        Execute a Cypher query with optional pre-validation.

        Args:
            query: The Cypher query to execute,
            params: Query parameters,
            validate: Whether to validate query before execution

        Returns:
            Result containing query results or validation/execution errors
        """
        try:
            # Pre-validate query if requested
            if validate:
                validation_result = await self.validate_query(query, strict_mode=False)
                if validation_result.is_error:
                    return Result.fail(validation_result.expect_error())

                validation = validation_result.value
                if not validation.is_valid:
                    error_summary = validation.get_error_summary()
                    validation.get_suggestions()

                    return Result.fail(
                        Errors.validation(
                            message=f"Query validation failed: {error_summary}",
                            field="cypher_query",
                        )
                    )

            # Execute the query - returns Neo4j Record objects
            records = await self.execute_query(query, params)

            # Convert Neo4j Record objects to dictionaries for easier handling
            results = [dict(record) for record in records]

            return Result.ok(results)

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return Result.fail(
                Errors.database(operation="execute_query", message=f"Query execution failed: {e!s}")
            )

    async def get_query_suggestions(self, _partial_query: str) -> Any:
        """
        Get suggestions for completing a partial query.

        Args:
            _partial_query: Partial query text (prefixed with _ as this is a stub)

        Note: This feature is not yet implemented. A query suggestion engine
        would analyze the partial query and provide autocomplete suggestions
        based on schema elements and common patterns.
        """
        from core.utils.result_simplified import Errors

        return Result.fail(
            Errors.system(
                message="Query suggestions not yet implemented", operation="get_query_suggestions"
            )
        )

    # Enhanced Template Methods
    async def smart_search(
        self, _search_term: str, _labels: list[str] | None = None, _limit: int = 25
    ) -> Any:
        """
        Smart search that automatically selects the best search strategy.

        This would intelligently choose between fulltext search, indexed search,
        or basic CONTAINS search based on available schema features.

        Args:
            _search_term: Text to search for (prefixed with _ as this is a stub)
            _labels: Optional list of labels to search within (prefixed with _ as this is a stub)
            _limit: Maximum results to return (prefixed with _ as this is a stub)

        Returns:
            Result[List[Dict]] with search results

        Note: This feature is not yet implemented. Enhanced search functionality
        would analyze available indexes and automatically select the optimal
        search strategy (fulltext, vector, or basic text search).
        """
        from core.utils.result_simplified import Errors

        return Result.fail(
            Errors.system(message="Smart search not yet implemented", operation="smart_search")
        )

    async def build_template_query(self, template_name: str, parameters: dict[str, Any]) -> Any:
        """
        Build an optimized query using a specific template.

        Args:
            template_name: Name of the template to use
            parameters: Parameters for the template

        Returns:
            Result[QueryOptimizationResult] with optimized query
        """
        builder = self.get_index_aware_builder()
        return await builder.from_template(template_name, parameters)

    async def recommend_templates(self, _search_criteria: Any) -> Any:
        """
        Get template recommendations based on search criteria.

        Args:
            _search_criteria: SearchCriteria object describing the search
                (prefixed with _ as this is a stub)

        Returns:
            Result[List[TemplateRecommendation]] ordered by confidence

        Note: This feature is not yet implemented. A recommendation engine
        would analyze search criteria and suggest the most appropriate
        query templates based on the requested operations, filters, and
        available schema features.
        """
        from core.utils.result_simplified import Errors

        return Result.fail(
            Errors.system(
                message="Template recommendations not yet implemented",
                operation="recommend_templates",
            )
        )

    async def execute_template(self, template_name: str, parameters: dict[str, Any]) -> Any:
        """
        Build and execute a template query with optimization.

        Args:
            template_name: Name of the template to use
            parameters: Parameters for the template

        Returns:
            Result[List[Dict]] with query results
        """
        # Build optimized query from template
        builder = self.get_index_aware_builder()
        build_result = await builder.from_template(template_name, parameters)

        if build_result.is_error:
            return build_result

        optimization = build_result.value
        plan = optimization.primary_plan

        # Execute the optimized query
        records = await self.execute_query(plan.cypher, plan.parameters)
        results = [dict(record) for record in records]

        return Result.ok(results)

    def get_available_templates(self) -> Any:
        """
        Get list of available template names organized by category.

        Returns:
            Result[Dict[str, List[str]]] mapping categories to template names
        """
        builder = self.get_index_aware_builder()
        library = builder.get_template_library()
        return Result.ok(library)

    def get_template_info(self, template_name: str) -> Any:
        """
        Get detailed information about a specific template.

        Args:
            template_name: Name of the template

        Returns:
            Result[TemplateSpec] with template details, or error if not found
        """
        builder = self.get_index_aware_builder()
        spec = builder.get_template_spec(template_name)

        if spec is None:
            from core.utils.result_simplified import Errors

            return Result.fail(Errors.not_found(resource="Template", identifier=template_name))

        return Result.ok(spec)

    # Index-Aware Query Builder Methods
    def get_index_aware_builder(self) -> Any:
        """Get the index-aware query builder service"""
        if not getattr(self, "_index_aware_builder", None):
            from core.services.query_builder import QueryBuilder

            self._index_aware_builder = QueryBuilder(self.get_schema_service())
        return self._index_aware_builder

    async def build_optimized_query(self, request: Any) -> Any:
        """
        Build an optimized query using index-aware planning.

        Args:
            request: QueryBuildRequest object

        Returns:
            Result[QueryOptimizationResult] with optimized query plans
        """
        builder = self.get_index_aware_builder()
        return await builder.build_optimized_query(request)

    async def execute_optimized_query(self, request: Any) -> Any:
        """
        Build and execute an optimized query.

        Args:
            request: QueryBuildRequest object

        Returns:
            Result[List[Dict]] with query results
        """
        # Get optimized query plan
        optimization_result = await self.build_optimized_query(request)
        if optimization_result.is_error:
            return optimization_result

        result = optimization_result.value
        best_plan = result.best_plan

        # Execute the optimized query
        return await self.execute_validated_query(best_plan.cypher, best_plan.parameters)

    # Schema Change Detection Methods
    def get_schema_change_detector(self) -> Any:
        """Get the schema change detection service"""
        if not getattr(self, "_schema_change_detector", None):
            from core.services.schema_change_detector import (
                AdaptiveOptimizationHandler,
                SchemaChangeDetector,
            )

            self._schema_change_detector = SchemaChangeDetector(self.get_schema_service())

            # Add adaptive handler to automatically respond to changes
            handler = AdaptiveOptimizationHandler(self)
            self._schema_change_detector.add_change_handler(handler.handle_schema_change)

        return self._schema_change_detector

    async def initialize_schema_monitoring(self, interval_seconds: int = 300) -> Any:
        """
        Initialize and start schema change monitoring.

        Args:
            interval_seconds: How often to check for changes (default: 5 minutes)

        Returns:
            Result[bool] indicating success
        """
        detector = self.get_schema_change_detector()

        # Initialize the detector
        init_result = await detector.initialize()
        if init_result.is_error:
            return init_result

        # Start monitoring
        return await detector.start_monitoring(interval_seconds)

    async def check_schema_changes(self) -> Any:
        """
        Manually check for schema changes.

        Returns:
            Result[SchemaChangeReport] with details of any changes
        """
        detector = self.get_schema_change_detector()
        return await detector.check_for_changes()

    async def stop_schema_monitoring(self) -> Any:
        """Stop schema change monitoring"""
        if getattr(self, "_schema_change_detector", None):
            return await self._schema_change_detector.stop_monitoring()
        return Result.ok(True)

    def get_schema_evolution_stats(self) -> Any:
        """Get statistics about schema evolution over time"""
        if getattr(self, "_schema_change_detector", None):
            return self._schema_change_detector.get_evolution_stats()
        return None
