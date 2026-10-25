"""No service admin account exists to be activated (ADR-091 S9).

Boot creates no ``user_system`` account, so the one way to turn a passwordless
service admin into a signed-in admin — an admin mints a reset token for it, the token
sets a password, the password signs in — has nothing to act on: the token door
answers it as it answers a uid that names nobody, and its email signs in to nothing.

The control runs the same three doors for a real user made at the user create door:
a token, a new password, and a sign-in that lands on ``/today``. Without it a refusal
would prove nothing — a broken reset door refuses every uid.

``user_vault_watcher`` has no test here: no code creates it, so only a graph's own
data can hold one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.rate_limit import reset_buckets_for_testing
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import _app, signed_in_client

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.outside_uid_grammar(
        "names the retired user_system account to show no door creates it", static_only=True
    ),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzsysacct"
ADMIN = seed_user_uid(f"{MARK}a")
REAL_USERNAME = f"{MARK}real"  # its uid is generated — cleanup finds it by username
REAL_EMAIL = f"{REAL_USERNAME}@example.com"
SYSTEM_UID = "user_system"
SYSTEM_EMAIL = "system@skuel.local"
NOBODY_UID = seed_user_uid(f"{MARK}nobody")
NEW_PASSWORD = "Sysacct-pass-123!"
RESET = "/api/admin/users/reset-password"


async def _count_users(driver: AsyncDriver, uid: str) -> int:
    async with driver.session() as session:
        result = await session.run("MATCH (u:User {uid: $uid}) RETURN count(u) AS n", uid=uid)
        record = await result.single()
    return int(record["n"]) if record else 0


async def _forget_auth_records(driver: AsyncDriver) -> None:
    """Remove what the doors below record about the test's accounts (events, tokens)."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE NOT n:User
              AND (n.user_uid CONTAINS $mark OR n.email CONTAINS $mark
                   OR n.email = $system_email OR n.user_uid = $system_uid)
            DETACH DELETE n
            """,
            mark=MARK,
            system_email=SYSTEM_EMAIL,
            system_uid=SYSTEM_UID,
        )


async def _set_admin(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = 'admin', u.is_active = true,
                u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=ADMIN,
        )


def _anonymous(app: Any) -> httpx.AsyncClient:  # boundary: fasthtml-app
    token = mint_token()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: token},
        headers={CSRF_HEADER_NAME: token},
        timeout=60,
        follow_redirects=False,
    )


async def _activate(
    admin: httpx.AsyncClient, anonymous: httpx.AsyncClient, uid: str, email: str
) -> tuple[int, int | None, int]:
    """Mint a reset token for ``uid`` as the admin, set a password with it, sign in.

    Returns the token door's status, the reset door's status (None when no token was
    minted) and the sign-in door's status — 303 is a signed-in redirect.
    """
    minted = await admin.post(RESET, params={"uid": uid})
    reset_status: int | None = None
    if minted.status_code == 200:
        reset = await anonymous.post(
            "/reset-password/submit",
            data={
                "token": minted.json()["reset_token"],
                "password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )
        reset_status = reset.status_code
    signed_in = await anonymous.post(
        "/login/submit", data={"username": email, "password": NEW_PASSWORD}
    )
    return minted.status_code, reset_status, signed_in.status_code


async def test_boot_creates_no_system_account(skuel_app: Any) -> None:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    services = skuel_app.state.services
    try:
        made = await services.user.create_user(
            username=REAL_USERNAME, email=REAL_EMAIL, display_name=REAL_USERNAME
        )
        assert made.is_ok, made
        # Control: the read sees a user the create door made.
        assert await _count_users(driver, made.value.uid) == 1
        assert await _count_users(driver, SYSTEM_UID) == 0
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (u:User) WHERE u.uid CONTAINS $mark OR u.title CONTAINS $mark "
                "DETACH DELETE u",
                mark=MARK,
            )


async def test_admin_cannot_activate_a_system_account(
    skuel_app: Any,  # boundary: fasthtml-app
) -> None:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    services = skuel_app.state.services
    reset_buckets_for_testing()
    await _forget_auth_records(driver)
    try:
        # The client's entry wipes every node carrying MARK, so the real user is made
        # inside it.
        async with signed_in_client(skuel_app, ADMIN, MARK) as admin:
            await _set_admin(driver)
            made = await services.user.create_user(
                username=REAL_USERNAME, email=REAL_EMAIL, display_name=REAL_USERNAME
            )
            assert made.is_ok, made
            real_uid = made.value.uid
            app, wiring = _app(skuel_app)
            await wiring
            async with _anonymous(app) as anonymous:
                # Control: the three doors activate a real user.
                assert await _activate(admin, anonymous, real_uid, REAL_EMAIL) == (200, 200, 303)

                system = await _activate(admin, anonymous, SYSTEM_UID, SYSTEM_EMAIL)
                nobody = await admin.post(RESET, params={"uid": NOBODY_UID})

        # The token door answers user_system as it answers a uid naming nobody, so
        # nothing is reset, and the email signs in to nothing.
        assert nobody.status_code == 404
        assert system == (nobody.status_code, None, 200)
        assert await _count_users(driver, SYSTEM_UID) == 0
    finally:
        await _forget_auth_records(driver)
        async with driver.session() as session:
            await session.run(
                "MATCH (u:User) WHERE u.uid CONTAINS $mark OR u.title CONTAINS $mark "
                "DETACH DELETE u",
                mark=MARK,
            )
