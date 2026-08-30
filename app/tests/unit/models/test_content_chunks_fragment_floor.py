"""The fragment floor (chunking algorithm v2): sub-sentence fragments never become chunks.

Measured 2026-08-28 on the live corpus: 83 of 998 `:ContentChunk` rows were
under 5 words — ``---`` rules, bare list markers, link-only and label-only
lines — against a 27-word median. A chunk that short can only ever be noise at
the similarity floor. The strategy now drops structural noise and folds any
other fragment into a prose neighbour; the algorithm version bumps to ``v2`` so
``regenerate_chunks(force=False)`` re-chunks every ``v1`` parent.
"""

from __future__ import annotations

from core.models.ps_content.content_chunks import (
    CHUNKING_ALGORITHM_VERSION,
    DEFAULT_CHUNKING_PARAMS,
    FRAGMENT_FLOOR_WORDS,
    ChunkingParams,
    ContentChunkingStrategy,
    ContentChunkType,
    chunk_version_tag,
)

_PARA_A = "Name five things you can see, four you can hear, and three you can touch."
_PARA_B = "What changed in your breathing while you counted the things around you?"
_FENCE = '```python\nprint("breathe")\n```'


def _texts(markdown: str) -> list[str]:
    return [c.text for c in ContentChunkingStrategy.chunk_markdown(markdown, "ps.test")]


def _words(text: str) -> int:
    return len(text.split())


class TestVersionBump:
    def test_v2_is_the_current_algorithm(self) -> None:
        # Every v1 chunk in the graph reads as stale under force=False.
        assert CHUNKING_ALGORITHM_VERSION == "v2"
        assert chunk_version_tag(DEFAULT_CHUNKING_PARAMS) == "v2"
        assert chunk_version_tag(ChunkingParams(max_chunk_size=300, context_size=60)) == "v2:300-60"

    def test_floor_is_below_the_corpus_median_and_above_a_bare_label(self) -> None:
        # 5 words: a `---`, a `[link](x.md)`, an `Ask:` are 1; the corpus median was 27.
        assert FRAGMENT_FLOOR_WORDS == 5


class TestStructuralNoiseIsDropped:
    def test_thematic_breaks_between_paragraphs_vanish(self) -> None:
        texts = _texts(f"# H\n\n{_PARA_A}\n\n---\n\n{_PARA_B}\n\n***\n\n___")
        assert texts == [_PARA_A, _PARA_B]

    def test_bare_list_markers_vanish(self) -> None:
        texts = _texts(f"# H\n\n{_PARA_A}\n\n-\n\n*\n\n1.\n\n{_PARA_B}")
        assert texts == [_PARA_A, _PARA_B]

    def test_a_rule_with_inner_spaces_still_counts_as_a_rule(self) -> None:
        assert _texts(f"# H\n\n{_PARA_A}\n\n- - -") == [_PARA_A]


class TestFragmentsFoldIntoProse:
    def test_label_folds_into_the_paragraph_it_introduces(self) -> None:
        texts = _texts(f"# H\n\nAsk:\n\n{_PARA_B}")
        assert texts == [f"Ask:\n\n{_PARA_B}"]

    def test_bold_pseudo_heading_folds_forward(self) -> None:
        # The live one-word PathStep chunk from the 2026-08-28 sample.
        texts = _texts(f"# H\n\n**5-4-3-2-1:**\n\n{_PARA_A}")
        assert texts == [f"**5-4-3-2-1:**\n\n{_PARA_A}"]

    def test_trailing_fragment_folds_back_into_the_last_paragraph(self) -> None:
        texts = _texts(f"# H\n\n{_PARA_A}\n\n[DRY](DRY.md)")
        assert texts == [f"{_PARA_A}\n\n[DRY](DRY.md)"]

    def test_consecutive_fragments_fold_together(self) -> None:
        texts = _texts(f"# H\n\nAsk:\n\nCount:\n\n{_PARA_B}")
        assert texts == [f"Ask:\n\nCount:\n\n{_PARA_B}"]

    def test_merged_chunk_is_retyped_from_its_final_text(self) -> None:
        chunks = ContentChunkingStrategy.chunk_markdown(f"# H\n\nExample:\n\n{_PARA_B}", "ps.test")
        assert [c.chunk_type for c in chunks] == [ContentChunkType.EXAMPLE]

    def test_a_section_of_only_fragments_becomes_one_joined_chunk(self) -> None:
        # Nothing to fold into: the fragments stay together under their heading
        # rather than becoming three one-word chunks.
        texts = _texts("# Links\n\n[DRY](DRY.md)\n\n[YAGNI](YAGNI.md)\n\n[[0a/delasd]]")
        assert texts == ["[DRY](DRY.md)\n\n[YAGNI](YAGNI.md)\n\n[[0a/delasd]]"]

    def test_exactly_the_floor_is_not_a_fragment(self) -> None:
        five = "one two three four five"
        assert _texts(f"# H\n\n{five}\n\n{_PARA_A}") == [five, _PARA_A]


class TestCodeFencesAreNeverMerged:
    def test_fragment_before_a_fence_waits_for_the_next_prose(self) -> None:
        chunks = ContentChunkingStrategy.chunk_markdown(
            f"# H\n\nExample:\n\n{_FENCE}\n\n{_PARA_B}", "ps.test"
        )
        assert [c.chunk_type for c in chunks] == [ContentChunkType.CODE, ContentChunkType.EXAMPLE]
        assert chunks[0].text == _FENCE
        assert chunks[1].text == f"Example:\n\n{_PARA_B}"

    def test_trailing_fragment_after_a_fence_folds_into_the_prose_before_it(self) -> None:
        chunks = ContentChunkingStrategy.chunk_markdown(
            f"# H\n\n{_PARA_A}\n\n{_FENCE}\n\nSee above.", "ps.test"
        )
        assert [c.text for c in chunks] == [f"{_PARA_A}\n\nSee above.", _FENCE]

    def test_a_short_fence_is_kept_verbatim(self) -> None:
        # Fences are code, not prose — the floor is a prose rule.
        chunks = ContentChunkingStrategy.chunk_markdown(f"# H\n\n{_FENCE}", "ps.test")
        assert [c.text for c in chunks] == [_FENCE]


class TestCleanInputIsUnchanged:
    def test_no_fragments_means_the_v1_boundaries(self) -> None:
        markdown = f"# One\n\n{_PARA_A}\n\n{_PARA_B}\n\n## Two\n\n{_PARA_A}"
        assert _texts(markdown) == [_PARA_A, _PARA_B, _PARA_A]

    def test_contexts_and_indexes_follow_the_folded_stream(self) -> None:
        chunks = ContentChunkingStrategy.chunk_markdown(
            f"# H\n\nAsk:\n\n{_PARA_A}\n\n---\n\n{_PARA_B}", "ps.test"
        )
        assert [c.chunk_index for c in chunks] == [0, 1]
        assert chunks[0].context_after.startswith(_PARA_B[:20])
        assert chunks[1].context_before.endswith(_PARA_A[-20:])
        assert all(c.chunking_version == "v2" for c in chunks)


class TestPlainTextPathHasTheSameFloor:
    def test_rules_drop_and_labels_fold_keeping_the_section_type(self) -> None:
        chunks = ContentChunkingStrategy.chunk_plain_text(
            f"Ask:\n\n---\n\n{_PARA_A}\n\nEnd.", "ue.test"
        )
        assert [c.text for c in chunks] == [f"Ask:\n\n{_PARA_A}\n\nEnd."]
        assert [c.chunk_type for c in chunks] == [ContentChunkType.SECTION]

    def test_fragments_only_input_yields_one_section_chunk(self) -> None:
        chunks = ContentChunkingStrategy.chunk_plain_text("Ask:\n\nCount:", "ue.test")
        assert [c.text for c in chunks] == ["Ask:\n\nCount:"]
        assert chunks[0].chunk_type is ContentChunkType.SECTION


def test_every_prose_chunk_of_a_fragment_laden_document_clears_the_floor() -> None:
    document = f"""# Grounding

**5-4-3-2-1:**

{_PARA_A}

---

Ask:

{_PARA_B}

-

Example:

{_FENCE}

{_PARA_A}

[DRY](DRY.md)
"""
    chunks = ContentChunkingStrategy.chunk_markdown(document, "ps.test")
    prose = [c for c in chunks if c.chunk_type is not ContentChunkType.CODE]
    assert prose, "the document has prose"
    assert all(_words(c.text) >= FRAGMENT_FLOOR_WORDS for c in prose)
    assert not any(c.text.strip() in {"---", "-"} for c in chunks)
