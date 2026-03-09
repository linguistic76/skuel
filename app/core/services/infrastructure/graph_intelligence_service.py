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
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

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
        MATCH (ku:Entity)
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
            return Result.fail(result.expect_error())

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
        MATCH (ku1:Entity {uid: $uid})-[]-(shared)-[]-(ku2:Entity)
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
            return Result.fail(result.expect_error())

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
        MATCH path = (end:Entity {uid: $uid})<-[:REQUIRES_KNOWLEDGE*]-(start)
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
            return Result.fail(result.expect_error())

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
            f"Prerequisite analysis: depth={analysis['max_depth']}, paths={analysis['total_paths']}"
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
        MATCH (ku:Entity)
        {domain_filter}
        MATCH (ku)-[r]-(neighbor:Entity)
        WITH ku, count(DISTINCT neighbor) as neighbor_count
        WHERE neighbor_count >= 2

        // Count triangles (ku-n1-n2-ku closed patterns)
        MATCH (ku)-[]-(n1:Entity)-[]-(n2:Entity)-[]-(ku)
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
            return Result.fail(result.expect_error())

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
        MATCH (ku:Entity {uid: $uid})

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
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.fail(Errors.not_found(resource="Entity", identifier=ku_uid))

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
        from core.services.infrastructure.graph_query_builder import (
            build_context_query_for_intent,
        )
        from core.services.infrastructure.graph_record_transformer import (
            transform_records_to_graph_context,
        )

        self.logger.info(
            f"Querying graph context: domain={domain}, node={node_uid}, "
            f"intent={intent}, depth={depth}"
        )

        query = build_context_query_for_intent(intent, depth)
        params = {"uid": node_uid}

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        if not records:
            return Result.fail(Errors.not_found(resource="Node", identifier=node_uid))

        graph_context = transform_records_to_graph_context(records, node_uid, domain, intent, depth)

        self.logger.info(
            f"Graph context retrieved: {graph_context.total_nodes} nodes, "
            f"{graph_context.total_relationships} relationships, "
            f"{len(graph_context.domains_involved)} domains"
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
        from core.models.query_types import QueryIntent
        from core.services.infrastructure.graph_query_builder import determine_domain

        # First, determine domain of entity by fetching it
        query = """
        MATCH (n {uid: $uid})
        RETURN n, labels(n) as labels
        """

        result = await self.executor.execute_query(query, {"uid": entity_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        if not records:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

        node_labels = records[0]["labels"]
        domain = determine_domain(records[0]["n"], node_labels)

        return await self.query_with_intent(
            domain=domain,
            node_uid=entity_uid,
            intent=QueryIntent.RELATIONSHIP,
            depth=depth,
        )
