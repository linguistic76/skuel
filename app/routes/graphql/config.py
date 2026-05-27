"""
GraphQL Configuration and Guardrails
====================================

Production-ready GraphQL configuration with security limits.
"""

from dataclasses import dataclass


@dataclass
class GraphQLConfig:
    """GraphQL security and performance limits.

    Every field here is enforced — there is no aspirational config. The
    query-shape limits (depth, tokens, aliases, complexity) run as Strawberry
    schema extensions; the timeouts run at the adapter boundary and as a
    per-resolver wrapper; the list / traversal caps are applied by the
    ``validate_*`` helpers below.

    A Cypher / transaction timeout is intentionally NOT here: it is a database
    concern that already has a home in ``DatabaseConfig.query_timeout`` and
    governs the app-wide executor, not just GraphQL.

    See: routes/graphql/guardrails.py (complexity + resolver-timeout extensions),
    adapters/inbound/graphql_routes.py (request timeout), schema.py (wiring).
    """

    # Query-shape limits — enforced as Strawberry schema extensions.
    max_query_depth: int = 5  # QueryDepthLimiter — cap nesting depth
    max_query_tokens: int = 1000  # MaxTokensLimiter — cap query size
    max_aliases: int = 10  # MaxAliasesLimiter — cap aliases (alias-based DoS)
    max_query_complexity: int = 1000  # QueryComplexityLimiter — cap summed field cost

    # Field-cost weights for QueryComplexityLimiter (see guardrails.py).
    basic_field_cost: int = 1  # Scalar / leaf field
    list_field_cost: int = 10  # Field returning a list
    nested_object_cost: int = 5  # Nested object field
    field_complexity_multiplier: float = 1.0  # Global scale on the summed cost

    # Timeouts (seconds) — request-level at the adapter, per-resolver via extension.
    max_query_timeout_seconds: int = 30  # Whole-operation ceiling (asyncio.wait_for)
    max_resolver_timeout_seconds: int = 10  # Per-resolver ceiling (ResolverTimeoutExtension)

    # List / traversal caps — applied by validate_list_limit / validate_query_depth.
    max_list_size: int = 100  # Maximum items in any list
    default_list_size: int = 20  # Default list size when unspecified
    max_cypher_depth: int = 5  # Maximum graph-traversal depth in resolvers

    # DataLoader batching — passed to every per-request DataLoader (context.py).
    max_batch_size: int = 100  # Maximum keys per DataLoader batch


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
