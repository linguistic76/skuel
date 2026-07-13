"""
Neo4j Reference Chunk Adapter
=============================

Persists the (Resource)-[:HAS_REFERENCE_CHUNK]->(ReferenceChunk) subtree — the
canon reference-book ingest door's SECOND, walled chunk pipeline (Phase 2 of
the canon journaling companion). Distinct from the curriculum
:ContentChunk subtree so canon vectors land on their OWN index
(``referencechunk_embedding_idx``) and stay structurally invisible to
SearchRouter, which reads only ``contentchunk_embedding_idx``.

There is NO intermediate :Content node: the book body's source of truth is the
vault ``.md`` file; only retrieval chunks are stored here. Shelf membership is
emergent — a Resource is "on the shelf" iff it has :ReferenceChunk nodes.

The chunk-embedding methods (``get_chunk_embedding_freshness``,
``store_chunk_embeddings``) deliberately mirror ``Neo4jContentAdapter``'s
names/shapes so the shared ``EmbeddingBackgroundWorker`` routes to this adapter
by a one-object swap.
"""

__version__ = "1.0"


from typing import Any

from core.models.ps_content.content_chunks import ContentChunk
from core.ports.query_types import ReferenceChunkHit, ShelvedBook
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

logger = get_logger(__name__)


class Neo4jReferenceChunkAdapter:
    """
    Neo4j adapter for the Resource/ReferenceChunk subtree.

    Same constructor contract as ``Neo4jContentAdapter`` (single Neo4j
    connection). Holds ALL Cypher for the reference-chunk pipeline (SKUEL021 —
    ``core/`` stays Cypher-free).
    """

    def __init__(self, neo4j_connection) -> None:
        """
        Initialize with Neo4j connection.

        Args:
            neo4j_connection: Neo4j database connection
        """
        self.neo4j = neo4j_connection

    async def store_reference_chunks(self, resource_uid: str, chunks: list[ContentChunk]) -> bool:
        """
        Store a canon book's reference chunks under its Resource.

        Delete-then-create in ONE transaction (mirrors
        ``Neo4jContentAdapter.store_content_with_chunks`` atomicity): a failure
        anywhere rolls the delete back, so a re-ingest can never leave the
        shelf half-populated. Embedding idempotency (ADR-074 §8) is preserved
        by carry-over, not node reuse: before deleting, the old chunks'
        embedding fields are read, and a new chunk whose ``context_window``
        matches an old chunk's ``embedding_source_text`` inherits that
        embedding — the worker's freshness pre-check then skips re-embedding it.

        The Resource is MATCHed (not MERGEd): a missing Resource matches
        nothing, so 0 chunks are created and this returns False. The ingest
        service fails fast on not-found before reaching here; this is a
        belt-and-braces guard, not the primary existence check.

        Args:
            resource_uid: The pre-existing Resource UID (canon book)
            chunks: Prose-tuned reference chunks to persist

        Returns:
            True if all chunks were created, False on mismatch or error
        """
        try:
            # Embedding carry-over map: source_text -> embedding fields of the
            # outgoing chunk set. Read BEFORE the delete below.
            carry_over: dict[str, dict[str, Any]] = {}
            old_rows = await self.neo4j.execute_query(
                """
                MATCH (r:Resource {uid: $uid})-[:HAS_REFERENCE_CHUNK]->(c:ReferenceChunk)
                WHERE c.embedding IS NOT NULL
                RETURN c.embedding_source_text AS source_text,
                       c.embedding AS embedding,
                       c.embedding_version AS version,
                       c.embedding_model AS model,
                       c.embedding_updated_at AS updated_at
                """,
                {"uid": resource_uid},
            )
            for row in old_rows or []:
                source_text = row.get("source_text")
                if source_text and source_text not in carry_over:
                    carry_over[source_text] = dict(row)

            chunk_rows = []
            for i, chunk in enumerate(chunks):
                inherited = carry_over.get(chunk.context_window)
                chunk_rows.append(
                    {
                        "chunk_uid": chunk.chunk_id,
                        "chunk_type": chunk.chunk_type.value,
                        "text": chunk.text,
                        "context_window": chunk.context_window,
                        "heading": chunk.heading,
                        "section_path": chunk.section_path,
                        "chunking_version": chunk.chunking_version,
                        "sequence": i,
                        "embedding": inherited["embedding"] if inherited else None,
                        "embedding_version": inherited["version"] if inherited else None,
                        "embedding_model": inherited["model"] if inherited else None,
                        "embedding_updated_at": (inherited["updated_at"] if inherited else None),
                        "embedding_source_text": (chunk.context_window if inherited else None),
                    }
                )

            # Delete + recreate in ONE statement = one transaction. MATCH (not
            # MERGE) on the Resource: a missing Resource yields no rows, so
            # UNWIND creates nothing and `created` is 0 (treated as not-found).
            chunk_result = await self.neo4j.execute_query(
                """
                MATCH (r:Resource {uid: $resource_uid})
                OPTIONAL MATCH (r)-[:HAS_REFERENCE_CHUNK]->(old:ReferenceChunk)
                DETACH DELETE old
                WITH DISTINCT r
                UNWIND $chunks AS row
                CREATE (c:ReferenceChunk {uid: row.chunk_uid})
                SET c.created_at = datetime(),
                    c.chunk_type = row.chunk_type,
                    c.text = row.text,
                    c.context_window = row.context_window,
                    c.heading = row.heading,
                    c.section_path = row.section_path,
                    c.chunking_version = row.chunking_version,
                    c.embedding = row.embedding,
                    c.embedding_version = row.embedding_version,
                    c.embedding_model = row.embedding_model,
                    c.embedding_updated_at = row.embedding_updated_at,
                    c.embedding_source_text = row.embedding_source_text
                CREATE (r)-[rel:HAS_REFERENCE_CHUNK]->(c)
                SET rel.sequence = row.sequence
                RETURN count(c) AS created
                """,
                {"resource_uid": resource_uid, "chunks": chunk_rows},
            )
            created = int(chunk_result[0]["created"]) if chunk_result else 0
            if created != len(chunks):
                logger.error(
                    f"Reference chunk create mismatch for {resource_uid}: expected "
                    f"{len(chunks)}, created {created} (Resource missing?)"
                )
                return False
            if chunks:
                kept = sum(1 for row in chunk_rows if row["embedding"] is not None)
                logger.info(
                    f"Stored {created} reference chunks for {resource_uid} "
                    f"({kept} embeddings carried over)"
                )
            return True

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to store reference chunks for {resource_uid}: {e}")
            return False

    async def search_reference_chunks(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
        resource_uids: list[str] | None = None,
    ) -> list[ReferenceChunkHit]:
        """Vector-search the canon shelf for passages nearest the query embedding.

        Two branches on ``resource_uids``:

        - ``None`` (whole shelf): targets the walled
          ``referencechunk_embedding_idx`` (NOT ``contentchunk_embedding_idx``)
          and joins each hit back to its owning :Resource for the book title. A
          ``candidate_limit`` of ``2 * limit`` widens the neighbor pool so the
          ``threshold`` cut still leaves ``limit`` survivors in the common case
          (mirrors ``VectorSearchBackend.semantic_search_chunks``' unscoped 2x
          pass).
        - a list (scoped): scores every chunk under the given Resources with an
          exact ``vector.similarity.cosine`` scan — no index, so no recall loss
          from over-fetch + post-filter. Cost tracks chunks in the *cited* books
          (~105/book today), not shelf size, so the exact scan is the
          shelf-growth-proof branch. ``[]`` short-circuits to no hits (empty
          scope ≠ whole shelf).

        This adapter holds the ONLY reads against the reference vectors —
        keeping both branches here, off the shared ``VectorSearchBackend``, is
        the structural guarantee that canon stays invisible to SearchRouter
        (frozen by ``tests/unit/adapters/test_reference_chunk_isolation.py``).

        Fails OPEN (empty list on read error) — a canon miss must degrade the
        caller's session to a normal one, never break it.

        Args:
            query_embedding: The query text's embedding vector.
            limit: Maximum passages to return.
            threshold: Minimum cosine similarity for a passage to count.
            resource_uids: ``None`` = whole shelf; list = scoped to those
                Resources; ``[]`` = empty scope, returns ``[]``.

        Returns:
            ``ReferenceChunkHit`` rows ordered by descending similarity. Empty
            on no match, empty scope, or error.
        """
        if resource_uids is not None and not resource_uids:
            return []

        if resource_uids is None:
            query = """
            CALL db.index.vector.queryNodes(
                'referencechunk_embedding_idx',
                $candidate_limit,
                $query_embedding
            ) YIELD node AS chunk, score
            WHERE score >= $threshold
            MATCH (r:Resource)-[rel:HAS_REFERENCE_CHUNK]->(chunk)
            RETURN chunk.uid AS chunk_uid,
                   chunk.text AS text,
                   chunk.context_window AS context_window,
                   chunk.heading AS heading,
                   chunk.section_path AS section_path,
                   rel.sequence AS sequence,
                   score AS similarity_score,
                   r.uid AS resource_uid,
                   r.title AS book_title
            ORDER BY score DESC
            LIMIT $limit
            """
            params: dict[str, Any] = {
                "query_embedding": query_embedding,
                "candidate_limit": limit * 2,
                "threshold": threshold,
                "limit": limit,
            }
        else:
            # Exact cosine over the scoped set — no candidate_limit: a full
            # scan of the in-scope chunks needs no over-fetch (that 2x pass
            # exists only to survive the index's threshold cut).
            query = """
            MATCH (r:Resource)-[rel:HAS_REFERENCE_CHUNK]->(chunk:ReferenceChunk)
            WHERE r.uid IN $resource_uids AND chunk.embedding IS NOT NULL
            WITH chunk, r, rel,
                 vector.similarity.cosine(chunk.embedding, $query_embedding) AS score
            WHERE score >= $threshold
            RETURN chunk.uid AS chunk_uid,
                   chunk.text AS text,
                   chunk.context_window AS context_window,
                   chunk.heading AS heading,
                   chunk.section_path AS section_path,
                   rel.sequence AS sequence,
                   score AS similarity_score,
                   r.uid AS resource_uid,
                   r.title AS book_title
            ORDER BY score DESC
            LIMIT $limit
            """
            params = {
                "query_embedding": query_embedding,
                "resource_uids": resource_uids,
                "threshold": threshold,
                "limit": limit,
            }

        try:
            result = await self.neo4j.execute_query(query, params)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Reference chunk vector search failed: {e}")
            return []

        def to_hit(row: dict[str, Any]) -> ReferenceChunkHit:
            return ReferenceChunkHit(
                chunk_uid=row["chunk_uid"],
                text=row["text"],
                context_window=row.get("context_window"),
                heading=row.get("heading"),
                section_path=row.get("section_path"),
                sequence=(int(row["sequence"]) if row.get("sequence") is not None else None),
                similarity_score=float(row["similarity_score"]),
                resource_uid=row["resource_uid"],
                book_title=row["book_title"] or "",
            )

        hits = [to_hit(row) for row in (result or [])]
        if resource_uids is not None:
            # Growth tripwire: data for a future measurement pass on the exact
            # scan (P3 escape hatch = chunk-count threshold -> index fallback).
            logger.debug(
                "Scoped canon search: %d resource(s) in scope, %d hit(s)",
                len(resource_uids),
                len(hits),
            )
        return hits

    async def list_shelved_books(self) -> list[ShelvedBook]:
        """List every shelved book (Resource with ≥1 :ReferenceChunk), title-ordered.

        The shelf's membership read, distinct from the vector search above: no
        embedding, just the distinct owning :Resource of any reference chunk.
        Powers the journal discussion composer's per-book source picker. Fails
        OPEN (empty list on read error) so a missing shelf degrades to no picker
        rather than breaking the page.
        """
        query = """
        MATCH (r:Resource)-[:HAS_REFERENCE_CHUNK]->(:ReferenceChunk)
        RETURN DISTINCT r.uid AS resource_uid, r.title AS title
        ORDER BY title
        """
        try:
            result = await self.neo4j.execute_query(query, {})
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to list shelved books: {e}")
            return []
        return [
            ShelvedBook(resource_uid=row["resource_uid"], title=row["title"] or "")
            for row in (result or [])
        ]

    async def get_chunk_embedding_freshness(self, chunk_uids: list[str]) -> list[dict[str, Any]]:
        """
        Read the freshness triple (has_embedding, version, source_text) per chunk.

        Same name/shape as ``Neo4jContentAdapter.get_chunk_embedding_freshness``
        so the shared worker's freshness skip works unchanged — only the label
        differs (:ReferenceChunk). Fails OPEN (empty list on read error) so the
        caller skips nothing.

        Args:
            chunk_uids: Chunk UIDs to check

        Returns:
            One dict per existing chunk: uid, has_embedding, version, source_text
        """
        query = """
        MATCH (c:ReferenceChunk)
        WHERE c.uid IN $uids
        RETURN c.uid as uid,
               c.embedding IS NOT NULL as has_embedding,
               c.embedding_version as version,
               c.embedding_source_text as source_text
        """
        try:
            result = await self.neo4j.execute_query(query, {"uids": chunk_uids})
            return [dict(record) for record in result] if result else []
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to read reference chunk embedding freshness: {e}")
            return []

    async def store_chunk_embeddings(
        self,
        chunk_uids: list[str],
        embeddings: list[list[float]],
        version: str,
        model: str,
        texts: list[str],
    ) -> bool:
        """
        Store pre-generated embeddings on existing ReferenceChunk nodes.

        Same name/signature as ``Neo4jContentAdapter.store_chunk_embeddings``
        (the worker calls it identically after batch generation) — only the
        label differs. ``embedding_source_text`` is stamped from ``texts`` (the
        exact text each vector was generated from), matching the truthful-
        provenance design that lets a conflicting re-chunk self-heal.

        Args:
            chunk_uids: Chunk UIDs to update
            embeddings: Embedding vectors (same length as chunk_uids)
            version: Embedding version (EMBEDDING_VERSION from callers)
            model: Model name (e.g., "text-embedding-3-small")
            texts: Source text each embedding was generated from (same
                length/order as embeddings)

        Returns:
            True if every chunk was updated, False otherwise
        """
        try:
            if len(chunk_uids) != len(embeddings):
                logger.error(
                    f"Mismatch: {len(chunk_uids)} chunk UIDs but {len(embeddings)} embeddings"
                )
                return False

            query = """
            UNWIND $chunks as chunk_data
            MATCH (c:ReferenceChunk {uid: chunk_data.uid})
            SET c.embedding = chunk_data.embedding,
                c.embedding_version = $version,
                c.embedding_model = $model,
                c.embedding_updated_at = datetime(),
                c.embedding_source_text = chunk_data.source_text
            RETURN count(c) as updated_count
            """

            chunks_param = [
                {"uid": uid, "embedding": emb, "source_text": text}
                for uid, emb, text in zip(chunk_uids, embeddings, texts, strict=True)
            ]

            result = await self.neo4j.execute_query(
                query,
                {"chunks": chunks_param, "version": version, "model": model},
            )

            if result and len(result) > 0:
                updated_count: int = result[0]["updated_count"]
                logger.info(
                    f"✅ Stored embeddings for {updated_count}/{len(chunk_uids)} reference chunks "
                    f"(version={version}, model={model})"
                )
                return updated_count == len(chunk_uids)

            logger.warning("No reference chunks updated - chunks may not exist")
            return False

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to store reference chunk embeddings: {e}")
            return False

    async def delete_reference_chunks(self, resource_uid: str) -> bool:
        """
        Un-shelf a book: delete its whole reference-chunk subtree.

        Removes every :ReferenceChunk under the Resource (and its
        HAS_REFERENCE_CHUNK edges), dropping the emergent shelf membership. The
        Resource node itself is untouched (Resource lifecycle is a governed
        curriculum-ingestion concern).

        Args:
            resource_uid: The Resource UID to un-shelf

        Returns:
            True if any chunks were deleted, False if none existed or on error
        """
        query = """
        MATCH (r:Resource {uid: $uid})-[:HAS_REFERENCE_CHUNK]->(c:ReferenceChunk)
        DETACH DELETE c
        RETURN count(c) as deleted
        """
        try:
            result = await self.neo4j.execute_query(query, {"uid": resource_uid})
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to delete reference chunks for {resource_uid}: {e}")
            return False

        if result and len(result) > 0 and result[0]["deleted"] > 0:
            logger.info(f"Deleted reference chunk subtree for resource: {resource_uid}")
            return True

        logger.debug(f"No reference chunks to delete for: {resource_uid}")
        return False
