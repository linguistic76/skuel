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
    just the email otherwise) — teardown removes all of them by test uid/email.
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
                DETACH DELETE s, u
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


async def test_revocation_invalidates_live_session(neo4j_driver, auth_env):
    """Server-side revocation must flip a live token to invalid.

    This is the graph half of forced re-login on privilege change (roadmap
    item 4): UserService.update_role / deactivate_user call
    invalidate_all_user_sessions, and AuthContextMiddleware clears any cookie
    whose token no longer validates (middleware half pinned in
    tests/unit/adapters/test_auth_context.py).
    """
    auth, track = auth_env
    username, email = track(*_credentials("revoke"))
    user_uid = f"user_{username}"

    signup = await auth.sign_up(email=email, password=_PASSWORD, username=username)
    assert signup.is_ok, f"sign_up failed: {signup.error}"

    signin = await auth.sign_in(email=email, password=_PASSWORD)
    assert signin.is_ok, f"sign_in failed: {signin.error}"
    token = signin.value["session_token"]

    valid = await auth.validate_session_uid(token)
    assert valid.is_ok and valid.value == user_uid, "live session must validate before revocation"

    revoked = await auth.session_backend.invalidate_all_user_sessions(user_uid)
    assert revoked.is_ok, f"revocation failed: {revoked.error}"
    assert revoked.value == 1, "exactly the one live session should be revoked"

    after = await auth.validate_session_uid(token)
    assert after.is_ok, f"post-revocation validation errored: {after.error}"
    assert after.value is None, "revoked session must not validate"


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
