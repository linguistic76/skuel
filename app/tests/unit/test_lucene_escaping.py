"""
Lucene query escaping — the fulltext parse-error guard.

``db.index.fulltext.queryNodes`` parses its query string as Lucene syntax, so
raw user input carrying a special character throws a parse error instead of
searching. ``escape_lucene_query`` neutralizes user input into literal terms at
the one boundary that accepts it (SearchRouter → hybrid search).
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
