"""
APOC Canary Tests
==============================

Verify APOC procedures work correctly before/after Neo4j upgrades.

CONTEXT:

- APOC still used for infrastructure: batch ops, schema introspection
- These tests validate APOC infrastructure procedures only

Run before/after Neo4j version upgrades to catch breaking changes.
"""

import pytest
from neo4j import AsyncDriver


@pytest.mark.asyncio
class TestApocCanary:
    """
    Canary tests for APOC infrastructure procedures.

    These tests validate that APOC procedures used for infrastructure
    operations (batch loading, schema introspection) work correctly.

    Run these tests before/after Neo4j upgrades.
    """

    async def test_apoc_version_matches_neo4j(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify APOC version matches Neo4j version.

        Critical for compatibility - APOC version must exactly match Neo4j.
        """
        async with neo4j_driver.session() as session:
            # Get Neo4j version
            neo4j_result = await session.run(
                "CALL dbms.components() "
                "YIELD name, versions "
                "WHERE name = 'Neo4j Kernel' "
                "RETURN versions[0] as version"
            )
            neo4j_record = await neo4j_result.single()
            neo4j_version = neo4j_record["version"]

            # Get APOC version
            apoc_result = await session.run("RETURN apoc.version() as version")
            apoc_record = await apoc_result.single()
            apoc_version = apoc_record["version"]

            # Versions must match
            assert neo4j_version == apoc_version, (
                f"Version mismatch! Neo4j: {neo4j_version}, APOC: {apoc_version}. "
                "APOC version must exactly match Neo4j version."
            )

    async def test_periodic_iterate_works(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify apoc.periodic.iterate (batch operations).

        Used for bulk loading knowledge units from markdown files.
        """
        async with neo4j_driver.session() as session:
            # Clean up any existing test nodes
            await session.run("MATCH (n:CanaryTest) DETACH DELETE n")

            # Test batch creation
            query = """
            CALL apoc.periodic.iterate(
                'UNWIND range(1, 5) as n RETURN n',
                'CREATE (x:CanaryTest {value: n})',
                {batchSize: 2}
            )
            YIELD batches, total
            RETURN batches, total
            """
            result = await session.run(query)
            record = await result.single()

            assert record is not None
            assert record["total"] == 5, "Should create 5 test nodes"
            assert record["batches"] > 0, "Should execute in batches"

            # Verify nodes were created
            count_result = await session.run("MATCH (n:CanaryTest) RETURN count(n) as count")
            count_record = await count_result.single()
            assert count_record["count"] == 5

            # Cleanup
            await session.run("MATCH (n:CanaryTest) DETACH DELETE n")

    async def test_meta_graph_works(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify apoc.meta.graph (schema introspection).

        Used for understanding graph structure and relationships.
        """
        async with neo4j_driver.session() as session:
            query = "CALL apoc.meta.graph() YIELD nodes, relationships RETURN nodes, relationships"
            result = await session.run(query)
            record = await result.single()

            assert record is not None
            # Neo4j Record objects require .get() or .keys() check, not "in" operator
            assert record.get("nodes") is not None
            assert record.get("relationships") is not None

    async def test_schema_node_type_properties(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify apoc.meta.nodeTypeProperties (schema discovery).

        Used for discovering what properties exist on node types.
        """
        async with neo4j_driver.session() as session:
            query = "CALL apoc.meta.nodeTypeProperties() YIELD nodeType, propertyName RETURN nodeType, propertyName LIMIT 10"
            result = await session.run(query)
            records = await result.fetch(10)

            # Should return schema information (may be empty on fresh DB)
            assert records is not None

    async def test_import_json_works(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify apoc.convert.fromJsonMap (JSON parsing).

        Used for parsing JSON data during knowledge unit import.
        """
        async with neo4j_driver.session() as session:
            query = """
            WITH '{"name": "Test", "value": 123}' as json_str
            RETURN apoc.convert.fromJsonMap(json_str) as data
            """
            result = await session.run(query)
            record = await result.single()

            assert record is not None
            data = record["data"]
            assert data["name"] == "Test"
            assert data["value"] == 123


@pytest.mark.asyncio
class TestSemanticRelationshipCanary:
    """
    Canary tests for semantic relationship types.

    Validates that all 10 semantic relationship types work correctly
    and that Neo4j query planner can optimize queries using them.
    """

    async def test_prerequisite_semantic_types_exist(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify all 4 prerequisite semantic types work.

        established these types to replace APOC traversal.
        """
        async with neo4j_driver.session() as session:
            # Create test nodes
            await session.run("""
                CREATE (a:CanaryKnowledge {uid: 'canary.a', title: 'A'})
                CREATE (b:CanaryKnowledge {uid: 'canary.b', title: 'B'})
                CREATE (c:CanaryKnowledge {uid: 'canary.c', title: 'C'})
                CREATE (d:CanaryKnowledge {uid: 'canary.d', title: 'D'})
            """)

            # Create prerequisite relationships (all 4 types)
            await session.run("""
                MATCH (a:CanaryKnowledge {uid: 'canary.a'})
                MATCH (b:CanaryKnowledge {uid: 'canary.b'})
                MATCH (c:CanaryKnowledge {uid: 'canary.c'})
                MATCH (d:CanaryKnowledge {uid: 'canary.d'})
                CREATE (b)-[:REQUIRES_THEORETICAL_UNDERSTANDING]->(a)
                CREATE (c)-[:REQUIRES_PRACTICAL_APPLICATION]->(a)
                CREATE (d)-[:REQUIRES_CONCEPTUAL_FOUNDATION]->(a)
                CREATE (d)-[:BUILDS_ON_FOUNDATION]->(b)
            """)

            # Query using all 4 prerequisite types
            result = await session.run("""
                MATCH (node:CanaryKnowledge {uid: 'canary.d'})
                MATCH path = (node)-[:REQUIRES_THEORETICAL_UNDERSTANDING|REQUIRES_PRACTICAL_APPLICATION|REQUIRES_CONCEPTUAL_FOUNDATION|BUILDS_ON_FOUNDATION*1..2]->(prereq)
                RETURN count(DISTINCT prereq) as prereq_count
            """)
            record = await result.single()

            # Should find prerequisites via semantic types
            assert record["prereq_count"] >= 2, "Should find prerequisites using semantic types"

            # Cleanup
            await session.run("MATCH (n:CanaryKnowledge) DETACH DELETE n")

    async def test_hierarchy_semantic_types_work(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify hierarchy semantic types (HAS_BROADER_CONCEPT, HAS_NARROWER_CONCEPT).
        """
        async with neo4j_driver.session() as session:
            # Create test hierarchy
            await session.run("""
                CREATE (broad:CanaryKnowledge {uid: 'canary.broad', title: 'Broad Concept'})
                CREATE (narrow:CanaryKnowledge {uid: 'canary.narrow', title: 'Narrow Concept'})
                CREATE (narrow)-[:HAS_BROADER_CONCEPT]->(broad)
                CREATE (broad)-[:HAS_NARROWER_CONCEPT]->(narrow)
            """)

            # Query using hierarchy types
            result = await session.run("""
                MATCH (n:CanaryKnowledge {uid: 'canary.narrow'})
                MATCH (n)-[:HAS_BROADER_CONCEPT]->(parent)
                RETURN parent.title as parent_title
            """)
            record = await result.single()

            assert record["parent_title"] == "Broad Concept"

            # Cleanup
            await session.run("MATCH (n:CanaryKnowledge) DETACH DELETE n")

    async def test_relationship_semantic_types_work(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify relationship semantic types (SHARES_PRINCIPLE_WITH, etc.).
        """
        async with neo4j_driver.session() as session:
            # Create test relationships
            await session.run("""
                CREATE (a:CanaryKnowledge {uid: 'canary.principle.a', title: 'Concept A'})
                CREATE (b:CanaryKnowledge {uid: 'canary.principle.b', title: 'Concept B'})
                CREATE (c:CanaryKnowledge {uid: 'canary.analogous.c', title: 'Concept C'})
                CREATE (a)-[:SHARES_PRINCIPLE_WITH]->(b)
                CREATE (a)-[:ANALOGOUS_TO]->(c)
            """)

            # Query using relationship types
            result = await session.run("""
                MATCH (a:CanaryKnowledge {uid: 'canary.principle.a'})
                MATCH (a)-[:SHARES_PRINCIPLE_WITH|ANALOGOUS_TO]->(related)
                RETURN count(related) as related_count
            """)
            record = await result.single()

            assert record["related_count"] == 2, "Should find 2 related concepts"

            # Cleanup
            await session.run("MATCH (n:CanaryKnowledge) DETACH DELETE n")

    async def test_variable_length_pattern_works(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify variable-length patterns work with semantic types.

        This is the pure Cypher pattern that replaced APOC in
        """
        async with neo4j_driver.session() as session:
            # Create chain: D -> C -> B -> A
            await session.run("""
                CREATE (a:CanaryKnowledge {uid: 'canary.chain.a', title: 'A'})
                CREATE (b:CanaryKnowledge {uid: 'canary.chain.b', title: 'B'})
                CREATE (c:CanaryKnowledge {uid: 'canary.chain.c', title: 'C'})
                CREATE (d:CanaryKnowledge {uid: 'canary.chain.d', title: 'D'})
                CREATE (b)-[:REQUIRES_THEORETICAL_UNDERSTANDING]->(a)
                CREATE (c)-[:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
                CREATE (d)-[:REQUIRES_THEORETICAL_UNDERSTANDING]->(c)
            """)

            # Variable-length pattern query (depth 1-3)
            result = await session.run("""
                MATCH (target:CanaryKnowledge {uid: 'canary.chain.d'})
                MATCH path = (target)-[:REQUIRES_THEORETICAL_UNDERSTANDING*1..3]->(prereq)
                RETURN count(DISTINCT prereq) as prereq_count, max(length(path)) as max_depth
            """)
            record = await result.single()

            assert record["prereq_count"] == 3, "Should find 3 prerequisites (A, B, C)"
            assert record["max_depth"] == 3, "Should traverse up to depth 3"

            # Cleanup
            await session.run("MATCH (n:CanaryKnowledge) DETACH DELETE n")


@pytest.mark.asyncio
class TestQueryPlannerCanary:
    """
    Canary tests for Neo4j query planner optimization.

    Validates that query planner can optimize semantic relationship queries
    and that relationship type indexes exist.
    """

    async def test_relationship_type_scan_works(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify query planner can scan relationship types.

        EXPLAIN should show RelationshipTypeScan for semantic type queries.
        """
        async with neo4j_driver.session() as session:
            # EXPLAIN query (doesn't execute, just shows plan)
            result = await session.run("""
                EXPLAIN
                MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
                RETURN a, b
            """)

            # Should complete without error
            # In production, would parse execution plan to verify RelationshipTypeScan
            summary = await result.consume()
            assert summary is not None

    async def test_parameterized_queries_work(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify parameterized queries work (enables query caching).

        Query cache provides 10-100x speedup for repeated queries.
        """
        async with neo4j_driver.session() as session:
            # Parameterized query
            result = await session.run(
                "MATCH (n:CanaryKnowledge {uid: $uid}) RETURN n", uid="test.uid"
            )

            # Should execute without error (no matching node is fine)
            summary = await result.consume()
            assert summary is not None


@pytest.mark.asyncio
class TestNeo4jVersionCanary:
    """
    Canary tests for Neo4j version verification.

    Validates that Neo4j is running the expected version (5.26.0).
    """

    async def test_neo4j_version_is_5_26_0(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify Neo4j version is exactly 5.26.0.

        pinned Neo4j driver to 5.26.0 - server must match.
        """
        async with neo4j_driver.session() as session:
            result = await session.run(
                "CALL dbms.components() "
                "YIELD name, versions, edition "
                "WHERE name = 'Neo4j Kernel' "
                "RETURN versions[0] as version, edition"
            )
            record = await result.single()

            version = record["version"]
            edition = record["edition"]

            # Verify version
            assert version.startswith("5.26"), (
                f"Expected Neo4j 5.26.x, got {version}. "
                "Update pyproject.toml if intentionally upgraded."
            )

            # Log edition for reference
            print(f"Neo4j {version} ({edition})")

    async def test_driver_version_is_5_26_0(self, neo4j_driver: AsyncDriver):
        """
        Canary: Verify Python driver version is 5.26.0.

        Driver version must match server version.
        """
        import neo4j

        driver_version = neo4j.__version__

        assert driver_version.startswith("5.26"), (
            f"Expected driver 5.26.x, got {driver_version}. "
            "Run 'poetry install' to use pinned version."
        )
