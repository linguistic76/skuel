"""
Regression: WS admin validates the graph session AND re-checks Neo4j role
==========================================================================

Two closed findings layer here:

- 2026-05-26 security audit: `require_websocket_admin` previously trusted the
  `session.is_admin` cookie flag, so a user demoted from ADMIN kept WS access
  until re-login. The helper fetches the user via `user_service` and gates on
  `User.has_permission(UserRole.ADMIN)` — mirroring HTTP `@require_admin`.
- Codex P1 on #798: AuthContextMiddleware never sees WebSocket scopes
  (BaseHTTPMiddleware is HTTP-only), so the helper validated the role but not
  the SESSION — a cookie revoked by logout/password change/privilege change
  could still open a socket. The handshake now validates `session_token`
  against the graph before any role check.
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
    ws.session = {"user_uid": "user_alice", "session_token": "tok"}
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


def _graph_auth_returning(result: Result | None = None) -> MagicMock:
    """Mock GraphAuthService; default validates the token to user_alice."""
    graph_auth = MagicMock()
    graph_auth.validate_session_uid = AsyncMock(
        return_value=result if result is not None else Result.ok("user_alice")
    )
    return graph_auth


@pytest.mark.asyncio
async def test_admin_passes(ws_authenticated):
    """Live session + ADMIN role from DB → returns UserUID, ws.close NOT called."""
    user_service = _user_service_returning(role=UserRole.ADMIN)
    graph_auth = _graph_auth_returning()

    user_uid = await require_websocket_admin(ws_authenticated, user_service, graph_auth)

    assert user_uid == "user_alice"
    ws_authenticated.close.assert_not_called()
    graph_auth.validate_session_uid.assert_awaited_once_with("tok")
    user_service.get_user.assert_awaited_once_with("user_alice")


@pytest.mark.asyncio
async def test_revoked_session_rejected_before_role_check(ws_authenticated):
    """Codex P1 on #798: a revoked cookie must not open a socket, even for an
    admin — the graph-session check runs BEFORE (and instead of reaching) the
    role fetch."""
    user_service = _user_service_returning(role=UserRole.ADMIN)
    graph_auth = _graph_auth_returning(Result.ok(None))  # revoked/expired

    user_uid = await require_websocket_admin(ws_authenticated, user_service, graph_auth)

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()
    user_service.get_user.assert_not_called()


@pytest.mark.asyncio
async def test_validation_error_rejected(ws_authenticated):
    """Graph unreachable → fail closed (deny the handshake, no role fetch)."""
    user_service = _user_service_returning(role=UserRole.ADMIN)
    graph_auth = _graph_auth_returning(
        Result.fail(Errors.database(operation="validate", message="down"))
    )

    user_uid = await require_websocket_admin(ws_authenticated, user_service, graph_auth)

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()
    user_service.get_user.assert_not_called()


@pytest.mark.asyncio
async def test_demoted_user_rejected_even_with_stale_session_flag(ws_authenticated):
    """The original gap: session may say is_admin=True, but DB role is MEMBER → REJECT."""
    ws_authenticated.session["is_admin"] = True  # Stale cookie flag
    user_service = _user_service_returning(role=UserRole.MEMBER)

    user_uid = await require_websocket_admin(
        ws_authenticated, user_service, _graph_auth_returning()
    )

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()
    args, kwargs = ws_authenticated.close.call_args
    assert kwargs.get("code", args[0] if args else None) == 4003


@pytest.mark.asyncio
async def test_teacher_rejected(ws_authenticated):
    """TEACHER role lacks ADMIN permission → REJECT."""
    user_service = _user_service_returning(role=UserRole.TEACHER)

    user_uid = await require_websocket_admin(
        ws_authenticated, user_service, _graph_auth_returning()
    )

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_not_found_rejected(ws_authenticated):
    """Valid session pointing to a since-deleted user → REJECT (no crash, no allow)."""
    user_service = _user_service_returning(role=None)

    user_uid = await require_websocket_admin(
        ws_authenticated, user_service, _graph_auth_returning()
    )

    assert user_uid is None
    ws_authenticated.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unauthenticated_rejected_without_db_call(ws_anonymous):
    """No session token → short-circuit close, never touch the graph or DB."""
    user_service = _user_service_returning(role=UserRole.ADMIN)
    graph_auth = _graph_auth_returning()

    user_uid = await require_websocket_admin(ws_anonymous, user_service, graph_auth)

    assert user_uid is None
    ws_anonymous.close.assert_awaited_once()
    graph_auth.validate_session_uid.assert_not_called()
    user_service.get_user.assert_not_called()
