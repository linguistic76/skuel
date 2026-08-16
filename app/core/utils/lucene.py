"""
Lucene Query Escaping
=====================

Neo4j fulltext indexes (`db.index.fulltext.queryNodes`) parse their query
string as Lucene syntax. Raw user input throws a parse error instead of
searching, or silently changes meaning. This helper neutralizes user input
into a plain term query.

Lucene syntax reaches the parser through TWO doors, and escaping only the
first leaves the second open (Codex, PR #1074):

1. **Special characters** — `+ - && || ! ( ) { } [ ] ^ " ~ * ? : \\ /`.
   Backslash-escaped.
2. **Reserved boolean keywords** — bare uppercase `AND`, `OR`, `NOT`.
   Quoted. Verified against a real Neo4j: a bare `AND` raises
   `ParseException`, `war AND peace` becomes a conjunction rather than three
   literal terms, and `peace NOT war` excludes matches the user asked for.

`TO` is reserved only inside a range (`[a TO b]`), and `[`/`]` are already
escaped in step 1, so a range can never form — quoting it would only corrupt
searches for the ordinary word.

Applied ONLY at the user-input boundary (SearchRouter → hybrid search). It is
deliberately NOT applied to power-user surfaces that accept Lucene syntax
on purpose.

Usage:
    from core.utils.lucene import escape_lucene_query

    safe = escape_lucene_query('C++ (advanced)')  # 'C\\+\\+ \\(advanced\\)'
    safe = escape_lucene_query('war AND peace')   # 'war "AND" peace'
"""

from __future__ import annotations

import re

# The Lucene special characters, per the Lucene query-parser syntax spec.
# `&&` / `||` are two-character operators — escaping each `&` / `|` covers them.
_LUCENE_SPECIAL_CHARS = frozenset('+-!(){}[]^"~*?:\\/&|')

# Lucene's classic parser treats these as operators ONLY in uppercase, so the
# pattern is deliberately case-sensitive: a user searching for "and" means the
# word, and rewriting it would change their query for no safety gain.
_RESERVED_OPERATORS = re.compile(r"\b(?:AND|OR|NOT)\b")


def _quote_operator(match: re.Match[str]) -> str:
    """Wrap a reserved keyword so Lucene reads it as a term, not an operator."""
    return f'"{match.group(0)}"'


def escape_lucene_query(query_text: str) -> str:
    """
    Neutralize Lucene query syntax in user input.

    Backslash-escapes every special character and quotes the reserved boolean
    keywords, so the input is searched as literal terms rather than parsed as
    Lucene operators.

    Args:
        query_text: Raw user search input

    Returns:
        The input with Lucene specials escaped and boolean keywords quoted
    """
    escaped = "".join(f"\\{char}" if char in _LUCENE_SPECIAL_CHARS else char for char in query_text)
    return _RESERVED_OPERATORS.sub(_quote_operator, escaped)
