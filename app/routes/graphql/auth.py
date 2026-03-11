"""
GraphQL Authentication Helpers
==============================

Provides resolver-level auth utilities for extracting the authenticated user
from GraphQL context. Authentication is enforced at the HTTP layer
(``require_authenticated_user`` in ``graphql_routes.py``), so these helpers
are defense-in-depth — they should never fail in normal operation.

Error strategy (decided March 2026):
    - HTTP layer: 401 for unauthenticated requests (hard boundary)
    - Resolver layer: GraphQL error only if context.user_uid is missing
      (should not happen — indicates a bug in route wiring)
    - Data layer: empty list / None for missing data (graceful)
"""

from __future__ import annotations

from typing import Any

from strawberry.types import (
    Info,  # noqa: TC002 - Strawberry evaluates resolver annotations at runtime
)

from routes.graphql.context import GraphQLContext


def require_user_uid(info: Info[GraphQLContext, Any]) -> str:
    """
    Extract the authenticated user UID from GraphQL context.

    This is the standard way to get user_uid in resolvers. Since auth is
    enforced at the HTTP layer, this should always succeed. A missing
    user_uid indicates a route wiring bug, not a client auth failure.

    Args:
        info: Strawberry resolver info with GraphQLContext

    Returns:
        Authenticated user's UID

    Raises:
        ValueError: If user_uid is missing from context (bug in route wiring)

    Usage::

        @strawberry.field
        async def tasks(self, info: Info[GraphQLContext, Any]) -> list[Task]:
            user_uid = require_user_uid(info)
            # user_uid is guaranteed to be a non-empty string
    """
    user_uid = info.context.user_uid
    if not user_uid:
        raise ValueError(
            "GraphQL context missing user_uid — "
            "this indicates a bug in route wiring (auth should be enforced at HTTP layer)"
        )
    return user_uid


def resolve_target_user(info: Info[GraphQLContext, Any], user_uid: str | None = None) -> str:
    """
    Resolve the target user for a query that accepts an optional user_uid override.

    Used by resolvers that allow admin queries against other users' data.
    Falls back to the authenticated user when no override is provided.

    Args:
        info: Strawberry resolver info with GraphQLContext
        user_uid: Optional override (for admin queries)

    Returns:
        Target user UID (override or authenticated user)

    Usage::

        @strawberry.field
        async def learning_path_with_context(
            self,
            info: Info[GraphQLContext, Any],
            path_uid: str,
            user_uid: str | None = None,
        ) -> LearningPathContext | None:
            target_user_uid = resolve_target_user(info, user_uid)
    """
    if user_uid:
        # TODO: Add admin permission check (ADR pending)
        return user_uid
    return require_user_uid(info)


__all__ = [
    "require_user_uid",
    "resolve_target_user",
]
