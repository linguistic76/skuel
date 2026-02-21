"""
Route Helpers - Shared Utilities for Route Factories
=====================================================

Extracted common patterns to eliminate duplication across factories.
Each helper follows SKUEL's Result[T] pattern: returns Result internally;
boundary_handler converts to HTTP at the route level.

Helpers:
    check_required_role   - Role-based access control (used by CRUD, Analytics)
    verify_entity_ownership - Ownership verification returning 404 on failure (used by Status, Query, Intelligence)

See: /docs/patterns/AUTH_PATTERNS.md, /docs/patterns/OWNERSHIP_VERIFICATION.md
"""

from collections.abc import Callable
from typing import Any

from adapters.inbound.auth.session import require_authenticated_user
from core.models.enums import UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.helpers")


async def check_required_role(
    request: Any,
    require_role: UserRole | None,
    user_service_getter: Callable | None,
    domain: str,
) -> Result[None]:
    """
    Check if the authenticated user has the required role.

    Returns Result.ok(None) if no role is configured or user is authorized.
    Returns Result.fail with Forbidden error if user lacks the required role.

    Args:
        request: FastHTML request object
        require_role: Required role (None = no check needed)
        user_service_getter: Callable returning UserService (required when require_role is set)
        domain: Domain name for error messages

    See: /docs/patterns/AUTH_PATTERNS.md
    """
    if not require_role:
        return Result.ok(None)

    if not user_service_getter:
        return Result.fail(
            Errors.system(
                message="Role check requires user_service_getter",
                operation="check_required_role",
            )
        )

    user_uid = require_authenticated_user(request)

    user_service = user_service_getter()
    result = await user_service.get_user(user_uid)

    if result.is_error or not result.value:
        return Result.fail(
            Errors.forbidden(
                action=f"access {domain}",
                reason="User not found or access denied",
            )
        )

    user = result.value

    if not user.has_permission(require_role):
        return Result.fail(
            Errors.forbidden(
                action=f"access {domain}",
                reason=f"Requires {require_role.value} role or higher",
                required_role=require_role.value,
            )
        )

    return Result.ok(None)


async def verify_entity_ownership(
    service: Any,
    uid: str,
    user_uid: str,
    domain: str = "",
) -> Result[Any] | None:
    """
    Verify that a user owns an entity.

    Returns error Result if ownership check fails, None if it passes.
    Callers use truthiness check:

        ownership_error = await verify_entity_ownership(service, uid, user_uid, domain)
        if ownership_error:
            return ownership_error

    Security: Returns NotFound (404) not Forbidden (403), preventing UID enumeration.

    Args:
        service: Any service with a verify_ownership(uid, user_uid) -> Result method
        uid: Entity UID to check
        user_uid: Authenticated user UID
        domain: Domain name for debug logging

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md
    """
    ownership_result = await service.verify_ownership(uid, user_uid)
    if ownership_result.is_error:
        if domain:
            logger.debug(f"Ownership verification failed for {domain}: uid={uid}, user={user_uid}")
        return ownership_result
    return None


__all__ = ["check_required_role", "verify_entity_ownership"]
