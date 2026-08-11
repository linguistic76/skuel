"""
Query Builder - Persistence-Layer Orchestration
================================================

**LAYER**: Persistence adapter (adapters/persistence/neo4j/query_builders/)
**STATUS**: Internal orchestration layer — construct via UnifiedQueryBuilder, not directly
**UPDATED**: May 2026 (relocated below the hexagonal boundary, ADR-044/SKUEL022)

Facade coordinating specialized query building sub-services.
Decomposed from 1,614-line monolith (November 10, 2025).

This facade authors and optimizes Cypher, so it lives below the hexagonal
boundary alongside the sub-services it orchestrates and its only consumers
(UnifiedQueryBuilder, Neo4jAdapter). It was previously misplaced in
core/services/, where it pulled its sub-services *up* across the boundary —
relocated here so the dependency direction stays core → adapter only.

**Three-Layer Architecture:**

```
Application Layer: UnifiedQueryBuilder  ← USE THIS
    ↓
Orchestration Layer: QueryBuilder  ← This file (optimization, templates)
    ↓
Infrastructure Layer: query/cypher/ build_* functions  ← Utilities
```

**Sub-Services (Post-Decomposition):**
- QueryOptimizer: Index-aware optimization (689 lines)
- QueryTemplateRegistry: Template management (335 lines)
- QueryValidator: Query validation (275 lines)
- FacetedQueryBuilder: Faceted search (315 lines)
- GraphContextBuilder: Graph traversal (68 lines)

**Recommended Usage:**

```python
# ✅ PUBLIC ENTRY POINT - Use UnifiedQueryBuilder
from core.models.query import UnifiedQueryBuilder

result = (
    await UnifiedQueryBuilder(driver).template("search").params(...).execute()
)

# Internal — UnifiedQueryBuilder constructs and delegates to this facade.
# Direct construction is for the composition root / adapter wiring only.
from adapters.persistence.neo4j.query_builders import QueryBuilder

qb = QueryBuilder(schema_service)
```

**See Documentation:**
- Architecture: /docs/patterns/query_architecture.md
- Decomposition: /docs/QUERY_BUILDER_DECOMPOSITION_COMPLETE.md
"""

__version__ = "1.0"

from dataclasses import dataclass
from typing import Any

from adapters.persistence.neo4j.query import (
    QueryBuildRequest,
    QueryConstraint,
    QueryOptimizationResult,
    QueryPlan,
    TemplateSpec,
    ValidationResult,
)
from adapters.persistence.neo4j.query_builders.faceted_query_builder import FacetedQueryBuilder
from adapters.persistence.neo4j.query_builders.graph_context_builder import GraphContextBuilder
from adapters.persistence.neo4j.query_builders.query_optimizer import QueryOptimizer
from adapters.persistence.neo4j.query_builders.query_template_registry import QueryTemplateRegistry
from adapters.persistence.neo4j.query_builders.query_validator import QueryValidator
from core.models.query_types import QueryIntent
from core.models.search_models import FacetSetRequest as FacetSetSchema
from core.services.search.core_types import FacetSet
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


@dataclass
class TemplateRegistration:
    """Registration for a query template"""

    name: str
    spec: TemplateSpec
    category: str = "custom"


class QueryBuilder:
    """
    Query Builder Facade - Persistence-Layer Orchestration
    ======================================================

    **LAYER**: Persistence adapter (optimization, templates, validation)
    **STATUS**: Internal orchestration layer — construct via UnifiedQueryBuilder, not directly

    Orchestrates query building sub-services and provides template management.
    Decomposed from 1,614-line monolith to 225-line facade + 5 specialized services.

    **Three-Layer Architecture Position:**

    ```
    Application Layer: UnifiedQueryBuilder  ← USE THIS (user-facing API)
        ↓
    Orchestration Layer: QueryBuilder  ← YOU ARE HERE (optimization, templates)
        ↓
    Infrastructure Layer: query/cypher/ build_* functions  ← Utilities
    ```

    **Sub-Services:**
    - QueryOptimizer: Index-aware optimization (689 lines)
    - QueryTemplateRegistry: Template management (335 lines)
    - QueryValidator: Query validation (275 lines)
    - FacetedQueryBuilder: Faceted search (315 lines)
    - GraphContextBuilder: Graph traversal (68 lines)

    **When QueryBuilder is constructed directly:**

    Only at the composition root / adapter wiring, where the live instance is
    created and handed to UnifiedQueryBuilder:
    1. services_bootstrap (bootstrap-time construction)
    2. Neo4jAdapter.get_query_builder() and its index-aware builder
    3. UnifiedQueryBuilder._ensure_query_builder() (lazy auto-initialization)
    4. Testing template/optimization functionality in isolation

    Application code reaches these capabilities through UnifiedQueryBuilder,
    which delegates template/optimize/validate calls into this facade.

    **Usage:**

    ```python
    # ✅ PUBLIC ENTRY POINT - Use UnifiedQueryBuilder (auto-initializes QueryBuilder)
    from core.models.query import UnifiedQueryBuilder

    templates = UnifiedQueryBuilder(driver).list_templates()
    result = (
        await UnifiedQueryBuilder(driver).template("search").params(...).execute()
    )

    # Internal — direct construction at the composition root / adapter wiring
    from adapters.persistence.neo4j.query_builders import QueryBuilder

    qb = QueryBuilder(schema_service)
    templates = qb.get_template_library()
    ```
    """

    def __init__(self, schema_service) -> None:
        """Initialize facade with all sub-services."""
        self.schema_service = schema_service
        self.logger = get_logger("UnifiedQueryBuilder")

        # Initialize all sub-services
        self.optimizer = QueryOptimizer(schema_service)
        self.templates = QueryTemplateRegistry(schema_service)
        self.validator = QueryValidator(
            schema_service,
            optimizer=self.optimizer,
            template_manager=self.templates,
        )
        self.faceted = FacetedQueryBuilder(
            schema_service,
            optimizer=self.optimizer,  # ← Injected for faceted query optimization
        )
        self.graph = GraphContextBuilder(schema_service)

        # Register faceted search templates
        self.faceted.register_faceted_templates(self.templates)

        # Expose the registry's TemplateSpec map; UnifiedQueryBuilder reads this
        # directly (via getattr) to build its template cache.
        self._template_library = self.templates._template_library

    # ========================================================================
    # INDEX-AWARE OPTIMIZATION (Delegate to QueryOptimizer)
    # ========================================================================

    async def build_optimized_query(
        self, request: QueryBuildRequest
    ) -> Result[QueryOptimizationResult]:
        """Build an optimized query using the best available indexes."""
        return await self.optimizer.build_optimized_query(request)

    def get_query_explanation(self, plan: QueryPlan) -> str:
        """Get human-readable explanation of query plan."""
        return self.optimizer.get_query_explanation(plan)

    # ========================================================================
    # TEMPLATE MANAGEMENT (Delegate to QueryTemplateRegistry)
    # ========================================================================

    def register_template(self, name: str, spec: TemplateSpec, category: str = "custom") -> None:
        """Register a custom query template."""
        return self.templates.register_template(name, spec, category)

    async def from_template(
        self,
        template_name: str,
        **params: Any,
    ) -> Result[QueryOptimizationResult]:
        """Build a query from a predefined template."""
        return await self.templates.from_template(template_name, params)

    def get_template_library(self) -> dict[str, list[str]]:
        """Get the complete template library organized by category."""
        return self.templates.get_template_library()

    def get_template_spec(self, template_name: str) -> TemplateSpec | None:
        """Get the specification for a specific template."""
        return self.templates.get_template_spec(template_name)

    # ========================================================================
    # QUERY VALIDATION (Delegate to QueryValidator)
    # ========================================================================

    async def validate_only(
        self,
        cypher: str,
        strict_mode: bool = True,
    ) -> Result[ValidationResult]:
        """Validate a Cypher query without executing it."""
        return await self.validator.validate_only(cypher, strict_mode)

    async def validate_and_optimize(self, cypher: str) -> Result[QueryOptimizationResult]:
        """Validate an existing query and suggest optimizations."""
        return await self.validator.validate_and_optimize(cypher)

    async def build_from_natural_language(
        self,
        natural_language: str,
    ) -> Result[QueryOptimizationResult]:
        """Build a Cypher query from natural language description."""
        return await self.validator.build_from_natural_language(natural_language)

    # ========================================================================
    # FACETED SEARCH (Delegate to FacetedQueryBuilder)
    # ========================================================================

    async def build_faceted_query(
        self,
        request: QueryBuildRequest,
        facets: FacetSet | FacetSetSchema,
    ) -> Result[QueryOptimizationResult]:
        """Build a faceted search query with filters."""
        return await self.faceted.build_faceted_query(request, facets)

    def generate_facet_counts_query(
        self,
        base_query: str,
        facet_fields: list[str],
    ) -> Result[dict[str, str]]:
        """Generate a query to compute facet counts."""
        return self.faceted.generate_facet_counts_query(base_query, facet_fields)

    def register_faceted_templates(self) -> None:
        """Register templates for faceted search."""
        return self.faceted.register_faceted_templates(self.templates)

    # ========================================================================
    # GRAPH CONTEXT (Delegate to GraphContextBuilder)
    # ========================================================================

    def build_graph_context_query(self, node_uid: str, intent: QueryIntent, depth: int = 2) -> str:
        """Build Pure Cypher query for graph context traversal."""
        return self.graph.build_graph_context_query(node_uid, intent, depth)


# Helper functions for building requests
def search_request(
    labels: list[str] | None = None, search_text: str | None = None, limit: int = 25
) -> QueryBuildRequest:
    """Helper to create a text search request"""
    return QueryBuildRequest(labels=set(labels or []), search_text=search_text, limit=limit)


def filter_request(label: str, **filters: Any) -> QueryBuildRequest:
    """Helper to create a filter request"""
    constraints = []
    for prop, value in filters.items():
        constraints.append(
            QueryConstraint(property_name=prop, operator="=", value=value, label=label)
        )

    return QueryBuildRequest(labels={label}, constraints=constraints)


def range_request(
    label: str, property_name: str, min_value=None, max_value=None, limit: int | None = None
) -> QueryBuildRequest:
    """Helper to create a range query request"""
    constraints = []

    if min_value is not None:
        constraints.append(
            QueryConstraint(
                property_name=property_name, operator=">=", value=min_value, label=label
            )
        )

    if max_value is not None:
        constraints.append(
            QueryConstraint(
                property_name=property_name, operator="<=", value=max_value, label=label
            )
        )

    return QueryBuildRequest(labels={label}, constraints=constraints, limit=limit)
