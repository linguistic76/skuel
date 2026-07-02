"""
Batch Embedding Generation Script
==================================

The BACKSTOP of the embedding pipeline (ADR-074 §7): generates embeddings for
existing entities and content chunks that don't have them, or re-embeds ones
whose embedding has gone stale (--stale). Routine freshness is the event
pipeline — app-process worker loop, or the script-mode subscribe-then-drain in
vault_bridge_sync.py; this script recovers pre-existing gaps (CORE-tier
periods, events lost from the in-memory queue on an app restart).

Usage:
    # Backfill all entity types + content chunks
    uv run python scripts/generate_embeddings_batch.py

    # Specific entity label, or chunks only
    uv run python scripts/generate_embeddings_batch.py --label PathStep
    uv run python scripts/generate_embeddings_batch.py --label ContentChunk

    # Limit batches (for testing)
    uv run python scripts/generate_embeddings_batch.py --label Ku --max-batches 2

    # Re-embed stale nodes (edited after last embed, or older embedding version)
    uv run python scripts/generate_embeddings_batch.py --stale

The two modes stay separate so re-embedding — which re-spends API money on
existing vectors — is always an explicit choice: the default run embeds nodes
with no embedding yet (--stale deliberately skips them); --stale re-embeds
drifted ones.

ARCHITECTURE:
- Entities: EmbeddingsService for generation AND storage, so backfilled nodes
  carry the same version/model metadata the background worker writes; text via
  build_embedding_text (same field maps as the event-driven path)
- Chunks: embeds ContentChunk.context_window and stores through
  Neo4jContentAdapter.store_chunk_embeddings — the same recipe + storage path
  as the worker's chunk batches. Chunks are immutable (a re-chunk deletes and
  recreates them), so chunk staleness is version-mismatch only
- Processes in batches of 25
- Graceful error handling - logs failures but continues processing

COST ESTIMATION (ADR-068, text-embedding-3-small):
- Typical entity: ~200 tokens
- 1000 entities: well under $0.01
"""

import argparse
import asyncio
from typing import Any

from core.events.embedding_publisher import EMBEDDING_NODE_LABELS
from core.models.enums.entity_enums import EntityType
from core.services.embeddings_service import EMBEDDING_VERSION, EmbeddingsService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.logging import get_logger

logger = get_logger("skuel.batch_embeddings")

# Neo4j label → EntityType, inverted from the chokepoint's one label map —
# no hand-maintained mirror (the map itself is guarded against
# EMBEDDING_EVENT_TYPES drift by test_post_persist_embedding.py).
EMBEDDABLE_LABELS: dict[str, EntityType] = {
    label: entity_type for entity_type, label in EMBEDDING_NODE_LABELS.items()
}

CHUNK_LABEL = "ContentChunk"


def build_candidate_query(label: str, stale: bool) -> str:
    """
    Cypher selecting one label's embedding candidates.

    Default: nodes with no embedding (coverage backfill). --stale: embedded
    nodes whose vector no longer matches the node — content edited after the
    last embed, or a model-version mismatch (NULL version counts as a
    mismatch). ``updated_at`` passes through ``datetime()`` because its
    storage type is writer-decided (some writers persist ISO strings, some
    native datetimes — both exist in the live graph): a bare ``<`` between
    DATETIME and STRING is null in Cypher and would silently skip those nodes.
    """
    if stale:
        predicate = """n.embedding IS NOT NULL AND (
        n.embedding_version IS NULL
        OR n.embedding_version <> $current_version
        OR (n.updated_at IS NOT NULL AND n.embedding_updated_at < datetime(n.updated_at))
    )"""
    else:
        predicate = "n.embedding IS NULL"
    return f"""
    MATCH (n:{label})
    WHERE {predicate}
    RETURN n.uid as uid, properties(n) as props
    """


async def generate_embeddings_batch(
    driver: Any,
    embeddings_service: EmbeddingsService,
    label: str,
    batch_size: int = 25,
    max_batches: int | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    """
    Generate embeddings for all nodes of a given label.

    Args:
        driver: Neo4j driver instance
        embeddings_service: EmbeddingsService instance
        label: Node label (e.g., "Ku", "PathStep", "Task")
        batch_size: Number of nodes per batch (default: 25)
        max_batches: Limit number of batches for testing (default: None = all)
        stale: Re-embed stale nodes instead of filling missing ones

    Returns:
        Stats dict with counts of processed, successful, and failed nodes
    """
    mode = "stale re-embedding" if stale else "embedding generation"
    logger.info(f"Starting batch {mode} for {label}")

    entity_type = EMBEDDABLE_LABELS.get(label)
    if entity_type is None:
        logger.error(f"Unsupported label: {label} (supported: {', '.join(EMBEDDABLE_LABELS)})")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    # Full properties feed build_embedding_text
    query = build_candidate_query(label, stale)
    params = {"current_version": EMBEDDING_VERSION} if stale else {}

    result = await driver.execute_query(query, params)
    records = result.records

    if not records:
        logger.info(f"No {label} nodes need embeddings")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    # Same text recipe as the event-driven path; skip content-less nodes
    candidates = [(r["uid"], build_embedding_text(entity_type, r["props"])) for r in records]
    skipped = [uid for uid, text in candidates if not text]
    candidates = [(uid, text) for uid, text in candidates if text]

    total = len(candidates)
    noun = "stale embeddings" if stale else "nodes without embeddings"
    logger.info(
        f"Found {total} {label} {noun}"
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


async def generate_chunk_embeddings(
    driver: Any,
    embeddings_service: EmbeddingsService,
    content_adapter: Any,
    batch_size: int = 25,
    max_batches: int | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    """
    Generate embeddings for ContentChunk nodes — the chunk backstop (ADR-074).

    Default: chunks with no embedding (e.g. created by a sync whose queued
    events were lost). --stale: chunks whose embedding_version mismatches the
    current EMBEDDING_VERSION (NULL counts as a mismatch). Chunks are immutable
    — a re-chunk deletes and recreates them — so there is no updated_at drift
    predicate, unlike entities.

    Embeds context_window and stores through the content adapter — the exact
    recipe + storage path of the worker's chunk batches (one recipe, two
    triggers).
    """
    mode = "stale re-embedding" if stale else "embedding generation"
    logger.info(f"Starting batch chunk {mode}")

    if stale:
        predicate = """c.embedding IS NOT NULL AND (
        c.embedding_version IS NULL OR c.embedding_version <> $current_version
    )"""
        params: dict[str, Any] = {"current_version": EMBEDDING_VERSION}
    else:
        predicate = "c.embedding IS NULL"
        params = {}

    # Paged LIMIT-only loop, never SKIP: a successfully embedded chunk leaves
    # the predicate (embedding set / version current), so re-querying page one
    # always yields the next unprocessed rows — SKIP against a shrinking match
    # set would leap over candidates. Only one page of context windows is in
    # memory at a time. Textless chunks are excluded in Cypher, not Python:
    # they can never leave the predicate and would loop forever.
    query = f"""
    MATCH (c:{CHUNK_LABEL})
    WHERE {predicate}
      AND c.context_window IS NOT NULL AND c.context_window <> ''
    RETURN c.uid as uid, c.context_window as text
    LIMIT $limit
    """

    batches_processed = 0
    successful = 0
    failed = 0
    total = 0

    while True:
        if max_batches and batches_processed >= max_batches:
            logger.info(f"Reached max_batches limit ({max_batches}), stopping")
            break

        result = await driver.execute_query(query, {**params, "limit": batch_size})
        records = result.records
        if not records:
            break

        batch = [(r["uid"], r["text"]) for r in records]
        total += len(batch)
        batches_processed += 1
        logger.info(f"Processing chunk batch {batches_processed}: {len(batch)} chunks")

        embeddings_result = await embeddings_service.create_batch_embeddings(
            [text for _, text in batch]
        )
        if embeddings_result.is_error:
            # Failed rows stay in the predicate — bail out instead of
            # re-fetching the same page forever.
            logger.error(f"Chunk batch failed, stopping: {embeddings_result.expect_error()}")
            failed += len(batch)
            break

        stored = await content_adapter.store_chunk_embeddings(
            chunk_uids=[uid for uid, _ in batch],
            embeddings=embeddings_result.value,
            version=EMBEDDING_VERSION,
            model=embeddings_service.model,
        )
        if stored:
            successful += len(batch)
        else:
            # Same self-shrink guard: unstored rows would re-match immediately.
            logger.error(f"Failed to store chunk batch {batches_processed}, stopping")
            failed += len(batch)
            break

    if not total:
        logger.info("No chunks need embeddings")

    logger.info(
        f"Batch chunk embedding complete: {batches_processed} batches, "
        f"{successful} successful, {failed} failed"
    )
    return {
        "label": CHUNK_LABEL,
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
        help="Specific label to process (e.g., Ku, PathStep, Task, ContentChunk)",
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
    parser.add_argument(
        "--stale",
        action="store_true",
        help=(
            "Re-embed stale nodes (entities: embedding_updated_at < updated_at "
            f"or embedding_version != current {EMBEDDING_VERSION!r}; chunks: "
            "version mismatch only — chunks are immutable) instead of filling "
            "missing embeddings. Complements the default mode (default = nodes "
            "with no embedding, --stale = drifted ones)"
        ),
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

    # All embeddable labels + chunks, a specific entity label, or chunks only
    if args.label is None:
        entity_labels = list(EMBEDDABLE_LABELS)
        include_chunks = True
    elif args.label == CHUNK_LABEL:
        entity_labels = []
        include_chunks = True
    else:
        entity_labels = [args.label]
        include_chunks = False

    logger.info(f"\n{'=' * 60}")
    logger.info("Batch Embedding Generation" + (" (stale re-embed)" if args.stale else ""))
    logger.info(f"{'=' * 60}\n")
    logger.info(f"Labels: {', '.join(entity_labels + ([CHUNK_LABEL] if include_chunks else []))}")
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
            stale=args.stale,
        )

        all_stats.append(stats)

        # Small delay between entity types
        await asyncio.sleep(2)

    if include_chunks:
        from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing {CHUNK_LABEL}")
        logger.info(f"{'=' * 60}\n")

        chunk_stats = await generate_chunk_embeddings(
            driver=driver,
            embeddings_service=embeddings_service,
            content_adapter=Neo4jContentAdapter(conn),
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            stale=args.stale,
        )
        all_stats.append(chunk_stats)

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
