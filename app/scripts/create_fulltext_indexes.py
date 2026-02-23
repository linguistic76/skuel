#!/usr/bin/env python3
"""
Create Full-Text Indexes for Hybrid Search
===========================================

Creates Neo4j full-text indexes to support hybrid search combining:
- Vector similarity search (semantic)
- Full-text keyword search (lexical)

Indexes are created for all searchable entity types with appropriate fields.

Usage:
    poetry run python scripts/create_fulltext_indexes.py

Created: January 2026
See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

import asyncio
from typing import Any

from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.fulltext_indexes")


# Full-text index definitions
# Format: {label: {index_name, fields_to_index}}
FULLTEXT_INDEX_DEFINITIONS = {
    "Curriculum": {
        "index_name": "curriculum_fulltext_idx",
        "fields": ["title", "content", "tags"],
        "description": "Curriculum - title, content, and tags",
    },
    "Task": {
        "index_name": "task_fulltext_idx",
        "fields": ["title", "description"],
        "description": "Tasks - title and description",
    },
    "Goal": {
        "index_name": "goal_fulltext_idx",
        "fields": ["title", "description"],
        "description": "Goals - title and description",
    },
    "Habit": {
        "index_name": "habit_fulltext_idx",
        "fields": ["title", "description"],
        "description": "Habits - title and description",
    },
    "Event": {
        "index_name": "event_fulltext_idx",
        "fields": ["title", "description"],
        "description": "Events - title and description",
    },
    "Choice": {
        "index_name": "choice_fulltext_idx",
        "fields": ["title", "description"],
        "description": "Choices - title and description",
    },
    "Principle": {
        "index_name": "principle_fulltext_idx",
        "fields": ["title", "statement", "description"],
        "description": "Principles - title, statement, and description",
    },
    "Lpstep": {
        "index_name": "lpstep_fulltext_idx",
        "fields": ["title", "description"],
        "description": "Learning Path Steps - title and description",
    },
}


async def check_index_exists(driver: Any, index_name: str) -> bool:
    """
    Check if a full-text index exists.

    Args:
        driver: Neo4j driver instance
        index_name: Name of index to check

    Returns:
        True if index exists, False otherwise
    """
    query = "SHOW INDEXES YIELD name WHERE name = $index_name RETURN count(*) as count"

    try:
        result = await driver.execute_query(query, {"index_name": index_name})
        return result[0]["count"] > 0 if result else False
    except Exception as e:
        logger.error(f"Error checking index {index_name}: {e}")
        return False


async def create_fulltext_index(
    driver: Any, label: str, index_name: str, fields: list[str]
) -> bool:
    """
    Create a full-text index for a node label.

    Args:
        driver: Neo4j driver instance
        label: Node label (e.g., "Curriculum", "Task")
        index_name: Name for the index
        fields: List of fields to index (e.g., ["title", "content"])

    Returns:
        True if created successfully, False otherwise
    """
    # Build field list with proper syntax: n.field1, n.field2, ...
    field_list = ", ".join([f"n.{field}" for field in fields])

    query = f"""
    CREATE FULLTEXT INDEX {index_name} IF NOT EXISTS
    FOR (n:{label})
    ON EACH [{field_list}]
    """

    try:
        await driver.execute_query(query)
        logger.info(f"✅ Created full-text index: {index_name} on {label}({', '.join(fields)})")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create index {index_name}: {e}")
        return False


async def drop_fulltext_index(driver: Any, index_name: str) -> bool:
    """
    Drop a full-text index.

    Args:
        driver: Neo4j driver instance
        index_name: Name of index to drop

    Returns:
        True if dropped successfully, False otherwise
    """
    query = f"DROP INDEX {index_name} IF EXISTS"

    try:
        await driver.execute_query(query)
        logger.info(f"🗑️  Dropped index: {index_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to drop index {index_name}: {e}")
        return False


async def create_all_fulltext_indexes(driver: Any, recreate: bool = False) -> dict[str, bool]:
    """
    Create all full-text indexes for hybrid search.

    Args:
        driver: Neo4j driver instance
        recreate: If True, drop existing indexes before creating

    Returns:
        Dict mapping index_name -> success status
    """
    results = {}

    logger.info("=" * 70)
    logger.info("Creating Full-Text Indexes for Hybrid Search")
    logger.info("=" * 70)

    for label, config in FULLTEXT_INDEX_DEFINITIONS.items():
        index_name = config["index_name"]
        fields = config["fields"]
        description = config["description"]

        logger.info(f"\n{label}: {description}")

        # Check if index exists
        exists = await check_index_exists(driver, index_name)

        if exists:
            if recreate:
                logger.info("  Index exists - dropping for recreation")
                await drop_fulltext_index(driver, index_name)
            else:
                logger.info("  ⏭️  Index already exists - skipping")
                results[index_name] = True
                continue

        # Create index
        success = await create_fulltext_index(driver, label, index_name, fields)
        results[index_name] = success

    logger.info("\n" + "=" * 70)
    logger.info("Summary")
    logger.info("=" * 70)

    successful = sum(1 for status in results.values() if status)
    total = len(results)

    logger.info(f"Created {successful}/{total} full-text indexes")

    if successful < total:
        logger.warning("⚠️  Some indexes failed to create - check errors above")
    else:
        logger.info("✅ All full-text indexes created successfully")

    return results


async def verify_fulltext_indexes(driver: Any) -> dict[str, bool]:
    """
    Verify all full-text indexes exist.

    Args:
        driver: Neo4j driver instance

    Returns:
        Dict mapping index_name -> exists status
    """
    results = {}

    logger.info("\n" + "=" * 70)
    logger.info("Verifying Full-Text Indexes")
    logger.info("=" * 70)

    for label, config in FULLTEXT_INDEX_DEFINITIONS.items():
        index_name = config["index_name"]
        exists = await check_index_exists(driver, index_name)
        results[index_name] = exists

        status = "✅ EXISTS" if exists else "❌ MISSING"
        logger.info(f"{index_name:25s} {status}")

    logger.info("=" * 70)

    missing = sum(1 for status in results.values() if not status)
    if missing > 0:
        logger.warning(f"⚠️  {missing} indexes are missing")
    else:
        logger.info("✅ All indexes verified")

    return results


async def main():
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create full-text indexes for hybrid search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create all indexes (skip existing)
  poetry run python scripts/create_fulltext_indexes.py

  # Recreate all indexes (drop and recreate)
  poetry run python scripts/create_fulltext_indexes.py --recreate

  # Verify indexes exist
  poetry run python scripts/create_fulltext_indexes.py --verify

  # Drop all indexes
  poetry run python scripts/create_fulltext_indexes.py --drop
        """,
    )

    parser.add_argument(
        "--recreate", action="store_true", help="Drop and recreate existing indexes"
    )
    parser.add_argument("--verify", action="store_true", help="Verify indexes exist (no creation)")
    parser.add_argument("--drop", action="store_true", help="Drop all full-text indexes")

    args = parser.parse_args()

    # Get Neo4j credentials
    try:
        neo4j_uri = get_credential("NEO4J_URI", fallback_to_env=True)
        neo4j_user = get_credential("NEO4J_USER", fallback_to_env=True)
        neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

        if not all([neo4j_uri, neo4j_user, neo4j_password]):
            logger.error("❌ Neo4j credentials not configured")
            logger.error("   Configure NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
            return 1

    except Exception as e:
        logger.error(f"❌ Failed to get credentials: {e}")
        return 1

    # Connect to Neo4j
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # Verify connection
        await driver.verify_connectivity()
        logger.info("✅ Connected to Neo4j")

        if args.drop:
            # Drop all indexes
            logger.info("\n🗑️  Dropping all full-text indexes...")
            for config in FULLTEXT_INDEX_DEFINITIONS.values():
                await drop_fulltext_index(driver, config["index_name"])

        elif args.verify:
            # Verify only
            await verify_fulltext_indexes(driver)

        else:
            # Create indexes
            results = await create_all_fulltext_indexes(driver, recreate=args.recreate)

            # Verify after creation
            await verify_fulltext_indexes(driver)

            # Return exit code based on results
            if all(results.values()):
                return 0
            else:
                return 1

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 1

    finally:
        await driver.close()
        logger.info("✅ Disconnected from Neo4j")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
