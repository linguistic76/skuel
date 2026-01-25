"""
Query Builder Service - Service Layer Orchestration
====================================================

**LAYER**: Service Layer (optimization, templates, validation)
**STATUS**: Legacy - Use UnifiedQueryBuilder for new code
**UPDATED**: November 10, 2025

Facade coordinating specialized query building sub-services.
Decomposed from 1,614-line monolith (November 10, 2025).

**Three-Layer Architecture:**

```
Application Layer: UnifiedQueryBuilder  ← USE THIS
    ↓
Service Layer: QueryBuilder  ← This file (orchestration)
    ↓
Infrastructure Layer: CypherGenerator  ← Utilities
```

**Sub-Services (Post-Decomposition):**
- QueryOptimizer: Index-aware optimization (689 lines)
- QueryTemplateManager: Template management (335 lines)
- QueryValidator: Query validation (275 lines)
- FacetedQueryBuilder: Faceted search (315 lines)
- GraphContextBuilder: Graph traversal (68 lines)

**Recommended Usage:**

```python
# ✅ PREFERRED - Use UnifiedQueryBuilder
from core.models.query import UnifiedQueryBuilder

result = (
    await UnifiedQueryBuilder(driver).template("search").params(...).execute()
)

# ⚠️ LEGACY - Direct QueryBuilder usage (backward compatibility only)
from core.services.query_builder import QueryBuilder

qb = QueryBuilder(schema_service)
```

**See Documentation:**
- Architecture: /docs/patterns/query_architecture.md
- Decomposition: /docs/QUERY_BUILDER_DECOMPOSITION_COMPLETE.md
"""

__version__ = "1.0"

from dataclasses import dataclass
from typing import Any

from core.models.query import (
    QueryBuildRequest,
    QueryConstraint,
    QueryIntent,
    QueryOptimizationResult,
    QueryPlan,
    TemplateSpec,
    ValidationResult,
)
from core.models.transcription.transcription_request import FacetSetRequest as FacetSetSchema
from core.services.query.faceted_query_builder import FacetedQueryBuilder
from core.services.query.graph_context_builder import GraphContextBuilder
from core.services.query.query_optimizer import QueryOptimizer
from core.services.query.query_template_manager import QueryTemplateManager
from core.services.query.query_validator import QueryValidator
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
    Query Builder Facade - Service Layer Orchestration
    ===================================================

    **LAYER**: Service Layer (optimization, templates, validation)
    **STATUS**: Legacy - Use UnifiedQueryBuilder for new code
    **UPDATED**: November 10, 2025

    Orchestrates query building sub-services and provides template management.
    Decomposed from 1,614-line monolith to 225-line facade + 5 specialized services.

    **Three-Layer Architecture Position:**

    ```
    Application Layer: UnifiedQueryBuilder  ← USE THIS (user-facing API)
        ↓
    Service Layer: QueryBuilder  ← YOU ARE HERE (optimization, templates)
        ↓
    Infrastructure Layer: CypherGenerator  ← Utilities
    ```

    **Sub-Services:**
    - QueryOptimizer: Index-aware optimization (689 lines)
    - QueryTemplateManager: Template management (335 lines)
    - QueryValidator: Query validation (275 lines)
    - FacetedQueryBuilder: Faceted search (315 lines)
    - GraphContextBuilder: Graph traversal (68 lines)

    **When to Use QueryBuilder Directly:**

    Use ONLY when:
    1. Implementing new UnifiedQueryBuilder features that need templates
    2. Testing template functionality in isolation
    3. Accessing optimization internals for analysis

    **Recommended Usage:**

    ```python
    # ✅ PREFERRED - Use UnifiedQueryBuilder (auto-initializes QueryBuilder)
    from core.models.query import UnifiedQueryBuilder

    templates = UnifiedQueryBuilder(driver).list_templates()
    result = (
        await UnifiedQueryBuilder(driver).template("search").params(...).execute()
    )

    # ⚠️ ONLY IF NECESSARY - Direct QueryBuilder usage
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service)
    templates = qb.get_template_library()
    ```

    **Backward Compatibility:**

    This facade maintains the same API as the original monolithic QueryBuilder,
    ensuring zero breaking changes for existing code that depends on it.
    """

    def __init__(self, schema_service) -> None:
        """Initialize facade with all sub-services."""
        self.schema_service = schema_service
        self.logger = get_logger("UnifiedQueryBuilder")

        # Initialize all sub-services
        self.optimizer = QueryOptimizer(schema_service)
        self.templates = QueryTemplateManager(schema_service)
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

        # Expose template library for backward compatibility
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
    # TEMPLATE MANAGEMENT (Delegate to QueryTemplateManager)
    # ========================================================================

    def register_template(self, name: str, spec: TemplateSpec, category: str = "custom"):
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

    async def generate_facet_counts_query(
        self,
        base_query: str,
        facet_fields: list[str],
    ) -> Result[dict[str, str]]:
        """Generate a query to compute facet counts."""
        return await self.faceted.generate_facet_counts_query(base_query, facet_fields)

    def register_faceted_templates(self):
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
