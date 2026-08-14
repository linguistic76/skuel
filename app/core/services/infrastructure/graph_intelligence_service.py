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

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import Domain
from core.models.type_hints import EntityUID
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.ports.cross_domain_protocols import CrossDomainBackendOperations

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

    def __init__(self, backend: CrossDomainBackendOperations) -> None:
        """
        Initialize graph intelligence service.

        Args:
            backend: CrossDomainBackend for graph queries
        """
        self.backend = backend
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

        result = await self.backend.find_knowledge_hubs(domain_filter=domain_filter, params=params)
        if result.is_error:
            return Result.fail(result)

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

        result = await self.backend.find_similar_knowledge(
            uid=ku_uid, min_similarity=min_similarity, limit=limit
        )
        if result.is_error:
            return Result.fail(result)

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

        result = await self.backend.analyze_prerequisite_depth(uid=ku_uid)
        if result.is_error:
            return Result.fail(result)

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

        result = await self.backend.find_learning_clusters(
            domain_filter=domain_filter, params=params
        )
        if result.is_error:
            return Result.fail(result)

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

        result = await self.backend.calculate_knowledge_importance(uid=ku_uid)
        if result.is_error:
            return Result.fail(result)

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
        relationship_types: list[str] | None = None,
    ) -> Result[GraphContext]:
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
            relationship_types: Optional registry-sourced edge vocabulary (mechanism B /
                Convergence Phase 1). When supplied, the traversal filters on these edge
                types — the domain's ``cross_domain_relationship_types`` — instead of the
                hard-coded per-intent literal. ``intent`` still shapes the result.
                See: /docs/roadmap/intent-traversal-registry-convergence.md

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
        from core.services.infrastructure.graph_record_transformer import (
            build_graph_context_from_domain_context,
        )

        self.logger.info(
            f"Querying graph context: domain={domain}, node={node_uid}, "
            f"intent={intent}, depth={depth}"
        )

        result = await self.backend.query_with_intent(
            intent=intent, depth=depth, uid=node_uid, relationship_types=relationship_types
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value or []

        if not records:
            return Result.fail(Errors.not_found(resource="Node", identifier=node_uid))

        # The shared producer returns one record {center_uid, domain_context}; the
        # transformer de-dups the attributed node list into a GraphContext.
        domain_context = records[0].get("domain_context", [])
        graph_context = build_graph_context_from_domain_context(
            domain_context, node_uid, domain, intent, depth
        )

        self.logger.info(
            f"Graph context retrieved: {graph_context.total_nodes} nodes, "
            f"{graph_context.total_relationships} relationships, "
            f"{len(graph_context.domains_involved)} domains"
        )

        return Result.ok(graph_context)

    @with_error_handling(error_type="database")
    async def get_sel_categories(self, uids: list[str]) -> Result[dict[str, str]]:
        """Batch-resolve entity UIDs to their ``sel_category`` field.

        The field-based grouping for cross-domain pattern analysis — entity
        kind and category come from stored fields, never from parsing the
        UID string (ADR-013 never-sniff). Entities without a category are
        omitted from the mapping (deliberately unassigned is valid).

        Backend: CrossDomainBackend.get_sel_categories
        """
        result = await self.backend.get_sel_categories(uids)
        if result.is_error:
            return Result.fail(result)
        # SelCategoryRow guarantees both keys (nulls filtered at the source).
        return Result.ok({row["uid"]: row["sel_category"] for row in result.value or []})

    @with_error_handling(error_type="database", uid_param="entity_uid")
    async def get_entity_context(
        self, entity_uid: EntityUID, depth: int = 2
    ) -> Result[GraphContext]:
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
        from core.services.infrastructure.graph_record_transformer import determine_domain

        # First, determine domain of entity by fetching it
        result = await self.backend.get_entity_labels(uid=entity_uid)
        if result.is_error:
            return Result.fail(result)

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
