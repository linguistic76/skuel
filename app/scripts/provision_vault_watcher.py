#!/usr/bin/env python3
"""
Provision the vault_watcher service account for scripts/vault_watch.py.

Creates a dedicated ADMIN account (`vault_watcher`) through the normal
GraphAuthService sign-up path (correct bcrypt hashing), elevates it to admin,
and stores a generated random password in the active credential backend under
SKUEL_VAULT_WATCH_PASSWORD. The password is never displayed.

This grants admin privileges in the live graph — run it yourself, deliberately:

    uv run python scripts/provision_vault_watcher.py

Then set the username (e.g. in .env):

    SKUEL_VAULT_WATCH_USERNAME=vault_watcher

Idempotent-ish: re-running rotates the password for the existing account.
"""

import asyncio
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE, override=False)

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection  # noqa: E402
from adapters.persistence.neo4j.session_backend import SessionBackend  # noqa: E402
from adapters.persistence.neo4j.user_backend import UserBackend  # noqa: E402
from core.auth.graph_auth import GraphAuthService  # noqa: E402
from core.config.credential_store import get_active_backend  # noqa: E402

USERNAME = "vault_watcher"
EMAIL = "vault-watcher@skuel.local"


async def main() -> int:
    conn = Neo4jConnection()
    driver = await conn.connect()
    try:
        user_backend = UserBackend(driver)
        auth = GraphAuthService(user_backend, SessionBackend(driver))
        password = secrets.token_urlsafe(24)

        existing = await user_backend.get_user_by_username(USERNAME)
        if existing.is_ok and existing.value:
            # Rotate via the admin reset-token flow (the one path for setting
            # a password outside the user's own change_password).
            token_result = await auth.admin_generate_reset_token(
                existing.value.uid, admin_uid="provision_script"
            )
            if token_result.is_error:
                print(f"✗ Reset token failed: {token_result.expect_error().message}")
                return 1
            reset = await auth.reset_password_with_token(token_result.value, password)
            if reset.is_error:
                print(f"✗ Password rotation failed: {reset.expect_error().message}")
                return 1
            print(f"✓ Existing {USERNAME} account — password rotated")
        else:
            result = await auth.sign_up(
                email=EMAIL,
                password=password,
                username=USERNAME,
                display_name="Vault Watcher (service account)",
            )
            if result.is_error:
                print(f"✗ Sign-up failed: {result.expect_error().message}")
                return 1
            print(f"✓ Created {USERNAME} account")

        async with driver.session() as session:
            # Match by uid — create_user derives it as user_{username}, and uid
            # is the one identity that can't drift (the username lives in the
            # node's `title` property, not a `username` property).
            res = await session.run(
                "MATCH (u:User {uid: $uid}) SET u.role = 'admin' "
                "RETURN u.uid AS uid, u.role AS role",
                {"uid": f"user_{USERNAME}"},
            )
            record = await res.single()
            if record is None:
                print("✗ Role elevation failed: account not found after creation")
                return 1
            print(f"✓ {record['uid']} role={record['role']}")

        get_active_backend().set("SKUEL_VAULT_WATCH_PASSWORD", password)
        print("✓ Password stored in credential backend under SKUEL_VAULT_WATCH_PASSWORD")
        print(f"\nNext: set SKUEL_VAULT_WATCH_USERNAME={USERNAME} in .env, then:")
        print("  ./dev vault-watch --once")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
