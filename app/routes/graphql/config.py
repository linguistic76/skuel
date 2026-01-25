"""
GraphQL Configuration and Guardrails
====================================

Production-ready GraphQL configuration with security limits.
"""

from dataclasses import dataclass


@dataclass
class GraphQLConfig:
    """
    GraphQL security and performance configuration.

    These limits prevent abuse and ensure good performance.
    """

    # Query Depth Limits
    max_query_depth: int = 5  # Prevent deeply nested queries
    max_aliases: int = 10  # Prevent alias-based DoS attacks

    # Node Limits (prevent fetching too much data)
    max_list_size: int = 100  # Maximum items in any list
    default_list_size: int = 20  # Default if not specified

    # Timeout Limits
    max_query_timeout_seconds: int = 30  # Kill queries taking too long
    max_resolver_timeout_seconds: int = 10  # Individual resolver timeout

    # Complexity Limits
    max_query_complexity: int = 1000  # Maximum complexity score
    max_query_tokens: int = 1000  # Maximum tokens in query (prevent huge queries)
    field_complexity_multiplier: float = 1.0  # Adjust complexity calculations

    # DataLoader Limits
    max_batch_size: int = 100  # Maximum items per DataLoader batch

    # Cypher Query Limits (Neo4j specific)
    max_cypher_depth: int = 5  # Maximum graph traversal depth
    max_cypher_nodes: int = 1000  # Maximum nodes to return
    cypher_timeout_seconds: int = 10  # Cypher query timeout

    # Field-Level Complexity Costs
    # These define the computational cost of different field types
    basic_field_cost: int = 1  # Simple scalar fields
    list_field_cost: int = 10  # Fields that return lists
    nested_object_cost: int = 5  # Nested object fields
    resolver_field_cost: int = 10  # Fields with custom resolvers (DataLoader)


# Global config instance
graphql_config = GraphQLConfig()


def get_graphql_config() -> GraphQLConfig:
    """Get GraphQL configuration."""
    return graphql_config


def validate_list_limit(limit: int | None, default: int | None = None) -> int:
    """
    Validate and normalize list limit parameter.

    Args:
        limit: Requested limit (from query)
        default: Default limit to use if not specified

    Returns:
        Validated limit within allowed range

    Example:
        @strawberry.field
        async def knowledge_units(
            self,
            limit: int | None = None
        ) -> list[KnowledgeNode]:
            # Validate limit
            safe_limit = validate_list_limit(limit)  # Max 100, default 20
            result = await service.list_knowledge_units(limit=safe_limit)
    """
    config = get_graphql_config()

    # Use provided default or config default
    default_limit = default if default is not None else config.default_list_size

    # If no limit specified, use default
    if limit is None:
        return default_limit

    # Enforce maximum
    if limit > config.max_list_size:
        return config.max_list_size

    # Enforce minimum
    if limit < 1:
        return default_limit

    return limit


def validate_query_depth(depth: int | None, default: int = 2) -> int:
    """
    Validate graph traversal depth parameter.

    Args:
        depth: Requested depth (from query)
        default: Default depth if not specified

    Returns:
        Validated depth within allowed range

    Example:
        async def get_knowledge_with_context(
            uid: str,
            depth: int | None = None
        ):
            safe_depth = validate_query_depth(depth, default=2)
            # Use safe_depth in Cypher query
    """
    config = get_graphql_config()

    # Use default if not specified
    if depth is None:
        return default

    # Enforce maximum
    if depth > config.max_cypher_depth:
        return config.max_cypher_depth

    # Enforce minimum
    if depth < 0:
        return 0

    return depth
