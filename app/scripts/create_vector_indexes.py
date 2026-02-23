"""
Create Vector Indexes for Neo4j GenAI Plugin
=============================================

This script creates vector indexes for all embedding-enabled entities in SKUEL.
Run this after starting Neo4j with GenAI plugin enabled (via docker-compose).

Prerequisites:
- Docker Neo4j running with GenAI plugin enabled (NEO4J_PLUGINS='["genai"]')
- OPENAI_API_KEY environment variable set
- Connection to Neo4j (bolt://localhost:7687)

Usage:
    # Create indexes for all priority entities
    poetry run python scripts/create_vector_indexes.py

    # Create indexes for specific entities only
    poetry run python scripts/create_vector_indexes.py --labels Ku Task Goal

    # Use different embedding dimensions
    poetry run python scripts/create_vector_indexes.py --dimension 3072

See also:
- /docs/development/GENAI_SETUP.md - Docker GenAI setup guide
- /docs/deployment/AURADB_MIGRATION_GUIDE.md - AuraDB production migration
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file before importing config
from dotenv import load_dotenv

load_dotenv()

from neo4j import AsyncGraphDatabase

from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from core.config import create_config
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.create_vector_indexes")


# Priority entities with embedding fields (as of Phase 8 - January 2026)
PRIORITY_ENTITIES = [
    "Curriculum",  # Curriculum (Knowledge Units) - CRITICAL
    "ContentChunk",  # KU Content Chunks - CRITICAL (for RAG)
    "Task",  # Tasks - HIGH
    "Goal",  # Goals - HIGH
    "LpStep",  # Learning Path Steps - HIGH
]


async def create_vector_indexes(
    entity_labels: list[str] | None = None,
    dimension: int = 1536,
    similarity: str = "cosine",
) -> None:
    """
    Create vector indexes for embedding-enabled entities.

    Args:
        entity_labels: List of entity labels (defaults to PRIORITY_ENTITIES)
        dimension: Vector dimension (default 1536 for text-embedding-3-small)
        similarity: Similarity function (default "cosine")
    """
    config = create_config()

    # Check if GenAI is enabled
    if not config.genai.enabled:
        logger.warning("⚠️ GenAI plugin is disabled in config (GENAI_ENABLED=False)")
        logger.warning("   Vector indexes will be created, but search will not work")
        logger.warning("   Enable GenAI in config and restart app to use vector search")
        logger.warning("")

    # Check if vector search is enabled
    if not config.genai.vector_search_enabled:
        logger.warning("⚠️ Vector search is disabled in config (GENAI_VECTOR_SEARCH_ENABLED=False)")
        logger.warning("   Vector indexes will be created, but search will not work")
        logger.warning("   Enable vector search in config to use")
        logger.warning("")

    # Use provided labels or default to priority entities
    labels = entity_labels or PRIORITY_ENTITIES

    logger.info(f"Creating vector indexes for {len(labels)} entities")
    logger.info(f"Entity labels: {', '.join(labels)}")
    logger.info(f"Dimension: {dimension}")
    logger.info(f"Similarity: {similarity}")
    logger.info("")

    # Connect to Neo4j
    driver = AsyncGraphDatabase.driver(
        config.database.neo4j_uri,
        auth=(config.database.neo4j_username, config.database.neo4j_password),
    )

    try:
        # Create schema manager
        schema_manager = Neo4jSchemaManager(driver)

        # Sync vector indexes
        result = await schema_manager.sync_vector_indexes(
            entity_labels=labels, dimension=dimension, similarity=similarity
        )

        if result.is_error:
            logger.error(f"❌ Failed to create vector indexes: {result.error}")
            return

        # Display results
        summary = result.value
        created = summary.get("created", [])
        failed = summary.get("failed", [])

        logger.info("")
        logger.info("✅ Vector index creation complete")
        logger.info(f"   Created: {len(created)}")
        logger.info(f"   Failed: {len(failed)}")
        logger.info("")

        if created:
            logger.info("Created indexes:")
            for index_name in created:
                logger.info(f"  ✅ {index_name}")

        if failed:
            logger.warning("")
            logger.warning("Failed indexes:")
            for index_name in failed:
                logger.warning(f"  ❌ {index_name}")

        # Verification instructions
        logger.info("")
        logger.info("Verification:")
        logger.info("  Run in Neo4j Browser: SHOW INDEXES")
        logger.info("  Look for indexes with type: VECTOR")
        logger.info("")

        # Next steps
        logger.info("Next steps:")
        logger.info("  1. Verify indexes exist: SHOW INDEXES")
        logger.info(
            "  2. Generate embeddings: poetry run python scripts/generate_embeddings_batch.py"
        )
        logger.info("  3. Test vector search via API: POST /api/search/unified")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ Error creating vector indexes: {e}")
        raise

    finally:
        await driver.close()


async def verify_vector_indexes() -> None:
    """
    Verify that vector indexes exist and show their configuration.
    """
    config = create_config()

    logger.info("Verifying vector indexes...")

    # Connect to Neo4j
    driver = AsyncGraphDatabase.driver(
        config.database.neo4j_uri,
        auth=(config.database.neo4j_username, config.database.neo4j_password),
    )

    try:
        async with driver.session() as session:
            # Get all indexes
            result = await session.run("SHOW INDEXES")
            indexes = await result.data()

            # Filter to vector indexes
            vector_indexes = [idx for idx in indexes if idx.get("type") == "VECTOR"]

            if not vector_indexes:
                logger.warning("⚠️ No vector indexes found")
                logger.warning("   Run: poetry run python scripts/create_vector_indexes.py")
                return

            logger.info(f"✅ Found {len(vector_indexes)} vector indexes")
            logger.info("")

            for idx in vector_indexes:
                name = idx.get("name")
                labels = idx.get("labelsOrTypes", [])
                properties = idx.get("properties", [])
                logger.info(f"  Index: {name}")
                logger.info(f"    Labels: {labels}")
                logger.info(f"    Properties: {properties}")
                logger.info("")

    except Exception as e:
        logger.error(f"❌ Error verifying indexes: {e}")
        raise

    finally:
        await driver.close()


def main() -> None:
    """Main entry point for script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create vector indexes for Neo4j GenAI plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create indexes for all priority entities (Curriculum, Task, Goal, LpStep)
  poetry run python scripts/create_vector_indexes.py

  # Create indexes for specific entities only
  poetry run python scripts/create_vector_indexes.py --labels Curriculum Task

  # Use different embedding dimensions (for text-embedding-3-large)
  poetry run python scripts/create_vector_indexes.py --dimension 3072

  # Verify existing indexes
  poetry run python scripts/create_vector_indexes.py --verify

For more information:
  - Setup guide: /docs/development/GENAI_SETUP.md
  - Migration guide: /docs/migrations/NEO4J_GENAI_MIGRATION.md
        """,
    )

    parser.add_argument(
        "--labels",
        nargs="+",
        help=f"Entity labels to create indexes for (default: {' '.join(PRIORITY_ENTITIES)})",
    )

    parser.add_argument(
        "--dimension",
        type=int,
        default=1536,
        help="Vector dimension (default: 1536 for text-embedding-3-small)",
    )

    parser.add_argument(
        "--similarity",
        choices=["cosine", "euclidean", "dot"],
        default="cosine",
        help="Similarity function (default: cosine)",
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing vector indexes instead of creating new ones",
    )

    args = parser.parse_args()

    if args.verify:
        asyncio.run(verify_vector_indexes())
    else:
        asyncio.run(
            create_vector_indexes(
                entity_labels=args.labels, dimension=args.dimension, similarity=args.similarity
            )
        )


if __name__ == "__main__":
    main()
