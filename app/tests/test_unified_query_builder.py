"""
Tests for Unified Query Builder
================================

Tests the fluent API facade that eliminates query builder confusion.
"""

from datetime import date

import pytest

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.query import UnifiedQueryBuilder, query
from core.models.task.task import Task


class TestModelQueryBuilder:
    """Tests for model-based queries."""

    def test_simple_filter_build(self):
        """Test building simple filter query."""
        cypher, params = (
            query().for_model(Task).filter(priority="high", status="in_progress").build()
        )

        assert "MATCH (n:Task)" in cypher or "MATCH (n:TaskPure)" in cypher
        assert "WHERE" in cypher
        assert "priority" in params
        assert "status" in params
        assert params["priority"] == "high"
        assert params["status"] == "in_progress"

    def test_comparison_operators_build(self):
        """Test building query with comparison operators."""
        cypher, params = (
            query()
            .for_model(Task)
            .filter(
                due_date__gte=date(2025, 1, 1),
                priority__lt="medium",  # Use a field that exists in Task
            )
            .build()
        )

        assert ">=" in cypher
        assert "<" in cypher
        assert "due_date_gte" in params or "due_date__gte" in params
        assert "priority_lt" in params or "priority__lt" in params

    def test_string_matching_build(self):
        """Test building query with string matching."""
        cypher, params = query().for_model(Task).filter(title__contains="urgent").build()

        assert "CONTAINS" in cypher
        assert "title_contains" in params or "title__contains" in params

    def test_list_membership_build(self):
        """Test building query with IN operator."""
        cypher, params = query().for_model(Task).filter(priority__in=["high", "urgent"]).build()

        assert "IN" in cypher
        assert "priority_in" in params or "priority__in" in params
        assert isinstance(params.get("priority_in") or params.get("priority__in"), list)

    def test_limit_and_offset_build(self):
        """Test building query with pagination."""
        cypher, params = (
            query().for_model(Task).filter(status="active").limit(50).offset(10).build()
        )

        assert "LIMIT" in cypher
        assert "SKIP" in cypher
        assert params.get("limit") == 50
        assert params.get("skip") == 10

    def test_order_by_build(self):
        """Test building query with ordering."""
        cypher, params = (
            query().for_model(Task).filter(status="active").order_by("due_date", desc=True).build()
        )

        assert "ORDER BY" in cypher
        assert "DESC" in cypher
        assert "due_date" in cypher

    def test_list_query_without_filters(self):
        """Test building list query without filters."""
        cypher, params = query().for_model(Task).limit(100).build()

        assert "MATCH (n:Task)" in cypher or "MATCH (n:TaskPure)" in cypher
        assert "RETURN n" in cypher
        assert params.get("limit") == 100

    def test_fluent_chaining(self):
        """Test fluent method chaining."""
        builder = (
            query()
            .for_model(Task)
            .filter(priority="high")
            .filter(status="in_progress")  # Multiple filter calls
            .limit(25)
            .order_by("created_at", desc=True)
        )

        cypher, params = builder.build()

        assert "priority" in params
        assert "status" in params
        assert params.get("limit") == 25
        assert "ORDER BY" in cypher


class TestSemanticQueryBuilder:
    """Tests for semantic relationship queries."""

    def test_semantic_context_build(self):
        """Test building semantic context query."""
        cypher, params = (
            query()
            .semantic("ku.python_basics")
            .traverse(
                types=[
                    SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
                    SemanticRelationshipType.BUILDS_MENTAL_MODEL,
                ]
            )
            .depth(3)
            .min_confidence(0.8)
            .build()
        )

        assert "MATCH" in cypher
        assert params.get("uid") == "ku.python_basics"
        assert params.get("min_confidence") == 0.8

    def test_prerequisites_build(self):
        """Test building prerequisite chain query."""
        cypher, params = (
            query()
            .semantic("ku.advanced_python")
            .prerequisites()  # Changes query type
            .traverse(types=[SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION])
            .depth(5)
            .build()
        )

        assert "MATCH" in cypher
        assert params.get("uid") == "ku.advanced_python"
        # Prerequisites use different pattern than context

    def test_path_finding_build(self):
        """Test building shortest path query."""
        cypher, params = (
            query()
            .semantic("ku.python_basics")
            .path_to("ku.async_programming")
            .traverse(types=[SemanticRelationshipType.PROVIDES_FOUNDATION_FOR])
            .depth(5)
            .build()
        )

        assert "shortestPath" in cypher or "MATCH" in cypher
        assert params.get("start_uid") == "ku.python_basics"
        assert params.get("end_uid") == "ku.async_programming"

    def test_semantic_type_conversion(self):
        """Test that semantic types are converted to Neo4j names."""
        cypher, params = (
            query()
            .semantic("test.uid")
            .traverse(types=[SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING])
            .build()
        )

        # Should contain Neo4j relationship name
        assert "REQUIRES_THEORETICAL_UNDERSTANDING" in cypher


# TestBatchQueryBuilder removed - Pure Cypher migration (October 20, 2025)
# Batch operations now use Pure Cypher UNWIND patterns instead of APOC


class TestUnifiedQueryBuilder:
    """Tests for unified builder entry point."""

    def test_for_model_returns_model_builder(self):
        """Test that for_model returns ModelQueryBuilder."""
        builder = UnifiedQueryBuilder().for_model(Task)

        from core.models.query.unified_query_builder import ModelQueryBuilder

        assert isinstance(builder, ModelQueryBuilder)
        assert builder.model == Task

    def test_semantic_returns_semantic_builder(self):
        """Test that semantic returns SemanticQueryBuilder."""
        builder = UnifiedQueryBuilder().semantic("test.uid")

        from core.models.query.unified_query_builder import SemanticQueryBuilder

        assert isinstance(builder, SemanticQueryBuilder)
        assert builder.uid == "test.uid"

    def test_template_returns_template_builder(self):
        """Test that template returns TemplateQueryBuilder."""
        # Use a valid template name that exists in the default templates
        builder = UnifiedQueryBuilder().template("get_by_uid")

        from core.models.query.unified_query_builder import TemplateQueryBuilder

        assert isinstance(builder, TemplateQueryBuilder)
        assert builder.template_name == "get_by_uid"

    def test_convenience_factory(self):
        """Test convenience factory function."""
        builder = query()

        assert isinstance(builder, UnifiedQueryBuilder)

    def test_driver_not_required_for_build(self):
        """Test that driver is not required for build() operations."""
        # Should not raise - build() doesn't need driver
        cypher, params = query().for_model(Task).filter(status="active").build()

        assert cypher
        assert isinstance(params, dict)

    @pytest.mark.asyncio
    async def test_driver_required_for_execute(self):
        """Test that driver is required for execute() operations."""
        builder = query().for_model(Task).filter(status="active")

        # Should raise ValueError when trying to execute without driver
        with pytest.raises(ValueError, match="Driver is required"):
            await builder.execute()


class TestApiClarity:
    """Tests that demonstrate API clarity improvements."""

    def test_no_decision_matrix_needed(self):
        """Test that API is self-documenting."""
        # Before: Need to decide between CypherGenerator, ApocQueryBuilder, QueryBuilder
        # After: API tells you what to do

        builder = UnifiedQueryBuilder()

        # For model queries - obvious
        model_builder = builder.for_model(Task)
        assert model_builder is not None

        # For semantic queries - obvious
        semantic_builder = builder.semantic("uid")
        assert semantic_builder is not None

        # For templates - obvious (use a valid template name)
        template_builder = builder.template("get_by_uid")
        assert template_builder is not None

    def test_type_safety(self):
        """Test that generic types work correctly."""
        # ModelQueryBuilder[Task] should be type-safe
        builder = query().for_model(Task)

        # Should have correct model type
        assert builder.model == Task

    def test_fluent_api_readability(self):
        """Test that fluent chains are readable."""
        # The fluent API should read like natural language
        cypher, params = (
            query()
            .for_model(Task)
            .filter(priority="high")
            .filter(status="in_progress")
            .order_by("due_date", desc=True)
            .limit(10)
            .build()
        )

        # Should generate valid Cypher
        assert "MATCH" in cypher
        assert "WHERE" in cypher
        assert "ORDER BY" in cypher
        assert "LIMIT" in cypher


class TestBackwardCompatibility:
    """Tests that verify backward compatibility during migration."""

    def test_modular_cypher_functions_work(self):
        """Test that modular cypher functions work."""
        from core.models.query import build_search_query

        # Direct function import (one way forward)
        cypher, params = build_search_query(Task, {"priority": "high"})

        assert "MATCH" in cypher
        assert "priority" in params


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
