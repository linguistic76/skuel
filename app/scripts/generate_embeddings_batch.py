"""
Batch Embedding Generation Script
==================================

Generates embeddings for existing entities that don't have them.

Usage:
    # Generate embeddings for all entity types
    uv run python scripts/generate_embeddings_batch.py

    # Generate for specific entity type
    uv run python scripts/generate_embeddings_batch.py --label PathStep

    # Limit batches (for testing)
    uv run python scripts/generate_embeddings_batch.py --label Ku --max-batches 2

ARCHITECTURE:
- Uses EmbeddingsService for embedding generation AND storage, so backfilled
  nodes carry the same version/model metadata the background worker writes
- Embedding text built via build_embedding_text (same field maps as the
  event-driven path — one text recipe, two triggers)
- Processes in batches of 25
- Graceful error handling - logs failures but continues processing

COST ESTIMATION (ADR-068, text-embedding-3-small):
- Typical entity: ~200 tokens
- 1000 entities: well under $0.01
"""

import argparse
import asyncio
from typing import Any

from core.models.enums.entity_enums import EntityType
from core.services.embeddings_service import EmbeddingsService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.logging import get_logger

logger = get_logger("skuel.batch_embeddings")

# Neo4j label → EntityType for embedding-text field maps (mirrors the
# background worker's label_map, inverted).
EMBEDDABLE_LABELS: dict[str, EntityType] = {
    "Task": EntityType.TASK,
    "Goal": EntityType.GOAL,
    "Habit": EntityType.HABIT,
    "Event": EntityType.EVENT,
    "Choice": EntityType.CHOICE,
    "Principle": EntityType.PRINCIPLE,
    "Ku": EntityType.KU,
    "Resource": EntityType.RESOURCE,
    "Exercise": EntityType.EXERCISE,
    "PathStep": EntityType.PATH_STEP,
    "LearningPath": EntityType.LEARNING_PATH,
    "RevisedExercise": EntityType.REVISED_EXERCISE,
}


async def generate_embeddings_batch(
    driver: Any,
    embeddings_service: EmbeddingsService,
    label: str,
    batch_size: int = 25,
    max_batches: int | None = None,
) -> dict[str, Any]:
    """
    Generate embeddings for all nodes of a given label.

    Args:
        driver: Neo4j driver instance
        embeddings_service: EmbeddingsService instance
        label: Node label (e.g., "Ku", "PathStep", "Task")
        batch_size: Number of nodes per batch (default: 25)
        max_batches: Limit number of batches for testing (default: None = all)

    Returns:
        Stats dict with counts of processed, successful, and failed nodes
    """
    logger.info(f"Starting batch embedding generation for {label}")

    entity_type = EMBEDDABLE_LABELS.get(label)
    if entity_type is None:
        logger.error(f"Unsupported label: {label} (supported: {', '.join(EMBEDDABLE_LABELS)})")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    # Find nodes without embeddings; full properties feed build_embedding_text
    query = f"""
    MATCH (n:{label})
    WHERE n.embedding IS NULL
    RETURN n.uid as uid, properties(n) as props
    """

    result = await driver.execute_query(query)
    records = result.records

    if not records:
        logger.info(f"No {label} nodes need embeddings")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    # Same text recipe as the event-driven path; skip content-less nodes
    candidates = [(r["uid"], build_embedding_text(entity_type, r["props"])) for r in records]
    skipped = [uid for uid, text in candidates if not text]
    candidates = [(uid, text) for uid, text in candidates if text]

    total = len(candidates)
    logger.info(
        f"Found {total} {label} nodes without embeddings"
        + (f" ({len(skipped)} skipped: no embeddable text)" if skipped else "")
    )

    # Process in batches
    batches_processed = 0
    successful = 0
    failed = 0

    for i in range(0, total, batch_size):
        if max_batches and batches_processed >= max_batches:
            logger.info(f"Reached max_batches limit ({max_batches}), stopping")
            break

        batch = candidates[i : i + batch_size]

        logger.info(f"Processing batch {batches_processed + 1}: {len(batch)} nodes")

        # Generate embeddings
        embeddings_result = await embeddings_service.create_batch_embeddings(
            [text for _, text in batch]
        )

        if embeddings_result.is_error:
            logger.error(f"Batch failed: {embeddings_result.expect_error()}")
            failed += len(batch)
            batches_processed += 1
            continue

        embeddings = embeddings_result.value

        # Store through the service so version/model metadata matches the worker path
        for (uid, _), embedding in zip(batch, embeddings, strict=True):
            store_result = await embeddings_service.store_embedding_with_metadata(
                uid=uid, label=label, embedding=embedding
            )
            if store_result.is_error:
                logger.error(f"Failed to store embedding for {uid}: {store_result.error}")
                failed += 1
            else:
                successful += 1

        batches_processed += 1

    logger.info(
        f"Batch embedding generation complete for {label}: "
        f"{batches_processed} batches, {successful} successful, {failed} failed"
    )

    return {
        "label": label,
        "total": total,
        "processed": successful + failed,
        "successful": successful,
        "failed": failed,
    }


async def main():
    """Run batch embedding generation for all entity types or a specific one."""
    parser = argparse.ArgumentParser(description="Generate embeddings for existing entities")
    parser.add_argument(
        "--label",
        type=str,
        help="Specific entity label to process (e.g., Ku, PathStep, Task)",
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
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = await conn.connect()

    # Create embeddings service (inference client behind a port — W1).
    # The factory is the provider chokepoint (ADR-068); a missing API key
    # raises ValueError = the "not available" signal.
    from adapters.external.embeddings import create_embedding_client
    from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    try:
        embedding_client = create_embedding_client()
    except ValueError as e:
        logger.error(f"❌ Embedding client not available - cannot generate embeddings: {e}")
        return

    embeddings_service = EmbeddingsService(
        backend=EmbeddingsBackend(executor=Neo4jQueryExecutor(driver)),
        embedding_client=embedding_client,
    )

    # All embeddable labels, or a specific one
    entity_labels = [args.label] if args.label else list(EMBEDDABLE_LABELS)

    logger.info(f"\n{'=' * 60}")
    logger.info("Batch Embedding Generation")
    logger.info(f"{'=' * 60}\n")
    logger.info(f"Entity types: {', '.join(entity_labels)}")
    logger.info(f"Batch size: {args.batch_size}")
    if args.max_batches:
        logger.info(f"Max batches: {args.max_batches}")
    logger.info("")

    all_stats = []

    for label in entity_labels:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing {label}")
        logger.info(f"{'=' * 60}\n")

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
    logger.info(f"\n{'=' * 60}")
    logger.info("Summary")
    logger.info(f"{'=' * 60}\n")

    total_processed = sum(s["successful"] for s in all_stats)
    total_failed = sum(s["failed"] for s in all_stats)

    for stats in all_stats:
        logger.info(
            f"{stats['label']}: {stats['successful']}/{stats['total']} successful "
            f"({stats['failed']} failed)"
        )

    logger.info("\n✅ All batch embedding generation complete")
    logger.info(f"Total: {total_processed} successful, {total_failed} failed")

    await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
