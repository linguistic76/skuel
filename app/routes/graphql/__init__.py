"""
GraphQL API Module for SKUEL
============================

Provides GraphQL interface for complex nested queries and real-time updates.
"""

from routes.graphql.auth import require_user_uid, resolve_target_user
from routes.graphql.context import GraphQLContext, create_graphql_context
from routes.graphql.schema import create_graphql_schema

__all__ = [
    "GraphQLContext",
    "create_graphql_context",
    "create_graphql_schema",
    "require_user_uid",
    "resolve_target_user",
]
