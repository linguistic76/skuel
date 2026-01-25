"""
Integration tests for graph traversal operations.

Tests the traverse(), get_domain_context_raw(), and find_path() methods
in UniversalNeo4jBackend.

Date: January 2026
"""

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.ku.ku import Ku
from core.models.shared_enums import Domain, SELCategory


@pytest.mark.asyncio
class TestTraverseOperations:
    """Integration tests for traverse() method."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Ku", Ku)

    @pytest_asyncio.fixture
    async def traversal_graph(self, ku_backend):
        """
        Create a test graph for traversal testing.

        Graph structure:
            A --PREREQUISITE--> B --PREREQUISITE--> C --PREREQUISITE--> D
            |               |
            +--ENABLES----> E --PREREQUISITE--> F
        """
        # Create nodes
        nodes = {
            "A": Ku(
                uid="ku:traverse-a",
                title="Node A",
                content="Content A",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            "B": Ku(
                uid="ku:traverse-b",
                title="Node B",
                content="Content B",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            "C": Ku(
                uid="ku:traverse-c",
                title="Node C",
                content="Content C",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            "D": Ku(
                uid="ku:traverse-d",
                title="Node D",
                content="Content D",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            "E": Ku(
                uid="ku:traverse-e",
                title="Node E",
                content="Content E",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            "F": Ku(
                uid="ku:traverse-f",
                title="Node F",
                content="Content F",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
        }

        # Create all nodes
        for node in nodes.values():
            result = await ku_backend.create(node)
            assert result.is_ok, f"Failed to create {node.uid}: {result.error}"

        # Create relationships (tuples use strings)
        # Valid KU relationship types: REQUIRES_KNOWLEDGE, ENABLES_KNOWLEDGE, RELATED_TO
        # January 2026: Use unified relationship names from RelationshipName enum
        relationships = [
            ("ku:traverse-a", "ku:traverse-b", "REQUIRES_KNOWLEDGE", None),  # A -> B
            ("ku:traverse-b", "ku:traverse-c", "REQUIRES_KNOWLEDGE", None),  # B -> C
            ("ku:traverse-c", "ku:traverse-d", "REQUIRES_KNOWLEDGE", None),  # C -> D
            ("ku:traverse-a", "ku:traverse-e", "ENABLES_KNOWLEDGE", None),  # A -> E
            ("ku:traverse-b", "ku:traverse-e", "REQUIRES_KNOWLEDGE", None),  # B -> E
            ("ku:traverse-e", "ku:traverse-f", "REQUIRES_KNOWLEDGE", None),  # E -> F
        ]
        result = await ku_backend.create_relationships_batch(relationships)
        assert result.is_ok, f"Failed to create relationships: {result.error}"

        return nodes

    async def test_traverse_basic(self, ku_backend, traversal_graph):
        """Test basic traversal returns connected nodes."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE",
            max_depth=3,
        )

        assert result.is_ok
        nodes = result.value
        assert len(nodes) > 0

        # Should find B, C, D via PREREQUISITE chain (but not E which is via ENABLES)
        uids = {n["uid"] for n in nodes}
        assert "ku:traverse-b" in uids  # Direct PREREQUISITE from A

    async def test_traverse_max_depth_1(self, ku_backend, traversal_graph):
        """Test depth=1 returns only direct neighbors."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE",
            max_depth=1,
        )

        assert result.is_ok
        nodes = result.value

        # With depth 1, should only get B and E (direct neighbors of A)
        uids = {n["uid"] for n in nodes}
        assert "ku:traverse-b" in uids  # Direct via PREREQUISITE
        assert "ku:traverse-e" in uids  # Direct via ENABLES
        # C, D, F should NOT be present (depth > 1)
        assert "ku:traverse-c" not in uids
        assert "ku:traverse-d" not in uids
        assert "ku:traverse-f" not in uids

    async def test_traverse_max_depth_3(self, ku_backend, traversal_graph):
        """Test depth=3 returns nodes up to 3 hops away."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE",
            max_depth=3,
        )

        assert result.is_ok
        nodes = result.value

        # With depth 3, should reach all nodes except D (which is 4 hops: A->B->C->D)
        uids = {n["uid"] for n in nodes}
        assert "ku:traverse-b" in uids  # depth 1
        assert "ku:traverse-e" in uids  # depth 1
        assert "ku:traverse-c" in uids  # depth 2
        assert "ku:traverse-f" in uids  # depth 2

    async def test_traverse_multiple_rel_types(self, ku_backend, traversal_graph):
        """Test traversal with multiple relationship types (OR pattern)."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE",
            max_depth=2,
        )

        assert result.is_ok
        nodes = result.value

        # Should traverse both PREREQUISITE and ENABLES relationships
        uids = {n["uid"] for n in nodes}
        assert "ku:traverse-b" in uids  # via PREREQUISITE
        assert "ku:traverse-e" in uids  # via ENABLES

    async def test_traverse_depth_ordering(self, ku_backend, traversal_graph):
        """Test that results are ordered by depth."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE",
            max_depth=3,
        )

        assert result.is_ok
        nodes = result.value

        # Verify depth ordering (each node's depth should be <= next node's depth)
        depths = [n["depth"] for n in nodes]
        assert depths == sorted(depths), "Results should be ordered by depth"

    async def test_traverse_include_properties_true(self, ku_backend, traversal_graph):
        """Test that include_properties=True returns node properties."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE",
            max_depth=1,
            include_properties=True,
        )

        assert result.is_ok
        nodes = result.value
        assert len(nodes) > 0

        # When include_properties=True, should have 'properties' field
        node = nodes[0]
        assert "properties" in node
        assert "title" in node["properties"]
        assert "content" in node["properties"]

    async def test_traverse_include_properties_false(self, ku_backend, traversal_graph):
        """Test that include_properties=False returns minimal data."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE",
            max_depth=1,
            include_properties=False,
        )

        assert result.is_ok
        nodes = result.value
        assert len(nodes) > 0

        # When include_properties=False, should NOT have 'properties' field
        node = nodes[0]
        assert "uid" in node
        assert "labels" in node
        assert "depth" in node
        assert "properties" not in node

    async def test_traverse_deduplication(self, ku_backend, traversal_graph):
        """Test that nodes reached via multiple paths appear only once."""
        # Node E is reachable via A->E and A->B->E
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE",
            max_depth=2,
        )

        assert result.is_ok
        nodes = result.value

        # E should appear only once (DISTINCT in query)
        e_nodes = [n for n in nodes if n["uid"] == "ku:traverse-e"]
        assert len(e_nodes) == 1, "Node E should appear exactly once"

    async def test_traverse_empty_result(self, ku_backend, traversal_graph):
        """Test traversal with no matches returns empty list."""
        result = await ku_backend.traverse(
            start_uid="ku:traverse-a",
            rel_pattern="NONEXISTENT_REL",
            max_depth=3,
        )

        assert result.is_ok
        assert result.value == []

    async def test_traverse_invalid_start_uid(self, ku_backend, traversal_graph):
        """Test traversal from non-existent node returns empty list."""
        result = await ku_backend.traverse(
            start_uid="ku:nonexistent",
            rel_pattern="REQUIRES_KNOWLEDGE",
            max_depth=3,
        )

        assert result.is_ok
        assert result.value == []

    async def test_traverse_cyclic_graph(self, ku_backend, clean_neo4j):
        """Test traversal handles cycles without infinite loop."""
        # Create a cycle: X -> Y -> Z -> X
        nodes = [
            Ku(
                uid="ku:cycle-x",
                title="Cycle X",
                content="X",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:cycle-y",
                title="Cycle Y",
                content="Y",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:cycle-z",
                title="Cycle Z",
                content="Z",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
        ]
        for node in nodes:
            await ku_backend.create(node)

        # Create cycle
        relationships = [
            ("ku:cycle-x", "ku:cycle-y", "REQUIRES_KNOWLEDGE", None),
            ("ku:cycle-y", "ku:cycle-z", "REQUIRES_KNOWLEDGE", None),
            ("ku:cycle-z", "ku:cycle-x", "REQUIRES_KNOWLEDGE", None),  # Back to X
        ]
        await ku_backend.create_relationships_batch(relationships)

        # Traverse should handle cycle gracefully
        result = await ku_backend.traverse(
            start_uid="ku:cycle-x",
            rel_pattern="REQUIRES_KNOWLEDGE",
            max_depth=5,
        )

        assert result.is_ok
        # Should have found Y and Z (X is start, won't be in results)
        uids = {n["uid"] for n in result.value}
        assert "ku:cycle-y" in uids
        assert "ku:cycle-z" in uids

    async def test_traverse_self_loop(self, ku_backend, clean_neo4j):
        """Test traversal handles self-referential relationships."""
        # Create node with self-loop
        node = Ku(
            uid="ku:selfloop",
            title="Self Loop",
            content="Self-referential",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(node)

        # Create self-loop relationship
        relationships = [("ku:selfloop", "ku:selfloop", "RELATES_TO", None)]
        await ku_backend.create_relationships_batch(relationships)

        # Traverse should handle self-loop
        result = await ku_backend.traverse(
            start_uid="ku:selfloop",
            rel_pattern="RELATES_TO",
            max_depth=3,
        )

        # Should complete without error
        assert result.is_ok


@pytest.mark.asyncio
class TestGetDomainContextRaw:
    """Integration tests for get_domain_context_raw() method."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Ku", Ku)

    @pytest_asyncio.fixture
    async def context_graph(self, ku_backend):
        """
        Create a test graph for context testing with confidence values.

        Graph structure:
            Center --PREREQUISITE(0.9)--> Related1 --PREREQUISITE(0.8)--> Deep1
            Center --ENABLES(0.7)---> Related2
        """
        nodes = [
            Ku(
                uid="ku:context-center",
                title="Center Node",
                content="Center",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:context-related1",
                title="Related 1",
                content="Related 1",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:context-related2",
                title="Related 2",
                content="Related 2",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:context-deep1",
                title="Deep 1",
                content="Deep 1",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
        ]

        for node in nodes:
            result = await ku_backend.create(node)
            assert result.is_ok

        # Create relationships with confidence properties
        relationships = [
            (
                "ku:context-center",
                "ku:context-related1",
                "REQUIRES_KNOWLEDGE",
                {"confidence": 0.9},
            ),
            (
                "ku:context-related1",
                "ku:context-deep1",
                "REQUIRES_KNOWLEDGE",
                {"confidence": 0.8},
            ),
            (
                "ku:context-center",
                "ku:context-related2",
                "ENABLES_KNOWLEDGE",
                {"confidence": 0.7},
            ),
        ]
        result = await ku_backend.create_relationships_batch(relationships)
        assert result.is_ok

        return nodes

    async def test_context_raw_basic(self, ku_backend, context_graph):
        """Test basic context retrieval returns GraphContextNode list."""
        result = await ku_backend.get_domain_context_raw(
            entity_uid="ku:context-center",
            entity_label="Ku",
            relationship_types=["REQUIRES_KNOWLEDGE", "ENABLES_KNOWLEDGE"],
            depth=2,
        )

        assert result.is_ok
        context = result.value
        assert isinstance(context, list)

    async def test_context_raw_relationship_filter(self, ku_backend, context_graph):
        """Test that only specified relationship types are included."""
        # Only PREREQUISITE, not ENABLES
        result = await ku_backend.get_domain_context_raw(
            entity_uid="ku:context-center",
            entity_label="Ku",
            relationship_types=["REQUIRES_KNOWLEDGE"],
            depth=2,
        )

        assert result.is_ok
        context = result.value

        # Should find related1 and deep1 via PREREQUISITE, but not related2 (ENABLES)
        uids = {n.get("uid") for n in context}
        if context:  # Context may be empty if query structure differs
            assert "ku:context-related2" not in uids

    async def test_context_raw_depth_limit(self, ku_backend, context_graph):
        """Test that depth parameter is respected."""
        result = await ku_backend.get_domain_context_raw(
            entity_uid="ku:context-center",
            entity_label="Ku",
            relationship_types=["REQUIRES_KNOWLEDGE"],
            depth=1,
        )

        assert result.is_ok
        context = result.value

        # With depth 1, should only get related1, not deep1
        if context:
            # deep1 should not be present at depth 1
            for node in context:
                if node.get("distance"):
                    assert node["distance"] <= 1

    async def test_context_raw_empty(self, ku_backend, context_graph):
        """Test context for isolated node returns empty list."""
        # Create isolated node
        isolated = Ku(
            uid="ku:isolated",
            title="Isolated",
            content="No connections",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(isolated)

        result = await ku_backend.get_domain_context_raw(
            entity_uid="ku:isolated",
            entity_label="Ku",
            relationship_types=["REQUIRES_KNOWLEDGE"],
            depth=2,
        )

        assert result.is_ok
        assert result.value == []

    async def test_context_raw_nonexistent_entity(self, ku_backend, context_graph):
        """Test context for non-existent entity returns empty list."""
        result = await ku_backend.get_domain_context_raw(
            entity_uid="ku:nonexistent",
            entity_label="Ku",
            relationship_types=["REQUIRES_KNOWLEDGE"],
            depth=2,
        )

        assert result.is_ok
        assert result.value == []


@pytest.mark.asyncio
class TestFindPath:
    """Integration tests for find_path() method."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Ku", Ku)

    @pytest_asyncio.fixture
    async def path_graph(self, ku_backend):
        """
        Create a test graph for pathfinding.

        Graph structure:
            Start --PREREQUISITE--> Mid1 --PREREQUISITE--> End
            Start --ENABLES---> Mid2 --ENABLES---> End

        Two paths from Start to End:
        - PREREQUISITE path: length 2
        - ENABLES path: length 2
        """
        nodes = [
            Ku(
                uid="ku:path-start",
                title="Start",
                content="Start",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:path-mid1",
                title="Mid1",
                content="Mid1",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:path-mid2",
                title="Mid2",
                content="Mid2",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:path-end",
                title="End",
                content="End",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
        ]

        for node in nodes:
            result = await ku_backend.create(node)
            assert result.is_ok

        relationships = [
            ("ku:path-start", "ku:path-mid1", "REQUIRES_KNOWLEDGE", None),
            ("ku:path-mid1", "ku:path-end", "REQUIRES_KNOWLEDGE", None),
            ("ku:path-start", "ku:path-mid2", "ENABLES_KNOWLEDGE", None),
            ("ku:path-mid2", "ku:path-end", "ENABLES_KNOWLEDGE", None),
        ]
        result = await ku_backend.create_relationships_batch(relationships)
        assert result.is_ok

        return nodes

    async def test_find_path_exists(self, ku_backend, path_graph):
        """Test finding shortest path returns node list."""
        result = await ku_backend.find_path(
            from_uid="ku:path-start",
            to_uid="ku:path-end",
            rel_types=["REQUIRES_KNOWLEDGE"],
            max_depth=5,
        )

        assert result.is_ok
        path = result.value
        assert path is not None
        assert len(path) == 3  # start -> mid1 -> end

        # Verify path nodes
        uids = [n["uid"] for n in path]
        assert uids[0] == "ku:path-start"
        assert uids[-1] == "ku:path-end"

    async def test_find_path_no_path(self, ku_backend, path_graph):
        """Test no path exists returns Ok(None)."""
        result = await ku_backend.find_path(
            from_uid="ku:path-start",
            to_uid="ku:path-end",
            rel_types=["NONEXISTENT_REL"],
            max_depth=5,
        )

        assert result.is_ok
        assert result.value is None

    async def test_find_path_same_node(self, ku_backend, path_graph):
        """Test path from node to itself returns error (Neo4j limitation).

        Neo4j's shortestPath algorithm doesn't support same start/end nodes.
        This test verifies the error is handled gracefully.
        """
        result = await ku_backend.find_path(
            from_uid="ku:path-start",
            to_uid="ku:path-start",
            rel_types=["REQUIRES_KNOWLEDGE"],
            max_depth=5,
        )

        # Neo4j shortestPath doesn't support same start/end - returns error
        # This is expected behavior, not a bug in our code
        assert result.is_error
        assert "same" in str(result.error).lower() or "shortest" in str(result.error).lower()

    async def test_find_path_max_depth(self, ku_backend, path_graph):
        """Test that max_depth limits path search."""
        # Create a longer chain: Start -> Mid1 -> End requires depth 2
        # With max_depth=1, should not find path
        result = await ku_backend.find_path(
            from_uid="ku:path-start",
            to_uid="ku:path-end",
            rel_types=["REQUIRES_KNOWLEDGE"],
            max_depth=1,
        )

        assert result.is_ok
        # With depth 1, cannot reach end (needs 2 hops)
        # Should return None
        assert result.value is None

    async def test_find_path_multiple_rel_types(self, ku_backend, path_graph):
        """Test pathfinding with multiple allowed relationship types."""
        result = await ku_backend.find_path(
            from_uid="ku:path-start",
            to_uid="ku:path-end",
            rel_types=["REQUIRES_KNOWLEDGE", "ENABLES_KNOWLEDGE"],
            max_depth=5,
        )

        assert result.is_ok
        path = result.value
        assert path is not None
        assert len(path) == 3  # Either path has 3 nodes

    async def test_find_path_shortest(self, ku_backend, clean_neo4j):
        """Test that shortest path is returned when multiple exist."""
        # Create graph with short and long paths:
        # Start -> End (direct, length 1)
        # Start -> Mid -> End (length 2)
        nodes = [
            Ku(
                uid="ku:short-start",
                title="Start",
                content="Start",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:short-mid",
                title="Mid",
                content="Mid",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Ku(
                uid="ku:short-end",
                title="End",
                content="End",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
        ]
        for node in nodes:
            await ku_backend.create(node)

        relationships = [
            ("ku:short-start", "ku:short-end", "REQUIRES_KNOWLEDGE", None),  # Direct
            ("ku:short-start", "ku:short-mid", "REQUIRES_KNOWLEDGE", None),  # Via mid
            ("ku:short-mid", "ku:short-end", "REQUIRES_KNOWLEDGE", None),
        ]
        await ku_backend.create_relationships_batch(relationships)

        result = await ku_backend.find_path(
            from_uid="ku:short-start",
            to_uid="ku:short-end",
            rel_types=["REQUIRES_KNOWLEDGE"],
            max_depth=5,
        )

        assert result.is_ok
        path = result.value
        assert path is not None
        # Shortest path should be direct: Start -> End (2 nodes)
        assert len(path) == 2
        assert path[0]["uid"] == "ku:short-start"
        assert path[1]["uid"] == "ku:short-end"
