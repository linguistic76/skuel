#!/usr/bin/env python3
"""One-shot READ-ONLY runtime verification for Askesis-canon PR-B.

Exercises the REAL retrieval stack against the live graph — real embedding
call, real scoped Cypher, real teaching block, real prompt append, real UI
renderer — scoped to the one shelved book (``resource.hypermedia-systems``).
No graph writes: the ``:ReferenceChunk`` count is asserted unchanged.

Interactive CLI (not production runtime) — print() is correct here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

SHELVED = "resource.hypermedia-systems"
QUESTION = "What is hypermedia, and how does HTML act as a hypermedia?"


async def main() -> int:
    from adapters.external.embeddings import create_embedding_client
    from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.neo4j_reference_chunk_adapter import (
        Neo4jReferenceChunkAdapter,
    )
    from core.services.canon import CanonRetrievalService
    from core.services.embeddings_service import EmbeddingsService

    conn = Neo4jConnection()
    driver = conn.connect()

    async def chunk_count() -> int:
        result = await driver.execute_query(
            "MATCH (:Resource {uid:$uid})-[:HAS_REFERENCE_CHUNK]->(c:ReferenceChunk) "
            "RETURN count(c) AS n",
            {"uid": SHELVED},
        )
        return int(result.records[0]["n"])

    before = await chunk_count()
    print(f"[setup] ReferenceChunk count for {SHELVED}: {before}")

    embeddings_service = EmbeddingsService(
        backend=EmbeddingsBackend(executor=Neo4jQueryExecutor(driver)),
        embedding_client=create_embedding_client(),
    )
    canon = CanonRetrievalService(
        reference_search=Neo4jReferenceChunkAdapter(conn),
        embeddings_service=embeddings_service,
    )

    failures: list[str] = []

    # ── 1. Scoped retrieval against the live shelf (the B2 call, verbatim) ──
    result = await canon.retrieve(QUESTION, resource_uids=[SHELVED])
    if result.is_error:
        failures.append(f"retrieve failed: {result.error}")
        ctx = None
    else:
        ctx = result.value
        print(f"[1] scoped retrieve → {len(ctx.passages)} passage(s)")
        if not ctx.has_passages:
            failures.append("no passage cleared min_score for an on-book question")
        for p in ctx.passages:
            print(f"    {p.similarity_score:.3f}  {p.citation_line()}")
            if p.resource_uid != SHELVED:
                failures.append(f"OUT-OF-SCOPE passage from {p.resource_uid}")

    # ── 2. Out-of-scope uid → empty (scope wall) ────────────────────────────
    miss = await canon.retrieve(QUESTION, resource_uids=["resource.transcend"])
    if miss.is_error:
        failures.append(f"out-of-scope retrieve errored: {miss.error}")
    elif miss.value.has_passages:
        failures.append("out-of-scope retrieve returned passages (scope leak)")
    else:
        print("[2] out-of-scope uid (resource.transcend, 0 chunks) → empty ✓")

    if ctx is not None and ctx.has_passages:
        # ── 3. Teaching block: citation + faithfulness contract ────────────
        block = ctx.to_teaching_block()
        failures.extend(
            f"teaching block missing: {needle!r}"
            for needle in (
                "## Readings for This Step",
                "Do not surrender the method",
                "never invent a passage, chapter, or section",
                "Hypermedia Systems",
            )
            if needle not in block
        )
        print("[3] teaching block carries citations + faithfulness contract ✓")

        # ── 4. Prompt append through the REAL ResponseGenerator seam ───────
        from core.models.enums import GuidanceMode
        from core.services.askesis.response_generator import ResponseGenerator

        generator = ResponseGenerator()
        generator._build_socratic_prompt = MagicMock(return_value="BASE")  # isolate the seam
        guidance = MagicMock()
        guidance.mode = GuidanceMode.SOCRATIC
        prompt = generator.build_guided_system_prompt(
            guidance, MagicMock(), MagicMock(), canon_context=ctx
        )
        if not (prompt.startswith("BASE") and "## Readings for This Step" in prompt):
            failures.append("build_guided_system_prompt did not append the teaching block")
        else:
            print("[4] build_guided_system_prompt appends the real teaching block ✓")

        # ── 5. UI: real sources → CanonSourcesBlock with Resource link ─────
        from html import escape

        from fasthtml.common import to_xml

        from ui.askesis.chat import render_assistant_message

        sources = ctx.sources()
        html = to_xml(render_assistant_message("answer", canon_sources=sources))
        link = f"/library/resources/get?uid={SHELVED}"
        if link not in html:
            failures.append(f"rendered message missing Resource link {link}")
        elif sources[0].locators and escape(sources[0].locators[0]) not in html:
            failures.append("rendered message missing the in-book locator")
        else:
            print(f"[5] render_assistant_message links {link} with locators ✓")

        empty_html = to_xml(render_assistant_message("answer"))
        if "/library/resources/get" in empty_html:
            failures.append("readings block rendered with no canon sources")
        else:
            print("[5b] no canon sources → no readings block (silent degrade) ✓")

    # ── 6. Read-only proof ──────────────────────────────────────────────────
    after = await chunk_count()
    if after != before:
        failures.append(f"ReferenceChunk count changed: {before} → {after}")
    else:
        print(f"[6] ReferenceChunk count unchanged ({after}) — read-only ✓")

    await conn.close()

    if failures:
        print("\n❌ FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n✅ PR-B canon grounding verified against the live graph (read-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
