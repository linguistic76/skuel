#!/usr/bin/env python3
"""Ingest a canon reference book into :ReferenceChunk nodes, in-process.

The admin entry point for Phase 2 of the canon journaling companion — the
SECOND, walled ingest door. Reads a cleaned ``0vault/Resources/*.md`` book,
chunks it (prose-tuned), persists :ReferenceChunk nodes under a PRE-EXISTING
Resource, and (FULL tier) embeds them onto their OWN vector index
(``referencechunk_embedding_idx``) — structurally invisible to SearchRouter.

The Resource must already exist: this door validates and fails if absent; it
never creates Resources (a governed curriculum-ingestion concern).

Embedding freshness (ADR-074): the embedding worker is subscribed BEFORE the
ingest and drained in-process afterward, so the ReferenceChunkEmbeddingRequested
event embeds right here — no follow-up command. In CORE tier (or no API key)
there is no worker and the event is a no-op: chunks are written (shelf
membership holds), vectors fill on a later FULL run.

Usage:
    uv run python scripts/ingest_canon_book.py \\
        "$INGESTION_PATH/Resources/0 Hyper Media Systems.md" \\
        --resource-uid resource.hypermedia-systems

    # Chunks only, no embeddings (skip the worker even on FULL):
    uv run python scripts/ingest_canon_book.py <book.md> --no-embed
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path


def _resource_uid_from_frontmatter(markdown_text: str) -> str | None:
    """Read ``resource_uid:`` from a leading YAML frontmatter block, if present."""
    if not markdown_text.startswith("---"):
        return None
    end = markdown_text.find("\n---", 3)
    if end == -1:
        return None
    block = markdown_text[3:end]
    match = re.search(r'^\s*resource_uid:\s*"?([^"\n]+)"?\s*$', block, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


async def run_ingest(book_md: Path, resource_uid: str | None, no_embed: bool) -> int:
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j.neo4j_connection import get_connection
    from adapters.persistence.neo4j.neo4j_reference_chunk_adapter import (
        Neo4jReferenceChunkAdapter,
    )
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.services.ingestion.reference_ingestion import ReferenceIngestionService
    from services_bootstrap import compose_services

    if not book_md.is_file():
        print(f"ERROR: book file not found: {book_md}", file=sys.stderr)
        return 1

    markdown_text = book_md.read_text(encoding="utf-8")
    resolved_uid = resource_uid or _resource_uid_from_frontmatter(markdown_text)
    if not resolved_uid:
        print(
            "ERROR: no Resource UID — pass --resource-uid or add a "
            "`resource_uid:` frontmatter line to the book.",
            file=sys.stderr,
        )
        return 1

    print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        event_bus = InMemoryEventBus()
        composed = await compose_services(adapter, event_bus)
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1

        # None when CORE tier / no API key — chunks-only, fail-soft.
        worker = composed.value.embedding_worker
        resource_service = composed.value.resource

        # Embed only when a worker exists to drain the event. Injecting event_bus
        # without a subscriber would publish a one-shot ReferenceChunkEmbeddingRequested
        # that no one drains — lost, while the report falsely claims embeddings were
        # requested. Gate the bus on the SAME condition as subscribe()/drain() below.
        embed = worker is not None and not no_embed

        reference_chunk_adapter = Neo4jReferenceChunkAdapter(get_connection())
        ingest = ReferenceIngestionService(
            reference_chunk_adapter,
            event_bus=(event_bus if embed else None),
            resource_service=resource_service,
        )

        if embed and worker is not None:
            # Subscribe BEFORE the ingest so its published event lands in the
            # worker's queue; drain() below processes it in-process.
            worker.subscribe()

        print(f"Ingesting {book_md.name} → {resolved_uid} ...")
        report_result = await ingest.ingest_book(resolved_uid, markdown_text)

        # Drain BEFORE the error check so any queued embeddings are not lost.
        if embed and worker is not None:
            print("\nDraining embedding events in-process ...")
            drained = await worker.drain()
            print(f"  chunk parents dequeued: {drained['chunk_parents']} (includes retry passes)")
        elif no_embed:
            print("\n(--no-embed: chunks written, no embeddings requested)")
        else:
            print("\n(no embedding worker — CORE tier or embeddings unavailable; chunks only)")

        if report_result.is_error:
            print(f"ERROR: ingest failed: {report_result.expect_error()}", file=sys.stderr)
            return 1

        report = report_result.value
        print("\n=== ReferenceIngestReport ===")
        print(f"  resource_uid:    {report.resource_uid}")
        print(f"  chunks_written:  {report.chunks_written}")
        print(f"  embed_requested: {report.embed_requested}")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a canon reference book into :ReferenceChunk nodes."
    )
    parser.add_argument("book_md", type=Path, help="Path to the cleaned book .md file")
    parser.add_argument(
        "--resource-uid",
        help="Explicit Resource UID (overrides frontmatter `resource_uid:`).",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Write chunks only; skip embedding requests even on FULL tier.",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(run_ingest(args.book_md, args.resource_uid, args.no_embed)))


if __name__ == "__main__":
    main()
