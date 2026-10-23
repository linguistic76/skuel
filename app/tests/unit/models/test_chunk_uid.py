"""A chunk's uid: ``chunk_{hash}`` of its store, parent and index (``chunk_uid``).

The uid is deterministic so a re-chunk re-creates the uids a queued
``ChunkEmbeddingRequested`` names, and the store is hashed in so a body chunk and
a shelved-book chunk of one parent can never share a uid.
"""

from __future__ import annotations

from core.models.ps_content.content import CurriculumContent
from core.models.ps_content.content_chunks import (
    ChunkStore,
    ContentChunk,
    ContentChunkType,
    chunk_uid,
)
from core.services.ingestion.config import REFERENCE_CHUNKING_PARAMS
from core.services.ingestion.reference_ingestion import _consolidate_chunks
from core.utils.uid_grammar import UidVerdict, classify, exemptions_for, hashed_uid


def _chunk(
    parent_uid: str = "ps.a.b", index: int = 3, store: ChunkStore = ChunkStore.CONTENT
) -> ContentChunk:
    return ContentChunk(
        parent_uid=parent_uid,
        chunk_index=index,
        chunk_type=ContentChunkType.SECTION,
        text="t",
        context_before="",
        context_after="",
        store=store,
    )


def test_a_chunk_uid_fits_the_grammar_and_needs_no_exemption() -> None:
    uid = _chunk().chunk_id
    assert uid.startswith("chunk_")
    assert classify(uid) is UidVerdict.FITS
    assert exemptions_for(uid) == ()


def test_the_uid_is_the_hash_of_store_parent_and_index() -> None:
    assert _chunk().chunk_id == hashed_uid("chunk", "content", "ps.a.b", "3")
    assert _chunk().chunk_id == chunk_uid(ChunkStore.CONTENT, "ps.a.b", 3)


def test_the_same_chunk_position_always_has_the_same_uid() -> None:
    assert _chunk().chunk_id == _chunk().chunk_id


def test_index_and_parent_each_change_the_uid() -> None:
    uids = {_chunk().chunk_id, _chunk(index=4).chunk_id, _chunk(parent_uid="ps.a.c").chunk_id}
    assert len(uids) == 3


def test_the_two_stores_never_mint_one_uid() -> None:
    body = _chunk(parent_uid="resource.tao-te-ching", index=0)
    shelf = _chunk(parent_uid="resource.tao-te-ching", index=0, store=ChunkStore.REFERENCE)
    assert body.chunk_id != shelf.chunk_id
    assert shelf.chunk_id == chunk_uid(ChunkStore.REFERENCE, "resource.tao-te-ching", 0)


def test_a_body_chunk_belongs_to_the_content_store() -> None:
    content = CurriculumContent.create(unit_uid="ps.a.b", body="## One\n\nSome words here.")
    assert content.chunks
    assert {chunk.store for chunk in content.chunks} == {ChunkStore.CONTENT}
    assert [chunk.chunk_id for chunk in content.chunks] == [
        chunk_uid(ChunkStore.CONTENT, "ps.a.b", i) for i in range(len(content.chunks))
    ]


def test_a_consolidated_passage_belongs_to_the_reference_store() -> None:
    raw = [_chunk(parent_uid="resource.x", index=i) for i in range(3)]
    passages = _consolidate_chunks(raw, "resource.x", REFERENCE_CHUNKING_PARAMS)
    assert passages
    assert {passage.store for passage in passages} == {ChunkStore.REFERENCE}
    assert [passage.chunk_id for passage in passages] == [
        chunk_uid(ChunkStore.REFERENCE, "resource.x", i) for i in range(len(passages))
    ]
