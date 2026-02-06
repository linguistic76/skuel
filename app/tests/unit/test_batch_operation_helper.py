"""
Tests for BatchOperationHelper - centralized batch operation utilities.

Tests cover:
1. build_relationship_exists_query() - UNWIND existence checks
2. build_relationship_count_query() - UNWIND count queries
3. build_relationship_properties_query() - Relationship property retrieval
4. build_relationship_delete_query() - Batch delete queries
5. build_multi_direction_count_queries() - Multi-direction count optimization
6. build_relationships_list() - Flattening UID lists into tuples
7. group_relationships_by_type() - Group by type for pure Cypher batch
8. build_relationship_create_query() - Pure Cypher UNWIND query per type
9. build_relationship_create_queries() - Full batch query builder
"""

import pytest

from core.infrastructure.batch import BatchOperationHelper, BatchQueryResult


class TestBuildRelationshipExistsQuery:
    """Tests for build_relationship_exists_query()."""

    def test_outgoing_direction(self):
        """Test building exists query for outgoing relationships."""
        result = BatchOperationHelper.build_relationship_exists_query(
            node_label="Task",
            relationship_types=["APPLIES_KNOWLEDGE", "REQUIRES_KNOWLEDGE"],
            direction="outgoing",
        )

        assert isinstance(result, BatchQueryResult)
        assert "UNWIND $uids as uid" in result.query
        assert "(n)-[r]->(related)" in result.query
        assert "relationship_types" in result.params
        assert result.params["relationship_types"] == [
            "APPLIES_KNOWLEDGE",
            "REQUIRES_KNOWLEDGE",
        ]

    def test_incoming_direction(self):
        """Test building exists query for incoming relationships."""
        result = BatchOperationHelper.build_relationship_exists_query(
            node_label="Goal",
            relationship_types=["SUPPORTS_GOAL"],
            direction="incoming",
        )

        assert "(n)<-[r]-(related)" in result.query

    def test_both_direction(self):
        """Test building exists query for both directions."""
        result = BatchOperationHelper.build_relationship_exists_query(
            node_label="Ku",
            relationship_types=["RELATED_TO"],
            direction="both",
        )

        assert "(n)-[r]-(related)" in result.query


class TestBuildRelationshipCountQuery:
    """Tests for build_relationship_count_query()."""

    def test_outgoing_count(self):
        """Test building count query for outgoing relationships."""
        result = BatchOperationHelper.build_relationship_count_query(
            node_label="Task",
            relationship_types=["APPLIES_KNOWLEDGE"],
            direction="outgoing",
        )

        assert "count" in result.query.lower()
        assert "(n)-[r]->(related)" in result.query

    def test_incoming_count(self):
        """Test building count query for incoming relationships."""
        result = BatchOperationHelper.build_relationship_count_query(
            node_label="Goal",
            relationship_types=["FULFILLS_GOAL"],
            direction="incoming",
        )

        assert "(n)<-[r]-(related)" in result.query

    def test_both_direction_count(self):
        """Test building count query for both directions."""
        result = BatchOperationHelper.build_relationship_count_query(
            node_label="Principle",
            relationship_types=["RELATED_TO"],
            direction="both",
        )

        assert "(n)-[r]-(related)" in result.query


class TestBuildRelationshipPropertiesQuery:
    """Tests for build_relationship_properties_query()."""

    def test_basic_properties_query(self):
        """Test building properties query for relationships."""
        relationships = [
            ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
            ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
        ]
        result = BatchOperationHelper.build_relationship_properties_query(
            relationships=relationships
        )

        assert isinstance(result, BatchQueryResult)
        assert "UNWIND $rels as rel" in result.query
        assert "properties(r)" in result.query
        assert len(result.params["rels"]) == 2

    def test_empty_relationships(self):
        """Test properties query with empty list."""
        result = BatchOperationHelper.build_relationship_properties_query(relationships=[])

        assert result.params["rels"] == []


class TestBuildRelationshipDeleteQuery:
    """Tests for build_relationship_delete_query()."""

    def test_basic_delete_query(self):
        """Test building delete query for relationships."""
        relationships = [
            ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
        ]
        result = BatchOperationHelper.build_relationship_delete_query(relationships=relationships)

        assert isinstance(result, BatchQueryResult)
        assert "DELETE r" in result.query
        assert "UNWIND $rels as rel" in result.query

    def test_multiple_relationships_delete(self):
        """Test delete query with multiple relationships."""
        relationships = [
            ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
            ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
        ]
        result = BatchOperationHelper.build_relationship_delete_query(relationships=relationships)

        assert len(result.params["rels"]) == 2


class TestBuildMultiDirectionCountQueries:
    """Tests for build_multi_direction_count_queries()."""

    def test_groups_by_direction(self):
        """Test that queries are grouped by direction."""
        requests = [
            ("task:1", "DEPENDS_ON", "outgoing"),
            ("task:2", "DEPENDS_ON", "outgoing"),
            ("goal:1", "SUPPORTS_GOAL", "incoming"),
        ]

        results = BatchOperationHelper.build_multi_direction_count_queries(requests=requests)

        # Should have entries for outgoing and incoming
        assert isinstance(results, dict)
        assert "outgoing" in results or "incoming" in results

    def test_single_direction(self):
        """Test with all same direction."""
        requests = [
            ("task:1", "DEPENDS_ON", "outgoing"),
            ("task:2", "DEPENDS_ON", "outgoing"),
        ]

        results = BatchOperationHelper.build_multi_direction_count_queries(requests=requests)

        # Should only have outgoing
        assert "outgoing" in results


class TestBuildRelationshipsList:
    """Tests for build_relationships_list()."""

    def test_basic_relationships(self):
        """Test building relationships list from UID lists."""
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid="task:123",
            relationship_specs=[
                (["ku:1", "ku:2"], "APPLIES_KNOWLEDGE", None),
                (["ku:3"], "REQUIRES_KNOWLEDGE", None),
            ],
        )

        assert len(relationships) == 3
        assert ("task:123", "ku:1", "APPLIES_KNOWLEDGE", None) in relationships
        assert ("task:123", "ku:2", "APPLIES_KNOWLEDGE", None) in relationships
        assert ("task:123", "ku:3", "REQUIRES_KNOWLEDGE", None) in relationships

    def test_with_properties(self):
        """Test building relationships with properties."""
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid="goal:456",
            relationship_specs=[
                (["habit:1"], "REQUIRES_HABIT", {"essentiality": "essential"}),
                (["habit:2"], "REQUIRES_HABIT", {"essentiality": "critical"}),
            ],
        )

        assert len(relationships) == 2
        assert (
            "goal:456",
            "habit:1",
            "REQUIRES_HABIT",
            {"essentiality": "essential"},
        ) in relationships
        assert (
            "goal:456",
            "habit:2",
            "REQUIRES_HABIT",
            {"essentiality": "critical"},
        ) in relationships

    def test_empty_lists_ignored(self):
        """Test that empty or None lists are ignored."""
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid="task:789",
            relationship_specs=[
                (None, "APPLIES_KNOWLEDGE", None),
                ([], "REQUIRES_KNOWLEDGE", None),
                (["ku:1"], "RELATED_TO", None),
            ],
        )

        assert len(relationships) == 1
        assert ("task:789", "ku:1", "RELATED_TO", None) in relationships

    def test_all_empty_returns_empty(self):
        """Test that all empty specs returns empty list."""
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid="task:000",
            relationship_specs=[
                (None, "APPLIES_KNOWLEDGE", None),
                ([], "REQUIRES_KNOWLEDGE", None),
            ],
        )

        assert relationships == []

    def test_mixed_with_and_without_properties(self):
        """Test mixing relationships with and without properties."""
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid="goal:abc",
            relationship_specs=[
                (["ku:1", "ku:2"], "REQUIRES_KNOWLEDGE", None),
                (["habit:1"], "REQUIRES_HABIT", {"essentiality": "essential"}),
                (["lp:1"], "ALIGNED_WITH_PATH", None),
            ],
        )

        assert len(relationships) == 4
        # Check None properties
        assert ("goal:abc", "ku:1", "REQUIRES_KNOWLEDGE", None) in relationships
        # Check dict properties
        assert (
            "goal:abc",
            "habit:1",
            "REQUIRES_HABIT",
            {"essentiality": "essential"},
        ) in relationships


class TestGroupRelationshipsByType:
    """Tests for group_relationships_by_type() - Pure Cypher batch grouping."""

    def test_single_type(self):
        """Test grouping relationships of a single type."""
        relationships = [
            ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
            ("task:1", "ku:b", "APPLIES_KNOWLEDGE", {"confidence": 0.9}),
        ]

        grouped = BatchOperationHelper.group_relationships_by_type(relationships)

        assert len(grouped) == 1
        assert "APPLIES_KNOWLEDGE" in grouped
        assert len(grouped["APPLIES_KNOWLEDGE"]) == 2
        assert ("task:1", "ku:a", {}) in grouped["APPLIES_KNOWLEDGE"]
        assert ("task:1", "ku:b", {"confidence": 0.9}) in grouped["APPLIES_KNOWLEDGE"]

    def test_multiple_types(self):
        """Test grouping relationships of multiple types."""
        relationships = [
            ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
            ("task:1", "goal:1", "FULFILLS_GOAL", None),
            ("task:1", "ku:b", "APPLIES_KNOWLEDGE", None),
            ("task:1", "goal:2", "FULFILLS_GOAL", {"priority": "high"}),
        ]

        grouped = BatchOperationHelper.group_relationships_by_type(relationships)

        assert len(grouped) == 2
        assert "APPLIES_KNOWLEDGE" in grouped
        assert "FULFILLS_GOAL" in grouped
        assert len(grouped["APPLIES_KNOWLEDGE"]) == 2
        assert len(grouped["FULFILLS_GOAL"]) == 2

    def test_empty_relationships(self):
        """Test grouping empty list."""
        grouped = BatchOperationHelper.group_relationships_by_type([])

        assert grouped == {}

    def test_none_properties_converted_to_empty_dict(self):
        """Test that None properties become empty dict."""
        relationships = [
            ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
        ]

        grouped = BatchOperationHelper.group_relationships_by_type(relationships)

        # Properties should be empty dict, not None
        assert grouped["APPLIES_KNOWLEDGE"][0] == ("task:1", "ku:a", {})


class TestBuildRelationshipCreateQuery:
    """Tests for build_relationship_create_query() - Pure Cypher query generation."""

    def test_generates_unwind_query(self):
        """Test that query uses UNWIND pattern."""
        query = BatchOperationHelper.build_relationship_create_query("APPLIES_KNOWLEDGE")

        assert "UNWIND $rels AS rel" in query
        assert "MATCH (a {uid: rel.from_uid})" in query
        assert "MATCH (b {uid: rel.to_uid})" in query

    def test_uses_literal_relationship_type(self):
        """Test that relationship type is literal in query (not parameterized)."""
        query = BatchOperationHelper.build_relationship_create_query("SUPPORTS_GOAL")

        # Relationship type should be literal, not a parameter
        assert "MERGE (a)-[r:SUPPORTS_GOAL]->(b)" in query
        # Should NOT use type() function or parameter
        assert "type(r)" not in query
        assert "$rel_type" not in query

    def test_sets_properties(self):
        """Test that query sets relationship properties."""
        query = BatchOperationHelper.build_relationship_create_query("RELATED_TO")

        assert "SET r += rel.properties" in query

    def test_returns_count(self):
        """Test that query returns created count."""
        query = BatchOperationHelper.build_relationship_create_query("DEPENDS_ON")

        assert "RETURN count(r) as created_count" in query


class TestBuildRelationshipCreateQueries:
    """Tests for build_relationship_create_queries() - Full batch query builder."""

    def test_single_relationship_type(self):
        """Test building queries for single relationship type."""
        relationships = [
            ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
            ("task:1", "ku:b", "APPLIES_KNOWLEDGE", {"confidence": 0.9}),
        ]

        queries = BatchOperationHelper.build_relationship_create_queries(relationships)

        assert len(queries) == 1  # One query per type
        query, rels_data = queries[0]

        assert "APPLIES_KNOWLEDGE" in query
        assert len(rels_data) == 2
        assert {"from_uid": "task:1", "to_uid": "ku:a", "properties": {}} in rels_data
        assert {
            "from_uid": "task:1",
            "to_uid": "ku:b",
            "properties": {"confidence": 0.9},
        } in rels_data

    def test_multiple_relationship_types(self):
        """Test building queries for multiple relationship types."""
        relationships = [
            ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
            ("task:1", "goal:1", "FULFILLS_GOAL", None),
            ("task:1", "ku:b", "APPLIES_KNOWLEDGE", None),
        ]

        queries = BatchOperationHelper.build_relationship_create_queries(relationships)

        assert len(queries) == 2  # One query per type

        # Extract queries by type
        query_by_type = {}
        for query, rels_data in queries:
            if "APPLIES_KNOWLEDGE" in query:
                query_by_type["APPLIES_KNOWLEDGE"] = (query, rels_data)
            elif "FULFILLS_GOAL" in query:
                query_by_type["FULFILLS_GOAL"] = (query, rels_data)

        assert "APPLIES_KNOWLEDGE" in query_by_type
        assert "FULFILLS_GOAL" in query_by_type
        assert len(query_by_type["APPLIES_KNOWLEDGE"][1]) == 2
        assert len(query_by_type["FULFILLS_GOAL"][1]) == 1

    def test_empty_relationships(self):
        """Test that empty list returns empty queries."""
        queries = BatchOperationHelper.build_relationship_create_queries([])

        assert queries == []

    def test_rels_data_format(self):
        """Test that rels_data has correct format for Neo4j."""
        relationships = [
            ("report:123", "goal:456", "SUPPORTS_GOAL", None),
        ]

        queries = BatchOperationHelper.build_relationship_create_queries(relationships)

        _, rels_data = queries[0]

        # Each entry should have from_uid, to_uid, properties
        assert len(rels_data) == 1
        entry = rels_data[0]
        assert "from_uid" in entry
        assert "to_uid" in entry
        assert "properties" in entry
        assert entry["from_uid"] == "report:123"
        assert entry["to_uid"] == "goal:456"
        assert entry["properties"] == {}


class TestBatchQueryResult:
    """Tests for BatchQueryResult dataclass."""

    def test_dataclass_creation(self):
        """Test creating BatchQueryResult."""
        result = BatchQueryResult(
            query="MATCH (n) RETURN n",
            params={"uid": "test"},
        )

        assert result.query == "MATCH (n) RETURN n"
        assert result.params == {"uid": "test"}

    def test_immutable_dataclass(self):
        """Test that BatchQueryResult is a frozen dataclass."""
        result = BatchQueryResult(query="test", params={})

        # Should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            result.query = "modified"
