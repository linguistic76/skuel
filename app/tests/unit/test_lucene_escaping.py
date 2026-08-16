"""
Lucene query escaping — the fulltext parse-error guard.

``db.index.fulltext.queryNodes`` parses its query string as Lucene syntax, so
raw user input throws a parse error instead of searching, or silently changes
meaning. ``escape_lucene_query`` neutralizes user input into literal terms at
the one boundary that accepts it (SearchRouter → hybrid search).

Syntax reaches the parser through two doors and both are covered here:
special CHARACTERS (escaped) and reserved boolean KEYWORDS (quoted). The
keyword door was open in the first cut of this helper — Codex caught it on
PR #1074, and it is measured against a real Neo4j in
tests/integration/test_fulltext_hybrid_search.py.
"""

from __future__ import annotations

import pytest

from core.utils.lucene import escape_lucene_query

# Every character the Lucene query parser treats as syntax. `&` and `|` are
# escaped individually, which covers the two-character `&&` / `||` operators.
LUCENE_SPECIALS = '+-!(){}[]^"~*?:\\/&|'


class TestEscapeLuceneQuery:
    @pytest.mark.parametrize("char", list(LUCENE_SPECIALS))
    def test_every_special_is_backslash_escaped(self, char: str) -> None:
        assert escape_lucene_query(char) == f"\\{char}"

    def test_plain_text_is_untouched(self) -> None:
        assert escape_lucene_query("breath awareness") == "breath awareness"

    def test_alphanumerics_and_punctuation_that_lucene_ignores_survive(self) -> None:
        assert escape_lucene_query("Python 3.14, e.g. asyncio") == "Python 3.14, e.g. asyncio"

    def test_real_world_query_with_specials(self) -> None:
        assert escape_lucene_query("C++ (advanced)") == "C\\+\\+ \\(advanced\\)"

    def test_boolean_operators_are_neutralized(self) -> None:
        assert escape_lucene_query("a && b") == "a \\&\\& b"

    def test_wildcards_are_neutralized(self) -> None:
        """A bare `*` is a valid Lucene query but not what the user typed."""
        assert escape_lucene_query("test*") == "test\\*"

    def test_field_syntax_is_neutralized(self) -> None:
        """`title:foo` would target a field; the user meant the literal text."""
        assert escape_lucene_query("title:foo") == "title\\:foo"

    def test_unbalanced_quote_does_not_raise(self) -> None:
        """The parse error this helper exists to prevent."""
        assert escape_lucene_query('say "hello') == 'say \\"hello'

    def test_empty_string(self) -> None:
        assert escape_lucene_query("") == ""

    def test_escaping_is_not_applied_twice(self) -> None:
        """Escaping an already-escaped string doubles the backslashes.

        Documents the contract: call this ONCE, at the input boundary.
        """
        assert escape_lucene_query(escape_lucene_query("a+b")) == "a\\\\\\+b"


class TestReservedBooleanKeywords:
    """The second door: uppercase AND/OR/NOT are operators, not characters.

    Verified against a real Neo4j (PR #1074): a bare `AND` raises
    ParseException, `war AND peace` becomes a conjunction, and `peace NOT war`
    excludes documents the user asked for.
    """

    @pytest.mark.parametrize("keyword", ["AND", "OR", "NOT"])
    def test_bare_keyword_is_quoted(self, keyword: str) -> None:
        assert escape_lucene_query(keyword) == f'"{keyword}"'

    def test_conjunction_becomes_literal_terms(self) -> None:
        assert escape_lucene_query("war AND peace") == 'war "AND" peace'

    def test_negation_becomes_literal_terms(self) -> None:
        assert escape_lucene_query("peace NOT war") == 'peace "NOT" war'

    def test_quoting_survives_alongside_escaped_quotes(self) -> None:
        """The risky interaction: real quotes added next to escaped ones."""
        assert escape_lucene_query('say "hello AND goodbye') == 'say \\"hello "AND" goodbye'

    @pytest.mark.parametrize("word", ["android", "NOTE", "ORDER", "candy", "NOTHING", "FOR"])
    def test_keywords_inside_words_are_untouched(self, word: str) -> None:
        """Word-boundary anchored — `NOTE` is not a negated `E`."""
        assert escape_lucene_query(word) == word

    @pytest.mark.parametrize("word", ["and", "or", "not", "And", "Not"])
    def test_lowercase_and_mixed_case_are_untouched(self, word: str) -> None:
        """Lucene only treats UPPERCASE as operators; rewriting the ordinary
        word would change the user's query for no safety gain."""
        assert escape_lucene_query(word) == word

    def test_to_is_left_alone(self) -> None:
        """`TO` is reserved only inside a range, and `[`/`]` are already escaped."""
        assert escape_lucene_query("TO peace") == "TO peace"
