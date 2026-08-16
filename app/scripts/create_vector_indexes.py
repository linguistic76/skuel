"""
Create Vector Indexes for Semantic Search
==========================================

This script creates vector indexes for all embedding-enabled entities in SKUEL.
Embeddings are generated Python-side via EmbeddingsService (ADR-068:
text-embedding-3-small at 1024 dims). No Neo4j plugin is required.

A vector index silently ignores vectors whose dimension doesn't match its
config, and ``CREATE VECTOR INDEX IF NOT EXISTS`` never alters an existing
index — so changing embedding dimension REQUIRES ``--recreate`` (drop + create).

Prerequisites:
- Neo4j running (Docker or AuraDB)
- Connection to Neo4j (bolt://localhost:7687)

Usage:
    # Create indexes for all priority entities
    uv run python scripts/create_vector_indexes.py

    # Drop + recreate (required when the embedding dimension changes)
    uv run python scripts/create_vector_indexes.py --recreate

    # Create indexes for specific entities only
    uv run python scripts/create_vector_indexes.py --labels Ku Task Goal

See also:
- /docs/decisions/ADR-068-openai-embeddings-now-bge-later.md
- /docs/architecture/SEARCH_ARCHITECTURE.md
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
from core.constants import EmbeddingGeometry
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.create_vector_indexes")


# Labels carrying vector indexes. `Entity` covers every domain node via the
# multi-label architecture; Task/Goal are per-label query optimizations;
# ContentChunk powers RAG retrieval; ReferenceChunk powers canon reference
# retrieval on its own index (SearchRouter-invisible); Ku/PathStep power the
# node→node "Related concepts" lens on the explore detail pages;
# LearningPath powers the SearchRouter hybrid rung's vector half.
PRIORITY_ENTITIES = [
    "Entity",
    "ContentChunk",
    "ReferenceChunk",
    "Task",
    "Goal",
    "Ku",
    "PathStep",
    "LearningPath",
]


async def create_vector_indexes(
    entity_labels: list[str] | None = None,
    dimension: int = EmbeddingGeometry.DIMENSION,
    similarity: str = "cosine",
    recreate: bool = False,
) -> None:
    """
    Create vector indexes for embedding-enabled entities.

    Args:
        entity_labels: List of entity labels (defaults to PRIORITY_ENTITIES)
        dimension: Vector dimension (default EmbeddingGeometry.DIMENSION — frozen, ADR-083)
        similarity: Similarity function (default "cosine")
        recreate: Drop each index first (required when dimension changes —
            CREATE ... IF NOT EXISTS never alters an existing index)
    """
    from core.config.intelligence_tier import IntelligenceTier

    config = create_config()

    if not IntelligenceTier.from_env().ai_enabled:
        logger.warning("⚠️ Intelligence tier is CORE — embeddings/vector search are inactive")
        logger.warning("   Vector indexes will be created, but stay unused")
        logger.warning("   Set INTELLIGENCE_TIER=full in .env and restart app to use vector search")
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

        if recreate:
            logger.info("Dropping existing vector indexes (--recreate)...")
            async with driver.session() as session:
                for raw_label in labels:
                    index_name = f"{raw_label.lower()}_embedding_idx"
                    await session.run(f"DROP INDEX {index_name} IF EXISTS")
                    logger.info(f"  Dropped (if existed): {index_name}")
            logger.info("")

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
        logger.info("  2. Generate embeddings: uv run python scripts/generate_embeddings_batch.py")
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
                logger.warning("   Run: uv run python scripts/create_vector_indexes.py")
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
        description="Create vector indexes for semantic search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create indexes for all priority entities (Entity, ContentChunk, Task, Goal)
  uv run python scripts/create_vector_indexes.py

  # Drop + recreate at the current dimension (required after a dimension change)
  uv run python scripts/create_vector_indexes.py --recreate

  # Create indexes for specific entities only
  uv run python scripts/create_vector_indexes.py --labels Ku Task

  # Verify existing indexes
  uv run python scripts/create_vector_indexes.py --verify

For more information:
  - ADR-068: /docs/decisions/ADR-068-openai-embeddings-now-bge-later.md
  - Search architecture: /docs/architecture/SEARCH_ARCHITECTURE.md
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
        default=EmbeddingGeometry.DIMENSION,
        help=f"Vector dimension (default: {EmbeddingGeometry.DIMENSION} — "
        "EmbeddingGeometry.DIMENSION, frozen by ADR-083; shared by "
        "text-embedding-3-small via the API dimensions param and the staged BGE path)",
    )

    parser.add_argument(
        "--similarity",
        choices=["cosine", "euclidean"],
        default="cosine",
        help="Similarity function (default: cosine)",
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop each index before creating (required when the dimension changes)",
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
                entity_labels=args.labels,
                dimension=args.dimension,
                similarity=args.similarity,
                recreate=args.recreate,
            )
        )


if __name__ == "__main__":
    main()
