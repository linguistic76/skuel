"""
Unified Query Builder - THE Single Entry Point
==============================================

Fluent API facade that eliminates query builder confusion.

**Problem Solved:**
Before: 3 query builders (CypherGenerator, QueryBuilder, SemanticQueryBuilder)
        + Decision matrix needed to know which one to use
After:  Single fluent API that routes internally

**Architecture:**
- Public: Fluent API methods (for_model, semantic, template)
- Internal: Routes to CypherGenerator or templates
- Automatic: Index optimization, query planning, execution strategy
- Pure Cypher: No APOC dependencies - maximum portability

**Usage Examples:**

```python
from core.models.query import UnifiedQueryBuilder
from core.constants import GraphDepth, QueryLimit

# Simple model queries (routes to CypherGenerator)
tasks = await (
    UnifiedQueryBuilder()
    .for_model(Task)
    .filter(priority="high", status="in_progress")
    .limit(50)
    .execute()
)

# Semantic graph traversal (routes to build_semantic_context)
context = await (
    UnifiedQueryBuilder()
    .semantic("ku.python_basics")
    .traverse(types=[SemanticRelationshipType.REQUIRES_FOUNDATION])
    .execute()
)  # GraphDepth.DEFAULT is default

# Template-based queries (routes to QueryBuilder templates)
results = await (
    UnifiedQueryBuilder()
    .template("faceted_knowledge_search")
    .params(domain="TECH", level=2, QueryLimit.LARGE)
    .execute()
)
```

**Benefits:**
1. Single entry point - no decision matrix needed
2. Type-safe - Generic[T] provides IDE autocomplete
3. Discoverable - .for_model(), .semantic(), .template() are obvious
4. Pure Cypher - works on ALL Neo4j installations (Desktop, Aura, Docker)
5. Internal routing - automatically picks best strategy

**Migration Status:**
- Phase 1: Facade created ✓
- Phase 2: UniversalBackend using fluent API ✓
- Phase 3: Services migrated to Pure Cypher ✓
- Phase 4: CypherGenerator marked as internal ✓
- Phase 5: APOC completely removed (October 20, 2025) ✓
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from neo4j import AsyncDriver

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.query._query_models import QueryIntent

# Phase 4: Import from internal modules (marked with underscore prefix)
from core.models.query.cypher import (
    build_count_query,
    build_list_query,
    build_prerequisite_chain,
    build_search_query,
    build_semantic_context,
    build_semantic_traversal,
)
from core.models.query.graph_traversal import build_graph_context_query
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.query_builder import QueryBuilder
    from core.services.schema_service import SchemaContext

T = TypeVar("T")
logger = get_logger(__name__)


@dataclass
class QueryResult[T]:
    """Result of query execution with metadata."""

    data: list[T]
    cypher: str
    parameters: dict[str, Any]
    strategy: str  # "cypher", "apoc", "template"
    estimated_cost: int | None = None


class ModelQueryBuilder[T]:
    """
    Fluent builder for model-based queries.

    Routes to CypherGenerator internally.
    """

    def __init__(
        self, model: type[T], driver: AsyncDriver | None = None, label: str | None = None
    ) -> None:
        self.model = model
        self.driver = driver
        self.label = label  # Neo4j label (e.g., "Journal" instead of "JournalPure")
        self._filters: dict[str, Any] = {}
        self._limit_val: int | None = None
        self._offset_val: int = 0
        self._order_by_field: str | None = None
        self._order_desc: bool = False
        self._fulltext_query: str | None = None
        self._fulltext_index: str | None = None

    def filter(self, **filters: Any) -> "ModelQueryBuilder[T]":
        """
        Add filters to query.

        Supports operators via double underscore:
        - eq (default): .filter(priority='high')
        - gt, lt, gte, lte: .filter(due_date__gte=date.today())
        - contains: .filter(title__contains='urgent')
        - in: .filter(priority__in=['high', 'urgent'])
        """
        self._filters.update(filters)
        return self

    def limit(self, limit: int) -> "ModelQueryBuilder[T]":
        """Limit number of results."""
        self._limit_val = limit
        return self

    def offset(self, offset: int) -> "ModelQueryBuilder[T]":
        """Skip first N results."""
        self._offset_val = offset
        return self

    def order_by(self, field: str, desc: bool = False) -> "ModelQueryBuilder[T]":
        """Order results by field."""
        self._order_by_field = field
        self._order_desc = desc
        return self

    def fulltext(self, query_text: str, index_name: str | None = None) -> "ModelQueryBuilder[T]":
        """
        Search using Neo4j full-text index for optimal text search performance.

        Full-text indexes provide:
        - Case-insensitive search
        - Token-based matching (words, not substrings)
        - Relevance scoring
        - 10-100x faster than CONTAINS for large datasets

        Args:
            query_text: Text to search for (Lucene query syntax supported)
            index_name: Optional full-text index name (defaults to model-based name)

        Example:
            mocs = await (builder
                .for_model(MapOfContent)
                .fulltext("python async")  # Finds MOCs with "python" AND "async"
                .limit(20)
                .execute())

        Note:
            Requires full-text index to exist. Create via:
            db.index.fulltext.createNodeIndex('moc_search', ['MapOfContent'], ['title', 'description', 'tags'])
        """
        self._fulltext_query = query_text
        if index_name:
            self._fulltext_index = index_name
        else:
            # Default index name: {model_name}_fulltext
            model_name = self.model.__name__
            self._fulltext_index = f"{model_name.lower()}_fulltext"
        return self

    def build(self) -> tuple[str, dict[str, Any]]:
        """
        Build query without executing.

        Returns:
            Tuple of (cypher_query, parameters)
        """
        # Full-text search query (highest priority)
        if self._fulltext_query:
            # Build full-text search query
            query = """
            CALL db.index.fulltext.queryNodes($index_name, $query_text)
            YIELD node AS n, score
            """

            # Add filters if specified
            if self._filters:
                filter_conditions = [f"n.{key} = ${key}" for key in self._filters]
                query += "WHERE " + " AND ".join(filter_conditions) + "\n"

            # Add ordering (by score DESC by default, or custom)
            if self._order_by_field:
                direction = "DESC" if self._order_desc else "ASC"
                query += f"RETURN n, score ORDER BY n.{self._order_by_field} {direction}\n"
            else:
                query += "RETURN n, score ORDER BY score DESC\n"

            # Add pagination
            if self._offset_val > 0:
                query += f"SKIP {self._offset_val}\n"
            if self._limit_val:
                query += f"LIMIT {self._limit_val}\n"

            params = {
                "index_name": self._fulltext_index,
                "query_text": self._fulltext_query,
                **self._filters,
            }

            return query, params

        # Filter-based search
        elif self._filters:
            # Search query with filters
            query, params = build_search_query(self.model, self._filters, label=self.label)

            # Build query clauses in correct Cypher order: RETURN ... ORDER BY ... SKIP ... LIMIT
            return_clause = "RETURN n"

            # Add ordering if specified
            if self._order_by_field:
                direction = "DESC" if self._order_desc else "ASC"
                return_clause += f" ORDER BY n.{self._order_by_field} {direction}"

            # Add pagination (SKIP must come before LIMIT)
            if self._offset_val > 0:
                return_clause += " SKIP $skip"
                params["skip"] = self._offset_val

            if self._limit_val:
                return_clause += " LIMIT $limit"
                params["limit"] = self._limit_val

            # Replace the RETURN n with our complete clause
            query = query.replace("RETURN n", return_clause)

            return query, params

        # List query (no filters, no full-text)
        else:
            query, params = build_list_query(
                self.model,
                label=self.label,
                limit=self._limit_val or 100,
                skip=self._offset_val,
                order_by=self._order_by_field,
                order_desc=self._order_desc,
            )
            return query, params

    async def execute(self) -> QueryResult[T]:
        """
        Execute query and return results.

        Requires driver to be set during initialization.
        """
        if not self.driver:
            raise ValueError(
                "Driver is required for execution. Use .build() to get query without executing."
            )

        query, params = self.build()

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            # Convert Neo4j records to model instances using generic mapper
            data = [from_neo4j_node(dict(r["n"]), self.model) for r in records]

            return QueryResult(data=data, cypher=query, parameters=params, strategy="cypher")

    async def count(self) -> int:
        """
        Count matching records without retrieving them.

        More efficient than execute() + len().
        """
        query, params = build_count_query(
            self.model, self._filters if self._filters else None, label=self.label
        )

        if not self.driver:
            raise ValueError("Driver is required for execution")

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            return record["count"] if record else 0


class SemanticQueryBuilder:
    """
    Fluent builder for semantic relationship queries.

    Routes to build_semantic_context() internally.
    """

    def __init__(self, uid: str, driver: AsyncDriver | None = None) -> None:
        self.uid = uid
        self.driver = driver
        self._semantic_types: list[SemanticRelationshipType] = []
        self._depth: int = 2
        self._min_confidence: float = 0.0
        self._query_type: str = "context"  # context, prerequisites, traversal
        self._end_uid: str | None = None

    def traverse(self, types: list[SemanticRelationshipType]) -> "SemanticQueryBuilder":
        """Specify semantic relationship types to traverse."""
        self._semantic_types = types
        return self

    def depth(self, depth: int) -> "SemanticQueryBuilder":
        """Set maximum traversal depth."""
        self._depth = depth
        return self

    def min_confidence(self, confidence: float) -> "SemanticQueryBuilder":
        """Filter relationships by minimum confidence score."""
        self._min_confidence = confidence
        return self

    def prerequisites(self) -> "SemanticQueryBuilder":
        """Get prerequisite chain instead of general context."""
        self._query_type = "prerequisites"
        return self

    def path_to(self, end_uid: str) -> "SemanticQueryBuilder":
        """Find shortest path to target node."""
        self._query_type = "traversal"
        self._end_uid = end_uid
        return self

    def build(self) -> tuple[str, dict[str, Any]]:
        """
        Build query without executing.

        Returns:
            Tuple of (cypher_query, parameters)
        """
        if self._query_type == "prerequisites":
            return build_prerequisite_chain(
                node_uid=self.uid, semantic_types=self._semantic_types, depth=self._depth
            )
        elif self._query_type == "traversal" and self._end_uid:
            return build_semantic_traversal(
                start_uid=self.uid,
                end_uid=self._end_uid,
                semantic_types=self._semantic_types,
                max_depth=self._depth,
            )
        else:
            # Default: semantic context
            return build_semantic_context(
                node_uid=self.uid,
                semantic_types=self._semantic_types,
                depth=self._depth,
                min_confidence=self._min_confidence,
            )

    async def execute(self) -> QueryResult:
        """Execute semantic query and return results."""
        if not self.driver:
            raise ValueError(
                "Driver is required for execution. Use .build() to get query without executing."
            )

        query, params = self.build()

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            return QueryResult(
                data=records, cypher=query, parameters=params, strategy="cypher_semantic"
            )


# BatchQueryBuilder removed - Pure Cypher migration (October 20, 2025)
# Use Pure Cypher UNWIND patterns instead of APOC batch operations:
#
#   UNWIND $nodes AS node_data
#   MERGE (n:Label {uid: node_data.uid})
#   SET n += node_data.properties
#   RETURN count(n) as created_count


class TemplateQueryBuilder:
    """
    Fluent builder for template-based queries.

    Routes to QueryBuilder.from_template() internally.
    """

    def __init__(self, template_name: str, query_builder_service=None) -> None:
        self.template_name = template_name
        self.query_builder_service = query_builder_service
        self._params: dict[str, Any] = {}

    def params(self, **params: Any) -> "TemplateQueryBuilder":
        """Set template parameters."""
        self._params.update(params)
        return self

    async def execute(self):
        """Execute template query."""
        if not self.query_builder_service:
            raise ValueError(
                "QueryBuilder service is required for template execution. "
                "Pass query_builder_service to UnifiedQueryBuilder constructor."
            )

        result = await self.query_builder_service.from_template(self.template_name, self._params)

        if result.is_error:
            raise ValueError(f"Template execution failed: {result.error}")

        query_plan = result.value.primary_plan

        return QueryResult(
            data=[],  # Template execution returns plan, not data
            cypher=query_plan.cypher,
            parameters=query_plan.parameters,
            strategy="template",
            estimated_cost=query_plan.estimated_cost,
        )


class UnifiedQueryBuilder:
    """
    THE single entry point for all query building in SKUEL.

    Eliminates confusion by providing fluent API that routes internally.

    **Pure Cypher architecture - no APOC dependencies.**

    **Phase 1 Improvements (November 2025):**
    - Template discovery via list_templates()
    - Automatic QueryBuilder initialization
    - Template validation before execution

    **Phase 2 Improvements (November 2025):**
    - Query optimization via optimize_query()
    - Query validation via validate_query()
    - Query explanation via explain_query()
    - Automatic bridge to QueryOptimizer

    Usage:
        # Model queries
        await UnifiedQueryBuilder(driver).for_model(Task).filter(status='active').execute()

        # Semantic queries
        await UnifiedQueryBuilder(driver).semantic("ku.123").traverse(...).execute()

        # Template discovery
        templates = UnifiedQueryBuilder(driver).list_templates()
        print(f"Available templates: {list(templates.keys())}")

        # Templates (auto-initialized, validated)
        await UnifiedQueryBuilder(driver).template("search").params(...).execute()

        # Query optimization (NEW in Phase 2!)
        result = await UnifiedQueryBuilder(driver).optimize_query(cypher_query)

        # Query validation (NEW in Phase 2!)
        validation = await UnifiedQueryBuilder(driver).validate_query(cypher_query)

        # Query explanation (NEW in Phase 2!)
        explanation = UnifiedQueryBuilder(driver).explain_query(cypher_query)

        # Graph context
        query = UnifiedQueryBuilder().graph_context("task.123", QueryIntent.HIERARCHICAL)
    """

    def __init__(
        self,
        driver: AsyncDriver | None = None,
        query_builder_service: "QueryBuilder | None" = None,
        schema_service: "SchemaContext | None" = None,
    ) -> None:
        """
        Initialize unified query builder.

        Args:
            driver: Neo4j AsyncDriver for query execution,
            query_builder_service: Optional QueryBuilder service for template support
            schema_service: Optional SchemaContext for auto-creating QueryBuilder
        """
        self.driver = driver
        self.query_builder_service: QueryBuilder | None = query_builder_service
        self._schema_service = schema_service
        self._template_library_cache: dict[str, Any] | None = None

    def for_model(self, model: type[T], label: str | None = None) -> ModelQueryBuilder[T]:
        """
        Start building query for specific model.

        Routes to CypherGenerator internally.

        Args:
            model: Domain model class
            label: Optional Neo4j label (defaults to model.__name__ if not provided)

        Example:
            tasks = await (builder
                .for_model(Task, label="Task")  # Explicit label
                .filter(priority='high', status='in_progress')
                .order_by('due_date', desc=True)
                .limit(50)
                .execute())
        """
        return ModelQueryBuilder(model, self.driver, label=label)

    def semantic(self, uid: str) -> SemanticQueryBuilder:
        """
        Start building semantic relationship query.

        Routes to build_semantic_context() internally.

        Example:
            context = await (builder
                .semantic("ku.python_basics")
                .traverse(types=[SemanticRelationshipType.REQUIRES_FOUNDATION])
                .min_confidence(0.8)
                .execute())  # GraphDepth.DEFAULT is default
        """
        return SemanticQueryBuilder(uid, self.driver)

    # batch() method removed - Pure Cypher migration (October 20, 2025)
    # Use Pure Cypher UNWIND patterns for batch operations instead

    def _ensure_query_builder(self) -> "QueryBuilder":
        """
        Lazy initialization of QueryBuilder if not provided.

        Creates QueryBuilder automatically if schema_service was provided
        or raises ValueError if initialization fails.

        Returns:
            QueryBuilder instance (either provided or auto-created)

        Raises:
            ValueError: If QueryBuilder cannot be initialized
        """
        if not self.query_builder_service:
            # Try to create QueryBuilder with schema_service if available
            try:
                from core.services.query_builder import QueryBuilder

                self.query_builder_service = QueryBuilder(self._schema_service)
                logger.info("Auto-initialized QueryBuilder for template support")
            except Exception as e:
                logger.warning(
                    f"Could not auto-initialize QueryBuilder: {e}. "
                    "Template functionality will be limited."
                )
                raise ValueError(
                    "QueryBuilder service is required for template execution. "
                    "Pass query_builder_service or schema_service to UnifiedQueryBuilder constructor."
                ) from e

        return self.query_builder_service

    def list_templates(self, category: str | None = None) -> dict[str, Any]:
        """
        List all available query templates.

        Templates are loaded from QueryBuilder's template library and cached
        for efficient repeated access.

        Args:
            category: Optional category filter (e.g., "knowledge", "faceted", "traversal")

        Returns:
            Dictionary of template_name -> TemplateSpec

        Example:
            templates = builder.list_templates()
            print(f"Available: {list(templates.keys())}")

            # Filter by category
            knowledge_templates = builder.list_templates(category="knowledge")
        """
        # Ensure QueryBuilder is initialized
        qb = self._ensure_query_builder()

        # Get template library (with caching)
        if self._template_library_cache is None:
            # Access _template_library directly (contains TemplateSpec objects)
            # Note: get_template_library() returns a different structure (dict[category -> list])
            self._template_library_cache = getattr(qb, "_template_library", {})

        # Filter by category if requested
        if category:
            return {
                name: spec
                for name, spec in self._template_library_cache.items()
                if spec.category == category
            }

        return self._template_library_cache

    def template(self, name: str) -> TemplateQueryBuilder:
        """
        Start building template-based query with automatic template discovery.

        Routes to QueryBuilder.from_template() internally. QueryBuilder is
        auto-initialized if not provided during construction.

        Args:
            name: Template name (use list_templates() to see available templates)

        Returns:
            TemplateQueryBuilder for fluent API chaining

        Raises:
            ValueError: If template name not found in template library

        Example:
            # Discover available templates
            templates = builder.list_templates()
            print(f"Available: {list(templates.keys())}")

            # Use template
            results = await (builder
                .template("faceted_knowledge_search")
                .params(domain="TECH", level=2, QueryLimit.LARGE)
                .execute())
        """
        # Ensure QueryBuilder is initialized
        qb = self._ensure_query_builder()

        # Validate template exists
        templates = self.list_templates()
        if name not in templates:
            available = list(templates.keys())
            # Show first 10 templates in error message
            preview = available[:10]
            more = f" (+{len(available) - 10} more)" if len(available) > 10 else ""
            raise ValueError(
                f"Template '{name}' not found. "
                f"Available templates: {preview}{more}. "
                f"Use list_templates() to see all templates."
            )

        return TemplateQueryBuilder(name, qb)

    # ========================================================================
    # OPTIMIZATION BRIDGE (Phase 2 - November 2025)
    # ========================================================================

    async def optimize_query(
        self, cypher: str, _context: dict[str, Any] | None = None
    ) -> Result[Any]:
        """
        Optimize an existing Cypher query using index-aware optimization.

        Bridges to QueryOptimizer through QueryBuilder. Auto-initializes
        QueryBuilder if not provided during construction.

        Args:
            cypher: Cypher query to optimize
            _context: Optional context for optimization (reserved for future use)

        Returns:
            Result containing QueryOptimizationResult with optimized query and plan

        Example:
            result = await builder.optimize_query(
                "MATCH (t:Task) WHERE t.status = 'active' RETURN t",
                context={"node_labels": ["Task"], "properties": ["status"]}
            )

            if result.is_ok:
                print(f"Original: {result.value.original_query}")
                print(f"Optimized: {result.value.optimized_query}")
                print(f"Explanation: {result.value.explanation}")
        """
        qb = self._ensure_query_builder()
        return await qb.validate_and_optimize(cypher)

    async def validate_query(
        self, cypher: str, context: dict[str, Any] | None = None
    ) -> Result[Any]:
        """
        Validate a Cypher query without executing it.

        Bridges to QueryValidator through QueryBuilder. Checks syntax,
        semantics, and potential performance issues.

        Args:
            cypher: Cypher query to validate
            context: Optional context for validation

        Returns:
            Result containing ValidationResult with issues and warnings

        Example:
            result = await builder.validate_query(
                "MATCH (t:Task) WHERE t.status = 'active' RETURN t"
            )

            if result.is_ok:
                if result.value.is_valid:
                    print("Query is valid!")
                else:
                    for issue in result.value.issues:
                        print(f"{issue.severity}: {issue.message}")
        """
        qb = self._ensure_query_builder()
        return await qb.validate_only(cypher, context)

    def explain_query(self, cypher: str) -> str:
        """
        Get human-readable explanation of query execution plan.

        Bridges to QueryOptimizer through QueryBuilder. Explains what
        the query does, which indexes it uses, and potential bottlenecks.

        Args:
            cypher: Cypher query to explain

        Returns:
            Human-readable explanation string

        Example:
            explanation = builder.explain_query(
                "MATCH (t:Task)-[:APPLIES_KNOWLEDGE]->(ku:Ku) "
                "WHERE t.status = 'active' RETURN t, ku"
            )
            print(explanation)
            # Output: "This query traverses Task->KnowledgeUnit relationships..."
        """
        qb = self._ensure_query_builder()

        # Create a basic QueryPlan for explanation
        # (In real usage, this would come from build_optimized_query)
        from core.models.query import IndexStrategy, QueryPlan

        plan = QueryPlan(
            cypher=cypher,
            parameters={},
            strategy=IndexStrategy.NO_INDEX,
            used_indexes=[],
            estimated_cost=0,
            explanation="Basic query without optimization",
        )

        return qb.get_query_explanation(plan)

    def graph_context(self, uid: str, intent: QueryIntent, depth: int = 2) -> str:
        """
        Build APOC graph context query (convenience method).

        Routes to build_graph_context_query().

        Example:
            query = builder.graph_context(
                uid="task.123",
                intent=QueryIntent.HIERARCHICAL,
                GraphDepth.NEIGHBORHOOD
            )
        """
        return build_graph_context_query(uid, intent, depth)


# Convenience factory function
def query(driver: AsyncDriver | None = None) -> UnifiedQueryBuilder:
    """
    Create unified query builder instance.

    Shorthand for UnifiedQueryBuilder(driver).

    Usage:
        from core.models.query import query

        tasks = await query(driver).for_model(Task).filter(status='active').execute()
    """
    return UnifiedQueryBuilder(driver)
