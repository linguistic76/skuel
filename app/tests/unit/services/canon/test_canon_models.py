"""Tests for canon value objects — prompt block, footer, book de-dupe, empty."""

from core.services.canon import CanonContext, CanonPassage


def _passage(text: str, book: str, uid: str = "resource_book", score: float = 0.9) -> CanonPassage:
    return CanonPassage(text=text, book_title=book, resource_uid=uid, similarity_score=score)


class TestCanonContextEmpty:
    def test_empty_has_no_passages(self):
        ctx = CanonContext.empty()
        assert ctx.has_passages is False
        assert ctx.passages == ()

    def test_empty_renders_no_prompt_block(self):
        assert CanonContext.empty().to_prompt_block() == ""

    def test_empty_renders_no_footer(self):
        assert CanonContext.empty().attribution_footer() == ""

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
        footer = ctx.attribution_footer()
        assert footer == "\n\n---\n*Drawing on:* *Hyper Media Systems*, *Book B*"

    def test_footer_dedupes_books(self):
        ctx = CanonContext(
            passages=(
                _passage("a", "HMS"),
                _passage("b", "HMS"),
            )
        )
        assert ctx.attribution_footer() == "\n\n---\n*Drawing on:* *HMS*"

    def test_footer_empty_when_all_text_blank(self):
        # A blank-text passage is dropped from the prompt block, so it must not
        # be attributed either — the footer and the infusion share one truth.
        ctx = CanonContext(passages=(_passage("   ", "HMS"),))
        assert ctx.to_prompt_block() == ""
        assert ctx.books() == []
        assert ctx.attribution_footer() == ""
