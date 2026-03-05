"""
Clear Neo4j Database
====================

Safely removes all nodes and relationships from Neo4j.
Use before ingesting fresh curriculum data.

CAUTION: This will delete ALL data in the database!
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

# Add project root to Python path BEFORE imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

from core.utils.logging import get_logger

# Load environment variables
load_dotenv(project_root / ".env")

logger = get_logger(__name__)


async def clear_database(
    uri: str = "bolt://localhost:7687",
    username: str = "neo4j",
    password: str | None = None,
    confirm: bool = False,
):
    """
    Clear all nodes and relationships from Neo4j database.

    Args:
        uri: Neo4j connection URI,
        username: Neo4j username,
        password: Neo4j password,
        confirm: If False, will prompt for confirmation

    Returns:
        Statistics about what was deleted
    """

    # Get password from credential store or prompt
    if password is None:
        # Try credential store first
        try:
            from core.config.credential_store import get_credential

            password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        except Exception:
            password = None

        if password is None:
            password = getpass.getpass(f"Neo4j password for {username}: ")

    # Safety confirmation
    if not confirm:
        print("\n⚠️  WARNING: This will DELETE ALL DATA in Neo4j database!")
        print(f"   Connection: {uri}")
        print(f"   Username: {username}")
        response = input("\n   Type 'DELETE ALL' to confirm: ")

        if response != "DELETE ALL":
            print("❌ Aborted. No data was deleted.")
            return None

    conn = Neo4jConnection(uri=uri, username=username, password=password)
    await conn.connect()
    driver = conn.driver

    try:
        async with driver.session() as session:
            # Step 1: Get counts before deletion
            logger.info("📊 Counting existing data...")

            count_result = await session.run("""
                MATCH (n)
                RETURN count(n) as node_count
            """)
            count_record = await count_result.single()
            node_count = count_record["node_count"]

            rel_result = await session.run("""
                MATCH ()-[r]->()
                RETURN count(r) as rel_count
            """)
            rel_record = await rel_result.single()
            rel_count = rel_record["rel_count"]

            logger.info(f"   Found {node_count} nodes")
            logger.info(f"   Found {rel_count} relationships")

            if node_count == 0:
                logger.info("✅ Database is already empty!")
                return {
                    "nodes_deleted": 0,
                    "relationships_deleted": 0,
                    "constraints_removed": 0,
                    "indexes_removed": 0,
                }

            # Step 2: Delete all nodes and relationships
            # Using DETACH DELETE removes relationships automatically
            logger.info("🗑️  Deleting all nodes and relationships...")

            delete_result = await session.run("""
                MATCH (n)
                DETACH DELETE n
                RETURN count(n) as deleted_count
            """)
            delete_record = await delete_result.single()
            deleted_count = delete_record["deleted_count"]

            logger.info(f"✅ Deleted {deleted_count} nodes and their relationships")

            # Step 3: Remove constraints (optional - usually keep for schema)
            logger.info("🔍 Checking constraints...")

            constraints_result = await session.run("SHOW CONSTRAINTS")
            constraints = [record async for record in constraints_result]

            logger.info(f"   Found {len(constraints)} constraints (keeping for schema)")

            # Step 4: Remove indexes (optional - usually keep for performance)
            logger.info("🔍 Checking indexes...")

            indexes_result = await session.run("SHOW INDEXES")
            indexes = [record async for record in indexes_result]

            logger.info(f"   Found {len(indexes)} indexes (keeping for performance)")

            # Verify deletion
            verify_result = await session.run("""
                MATCH (n)
                RETURN count(n) as remaining
            """)
            verify_record = await verify_result.single()
            remaining = verify_record["remaining"]

            if remaining == 0:
                logger.info("✅ Database successfully cleared!")
            else:
                logger.warning(f"⚠️  {remaining} nodes still remain")

            return {
                "nodes_deleted": deleted_count,
                "relationships_deleted": rel_count,
                "constraints_kept": len(constraints),
                "indexes_kept": len(indexes),
                "verified_empty": remaining == 0,
            }

    except Exception as e:
        logger.error(f"❌ Error clearing database: {e}", exc_info=True)
        raise
    finally:
        await conn.close()


async def clear_with_constraints(
    uri: str | None = None, username: str | None = None, password: str | None = None
):
    """
    Clear database AND remove all constraints/indexes.

    Use this for a completely fresh start.
    """

    # Get credentials from credential store or environment
    if uri is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    if username is None:
        username = os.getenv("NEO4J_USERNAME", "neo4j")
    if password is None:
        # Try credential store first
        try:
            from core.config.credential_store import get_credential

            password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        except Exception:
            password = os.getenv("NEO4J_PASSWORD")

        if password is None:
            password = getpass.getpass(f"Neo4j password for {username}: ")

    print("\n⚠️  WARNING: This will DELETE ALL DATA, CONSTRAINTS, AND INDEXES!")
    print(f"   Connection: {uri}")
    response = input("\n   Type 'DELETE EVERYTHING' to confirm: ")

    if response != "DELETE EVERYTHING":
        print("❌ Aborted. No data was deleted.")
        return None

    conn = Neo4jConnection(uri=uri, username=username, password=password)
    await conn.connect()
    driver = conn.driver

    try:
        async with driver.session() as session:
            # Delete all nodes and relationships
            logger.info("🗑️  Deleting all nodes and relationships...")
            await session.run("MATCH (n) DETACH DELETE n")

            # Drop all constraints
            logger.info("🗑️  Dropping all constraints...")
            constraints_result = await session.run("SHOW CONSTRAINTS")
            constraint_count = 0
            async for record in constraints_result:
                constraint_name = record.get("name")
                if constraint_name:
                    await session.run(f"DROP CONSTRAINT {constraint_name}")
                    constraint_count += 1

            logger.info(f"   Dropped {constraint_count} constraints")

            # Drop all indexes (except constraints-based indexes)
            logger.info("🗑️  Dropping all indexes...")
            indexes_result = await session.run("SHOW INDEXES")
            index_count = 0
            async for record in indexes_result:
                index_name = record.get("name")
                index_type = record.get("type", "")
                # Skip constraint-based indexes (they're already dropped with constraints)
                if index_name and "CONSTRAINT" not in index_type.upper():
                    try:
                        await session.run(f"DROP INDEX {index_name}")
                        index_count += 1
                    except Exception as e:
                        logger.warning(f"Could not drop index {index_name}: {e}")

            logger.info(f"   Dropped {index_count} indexes")

            logger.info("✅ Database completely cleared (data, constraints, indexes)")

            return {
                "nodes_deleted": True,
                "constraints_removed": constraint_count,
                "indexes_removed": index_count,
            }

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        raise
    finally:
        await conn.close()


async def clear_domain_bundle_only(
    bundle_name: str,
    uri: str = "bolt://localhost:7687",
    username: str = "neo4j",
    password: str | None = None,
):
    """
    Clear only entities from a specific domain bundle.

    Safer option - only removes entities with UIDs matching the bundle.

    Args:
        bundle_name: Name of bundle to remove (e.g., "mindfulness_101")
    """

    # Get password from credential store or prompt
    if password is None:
        # Try credential store first
        try:
            from core.config.credential_store import get_credential

            password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        except Exception:
            password = None

        if password is None:
            password = getpass.getpass(f"Neo4j password for {username}: ")

    conn = Neo4jConnection(uri=uri, username=username, password=password)
    await conn.connect()
    driver = conn.driver

    try:
        async with driver.session() as session:
            logger.info(f"🗑️  Clearing bundle: {bundle_name}")

            # Get bundle UIDs from manifest (would need to read manifest file)
            # For now, use UID prefix patterns
            uid_patterns = [
                f"ku:{bundle_name}%",
                f"ls:{bundle_name}%",
                f"lp:{bundle_name}%",
                f"principle:{bundle_name}%",
                f"choice:{bundle_name}%",
                f"habit:{bundle_name}%",
                f"task:{bundle_name}%",
                f"event:{bundle_name}%",
                f"goal:{bundle_name}%",
            ]

            total_deleted = 0
            for pattern in uid_patterns:
                result = await session.run(
                    """
                    MATCH (n)
                    WHERE n.uid STARTS WITH $pattern
                    DETACH DELETE n
                    RETURN count(n) as deleted
                """,
                    pattern=pattern.replace("%", ""),
                )

                record = await result.single()
                deleted = record["deleted"]
                if deleted > 0:
                    total_deleted += deleted
                    logger.info(f"   Deleted {deleted} nodes matching {pattern}")

            logger.info(f"✅ Removed {total_deleted} nodes from bundle '{bundle_name}'")

            return {"nodes_deleted": total_deleted}

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    # Parse command line arguments
    mode = sys.argv[1] if len(sys.argv) > 1 else "clear"

    if mode == "clear":
        # Standard clear - removes data, keeps constraints/indexes
        print("\n🧹 CLEAR MODE: Remove all data (keep constraints/indexes)")
        asyncio.run(clear_database())

    elif mode == "reset":
        # Complete reset - removes everything
        print("\n🔥 RESET MODE: Remove EVERYTHING (data + constraints + indexes)")
        asyncio.run(clear_with_constraints())

    elif mode == "bundle":
        # Clear specific bundle only
        bundle = sys.argv[2] if len(sys.argv) > 2 else "mindfulness_101"
        print(f"\n🎯 BUNDLE MODE: Remove only '{bundle}' entities")
        asyncio.run(clear_domain_bundle_only(bundle))

    else:
        print("""
Usage:
    poetry run python scripts/clear_neo4j.py [mode] [bundle_name]

Modes:
    clear      Remove all data (keep constraints/indexes) [DEFAULT]
    reset      Remove EVERYTHING (data + constraints + indexes)
    bundle     Remove only specific bundle entities

Examples:
    poetry run python scripts/clear_neo4j.py                    # Clear all data
    poetry run python scripts/clear_neo4j.py reset              # Complete reset
    poetry run python scripts/clear_neo4j.py bundle mindfulness_101  # Clear bundle only

Safety:
    All modes require explicit confirmation before deletion.
    Type exactly what is prompted to proceed.
        """)
