"""
Migration: Add Role Field to User Nodes
========================================

Adds the 'role' field to all existing User nodes in Neo4j.

Strategy:
- Existing users are grandfathered as MEMBER (paid subscriber)
- New users will default to REGISTERED (free trial) via application code

This is a one-time migration that should be run before deploying
the user roles feature.

Usage:
    poetry run python scripts/migrations/add_user_role.py

Options:
    --dry-run    Show what would be done without making changes
    --verify     Verify all users have role field after migration

Version: 1.0.0
Date: 2025-12-06
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from neo4j import AsyncGraphDatabase


async def get_driver():
    """Get Neo4j driver from environment, using SKUEL's credential store."""
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")

    # Get password from credential store (same as unified_config.py)
    try:
        from core.config.credential_store import get_credential
        password = get_credential("NEO4J_PASSWORD", fallback_to_env=True) or ""
    except Exception:
        password = os.getenv("NEO4J_PASSWORD", "password")

    return AsyncGraphDatabase.driver(uri, auth=(user, password))


async def count_users_without_role(driver) -> int:
    """Count users that don't have a role field."""
    query = """
    MATCH (u:User)
    WHERE u.role IS NULL
    RETURN count(u) as count
    """

    async with driver.session() as session:
        result = await session.run(query)
        record = await result.single()
        return record["count"] if record else 0


async def count_users_with_role(driver) -> dict:
    """Count users by role."""
    query = """
    MATCH (u:User)
    WHERE u.role IS NOT NULL
    RETURN u.role as role, count(u) as count
    ORDER BY count DESC
    """

    async with driver.session() as session:
        result = await session.run(query)
        records = await result.data()
        return {r["role"]: r["count"] for r in records}


async def migrate(driver, dry_run: bool = False) -> int:
    """
    Add role field to all existing users.

    Sets existing users to 'member' (grandfathered as paid).

    Args:
        driver: Neo4j async driver
        dry_run: If True, don't actually make changes

    Returns:
        Number of users updated
    """
    # Check how many users need updating
    users_without_role = await count_users_without_role(driver)

    if users_without_role == 0:
        print("✅ All users already have role field - nothing to migrate")
        return 0

    print(f"📋 Found {users_without_role} users without role field")

    if dry_run:
        print(f"🔍 DRY RUN: Would update {users_without_role} users to 'member' role")
        return users_without_role

    # Perform migration
    query = """
    MATCH (u:User)
    WHERE u.role IS NULL
    SET u.role = 'member'
    RETURN count(u) as updated_count
    """

    async with driver.session() as session:
        result = await session.run(query)
        record = await result.single()
        updated_count = record["updated_count"] if record else 0

    print(f"✅ Updated {updated_count} users to 'member' role")
    return updated_count


async def verify(driver) -> bool:
    """
    Verify all users have role field.

    Returns:
        True if all users have role, False otherwise
    """
    users_without_role = await count_users_without_role(driver)

    if users_without_role > 0:
        print(f"❌ VERIFICATION FAILED: {users_without_role} users still missing role field!")
        return False

    # Show role distribution
    role_counts = await count_users_with_role(driver)
    print("✅ Verification passed - all users have role field")
    print("\n📊 Role distribution:")
    for role, count in role_counts.items():
        print(f"   - {role}: {count}")

    return True


async def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add role field to User nodes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--verify", action="store_true", help="Verify migration results")
    args = parser.parse_args()

    print("=" * 60)
    print("SKUEL User Role Migration")
    print("=" * 60)

    driver = await get_driver()

    try:
        if args.verify:
            print("\n🔍 Verifying role field...")
            success = await verify(driver)
            sys.exit(0 if success else 1)

        print("\n🚀 Running migration...")
        await migrate(driver, dry_run=args.dry_run)

        if not args.dry_run:
            print("\n🔍 Verifying migration...")
            await verify(driver)

        print("\n✅ Migration complete!")

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
