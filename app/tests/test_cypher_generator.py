"""
Tests for CypherGenerator - Consolidation
==================================================

Validates that CypherGenerator correctly consolidates functionality from:
- DynamicQueryBuilder (model introspection)
- SemanticCypherBuilder (semantic relationship queries)
"""

from dataclasses import dataclass
from datetime import date

import pytest

from core.models.query import (
    build_count_query,
    build_cross_domain_bridges,
    build_get_by_field_query,
    build_hierarchical_context,
    build_list_query,
    build_prerequisite_chain,
    build_search_query,
    build_semantic_context,
    build_semantic_filter_query,
    build_semantic_traversal,
    count,
    get_by,
    get_filterable_fields,
    get_supported_operators,
    list_entities,
    search,
)


# Test fixture models (avoid "Test" prefix to prevent pytest collection warnings)
@dataclass
class SampleTask:
    uid: str
    title: str
    priority: str
    status: str
    due_date: date | None = None
    estimated_hours: float | None = None


@dataclass
class SampleKnowledge:
    uid: str
    title: str
    domain: str
    level: int


class TestCypherGeneratorDynamic:
    """Test dynamic query generation from model introspection."""

    def test_build_search_query_simple_equality(self):
        """Test simple equality filters."""
        query, params = build_search_query(
            SampleTask, {"priority": "high", "status": "in_progress"}
        )

        assert "MATCH (n:SampleTask)" in query
        assert "WHERE" in query
        assert "n.priority = $priority" in query
        assert "n.status = $status" in query
        assert "RETURN n" in query
        assert params["priority"] == "high"
        assert params["status"] == "in_progress"

    def test_build_search_query_comparison_operators(self):
        """Test comparison operators (gte, lt, etc.)."""
        query, params = build_search_query(
            SampleTask, {"due_date__gte": date(2025, 10, 1), "estimated_hours__lt": 5.0}
        )

        assert "n.due_date >= $due_date_gte" in query
        assert "n.estimated_hours < $estimated_hours_lt" in query
        assert params["due_date_gte"] == "2025-10-01"  # Converted to ISO string
        assert params["estimated_hours_lt"] == 5.0

    def test_build_search_query_contains(self):
        """Test string contains operator."""
        query, params = build_search_query(SampleTask, {"title__contains": "urgent"})

        assert "n.title CONTAINS $title_contains" in query
        assert params["title_contains"] == "urgent"

    def test_build_search_query_in_operator(self):
        """Test IN operator for list membership."""
        query, params = build_search_query(
            SampleTask, {"priority__in": ["high", "urgent", "critical"]}
        )

        assert "n.priority IN $priority_in" in query
        assert params["priority_in"] == ["high", "urgent", "critical"]

    def test_build_get_by_field_query(self):
        """Test get by specific field."""
        query, params = build_get_by_field_query(SampleTask, "uid", "task-123")

        assert "MATCH (n:SampleTask)" in query
        assert "WHERE n.uid = $field_value" in query
        assert "RETURN n" in query
        assert params["field_value"] == "task-123"

    def test_build_list_query_with_ordering(self):
        """Test list query with ordering."""
        query, params = build_list_query(
            SampleTask, limit=50, skip=10, order_by="due_date", order_desc=True
        )

        assert "MATCH (n:SampleTask)" in query
        assert "ORDER BY n.due_date DESC" in query
        assert "SKIP $skip" in query
        assert "LIMIT $limit" in query
        assert params["limit"] == 50
        assert params["skip"] == 10

    def test_build_count_query_with_filters(self):
        """Test count query with filters."""
        query, params = build_count_query(SampleTask, {"priority": "high", "status": "completed"})

        assert "MATCH (n:SampleTask)" in query
        assert "WHERE" in query
        assert "n.priority = $priority" in query
        assert "n.status = $status" in query
        assert "RETURN count(n) as count" in query
        assert params["priority"] == "high"
        assert params["status"] == "completed"

    def test_build_count_query_no_filters(self):
        """Test count query without filters."""
        query, params = build_count_query(SampleTask)

        assert "MATCH (n:SampleTask)" in query
        assert "RETURN count(n) as count" in query
        assert params == {}

    def test_get_filterable_fields(self):
        """Test getting filterable fields from model."""
        fields = get_filterable_fields(SampleTask)

        assert "uid" in fields
        assert "title" in fields
        assert "priority" in fields
        assert "status" in fields
        assert "due_date" in fields
        assert "estimated_hours" in fields

    def test_get_supported_operators(self):
        """Test getting supported operators."""
        operators = get_supported_operators()

        assert "eq" in operators
        assert "gt" in operators
        assert "lt" in operators
        assert "gte" in operators
        assert "lte" in operators
        assert "contains" in operators
        assert "in" in operators


class TestCypherGeneratorSemantic:
    """Test semantic relationship query generation."""

    def test_build_semantic_context(self):
        """Test semantic context query building."""
        # Mock semantic relationship types
        from unittest.mock import Mock

        mock_type1 = Mock()
        mock_type1.to_neo4j_name.return_value = "REQUIRES_THEORETICAL_UNDERSTANDING"

        mock_type2 = Mock()
        mock_type2.to_neo4j_name.return_value = "BUILDS_MENTAL_MODEL"

        query, params = build_semantic_context(
            node_uid="ku.python_basics",
            semantic_types=[mock_type1, mock_type2],
            depth=2,
            min_confidence=0.8,
        )

        assert "MATCH (center {uid: $uid})" in query
        assert "REQUIRES_THEORETICAL_UNDERSTANDING|BUILDS_MENTAL_MODEL" in query
        assert "c >= $min_confidence" in query
        assert params["uid"] == "ku.python_basics"
        assert params["min_confidence"] == 0.8

    def test_build_prerequisite_chain(self):
        """Test prerequisite chain query building."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "REQUIRES_PRACTICAL_APPLICATION"

        query, params = build_prerequisite_chain(
            node_uid="ku.advanced_python", semantic_types=[mock_type], depth=5
        )

        assert "MATCH (target {uid: $uid})" in query
        assert "REQUIRES_PRACTICAL_APPLICATION" in query
        assert "*1..5" in query
        assert params["uid"] == "ku.advanced_python"

    def test_build_semantic_traversal(self):
        """Test semantic path finding."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "PROVIDES_FOUNDATION_FOR"

        query, params = build_semantic_traversal(
            start_uid="ku.python_basics",
            end_uid="ku.async_programming",
            semantic_types=[mock_type],
            max_depth=5,
        )

        assert "MATCH (start {uid: $start_uid})" in query
        assert "MATCH (end {uid: $end_uid})" in query
        assert "shortestPath" in query
        assert "PROVIDES_FOUNDATION_FOR" in query
        assert params["start_uid"] == "ku.python_basics"
        assert params["end_uid"] == "ku.async_programming"

    def test_build_hierarchical_context(self):
        """Test hierarchical context query building."""
        from unittest.mock import Mock

        mock_parent = Mock()
        mock_parent.to_neo4j_name.return_value = "REQUIRES_CONCEPTUAL_FOUNDATION"

        mock_child = Mock()
        mock_child.to_neo4j_name.return_value = "DEMONSTRATES_IN_PROJECT"

        query, params = build_hierarchical_context(
            node_uid="task.learn_react",
            parent_types=[mock_parent],
            child_types=[mock_child],
            depth=2,
        )

        assert "MATCH (center {uid: $uid})" in query
        assert "REQUIRES_CONCEPTUAL_FOUNDATION" in query
        assert "DEMONSTRATES_IN_PROJECT" in query
        assert "direction: 'parent'" in query
        assert "direction: 'child'" in query
        assert params["uid"] == "task.learn_react"

    def test_build_cross_domain_bridges(self):
        """Test cross-domain bridge query building."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "SHARES_PRINCIPLE_WITH"

        query, params = build_cross_domain_bridges(
            domain_a="programming", domain_b="mathematics", semantic_types=[mock_type], limit=10
        )

        assert "MATCH (a {domain: $domain_a})" in query
        assert "MATCH (b {domain: $domain_b})" in query
        assert "shortestPath" in query
        assert "SHARES_PRINCIPLE_WITH" in query
        assert "LIMIT $limit" in query
        assert params["domain_a"] == "programming"
        assert params["domain_b"] == "mathematics"
        assert params["limit"] == 10

    def test_build_semantic_filter_query_outgoing(self):
        """Test semantic filter query with outgoing direction."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "REQUIRES_THEORETICAL_UNDERSTANDING"

        query, params = build_semantic_filter_query(
            label="Entity",
            semantic_type=mock_type,
            min_confidence=0.8,
            direction="outgoing",
            limit=50,
        )

        assert "MATCH (n:Entity)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(target)" in query
        assert "r.confidence >= $min_confidence" in query
        assert "LIMIT $limit" in query
        assert params["min_confidence"] == 0.8
        assert params["limit"] == 50

    def test_build_semantic_filter_query_incoming(self):
        """Test semantic filter query with incoming direction."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "ENABLES"

        query, params = build_semantic_filter_query(
            label="Task", semantic_type=mock_type, direction="incoming"
        )

        assert "MATCH (n:Task)<-[r:ENABLES]-(source)" in query

    def test_build_semantic_filter_query_both(self):
        """Test semantic filter query with bidirectional."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "RELATED_TO"

        query, params = build_semantic_filter_query(
            label="Topic", semantic_type=mock_type, direction="both"
        )

        assert "MATCH (n:Topic)-[r:RELATED_TO]-(connected)" in query


class TestConvenienceFunctions:
    """Test convenience wrapper functions."""

    def test_search_convenience(self):
        """Test search() convenience function."""
        query, params = search(SampleTask, priority="high", status="in_progress")

        assert "MATCH (n:SampleTask)" in query
        assert "n.priority = $priority" in query
        assert params["priority"] == "high"

    def test_get_by_convenience(self):
        """Test get_by() convenience function."""
        query, params = get_by(SampleTask, "uid", "task-123")

        assert "MATCH (n:SampleTask)" in query
        assert "n.uid = $field_value" in query
        assert params["field_value"] == "task-123"

    def test_list_entities_convenience(self):
        """Test list_entities() convenience function."""
        query, params = list_entities(SampleTask, limit=50, order_by="created_at")

        assert "MATCH (n:SampleTask)" in query
        assert "LIMIT $limit" in query
        assert params["limit"] == 50

    def test_count_convenience(self):
        """Test count() convenience function."""
        query, params = count(SampleTask, priority="high", status="completed")

        assert "MATCH (n:SampleTask)" in query
        assert "RETURN count(n) as count" in query
        assert params["priority"] == "high"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_non_dataclass_raises_error(self):
        """Test that non-dataclass raises ValueError."""

        class NotADataclass:
            pass

        with pytest.raises(ValueError, match="must be a dataclass"):
            build_search_query(NotADataclass, {})

    def test_invalid_field_name_skips(self):
        """Test that invalid field names are skipped with warning."""
        query, params = build_search_query(
            SampleTask, {"invalid_field": "value", "priority": "high"}
        )

        # Should skip invalid_field but include priority
        assert "n.priority = $priority" in query
        assert "invalid_field" not in query
        assert params["priority"] == "high"

    def test_unknown_operator_skips(self):
        """Test that unknown operators are skipped with warning."""
        query, params = build_search_query(SampleTask, {"priority__unknown_op": "high"})

        # Should generate query but skip the unknown operator
        assert "MATCH (n:SampleTask)" in query
        # The WHERE clause should be empty or have default "1=1"
        assert "1=1" in query or "WHERE" not in query

    def test_custom_label(self):
        """Test using custom label instead of class name."""
        query, params = build_search_query(SampleTask, {"priority": "high"}, label="CustomTask")

        assert "MATCH (n:CustomTask)" in query
        assert "MATCH (n:SampleTask)" not in query

    def test_empty_filters_dict(self):
        """Test with empty filters dictionary."""
        query, params = build_search_query(SampleTask, {})

        assert "MATCH (n:SampleTask)" in query
        assert "WHERE 1=1" in query or "WHERE" not in query
        assert "RETURN n" in query

    def test_none_value_in_filters(self):
        """Test handling of None values in filters."""
        query, params = build_search_query(SampleTask, {"due_date": None, "priority": "high"})

        # Should handle None and still include valid filters
        assert "n.priority = $priority" in query
        assert params["priority"] == "high"

    def test_empty_string_filter(self):
        """Test handling of empty string filters."""
        query, params = build_search_query(SampleTask, {"title__contains": ""})

        assert "n.title CONTAINS $title_contains" in query
        assert params["title_contains"] == ""

    def test_very_large_limit(self):
        """Test with very large limit value."""
        query, params = build_list_query(SampleTask, limit=10000, skip=0)

        assert "LIMIT $limit" in query
        assert params["limit"] == 10000

    def test_zero_depth_semantic_context(self):
        """Test semantic context with depth=0."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "REQUIRES"

        # Depth 0 should still work but match no paths
        query, params = build_semantic_context(
            node_uid="ku.test", semantic_types=[mock_type], depth=0
        )

        # Should generate valid query even with depth=0
        assert "MATCH (center {uid: $uid})" in query

    def test_multiple_semantic_types(self):
        """Test with many semantic relationship types."""
        from unittest.mock import Mock

        # Create 10 different semantic types
        semantic_types = []
        for i in range(10):
            mock_type = Mock()
            mock_type.to_neo4j_name.return_value = f"SEMANTIC_TYPE_{i}"
            semantic_types.append(mock_type)

        query, params = build_semantic_context(
            node_uid="ku.test", semantic_types=semantic_types, depth=2
        )

        # All types should be in the relationship pattern
        for i in range(10):
            assert f"SEMANTIC_TYPE_{i}" in query

    def test_combined_comparison_operators(self):
        """Test combining multiple comparison operators."""
        query, params = build_search_query(
            SampleTask,
            {
                "estimated_hours__gte": 2.0,
                "estimated_hours__lte": 8.0,
                "due_date__gt": date(2025, 10, 1),
            },
        )

        assert "n.estimated_hours >= $estimated_hours_gte" in query
        assert "n.estimated_hours <= $estimated_hours_lte" in query
        assert "n.due_date > $due_date_gt" in query
        assert params["estimated_hours_gte"] == 2.0
        assert params["estimated_hours_lte"] == 8.0

    def test_empty_in_list(self):
        """Test IN operator with empty list."""
        query, params = build_search_query(SampleTask, {"priority__in": []})

        assert "n.priority IN $priority_in" in query
        assert params["priority_in"] == []

    def test_single_item_in_list(self):
        """Test IN operator with single item."""
        query, params = build_search_query(SampleTask, {"priority__in": ["high"]})

        assert "n.priority IN $priority_in" in query
        assert params["priority_in"] == ["high"]

    def test_special_characters_in_string_filter(self):
        """Test handling of special characters in string filters."""
        query, params = build_search_query(
            SampleTask, {"title__contains": "urgent: review Mike's code"}
        )

        assert "n.title CONTAINS $title_contains" in query
        assert params["title_contains"] == "urgent: review Mike's code"

    def test_order_by_invalid_field(self):
        """Test list query with invalid order_by field."""
        query, params = build_list_query(SampleTask, order_by="invalid_field", limit=50)

        # Should skip invalid order_by and still generate valid query
        assert "MATCH (n:SampleTask)" in query
        assert "ORDER BY" not in query  # Invalid field should be ignored

    def test_zero_confidence_semantic(self):
        """Test semantic query with 0.0 confidence threshold."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "REQUIRES"

        query, params = build_semantic_context(
            node_uid="ku.test", semantic_types=[mock_type], min_confidence=0.0
        )

        assert params["min_confidence"] == 0.0
        assert "c >= $min_confidence" in query

    def test_max_confidence_semantic(self):
        """Test semantic query with 1.0 confidence threshold."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "REQUIRES"

        query, params = build_semantic_context(
            node_uid="ku.test", semantic_types=[mock_type], min_confidence=1.0
        )

        assert params["min_confidence"] == 1.0

    def test_very_deep_semantic_traversal(self):
        """Test semantic traversal with very large depth."""
        from unittest.mock import Mock

        mock_type = Mock()
        mock_type.to_neo4j_name.return_value = "LEADS_TO"

        query, params = build_semantic_traversal(
            start_uid="ku.start", end_uid="ku.end", semantic_types=[mock_type], max_depth=100
        )

        assert "*1..100" in query

    def test_unicode_in_filters(self):
        """Test handling of Unicode characters in filters."""
        query, params = build_search_query(SampleTask, {"title__contains": "学习 Python 编程"})

        assert "n.title CONTAINS $title_contains" in query
        assert params["title_contains"] == "学习 Python 编程"

    def test_mixed_valid_invalid_semantic_types(self):
        """Test semantic query with mix of valid types and edge cases."""
        from unittest.mock import Mock

        valid_type = Mock()
        valid_type.to_neo4j_name.return_value = "VALID_TYPE"

        # Create semantic context with valid type
        query, params = build_semantic_context(
            node_uid="ku.test", semantic_types=[valid_type], depth=2, min_confidence=0.5
        )

        assert "VALID_TYPE" in query
        assert params["min_confidence"] == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
