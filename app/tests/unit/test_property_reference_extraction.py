"""
Tests for Property Reference Extraction
========================================

Tests the Cypher query parser that extracts property references
and classifies their usage (filter, lookup, return, sort, aggregate).

This is a foundational feature for query validation and optimization.
"""

from adapters.persistence.neo4j.query._query_models import (
    PropertyReference,
    _extract_property_references,
    analyze_query_intent,
)


class TestPropertyReferenceExtraction:
    """Tests for _extract_property_references function."""

    def test_simple_match_filter(self):
        """Test extracting property from simple MATCH with WHERE."""
        query = """
        MATCH (n:Task)
        WHERE n.priority = 'high'
        RETURN n
        """

        refs = _extract_property_references(query)

        assert len(refs) == 1
        assert refs[0].label == "Task"
        assert refs[0].property == "priority"
        assert refs[0].usage == "filter"

    def test_match_with_equality_lookup(self):
        """Test MATCH clause with equality should be classified as lookup."""
        query = """
        MATCH (n:Task {uid: $uid})
        RETURN n
        """

        refs = _extract_property_references(query)

        # uid in MATCH with = is a lookup (indexed)
        assert len(refs) >= 1
        uid_ref = next((r for r in refs if r.property == "uid"), None)
        assert uid_ref is not None
        assert uid_ref.label == "Task"
        assert uid_ref.usage == "lookup"

    def test_return_clause(self):
        """Test property in RETURN clause."""
        query = """
        MATCH (n:Task)
        RETURN n.title, n.priority
        """

        refs = _extract_property_references(query)

        assert len(refs) == 2
        title_ref = next((r for r in refs if r.property == "title"), None)
        priority_ref = next((r for r in refs if r.property == "priority"), None)

        assert title_ref is not None
        assert title_ref.usage == "return"
        assert priority_ref is not None
        assert priority_ref.usage == "return"

    def test_order_by_clause(self):
        """Test property in ORDER BY clause."""
        query = """
        MATCH (n:Task)
        RETURN n
        ORDER BY n.priority DESC, n.due_date ASC
        """

        refs = _extract_property_references(query)

        assert len(refs) == 2
        priority_ref = next((r for r in refs if r.property == "priority"), None)
        due_date_ref = next((r for r in refs if r.property == "due_date"), None)

        assert priority_ref is not None
        assert priority_ref.usage == "sort"
        assert due_date_ref is not None
        assert due_date_ref.usage == "sort"

    def test_aggregation_functions(self):
        """Test properties used in aggregation functions."""
        query = """
        MATCH (n:Task)
        RETURN COUNT(n.uid), SUM(n.estimated_hours), AVG(n.completion_percentage)
        """

        refs = _extract_property_references(query)

        assert len(refs) == 3

        # All should be classified as aggregate
        for ref in refs:
            assert ref.usage == "aggregate"

        # Check specific properties
        properties = {ref.property for ref in refs}
        assert "uid" in properties
        assert "estimated_hours" in properties
        assert "completion_percentage" in properties

    def test_complex_query_multiple_usages(self):
        """Test complex query with properties in multiple contexts."""
        query = """
        MATCH (t:Task)
        WHERE t.status = 'active' AND t.priority = 'high'
        RETURN t.uid, t.title, COUNT(t.uid) as task_count
        ORDER BY t.created_at DESC
        """

        refs = _extract_property_references(query)

        # Should have references for: status, priority, uid (x2), title, created_at
        assert len(refs) >= 5

        # Check each property's usage
        status_refs = [r for r in refs if r.property == "status"]
        assert len(status_refs) == 1
        assert status_refs[0].usage == "filter"

        priority_refs = [r for r in refs if r.property == "priority"]
        assert len(priority_refs) == 1
        assert priority_refs[0].usage == "filter"

        # uid appears twice - once in return, once in aggregate
        uid_refs = [r for r in refs if r.property == "uid"]
        assert len(uid_refs) == 2
        usages = {r.usage for r in uid_refs}
        assert "return" in usages
        assert "aggregate" in usages

        # title in return
        title_refs = [r for r in refs if r.property == "title"]
        assert len(title_refs) == 1
        assert title_refs[0].usage == "return"

        # created_at in order by
        created_refs = [r for r in refs if r.property == "created_at"]
        assert len(created_refs) == 1
        assert created_refs[0].usage == "sort"

    def test_multiple_labels(self):
        """Test extracting properties from query with multiple labels."""
        query = """
        MATCH (u:User)-[:OWNS]->(t:Task)
        WHERE u.uid = $user_uid AND t.status = 'active'
        RETURN u.name, t.title
        """

        refs = _extract_property_references(query)

        assert len(refs) == 4

        # Check User properties
        user_refs = [r for r in refs if r.label == "User"]
        assert len(user_refs) == 2
        uid_ref = next((r for r in user_refs if r.property == "uid"), None)
        name_ref = next((r for r in user_refs if r.property == "name"), None)
        assert uid_ref is not None
        assert uid_ref.usage == "filter"
        assert name_ref is not None
        assert name_ref.usage == "return"

        # Check Task properties
        task_refs = [r for r in refs if r.label == "Task"]
        assert len(task_refs) == 2
        status_ref = next((r for r in task_refs if r.property == "status"), None)
        title_ref = next((r for r in task_refs if r.property == "title"), None)
        assert status_ref is not None
        assert status_ref.usage == "filter"
        assert title_ref is not None
        assert title_ref.usage == "return"

    def test_label_inference(self):
        """Test that variable-to-label mapping works correctly."""
        query = """
        MATCH (task:Task)
        WHERE task.priority = 'high'
        RETURN task.title
        """

        refs = _extract_property_references(query)

        assert len(refs) == 2
        for ref in refs:
            assert ref.label == "Task"

    def test_no_properties(self):
        """Test query with no property references."""
        query = """
        MATCH (n:Task)
        RETURN n
        """

        refs = _extract_property_references(query)

        assert len(refs) == 0

    def test_property_in_relationship(self):
        """Test extracting properties from relationship patterns."""
        query = """
        MATCH (n:Task)-[r:DEPENDS_ON]->(m:Task)
        WHERE r.strength > 0.5
        RETURN r.strength
        """

        refs = _extract_property_references(query)

        # Should extract r.strength (twice - once in WHERE, once in RETURN)
        assert len(refs) >= 2
        strength_refs = [r for r in refs if r.property == "strength"]
        assert len(strength_refs) == 2

        # One should be filter, one should be return
        usages = {r.usage for r in strength_refs}
        assert "filter" in usages
        assert "return" in usages


class TestAnalyzeQueryIntentIntegration:
    """Tests for property reference integration with analyze_query_intent."""

    def test_intent_includes_property_refs(self):
        """Test that analyze_query_intent populates property_references."""
        query = """
        MATCH (n:Task)
        WHERE n.priority = 'high'
        RETURN n.title
        ORDER BY n.due_date
        """

        elements = analyze_query_intent(query)

        # Should have extracted property references
        assert len(elements.property_references) == 3

        # Check properties
        properties = {ref.property for ref in elements.property_references}
        assert "priority" in properties
        assert "title" in properties
        assert "due_date" in properties

        # Check usages
        priority_ref = next(
            (r for r in elements.property_references if r.property == "priority"), None
        )
        assert priority_ref is not None
        assert priority_ref.usage == "filter"

        title_ref = next((r for r in elements.property_references if r.property == "title"), None)
        assert title_ref is not None
        assert title_ref.usage == "return"

        due_date_ref = next(
            (r for r in elements.property_references if r.property == "due_date"), None
        )
        assert due_date_ref is not None
        assert due_date_ref.usage == "sort"

    def test_empty_query_has_empty_refs(self):
        """Test that simple query without properties has empty list."""
        query = "MATCH (n:Task) RETURN n"

        elements = analyze_query_intent(query)

        assert elements.property_references == []

    def test_property_refs_preserved_in_elements(self):
        """Test that property references are preserved through QueryElements."""
        query = """
        MATCH (n:Task)
        WHERE n.status = 'active'
        RETURN COUNT(n.uid)
        """

        elements = analyze_query_intent(query)

        assert len(elements.property_references) == 2

        # Verify PropertyReference objects are valid
        for ref in elements.property_references:
            assert isinstance(ref, PropertyReference)
            assert ref.property in ["status", "uid"]
            assert ref.usage in ["filter", "aggregate"]
            assert ref.label == "Task"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_malformed_query(self):
        """Test that malformed queries don't crash the parser."""
        query = "MATCH (n:Task WHERE n.priority"

        # Should not raise exception
        refs = _extract_property_references(query)

        # May extract partial info or nothing
        assert isinstance(refs, list)

    def test_case_insensitive_keywords(self):
        """Test that keyword detection is case-insensitive."""
        query = """
        match (n:Task)
        where n.priority = 'high'
        return n.title
        order by n.due_date
        """

        refs = _extract_property_references(query)

        assert len(refs) == 3

        # Check that usage classification worked despite lowercase keywords
        usages = {ref.usage for ref in refs}
        assert "filter" in usages
        assert "return" in usages
        assert "sort" in usages

    def test_whitespace_variations(self):
        """Test that parser handles various whitespace patterns."""
        query = """
        MATCH(n:Task)WHERE n . priority='high'RETURN n.title ORDER BY n.due_date
        """

        refs = _extract_property_references(query)

        # Should still extract properties despite minimal whitespace
        assert len(refs) >= 3
        properties = {ref.property for ref in refs}
        assert "priority" in properties
        assert "title" in properties
        assert "due_date" in properties

    def test_numeric_property_names(self):
        """Test properties with numbers in their names."""
        query = """
        MATCH (n:Task)
        WHERE n.priority_level_1 > 5
        RETURN n.field_2
        """

        refs = _extract_property_references(query)

        assert len(refs) == 2
        properties = {ref.property for ref in refs}
        assert "priority_level_1" in properties
        assert "field_2" in properties

    def test_underscore_property_names(self):
        """Test properties with underscores."""
        query = """
        MATCH (n:Task)
        WHERE n.due_date_time > $now
        RETURN n.created_at_timestamp
        """

        refs = _extract_property_references(query)

        assert len(refs) == 2
        properties = {ref.property for ref in refs}
        assert "due_date_time" in properties
        assert "created_at_timestamp" in properties
