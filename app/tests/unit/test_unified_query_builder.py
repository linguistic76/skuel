"""
Tests for Unified Query Builder
================================

Tests the fluent API facade that eliminates query builder confusion.
"""

from datetime import date

import pytest

from adapters.persistence.neo4j.query import UnifiedQueryBuilder, query
from core.models.task.task import Task as Task


class TestModelQueryBuilder:
    """Tests for model-based queries."""

    def test_simple_filter_build(self):
        """Test building simple filter query."""
        cypher, params = (
            query().for_model(Task).filter(priority="high", status="in_progress").build()
        )

        assert "MATCH (n:Entity)" in cypher
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
        cypher, _params = (
            query().for_model(Task).filter(status="active").order_by("due_date", desc=True).build()
        )

        assert "ORDER BY" in cypher
        assert "DESC" in cypher
        assert "due_date" in cypher

    def test_list_query_without_filters(self):
        """Test building list query without filters."""
        cypher, params = query().for_model(Task).limit(100).build()

        assert "MATCH (n:Entity)" in cypher
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


# TestBatchQueryBuilder removed - Pure Cypher migration (October 20, 2025)
# Batch operations now use Pure Cypher UNWIND patterns instead of APOC


class TestUnifiedQueryBuilder:
    """Tests for unified builder entry point."""

    def test_for_model_returns_model_builder(self):
        """Test that for_model returns ModelQueryBuilder."""
        builder = UnifiedQueryBuilder().for_model(Task)

        from adapters.persistence.neo4j.query.unified_query_builder import ModelQueryBuilder

        assert isinstance(builder, ModelQueryBuilder)
        assert builder.model == Task

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
        with pytest.raises(ValueError, match="Executor is required"):
            await builder.execute()


class TestApiClarity:
    """Tests that demonstrate API clarity improvements."""

    def test_entry_point_is_self_documenting(self):
        """for_model() names what it does — no decision matrix needed."""
        builder = UnifiedQueryBuilder()

        model_builder = builder.for_model(Task)
        assert model_builder is not None

    def test_type_safety(self):
        """Test that generic types work correctly."""
        # ModelQueryBuilder[Task] should be type-safe
        builder = query().for_model(Task)

        # Should have correct model type
        assert builder.model == Task

    def test_fluent_api_readability(self):
        """Test that fluent chains are readable."""
        # The fluent API should read like natural language
        cypher, _params = (
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
        from adapters.persistence.neo4j.query import build_search_query

        # Direct function import (one way forward)
        cypher, params = build_search_query(Task, {"priority": "high"})

        assert "MATCH" in cypher
        assert "priority" in params


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
