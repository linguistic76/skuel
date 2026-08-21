"""
Prerequisite-Candidate Backend
==============================

Read side of prerequisite-edge suggestions (Discovery Analytics PR 4).

Fetches Ku embeddings + existing Ku↔Ku edges so ``PrereqSuggestionService``
can compute candidate pairs in Python (pairwise cosine over ~121 Kus is
trivial in-process — no vector-index round-trips needed, and the candidate
band is MID-similarity 0.40-0.72, below the 0.72 "related concepts" knob).

This backend is READ-ONLY: the feature never writes to the graph — the only
write is the Edge YAML file the admin approves into the content vault
(``ContentVaultEdgeWriter``), which lands in the graph via content sync.

Like :SearchEvent's backend, this takes a Neo4jQueryExecutor directly
(InsightBackend precedent) — it reads across Kus rather than serving one
entity type's CRUD, so it does not extend UniversalNeo4jBackend.

Protocol: core/ports/curriculum_protocols.py PrereqSuggestionBackendOperations
See: /docs/roadmap/done/SEMANTIC_ANALYSIS_ROADMAP.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.ports.query_types import (
    KuEdgeRow,
    KuEmbeddingRow,
    to_ku_edge_rows,
    to_ku_embedding_rows,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class PrereqCandidateBackend:
    """Read-only backend for prerequisite-edge candidate generation."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def get_kus_with_embeddings(self) -> Result[list[KuEmbeddingRow]]:
        """All Kus that have a stored entity embedding (uid, title, summary, vector)."""
        result = await self._executor.execute_query(
            """
            MATCH (k:Ku)
            WHERE k.embedding IS NOT NULL
            RETURN k.uid AS uid,
                   k.title AS title,
                   coalesce(k.summary, k.description, '') AS summary,
                   k.embedding AS embedding
            """,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_ku_embedding_rows(result.value or []))

    async def get_ku_ku_edges(self) -> Result[list[KuEdgeRow]]:
        """All directed Ku→Ku relationships of any type (for pair exclusion)."""
        result = await self._executor.execute_query(
            """
            MATCH (a:Ku)-[r]->(b:Ku)
            RETURN a.uid AS from_uid, b.uid AS to_uid, type(r) AS rel_type
            """,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_ku_edge_rows(result.value or []))

    async def get_ku_titles(self, uids: list[str]) -> Result[dict[str, str]]:
        """Titles of the given Ku uids — doubles as the approve-time existence check."""
        result = await self._executor.execute_query(
            """
            MATCH (k:Ku)
            WHERE k.uid IN $uids
            RETURN k.uid AS uid, k.title AS title
            """,
            {"uids": uids},
        )
        if result.is_error:
            return Result.fail(result)
        titles: dict[str, str] = {}
        for record in result.value or []:
            uid = record.get("uid")
            if isinstance(uid, str):
                titles[uid] = str(record.get("title") or uid)
        return Result.ok(titles)
