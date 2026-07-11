"""Tests for CanonRetrievalService — fail-soft + happy-path retrieval."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.query_types import ReferenceChunkHit
from core.services.canon import CanonRetrievalService
from core.utils.result_simplified import Errors, Result


def _hit(
    text: str,
    book: str,
    uid: str = "resource_hms",
    score: float = 0.8,
    *,
    heading: str | None = None,
    section_path: str | None = None,
    sequence: int | None = None,
) -> ReferenceChunkHit:
    return ReferenceChunkHit(
        chunk_uid="rc_1",
        text=text,
        context_window=None,
        heading=heading,
        section_path=section_path,
        sequence=sequence,
        similarity_score=score,
        resource_uid=uid,
        book_title=book,
    )


class TestRetrieveFailSoft:
    @pytest.mark.asyncio
    async def test_no_embeddings_fails(self):
        # CORE tier — no embeddings service, so no query vector: fail (caller degrades).
        search = MagicMock()
        service = CanonRetrievalService(reference_search=search, embeddings_service=None)
        result = await service.retrieve("hypermedia and linked knowledge")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_blank_query_fails(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock()
        search = MagicMock()
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)
        result = await service.retrieve("   ")
        assert result.is_error
        embeddings.create_embedding.assert_not_called()

    @pytest.mark.asyncio
    async def test_embedding_error_propagates(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock(
            return_value=Result.fail(Errors.integration("embeddings", "boom"))
        )
        search = MagicMock()
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)
        result = await service.retrieve("something")
        assert result.is_error


class TestRetrieveHappyPath:
    @pytest.mark.asyncio
    async def test_no_hits_returns_empty_context(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1, 0.2, 0.3]))
        search = MagicMock()
        search.search_reference_chunks = AsyncMock(return_value=[])
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)

        result = await service.retrieve("no resonance")

        assert result.is_ok
        assert result.value.has_passages is False

    @pytest.mark.asyncio
    async def test_builds_context_with_books(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1, 0.2, 0.3]))
        search = MagicMock()
        search.search_reference_chunks = AsyncMock(
            return_value=[
                _hit("Linked knowledge endures.", "Hyper Media Systems"),
                _hit("A second idea.", "Book B"),
            ]
        )
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)

        result = await service.retrieve("hypermedia thoughts")

        assert result.is_ok
        ctx = result.value
        assert ctx.has_passages is True
        assert ctx.books() == ["Hyper Media Systems", "Book B"]
        assert "Linked knowledge endures." in ctx.to_prompt_block()

    @pytest.mark.asyncio
    async def test_maps_location_fields_into_passages(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1]))
        search = MagicMock()
        search.search_reference_chunks = AsyncMock(
            return_value=[
                _hit(
                    "HTML is a hypermedia.",
                    "Hypermedia Systems",
                    heading="A Reintroduction",
                    section_path="Hypermedia Concepts",
                    sequence=3,
                )
            ]
        )
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)

        result = await service.retrieve("hypermedia")

        passage = result.value.passages[0]
        assert passage.heading == "A Reintroduction"
        assert passage.section_path == "Hypermedia Concepts"
        assert passage.sequence == 3
        assert passage.locator == "Hypermedia Concepts > A Reintroduction"

    @pytest.mark.asyncio
    async def test_passes_constants_through_to_search(self):
        from core.constants import CANON_RETRIEVAL_LIMIT, CANON_RETRIEVAL_MIN_SCORE

        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1]))
        search = MagicMock()
        search.search_reference_chunks = AsyncMock(return_value=[])
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)

        await service.retrieve("q")

        search.search_reference_chunks.assert_awaited_once()
        kwargs = search.search_reference_chunks.await_args.kwargs
        assert kwargs["limit"] == CANON_RETRIEVAL_LIMIT
        assert kwargs["threshold"] == CANON_RETRIEVAL_MIN_SCORE
        assert kwargs["query_embedding"] == [0.1]
        # Default scope is the whole shelf — journal behaviour unchanged.
        assert kwargs["resource_uids"] is None

    @pytest.mark.asyncio
    async def test_resource_uids_pass_through_to_search(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1]))
        search = MagicMock()
        search.search_reference_chunks = AsyncMock(return_value=[])
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)

        await service.retrieve("q", resource_uids=["resource.hms", "resource.other"])

        kwargs = search.search_reference_chunks.await_args.kwargs
        assert kwargs["resource_uids"] == ["resource.hms", "resource.other"]
