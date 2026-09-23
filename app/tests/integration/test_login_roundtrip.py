"""
Integration tests for the REAL auth round-trip (testcontainer Neo4j).

Promotes the live-only login check to a repeatable test. The mock-only suite
(tests/integration/routes/test_auth_routes.py) exercises route wiring but can
never catch graph-side regressions — Arc F's F8 (role stored as 'MEMBER'
uppercase broke every raw-Cypher ``u.role = 'admin'`` predicate) is exactly
the bug class this file pins.

Wiring mirrors services_bootstrap/compose.py: GraphAuthService composed from
the real UserBackend + SessionBackend against the testcontainer driver
(email_service stays None, as in local dev).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.session_backend import SessionBackend
from adapters.persistence.neo4j.user_backend import UserBackend
from core.auth.graph_auth import GraphAuthService

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Unique per run so repeated local runs never collide with leftover state.
_RUN_ID = uuid.uuid4().hex[:8]
_PASSWORD = "roundtrip-Correct-1234"


def _credentials(tag: str) -> tuple[str, str]:
    """Unique (username, email) pair for one test."""
    username = f"rt_{tag}_{_RUN_ID}"
    return username, f"{username}@example.com"


@pytest_asyncio.fixture(loop_scope="session")
async def auth_env(neo4j_driver):
    """Real GraphAuthService + a tracker that guarantees teardown.

    sign_in creates (:Session) nodes (via HAS_SESSION) and (:AuthEvent) audit
    nodes (linked HAD_AUTH_EVENT when a user_uid is known, standalone with
    just the email otherwise); the reset flows create (:PasswordResetToken)
    nodes (via HAS_RESET_TOKEN) — teardown removes all of them by test uid/email.
    """
    auth = GraphAuthService(
        user_backend=UserBackend(neo4j_driver),
        session_backend=SessionBackend(neo4j_driver),
    )
    created: list[tuple[str, str]] = []  # (user_uid, email)

    def track(username: str, email: str) -> tuple[str, str]:
        created.append((f"user_{username}", email))
        return username, email

    yield auth, track

    async with neo4j_driver.session() as session:
        for user_uid, email in created:
            # Sessions hang off the user; AuthEvents may be standalone
            # (failed login before the user was resolved) — sweep both.
            await session.run(
                """
                OPTIONAL MATCH (u:User {uid: $uid})
                OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
                OPTIONAL MATCH (u)-[:HAS_RESET_TOKEN]->(t:PasswordResetToken)
                DETACH DELETE s, t, u
                """,
                uid=user_uid,
            )
            await session.run(
                "MATCH (s:Session {user_uid: $uid}) DETACH DELETE s",
                uid=user_uid,
            )
            await session.run(
                """
                MATCH (e:AuthEvent)
                WHERE e.user_uid = $uid OR e.email = $email
                DETACH DELETE e
                """,
                uid=user_uid,
                email=email,
            )


async def _count_sessions(neo4j_driver, user_uid: str) -> int:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $uid})-[:HAS_SESSION]->(s:Session) RETURN count(s) AS c",
            uid=user_uid,
        )
        record = await result.single()
        return int(record["c"]) if record else 0


async def test_signup_then_signin_email_roundtrip(neo4j_driver, auth_env):
    """sign_up → sign_in by email returns a session token AND lands a Session node."""
    auth, track = auth_env
    username, email = track(*_credentials("email"))

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"
    assert signup.value["user_uid"] == f"user_{username}"
    assert signup.value["email"] == email

    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"

    data = signin.value
    assert data["session_token"], "sign_in must return a session token"
    assert data["user_uid"] == f"user_{username}"
    assert data["user"] is not None and data["user"].email == email

    # The session must actually exist in the graph — a token with no
    # (:Session) node is the graph-side regression class this suite pins.
    assert await _count_sessions(neo4j_driver, f"user_{username}") == 1


async def test_signin_via_username_lookup(neo4j_driver, auth_env):
    """Pin the username login path: login_submit resolves username→email via
    user_service.get_user_by_username (adapters/inbound/auth_ui.py) and then
    signs in with the resolved email."""
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
    from core.services.user_service import UserService

    auth, track = auth_env
    username, email = track(*_credentials("uname"))

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    # Same composition as the conftest user_service fixture / bootstrap:
    # UserService delegates identity lookups to UserBackend.
    user_service = UserService(
        user_repo=UserBackend(neo4j_driver),
        query_executor=UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)),
    )

    lookup = await user_service.get_user_by_username(username)
    assert lookup.is_ok, f"get_user_by_username failed: {lookup.error}"
    assert lookup.value is not None, "username lookup must find the user sign_up created"
    assert lookup.value.email == email

    signin = await auth.sign_in(email=lookup.value.email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in via resolved email failed: {signin.error}"
    assert signin.value["user_uid"] == f"user_{username}"


async def test_wrong_password_rejected_and_no_session(neo4j_driver, auth_env):
    """Wrong password → error Result and NO Session node created."""
    auth, track = auth_env
    username, email = track(*_credentials("wrongpw"))

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    signin = await auth.sign_in(email=email, password="definitely-not-the-Password-1")
    assert signin.is_error, "Wrong password must fail, not silently sign in"
    assert await _count_sessions(neo4j_driver, f"user_{username}") == 0, (
        "A failed login must not create a Session node"
    )


async def test_role_change_atomically_revokes_live_sessions(neo4j_driver, auth_env):
    """Pin the one-transaction role-change+revoke (Codex P1 on #798 round 3).

    Any two-step sequence has a hole: revoke-then-update lets the target
    sign in against the old user record inside the window (the fresh session
    dodges the completed sweep); update-then-revoke isn't retryable. The
    atomic backend op must persist the role (lowercase — the F8 regression
    class) AND kill the token in one commit.
    """
    from core.models.enums import UserRole

    auth, track = auth_env
    username, email = track(*_credentials("rolerev"))
    user_uid = f"user_{username}"

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    token = signin.value["session_token"]

    valid = await auth.validate_session_uid(token)
    assert valid.is_ok and valid.value == user_uid, "live session must validate before role change"

    atomic = await auth.session_backend.update_role_and_revoke_sessions(user_uid, UserRole.MEMBER)
    assert atomic.is_ok, f"atomic role-change+revoke failed: {atomic.error}"
    assert atomic.value == 1, "exactly the one live session should be revoked"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-role-change validation errored: {after.error}"
    assert after.value is None, "a pre-change session must not validate after the role change"

    async with neo4j_driver.session() as session:
        result = await session.run("MATCH (u:User {uid: $uid}) RETURN u.role AS role", uid=user_uid)
        record = await result.single()
    assert record is not None and record["role"] == "member", (
        "the role must persist as the lowercase enum value (F8)"
    )


async def test_deactivation_atomically_revokes_live_sessions(neo4j_driver, auth_env):
    """Pin the one-transaction deactivate+revoke (Codex P1 on #798 round 2).

    A two-step sequence (persist is_active=false, then revoke) could leave
    the account looking deactivated while its live sessions — cached
    user_is_active=true — kept validating. The atomic backend op must flip
    the flag AND kill the token in one commit.
    """
    auth, track = auth_env
    username, email = track(*_credentials("atomic"))
    user_uid = f"user_{username}"

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    token = signin.value["session_token"]

    valid = await auth.validate_session_uid(token)
    assert valid.is_ok and valid.value == user_uid, "live session must validate before deactivation"

    atomic = await auth.session_backend.deactivate_user_and_revoke_sessions(user_uid)
    assert atomic.is_ok, f"atomic deactivate+revoke failed: {atomic.error}"
    assert atomic.value == 1, "exactly the one live session should be revoked"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-deactivation validation errored: {after.error}"
    assert after.value is None, "a deactivated user's session must not validate"

    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (u:User {uid: $uid}) RETURN u.is_active AS active", uid=user_uid
        )
        record = await result.single()
    assert record is not None and record["active"] is False, "the flag flip must have committed"


async def test_deactivated_user_cannot_mint_session(neo4j_driver, auth_env):
    """Pin create_session's atomic active-user guard (Codex P1 on #798).

    sign_in checks ``user.is_active`` early, then spends ~100ms hashing the
    password — a deactivation landing in that window must not mint a live
    session (its cached ``user_is_active`` would be stale-True and
    validate_session_uid trusts it). The direct backend call below bypasses
    sign_in's early check, exactly like a sign-in that loaded the user before
    the deactivation committed.
    """
    from core.models.auth.session import create_session

    auth, track = auth_env
    username, email = track(*_credentials("inactive"))
    user_uid = f"user_{username}"

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) SET u.is_active = false", uid=user_uid)

    stale_session = create_session(user_uid=user_uid, ip_address="test", user_agent="test")
    created = await auth.session_backend.create_session(stale_session)
    assert created.is_error, "Session creation must refuse a deactivated user"
    assert await _count_sessions(neo4j_driver, user_uid) == 0

    # The ordinary path fails too (early is_active check)
    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_error, "Deactivated accounts must not sign in"


async def test_soft_deleted_user_sessions_stop_validating(neo4j_driver, auth_env):
    """Pin the deletion kill switch (Codex P1 on #798 round 4).

    Soft delete flips is_active and PII-scrubs but keeps the graph — its
    sessions must die in the same commit, and validation must anchor on the
    LIVE User (not the session's cached user_is_active snapshot).
    """
    auth, track = auth_env
    username, email = track(*_credentials("softdel"))
    user_uid = f"user_{username}"

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"
    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    token = signin.value["session_token"]

    deleted = await UserBackend(neo4j_driver).delete_user(user_uid)
    assert deleted.is_ok and deleted.value is True, f"soft delete failed: {deleted.error}"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-delete validation errored: {after.error}"
    assert after.value is None, "a soft-deleted user's session must not validate"


async def test_hard_deleted_user_sessions_are_erased(neo4j_driver, auth_env):
    """Hard delete (GDPR erasure) must take the Session nodes with it.

    DETACH DELETE on the User alone would orphan sessions still carrying the
    erased uid; validation anchored on the User already refuses them (no node,
    no HAS_SESSION edge), and the cascade removes the litter itself.
    """
    auth, track = auth_env
    username, email = track(*_credentials("harddel"))
    user_uid = f"user_{username}"

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"
    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    token = signin.value["session_token"]

    erased = await UserBackend(neo4j_driver).hard_delete_user(user_uid)
    assert erased.is_ok and erased.value >= 1, f"hard delete failed: {erased.error}"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-erasure validation errored: {after.error}"
    assert after.value is None, "an erased user's session must not validate"

    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (s:Session {user_uid: $uid}) RETURN count(s) AS c", uid=user_uid
        )
        record = await result.single()
    assert record is not None and record["c"] == 0, "erasure must not orphan Session nodes"


async def test_role_stored_lowercase_on_signup(neo4j_driver, auth_env):
    """Pin F8: the persisted role property is lowercase.

    Arc F's F8: a role stored as 'MEMBER' (uppercase) broke every raw-Cypher
    role predicate (e.g. get_admin_uid's ``admin.role = 'admin'``). sign_up
    must persist the UserRole StrEnum value — lowercase 'registered'.
    """
    auth, track = auth_env
    username, email = track(*_credentials("role"))

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (u:User {uid: $uid}) RETURN u.role AS role",
            uid=f"user_{username}",
        )
        record = await result.single()

    assert record is not None
    role = record["role"]
    assert role is not None, "sign_up must persist a role property"
    assert role == role.lower(), f"role must be stored lowercase (F8), got {role!r}"
    assert role == "registered", f"new users default to REGISTERED, got {role!r}"


# ============================================================================
# SIGN-OUT, SESSION VALIDATION, PASSWORD CHANGE AND RESET
# ============================================================================

_NEW_PASSWORD = "roundtrip-Rotated-5678"


async def _signed_up_and_in(auth, track, tag: str) -> tuple[str, str, str]:
    """sign_up + sign_in a fresh user; returns (user_uid, email, session_token)."""
    username, email = track(*_credentials(tag))
    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"
    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    return f"user_{username}", email, signin.value["session_token"]


async def _count_auth_events(neo4j_driver, user_uid: str, event_type: str) -> int:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:User {uid: $uid})-[:HAD_AUTH_EVENT]->(e:AuthEvent {event_type: $type})
            RETURN count(e) AS c
            """,
            uid=user_uid,
            type=event_type,
        )
        record = await result.single()
        return int(record["c"]) if record else 0


async def test_sign_out_kills_token_and_logs_logout(neo4j_driver, auth_env):
    """sign_out must make the token stop validating and leave a LOGOUT audit event."""
    from core.models.auth.auth_event import AuthEventType

    auth, track = auth_env
    user_uid, _email, token = await _signed_up_and_in(auth, track, "signout")

    out = await auth.sign_out(token)
    assert out.is_ok and out.value is True, f"sign_out failed: {out.error}"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-sign-out validation errored: {after.error}"
    assert after.value is None, "a signed-out token must not validate"
    assert await _count_auth_events(neo4j_driver, user_uid, AuthEventType.LOGOUT.value) == 1


async def test_sign_out_only_kills_its_own_session(neo4j_driver, auth_env):
    """Signing out on one device must leave the user's other sessions alive."""
    auth, track = auth_env
    user_uid, email, token_a = await _signed_up_and_in(auth, track, "signout2")
    signin_b = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin_b.is_ok, f"second sign_in failed: {signin_b.error}"
    token_b = signin_b.value["session_token"]

    out = await auth.sign_out(token_a)
    assert out.is_ok, f"sign_out failed: {out.error}"

    still = await auth.validate_session_uid(token_b)
    assert still.is_ok and still.value == user_uid, "the other session must survive"


async def test_validate_session_returns_full_user(neo4j_driver, auth_env):
    """validate_session resolves a live token to its User, and an unknown token to None."""
    auth, track = auth_env
    user_uid, email, token = await _signed_up_and_in(auth, track, "validate")

    valid = await auth.validate_session(token)
    assert valid.is_ok, f"validate_session failed: {valid.error}"
    assert valid.value is not None and valid.value.uid == user_uid
    assert valid.value.email == email

    unknown = await auth.validate_session(f"no-such-token-{_RUN_ID}")
    assert unknown.is_ok, f"unknown-token validation errored: {unknown.error}"
    assert unknown.value is None, "an unknown token must resolve to no user"


async def test_change_password_rotates_credentials_and_revokes_sessions(neo4j_driver, auth_env):
    """change_password: new password works, old one doesn't, live sessions die, event logged."""
    from core.models.auth.auth_event import AuthEventType

    auth, track = auth_env
    user_uid, email, token = await _signed_up_and_in(auth, track, "chpw")

    changed = await auth.change_password(user_uid, _PASSWORD, _NEW_PASSWORD)
    assert changed.is_ok and changed.value is True, f"change_password failed: {changed.error}"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-change validation errored: {after.error}"
    assert after.value is None, "a pre-change session must not validate after a password change"

    old = await auth.sign_in(email=email, password=_PASSWORD)
    assert old.is_error, "the old password must stop working"
    new = await auth.sign_in(email=email, password=_NEW_PASSWORD)
    assert new.is_ok, f"the new password must work: {new.error}"
    assert (
        await _count_auth_events(neo4j_driver, user_uid, AuthEventType.PASSWORD_CHANGED.value) == 1
    )


async def test_change_password_wrong_current_password_changes_nothing(neo4j_driver, auth_env):
    """A wrong current password is refused and leaves the password and sessions intact."""
    auth, track = auth_env
    user_uid, email, token = await _signed_up_and_in(auth, track, "chpwbad")

    changed = await auth.change_password(user_uid, "not-the-Current-1234", _NEW_PASSWORD)
    assert changed.is_error, "a wrong current password must be refused"

    still = await auth.validate_session_uid(token)
    assert still.is_ok and still.value == user_uid, "a refused change must not revoke sessions"
    new = await auth.sign_in(email=email, password=_NEW_PASSWORD)
    assert new.is_error, "a refused change must not have set the new password"


async def _make_admin(neo4j_driver, user_uid: str) -> None:
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) SET u.role = 'admin'", uid=user_uid)


async def test_admin_reset_token_resets_password_once(neo4j_driver, auth_env):
    """Admin-issued reset token: sets the new password, revokes sessions, and is single-use."""
    from core.models.auth.auth_event import AuthEventType

    auth, track = auth_env
    admin_uid, _admin_email, _ = await _signed_up_and_in(auth, track, "admin")
    await _make_admin(neo4j_driver, admin_uid)
    user_uid, email, token = await _signed_up_and_in(auth, track, "resetee")

    issued = await auth.admin_generate_reset_token(user_uid, admin_uid)
    assert issued.is_ok, f"admin_generate_reset_token failed: {issued.error}"
    reset_token = issued.value

    reset = await auth.reset_password_with_token(reset_token, _NEW_PASSWORD)
    assert reset.is_ok and reset.value is True, f"reset_password_with_token failed: {reset.error}"

    after = await auth.validate_session_uid(token)
    assert after.is_ok and after.value is None, "a reset must revoke the user's live sessions"
    assert (await auth.sign_in(email=email, password=_PASSWORD)).is_error
    assert (await auth.sign_in(email=email, password=_NEW_PASSWORD)).is_ok

    reused = await auth.reset_password_with_token(reset_token, "roundtrip-Third-9999")
    assert reused.is_error, "a used reset token must be refused"
    assert (await auth.sign_in(email=email, password=_NEW_PASSWORD)).is_ok, (
        "a refused reuse must not change the password"
    )
    assert (
        await _count_auth_events(
            neo4j_driver, user_uid, AuthEventType.PASSWORD_RESET_COMPLETED.value
        )
        == 1
    )


async def test_non_admin_cannot_issue_reset_token(neo4j_driver, auth_env):
    """A non-admin requesting a reset token for someone else is refused and mints nothing."""
    auth, track = auth_env
    other_uid, _, _ = await _signed_up_and_in(auth, track, "notadmin")
    target_uid, _, _ = await _signed_up_and_in(auth, track, "target")

    issued = await auth.admin_generate_reset_token(target_uid, other_uid)
    assert issued.is_error, "a non-admin must not be able to issue reset tokens"

    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $uid})-[:HAS_RESET_TOKEN]->(t) RETURN count(t) AS c",
            uid=target_uid,
        )
        record = await result.single()
    assert record is not None and record["c"] == 0, "a refused request must not create a token"


async def _issue_reset_token(auth, user_uid: str, *, expiry_minutes: int = 15) -> str:
    from core.models.auth.password_reset_token import create_password_reset_token

    token = create_password_reset_token(user_uid, expiry_minutes=expiry_minutes)
    created = await auth.session_backend.create_reset_token(token)
    assert created.is_ok, f"create_reset_token failed: {created.error}"
    return token.token


async def test_concurrent_resets_with_one_token_exactly_one_wins(neo4j_driver, auth_env):
    """Two simultaneous redemptions of one token: exactly one sets its password."""
    from core.models.auth.auth_event import AuthEventType

    auth, track = auth_env
    user_uid, email, _ = await _signed_up_and_in(auth, track, "racereset")
    reset_token = await _issue_reset_token(auth, user_uid)
    passwords = ("roundtrip-RaceA-1111", "roundtrip-RaceB-2222")

    results = await asyncio.gather(
        *(auth.reset_password_with_token(reset_token, pw) for pw in passwords)
    )

    winners = [pw for pw, r in zip(passwords, results, strict=True) if r.is_ok]
    assert len(winners) == 1, f"exactly one redemption may win, got {results}"
    (loser,) = set(passwords) - set(winners)
    assert (await auth.sign_in(email=email, password=winners[0])).is_ok
    assert (await auth.sign_in(email=email, password=loser)).is_error
    assert (
        await _count_auth_events(
            neo4j_driver, user_uid, AuthEventType.PASSWORD_RESET_COMPLETED.value
        )
        == 1
    )


async def test_concurrent_backend_claims_are_decided_by_the_write(neo4j_driver, auth_env):
    """Many claims racing on one token, hashes precomputed so they truly overlap.

    The service-level race above hashes with bcrypt on the event loop, which
    staggers the statements; this drives the claim statement itself. Without
    the write-lock taken before the read, concurrent statements all see
    ``is_used = false`` and all "claim".
    """
    from core.auth.password import hash_password

    auth, track = auth_env
    user_uid, _email, _ = await _signed_up_and_in(auth, track, "raceclaim")
    new_hash = hash_password("roundtrip-Claimed-3333")

    for _trial in range(5):
        reset_token = await _issue_reset_token(auth, user_uid)
        claims = await asyncio.gather(
            *(
                auth.session_backend.reset_password_and_revoke_sessions(reset_token, new_hash)
                for _ in range(6)
            )
        )
        assert all(c.is_ok for c in claims), claims
        assert sum(1 for c in claims if c.value is not None and c.value.claimed) == 1


async def test_expired_reset_token_is_refused_by_the_write(neo4j_driver, auth_env):
    """Expiry is checked in the claiming statement: nothing changes, sessions live."""
    auth, track = auth_env
    user_uid, email, token = await _signed_up_and_in(auth, track, "expired")
    reset_token = await _issue_reset_token(auth, user_uid, expiry_minutes=-1)

    reset = await auth.reset_password_with_token(reset_token, _NEW_PASSWORD)

    assert reset.is_error, "an expired token must be refused"
    assert (await auth.sign_in(email=email, password=_PASSWORD)).is_ok
    still = await auth.validate_session_uid(token)
    assert still.is_ok and still.value == user_uid, "a refused reset must not revoke sessions"


async def test_change_password_refused_when_hash_changed_underneath(neo4j_driver, auth_env):
    """A change verified against a stale hash must not overwrite a newer password.

    Models change_password reading the user, then a reset committing before
    its write: the compare-and-set sees a different hash and writes nothing.
    """
    from core.auth.password import hash_password

    auth, track = auth_env
    user_uid, email, _ = await _signed_up_and_in(auth, track, "casswap")
    stale = await auth.user_backend.get_user_by_uid(user_uid)
    assert stale.is_ok and stale.value is not None

    reset = await auth.reset_password_with_token(
        await _issue_reset_token(auth, user_uid), _NEW_PASSWORD
    )
    assert reset.is_ok, f"reset failed: {reset.error}"

    swap = await auth.session_backend.change_password_and_revoke_sessions(
        user_uid, stale.value.password_hash, hash_password("roundtrip-Stale-4444")
    )

    assert swap.is_ok and swap.value is None, "a stale compare must write nothing"
    assert (await auth.sign_in(email=email, password=_NEW_PASSWORD)).is_ok
