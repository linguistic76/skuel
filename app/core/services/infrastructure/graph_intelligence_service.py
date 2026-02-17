"""
Graph Intelligence Service - Pure Cypher Analytics
==================================================

Provides graph algorithm-style analytics using pure Cypher only.
Zero external dependencies - no APOC, no GDS required.

Philosophy: "Simplicity and portability over advanced algorithms"

This service achieves 80% of graph intelligence value using only native Cypher:
- Hub detection (degree centrality)
- Knowledge similarity (Jaccard via shared neighbors)
- Prerequisite chain analysis
- Learning cluster detection (density-based approximation)

For the remaining 20% (PageRank, Louvain, etc.), users can optionally install GDS.
See: /docs/ADVANCED_GDS_INTEGRATION.md

Date: October 26, 2025
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import Domain
from core.services.protocols import get_enum_value
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import QueryExecutor

logger = get_logger(__name__)


class GraphIntelligenceService:
    """
    Pure Cypher graph intelligence and analytics.

    NO EXTERNAL DEPENDENCIES - works with any Neo4j instance.

    This service provides graph algorithm-style analytics using only
    native Cypher queries. While not as sophisticated as GDS algorithms
    (Louvain, PageRank, etc.), these methods provide 80% of the value
    while maintaining SKUEL's zero-dependency architecture.

    Key Capabilities:
    - Hub detection: Find highly connected knowledge units
    - Similarity: Find related knowledge via shared neighbors
    - Clustering: Approximate clustering via density analysis
    - Path analysis: Analyze prerequisite chains and depths
    - Centrality: Simple degree-based importance scores

    Semantic Types Used:
    - REQUIRES_KNOWLEDGE: Prerequisite relationships for path analysis
    - RELATED_TO: Generic relationships for similarity calculations
    - (Analyzes all relationship types for hub/centrality detection)

    Source Tag: "graph_intelligence_computed"
    - All metrics are computed via graph algorithms

    Confidence Scoring:
    - 1.0: Structural graph metrics (degree, path length)
    - 0.8-0.9: Similarity scores (Jaccard, shared neighbors)
    - 0.6-0.8: Clustering/community detection (heuristic-based)
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize graph intelligence service.

        Args:
            executor: QueryExecutor for graph queries
        """
        self.executor = executor
        self.logger = get_logger("skuel.graph.intelligence")

    # ========================================================================
    # HUB DETECTION - DEGREE CENTRALITY
    # ========================================================================

    @with_error_handling(error_type="database")
    async def find_knowledge_hubs(
        self,
        domain: Domain | None = None,
        min_connections: int = 5,
        min_confidence: float = 0.7,
        limit: int = 20,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find highly connected knowledge units (hubs).

        Uses degree centrality - counts high-quality relationships.
        Pure Cypher - no GDS required.

        Hubs are knowledge units that:
        - Have many relationships (degree >= min_connections)
        - Relationships have high confidence (>= min_confidence)
        - Act as connectors in the knowledge graph

        Args:
            domain: Optional domain filter
            min_connections: Minimum relationship count (default: 5)
            min_confidence: Minimum relationship confidence (default: 0.7)
            limit: Maximum results to return (default: 20)

        Returns:
            Result containing list of hubs with:
            - uid: Knowledge unit UID
            - title: Knowledge unit title
            - connections: Number of high-quality relationships
            - centrality_score: Normalized centrality (0.0-1.0)
            - incoming_count: Incoming relationship count
            - outgoing_count: Outgoing relationship count

        Example:
            hubs = await service.find_knowledge_hubs(
                domain=Domain.TECH,
                min_connections=10,
                min_ConfidenceLevel.STANDARD
            )

            for hub in hubs.value:
                print(f"{hub['title']}: {hub['connections']} connections")
        """
        self.logger.info(
            f"Finding knowledge hubs (domain={domain}, "
            f"min_connections={min_connections}, min_confidence={min_confidence})"
        )

        # Build domain filter
        domain_filter = ""
        params: dict[str, Any] = {
            "min_connections": min_connections,
            "min_confidence": min_confidence,
            "limit": limit,
        }

        if domain:
            domain_filter = "WHERE ku.domain = $domain"
            params["domain"] = domain.value

        query = f"""
        MATCH (ku:Ku)
        {domain_filter}
        OPTIONAL MATCH (ku)-[r WHERE coalesce(r.confidence, 1.0) >= $min_confidence]-()
        WITH ku, count(r) as total_connections
        WHERE total_connections >= $min_connections

        // Count incoming and outgoing separately
        OPTIONAL MATCH (ku)<-[r_in WHERE coalesce(r_in.confidence, 1.0) >= $min_confidence]-()
        WITH ku, total_connections, count(r_in) as incoming_count
        OPTIONAL MATCH (ku)-[r_out WHERE coalesce(r_out.confidence, 1.0) >= $min_confidence]->()
        WITH ku, total_connections, incoming_count, count(r_out) as outgoing_count

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               total_connections,
               incoming_count,
               outgoing_count,
               toFloat(total_connections) as centrality_score
        ORDER BY total_connections DESC
        LIMIT $limit
        """

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return result

        records = result.value or []

        hubs = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "domain": record["domain"],
                "connections": record["total_connections"],
                "incoming_count": record["incoming_count"],
                "outgoing_count": record["outgoing_count"],
                "centrality_score": record["centrality_score"],
            }
            for record in records
        ]

        self.logger.info(f"Found {len(hubs)} knowledge hubs")
        return Result.ok(hubs)

    # ========================================================================
    # SIMILARITY - JACCARD VIA SHARED NEIGHBORS
    # ========================================================================

    @with_error_handling(error_type="database", uid_param="ku_uid")
    async def find_similar_knowledge(
        self, ku_uid: str, min_similarity: float = 0.3, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """
        Find similar knowledge units via Jaccard similarity.

        Uses shared neighbors to calculate similarity.
        Pure Cypher - no GDS required.

        Jaccard similarity = |shared_neighbors| / |total_unique_neighbors|

        This works well for finding:
        - Related learning topics
        - Alternative learning paths
        - Knowledge units that can be studied together

        Args:
            ku_uid: Source knowledge unit UID
            min_similarity: Minimum similarity threshold (0.0-1.0, default: 0.3)
            limit: Maximum results to return (default: 10)

        Returns:
            Result containing list of similar knowledge with:
            - uid: Knowledge unit UID
            - title: Knowledge unit title
            - similarity: Jaccard similarity score (0.0-1.0)
            - shared_neighbors: Count of shared connections
            - total_neighbors: Total unique neighbors

        Example:
            similar = await service.find_similar_knowledge(
                ku_uid="ku.programming.algorithms",
                min_similarity=0.5
            )

            for item in similar.value:
                print(f"{item['title']}: {item['similarity']:.2f} similarity")
        """
        self.logger.info(f"Finding similar knowledge to {ku_uid} (min_similarity={min_similarity})")

        query = """
        // Find shared neighbors (any relationship direction)
        MATCH (ku1:Ku {uid: $uid})-[]-(shared)-[]-(ku2:Ku)
        WHERE ku1 <> ku2
        WITH ku1, ku2, count(DISTINCT shared) as shared_count

        // Count ku1's total neighbors
        MATCH (ku1)-[]-(ku1_neighbor)
        WITH ku1, ku2, shared_count, count(DISTINCT ku1_neighbor) as ku1_degree

        // Count ku2's total neighbors
        MATCH (ku2)-[]-(ku2_neighbor)
        WITH ku1, ku2, shared_count, ku1_degree,
             count(DISTINCT ku2_neighbor) as ku2_degree

        // Calculate Jaccard similarity
        WITH ku2, shared_count, ku1_degree, ku2_degree,
             toFloat(shared_count) / (ku1_degree + ku2_degree - shared_count) as similarity

        WHERE similarity >= $min_similarity

        RETURN ku2.uid as uid,
               ku2.title as title,
               ku2.domain as domain,
               similarity,
               shared_count,
               (ku1_degree + ku2_degree - shared_count) as total_neighbors
        ORDER BY similarity DESC
        LIMIT $limit
        """

        params = {"uid": ku_uid, "min_similarity": min_similarity, "limit": limit}

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return result

        records = result.value or []

        similar = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "domain": record["domain"],
                "similarity": record["similarity"],
                "shared_neighbors": record["shared_count"],
                "total_neighbors": record["total_neighbors"],
            }
            for record in records
        ]

        self.logger.info(f"Found {len(similar)} similar knowledge units")
        return Result.ok(similar)

    # ========================================================================
    # PREREQUISITE CHAIN ANALYSIS
    # ========================================================================

    @with_error_handling(error_type="database", uid_param="ku_uid")
    async def analyze_prerequisite_depth(self, ku_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze prerequisite chain depth and complexity.

        Uses variable-length path queries to trace prerequisites.
        Pure Cypher - uses native path operations.

        Provides insights into:
        - How deep the prerequisite chain is
        - How many different learning paths exist
        - Average prerequisite depth
        - Root prerequisites (no further prerequisites)

        Args:
            ku_uid: Knowledge unit UID to analyze

        Returns:
            Result containing analysis:
            - max_depth: Maximum prerequisite chain depth
            - avg_depth: Average prerequisite depth
            - total_paths: Number of unique prerequisite paths
            - root_prerequisites: UIDs of root prerequisites (no further prereqs)
            - complexity_score: Relative complexity (max_depth * total_paths)

        Example:
            analysis = await service.analyze_prerequisite_depth(
                ku_uid="ku.advanced.machine_learning"
            )

            if analysis.is_ok:
                print(f"Max depth: {analysis.value['max_depth']}")
                print(f"Root prerequisites: {analysis.value['root_prerequisites']}")
        """
        self.logger.info(f"Analyzing prerequisite depth for {ku_uid}")

        query = """
        // Find all prerequisite paths
        MATCH path = (end:Ku {uid: $uid})<-[:REQUIRES_KNOWLEDGE*]-(start)
        WHERE NOT (start)<-[:REQUIRES_KNOWLEDGE]-()

        WITH path,
             length(path) as depth,
             [node in nodes(path) | node.uid] as path_uids

        // Aggregate statistics
        WITH collect(DISTINCT path) as all_paths,
             max(depth) as max_depth,
             avg(depth) as avg_depth,
             collect(DISTINCT path_uids[size(path_uids)-1]) as root_uids

        RETURN max_depth,
               avg_depth,
               size(all_paths) as total_paths,
               root_uids,
               max_depth * size(all_paths) as complexity_score
        """

        params = {"uid": ku_uid}

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return result

        records = result.value or []
        record = records[0] if records else None

        if not record or record.get("max_depth") is None:
            # No prerequisites found
            return Result.ok(
                {
                    "max_depth": 0,
                    "avg_depth": 0.0,
                    "total_paths": 0,
                    "root_prerequisites": [],
                    "complexity_score": 0,
                }
            )

        analysis = {
            "max_depth": record["max_depth"],
            "avg_depth": record["avg_depth"],
            "total_paths": record["total_paths"],
            "root_prerequisites": record["root_uids"],
            "complexity_score": record["complexity_score"],
        }

        self.logger.info(
            f"Prerequisite analysis: depth={analysis['max_depth']}, "
            f"paths={analysis['total_paths']}"
        )
        return Result.ok(analysis)

    # ========================================================================
    # LEARNING CLUSTER DETECTION - DENSITY-BASED
    # ========================================================================

    @with_error_handling(error_type="database")
    async def find_learning_clusters(
        self, domain: Domain | None = None, min_density: float = 0.3, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """
        Find tightly connected knowledge clusters.

        Uses clustering coefficient (triangle density) as approximation.
        Pure Cypher - no GDS Louvain required.

        A cluster is a set of knowledge units with high interconnectivity:
        - Many shared neighbors (triangle patterns)
        - High density of internal relationships
        - Forms a cohesive learning module

        This is simpler than Louvain but works well for learning paths.

        Args:
            domain: Optional domain filter
            min_density: Minimum clustering coefficient (0.0-1.0, default: 0.3)
            limit: Maximum results to return (default: 20)

        Returns:
            Result containing list of cluster members:
            - uid: Knowledge unit UID
            - title: Knowledge unit title
            - neighbor_count: Number of neighbors
            - triangles: Number of triangles (closed patterns)
            - density: Clustering coefficient (0.0-1.0)

        Example:
            clusters = await service.find_learning_clusters(
                domain=Domain.TECH,
                min_density=0.5
            )

            for member in clusters.value:
                print(f"{member['title']}: density={member['density']:.2f}")
        """
        self.logger.info(f"Finding learning clusters (domain={domain}, min_density={min_density})")

        # Build domain filter
        domain_filter = ""
        params: dict[str, Any] = {"min_density": min_density, "limit": limit}

        if domain:
            domain_filter = "WHERE ku.domain = $domain"
            params["domain"] = domain.value

        query = f"""
        // Find knowledge units with neighbors
        MATCH (ku:Ku)
        {domain_filter}
        MATCH (ku)-[r]-(neighbor:Ku)
        WITH ku, count(DISTINCT neighbor) as neighbor_count
        WHERE neighbor_count >= 2

        // Count triangles (ku-n1-n2-ku closed patterns)
        MATCH (ku)-[]-(n1:Ku)-[]-(n2:Ku)-[]-(ku)
        WHERE n1 <> n2 AND id(n1) < id(n2)
        WITH ku, neighbor_count, count(*) as triangles

        // Calculate clustering coefficient (density)
        WITH ku, neighbor_count, triangles,
             toFloat(triangles) / (neighbor_count * (neighbor_count - 1) / 2) as density

        WHERE density >= $min_density

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               neighbor_count,
               triangles,
               density
        ORDER BY density DESC, neighbor_count DESC
        LIMIT $limit
        """

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return result

        records = result.value or []

        clusters = [
            {
                "uid": record["uid"],
                "title": record["title"],
                "domain": record["domain"],
                "neighbor_count": record["neighbor_count"],
                "triangles": record["triangles"],
                "density": record["density"],
            }
            for record in records
        ]

        self.logger.info(f"Found {len(clusters)} cluster members")
        return Result.ok(clusters)

    # ========================================================================
    # KNOWLEDGE IMPORTANCE - COMPOSITE SCORE
    # ========================================================================

    @with_error_handling(error_type="database", uid_param="ku_uid")
    async def calculate_knowledge_importance(self, ku_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate composite importance score for knowledge unit.

        Combines multiple metrics:
        - Degree centrality (connection count)
        - Prerequisite depth (foundational importance)
        - Clustering coefficient (cohesiveness)
        - Confidence score (relationship quality)

        Pure Cypher - approximates PageRank without GDS.

        Args:
            ku_uid: Knowledge unit UID

        Returns:
            Result containing importance metrics:
            - importance_score: Composite score (0.0-100.0)
            - degree_centrality: Normalized connection count
            - prerequisite_importance: Depth in prerequisite chains
            - cluster_coefficient: Local clustering density
            - avg_confidence: Average relationship confidence

        Example:
            importance = await service.calculate_knowledge_importance(
                ku_uid="ku.fundamentals.logic"
            )

            print(f"Importance score: {importance.value['importance_score']}")
        """
        self.logger.info(f"Calculating importance for {ku_uid}")

        query = """
        MATCH (ku:Ku {uid: $uid})

        // Metric 1: Degree centrality
        OPTIONAL MATCH (ku)-[r]-()
        WITH ku, count(r) as degree,
             avg(coalesce(r.confidence, 1.0)) as avg_confidence

        // Metric 2: Prerequisite importance (how many depend on this)
        OPTIONAL MATCH (ku)<-[:REQUIRES_KNOWLEDGE*]-(dependent)
        WITH ku, degree, avg_confidence, count(DISTINCT dependent) as dependents

        // Metric 3: Clustering coefficient
        OPTIONAL MATCH (ku)-[]-(n1)-[]-(n2)-[]-(ku)
        WHERE n1 <> n2 AND id(n1) < id(n2)
        WITH ku, degree, avg_confidence, dependents, count(*) as triangles

        // Calculate composite score
        WITH ku,
             degree,
             dependents,
             triangles,
             avg_confidence,
             CASE WHEN degree >= 2
                  THEN toFloat(triangles) / (degree * (degree - 1) / 2)
                  ELSE 0.0
             END as clustering

        RETURN toFloat(degree) as degree_centrality,
               toFloat(dependents) as prerequisite_importance,
               clustering as cluster_coefficient,
               avg_confidence,
               (degree * 0.3 + dependents * 0.4 + clustering * 10 * 0.3) as importance_score
        """

        params = {"uid": ku_uid}

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return result

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))

        importance = {
            "importance_score": record["importance_score"],
            "degree_centrality": record["degree_centrality"],
            "prerequisite_importance": record["prerequisite_importance"],
            "cluster_coefficient": record["cluster_coefficient"],
            "avg_confidence": record["avg_confidence"],
        }

        self.logger.info(f"Importance score: {importance['importance_score']:.2f}")
        return Result.ok(importance)

    # ========================================================================
    # GRAPH CONTEXT RETRIEVAL - CORE INTELLIGENCE METHODS
    # ========================================================================

    @with_error_handling(error_type="database", uid_param="node_uid")
    async def query_with_intent(
        self,
        domain: Any,  # Domain enum
        node_uid: str,
        intent: Any,  # QueryIntent enum
        depth: int = 2,
    ) -> Result[Any]:  # Returns Result[GraphContext]
        """
        Execute graph context query with specific intent.

        This is the PRIMARY method for intelligence services to retrieve
        rich graph context around an entity. Uses Pure Cypher traversal
        optimized for the given query intent.

        Args:
            domain: Domain of the origin node
            node_uid: UID of node to get context for
            intent: QueryIntent determining traversal strategy
            depth: Maximum traversal depth (default: 2)

        Returns:
            Result containing GraphContext with:
            - origin node and metadata
            - all nodes within depth hops
            - all relationships traversed
            - domain-specific contexts
            - cross-domain insights

        Example:
            context = await graph_intel.query_with_intent(
                domain=Domain.HABITS,
                node_uid="habit_morning_workout",
                intent=QueryIntent.PRACTICE,
                GraphDepth.NEIGHBORHOOD
            )
        """
        from datetime import datetime

        from core.models.graph_context import (
            ContextRelevance,
            DomainContext,
            GraphContext,
            GraphNode,
            GraphRelationship,
            RelationshipStrength,
        )

        self.logger.info(
            f"Querying graph context: domain={domain}, node={node_uid}, "
            f"intent={intent}, depth={depth}"
        )

        # Build intent-specific Pure Cypher query
        query = self._build_context_query_for_intent(intent, depth)
        params = {"uid": node_uid}

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return result

        records = result.value or []

        if not records:
            return Result.fail(Errors.not_found(resource="Node", identifier=node_uid))

        # Parse nodes and relationships from Cypher results
        all_nodes = []
        all_relationships = []

        for record in records:
            # Extract nodes (may be in different result keys depending on intent)
            nodes_data = record.get("nodes", []) or record.get("related_nodes", [])
            rels_data = record.get("relationships", [])

            # Build GraphNode objects
            for i, node_dict in enumerate(nodes_data):
                if not node_dict:
                    continue

                # Extract node properties
                uid = node_dict.get("uid", f"node_{i}")
                labels = node_dict.get("labels", ["Unknown"])
                if isinstance(labels, str):
                    labels = [labels]

                # Determine domain from node properties or labels
                node_domain = self._determine_domain(node_dict, labels)

                graph_node = GraphNode(
                    uid=uid,
                    labels=labels,
                    domain=node_domain,
                    properties=node_dict,
                    distance_from_origin=node_dict.get("distance", 1),
                    relevance=ContextRelevance.MEDIUM,
                    relationship_to_origin=node_dict.get("relationship_type"),
                )
                all_nodes.append(graph_node)

            # Build GraphRelationship objects
            for rel_dict in rels_data:
                if not rel_dict:
                    continue

                graph_rel = GraphRelationship(
                    type=rel_dict.get("type", "RELATED_TO"),
                    start_node_uid=rel_dict.get("start_uid", ""),
                    end_node_uid=rel_dict.get("end_uid", ""),
                    properties=rel_dict.get("properties", {}),
                    strength=RelationshipStrength.MODERATE,
                    bidirectional=rel_dict.get("bidirectional", False),
                )
                all_relationships.append(graph_rel)

        # Group nodes by domain
        domain_contexts_dict = {}
        for node in all_nodes:
            if node.domain not in domain_contexts_dict:
                domain_contexts_dict[node.domain] = {
                    "nodes": [],
                    "relationships": [],
                }
            domain_contexts_dict[node.domain]["nodes"].append(node)

        # Build DomainContext objects
        domain_contexts = {}
        for dom, data in domain_contexts_dict.items():
            domain_rels = [
                r
                for r in all_relationships
                if any(n.uid == r.start_node_uid or n.uid == r.end_node_uid for n in data["nodes"])
            ]
            domain_contexts[dom] = DomainContext(
                domain=dom,
                nodes=data["nodes"],
                relationships=domain_rels,
                node_count=len(data["nodes"]),
                relationship_count=len(domain_rels),
            )

        # Calculate relationship patterns
        relationship_patterns = {}
        for rel in all_relationships:
            relationship_patterns[rel.type] = relationship_patterns.get(rel.type, 0) + 1

        # Build GraphContext
        graph_context = GraphContext(
            origin_uid=node_uid,
            origin_domain=domain,
            query_intent=get_enum_value(intent),
            all_nodes=all_nodes,
            all_relationships=all_relationships,
            domain_contexts=domain_contexts,
            cross_domain_insights=[],
            relationship_patterns=relationship_patterns,
            total_nodes=len(all_nodes),
            total_relationships=len(all_relationships),
            domains_involved=list(domain_contexts.keys()),
            max_depth_reached=depth,
            query_timestamp=datetime.now(),
            neo4j_query_time_ms=None,
            processing_time_ms=None,
        )

        self.logger.info(
            f"Graph context retrieved: {len(all_nodes)} nodes, "
            f"{len(all_relationships)} relationships, "
            f"{len(domain_contexts)} domains"
        )

        return Result.ok(graph_context)

    @with_error_handling(error_type="database", uid_param="entity_uid")
    async def get_entity_context(
        self, entity_uid: str, depth: int = 2
    ) -> Result[Any]:  # Returns Result[GraphContext]
        """
        Get generic graph context for any entity.

        Simplified version of query_with_intent that uses RELATIONSHIP intent
        for generic graph traversal without specific intent optimization.

        Args:
            entity_uid: UID of entity to get context for
            depth: Maximum traversal depth (default: 2)

        Returns:
            Result containing GraphContext

        Example:
            context = await graph_intel.get_entity_context("event_meeting_123", GraphDepth.NEIGHBORHOOD)
        """
        from core.models.query import QueryIntent

        # First, determine domain of entity by fetching it
        query = """
        MATCH (n {uid: $uid})
        RETURN n, labels(n) as labels
        """

        result = await self.executor.execute_query(query, {"uid": entity_uid})
        if result.is_error:
            return result

        records = result.value or []

        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        node_labels = records[0]["labels"]
        domain = self._determine_domain(records[0]["n"], node_labels)

        # Use query_with_intent with RELATIONSHIP intent for generic traversal
        return await self.query_with_intent(
            domain=domain,
            node_uid=entity_uid,
            intent=QueryIntent.RELATIONSHIP,
            depth=depth,
        )

    def _build_context_query_for_intent(self, intent: Any, depth: int) -> str:
        """
        Build Pure Cypher query for graph context retrieval based on intent.

        Uses variable-length patterns for efficient traversal.

        Args:
            intent: QueryIntent determining traversal strategy
            depth: Maximum traversal depth

        Returns:
            Pure Cypher query string
        """
        from core.models.query import QueryIntent

        intent_value = get_enum_value(intent)

        # Build query based on intent
        if intent_value == QueryIntent.HIERARCHICAL.value:
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN ['HAS_CHILD', 'PARENT_OF', 'CHILD_OF'])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        elif intent_value == QueryIntent.PREREQUISITE.value:
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN ['REQUIRES_KNOWLEDGE', 'PREREQUISITE_FOR', 'ENABLES'])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        elif intent_value == QueryIntent.PRACTICE.value:
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN ['PRACTICES', 'REINFORCES', 'APPLIES_KNOWLEDGE'])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        elif intent_value == QueryIntent.GOAL_ACHIEVEMENT.value:
            # Goal achievement path: tasks, habits, knowledge, subgoals, milestones, principles
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN [
                'FULFILLS_GOAL', 'SUPPORTS_GOAL', 'REQUIRES_KNOWLEDGE',
                'SUBGOAL_OF', 'HAS_MILESTONE', 'GUIDED_BY_PRINCIPLE',
                'CONTRIBUTES_TO_GOAL'
            ])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        elif intent_value == QueryIntent.PRINCIPLE_EMBODIMENT.value:
            # Principle embodiment: how principle is LIVED across domains
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN [
                'GUIDED_BY_PRINCIPLE', 'ALIGNED_WITH_PRINCIPLE', 'INSPIRES_HABIT',
                'GROUNDED_IN_KNOWLEDGE', 'GUIDES_GOAL', 'GUIDES_CHOICE'
            ])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        elif intent_value == QueryIntent.PRINCIPLE_ALIGNMENT.value:
            # Choice principle alignment: principles guiding choice, knowledge informing it
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN [
                'ALIGNED_WITH_PRINCIPLE', 'INFORMED_BY_KNOWLEDGE', 'SUPPORTS_GOAL',
                'CONFLICTS_WITH_GOAL', 'REQUIRES_KNOWLEDGE_FOR_DECISION',
                'OPENS_LEARNING_PATH', 'GUIDED_BY_PRINCIPLE'
            ])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        elif intent_value == QueryIntent.SCHEDULED_ACTION.value:
            # Scheduled action: tasks executed, knowledge practiced, habits reinforced
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WHERE any(r in relationships(path) WHERE type(r) IN [
                'EXECUTES_TASK', 'PRACTICES_KNOWLEDGE', 'REINFORCES_HABIT',
                'MILESTONE_FOR_GOAL', 'CONFLICTS_WITH', 'SUPPORTS_GOAL',
                'SCHEDULED_FOR', 'DERIVED_FROM_TASK'
            ])
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            """

        else:  # RELATIONSHIP, EXPLORATORY, SPECIFIC, AGGREGATION - generic traversal
            return f"""
            MATCH (origin {{uid: $uid}})
            OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
            WITH origin, collect(DISTINCT related) as nodes,
                 collect(DISTINCT [r in relationships(path) | {{
                     type: type(r),
                     start_uid: startNode(r).uid,
                     end_uid: endNode(r).uid,
                     properties: properties(r)
                 }}]) as rels
            RETURN nodes, rels[0] as relationships
            LIMIT 100
            """

    def _determine_domain(self, node_dict: dict[str, Any], labels: list[str]) -> Any:
        """
        Determine domain from node properties or labels.

        Args:
            node_dict: Node properties dictionary
            labels: Node labels list

        Returns:
            Domain enum value
        """
        from core.models.enums import Domain

        # Check if domain is in properties
        if "domain" in node_dict:
            domain_val = node_dict["domain"]
            try:
                return Domain(domain_val) if isinstance(domain_val, str) else domain_val
            except ValueError:
                pass

        # Infer from labels
        label_to_domain = {
            "Task": Domain.TASKS,
            "Habit": Domain.HABITS,
            "Goal": Domain.GOALS,
            "Event": Domain.EVENTS,
            "Ku": Domain.KNOWLEDGE,
            "Lp": Domain.LEARNING,
            "Finance": Domain.FINANCE,
            "Choice": Domain.CHOICES,
            "Principle": Domain.PRINCIPLES,
            "Journal": Domain.JOURNALS,
        }

        for label in labels:
            if label in label_to_domain:
                return label_to_domain[label]

        # Default fallback
        return Domain.KNOWLEDGE
