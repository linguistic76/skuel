"""Canon retrieval — ranked shelf passages for a query, with book attribution.

Reusable and domain-agnostic: "query text in, resonant canon passages + the books
they came from out". Journals is the first caller (voice-infusing FOUNDER Stage 2
/ Stage 3); the same capability is Askesis-ready later — nothing here knows about
journals.

FULL tier only: without an embeddings service there is no query vector, so
``retrieve`` fails and the caller degrades to a normal, canon-free response. The
read itself targets the walled reference index via
``ReferenceChunkSearchOperations`` — SearchRouter never sees it (ADR: canon
isolation, Phase 2).

Nothing is persisted (ADR-073): the returned ``CanonContext`` is ephemeral prompt
context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.constants import CANON_RETRIEVAL_LIMIT, CANON_RETRIEVAL_MIN_SCORE
from core.services.canon.canon_models import CanonContext, CanonPassage
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.chunk_protocols import ReferenceChunkSearchOperations
    from core.services.embeddings_service import EmbeddingsService

logger = get_logger("skuel.services.canon")


class CanonRetrievalService:
    """Retrieve the canon shelf's most resonant passages for a query.

    Backend: ``ReferenceChunkSearchOperations`` (reference vector index);
    ``EmbeddingsService`` (query embedding — ``None`` on CORE tier).
    """

    def __init__(
        self,
        reference_search: ReferenceChunkSearchOperations,
        embeddings_service: EmbeddingsService | None = None,
    ) -> None:
        self._reference_search = reference_search
        self._embeddings = embeddings_service

    async def retrieve(
        self,
        query_text: str,
        *,
        limit: int = CANON_RETRIEVAL_LIMIT,
        min_score: float = CANON_RETRIEVAL_MIN_SCORE,
        resource_uids: list[str] | None = None,
    ) -> Result[CanonContext]:
        """Return canon passages nearest ``query_text``.

        Fails (so the caller fail-softs to canon-free) when embeddings are
        unavailable (CORE tier) or the query is blank — mirrors
        ``Neo4jVectorSearchService.find_similar_chunks_by_text``. A successful
        search with no resonant passage is *not* a failure: it returns an empty
        ``CanonContext`` so the caller proceeds cleanly.

        Args:
            query_text: The text to find resonant canon passages for (the raw
                journal entry, or a learner's question).
            limit: Maximum passages to draw.
            min_score: Minimum cosine similarity for a passage to count.
            resource_uids: Restrict the draw to these Resources (e.g. a
                PathStep's cited books); ``None`` = the whole shelf.

        Returns:
            ``Result.ok(CanonContext)`` on success (possibly empty), or
            ``Result.fail`` when retrieval could not run.
        """
        if self._embeddings is None:
            return Result.fail(
                Errors.unavailable(
                    feature="canon_retrieval",
                    reason="Embeddings service required (FULL tier only).",
                    operation="canon_retrieve",
                )
            )
        if not query_text or not query_text.strip():
            return Result.fail(Errors.validation("Query text cannot be empty", field="query_text"))

        embedding_result = await self._embeddings.create_embedding(query_text)
        if embedding_result.is_error:
            return Result.fail(embedding_result)

        hits = await self._reference_search.search_reference_chunks(
            query_embedding=embedding_result.value,
            limit=limit,
            threshold=min_score,
            resource_uids=resource_uids,
        )
        if not hits:
            logger.debug("Canon draw: no passage cleared min_score=%.3f", min_score)
            return Result.ok(CanonContext.empty())

        passages = tuple(
            CanonPassage(
                text=hit["text"],
                book_title=hit["book_title"],
                resource_uid=hit["resource_uid"],
                similarity_score=hit["similarity_score"],
                heading=hit.get("heading"),
                section_path=hit.get("section_path"),
                sequence=hit.get("sequence"),
            )
            for hit in hits
        )
        context = CanonContext(passages=passages)
        # Observability for the documented tuning work (min_score / limit): the
        # only window onto what a summon actually drew. Titles + scores only —
        # never passage or journal text (ADR-073).
        scores = [p.similarity_score for p in passages]
        logger.info(
            "Canon draw: %d passage(s) from %s (score %.3f-%.3f, min_score=%.3f)",
            len(passages),
            ", ".join(context.books()) or "(untitled)",
            min(scores),
            max(scores),
            min_score,
        )
        return Result.ok(context)
