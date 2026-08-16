"""
Lucene Query Escaping
=====================

Neo4j fulltext indexes (`db.index.fulltext.queryNodes`) parse their query
string as Lucene syntax. Raw user input containing Lucene special characters
(`+ - && || ! ( ) { } [ ] ^ " ~ * ? : \\ /`) throws a parse error instead of
searching. This helper neutralizes user input into a plain term query.

Applied ONLY at the user-input boundary (SearchRouter → hybrid search). It is
deliberately NOT applied to power-user surfaces that accept Lucene syntax
on purpose.

Usage:
    from core.utils.lucene import escape_lucene_query

    safe = escape_lucene_query('C++ (advanced)')  # 'C\\+\\+ \\(advanced\\)'
"""

from __future__ import annotations

# The Lucene special characters, per the Lucene query-parser syntax spec.
# `&&` / `||` are two-character operators — escaping each `&` / `|` covers them.
_LUCENE_SPECIAL_CHARS = frozenset('+-!(){}[]^"~*?:\\/&|')


def escape_lucene_query(query_text: str) -> str:
    """
    Escape Lucene query-parser special characters in user input.

    Backslash-escapes every special character so the input is searched as
    literal terms rather than parsed as Lucene operators.

    Args:
        query_text: Raw user search input

    Returns:
        The input with all Lucene specials backslash-escaped
    """
    return "".join(f"\\{char}" if char in _LUCENE_SPECIAL_CHARS else char for char in query_text)
