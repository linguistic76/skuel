#!/usr/bin/env python3
"""
Test async Neo4j connection - minimal test case.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential


async def test_async_connection():
    """Test async Neo4j connection."""
    print("=" * 60)
    print("Async Neo4j Connection Test")
    print("=" * 60)
    print()

    # Get credentials
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    # Strip whitespace from credentials (in case there's trailing whitespace)
    if neo4j_password:
        neo4j_password = neo4j_password.strip()
    if neo4j_user:
        neo4j_user = neo4j_user.strip()
    if neo4j_uri:
        neo4j_uri = neo4j_uri.strip()

    # Convert neo4j:// to bolt://
    if neo4j_uri.startswith("neo4j://"):
        neo4j_uri = neo4j_uri.replace("neo4j://", "bolt://")

    print(f"URI:      {neo4j_uri}")
    print(f"Username: {neo4j_user}")
    print(f"Password: {'*' * len(neo4j_password) if neo4j_password else 'NOT SET'}")
    print(f"Password length: {len(neo4j_password) if neo4j_password else 0}")
    print(f"Password type: {type(neo4j_password)}")
    print(f"Username type: {type(neo4j_user)}")
    print()

    if not neo4j_password:
        print("❌ ERROR: Neo4j password not found")
        return False

    print("Creating async driver...")
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        print("Opening session...")
        async with driver.session() as session:
            print("Running query...")
            result = await session.run("RETURN 1 as num")
            record = await result.single()

            if record and record["num"] == 1:
                print("✅ SUCCESS! Async connection works!")
                return True
            else:
                print("❌ FAILED: Unexpected result")
                return False

    except Exception as e:
        print(f"❌ FAILED: {e!s}")
        print(f"Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        print("Closing driver...")
        await driver.close()
        print("Driver closed.")


if __name__ == "__main__":
    success = asyncio.run(test_async_connection())
    print()
    print("=" * 60)
    sys.exit(0 if success else 1)
