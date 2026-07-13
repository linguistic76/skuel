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

import json
from typing import TYPE_CHECKING

from core.constants import CANON_RETRIEVAL_LIMIT, CANON_RETRIEVAL_MIN_SCORE
from core.services.canon.canon_models import CanonContext, CanonPassage, SourceKind
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.chunk_protocols import ReferenceChunkSearchOperations
    from core.ports.query_types import ShelvedBook
    from core.ports.vector_search_protocols import VectorSearchBackendOperations
    from core.services.embeddings_service import EmbeddingsService

logger = get_logger("skuel.services.canon")


def _vault_display_path(parent_metadata: str | None) -> str | None:
    """Vault-relative display path from a UserEntry's raw metadata JSON.

    The stored ``vault_file_path`` is absolute; user-facing citations must
    never leak the host prefix (path-display policy, 2026-07-05 vault security
    arc). The service is vault-root-agnostic, so the display is the last two
    path components — ``knowledge/foo.md`` for doorway files. Malformed or
    missing metadata degrades to ``None`` (the citation falls back to the
    note title alone), never to a failed passage.
    """
    if not parent_metadata:
        return None
    try:
        raw_path = json.loads(parent_metadata).get("vault_file_path")
    except json.JSONDecodeError, TypeError, AttributeError:
        return None
    if not raw_path or not isinstance(raw_path, str):
        return None
    parts = raw_path.replace("\\", "/").strip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


class CanonRetrievalService:
    """Retrieve the most resonant passages for a query — shelf or vault.

    Backend: ``ReferenceChunkSearchOperations`` (reference vector index, the
    ``retrieve`` side); ``VectorSearchBackendOperations`` (owner-scoped content
    chunk index, the ``retrieve_vault`` side — canon P3); ``EmbeddingsService``
    (query embedding — ``None`` on CORE tier). Two substrates, two ports, one
    contract shape — never one Cypher (ADR-077).
    """

    def __init__(
        self,
        reference_search: ReferenceChunkSearchOperations,
        embeddings_service: EmbeddingsService | None = None,
        content_chunk_search: VectorSearchBackendOperations | None = None,
    ) -> None:
        self._reference_search = reference_search
        self._embeddings = embeddings_service
        self._content_chunk_search = content_chunk_search

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
        if resource_uids is not None and not resource_uids:
            # Empty scope is a guaranteed miss — don't spend an embedding call
            # on it (the adapter would short-circuit to [] anyway).
            logger.debug("Canon draw: empty resource scope — skipping retrieval")
            return Result.ok(CanonContext.empty())

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

    async def retrieve_vault(
        self,
        query_text: str,
        user_uid: str,
        *,
        limit: int = CANON_RETRIEVAL_LIMIT,
        min_score: float = CANON_RETRIEVAL_MIN_SCORE,
    ) -> Result[CanonContext]:
        """Return the user's own vault-note passages nearest ``query_text``.

        The canon-P3 sibling of :meth:`retrieve`: same guards, same contract
        shape, the OTHER substrate — owner-scoped :ContentChunk retrieval over
        the user's non-private knowledge notes (the vault-minus-private
        corpus). A sibling method rather than a scope parameter keeps ADR-077's
        "two substrates, never one Cypher" legible at the call site.

        Fails (so the caller fail-softs to an ungrounded stage) when embeddings
        or the content-chunk backend are unavailable, or the query is blank. A
        successful search with no resonant passage returns an empty
        ``CanonContext``.

        Args:
            query_text: The text to find resonant vault passages for (the raw
                journal entry, or the user's follow-up question).
            user_uid: The acting user — retrieval never crosses this scope.
            limit: Maximum passages to draw.
            min_score: Minimum cosine similarity for a passage to count.

        Returns:
            ``Result.ok(CanonContext)`` (``source_kind=VAULT``) on success, or
            ``Result.fail`` when retrieval could not run.
        """
        if self._embeddings is None or self._content_chunk_search is None:
            return Result.fail(
                Errors.unavailable(
                    feature="vault_retrieval",
                    reason="Embeddings + content chunk search required (FULL tier only).",
                    operation="vault_retrieve",
                )
            )
        if not query_text or not query_text.strip():
            return Result.fail(Errors.validation("Query text cannot be empty", field="query_text"))

        embedding_result = await self._embeddings.create_embedding(query_text)
        if embedding_result.is_error:
            return Result.fail(embedding_result)

        hits_result = await self._content_chunk_search.semantic_search_chunks(
            query_embedding=embedding_result.value,
            limit=limit,
            threshold=min_score,
            parent_filters={"pipeline": "knowledge"},
            owner_uid=user_uid,
        )
        if hits_result.is_error:
            return Result.fail(hits_result)
        hits = hits_result.value
        if not hits:
            logger.debug("Vault draw: no passage cleared min_score=%.3f", min_score)
            return Result.ok(CanonContext.empty())

        passages = tuple(
            CanonPassage(
                text=hit["text"],
                book_title=hit["parent_title"],
                resource_uid=hit["parent_uid"],
                similarity_score=hit["similarity_score"],
                source_kind=SourceKind.VAULT,
                vault_path=_vault_display_path(hit.get("parent_metadata")),
            )
            for hit in hits
        )
        context = CanonContext(passages=passages, source_kind=SourceKind.VAULT)
        # ADR-073 logging parity with the canon draw: titles + scores only —
        # never passage or journal text.
        scores = [p.similarity_score for p in passages]
        logger.info(
            "Vault draw: %d passage(s) from %s (score %.3f-%.3f, min_score=%.3f)",
            len(passages),
            ", ".join(context.books()) or "(untitled)",
            min(scores),
            max(scores),
            min_score,
        )
        return Result.ok(context)

    async def list_shelf(self) -> Result[list[ShelvedBook]]:
        """List every book on the canon shelf (title-ordered) for the source picker.

        The shelf's membership read — no embeddings needed, so it works on any
        tier the reference backend is wired for. Fail-soft: the underlying read
        fails open to an empty list, and the picker renders nothing rather than
        breaking the composer.

        Backend: ``ReferenceChunkSearchOperations.list_shelved_books``.
        """
        return Result.ok(await self._reference_search.list_shelved_books())
