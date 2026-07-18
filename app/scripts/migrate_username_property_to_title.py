"""
Migrate: Legacy ``username`` Property -> ``title``
==================================================

One-shot migration companion to the ``get_user_by_username`` fix
(PR #301). The User model stores the username in ``title``
(``create_user``: ``uid=f"user_{username}", title=username``; the profile
DTO maps ``username=user.title``) — a separate ``username`` node property
was only ever written by retired creation paths. The backend lookup now
matches ``title`` exclusively, so any environment whose graph still
carries ``:User.username`` must move that value into ``title`` or those
accounts lose username login after deploy.

For each ``User`` node where ``username`` is set:

* ``SET u.title = u.username`` — the legacy property IS the username the
  account holder types, so it wins over whatever ``title`` held.
* ``REMOVE u.username`` — One Path Forward, no dual storage.

Email login and the ``uid`` are untouched.

Idempotent: re-running on a migrated (or fresh) database is a no-op.

Usage::

    uv run python scripts/migrate_username_property_to_title.py [--apply]

Without ``--apply`` the script audits only; pass the flag to actually
migrate.
"""

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.utils.logging import get_logger

load_dotenv(project_root / ".env")

logger = get_logger(__name__)

AUDIT_QUERY = """
MATCH (u:User) WHERE u.username IS NOT NULL
RETURN u.uid AS uid, u.title AS title, u.username AS username
"""

MIGRATE_QUERY = """
MATCH (u:User) WHERE u.username IS NOT NULL
SET u.title = u.username
REMOVE u.username
RETURN u.uid AS uid, u.title AS title
"""


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration (default: audit only)",
    )
    args = parser.parse_args()

    conn = Neo4jConnection()
    driver = conn.connect()
    try:
        async with driver.session() as session:
            result = await session.run(AUDIT_QUERY)
            rows = [r async for r in result]

        if not rows:
            print("✓ No User nodes carry a legacy `username` property — nothing to do")
            return 0

        print(f"Found {len(rows)} User node(s) with a legacy `username` property:")
        for r in rows:
            print(f"  {r['uid']}: title={r['title']!r} <- username={r['username']!r}")

        if not args.apply:
            print("\nAudit only — re-run with --apply to migrate")
            return 0

        async with driver.session() as session:
            result = await session.run(MIGRATE_QUERY)
            migrated = [r async for r in result]
        for r in migrated:
            print(f"✓ Migrated {r['uid']}: title={r['title']!r}, `username` property removed")
        print(f"✓ {len(migrated)} node(s) migrated")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
