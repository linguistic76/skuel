"""
Integration test for QueryBuilder facade decomposition.

Tests:
1. All imports work correctly
2. Sub-services are initialized
3. Delegation methods exist
4. Backward compatibility maintained
"""


def test_import_facade():
    """Test 1: Import QueryBuilder facade"""
    from core.services.query_builder import QueryBuilder

    assert QueryBuilder is not None


def test_import_sub_services():
    """Test 2: Import sub-services directly"""
    from core.services.query import (
        FacetedQueryBuilder,
        GraphContextBuilder,
        QueryOptimizer,
        QueryTemplateManager,
        QueryValidator,
    )

    assert QueryOptimizer is not None
    assert QueryTemplateManager is not None
    assert QueryValidator is not None
    assert FacetedQueryBuilder is not None
    assert GraphContextBuilder is not None


def test_initialize_facade():
    """Test 3: Initialize QueryBuilder facade"""
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service=None)
    assert qb is not None


def test_sub_services_initialized():
    """Test 4: Verify sub-services are initialized"""
    from core.services.query import (
        FacetedQueryBuilder,
        GraphContextBuilder,
        QueryOptimizer,
        QueryTemplateManager,
        QueryValidator,
    )
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service=None)

    assert hasattr(qb, "optimizer")
    assert hasattr(qb, "templates")
    assert hasattr(qb, "validator")
    assert hasattr(qb, "faceted")
    assert hasattr(qb, "graph")

    assert isinstance(qb.optimizer, QueryOptimizer)
    assert isinstance(qb.templates, QueryTemplateManager)
    assert isinstance(qb.validator, QueryValidator)
    assert isinstance(qb.faceted, FacetedQueryBuilder)
    assert isinstance(qb.graph, GraphContextBuilder)


def test_delegation_methods_exist():
    """Test 5: Verify all delegation methods exist"""
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service=None)

    delegation_methods = [
        # QueryOptimizer methods
        "build_optimized_query",
        "get_query_explanation",
        # QueryTemplateManager methods
        "register_template",
        "from_template",
        "get_template_library",
        "get_template_spec",
        # QueryValidator methods
        "validate_only",
        "validate_and_optimize",
        "build_from_natural_language",
        # FacetedQueryBuilder methods
        "build_faceted_query",
        "generate_facet_counts_query",
        "register_faceted_templates",
        # GraphContextBuilder methods
        "build_graph_context_query",
    ]

    for method_name in delegation_methods:
        assert hasattr(qb, method_name), f"Missing method: {method_name}"


def test_backward_compatibility():
    """Test 6: Verify backward compatibility"""
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service=None)

    # Template library should be exposed for backward compatibility
    assert hasattr(qb, "_template_library")
    assert qb._template_library is qb.templates._template_library


def test_graph_context_delegation():
    """Test 7: Test GraphContextBuilder delegation"""
    from core.models.query_types import QueryIntent
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service=None)

    query = qb.build_graph_context_query(
        node_uid="test:123", intent=QueryIntent.RELATIONSHIP, depth=2
    )

    assert isinstance(query, str)
    assert "MATCH" in query


def test_template_library_access():
    """Test 8: Test template library access"""
    from core.services.query_builder import QueryBuilder

    qb = QueryBuilder(schema_service=None)

    library = qb.get_template_library()
    assert isinstance(library, dict)
    assert len(library) > 0
