"""
Admin Lifecycle Mixin — UserService
=====================================

Admin-gated account lifecycle: role changes, listing, deactivation,
reactivation, and GDPR hard-delete. Every method verifies the acting admin
before touching the target, and the privilege-changing paths (role update,
deactivation) commit the change and the session revocation in ONE
transaction so no live cookie outlives its privileges.

Part of user_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.type_hints import UserUID
    from core.models.user import User
    from core.ports.service_protocols import SessionInvalidationOperations
    from core.services.user.user_core_service import UserCoreService

logger = get_logger(__name__)


class _AdminLifecycleMixin:
    """
    Admin-gated account lifecycle methods for UserService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by UserService.__init__
    core: UserCoreService
    session_invalidator: SessionInvalidationOperations | None
    get_user: Any  # delegation method on UserService

    async def hard_delete_user(
        self,
        target_user_uid: UserUID,
        admin_user_uid: UserUID,
        reason: str,
    ) -> Result[int]:
        """
        Hard-delete a user and every OWNS-linked entity (GDPR erasure, ADMIN only).

        Args:
            target_user_uid: User to erase.
            admin_user_uid: Admin initiating erasure (audit trail).
            reason: Free-form reason (required for audit).

        Returns:
            Result[int]: Count of deleted nodes (user + owned entities), or error.
        """
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted hard-delete of {target_user_uid}")
            return Result.fail(
                Errors.forbidden(
                    action="hard_delete_user",
                    reason="Hard-delete requires ADMIN role",
                    required_role=UserRole.ADMIN.value,
                )
            )

        return await self.core.hard_delete_user(
            target_user_uid,
            requester_role=admin.role,
            deleted_by=admin_user_uid,
            reason=reason,
        )

    async def update_role(
        self,
        target_user_uid: UserUID,
        new_role: UserRole,
        admin_user_uid: UserUID,
    ) -> Result[User]:
        """
        Update a user's role (ADMIN only).

        Performs authorization check before delegating to UserCoreService.

        Args:
            target_user_uid: User to update
            new_role: New role to assign
            admin_user_uid: UID of admin making the change

        Returns:
            Result[User]: Updated user or error

        Business Rules:
            - Only ADMIN can change user roles
            - Admins cannot demote themselves
            - Prevents escalation beyond ADMIN
            - An actual role change revokes all of the target's live sessions
              (forced re-login — see security-hardening roadmap item 4)
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(
                f"Non-admin {admin_user_uid} attempted to change role for {target_user_uid}"
            )
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can change user roles")
            )

        # Prevent self-demotion for admins
        if target_user_uid == admin_user_uid and new_role != UserRole.ADMIN:
            return Result.fail(
                Errors.business(rule="self_demotion", message="Admins cannot demote themselves")
            )

        # Fetch target first: a no-op role set must not revoke live sessions
        # (also keeps an ADMIN→ADMIN self-update from logging the admin out)
        target_result = await self.get_user(target_user_uid)
        if target_result.is_error:
            return Result.fail(target_result)
        if not target_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=target_user_uid))
        if target_result.value.role == new_role:
            return Result.ok(target_result.value)

        if self.session_invalidator is None:
            return Result.fail(
                Errors.system(
                    "Session invalidator not wired — pass session_invalidator to UserService",
                    operation="update_role",
                )
            )

        # Role change and session revocation commit in ONE transaction. Any
        # two-step sequence has a hole: revoke-then-update lets the target
        # sign in against the old user record inside the window (that fresh
        # session dodges the completed sweep — exploitable by a user being
        # demoted); update-then-revoke isn't retryable (the retry sees the
        # role already changed, takes the no-op branch above, and never
        # re-attempts the revocation).
        atomic = await self.session_invalidator.update_role_and_revoke_sessions(
            target_user_uid, new_role
        )
        if atomic.is_error:
            return Result.fail(atomic)
        logger.info(
            f"Updated role for {target_user_uid}: {target_result.value.role.value} → "
            f"{new_role.value}; revoked {atomic.value} live session(s)"
        )

        refreshed = await self.get_user(target_user_uid)
        if refreshed.is_error:
            return Result.fail(refreshed)
        if not refreshed.value:
            return Result.fail(Errors.not_found(resource="User", identifier=target_user_uid))
        return Result.ok(refreshed.value)

    async def list_users(
        self,
        admin_user_uid: UserUID,
        limit: int = 100,
        offset: int = 0,
        role_filter: UserRole | None = None,
        active_only: bool = True,
    ) -> Result[list[User]]:
        """
        List users (ADMIN only).

        Args:
            admin_user_uid: UID of admin making the request
            limit: Max results
            offset: Pagination offset
            role_filter: Optional filter by role
            active_only: Only return active users (default True)

        Returns:
            Result[list[User]]: List of users or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        if not admin_result.value.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to list users")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can list users")
            )

        # Delegate to core service
        return await self.core.list_users(limit, offset, role_filter, active_only)

    async def deactivate_user(
        self,
        target_user_uid: UserUID,
        admin_user_uid: UserUID,
        reason: str = "",
    ) -> Result[User]:
        """
        Deactivate a user account (ADMIN only).

        Deactivation and session revocation commit atomically (one Cypher
        transaction on SessionBackend) — deactivation must take effect
        immediately, not at next login, and must not be able to half-apply.

        Args:
            target_user_uid: User to deactivate
            admin_user_uid: Admin making the request
            reason: Reason for deactivation

        Returns:
            Result[User]: Updated user or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to deactivate {target_user_uid}")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can deactivate users")
            )

        # Prevent self-deactivation
        if target_user_uid == admin_user_uid:
            return Result.fail(
                Errors.business(
                    rule="self_deactivation", message="Admins cannot deactivate themselves"
                )
            )

        if self.session_invalidator is None:
            return Result.fail(
                Errors.system(
                    "Session invalidator not wired — pass session_invalidator to UserService",
                    operation="deactivate_user",
                )
            )

        # Deactivation and session revocation commit in ONE transaction.
        # Session nodes cache user_is_active at creation, and a two-step
        # sequence (persist is_active=false, then revoke) has a failure mode
        # where the account LOOKS deactivated but its live sessions keep
        # validating — and nothing prompts the admin to retry an operation
        # that already appears applied.
        atomic = await self.session_invalidator.deactivate_user_and_revoke_sessions(target_user_uid)
        if atomic.is_error:
            return Result.fail(atomic)
        logger.info(
            f"Deactivated {target_user_uid}, revoked {atomic.value} live session(s). "
            f"Reason: {reason or 'not specified'}"
        )

        refreshed = await self.get_user(target_user_uid)
        if refreshed.is_error:
            return Result.fail(refreshed)
        if not refreshed.value:
            return Result.fail(Errors.not_found(resource="User", identifier=target_user_uid))
        return Result.ok(refreshed.value)

    async def activate_user(
        self,
        target_user_uid: UserUID,
        admin_user_uid: UserUID,
    ) -> Result[User]:
        """
        Reactivate a user account (ADMIN only).

        Args:
            target_user_uid: User to reactivate
            admin_user_uid: Admin making the request

        Returns:
            Result[User]: Updated user or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        if not admin_result.value.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to activate {target_user_uid}")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can activate users")
            )

        # Delegate to core service
        return await self.core.activate_user(target_user_uid)
