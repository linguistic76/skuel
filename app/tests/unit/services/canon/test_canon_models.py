"""Tests for canon value objects — prompt block, footer, book de-dupe, empty, VAULT kind."""

from core.services.canon import (
    CanonContext,
    CanonPassage,
    SourceKind,
    merged_attribution_footer,
)


def _passage(
    text: str,
    book: str,
    uid: str = "resource_book",
    score: float = 0.9,
    *,
    heading: str | None = None,
    section_path: str | None = None,
    sequence: int | None = None,
) -> CanonPassage:
    return CanonPassage(
        text=text,
        book_title=book,
        resource_uid=uid,
        similarity_score=score,
        heading=heading,
        section_path=section_path,
        sequence=sequence,
    )


class TestCanonContextEmpty:
    def test_empty_has_no_passages(self):
        ctx = CanonContext.empty()
        assert ctx.has_passages is False
        assert ctx.passages == ()

    def test_empty_renders_no_prompt_block(self):
        assert CanonContext.empty().to_prompt_block() == ""

    def test_empty_renders_no_footer(self):
        assert merged_attribution_footer(CanonContext.empty()) == ""

    def test_empty_books_is_empty(self):
        assert CanonContext.empty().books() == []


class TestBooksDedupe:
    def test_distinct_books_order_preserved(self):
        ctx = CanonContext(
            passages=(
                _passage("a", "Hyper Media Systems"),
                _passage("b", "Book B"),
            )
        )
        assert ctx.books() == ["Hyper Media Systems", "Book B"]

    def test_same_book_collapses_to_one(self):
        ctx = CanonContext(
            passages=(
                _passage("a", "Hyper Media Systems"),
                _passage("b", "Hyper Media Systems"),
                _passage("c", "Book B"),
            )
        )
        assert ctx.books() == ["Hyper Media Systems", "Book B"]

    def test_blank_title_skipped(self):
        ctx = CanonContext(passages=(_passage("a", ""), _passage("b", "Real Book")))
        assert ctx.books() == ["Real Book"]


class TestPromptBlock:
    def test_block_carries_passage_text_and_no_quote_directive(self):
        ctx = CanonContext(passages=(_passage("Linked knowledge endures.", "HMS"),))
        block = ctx.to_prompt_block()
        assert "## Wisdom to Draw On" in block
        assert "Linked knowledge endures." in block
        # The model is told NOT to quote/cite the passages inline.
        assert "do NOT quote" in block

    def test_block_empty_when_all_text_blank(self):
        ctx = CanonContext(passages=(_passage("   ", "HMS"),))
        assert ctx.to_prompt_block() == ""


class TestAttributionFooter:
    def test_footer_names_books_italicised(self):
        ctx = CanonContext(
            passages=(
                _passage("a", "Hyper Media Systems"),
                _passage("b", "Book B"),
            )
        )
        footer = merged_attribution_footer(ctx)
        assert footer == "\n\n---\n*Drawing on:* *Hyper Media Systems*, *Book B*"

    def test_footer_dedupes_books(self):
        ctx = CanonContext(
            passages=(
                _passage("a", "HMS"),
                _passage("b", "HMS"),
            )
        )
        assert merged_attribution_footer(ctx) == "\n\n---\n*Drawing on:* *HMS*"

    def test_footer_empty_when_all_text_blank(self):
        # A blank-text passage is dropped from the prompt block, so it must not
        # be attributed either — the footer and the infusion share one truth.
        ctx = CanonContext(passages=(_passage("   ", "HMS"),))
        assert ctx.to_prompt_block() == ""
        assert ctx.books() == []
        assert merged_attribution_footer(ctx) == ""


class TestPassageLocation:
    def test_locator_joins_section_path_and_heading(self):
        p = _passage(
            "x",
            "HMS",
            section_path="Hypermedia Concepts > A Reintroduction",
            heading="A Brief History",
        )
        assert p.locator == "Hypermedia Concepts > A Reintroduction > A Brief History"

    def test_locator_empty_when_no_headings(self):
        assert _passage("x", "HMS").locator == ""

    def test_locator_heading_only(self):
        assert _passage("x", "HMS", heading="Foreword").locator == "Foreword"

    def test_citation_line_is_book_plus_location(self):
        p = _passage("x", "Hypermedia Systems", heading="Foreword")
        assert p.citation_line() == "Hypermedia Systems — Foreword"

    def test_citation_line_book_only_without_location(self):
        assert _passage("x", "Hypermedia Systems").citation_line() == "Hypermedia Systems"


class TestDiscussionBlock:
    def test_block_permits_quoting_and_names_the_shelf(self):
        ctx = CanonContext(
            passages=(_passage("HTML is a hypermedia.", "Hypermedia Systems", heading="Intro"),)
        )
        block = ctx.to_discussion_block()
        assert "## The Canon Shelf" in block
        # The exact passage text is present (quotable verbatim)…
        assert "HTML is a hypermedia." in block
        # …labelled with its source so a citation is exact…
        assert "Hypermedia Systems — Intro" in block
        # …and the faithfulness contract is stated (this is the discussion path,
        # the OPPOSITE of the silent-infusion to_prompt_block()).
        assert "verbatim" in block
        assert "never" in block.lower()
        assert "do NOT quote" not in block

    def test_block_empty_when_no_passages(self):
        assert CanonContext.empty().to_discussion_block() == ""

    def test_block_empty_when_all_text_blank(self):
        assert CanonContext(passages=(_passage("  ", "HMS"),)).to_discussion_block() == ""


class TestTeachingBlock:
    def test_block_grounds_guidance_with_citation_and_text(self):
        ctx = CanonContext(
            passages=(
                _passage(
                    "HTML is a hypermedia.",
                    "Hypermedia Systems",
                    heading="A Reintroduction",
                    section_path="Hypermedia Concepts",
                ),
            )
        )
        block = ctx.to_teaching_block()
        assert "## Readings for This Step" in block
        # The exact passage text is present (quotable verbatim)…
        assert "HTML is a hypermedia." in block
        # …labelled with its citation_line so a citation is exact.
        assert "Hypermedia Systems — Hypermedia Concepts > A Reintroduction" in block

    def test_block_keeps_the_socratic_method(self):
        ctx = CanonContext(passages=(_passage("An answer, stated plainly.", "HMS"),))
        block = ctx.to_teaching_block()
        # The method survives the readings: answers become better questions.
        assert "Do not surrender the method" in block
        # The ADR-076 faithfulness contract: no fabricated passages/anchors,
        # sparing verbatim quotes, chapter/section citations only.
        assert "never invent a passage, chapter, or section" in block
        assert "verbatim and sparingly" in block
        assert "never by page number" in block

    def test_block_direct_framing_drops_the_method_keeps_the_contract(self):
        """preserve_method=False (DIRECT mode, Codex #613 P2): the block grounds
        a direct answer instead of instructing the model to ask a better
        question — but the ADR-076 faithfulness contract is identical."""
        ctx = CanonContext(passages=(_passage("An answer, stated plainly.", "HMS"),))
        block = ctx.to_teaching_block(preserve_method=False)
        assert "Do not surrender the method" not in block
        assert "ask a better question" not in block
        assert "Answer directly" in block
        # Same faithfulness contract as the Socratic framing:
        assert "never invent a passage, chapter, or section" in block
        assert "verbatim and sparingly" in block
        assert "never by page number" in block
        # Same structure: passage text + citation still present.
        assert "An answer, stated plainly." in block

    def test_block_empty_when_no_passages(self):
        assert CanonContext.empty().to_teaching_block() == ""

    def test_block_empty_when_all_text_blank(self):
        assert CanonContext(passages=(_passage("   ", "HMS"),)).to_teaching_block() == ""

    def test_block_carries_only_passage_text(self):
        ctx = CanonContext(passages=(_passage("The one real passage.", "HMS"),))
        block = ctx.to_teaching_block()
        # Everything after the framing preamble is exactly the passage entries —
        # no text that isn't in `passages` can leak into the readings body.
        body = block.split("never by page number.\n\n", 1)[1]
        assert body == "### HMS\n\nThe one real passage."


class TestSources:
    def test_sources_carry_book_uid_and_location(self):
        ctx = CanonContext(
            passages=(
                _passage(
                    "x",
                    "Hypermedia Systems",
                    uid="resource.hypermedia-systems",
                    section_path="Hypermedia Concepts",
                    heading="A Reintroduction",
                ),
            )
        )
        sources = ctx.sources()
        assert len(sources) == 1
        assert sources[0].book_title == "Hypermedia Systems"
        assert sources[0].resource_uid == "resource.hypermedia-systems"
        assert sources[0].locators == ("Hypermedia Concepts > A Reintroduction",)

    def test_sources_group_distinct_locations_per_book(self):
        ctx = CanonContext(
            passages=(
                _passage("a", "HMS", uid="r", heading="Ch 1"),
                _passage("b", "HMS", uid="r", heading="Ch 2"),
            )
        )
        sources = ctx.sources()
        assert len(sources) == 1  # one book
        assert sources[0].locators == ("Ch 1", "Ch 2")

    def test_sources_empty_when_no_passages(self):
        assert CanonContext.empty().sources() == ()


def _vault_passage(
    text: str,
    title: str,
    uid: str = "ue_note",
    score: float = 0.9,
    *,
    vault_path: str | None = "knowledge/note.md",
) -> CanonPassage:
    return CanonPassage(
        text=text,
        book_title=title,
        resource_uid=uid,
        similarity_score=score,
        source_kind=SourceKind.VAULT,
        vault_path=vault_path,
    )


class TestVaultPassage:
    """Canon P3: VAULT passages reinterpret the book fields on the ONE family."""

    def test_defaults_are_canon_and_uniform_weight(self):
        p = _passage("text", "Book")
        assert p.source_kind is SourceKind.CANON
        assert p.vault_path is None
        # ADR-077 contract letter: weight exists, defaults 1.0, nothing reads it.
        assert p.weight == 1.0

    def test_vault_locator_is_the_path(self):
        p = _vault_passage("text", "My Note", vault_path="knowledge/stoicism.md")
        assert p.locator == "knowledge/stoicism.md"
        assert p.citation_line() == "My Note — knowledge/stoicism.md"

    def test_vault_locator_empty_without_path(self):
        p = _vault_passage("text", "My Note", vault_path=None)
        assert p.locator == ""
        assert p.citation_line() == "My Note"

    def test_vault_locator_ignores_book_heading_fields(self):
        p = CanonPassage(
            text="t",
            book_title="Note",
            resource_uid="ue_1",
            similarity_score=0.5,
            heading="Should not appear",
            section_path="Nor this",
            source_kind=SourceKind.VAULT,
            vault_path="knowledge/n.md",
        )
        assert p.locator == "knowledge/n.md"


class TestVaultRenderBlocks:
    def test_vault_prompt_block_uses_own_notes_framing(self):
        ctx = CanonContext(
            passages=(_vault_passage("A thought I wrote.", "My Note"),),
            source_kind=SourceKind.VAULT,
        )
        block = ctx.to_prompt_block()
        assert "The User's Own Notes to Draw On" in block
        assert "own vault notes" in block
        assert "do NOT quote" in block
        assert "A thought I wrote." in block
        # Never the canon-shelf framing.
        assert "curated shelf" not in block

    def test_vault_discussion_block_carries_faithfulness_contract(self):
        ctx = CanonContext(
            passages=(_vault_passage("Exact words here.", "My Note"),),
            source_kind=SourceKind.VAULT,
        )
        block = ctx.to_discussion_block()
        assert "The User's Vault Notes" in block
        assert "Faithfulness (non-negotiable):" in block
        assert "never reconstruct a quote from memory" in block
        assert "say so plainly rather than fabricate" in block
        assert "My Note — knowledge/note.md" in block
        assert "Exact words here." in block
        # Book-anchor phrasing must not leak into the vault framing.
        assert "chapter/section" not in block

    def test_canon_blocks_unchanged_by_default_kind(self):
        ctx = CanonContext(passages=(_passage("Canon text.", "Book"),))
        assert "Wisdom to Draw On" in ctx.to_prompt_block()
        assert "The Canon Shelf" in ctx.to_discussion_block()

    def test_vault_sources_carry_kind(self):
        ctx = CanonContext(
            passages=(_vault_passage("t", "My Note", uid="ue_9"),),
            source_kind=SourceKind.VAULT,
        )
        sources = ctx.sources()
        assert len(sources) == 1
        assert sources[0].source_kind is SourceKind.VAULT
        assert sources[0].resource_uid == "ue_9"
        assert sources[0].locators == ("knowledge/note.md",)


class TestMergedFooter:
    def test_merges_both_corpora_into_one_line(self):
        canon = CanonContext(passages=(_passage("a", "Book A"),))
        vault = CanonContext(
            passages=(_vault_passage("b", "My Note"),), source_kind=SourceKind.VAULT
        )
        footer = merged_attribution_footer(canon, vault)
        assert footer.count("---") == 1  # one rule, never two
        assert "*Book A*" in footer
        assert "*My Note*" in footer

    def test_dedupes_titles_across_contexts(self):
        a = CanonContext(passages=(_passage("a", "Same Title"),))
        b = CanonContext(
            passages=(_vault_passage("b", "Same Title"),), source_kind=SourceKind.VAULT
        )
        footer = merged_attribution_footer(a, b)
        assert footer.count("Same Title") == 1

    def test_empty_when_nothing_infused(self):
        assert merged_attribution_footer(CanonContext.empty(), CanonContext.empty()) == ""

    def test_single_context_renders_the_plain_footer(self):
        canon = CanonContext(passages=(_passage("a", "Book A"),))
        assert merged_attribution_footer(canon, CanonContext.empty()) == (
            "\n\n---\n*Drawing on:* *Book A*"
        )
