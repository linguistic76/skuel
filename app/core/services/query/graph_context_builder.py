"""
Graph Context Query Builder
===========================

Builds graph traversal queries for context discovery.

Part of QueryBuilder decomposition.
"""

from core.models.query_types import QueryIntent
from adapters.persistence.neo4j.query.graph_traversal import build_graph_context_query
from core.utils.logging import get_logger


class GraphContextBuilder:
    """
    Builds graph traversal queries for discovering entity context.

    Uses variable-length patterns instead of APOC procedures for
    pure Cypher graph traversal.
    """

    def __init__(self, schema_service=None) -> None:
        """
        Initialize graph context builder.

        Args:
            schema_service: Schema service (not currently used, for consistency)
        """
        self.schema_service = schema_service
        self.logger = get_logger("GraphContextBuilder")

    def build_graph_context_query(self, node_uid: str, intent: QueryIntent, depth: int = 2) -> str:
        """
        Build Pure Cypher query for graph context traversal.

        Uses variable-length patterns to discover related entities
        within N hops of the starting node.

        Args:
            node_uid: Starting node UID
            intent: Query intent (determines relationship types to traverse)
            depth: Maximum traversal depth (default: 2 hops)

        Returns:
            str: Cypher query for graph context discovery

        Example:
            >>> builder = GraphContextBuilder()
            >>> query = builder.build_graph_context_query(
            ... node_uid="task:123", intent=QueryIntent.DISCOVER_CONTEXT, GraphDepth.NEIGHBORHOOD
            ... )
        """
        self.logger.debug(f"Building graph context query for node={node_uid}, depth={depth}")
        return build_graph_context_query(node_uid, intent, depth)
