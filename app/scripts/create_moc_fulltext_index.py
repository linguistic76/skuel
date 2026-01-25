"""
Create Full-Text Index for MapOfContent
========================================

Creates Neo4j full-text index for MOC search optimization.

Index covers:
- title: Primary search field
- description: Secondary search field
- tags: Metadata search field

Usage:
    poetry run python scripts/create_moc_fulltext_index.py
"""

import asyncio
import os
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


async def create_moc_fulltext_index():
    """Create full-text index for MapOfContent search."""

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
        async with driver.session() as session:
            # Check if index already exists
            check_query = """
            SHOW FULLTEXT INDEXES
            YIELD name
            WHERE name = 'mapofcontent_fulltext'
            RETURN count(*) as exists
            """

            result = await session.run(check_query)
            record = await result.single()

            if record and record["exists"] > 0:
                logger.info("Full-text index 'mapofcontent_fulltext' already exists")
                return True

            # Create full-text index using Neo4j 5 syntax
            logger.info("Creating full-text index 'mapofcontent_fulltext'...")

            # Neo4j 5+ uses CREATE FULLTEXT INDEX syntax
            create_query = """
            CREATE FULLTEXT INDEX mapofcontent_fulltext IF NOT EXISTS
            FOR (n:MapOfContent)
            ON EACH [n.title, n.description, n.tags]
            """

            await session.run(create_query)

            logger.info("✓ Full-text index 'mapofcontent_fulltext' created successfully")
            logger.info("  - Label: MapOfContent")
            logger.info("  - Properties: title, description, tags")
            logger.info(
                "  - Usage: db.index.fulltext.queryNodes('mapofcontent_fulltext', 'query text')"
            )

            return True

    except Exception as e:
        logger.error(f"Failed to create full-text index: {e}")
        return False

    finally:
        await driver.close()


async def verify_index():
    """Verify the index was created correctly."""

    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER")
    neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        async with driver.session() as session:
            query = """
            SHOW FULLTEXT INDEXES
            YIELD name, labelsOrTypes, properties, entityType, state
            WHERE name = 'mapofcontent_fulltext'
            RETURN name, labelsOrTypes, properties, entityType, state
            """

            result = await session.run(query)
            record = await result.single()

            if record:
                logger.info("\nIndex verification:")
                logger.info(f"  Name: {record['name']}")
                logger.info(f"  Labels: {record['labelsOrTypes']}")
                logger.info(f"  Properties: {record['properties']}")
                logger.info(f"  Entity Type: {record['entityType']}")
                logger.info(f"  State: {record['state']}")
                return True
            else:
                logger.warning("Index not found during verification")
                return False

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False

    finally:
        await driver.close()


async def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("MOC Full-Text Index Setup")
    logger.info("=" * 60)

    # Create index
    success = await create_moc_fulltext_index()

    if success:
        # Verify index
        logger.info("\nVerifying index...")
        await verify_index()

        logger.info("\n" + "=" * 60)
        logger.info("Setup complete! MOC full-text search is now available.")
        logger.info("=" * 60)
    else:
        logger.error("\nSetup failed. Check logs above for details.")


if __name__ == "__main__":
    asyncio.run(main())
