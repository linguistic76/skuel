"""Tests for CanonRetrievalService — fail-soft + happy-path retrieval (shelf + vault)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.ps_content.content_chunks import ContentChunkType
from core.ports.query_types import ReferenceChunkHit, SemanticSearchChunkResult
from core.services.canon import CanonRetrievalService, SourceKind
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
    async def test_empty_scope_short_circuits_before_embedding(self):
        # An empty scope is a guaranteed miss: ok-empty, and neither the
        # embedding call nor the search is spent (Codex P2 on #612).
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock()
        search = MagicMock()
        search.search_reference_chunks = AsyncMock()
        service = CanonRetrievalService(reference_search=search, embeddings_service=embeddings)

        result = await service.retrieve("q", resource_uids=[])

        assert result.is_ok
        assert result.value.has_passages is False
        embeddings.create_embedding.assert_not_called()
        search.search_reference_chunks.assert_not_called()

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


# ---------------------------------------------------------------------------
# retrieve_vault — the canon-P3 owner-scoped sibling
# ---------------------------------------------------------------------------


def _vault_hit(
    text: str,
    title: str,
    uid: str = "ue_note_1",
    score: float = 0.8,
    *,
    metadata: str | None = None,
) -> SemanticSearchChunkResult:
    hit = SemanticSearchChunkResult(
        chunk_uid="cc_1",
        # A real persisted value — "content" is not a ContentChunkType member.
        chunk_type=ContentChunkType.SECTION.value,
        text=text,
        context_window=None,
        similarity_score=score,
        parent_uid=uid,
        parent_title=title,
        parent_entity_type="user_entry",
    )
    hit["parent_metadata"] = metadata
    return hit


def _vault_service(hits: list[SemanticSearchChunkResult] | None = None):
    embeddings = MagicMock()
    embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1, 0.2]))
    chunk_search = MagicMock()
    chunk_search.semantic_search_chunks = AsyncMock(return_value=Result.ok(hits or []))
    service = CanonRetrievalService(
        reference_search=MagicMock(),
        embeddings_service=embeddings,
        content_chunk_search=chunk_search,
    )
    return service, embeddings, chunk_search


class TestRetrieveVaultFailSoft:
    @pytest.mark.asyncio
    async def test_no_embeddings_fails(self):
        service = CanonRetrievalService(
            reference_search=MagicMock(),
            embeddings_service=None,
            content_chunk_search=MagicMock(),
        )
        result = await service.retrieve_vault("stoicism", "user_1")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_no_content_chunk_search_fails(self):
        embeddings = MagicMock()
        embeddings.create_embedding = AsyncMock()
        service = CanonRetrievalService(reference_search=MagicMock(), embeddings_service=embeddings)
        result = await service.retrieve_vault("stoicism", "user_1")
        assert result.is_error
        embeddings.create_embedding.assert_not_called()

    @pytest.mark.asyncio
    async def test_blank_query_fails(self):
        service, embeddings, _ = _vault_service()
        result = await service.retrieve_vault("   ", "user_1")
        assert result.is_error
        embeddings.create_embedding.assert_not_called()

    @pytest.mark.asyncio
    async def test_embedding_error_propagates(self):
        service, embeddings, _ = _vault_service()
        embeddings.create_embedding = AsyncMock(
            return_value=Result.fail(Errors.integration("embeddings", "boom"))
        )
        result = await service.retrieve_vault("q", "user_1")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_search_error_propagates(self):
        service, _, chunk_search = _vault_service()
        chunk_search.semantic_search_chunks = AsyncMock(
            return_value=Result.fail(Errors.database("chunk_search", "neo4j down"))
        )
        result = await service.retrieve_vault("q", "user_1")
        assert result.is_error


class TestRetrieveVaultHappyPath:
    @pytest.mark.asyncio
    async def test_no_hits_returns_empty_context(self):
        service, _, _ = _vault_service()
        result = await service.retrieve_vault("no resonance", "user_1")
        assert result.is_ok
        assert result.value.has_passages is False

    @pytest.mark.asyncio
    async def test_scopes_to_acting_user_and_knowledge_pipeline(self):
        from core.constants import CANON_RETRIEVAL_LIMIT, CANON_RETRIEVAL_MIN_SCORE

        service, _, chunk_search = _vault_service()

        await service.retrieve_vault("q", "user_1")

        chunk_search.semantic_search_chunks.assert_awaited_once()
        kwargs = chunk_search.semantic_search_chunks.await_args.kwargs
        assert kwargs["owner_uid"] == "user_1"
        # The vault scope narrows; the audience (viewer) is what admits the
        # user's own UserEntry chunks at all — omitting it would read
        # curriculum only and empty the vault draw.
        assert kwargs["viewer_uid"] == "user_1"
        assert kwargs["parent_filters"] == {"pipeline": "knowledge"}
        assert kwargs["limit"] == CANON_RETRIEVAL_LIMIT
        assert kwargs["threshold"] == CANON_RETRIEVAL_MIN_SCORE

    @pytest.mark.asyncio
    async def test_builds_vault_context_with_paths(self):
        metadata = json.dumps(
            {"vault_file_path": "/home/mike/0bsidian/skuel/knowledge/stoicism.md"}
        )
        service, _, _ = _vault_service(
            [_vault_hit("Virtue is the only good.", "My Stoicism Notes", metadata=metadata)]
        )

        result = await service.retrieve_vault("stoicism", "user_1")

        assert result.is_ok
        ctx = result.value
        assert ctx.source_kind is SourceKind.VAULT
        passage = ctx.passages[0]
        assert passage.source_kind is SourceKind.VAULT
        assert passage.book_title == "My Stoicism Notes"
        assert passage.resource_uid == "ue_note_1"
        # Display path is doorway-relative — the absolute host prefix never leaks.
        assert passage.vault_path == "knowledge/stoicism.md"
        assert passage.locator == "knowledge/stoicism.md"
        assert passage.citation_line() == "My Stoicism Notes — knowledge/stoicism.md"

    @pytest.mark.asyncio
    async def test_malformed_metadata_keeps_passage_without_path(self):
        service, _, _ = _vault_service(
            [
                _vault_hit("Text A.", "Note A", metadata="{not json"),
                _vault_hit("Text B.", "Note B", uid="ue_2", metadata=None),
                _vault_hit("Text C.", "Note C", uid="ue_3", metadata=json.dumps({"other": 1})),
            ]
        )

        result = await service.retrieve_vault("q", "user_1")

        assert result.is_ok
        for passage in result.value.passages:
            assert passage.vault_path is None
        # Citation degrades to the note title alone, never a failed passage.
        assert result.value.passages[0].citation_line() == "Note A"

    @pytest.mark.asyncio
    async def test_logs_titles_and_scores_never_text(self, capsys):
        # ADR-073: the retrieval log is titles + scores only — never passage
        # text (which is the user's own note content). The skuel logger writes
        # structured lines to stdout (propagate=False), so capture stdout.
        service, _, _ = _vault_service(
            [_vault_hit("The secret passage body text.", "My Note", score=0.91)]
        )

        await service.retrieve_vault("q", "user_1")

        log_text = capsys.readouterr().out
        assert "My Note" in log_text
        assert "0.910" in log_text
        assert "secret passage body" not in log_text


class TestListShelf:
    """The shelf source-picker read — no embeddings needed, fail-soft."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(self):
        from core.ports.query_types import ShelvedBook

        books = [ShelvedBook(resource_uid="resource_hms", title="Hypermedia Systems")]
        search = MagicMock()
        search.list_shelved_books = AsyncMock(return_value=books)
        service = CanonRetrievalService(reference_search=search, embeddings_service=None)

        result = await service.list_shelf()

        assert result.is_ok
        assert result.value == books
        search.list_shelved_books.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_works_without_embeddings(self):
        # Shelf membership is a plain graph read — available even on CORE tier.
        search = MagicMock()
        search.list_shelved_books = AsyncMock(return_value=[])
        service = CanonRetrievalService(reference_search=search, embeddings_service=None)

        result = await service.list_shelf()

        assert result.is_ok
        assert result.value == []
