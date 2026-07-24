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
    invalidator.invalidate_all_user_sessions = AsyncMock(
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
    service.core.update_user_role = AsyncMock(return_value=Result.ok(target))  # type: ignore[method-assign]
    service.core.deactivate_user = AsyncMock(return_value=Result.ok(target))  # type: ignore[method-assign]
    return service


# ============================================================================
# update_role
# ============================================================================


class TestUpdateRoleRevokesSessions:
    @pytest.mark.asyncio
    async def test_role_change_revokes_all_target_sessions(self):
        invalidator = _invalidator()
        service = _make_service(target_role=UserRole.REGISTERED, invalidator=invalidator)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_ok
        invalidator.invalidate_all_user_sessions.assert_awaited_once_with(TARGET_UID)

    @pytest.mark.asyncio
    async def test_noop_role_set_keeps_sessions(self):
        # Setting the role the user already has must not log them out —
        # this also protects an ADMIN→ADMIN self-update from self-logout.
        invalidator = _invalidator()
        service = _make_service(target_role=UserRole.MEMBER, invalidator=invalidator)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_ok
        invalidator.invalidate_all_user_sessions.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revocation_failure_leaves_role_unchanged(self):
        # THE retryability pin (Codex P1 on #798): revocation runs BEFORE the
        # role persists. Revoke-after was not retryable — the retry would see
        # the role already updated, take the no-op branch, and never
        # re-attempt the revocation. Failing here must leave the role
        # untouched so the admin's retry re-runs both steps.
        invalidator = _invalidator(
            Result.fail(Errors.database(operation="invalidate", message="neo4j down"))
        )
        service = _make_service(invalidator=invalidator)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_error
        assert "session" in result.expect_error().message.lower()
        service.core.update_user_role.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_failed_role_update_after_revocation_errors(self):
        # Revocation succeeded but the role persist failed: surface the error.
        # The target re-logs-in with the old role — annoying, never insecure.
        invalidator = _invalidator()
        service = _make_service(invalidator=invalidator)
        service.core.update_user_role = AsyncMock(  # type: ignore[method-assign]
            return_value=Result.fail(Errors.database(operation="update", message="boom"))
        )

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_error
        invalidator.invalidate_all_user_sessions.assert_awaited_once_with(TARGET_UID)

    @pytest.mark.asyncio
    async def test_unwired_invalidator_fails_fast(self):
        service = _make_service(invalidator=None)

        result = await service.update_role(TARGET_UID, UserRole.MEMBER, ADMIN_UID)

        assert result.is_error
        assert "not wired" in result.expect_error().message
        service.core.update_user_role.assert_not_awaited()  # type: ignore[attr-defined]


# ============================================================================
# deactivate_user
# ============================================================================


class TestDeactivateUserRevokesSessions:
    @pytest.mark.asyncio
    async def test_deactivation_revokes_all_target_sessions(self):
        # Session nodes cache user_is_active at creation — without explicit
        # revocation a deactivated user's live sessions would stay valid.
        invalidator = _invalidator()
        service = _make_service(invalidator=invalidator)

        result = await service.deactivate_user(TARGET_UID, ADMIN_UID, reason="test")

        assert result.is_ok
        invalidator.invalidate_all_user_sessions.assert_awaited_once_with(TARGET_UID)

    @pytest.mark.asyncio
    async def test_failed_deactivation_keeps_sessions(self):
        invalidator = _invalidator()
        service = _make_service(invalidator=invalidator)
        service.core.deactivate_user = AsyncMock(  # type: ignore[method-assign]
            return_value=Result.fail(Errors.database(operation="deactivate", message="boom"))
        )

        result = await service.deactivate_user(TARGET_UID, ADMIN_UID, reason="test")

        assert result.is_error
        invalidator.invalidate_all_user_sessions.assert_not_awaited()
