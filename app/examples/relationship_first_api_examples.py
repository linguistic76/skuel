"""
Relationship-First API Examples
================================

Demonstrates the new fluent interface for Neo4j relationship operations.

Philosophy: "Relationships ARE the primary API, not an afterthought"

Date: October 26, 2025
"""

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend


async def example_create_relationship(backend: UniversalNeo4jBackend):
    """
    Example: Creating a relationship using the fluent API.

    The relationship-first approach makes relationship creation explicit and expressive.
    """
    task_uid = "task.2025_10_26_implement_graph_api"
    ku_uid = "ku.programming.graph_databases.neo4j"

    # Old way (still works):
    # await backend.create_semantic_relationship(...)

    # New way - Relationship-first fluent API:
    result = (
        await backend.relate()
        .from_node(task_uid)
        .via("APPLIES_KNOWLEDGE")
        .to_node(ku_uid)
        .with_metadata(
            confidence=0.85,
            evidence="Applied Neo4j knowledge in task implementation",
            application_type="practical",
        )
        .create()
    )

    if result.is_ok:
        print(f"✅ Created APPLIES_KNOWLEDGE relationship: {task_uid} → {ku_uid}")
    else:
        print(f"❌ Failed: {result.error}")


async def example_traverse_knowledge_graph(backend: UniversalNeo4jBackend):
    """
    Example: Traversing the knowledge graph to find learning context.

    GRAPH-NATIVE DEFAULT: depth=3 provides rich neighborhood context.
    No need to specify .depth(3) - it's the default!
    """
    ku_uid = "ku.programming.graph_databases.neo4j"

    # Old way (manual Cypher):
    # await session.run("MATCH path=(start)-[:REQUIRES*1..3]->(end) WHERE ...")

    # New way - Relationship-first fluent API with graph-native defaults:
    result = (
        await backend.traverse()
        .from_node(ku_uid)
        .via_any(["REQUIRES_KNOWLEDGE", "BUILDS_ON", "PREREQUISITE_FOR"])
        .min_confidence(0.7)
        .get_context()
    )  # depth=3 by default!

    if result.is_ok:
        context = result.value
        print(f"📊 Knowledge Context for {ku_uid}:")
        print(f"  • Nodes: {context['node_count']}")
        print(f"  • Relationships: {context['relationship_count']}")
        print(f"  • Max depth: {context['max_depth']}")

        # Access the actual nodes and relationships
        for node in context["nodes"]:
            print(f"  - {node.get('uid')}: {node.get('title')}")
    else:
        print(f"❌ Failed: {result.error}")


async def example_semantic_task_context(backend: UniversalNeo4jBackend):
    """
    Example: Building semantic context for task intelligence.

    Uses default depth=3 for rich semantic context.
    Override to depth=5 for prerequisite chains.
    """
    task_uid = "task.2025_10_26_implement_graph_api"

    # Get all knowledge units this task applies or builds on
    # depth=3 by default - no need to specify!
    result = (
        await backend.traverse()
        .from_node(task_uid, labels=["Task"])
        .via_any(["APPLIES_KNOWLEDGE", "BUILDS_ON_KNOWLEDGE", "REQUIRES_KNOWLEDGE"])
        .direction("outgoing")
        .get_nodes()
    )

    if result.is_ok:
        knowledge_units = result.value
        print(f"🧠 Task applies {len(knowledge_units)} knowledge units:")
        for ku in knowledge_units:
            print(f"  - {ku.get('uid')}: {ku.get('title')}")
    else:
        print(f"❌ Failed: {result.error}")


async def example_prerequisite_chain(backend: UniversalNeo4jBackend):
    """
    Example: Building prerequisite chains for learning paths.

    OVERRIDE DEFAULT: Use depth=5 for prerequisite chain construction.
    This finds multi-hop dependencies that are critical for learning paths.
    """
    ku_uid = "ku.programming.advanced_algorithms.dynamic_programming"

    # For prerequisite chains, use depth=5
    result = (
        await backend.traverse()
        .from_node(ku_uid, labels=["Ku"])
        .via("REQUIRES_KNOWLEDGE")
        .depth(5)
        .direction("incoming")
        .min_confidence(0.8)
        .get_context()
    )

    if result.is_ok:
        context = result.value
        print("📚 Prerequisite Chain (depth=5):")
        print(f"  • {context['node_count']} prerequisite knowledge units")
        print(f"  • {context['relationship_count']} REQUIRES relationships")
        print(f"  • Max depth reached: {context['max_depth']}")

        # Build learning path from prerequisites
        prerequisites = sorted(context["nodes"], key=lambda n: n.get("difficulty_level", 0))
        print("\n  Learning Path Order:")
        for i, prereq in enumerate(prerequisites, 1):
            print(f"    {i}. {prereq.get('title')} (level {prereq.get('difficulty_level')})")
    else:
        print(f"❌ Failed: {result.error}")


async def example_bidirectional_traversal(backend: UniversalNeo4jBackend):
    """
    Example: Bi-directional graph traversal.

    Find both prerequisites (incoming) and enabled concepts (outgoing).
    Uses default depth=3 for rich neighborhood context.
    """
    ku_uid = "ku.programming.graph_databases.neo4j"

    # Get both prerequisites and what this enables
    # depth=3 by default - provides rich bi-directional context!
    result = (
        await backend.traverse()
        .from_node(ku_uid, labels=["Ku"])
        .via_any(["REQUIRES_KNOWLEDGE", "ENABLES_KNOWLEDGE"])
        .direction("both")
        .get_context()
    )

    if result.is_ok:
        context = result.value
        print("🔗 Bi-directional Knowledge Graph (depth=3):")
        print(f"  • Total connected nodes: {context['node_count']}")
        print(f"  • Total relationships: {context['relationship_count']}")

        # Analyze relationship directions
        for rel in context["relationships"]:
            print(f"  - {rel['type']}: {rel['properties']}")
    else:
        print(f"❌ Failed: {result.error}")


async def example_delete_relationship(backend: UniversalNeo4jBackend):
    """
    Example: Deleting a relationship using the fluent API.

    Clean, expressive syntax for relationship removal.
    """
    task_uid = "task.2025_10_26_implement_graph_api"
    ku_uid = "ku.programming.graph_databases.neo4j"

    # Delete the relationship
    result = (
        await backend.relate().from_node(task_uid).via("APPLIES_KNOWLEDGE").to_node(ku_uid).delete()
    )

    if result.is_ok:
        deleted_count = result.value
        print(f"🗑️  Deleted {deleted_count} APPLIES_KNOWLEDGE relationships")
    else:
        print(f"❌ Failed: {result.error}")


async def example_count_reachable_nodes(backend: UniversalNeo4jBackend):
    """
    Example: Count nodes reachable via traversal.

    Efficient way to measure graph connectivity without fetching all data.
    """
    ku_uid = "ku.programming.graph_databases.neo4j"

    # Count prerequisite depth
    result = (
        await backend.traverse()
        .from_node(ku_uid)
        .via("REQUIRES_KNOWLEDGE")
        .depth(3)
        .direction("incoming")
        .count()
    )

    if result.is_ok:
        prerequisite_count = result.value
        print(f"📈 {prerequisite_count} prerequisite knowledge units (depth 3)")
    else:
        print(f"❌ Failed: {result.error}")


# ============================================================================
# COMPARISON: OLD vs NEW API
# ============================================================================


async def comparison_create_relationship():
    """Comparison of old imperative vs new fluent API."""

    # OLD WAY - Imperative, verbose
    """
    await backend.create_semantic_relationship(
        from_uid="task.123",
        to_uid="ku.456",
        relationship_type=SemanticRelationshipType.APPLIES_KNOWLEDGE,
        metadata=RelationshipMetadata(
            confidence=0.85,
            evidence="Applied in task",
            created_at=datetime.now()
        )
    )
    """

    # NEW WAY - Fluent, expressive
    """
    await backend.relate() \\
        .from_node("task.123") \\
        .via("APPLIES_KNOWLEDGE") \\
        .to_node("ku.456") \\
        .with_metadata(confidence=0.85, evidence="Applied in task") \\
        .create()
    """
    pass


async def comparison_traverse_graph():
    """Comparison of manual Cypher vs fluent traversal with graph-native defaults."""

    # OLD WAY - Manual Cypher query
    """
    query = '''
        MATCH path=(start:Ku {uid: $uid})-[r:REQUIRES_KNOWLEDGE*1..3]->(end)
        WHERE all(rel in relationships(path) WHERE rel.confidence >= 0.7)
        RETURN nodes(path), relationships(path)
    '''
    async with driver.session() as session:
        result = await session.run(query, uid=ku_uid)
        # Manual processing...
    """

    # NEW WAY - Fluent builder with graph-native defaults
    """
    # depth=3 by default - no need to specify!
    await backend.traverse() \\
        .from_node(ku_uid) \\
        .via("REQUIRES_KNOWLEDGE") \\
        .min_confidence(0.7) \\
        .get_context()

    # Override depth only when needed (e.g., prerequisite chains)
    await backend.traverse() \\
        .from_node(ku_uid) \\
        .via("REQUIRES_KNOWLEDGE") \\
        .depth(5) \\
        .min_confidence(0.7) \\
        .get_context()
    """
    pass


# ============================================================================
# BENEFITS SUMMARY
# ============================================================================

"""
Benefits of Relationship-First API:

1. **Expressiveness**: Reads like natural language
   - "relate from task via APPLIES_KNOWLEDGE to knowledge"
   - "traverse from knowledge via REQUIRES" (depth=3 by default!)

2. **Graph-Native Defaults**: Multi-hop traversal is the default, not the exception
   - depth=3 by default (neighborhood context, not just direct relationships)
   - Override to depth=1 for shallow queries (rare)
   - Override to depth=5 for prerequisite chains
   - Override to depth=10 for shortest path (maximum)
   - Philosophy: "Don't be afraid of depth - graph databases are built for this!"

3. **Type Safety**: Builder pattern provides compile-time checking
   - IDE autocomplete for all methods
   - Clear parameter types

4. **Composability**: Easy to build complex queries incrementally
   - Start simple: .from_node().via().to_node()
   - Add filters: .min_confidence()
   - Override depth only when needed: .depth(5)
   - Choose output: .get_context() or .get_nodes() or .count()

5. **Consistency**: Same pattern across all relationship operations
   - Creating: .relate().from_node()...create()
   - Querying: .traverse().from_node()...get_context()
   - Deleting: .relate().from_node()...delete()

6. **Relationships as First-Class Citizens**:
   - Not hidden in service methods
   - Explicit in the API
   - Encourages relationship-first thinking

7. **Index-Free Adjacency**: Leverages Neo4j's core strength
   - O(1) relationship traversal
   - Efficient multi-hop queries (depth=3 default!)
   - Native graph algorithms

Philosophy: "Relationships ARE the data structure, not serialized lists"
Philosophy: "Multi-hop traversal is the default, not the exception"
"""
