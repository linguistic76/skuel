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

    # Re-embed stale nodes (edited after last embed, or older embedding version);
    # a content-hash fine filter skips entities whose text is actually unchanged
    uv run python scripts/generate_embeddings_batch.py --stale

    # One-shot hash rollout (zero API calls): stamp embedding_text_hash onto
    # already-embedded, version-current, non-drifted entity nodes
    uv run python scripts/generate_embeddings_batch.py --stamp-hashes

    # Full-corpus freshness audit (timestamp-free): hash-check every embedded
    # node against its current text, re-embed only real mismatches
    uv run python scripts/generate_embeddings_batch.py --audit

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
  as the worker's chunk batches. Chunk staleness is version-mismatch only: a
  re-chunk preserves unchanged chunks (embedding kept) and resets changed ones
  to embedding NULL, which the default coverage mode picks up — there is no
  drift state for chunks
- Processes in batches of 25
- Graceful error handling - logs failures but continues processing

COST ESTIMATION (ADR-068, text-embedding-3-small):
- Typical entity: ~200 tokens
- 1000 entities: well under $0.01
"""

import argparse
import asyncio
from typing import Any

# Label maps + per-label scope filters live in the retrievability module —
# the coverage gauge and this backfill share ONE source, so the gauge's
# missing counts and the remedy's candidate queries can never drift apart.
from core.services.embeddings.retrievability import (
    CONTENT_CHUNK_LABEL,
    EMBEDDABLE_LABELS,
    LABEL_EXTRA_FILTERS,
)
from core.services.embeddings_service import EMBEDDING_VERSION, EmbeddingsService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.logging import get_logger

logger = get_logger("skuel.batch_embeddings")


def _label_scope_clause(label: str) -> str:
    """The label's extra AND clause, or empty when the label is unscoped."""
    extra = LABEL_EXTRA_FILTERS.get(label)
    return f"\n      AND {extra}" if extra else ""


def build_candidate_query(label: str, stale: bool, audit: bool = False) -> str:
    """
    Cypher selecting one label's embedding candidates.

    Default: nodes with no embedding (coverage backfill). --stale: embedded
    nodes whose vector no longer matches the node — content edited after the
    last embed, or a model-version mismatch (NULL version counts as a
    mismatch). ``updated_at`` passes through ``datetime()`` because its
    storage type is writer-decided (some writers persist ISO strings, some
    native datetimes — both exist in the live graph): a bare ``<`` between
    DATETIME and STRING is null in Cypher and would silently skip those nodes.

    --audit: EVERY embedded node, no timestamp/version pre-filter — the
    content-hash fine filter downstream does all the work. Catches silent-pin
    states the --stale predicate is blind to (a raced store leaves
    embedding_updated_at AHEAD of updated_at) plus missed publishes and
    field-map drift.
    """
    if audit:
        predicate = "n.embedding IS NOT NULL"
    elif stale:
        predicate = """n.embedding IS NOT NULL AND (
        n.embedding_version IS NULL
        OR n.embedding_version <> $current_version
        OR (n.updated_at IS NOT NULL AND n.embedding_updated_at < datetime(n.updated_at))
    )"""
    else:
        predicate = "n.embedding IS NULL"
    return f"""
    MATCH (n:{label})
    WHERE {predicate}{_label_scope_clause(label)}
    RETURN n.uid as uid, properties(n) as props
    """


async def generate_embeddings_batch(
    driver: Any,
    embeddings_service: EmbeddingsService,
    label: str,
    batch_size: int = 25,
    max_batches: int | None = None,
    stale: bool = False,
    audit: bool = False,
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
        audit: Hash-audit every embedded node (timestamp-free) and re-embed
            mismatches — supersedes ``stale`` when both are set

    Returns:
        Stats dict with counts of processed, successful, and failed nodes
    """
    mode = "hash audit" if audit else ("stale re-embedding" if stale else "embedding generation")
    logger.info(f"Starting batch {mode} for {label}")

    entity_type = EMBEDDABLE_LABELS.get(label)
    if entity_type is None:
        logger.error(f"Unsupported label: {label} (supported: {', '.join(EMBEDDABLE_LABELS)})")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    # Full properties feed build_embedding_text
    query = build_candidate_query(label, stale, audit)
    params = {"current_version": EMBEDDING_VERSION} if stale and not audit else {}

    result = await driver.execute_query(query, params)
    records = result.records

    if not records:
        logger.info(f"No {label} nodes need embeddings")
        return {"label": label, "total": 0, "processed": 0, "successful": 0, "failed": 0}

    # Same text recipe as the event-driven path; skip content-less nodes
    candidates = [(r["uid"], build_embedding_text(entity_type, r["props"])) for r in records]
    skipped = [uid for uid, text in candidates if not text]
    candidates = [(uid, text) for uid, text in candidates if text]

    # Content-hash fine filter (--stale and --audit): the Cypher predicate
    # can't compute the current text hash (text is built in Python), so it
    # stays the coarse filter — here the hash drops candidates whose vector
    # already matches the current text (force re-ingests bump updated_at
    # without changing content). verify_fresh_embeddings owns the semantics
    # (version outranks hash) and touches the fresh nodes' embedding_updated_at
    # so they leave the coarse filter. Fails OPEN on a read error.
    if (stale or audit) and candidates:
        fresh_result = await embeddings_service.verify_fresh_embeddings(dict(candidates))
        if fresh_result.is_error:
            if audit:
                # Audit selects EVERY embedded node — the fine filter IS the
                # audit. Failing open here would re-embed the whole corpus, so
                # audit fails CLOSED instead (bail, re-run when reads work).
                # The aborted flag keeps the bail-out visible in main()'s
                # summary/exit code — zeroed stats alone would read as success.
                logger.error(
                    f"Freshness read failed — aborting {label} audit: "
                    f"{fresh_result.expect_error().message}"
                )
                return {
                    "label": label,
                    "total": 0,
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "aborted": True,
                }
            logger.warning(
                f"Freshness fine-filter failed — re-embedding all candidates: "
                f"{fresh_result.expect_error().message}"
            )
        elif fresh_result.value:
            fresh = fresh_result.value
            candidates = [(uid, text) for uid, text in candidates if uid not in fresh]
            logger.info(
                f"{len(fresh)} {label} embeddings verified fresh by text hash (touched, skipped)"
            )

    total = len(candidates)
    noun = (
        "hash-mismatched embeddings"
        if audit
        else ("stale embeddings" if stale else "nodes without embeddings")
    )
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

        # Store through the service so version/model/hash metadata matches the worker path
        for (uid, text), embedding in zip(batch, embeddings, strict=True):
            store_result = await embeddings_service.store_embedding_with_metadata(
                uid=uid, label=label, embedding=embedding, text=text
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


async def stamp_entity_hashes(
    driver: Any,
    embeddings_service: EmbeddingsService,
    label: str,
) -> dict[str, Any]:
    """
    One-shot hash rollout: stamp embedding_text_hash onto pre-hash nodes.

    Nodes embedded before the hash existed can't recover what text produced
    their vector — but a vector that is version-current and has no timestamp
    drift provably matches the node's CURRENT text, so hashing that text is
    sound (the drift guard lives in the backend write, re-checked there).
    Zero API calls; nodes failing the guards keep a null hash and self-heal
    through the normal re-embed paths.

    Chunks need no stamping: store_chunk_embeddings has always written
    embedding_source_text, which IS their freshness signal.
    """
    logger.info(f"Stamping embedding text hashes for {label}")

    entity_type = EMBEDDABLE_LABELS.get(label)
    if entity_type is None:
        logger.error(f"Unsupported label: {label} (supported: {', '.join(EMBEDDABLE_LABELS)})")
        return {"label": label, "total": 0, "stamped": 0}

    # Candidate pre-selection mirrors the backend write's guards (which
    # re-check them); same datetime() coercion as the --stale predicate —
    # updated_at's storage type is writer-decided.
    query = f"""
    MATCH (n:{label})
    WHERE n.embedding IS NOT NULL
      AND n.embedding_version = $current_version
      AND n.embedding_text_hash IS NULL
      AND NOT (n.updated_at IS NOT NULL AND n.embedding_updated_at < datetime(n.updated_at)){_label_scope_clause(label)}
    RETURN n.uid as uid, properties(n) as props
    """
    result = await driver.execute_query(query, {"current_version": EMBEDDING_VERSION})
    records = result.records

    if not records:
        logger.info(f"No {label} nodes need hash stamping")
        return {"label": label, "total": 0, "stamped": 0}

    # Same text recipe as every embed path; textless nodes can't be stamped
    texts = {
        r["uid"]: text for r in records if (text := build_embedding_text(entity_type, r["props"]))
    }
    skipped = len(records) - len(texts)
    if skipped:
        logger.info(f"{skipped} {label} nodes skipped: no embeddable text")

    stamp_result = await embeddings_service.stamp_embedding_hashes(label, texts)
    if stamp_result.is_error:
        logger.error(f"Hash stamping failed for {label}: {stamp_result.expect_error()}")
        return {"label": label, "total": len(texts), "stamped": 0}

    stamped = stamp_result.value
    logger.info(f"Stamped {stamped}/{len(texts)} {label} hashes")
    return {"label": label, "total": len(texts), "stamped": stamped}


async def generate_chunk_embeddings(
    driver: Any,
    embeddings_service: EmbeddingsService,
    content_adapter: Any,
    batch_size: int = 25,
    max_batches: int | None = None,
    stale: bool = False,
    audit: bool = False,
) -> dict[str, Any]:
    """
    Generate embeddings for ContentChunk nodes — the chunk backstop (ADR-074).

    Default: chunks with no embedding (e.g. created by a sync whose queued
    events were lost, or reset by a re-chunk whose text changed). --stale:
    chunks whose embedding_version mismatches the current EMBEDDING_VERSION
    (NULL counts as a mismatch). There is no updated_at drift predicate,
    unlike entities: a re-chunk wipes a changed chunk's embedding back to
    NULL (store_content_with_chunks), which the default mode covers.
    --audit: chunks whose stored embedding_source_text (the text the vector
    was generated from) no longer equals the node's context_window, OR whose
    embedding_version mismatches (version outranks text, ADR-074 §8) — the
    chunk equivalent of the entity hash audit, pure Cypher (both texts live
    on the node).

    Embeds context_window and stores through the content adapter — the exact
    recipe + storage path of the worker's chunk batches (one recipe, two
    triggers).
    """
    mode = "hash audit" if audit else ("stale re-embedding" if stale else "embedding generation")
    logger.info(f"Starting batch chunk {mode}")

    if audit:
        # Version outranks text (ADR-074 §8): a version-mismatched chunk is
        # stale even when its source text still matches — same semantics the
        # entity audit inherits from verify_fresh_embeddings.
        predicate = """c.embedding IS NOT NULL AND (
        c.embedding_source_text IS NULL OR c.embedding_source_text <> c.context_window
        OR c.embedding_version IS NULL OR c.embedding_version <> $current_version
    )"""
        params: dict[str, Any] = {"current_version": EMBEDDING_VERSION}
    elif stale:
        predicate = """c.embedding IS NOT NULL AND (
        c.embedding_version IS NULL OR c.embedding_version <> $current_version
    )"""
        params = {"current_version": EMBEDDING_VERSION}
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
    MATCH (c:{CONTENT_CHUNK_LABEL})
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
            texts=[text for _, text in batch],
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
        "label": CONTENT_CHUNK_LABEL,
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
            "version mismatch only — changed chunks reset to embedding NULL and "
            "the default mode covers them) instead of filling missing embeddings. "
            "A content-hash fine filter skips entities whose text is actually "
            "unchanged. Complements the default mode (default = nodes with no "
            "embedding, --stale = drifted ones)"
        ),
    )
    parser.add_argument(
        "--stamp-hashes",
        action="store_true",
        help=(
            "One-shot hash rollout: write embedding_text_hash (sha256 of the "
            "current embedding text) onto already-embedded, version-current, "
            "non-drifted entity nodes WITHOUT re-embedding. Zero API calls. "
            "Chunks never need this (embedding_source_text is their signal)."
        ),
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help=(
            "Full-corpus freshness audit, timestamp-free: check EVERY embedded "
            "node's stored hash (entities) / source text (chunks) against its "
            "current text and re-embed mismatches. Catches silent-pin states "
            "--stale is blind to (raced stores leave embedding_updated_at ahead "
            "of updated_at), missed publishes, and field-map drift. Costs one "
            "freshness read per corpus; API spend only on real mismatches."
        ),
    )

    args = parser.parse_args()
    exclusive_modes = [args.stale, args.stamp_hashes, args.audit]
    if sum(exclusive_modes) > 1:
        parser.error("--stale, --stamp-hashes, and --audit are mutually exclusive")

    # Bootstrap services
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = conn.connect()

    # Create embeddings service (inference client behind a port — W1).
    # The factory is the provider chokepoint (ADR-068); a missing API key
    # raises ValueError = the "not available" signal.
    from adapters.external.embeddings import create_embedding_client
    from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    try:
        embedding_client = create_embedding_client()
    except ValueError as e:
        # Exit nonzero: this script is the canonical coverage remedy
        # (./dev embed-backfill), and a missing key is exactly the gap class
        # the gauge reports — a zero exit here would let automation treat an
        # unrepaired gap as repaired (Codex #1068 P2).
        logger.error(f"❌ Embedding client not available - cannot generate embeddings: {e}")
        raise SystemExit(1) from e

    embeddings_service = EmbeddingsService(
        backend=EmbeddingsBackend(executor=Neo4jQueryExecutor(driver)),
        embedding_client=embedding_client,
    )

    # All embeddable labels + chunks, a specific entity label, or chunks only
    if args.label is None:
        entity_labels = list(EMBEDDABLE_LABELS)
        include_chunks = True
    elif args.label == CONTENT_CHUNK_LABEL:
        entity_labels = []
        include_chunks = True
    else:
        entity_labels = [args.label]
        include_chunks = False

    if args.stamp_hashes:
        # Hash rollout is entity-only and API-free — separate flow, own summary
        logger.info(f"\n{'=' * 60}")
        logger.info("Embedding Text Hash Stamping (no API calls)")
        logger.info(f"{'=' * 60}\n")

        stamp_stats = [
            await stamp_entity_hashes(driver, embeddings_service, label) for label in entity_labels
        ]

        logger.info(f"\n{'=' * 60}")
        logger.info("Summary")
        logger.info(f"{'=' * 60}\n")
        for stats in stamp_stats:
            logger.info(f"{stats['label']}: {stats['stamped']}/{stats['total']} stamped")
        logger.info(f"\n✅ Hash stamping complete: {sum(s['stamped'] for s in stamp_stats)} nodes")

        await driver.close()
        return

    mode_suffix = " (hash audit)" if args.audit else (" (stale re-embed)" if args.stale else "")
    logger.info(f"\n{'=' * 60}")
    logger.info("Batch Embedding Generation" + mode_suffix)
    logger.info(f"{'=' * 60}\n")
    logger.info(
        f"Labels: {', '.join(entity_labels + ([CONTENT_CHUNK_LABEL] if include_chunks else []))}"
    )
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
            audit=args.audit,
        )

        all_stats.append(stats)

        # Small delay between entity types
        await asyncio.sleep(2)

    if include_chunks:
        from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing {CONTENT_CHUNK_LABEL}")
        logger.info(f"{'=' * 60}\n")

        chunk_stats = await generate_chunk_embeddings(
            driver=driver,
            embeddings_service=embeddings_service,
            content_adapter=Neo4jContentAdapter(conn),
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            stale=args.stale,
            audit=args.audit,
        )
        all_stats.append(chunk_stats)

    # Print summary
    logger.info(f"\n{'=' * 60}")
    logger.info("Summary")
    logger.info(f"{'=' * 60}\n")

    total_processed = sum(s["successful"] for s in all_stats)
    total_failed = sum(s["failed"] for s in all_stats)
    aborted_labels = [s["label"] for s in all_stats if s.get("aborted")]

    for stats in all_stats:
        suffix = (
            " — ABORTED (freshness read failed, nothing verified)" if stats.get("aborted") else ""
        )
        logger.info(
            f"{stats['label']}: {stats['successful']}/{stats['total']} successful "
            f"({stats['failed']} failed){suffix}"
        )

    await driver.close()

    if aborted_labels:
        logger.error(
            f"\n❌ Audit incomplete — aborted labels: {', '.join(aborted_labels)}. "
            "Re-run when Neo4j freshness reads work."
        )
        raise SystemExit(1)

    if total_failed:
        # Same honesty contract as the aborted-audit exit: failures already
        # logged per batch above; the remedy must not report success while
        # gaps remain (Codex #1068 P2).
        logger.error(
            f"\n❌ Batch embedding generation incomplete: {total_processed} successful, "
            f"{total_failed} failed — see per-batch errors above and re-run."
        )
        raise SystemExit(1)

    logger.info("\n✅ All batch embedding generation complete")
    logger.info(f"Total: {total_processed} successful, {total_failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
