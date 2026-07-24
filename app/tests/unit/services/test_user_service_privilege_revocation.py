"""UserService session revocation on privilege change (role update, deactivation).

Roadmap: security-hardening-deferred item 4 — an actual privilege change must
revoke every live session so no cookie outlives its privileges. Revocation is
enforced per-request by AuthContextMiddleware (tests in
tests/unit/adapters/test_auth_context.py); these tests cover the service-side
trigger.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import UserRole
from core.models.type_hints import UserUID
from core.services.user_service import UserService
from core.utils.result_simplified import Errors, Result

ADMIN_UID = UserUID("user_admin")
TARGET_UID = UserUID("user_target")


def _user(role: UserRole, *, admin: bool = False) -> MagicMock:
    user = MagicMock()
    user.role = role
    user.can_manage_users = MagicMock(return_value=admin)
    return user


def _invalidator(result: Result | None = None) -> MagicMock:
    invalidator = MagicMock()
    invalidator.update_role_and_revoke_sessions = AsyncMock(
        return_value=result if result is not None else Result.ok(2)
    )
    invalidator.deactivate_user_and_revoke_sessions = AsyncMock(
        return_value=result if result is not None else Result.ok(2)
    )
    return invalidator


def _make_service(
    *,
    target_role: UserRole = UserRole.REGISTERED,
    invalidator: MagicMock | None = None,
) -> UserService:
    """Real facade, mocked below the seams update_role/deactivate_user use."""
    service = UserService(MagicMock(), session_invalidator=invalidator)
    admin = _user(UserRole.ADMIN, admin=True)
    target = _user(target_role)

    async def get_user(uid: UserUID) -> Result:
        return Result.ok(admin if uid == ADMIN_UID else target)

    service.get_user = get_user  # type: ignore[method-assign, assignment]
    return service


# ============================================================================
# update_role
# ============================================================================


class TestUpdateRoleRevokesSessions:
    @pytest.mark.asyncio
    async def test_role_change_uses_the_atomic_seam(self):
        # Role change + revocation commit in ONE transaction (Codex on #798):
        # revoke-then-update let the target sign in against the old record
        # inside the window; update-then-revoke wasn't retryable (the retry
        # saw the role already changed and skipped the revocation).
        invalidator = _invalidator()
        service = _make_service(target_role=UserRole.REGISTERED, invalidator=invalidator)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_ok
        invalidator.update_role_and_revoke_sessions.assert_awaited_once_with(
            TARGET_UID, UserRole.MEMBER
        )

    @pytest.mark.asyncio
    async def test_noop_role_set_keeps_sessions(self):
        # Setting the role the user already has must not log them out —
        # this also protects an ADMIN→ADMIN self-update from self-logout.
        invalidator = _invalidator()
        service = _make_service(target_role=UserRole.MEMBER, invalidator=invalidator)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_ok
        invalidator.update_role_and_revoke_sessions.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_atomic_role_change_surfaces_error(self):
        invalidator = _invalidator(
            Result.fail(Errors.database(operation="update_role", message="neo4j down"))
        )
        service = _make_service(invalidator=invalidator)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_unwired_invalidator_fails_fast(self):
        service = _make_service(invalidator=None)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_error
        assert "not wired" in result.expect_error().message


# ============================================================================
# deactivate_user
# ============================================================================


class TestDeactivateUserRevokesSessions:
    @pytest.mark.asyncio
    async def test_deactivation_uses_the_atomic_seam(self):
        # Deactivation + revocation commit in ONE transaction (Codex P1 on
        # #798 round 2): a two-step sequence could leave the account looking
        # deactivated while its live sessions kept validating — with nothing
        # prompting a retry of an operation that already appears applied.
        invalidator = _invalidator()
        service = _make_service(invalidator=invalidator)

        result = await service.deactivate_user(TARGET_UID, ADMIN_UID, reason="test")

        assert result.is_ok
        invalidator.deactivate_user_and_revoke_sessions.assert_awaited_once_with(TARGET_UID)

    @pytest.mark.asyncio
    async def test_failed_atomic_deactivation_surfaces_error(self):
        invalidator = _invalidator()
        service = _make_service(invalidator=invalidator)
        invalidator.deactivate_user_and_revoke_sessions = AsyncMock(
            return_value=Result.fail(Errors.database(operation="deactivate", message="boom"))
        )

        result = await service.deactivate_user(TARGET_UID, ADMIN_UID, reason="test")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_unwired_invalidator_fails_fast(self):
        service = _make_service(invalidator=None)

        result = await service.deactivate_user(TARGET_UID, ADMIN_UID, reason="test")

        assert result.is_error
        assert "not wired" in result.expect_error().message
