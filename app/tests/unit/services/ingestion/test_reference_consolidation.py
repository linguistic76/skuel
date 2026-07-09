"""Unit tests for canon reference-chunk consolidation.

The shared ``ContentChunkingStrategy`` splits per structural unit and never
enforces ``min_chunk_size`` (inert), so a book shatters into thousands of tiny
fragments. ``_consolidate_chunks`` packs those into prose-grain passages before
they become :ReferenceChunk nodes. These tests guard that behaviour with
synthetic chunks (no book, no DB, no API).
"""

from typing import Any

from core.models.ps_content.content_chunks import (
    ContentChunk,
    ContentChunkType,
    chunk_version_tag,
)
from core.services.ingestion.config import REFERENCE_CHUNKING_PARAMS
from core.services.ingestion.reference_ingestion import (
    ReferenceIngestionService,
    _consolidate_chunks,
)

_UID = "resource.test-book"


class _RecordingAdapter:
    """Fake reference-chunk adapter that flags any persistence call."""

    def __init__(self) -> None:
        self.store_called = False

    async def store_reference_chunks(self, resource_uid: str, chunks: Any) -> bool:
        self.store_called = True
        return True


def _frag(
    index: int,
    text: str,
    heading: str | None = None,
    section_path: str | None = None,
) -> ContentChunk:
    return ContentChunk(
        parent_uid=_UID,
        chunk_index=index,
        chunk_type=ContentChunkType.SECTION,
        text=text,
        context_before="",
        context_after="",
        heading=heading,
        section_path=section_path,
    )


def test_packs_small_fragments_up_to_target() -> None:
    # 100 fragments of 20 words each = 2000 words; target 1000 → ~2 passages.
    frags = [_frag(i, " ".join(["word"] * 20)) for i in range(100)]
    merged = _consolidate_chunks(frags, _UID, REFERENCE_CHUNKING_PARAMS)

    assert len(merged) < len(frags)
    for m in merged:
        assert len(m.text.split()) <= REFERENCE_CHUNKING_PARAMS.max_chunk_size
    # Most passages should be substantial, not 20-word fragments.
    assert max(len(m.text.split()) for m in merged) > REFERENCE_CHUNKING_PARAMS.min_chunk_size


def test_chunk_ids_are_unique_and_resequenced() -> None:
    frags = [_frag(i, " ".join(["word"] * 30)) for i in range(50)]
    merged = _consolidate_chunks(frags, _UID, REFERENCE_CHUNKING_PARAMS)

    ids = [m.chunk_id for m in merged]
    assert len(ids) == len(set(ids))  # unique
    assert [m.chunk_index for m in merged] == list(range(len(merged)))  # 0..n-1


def test_blank_and_heading_only_fragments_dropped() -> None:
    frags = [
        _frag(0, "real content here"),
        _frag(1, "   "),  # whitespace only
        _frag(2, ""),  # empty
        _frag(3, "more real content"),
    ]
    merged = _consolidate_chunks(frags, _UID, REFERENCE_CHUNKING_PARAMS)

    assert len(merged) == 1
    assert "real content here" in merged[0].text
    assert "more real content" in merged[0].text


def test_carries_isolated_version_tag() -> None:
    frags = [_frag(0, "content")]
    merged = _consolidate_chunks(frags, _UID, REFERENCE_CHUNKING_PARAMS)

    # v1:1000-150 — isolates reference staleness from the "v1" curriculum corpus.
    assert merged[0].chunking_version == chunk_version_tag(REFERENCE_CHUNKING_PARAMS)
    assert merged[0].chunking_version != "v1"


def test_oversized_single_fragment_stands_alone() -> None:
    # A fragment already past the target isn't split further here (the chunker
    # caps at max) — it just occupies its own passage.
    big = _frag(0, " ".join(["w"] * (REFERENCE_CHUNKING_PARAMS.max_chunk_size + 200)))
    small = _frag(1, "tail")
    merged = _consolidate_chunks([big, small], _UID, REFERENCE_CHUNKING_PARAMS)

    assert len(merged) == 2
    assert len(merged[0].text.split()) > REFERENCE_CHUNKING_PARAMS.max_chunk_size


def test_empty_input_yields_empty() -> None:
    assert _consolidate_chunks([], _UID, REFERENCE_CHUNKING_PARAMS) == []


def test_consolidation_takes_location_pair_from_first_fragment() -> None:
    # heading + section_path must come from the SAME fragment (the group's first)
    # so they describe one section. Picking each independently could pair the
    # first fragment's heading with a later fragment's path → a wrong anchor
    # (Codex #572 P2). Here frag 0 and frag 1 differ, so the merged pair must be
    # exactly frag 0's — never a "A Brief History" / "Later Part" cross.
    frags = [
        _frag(0, "content one", heading="A Brief History", section_path="Concepts > Reintro"),
        _frag(1, "content two", heading="Later Section", section_path="Later Part"),
    ]
    merged = _consolidate_chunks(frags, _UID, REFERENCE_CHUNKING_PARAMS)
    assert merged[0].heading == "A Brief History"
    assert merged[0].section_path == "Concepts > Reintro"


def test_consolidation_location_pair_stays_consistent_when_first_is_headingless() -> None:
    # A group starting mid-section (no immediate heading) keeps frag 0's pair:
    # heading None + its ancestor trail — never borrowing a later section's heading.
    frags = [
        _frag(0, "continuation paragraph", heading=None, section_path="Concepts > Reintro"),
        _frag(1, "next section body", heading="A New Section", section_path="Concepts"),
    ]
    merged = _consolidate_chunks(frags, _UID, REFERENCE_CHUNKING_PARAMS)
    assert merged[0].heading is None
    assert merged[0].section_path == "Concepts > Reintro"


def test_chunk_markdown_captures_ancestor_breadcrumb() -> None:
    # End-to-end: the shared chunker records each chunk's ancestor-heading trail
    # (excluding the chunk's own heading), and a same-level Part heading pops the
    # book title so it never pollutes every breadcrumb.
    from core.models.ps_content.content_chunks import ContentChunkingStrategy

    md = (
        "# Book Title\n\nfront matter text here that is long enough to keep\n\n"
        "# Part One\n\n## A Chapter\n\n### A Section\n\n"
        "body text of the section long enough to survive chunking cleanly\n"
    )
    chunks = ContentChunkingStrategy.chunk_markdown(md, _UID)
    by_heading = {c.heading: c.section_path for c in chunks}
    # Front matter under the title has no ancestors.
    assert by_heading.get("Book Title") is None
    # The deep section's trail is Part > Chapter — the title was popped by "Part One".
    assert by_heading.get("A Section") == "Part One > A Chapter"


async def test_zero_chunk_ingest_refuses_without_touching_the_shelf() -> None:
    # An empty/frontmatter-only file yields zero chunks. store_reference_chunks
    # is delete-then-create, so persisting [] would silently unshelve an existing
    # book — the ingest must refuse and never call the adapter.
    adapter = _RecordingAdapter()
    service = ReferenceIngestionService(adapter, event_bus=None, resource_service=None)

    result = await service.ingest_book(_UID, "---\nresource_uid: r\n---\n")

    assert result.is_error
    assert not adapter.store_called
    assert "unshelve" in result.expect_error().message.lower()
