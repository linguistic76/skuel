"""
Batch Embedding Generation Script
==================================

Generates embeddings for existing entities that don't have them.

Usage:
    # Generate embeddings for all entity types
    poetry run python scripts/generate_embeddings_batch.py

    # Generate for specific entity type
    poetry run python scripts/generate_embeddings_batch.py --label Ku

    # Limit batches (for testing)
    poetry run python scripts/generate_embeddings_batch.py --label Ku --max-batches 2

ARCHITECTURE:
- Uses Neo4jGenAIEmbeddingsService for embedding generation
- Processes in batches of 25 (Neo4j optimal batch size)
- Updates nodes with embedding, embedding_model, and embedding_updated_at
- Graceful error handling - logs failures but continues processing

COST ESTIMATION:
- OpenAI text-embedding-3-small: $0.02 per 1M tokens
- Typical entity: ~200 tokens
- 1000 entities: ~$0.004

See: /docs/migrations/NEO4J_GENAI_MIGRATION.md
"""

import argparse
import asyncio
from datetime import datetime

from core.models.shared_enums import EntityType
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.utils.logging import get_logger

logger = get_logger("skuel.batch_embeddings")


async def generate_embeddings_batch(
    driver: any,
    embeddings_service: Neo4jGenAIEmbeddingsService,
    label: str,
    batch_size: int = 25,
    max_batches: int | None = None,
) -> dict[str, any]:
    """
    Generate embeddings for all nodes of a given label.

    Args:
        driver: Neo4j driver instance
        embeddings_service: Neo4jGenAIEmbeddingsService instance
        label: Node label (e.g., "Ku", "Task", "Goal")
        batch_size: Number of nodes per batch (default: 25)
        max_batches: Limit number of batches for testing (default: None = all)

    Returns:
        Stats dict with counts of processed, successful, and failed nodes
    """
    logger.info(f"Starting batch embedding generation for {label}")

    # Find nodes without embeddings
    query = f"""
    MATCH (n:{label})
    WHERE n.embedding IS NULL
    RETURN n.uid as uid, n.title as title,
           COALESCE(n.content, n.description, '') as text
    """

    result = await driver.execute_query(query)

    if not result:
        logger.info(f"No {label} nodes need embeddings")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    total = len(result)
    logger.info(f"Found {total} {label} nodes without embeddings")

    # Process in batches
    batches_processed = 0
    successful = 0
    failed = 0

    for i in range(0, total, batch_size):
        if max_batches and batches_processed >= max_batches:
            logger.info(f"Reached max_batches limit ({max_batches}), stopping")
            break

        batch = result[i : i + batch_size]
        uids = [r["uid"] for r in batch]

        # Combine title and text for embedding
        texts = [f"{r['title']}\n{r['text']}" if r['title'] else r['text'] for r in batch]

        logger.info(f"Processing batch {batches_processed + 1}: {len(batch)} nodes")

        # Generate embeddings
        embeddings_result = await embeddings_service.create_batch_embeddings(texts)

        if embeddings_result.is_error:
            logger.error(f"Batch failed: {embeddings_result.expect_error()}")
            failed += len(batch)
            batches_processed += 1
            continue

        embeddings = embeddings_result.value

        # Update nodes with embeddings
        update_query = f"""
        UNWIND $updates as update
        MATCH (n:{label} {{uid: update.uid}})
        SET n.embedding = update.embedding,
            n.embedding_model = $model,
            n.embedding_updated_at = datetime()
        """

        updates = [{"uid": uid, "embedding": emb} for uid, emb in zip(uids, embeddings, strict=False)]

        try:
            await driver.execute_query(
                update_query, {"updates": updates, "model": embeddings_service.model}
            )

            logger.info(f"✅ Updated {len(updates)} nodes with embeddings")
            successful += len(updates)

        except Exception as e:
            logger.error(f"Failed to update batch: {e}")
            failed += len(batch)

        batches_processed += 1

    logger.info(
        f"Batch embedding generation complete for {label}: "
        f"{batches_processed} batches, {successful} successful, {failed} failed"
    )

    return {
        "label": label,
        "total": total,
        "processed": batches_processed * batch_size,
        "successful": successful,
        "failed": failed,
    }


async def main():
    """Run batch embedding generation for all entity types or a specific one."""
    parser = argparse.ArgumentParser(description="Generate embeddings for existing entities")
    parser.add_argument(
        "--label",
        type=str,
        help="Specific entity label to process (e.g., Ku, Task, Goal)",
        default=None,
    )
    parser.add_argument(
        "--batch-size", type=int, default=25, help="Number of entities per batch (default: 25)"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Maximum number of batches to process (for testing)",
    )

    args = parser.parse_args()

    # Bootstrap services
    from core.utils.db import get_driver

    driver = await get_driver()

    # Create embeddings service
    embeddings_service = Neo4jGenAIEmbeddingsService(driver)

    # Check if plugin available
    if not await embeddings_service._check_plugin_availability():
        logger.error("❌ Neo4j GenAI plugin not available - cannot generate embeddings")
        logger.error("   Configure GenAI plugin in AuraDB console with OpenAI API key")
        return

    # Priority entity labels
    if args.label:
        entity_labels = [args.label]
    else:
        entity_labels = ["Ku", "Task", "Goal", "LpStep"]

    logger.info(f"\n{'='*60}")
    logger.info(f"Batch Embedding Generation")
    logger.info(f"{'='*60}\n")
    logger.info(f"Entity types: {', '.join(entity_labels)}")
    logger.info(f"Batch size: {args.batch_size}")
    if args.max_batches:
        logger.info(f"Max batches: {args.max_batches}")
    logger.info("")

    all_stats = []

    for label in entity_labels:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {label}")
        logger.info(f"{'='*60}\n")

        stats = await generate_embeddings_batch(
            driver=driver,
            embeddings_service=embeddings_service,
            label=label,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )

        all_stats.append(stats)

        # Small delay between entity types
        await asyncio.sleep(2)

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("Summary")
    logger.info(f"{'='*60}\n")

    total_processed = sum(s["successful"] for s in all_stats)
    total_failed = sum(s["failed"] for s in all_stats)

    for stats in all_stats:
        logger.info(
            f"{stats['label']}: {stats['successful']}/{stats['total']} successful "
            f"({stats['failed']} failed)"
        )

    logger.info(f"\n✅ All batch embedding generation complete")
    logger.info(f"Total: {total_processed} successful, {total_failed} failed")

    await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
