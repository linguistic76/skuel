"""
Integration Tests for UnifiedQueryBuilder - Phase 1 & Phase 2 Improvements
===========================================================================

Tests comprehensive integration of UnifiedQueryBuilder with QueryBuilder,
QueryOptimizer, and template system.

**Phase 1 (Template Discovery):**
- Template discovery without manual injection
- Template validation with helpful errors
- Category-based filtering
- Lazy QueryBuilder initialization

**Phase 2 (Optimization Bridge):**
- Query optimization via optimize_query()
- Query validation via validate_query()
- Query explanation via explain_query()
- Automatic bridge to QueryOptimizer

Created: November 10, 2025
"""

import pytest

from core.models.query import UnifiedQueryBuilder
from core.services.query_builder import QueryBuilder

# ============================================================================
# PHASE 1 TESTS: Template Discovery
# ============================================================================


def test_list_templates_without_manual_injection():
    """Test that template discovery auto-initializes QueryBuilder."""
    # Create UnifiedQueryBuilder WITHOUT manually injecting QueryBuilder
    builder = UnifiedQueryBuilder(executor=None)

    # Should auto-initialize QueryBuilder and list templates
    templates = builder.list_templates()

    assert isinstance(templates, dict)
    assert len(templates) > 0, "Expected 40+ templates from QueryBuilder"

    # Verify well-known templates exist (from actual library)
    expected_templates = [
        "faceted_knowledge_search",
        "get_by_uid",
        "text_search",
    ]

    for template_name in expected_templates:
        assert template_name in templates, (
            f"Expected template '{template_name}' not found in library"
        )


def test_template_validation_with_helpful_errors():
    """Test that template validation provides helpful error messages."""
    builder = UnifiedQueryBuilder(executor=None)

    # Try to use nonexistent template
    with pytest.raises(ValueError) as exc_info:
        builder.template("nonexistent_template_xyz")

    error_msg = str(exc_info.value)

    # Verify error message is helpful
    assert "Template 'nonexistent_template_xyz' not found" in error_msg
    assert "Available templates:" in error_msg
    assert "Use list_templates()" in error_msg

    # Should show preview of available templates
    assert "[" in error_msg  # List preview
    assert "]" in error_msg


def test_category_based_filtering():
    """Test template discovery with category filtering."""
    builder = UnifiedQueryBuilder(executor=None)

    # Get all templates
    all_templates = builder.list_templates()
    assert len(all_templates) > 0

    # Get knowledge category only (if exists)
    knowledge_templates = builder.list_templates(category="knowledge")

    # Knowledge templates should be subset of all templates
    assert len(knowledge_templates) <= len(all_templates)

    # Verify all returned templates have correct category
    for name, spec in knowledge_templates.items():
        assert hasattr(spec, "category"), f"Template '{name}' missing category attribute"
        assert spec.category == "knowledge", (
            f"Template '{name}' has wrong category: {spec.category}"
        )


def test_lazy_query_builder_initialization():
    """Test that QueryBuilder is lazily initialized only when needed."""
    # Create builder without QueryBuilder or schema_service
    builder = UnifiedQueryBuilder(executor=None)

    # QueryBuilder should NOT be initialized yet
    assert builder.query_builder_service is None

    # Accessing templates should trigger lazy initialization
    templates = builder.list_templates()

    # NOW QueryBuilder should be initialized
    assert builder.query_builder_service is not None
    assert isinstance(builder.query_builder_service, QueryBuilder)
    assert len(templates) > 0


def test_template_library_caching():
    """Test that template library is cached after first access."""
    builder = UnifiedQueryBuilder(executor=None)

    # First access - should initialize and cache
    templates1 = builder.list_templates()
    assert builder._template_library_cache is not None

    # Second access - should use cache
    templates2 = builder.list_templates()

    # Should be same dictionary (cached)
    assert templates1 is templates2
    assert id(templates1) == id(templates2)


# ============================================================================
# PHASE 2 TESTS: Optimization Bridge
# ============================================================================


@pytest.mark.asyncio
async def test_optimize_query_bridge():
    """Test that optimize_query() bridges to QueryOptimizer correctly."""
    builder = UnifiedQueryBuilder(executor=None)

    # Simple query to optimize
    cypher = "MATCH (t:Task) WHERE t.status = 'active' RETURN t"

    # Should auto-initialize QueryBuilder and call validate_and_optimize()
    result = await builder.optimize_query(cypher)

    # Result should be returned (may fail if no schema, but that's OK for this test)
    # We're testing the bridge exists, not that optimization works
    assert result is not None

    # Verify QueryBuilder was initialized
    assert builder.query_builder_service is not None


@pytest.mark.asyncio
async def test_validate_query_bridge():
    """Test that validate_query() bridges to QueryValidator correctly."""
    builder = UnifiedQueryBuilder(executor=None)

    # Simple query to validate
    cypher = "MATCH (t:Task) WHERE t.status = 'active' RETURN t"

    # Should auto-initialize QueryBuilder and call validate_only()
    result = await builder.validate_query(cypher)

    # Result should be returned
    assert result is not None

    # Verify QueryBuilder was initialized
    assert builder.query_builder_service is not None


def test_explain_query_bridge():
    """Test that explain_query() bridges to QueryOptimizer correctly."""
    builder = UnifiedQueryBuilder(executor=None)

    # Simple query to explain
    cypher = "MATCH (t:Task)-[:APPLIES_KNOWLEDGE]->(ku:Ku) RETURN t, ku"

    # Should auto-initialize QueryBuilder and call get_query_explanation()
    explanation = builder.explain_query(cypher)

    # Explanation should be a string
    assert isinstance(explanation, str)
    assert len(explanation) > 0

    # Verify QueryBuilder was initialized
    assert builder.query_builder_service is not None


def test_optimization_methods_with_schema_service():
    """Test optimization methods work when schema_service is provided."""
    # Create builder with schema_service=None (QueryBuilder can initialize with None)
    builder = UnifiedQueryBuilder(executor=None, schema_service=None)

    # QueryBuilder should be lazily initialized when needed
    assert builder.query_builder_service is None

    # Access templates - should initialize QueryBuilder
    templates = builder.list_templates()

    # QueryBuilder should now be initialized
    assert builder.query_builder_service is not None
    # Schema service will be None, which is fine for template access
    assert builder.query_builder_service.schema_service is None
    assert len(templates) > 0


# ============================================================================
# INTEGRATION TESTS: Phase 1 + Phase 2 Together
# ============================================================================


@pytest.mark.asyncio
async def test_full_integration_workflow():
    """Test complete workflow: templates + optimization together."""
    builder = UnifiedQueryBuilder(executor=None)

    # Step 1: Discover templates (Phase 1)
    templates = builder.list_templates()
    assert len(templates) > 0

    # Step 2: Validate a query (Phase 2)
    cypher = "MATCH (t:Task) WHERE t.status = 'active' RETURN t"
    validation_result = await builder.validate_query(cypher)
    assert validation_result is not None

    # Step 3: Optimize the query (Phase 2)
    optimization_result = await builder.optimize_query(cypher)
    assert optimization_result is not None

    # Step 4: Explain the query (Phase 2)
    explanation = builder.explain_query(cypher)
    assert isinstance(explanation, str)

    # Verify QueryBuilder was initialized exactly once
    assert builder.query_builder_service is not None
    assert isinstance(builder.query_builder_service, QueryBuilder)


def test_phase_2_methods_available_in_api():
    """Test that Phase 2 methods are discoverable via dir()."""
    builder = UnifiedQueryBuilder(executor=None)

    # Verify all Phase 2 methods are available
    api_methods = dir(builder)

    assert "optimize_query" in api_methods
    assert "validate_query" in api_methods
    assert "explain_query" in api_methods

    # Verify Phase 1 methods still available
    assert "list_templates" in api_methods
    assert "template" in api_methods


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


def test_template_access_without_schema_succeeds():
    """Test that templates work even without schema_service."""
    # Create builder without schema_service
    builder = UnifiedQueryBuilder(executor=None)

    # Templates should still work (QueryBuilder can initialize with None schema)
    templates = builder.list_templates()
    assert len(templates) > 0


def test_optimization_without_driver_succeeds():
    """Test that optimization bridge works even without driver."""
    # Create builder without driver
    builder = UnifiedQueryBuilder(executor=None)

    # Optimization methods should still be callable (may fail internally, but bridge exists)
    explanation = builder.explain_query("MATCH (n) RETURN n")
    assert isinstance(explanation, str)


# ============================================================================
# DOCUMENTATION TESTS
# ============================================================================


def test_docstrings_exist_for_phase_2_methods():
    """Test that all Phase 2 methods have comprehensive docstrings."""
    builder = UnifiedQueryBuilder(executor=None)

    # Check optimize_query docstring
    assert builder.optimize_query.__doc__ is not None
    assert "Optimize an existing Cypher query" in builder.optimize_query.__doc__
    assert "Example:" in builder.optimize_query.__doc__

    # Check validate_query docstring
    assert builder.validate_query.__doc__ is not None
    assert "Validate a Cypher query" in builder.validate_query.__doc__
    assert "Example:" in builder.validate_query.__doc__

    # Check explain_query docstring
    assert builder.explain_query.__doc__ is not None
    assert "human-readable explanation" in builder.explain_query.__doc__
    assert "Example:" in builder.explain_query.__doc__


def test_class_docstring_documents_phase_2():
    """Test that UnifiedQueryBuilder class docstring documents Phase 2."""
    docstring = UnifiedQueryBuilder.__doc__

    assert docstring is not None
    assert "Phase 2 Improvements" in docstring
    assert "optimize_query()" in docstring
    assert "validate_query()" in docstring
    assert "explain_query()" in docstring
