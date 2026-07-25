"""
GraphQL API Module for SKUEL
============================

Provides GraphQL interface for complex nested queries (read-only).
"""

from adapters.inbound.graphql.auth import require_user_uid, resolve_target_user
from adapters.inbound.graphql.context import GraphQLContext, create_graphql_context
from adapters.inbound.graphql.schema import create_graphql_schema

__all__ = [
    "GraphQLContext",
    "create_graphql_context",
    "create_graphql_schema",
    "require_user_uid",
    "resolve_target_user",
]
