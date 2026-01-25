#!/usr/bin/env python3
"""
Compare sync vs async Neo4j drivers with identical credentials.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from neo4j import AsyncGraphDatabase, GraphDatabase

from core.config.credential_store import get_credential


def test_sync_connection(uri, username, password):
    """Test sync Neo4j connection."""
    print("=" * 60)
    print("SYNC Driver Test")
    print("=" * 60)

    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))

        with driver.session() as session:
            result = session.run("RETURN 1 as num")
            record = result.single()

            if record and record["num"] == 1:
                print("✅ SYNC: SUCCESS!")
                driver.close()
                return True
            else:
                print("❌ SYNC: FAILED - Unexpected result")
                driver.close()
                return False

    except Exception as e:
        print(f"❌ SYNC: FAILED - {e!s}")
        return False


async def test_async_connection(uri, username, password):
    """Test async Neo4j connection."""
    print()
    print("=" * 60)
    print("ASYNC Driver Test")
    print("=" * 60)

    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

        async with driver.session() as session:
            result = await session.run("RETURN 1 as num")
            record = await result.single()

            if record and record["num"] == 1:
                print("✅ ASYNC: SUCCESS!")
                await driver.close()
                return True
            else:
                print("❌ ASYNC: FAILED - Unexpected result")
                await driver.close()
                return False

    except Exception as e:
        print(f"❌ ASYNC: FAILED - {e!s}")
        return False


async def main():
    """Run both tests with identical credentials."""
    # Get credentials
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    # Strip whitespace
    neo4j_uri = neo4j_uri.strip()
    neo4j_username = neo4j_username.strip()
    neo4j_password = neo4j_password.strip() if neo4j_password else None

    # Convert to bolt://
    if neo4j_uri.startswith("neo4j://"):
        neo4j_uri = neo4j_uri.replace("neo4j://", "bolt://")

    print()
    print("Testing with IDENTICAL credentials:")
    print(f"  URI:      {neo4j_uri}")
    print(f"  Username: {neo4j_username}")
    print(f"  Password: {'*' * len(neo4j_password) if neo4j_password else 'NOT SET'}")
    print(f"  Password length: {len(neo4j_password) if neo4j_password else 0}")
    print()

    if not neo4j_password:
        print("❌ ERROR: No password found")
        return

    # Test sync driver
    sync_success = test_sync_connection(neo4j_uri, neo4j_username, neo4j_password)

    # Test async driver
    async_success = await test_async_connection(neo4j_uri, neo4j_username, neo4j_password)

    print()
    print("=" * 60)
    print("RESULTS:")
    print(f"  Sync:  {'✅ SUCCESS' if sync_success else '❌ FAILED'}")
    print(f"  Async: {'✅ SUCCESS' if async_success else '❌ FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
