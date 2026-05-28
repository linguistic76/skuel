"""
Regression: WS admin re-checks Neo4j (not session is_admin flag)
================================================================

Closes 2026-05-26 security audit finding: `require_websocket_admin` previously
trusted the `session.is_admin` cookie flag, so a user demoted from ADMIN kept
WS access until re-login. The helper now fetches the user via `user_service`
and gates on `User.has_permission(UserRole.ADMIN)` — mirroring the HTTP
`@require_admin` path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.inbound.auth import require_websocket_admin
from core.models.enums import UserRole
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def ws_authenticated() -> MagicMock:
    """WebSocket-like mock with an authenticated session (no is_admin flag)."""
    ws = MagicMock()
    ws.session = {"user_uid": "user_alice"}
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def ws_anonymous() -> MagicMock:
    """WebSocket-like mock with no user in session."""
    ws = MagicMock()
    ws.session = {}
    ws.close = AsyncMock()
    return ws


def _user_service_returning(*, role: UserRole | None) -> MagicMock:
    """Mock UserService whose get_user returns a user with the given role, or NotFound."""
    service = MagicMock()
    if role is None:
        service.get_user = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="User", identifier="user_alice"))
        )
    else:
        user = MagicMock()
        user.role = role
        user.has_permission = lambda required: role.has_permission(required)
        service.get_user = AsyncMock(return_value=Result.ok(user))
    return service


@pytest.mark.asyncio
async def test_admin_passes(ws_authenticated):
    """ADMIN role from DB → returns UserUID, ws.close NOT called."""
    user_service = _user_service_returning(role=UserRole.ADMIN)

    user_uid = await require_websocket_admin(ws_authenticated, user_service)

    assert user_uid == "user_alice"
    ws_authenticated.close.assert_not_called()
    user_service.get_user.assert_awaited_once_with("user_alice")


@pytest.mark.asyncio
async def test_demoted_user_rejected_even_with_stale_session_flag(ws_authenticated):
    """The real security gap: session may say is_admin=True, but DB role is MEMBER → REJECT."""
    ws_authenticated.session["is_admin"] = True  # Stale cookie flag
    user_service = _user_service_returning(role=UserRole.MEMBER)

    user_uid = await require_websocket_admin(ws_authenticated, user_service)

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()
    args, kwargs = ws_authenticated.close.call_args
    assert kwargs.get("code", args[0] if args else None) == 4003


@pytest.mark.asyncio
async def test_teacher_rejected(ws_authenticated):
    """TEACHER role lacks ADMIN permission → REJECT."""
    user_service = _user_service_returning(role=UserRole.TEACHER)

    user_uid = await require_websocket_admin(ws_authenticated, user_service)

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_not_found_rejected(ws_authenticated):
    """Stale cookie pointing to a deleted user → REJECT (no crash, no allow)."""
    user_service = _user_service_returning(role=None)

    user_uid = await require_websocket_admin(ws_authenticated, user_service)

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unauthenticated_rejected_without_db_call(ws_anonymous):
    """No session user → short-circuit close, never touch DB."""
    user_service = _user_service_returning(role=UserRole.ADMIN)

    user_uid = await require_websocket_admin(ws_anonymous, user_service)

    assert user_uid is None
    ws_anonymous.close.assert_awaited_once()
    user_service.get_user.assert_not_called()
