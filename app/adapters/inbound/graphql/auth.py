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
    Info,
)

from adapters.inbound.graphql.context import GraphQLContext
from core.models.enums.user_enums import UserRole
from core.models.type_hints import TypeConverter, UserUID


def require_user_uid(info: Info[GraphQLContext, Any]) -> UserUID:
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
            # user_uid is guaranteed to be a non-empty UserUID
    """
    user_uid = info.context.user_uid
    if not user_uid:
        raise ValueError(
            "GraphQL context missing user_uid — "
            "this indicates a bug in route wiring (auth should be enforced at HTTP layer)"
        )
    return user_uid


async def resolve_target_user(
    info: Info[GraphQLContext, Any], user_uid: str | None = None
) -> UserUID:
    """
    Resolve the target user for a query that accepts an optional user_uid override.

    This is the honest UserUID boundary for the GraphQL surface: the override
    arrives from the client as a raw GraphQL ``String`` (hence the ``str | None``
    param), and is validated + narrowed to ``UserUID`` here. Resolvers therefore
    pass their client-supplied ``user_uid`` query argument straight through — no
    per-call-site conversion and no ``UserUID`` custom scalar in the schema.

    Used by resolvers that allow admin queries against other users' data.
    Falls back to the authenticated user when no override is provided.
    When a user_uid override is supplied, the caller must have ADMIN role.

    Args:
        info: Strawberry resolver info with GraphQLContext
        user_uid: Optional client-supplied override (requires admin role)

    Returns:
        Target user UID (validated override or authenticated user)

    Raises:
        PermissionError: If user_uid override is provided by a non-admin caller
        ValueError: If the override is not a canonical ``user_<name>`` UID

    Usage::

        @strawberry.field
        async def learning_path_with_context(
            self,
            info: Info[GraphQLContext, Any],
            path_uid: str,
            user_uid: str | None = None,
        ) -> LearningPathContext | None:
            target_user_uid = await resolve_target_user(info, user_uid)
    """
    caller_uid = require_user_uid(info)
    if not user_uid:
        return caller_uid

    # Override requested — verify caller is admin
    context: GraphQLContext = info.context
    user_service = context.services.user
    if not user_service:
        raise PermissionError("User service unavailable — cannot verify admin role")

    caller_result = await user_service.get_user(caller_uid)
    if caller_result.is_error:
        raise PermissionError("Could not verify caller role")

    caller_user = caller_result.value
    if not caller_user:
        raise PermissionError("Could not verify caller role")
    if not caller_user.has_permission(UserRole.ADMIN):
        raise PermissionError("Admin role required to query other users' data")

    # Validate + narrow the client-supplied override to UserUID at this boundary.
    return TypeConverter.to_user_uid(user_uid)


__all__ = [
    "require_user_uid",
    "resolve_target_user",
]
