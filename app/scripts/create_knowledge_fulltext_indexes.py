#!/usr/bin/env python3
"""
Create Full-Text Indexes for Knowledge Domains
===============================================

Creates Neo4j full-text indexes for all knowledge-related entities:
- KnowledgeUnit (Ku): title, content, tags
- LearningPath: name, goal, tags
- Principle: name, statement, description, tags

Usage:
    poetry run python scripts/create_knowledge_fulltext_indexes.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential
from core.utils.logging import get_logger

# Add project root to Python path
project_root = Path(__file__).parent.parent

# Load .env file to get SKUEL_MASTER_KEY
load_dotenv()

logger = get_logger(__name__)


# Index specifications
INDEXES = [
    {
        "name": "ku_fulltext",
        "label": "Ku",
        "properties": ["title", "content", "tags"],
        "description": "Knowledge Units - searchable content, title, and tags",
    },
    {
        "name": "learningpath_fulltext",
        "label": "Lp",
        "properties": ["name", "goal", "tags"],
        "description": "Learning Paths - searchable name, goal, and tags",
    },
    {
        "name": "principle_fulltext",
        "label": "Principle",
        "properties": ["name", "statement", "description", "tags"],
        "description": "Principles - searchable name, statement, description, and tags",
    },
]


async def create_fulltext_index(session, index_spec: dict) -> bool:
    """
    Create a single full-text index.

    Args:
        session: Neo4j session
        index_spec: Index specification dict

    Returns:
        True if created or already exists, False on error
    """
    try:
        # Check if index already exists
        check_query = """
        SHOW FULLTEXT INDEXES
        YIELD name
        WHERE name = $index_name
        RETURN count(*) as exists
        """

        result = await session.run(check_query, {"index_name": index_spec["name"]})
        record = await result.single()

        if record and record["exists"] > 0:
            logger.info(f"  ✓ Index '{index_spec['name']}' already exists")
            return True

        # Create full-text index using Neo4j 5 syntax
        logger.info(f"  Creating index '{index_spec['name']}'...")

        # Build property list for query
        props_str = ", ".join([f"n.{prop}" for prop in index_spec["properties"]])

        create_query = f"""
        CREATE FULLTEXT INDEX {index_spec["name"]} IF NOT EXISTS
        FOR (n:{index_spec["label"]})
        ON EACH [{props_str}]
        """

        await session.run(create_query)

        logger.info(f"  ✓ Index '{index_spec['name']}' created successfully")
        logger.info(f"    Label: {index_spec['label']}")
        logger.info(f"    Properties: {', '.join(index_spec['properties'])}")
        logger.info(f"    Description: {index_spec['description']}")

        return True

    except Exception as e:
        logger.error(f"  ✗ Failed to create index '{index_spec['name']}': {e}")
        return False


async def verify_indexes(driver):
    """Verify all indexes were created correctly."""
    try:
        async with driver.session() as session:
            query = """
            SHOW FULLTEXT INDEXES
            YIELD name, labelsOrTypes, properties, entityType, state
            WHERE name IN $index_names
            RETURN name, labelsOrTypes, properties, entityType, state
            ORDER BY name
            """

            index_names = [idx["name"] for idx in INDEXES]
            result = await session.run(query, {"index_names": index_names})
            records = await result.data()

            if not records:
                logger.warning("No indexes found during verification")
                return False

            logger.info("\n" + "=" * 60)
            logger.info("Index Verification Summary")
            logger.info("=" * 60)

            for record in records:
                logger.info(f"\nIndex: {record['name']}")
                logger.info(f"  Labels: {record['labelsOrTypes']}")
                logger.info(f"  Properties: {record['properties']}")
                logger.info(f"  Entity Type: {record['entityType']}")
                logger.info(f"  State: {record['state']}")

            return True

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False


async def create_all_indexes():
    """Create all knowledge domain full-text indexes."""
    # Get Neo4j credentials from .env and encrypted store
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER")

    # Password is stored in encrypted credential store
    neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        logger.error("Missing Neo4j credentials")
        logger.error(f"  NEO4J_URI: {'✓' if neo4j_uri else '✗'}")
        logger.error(f"  NEO4J_USER: {'✓' if neo4j_user else '✗'}")
        logger.error(
            f"  NEO4J_PASSWORD: {'✓' if neo4j_password else '✗ (check encrypted credential store)'}"
        )
        logger.error("\nTo set NEO4J_PASSWORD:")
        logger.error("  poetry run python -m core.config.credential_setup")
        return False

    logger.info(f"Connecting to Neo4j at {neo4j_uri} as {neo4j_user}...")

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        success_count = 0
        total_count = len(INDEXES)

        async with driver.session() as session:
            for index_spec in INDEXES:
                logger.info(
                    f"\n[{success_count + 1}/{total_count}] Processing {index_spec['label']}..."
                )

                if await create_fulltext_index(session, index_spec):
                    success_count += 1

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Created {success_count}/{total_count} indexes successfully")
        logger.info("=" * 60)

        # Verify indexes
        if success_count > 0:
            logger.info("\nVerifying indexes...")
            await verify_indexes(driver)

        return success_count == total_count

    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")
        return False

    finally:
        await driver.close()


async def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("Knowledge Domain Full-Text Index Setup")
    logger.info("=" * 60)
    logger.info(f"\nCreating {len(INDEXES)} full-text indexes:")
    for idx in INDEXES:
        logger.info(f"  - {idx['name']}: {idx['label']} ({', '.join(idx['properties'])})")

    success = await create_all_indexes()

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("✓ Setup complete! All knowledge search indexes available.")
        logger.info("=" * 60)
        logger.info("\nUsage examples:")
        logger.info("  # Search knowledge units")
        logger.info("  CALL db.index.fulltext.queryNodes('ku_fulltext', 'python async')")
        logger.info("\n  # Search learning paths")
        logger.info(
            "  CALL db.index.fulltext.queryNodes('learningpath_fulltext', 'backend development')"
        )
        logger.info("\n  # Search principles")
        logger.info(
            "  CALL db.index.fulltext.queryNodes('principle_fulltext', 'continuous learning')"
        )
    else:
        logger.error("\n✗ Setup failed. Check logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
