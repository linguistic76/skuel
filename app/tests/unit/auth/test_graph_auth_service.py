"""
Unit tests for GraphAuthService branch logic (mocked backends).

The graph-side guarantees — sessions revoked on password change/reset, reset
tokens single-use, sign-out kills the token — are pinned against a real graph
in tests/integration/test_login_roundtrip.py. This file covers what a live
graph makes awkward to reach: input validation that must stop before any
write, refusals that must not leak whether an account exists, and the
email-reset flow's always-ok contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from core.auth.graph_auth import GraphAuthService
from core.auth.password import hash_password
from core.models.auth.auth_event import AuthEventType
from core.models.auth.password_reset_token import PasswordResetClaim
from core.models.user import create_user
from core.utils.result_simplified import ErrorCategory, Errors, Result

_PASSWORD = "unit-Correct-1234"
_NEW_PASSWORD = "unit-Rotated-5678"

# bcrypt is deliberately slow — hash once for the module.
_PASSWORD_HASH = hash_password(_PASSWORD)


def _user(*, is_active: bool = True):
    return create_user(
        username="alice",
        email="alice@example.com",
        password_hash=_PASSWORD_HASH,
        is_active=is_active,
    )


def _service(email_service=None) -> tuple[GraphAuthService, AsyncMock, AsyncMock]:
    user_backend = AsyncMock()
    session_backend = AsyncMock()
    session_backend.is_ip_rate_limited.return_value = Result.ok(False)
    session_backend.is_account_locked.return_value = Result.ok(False)
    session_backend.log_auth_event.return_value = Result.ok(None)
    service = GraphAuthService(
        user_backend=user_backend,
        session_backend=session_backend,
        email_service=email_service,
        app_url="https://skuel.test/",
    )
    return service, user_backend, session_backend


def _echo_created(user):
    return Result.ok(user)


def _logged_events(session_backend: AsyncMock) -> list:
    return [c.args[0] for c in session_backend.log_auth_event.await_args_list]


# ============================================================================
# sign_up
# ============================================================================


@pytest.mark.parametrize(
    ("email", "password", "username", "field"),
    [
        ("not-an-email", _PASSWORD, "alice", "email"),
        ("", _PASSWORD, "alice", "email"),
        ("alice@example.com", "short", "alice", "password"),
        ("alice@example.com", _PASSWORD, "al", "username"),
    ],
)
async def test_sign_up_rejects_bad_input_before_any_lookup(email, password, username, field):
    service, user_backend, _ = _service()

    result = await service.sign_up(email=email, password=password, username=username)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    assert result.expect_error().details.get("field") == field
    user_backend.find_by.assert_not_awaited()
    user_backend.create_user.assert_not_awaited()


async def test_sign_up_refuses_duplicate_email():
    service, user_backend, _ = _service()
    user_backend.find_by.return_value = Result.ok([_user()])

    result = await service.sign_up(email="alice@example.com", password=_PASSWORD, username="alice2")

    assert result.is_error
    user_backend.create_user.assert_not_awaited()


async def test_sign_up_refuses_taken_username():
    service, user_backend, _ = _service()
    user_backend.find_by.return_value = Result.ok([])
    user_backend.get_user_by_username.return_value = Result.ok(_user())

    result = await service.sign_up(email="new@example.com", password=_PASSWORD, username="alice")

    assert result.is_error
    user_backend.create_user.assert_not_awaited()


async def test_sign_up_stores_a_hash_not_the_password():
    service, user_backend, _ = _service()
    user_backend.find_by.return_value = Result.ok([])
    user_backend.get_user_by_username.return_value = Result.ok(None)
    user_backend.create_user.side_effect = _echo_created

    result = await service.sign_up(email="new@example.com", password=_PASSWORD, username="newbie")

    assert result.is_ok
    stored = user_backend.create_user.await_args.args[0]
    assert stored.password_hash and stored.password_hash != _PASSWORD


# ============================================================================
# sign_in
# ============================================================================


async def test_locked_account_is_refused_without_extending_the_lockout():
    """A locked account must not log another LOGIN_FAILED — that would push a
    fresh timestamp into the rolling window and keep the account locked forever."""
    service, user_backend, session_backend = _service()
    session_backend.is_account_locked.return_value = Result.ok(True)

    result = await service.sign_in(email="alice@example.com", password=_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.BUSINESS
    session_backend.log_auth_event.assert_not_awaited()
    user_backend.find_by.assert_not_awaited()


async def test_unknown_email_and_wrong_password_are_indistinguishable():
    """Both refusals must carry the same message so login can't enumerate accounts."""
    service, user_backend, session_backend = _service()

    user_backend.find_by.return_value = Result.ok([])
    unknown = await service.sign_in(email="ghost@example.com", password=_PASSWORD)

    user_backend.find_by.return_value = Result.ok([_user()])
    wrong = await service.sign_in(email="alice@example.com", password="wrong-Password-99")

    assert unknown.is_error and wrong.is_error
    assert unknown.expect_error().message == wrong.expect_error().message
    reasons = [e.metadata.get("reason") for e in _logged_events(session_backend)]
    assert reasons == ["user_not_found", "wrong_password"]
    session_backend.create_session.assert_not_awaited()


async def test_deactivated_user_gets_no_session():
    service, user_backend, session_backend = _service()
    user_backend.find_by.return_value = Result.ok([_user(is_active=False)])

    result = await service.sign_in(email="alice@example.com", password=_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.BUSINESS
    session_backend.create_session.assert_not_awaited()


async def test_sign_in_fails_when_session_cannot_be_stored():
    """No token may be handed out for a session the graph didn't record."""
    service, user_backend, session_backend = _service()
    user_backend.find_by.return_value = Result.ok([_user()])
    session_backend.create_session.return_value = Result.fail(
        Errors.database(operation="create_session", message="down")
    )

    result = await service.sign_in(email="alice@example.com", password=_PASSWORD)

    assert result.is_error
    success_events = [
        e for e in _logged_events(session_backend) if e.event_type == AuthEventType.LOGIN_SUCCESS
    ]
    assert success_events == []


async def test_sign_in_database_outage_is_a_database_error():
    service, _, session_backend = _service()
    session_backend.is_ip_rate_limited.side_effect = ServiceUnavailable("down")

    result = await service.sign_in(email="alice@example.com", password=_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE


# ============================================================================
# sign_out / validate_session
# ============================================================================


async def test_sign_out_of_unknown_token_still_invalidates_and_logs_nothing():
    service, _, session_backend = _service()
    session_backend.get_session_by_token.return_value = Result.ok(None)
    session_backend.invalidate_session.return_value = Result.ok(False)

    result = await service.sign_out("stale-token")

    assert result.is_ok
    session_backend.invalidate_session.assert_awaited_once_with("stale-token")
    session_backend.log_auth_event.assert_not_awaited()


async def test_sign_out_reports_failure_when_invalidation_fails():
    """If the session can't be invalidated, the caller must not be told it was."""
    service, _, session_backend = _service()
    session_backend.get_session_by_token.return_value = Result.ok(None)
    session_backend.invalidate_session.return_value = Result.fail(
        Errors.database(operation="invalidate_session", message="down")
    )

    result = await service.sign_out("live-token")

    assert result.is_error


async def test_validate_session_skips_user_fetch_for_invalid_token():
    service, user_backend, session_backend = _service()
    session_backend.validate_session_token.return_value = Result.ok(None)

    result = await service.validate_session("expired-token")

    assert result.is_ok and result.value is None
    user_backend.get_user_by_uid.assert_not_awaited()


# ============================================================================
# change_password
# ============================================================================


async def test_change_password_rejects_weak_password_before_lookup():
    service, user_backend, _ = _service()

    result = await service.change_password("user_alice", _PASSWORD, "short")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    user_backend.get_user_by_uid.assert_not_awaited()


async def test_change_password_for_unknown_user_is_not_found():
    service, user_backend, session_backend = _service()
    user_backend.get_user_by_uid.return_value = Result.ok(None)

    result = await service.change_password("user_ghost", _PASSWORD, _NEW_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    session_backend.change_password_and_revoke_sessions.assert_not_awaited()


async def test_change_password_swaps_against_the_verified_hash():
    """The write is guarded on the hash the old password was checked against."""
    service, user_backend, session_backend = _service()
    user_backend.get_user_by_uid.return_value = Result.ok(_user())
    session_backend.change_password_and_revoke_sessions.return_value = Result.ok(2)

    result = await service.change_password("user_alice", _PASSWORD, _NEW_PASSWORD)

    assert result.is_ok and result.value is True
    uid, expected_hash, new_hash = (
        session_backend.change_password_and_revoke_sessions.await_args.args
    )
    assert uid == "user_alice"
    assert expected_hash == _PASSWORD_HASH
    assert new_hash != _PASSWORD_HASH and _NEW_PASSWORD not in new_hash
    assert [e.event_type for e in _logged_events(session_backend)] == [
        AuthEventType.PASSWORD_CHANGED
    ]


async def test_change_password_reports_failure_when_swap_and_revoke_fails():
    """A failed hash-swap+revocation must not be reported as a changed password."""
    service, user_backend, session_backend = _service()
    user_backend.get_user_by_uid.return_value = Result.ok(_user())
    session_backend.change_password_and_revoke_sessions.return_value = Result.fail(
        Errors.database(operation="change_password_and_revoke_sessions", message="down")
    )

    result = await service.change_password("user_alice", _PASSWORD, _NEW_PASSWORD)

    assert result.is_error
    assert _logged_events(session_backend) == []


async def test_change_password_refused_when_hash_changed_underneath():
    """A reset (or another change) landing after the old-password check wins; this one fails."""
    service, user_backend, session_backend = _service()
    user_backend.get_user_by_uid.return_value = Result.ok(_user())
    session_backend.change_password_and_revoke_sessions.return_value = Result.ok(None)

    result = await service.change_password("user_alice", _PASSWORD, _NEW_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.BUSINESS
    assert _logged_events(session_backend) == []


# ============================================================================
# admin_generate_reset_token / reset_password_with_token
# ============================================================================


async def test_admin_reset_token_for_unknown_user_is_not_found():
    service, user_backend, session_backend = _service()
    user_backend.get_user_by_uid.return_value = Result.ok(None)

    result = await service.admin_generate_reset_token("user_ghost", "user_admin")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    session_backend.create_reset_token.assert_not_awaited()


async def test_reset_with_unknown_token_is_refused():
    service, _, session_backend = _service()
    session_backend.reset_password_and_revoke_sessions.return_value = Result.ok(None)

    result = await service.reset_password_with_token("bogus", _NEW_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    assert _logged_events(session_backend) == []


async def test_reset_with_unclaimable_token_is_refused():
    """A used/expired token comes back unclaimed — the backend wrote nothing, so no success."""
    service, _, session_backend = _service()
    session_backend.reset_password_and_revoke_sessions.return_value = Result.ok(
        PasswordResetClaim(
            claimed=False, user_uid="user_alice", email="alice@example.com", revoked_count=0
        )
    )

    result = await service.reset_password_with_token("spent-token", _NEW_PASSWORD)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
    assert _logged_events(session_backend) == []


async def test_reset_reports_failure_when_claim_and_revoke_fails():
    """A failed claim+revocation must not be reported as a completed reset."""
    service, _, session_backend = _service()
    session_backend.reset_password_and_revoke_sessions.return_value = Result.fail(
        Errors.database(operation="reset_password_and_revoke_sessions", message="down")
    )

    result = await service.reset_password_with_token("live-token", _NEW_PASSWORD)

    assert result.is_error
    assert _logged_events(session_backend) == []


async def test_reset_hashes_the_new_password_and_logs_completion():
    service, _, session_backend = _service()
    session_backend.reset_password_and_revoke_sessions.return_value = Result.ok(
        PasswordResetClaim(
            claimed=True, user_uid="user_alice", email="alice@example.com", revoked_count=1
        )
    )

    result = await service.reset_password_with_token("live-token", _NEW_PASSWORD)

    assert result.is_ok and result.value is True
    token_value, new_hash = session_backend.reset_password_and_revoke_sessions.await_args.args
    assert token_value == "live-token"
    assert _NEW_PASSWORD not in new_hash
    events = _logged_events(session_backend)
    assert [e.event_type for e in events] == [AuthEventType.PASSWORD_RESET_COMPLETED]
    assert events[0].user_uid == "user_alice"


async def test_reset_rejects_weak_password_before_consuming_token():
    service, _, session_backend = _service()

    result = await service.reset_password_with_token("any-token", "short")

    assert result.is_error
    session_backend.reset_password_and_revoke_sessions.assert_not_awaited()


# ============================================================================
# reset_password_email — always ok(True), so it can't reveal which emails exist
# ============================================================================


async def test_reset_email_without_email_service_is_ok_and_does_nothing():
    service, user_backend, _ = _service(email_service=None)

    result = await service.reset_password_email("alice@example.com")

    assert result.is_ok and result.value is True
    user_backend.get_user_by_email.assert_not_awaited()


async def test_reset_email_for_unknown_address_is_ok_and_sends_nothing():
    email_service = AsyncMock()
    service, user_backend, session_backend = _service(email_service=email_service)
    user_backend.get_user_by_email.return_value = Result.ok(None)

    result = await service.reset_password_email("ghost@example.com")

    assert result.is_ok and result.value is True
    session_backend.create_reset_token.assert_not_awaited()
    email_service.send_password_reset.assert_not_awaited()


async def test_reset_email_sends_link_carrying_the_stored_token():
    email_service = AsyncMock()
    email_service.send_password_reset.return_value = Result.ok(None)
    service, user_backend, session_backend = _service(email_service=email_service)
    user_backend.get_user_by_email.return_value = Result.ok(_user())
    session_backend.create_reset_token.return_value = Result.ok(None)

    result = await service.reset_password_email("alice@example.com")

    assert result.is_ok
    stored = session_backend.create_reset_token.await_args.args[0]
    assert stored.user_uid == "user_alice"
    assert stored.created_by_admin_uid is None
    sent = email_service.send_password_reset.await_args.kwargs
    assert sent["to_email"] == "alice@example.com"
    assert sent["reset_link"] == f"https://skuel.test/reset-password?token={stored.token}"


async def test_reset_email_does_not_send_when_token_cannot_be_stored():
    """A link to a token the graph never recorded would be a dead link."""
    email_service = AsyncMock()
    service, user_backend, session_backend = _service(email_service=email_service)
    user_backend.get_user_by_email.return_value = Result.ok(_user())
    session_backend.create_reset_token.return_value = Result.fail(
        Errors.database(operation="create_reset_token", message="down")
    )

    result = await service.reset_password_email("alice@example.com")

    assert result.is_ok and result.value is True
    email_service.send_password_reset.assert_not_awaited()


@pytest.mark.parametrize(
    "failure",
    ["lookup_error", "send_error", "database_outage"],
)
async def test_reset_email_failures_still_report_ok(failure):
    email_service = AsyncMock()
    email_service.send_password_reset.return_value = Result.ok(None)
    service, user_backend, session_backend = _service(email_service=email_service)
    user_backend.get_user_by_email.return_value = Result.ok(_user())
    session_backend.create_reset_token.return_value = Result.ok(None)

    if failure == "lookup_error":
        user_backend.get_user_by_email.return_value = Result.fail(
            Errors.database(operation="get_user_by_email", message="down")
        )
    elif failure == "send_error":
        email_service.send_password_reset.return_value = Result.fail(
            Errors.integration(service="resend", message="down")
        )
    else:
        user_backend.get_user_by_email.side_effect = ServiceUnavailable("down")

    result = await service.reset_password_email("alice@example.com")

    assert result.is_ok and result.value is True
