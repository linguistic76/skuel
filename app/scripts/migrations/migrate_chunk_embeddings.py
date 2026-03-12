"""
Batch Migration: Generate Embeddings for ContentChunk Nodes
============================================================

Generates embeddings for all existing ContentChunk nodes that don't have embeddings yet.

This migration script:
1. Queries all ContentChunk nodes without embeddings
2. Processes them in batches for efficiency
3. Generates embeddings for context windows
4. Stores embeddings with version metadata
5. Tracks progress and handles errors gracefully

Prerequisites:
- HF_API_TOKEN environment variable set
- INTELLIGENCE_TIER=full in .env
- Vector index created: contentchunk_embedding_idx

Usage:
    # Dry run (no changes, shows what would be done)
    uv run python scripts/migrations/migrate_chunk_embeddings.py --dry-run

    # Production run with default batch size (100)
    uv run python scripts/migrations/migrate_chunk_embeddings.py

    # Custom batch size
    uv run python scripts/migrations/migrate_chunk_embeddings.py --batch-size 50

    # Limit number of chunks to process (for testing)
    uv run python scripts/migrations/migrate_chunk_embeddings.py --limit 1000

See also:
- /docs/migrations/CHUNK_EMBEDDINGS_MIGRATION.md - Migration guide
- /scripts/create_vector_indexes.py - Vector index creation
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from neo4j import AsyncGraphDatabase

from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.config import create_config
from core.services.embeddings_service import HuggingFaceEmbeddingsService
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.chunk_embeddings")


async def get_chunks_without_embeddings(
    driver: any,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, any]]:
    """
    Query all ContentChunk nodes that don't have embeddings yet.

    Args:
        driver: Neo4j async driver
        limit: Optional limit on number of chunks to retrieve
        offset: Offset for pagination

    Returns:
        List of chunk dictionaries with uid and context_window
    """
    query = """
    MATCH (chunk:ContentChunk)
    WHERE chunk.embedding IS NULL
      AND chunk.context_window IS NOT NULL
      AND chunk.context_window <> ''
    RETURN
        chunk.uid as chunk_uid,
        chunk.context_window as context_window,
        chunk.chunk_type as chunk_type
    ORDER BY chunk.uid
    """

    if offset > 0:
        query += f" SKIP {offset}"

    if limit:
        query += f" LIMIT {limit}"

    async with driver.session() as session:
        result = await session.run(query)
        records = await result.data()
        return records


async def get_total_chunks_without_embeddings(driver: any) -> int:
    """
    Count total ContentChunk nodes without embeddings.

    Args:
        driver: Neo4j async driver

    Returns:
        Count of chunks without embeddings
    """
    query = """
    MATCH (chunk:ContentChunk)
    WHERE chunk.embedding IS NULL
      AND chunk.context_window IS NOT NULL
      AND chunk.context_window <> ''
    RETURN count(chunk) as total
    """

    async with driver.session() as session:
        result = await session.run(query)
        record = await result.single()
        return record["total"] if record else 0


async def migrate_chunk_embeddings(
    batch_size: int = 100,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Generate embeddings for all ContentChunk nodes without embeddings.

    Args:
        batch_size: Number of chunks to process per batch (default 100)
        limit: Optional limit on total chunks to process
        dry_run: If True, only simulate the migration without making changes

    Returns:
        Dictionary with migration statistics:
        - total: Total chunks found without embeddings
        - processed: Total chunks processed
        - successful: Successfully embedded chunks
        - failed: Failed chunks
        - skipped: Skipped chunks (dry run)
    """
    config = create_config()

    # Validate prerequisites
    if not config.genai.enabled:
        logger.error("❌ Embeddings service is disabled (INTELLIGENCE_TIER is not full)")
        logger.error("   Set INTELLIGENCE_TIER=full in .env before running migration")
        return {"total": 0, "processed": 0, "successful": 0, "failed": 0, "skipped": 0}

    if not config.genai.embeddings_enabled:
        logger.error("❌ Embeddings are disabled (GENAI_EMBEDDINGS_ENABLED=False)")
        logger.error("   Enable embeddings in config before running migration")
        return {"total": 0, "processed": 0, "successful": 0, "failed": 0, "skipped": 0}

    logger.info("=" * 70)
    logger.info("Chunk Embeddings Migration")
    logger.info("=" * 70)
    logger.info("")

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info("")

    # Connect to Neo4j
    driver = AsyncGraphDatabase.driver(
        config.database.neo4j_uri, auth=(config.database.neo4j_username, config.database.neo4j_password)
    )

    # Initialize services
    neo4j_connection = Neo4jConnection(
        uri=config.database.neo4j_uri,
        username=config.database.neo4j_username,
        password=config.database.neo4j_password,
    )
    await neo4j_connection.connect()

    embeddings_service = HuggingFaceEmbeddingsService(
        driver=driver,
        model=config.genai.embedding_model,
    )

    content_adapter = Neo4jContentAdapter(neo4j_connection)

    stats = {
        "total": 0,
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0,
    }

    try:
        # Get total count
        total_chunks = await get_total_chunks_without_embeddings(driver)
        stats["total"] = total_chunks

        if limit:
            total_chunks = min(total_chunks, limit)

        logger.info(f"📊 Found {total_chunks} chunks without embeddings")
        logger.info(f"   Batch size: {batch_size}")
        logger.info(f"   Processing limit: {limit or 'unlimited'}")
        logger.info("")

        if total_chunks == 0:
            logger.info("✅ No chunks need embeddings - migration complete!")
            return stats

        if dry_run:
            logger.info(f"🔍 DRY RUN: Would process {total_chunks} chunks in batches of {batch_size}")
            logger.info("")

            # Show sample of what would be processed
            sample_chunks = await get_chunks_without_embeddings(driver, limit=5)
            logger.info("Sample chunks that would be processed:")
            for i, chunk in enumerate(sample_chunks, 1):
                chunk_uid = chunk["chunk_uid"]
                chunk_type = chunk["chunk_type"]
                context_preview = chunk["context_window"][:100]
                logger.info(f"  {i}. {chunk_uid} ({chunk_type})")
                logger.info(f"     Context: {context_preview}...")

            stats["skipped"] = total_chunks
            return stats

        # Process in batches
        offset = 0
        batch_num = 0
        migration_start = time.time()

        while offset < total_chunks:
            batch_num += 1
            batch_start = time.time()

            # Get batch of chunks
            chunks = await get_chunks_without_embeddings(
                driver, limit=batch_size, offset=offset
            )

            if not chunks:
                break

            logger.info(f"📦 Batch {batch_num} ({offset + 1}-{offset + len(chunks)} of {total_chunks})")

            # Extract data for embedding generation
            chunk_uids = [c["chunk_uid"] for c in chunks]
            chunk_texts = [c["context_window"] for c in chunks]

            # Generate embeddings
            logger.info(f"   Generating embeddings for {len(chunk_texts)} chunks...")
            embeddings_result = await embeddings_service.create_batch_embeddings(chunk_texts)

            if embeddings_result.is_error:
                error_msg = embeddings_result.expect_error().message
                logger.error(f"   ❌ Batch embedding generation failed: {error_msg}")
                stats["failed"] += len(chunks)
                stats["processed"] += len(chunks)
                offset += batch_size
                continue

            embeddings = embeddings_result.value

            # Store embeddings
            logger.info(f"   Storing embeddings...")
            stored = await content_adapter.store_chunk_embeddings(
                chunk_uids=chunk_uids,
                embeddings=embeddings,
                version="v1",
                model=config.genai.embedding_model,
            )

            if stored:
                stats["successful"] += len(chunks)
                batch_duration = time.time() - batch_start
                logger.info(
                    f"   ✅ Stored {len(chunks)} embeddings successfully "
                    f"(took {batch_duration:.2f}s, ~{batch_duration/len(chunks):.3f}s per chunk)"
                )
            else:
                logger.error(f"   ❌ Failed to store embeddings for batch {batch_num}")
                stats["failed"] += len(chunks)

            stats["processed"] += len(chunks)
            offset += batch_size

            # Progress summary
            progress_pct = (stats["processed"] / total_chunks) * 100
            logger.info(
                f"   Progress: {stats['processed']}/{total_chunks} "
                f"({progress_pct:.1f}%) - "
                f"{stats['successful']} successful, {stats['failed']} failed"
            )
            logger.info("")

        # Final summary
        migration_duration = time.time() - migration_start
        logger.info("=" * 70)
        logger.info("Migration Complete")
        logger.info("=" * 70)
        logger.info(f"Total chunks found:      {stats['total']}")
        logger.info(f"Chunks processed:        {stats['processed']}")
        logger.info(f"Successfully embedded:   {stats['successful']}")
        logger.info(f"Failed:                  {stats['failed']}")
        logger.info(f"Total time:              {migration_duration:.2f}s")

        if stats['successful'] > 0:
            avg_time = migration_duration / stats['successful']
            logger.info(f"Average time per chunk:  {avg_time:.3f}s")

        logger.info("")

        # Success rate
        if stats['processed'] > 0:
            success_rate = (stats['successful'] / stats['processed']) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")

        logger.info("")

        # Next steps
        logger.info("Next steps:")
        logger.info("  1. Verify embeddings: MATCH (c:ContentChunk) WHERE c.embedding IS NOT NULL RETURN count(c)")
        logger.info("  2. Test semantic search: uv run python -m pytest tests/integration/test_chunk_semantic_search.py")
        logger.info("  3. Monitor query performance in production")
        logger.info("")

        return stats

    except Exception as e:
        logger.error(f"❌ Migration failed with exception: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        await driver.close()
        await neo4j_connection.close()


async def verify_vector_index() -> bool:
    """
    Verify that the ContentChunk vector index exists.

    Returns:
        True if index exists, False otherwise
    """
    config = create_config()
    driver = AsyncGraphDatabase.driver(
        config.database.neo4j_uri, auth=(config.database.neo4j_username, config.database.neo4j_password)
    )

    try:
        async with driver.session() as session:
            result = await session.run("SHOW INDEXES")
            indexes = await result.data()

            # Look for contentchunk_embedding_idx
            for idx in indexes:
                name = idx.get("name", "")
                if name == "contentchunk_embedding_idx":
                    logger.info(f"✅ Vector index found: {name}")
                    logger.info(f"   Type: {idx.get('type')}")
                    logger.info(f"   Labels: {idx.get('labelsOrTypes')}")
                    logger.info(f"   Properties: {idx.get('properties')}")
                    return True

        logger.warning("⚠️ Vector index 'contentchunk_embedding_idx' not found")
        logger.warning("   Run: uv run python scripts/create_vector_indexes.py")
        return False

    finally:
        await driver.close()


def main() -> None:
    """Main entry point for migration script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate embeddings for ContentChunk nodes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be processed
  uv run python scripts/migrations/migrate_chunk_embeddings.py --dry-run

  # Process all chunks with default batch size (100)
  uv run python scripts/migrations/migrate_chunk_embeddings.py

  # Process with custom batch size
  uv run python scripts/migrations/migrate_chunk_embeddings.py --batch-size 50

  # Process limited number of chunks (for testing)
  uv run python scripts/migrations/migrate_chunk_embeddings.py --limit 1000 --dry-run

Performance:
  - Batch size 100: ~10-15s per batch (HuggingFace Inference API rate limits)
  - Expected: ~100 chunks/minute
  - For 10,000 chunks: ~1.5-2 hours

Cost:
  - HuggingFace Inference API (free tier available; paid plans for higher throughput)

Prerequisites:
  1. Vector index created: uv run python scripts/create_vector_indexes.py
  2. HF_API_TOKEN set in .env
  3. INTELLIGENCE_TIER=full in .env
        """,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chunks to process per batch (default: 100)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit total number of chunks to process (default: unlimited)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without making changes",
    )

    parser.add_argument(
        "--verify-index",
        action="store_true",
        help="Verify vector index exists before migration",
    )

    args = parser.parse_args()

    # Verify index if requested
    if args.verify_index:
        index_exists = asyncio.run(verify_vector_index())
        if not index_exists:
            logger.error("Vector index verification failed - aborting migration")
            sys.exit(1)
        logger.info("")

    # Run migration
    stats = asyncio.run(
        migrate_chunk_embeddings(
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    )

    # Exit with appropriate code
    if stats["failed"] > 0:
        logger.warning(f"⚠️ Migration completed with {stats['failed']} failures")
        sys.exit(1)
    elif stats["successful"] > 0 or stats["skipped"] > 0:
        logger.info("✅ Migration completed successfully")
        sys.exit(0)
    else:
        logger.info("ℹ️ No chunks needed processing")
        sys.exit(0)


if __name__ == "__main__":
    main()
