#!/usr/bin/env python3
"""
Cypher Vocabulary Registry — shared by lint_skuel.py (SKUEL030) and cypher_linter.py (CYP011)
==============================================================================================

Neo4j validates neither node labels nor relationship types. A typo'd
``(:KnowlegeDomain)`` or ``[:OWNS_ENTITY]`` raises nothing — the pattern simply
matches zero rows, silently, forever. The only defence is checking every name
written in persistence Cypher against the enums that claim to be the single
source of truth for the graph vocabulary:

- ``RelationshipName`` (core/models/relationship_names.py) — "All valid Neo4j
  relationship type names"
- ``NeoLabel`` (core/models/enums/neo_labels.py) — "All valid Neo4j node labels
  in SKUEL"

Both linters need the same two things — the registry and the name scanner — so
they live here rather than being written twice with two sets of edge cases.

**The registry is READ, not MIRRORED.** The enum members are recovered by
AST-parsing the two source files. The linters deliberately carry no runtime
dependency on ``core/`` (see the CREDENTIAL_CATALOG note in lint_skuel.py), and
the established alternative — hand-mirroring the catalog plus a drift test —
does not scale to 218 members across two enums. Parsing the declaration site
cannot drift: there is nothing to keep in sync.

Missing/empty enum sources raise ``VocabularyError`` rather than returning an
empty set. A silently empty registry would make every name "unregistered" (loud,
harmless) or — if the caller inverted the check — every name valid (silent, and
the exact failure the rule exists to prevent). Failing closed is the only safe
default for a rule whose whole value is catching what nothing else catches.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path


class VocabularyError(RuntimeError):
    """The enum registry could not be read — the rule cannot run meaningfully."""


class NameKind(StrEnum):
    """Which half of the graph vocabulary a scanned name belongs to."""

    RELATIONSHIP = "relationship"
    LABEL = "label"


# (module path relative to app/, enum class name) per vocabulary half.
ENUM_SOURCES: dict[NameKind, tuple[str, str]] = {
    NameKind.RELATIONSHIP: ("core/models/relationship_names.py", "RelationshipName"),
    NameKind.LABEL: ("core/models/enums/neo_labels.py", "NeoLabel"),
}


@dataclass(frozen=True)
class ScannedName:
    """A label or relationship type recovered from a Cypher fragment."""

    kind: NameKind
    value: str
    line_offset: int
    """Newlines between the start of the scanned fragment and this name."""


@dataclass(frozen=True)
class Vocabulary:
    """The registered graph vocabulary, read from the enum declaration sites."""

    relationships: frozenset[str]
    labels: frozenset[str]

    def is_registered(self, name: ScannedName) -> bool:
        """True if ``name`` is a member of the enum that governs its kind."""
        known = self.relationships if name.kind is NameKind.RELATIONSHIP else self.labels
        return name.value in known

    def enum_for(self, kind: NameKind) -> str:
        """Enum class name governing ``kind`` — for violation messages."""
        return ENUM_SOURCES[kind][1]


# =============================================================================
# Registry loading
# =============================================================================


def _enum_member_values(source: Path, class_name: str) -> frozenset[str]:
    """String values of every ``NAME = "value"`` member of ``class_name``.

    AST-only: the file is never imported, so reading the registry cannot execute
    application code or drag ``core/`` into the linter's import graph.
    """
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VocabularyError(f"cannot read enum source {source}: {exc}") from exc
    except SyntaxError as exc:
        raise VocabularyError(f"cannot parse enum source {source}: {exc}") from exc

    class_def = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    if class_def is None:
        raise VocabularyError(f"class {class_name} not found in {source}")

    values = {
        stmt.value.value
        for stmt in class_def.body
        if isinstance(stmt, ast.Assign)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    }
    if not values:
        raise VocabularyError(f"{class_name} in {source} declared no string members")
    return frozenset(values)


def app_root() -> Path:
    """The `app/` directory — this module lives in `app/scripts/`.

    The registry is resolved from THIS file's location, never from a linter's
    target directory: the vocabulary is a property of the codebase, not of
    whatever subtree is being linted. Deriving it from a caller-supplied root
    would make `lint_skuel.py --file adapters/` silently read a different (or
    missing) registry than a full sweep.
    """
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=8)
def load_vocabulary(root: Path | None = None) -> Vocabulary:
    """Read both enums. Cached — one parse per process.

    ``root`` defaults to :func:`app_root` and exists only so tests can point at
    a fixture tree; production callers pass nothing.
    """
    base = root if root is not None else app_root()
    return Vocabulary(
        relationships=_enum_member_values(
            base / ENUM_SOURCES[NameKind.RELATIONSHIP][0],
            ENUM_SOURCES[NameKind.RELATIONSHIP][1],
        ),
        labels=_enum_member_values(
            base / ENUM_SOURCES[NameKind.LABEL][0],
            ENUM_SOURCES[NameKind.LABEL][1],
        ),
    )


# =============================================================================
# Cypher name scanning
# =============================================================================

# --- The gate: two anchors, one predicate ------------------------------------
#
# Anchor 1 (_CYPHER_CONTEXT_RE) — paren/sigil-anchored markers, matched ANYWHERE
# in the fragment. Position carries no signal here, so each arm must earn its
# keep from shape alone: a paren or sigil that essentially never follows the
# keyword in prose (mirrors lint_skuel's CYPHER_MARKERS).
#
# The `MATCH path = (...)` form needs its own arm: the clause keyword is separated
# from the first pattern by a path variable, so the bare `MATCH (` anchor misses
# every named-path query (which is most multi-hop traversal Cypher).
# The typed-DDL arm matters: Neo4j 5 spells index creation
# `CREATE FULLTEXT|VECTOR|RANGE|TEXT|POINT|LOOKUP INDEX ... FOR (n:Label)`, so an
# anchor requiring INDEX to follow CREATE *immediately* silently skips every one
# of them — including the live fulltext DDL in neo4j_adapter.py (Codex P2 on #732).
# The `CALL db.` arm covers vector/fulltext search: those queries OPEN with the
# procedure call and only then filter (`YIELD node ... WHERE EXISTS((node)-[:X]->())`),
# so a clause-keyword-only anchor left every search builder unscanned (Codex P2 on
# #732). `CALL db.` is the same marker lint_skuel's own CYPHER_MARKERS uses.
#
# Those last three arms are the tell: each was added case-by-case after a form
# the paren anchor could not see turned up. The anchor's ceiling, not its
# tuning, is what keeps producing them.
_CYPHER_CONTEXT_PATTERN = (
    r"(?:MATCH|MERGE|CREATE)\s*\("
    r"|CREATE\s+(?:\w+\s+){0,2}?(?:INDEX|CONSTRAINT)\b"
    r"|(?:MATCH|MERGE|CREATE)\s+\w+\s*=\s*\("
    r"|UNWIND \$"
    r"|CALL\s+db\."
)


# Anchor 2 (CYPHER_LEADING_CLAUSES) — clause keywords that may BEGIN a Cypher
# statement, matched only at the HEAD of the fragment. Position is the signal, so
# these need no paren/sigil and the statement families anchor 1 structurally
# cannot see stop being invisible: `RETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs`
# carries a real relationship type and has no paren adjacent to its clause
# keyword, and `MATCH path = shortestPath((a:Entity)-[:X]-(b))` misses the
# `= (` arm because a function call sits between the `=` and the pattern.
#
# Three conditions keep prose out, and each is load-bearing:
#
#   * head position — a fragment that merely NAMES a clause mid-sentence
#     ("cascade DETACH DELETE (default False)") is prose; only real Cypher leads
#     with it. Docstrings are already exempt on the SKUEL030 side as inert
#     nodes; head position is what keeps the rule honest for the prose that is
#     assigned or passed rather than hung as a bare statement.
#   * UPPERCASE — every query in this tree writes clauses uppercase, so
#     requiring it costs nothing and drops the whole lowercase-English surface.
#   * followed by whitespace + an operand — rules out the bare HTTP verb
#     "DELETE", header names like "SET-COOKIE", and `RETURNS`/`CREATED`/
#     `WITHOUT`-style words that merely start with a clause name.
#
# Uppercase is required by DEFAULT, not always. The requirement is a prose
# guard, and prose risk is a property of the CALLER, not of Cypher: SKUEL030
# reads arbitrary Python string literals, where `"return 1 as ping"` really is
# ambiguous. A `.cypher` file has no prose to protect, so callers on that side
# pass `declared_cypher=True` and skip BOTH the uppercase requirement and the
# gate itself — see `scan_names`.
#
# The list is NOT pruned to "clauses that can carry vocabulary". Pruning would
# invent a second judgement call — and get it wrong: `DROP CONSTRAINT ... FOR
# (n:Label)` and `LOAD CSV ... MERGE (n:Label)` both carry names. One question,
# one answer: does this fragment lead with a Cypher clause?
#
# SKUEL021 asks the same question of `core/` and is growing the same anchor.
# Whichever lands second should import this tuple rather than keep a second copy
# — a hand-mirror in this codebase has drifted twice already (SKUEL013's
# 170-entry relationship mirror, and the SKUEL021 marker copy in
# test_core_utils_boundary.py). This module is the one both linters already
# import, so it is the side that should own it.
CYPHER_LEADING_CLAUSES: tuple[str, ...] = (
    "CALL",
    "CREATE",
    "DELETE",
    "DETACH DELETE",
    "DROP",
    "EXPLAIN",
    "FOREACH",
    "LOAD CSV",
    "MATCH",
    "MERGE",
    "OPTIONAL MATCH",
    "PROFILE",
    "REMOVE",
    "RETURN",
    "SET",
    "SHOW",
    "UNWIND",
    "USE",
    "WITH",
)

# Longest-first: a regex alternation is ORDERED, not longest-match, so a
# two-word clause must be offered before any single word it could be confused
# with. No such pair exists in the current list, which is exactly why the
# ordering is applied here rather than left to whoever adds the next clause.
_LEADING_CLAUSE_PATTERN = (
    r"^(?:" + "|".join(sorted(CYPHER_LEADING_CLAUSES, key=len, reverse=True)) + r")(?=\s)"
)


# `[r:TYPE]` / `[:TYPE]` / `[r:A|B*1..3]`. The body stops at the first `]`,
# whitespace, or brace — a property map or a var-length bound ends the name.
_REL_RE = re.compile(r"\[\s*(?:[A-Za-z_]\w*)?\s*:\s*([^\]\s{}]+)")

# `(n:Label)` / `(:Label)` / `(n:Entity:Ku)`. Same stopping rule.
_LABEL_RE = re.compile(r"\(\s*(?:[A-Za-z_]\w*)?\s*:\s*([^)\s{}]+)")

# One name inside a multi-name group — `A` and `B` of `(n:A:B)` or `[:A|B]`.
# Matched with positions so each name is reported where it actually is.
_NAME_PART_RE = re.compile(r"[A-Za-z_]\w*")

# Relationship types are UPPER_SNAKE; labels are PascalCase. Anything else
# (lowercase alias, digit-led fragment) is not vocabulary and is ignored.
_REL_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_LABEL_NAME_RE = re.compile(r"[A-Z][A-Za-z0-9]*")

# Marks where an interpolated expression stood in a reconstructed f-string.
# Chosen to survive the regexes above as an ordinary "word" character run while
# being impossible to write in source.
INTERPOLATION_SENTINEL = "\x00interp\x00"

# Var-length bounds (`*1..3`, `*`) trail the type name inside the brackets.
_VARLEN_RE = re.compile(r"\*.*$")

# Predicate position: `type(r) = 'X'` and `type(r) IN ['A', 'B']`. Vocabulary
# named here is just as load-bearing as vocabulary in a pattern — a typo makes the
# predicate unsatisfiable and the query returns nothing — but it is invisible to
# the pattern regexes above (Codex P2 on #732). Parameterized forms
# (`type(r) = $rel_type`) have no static name and simply do not match.
_TYPE_PREDICATE_PATTERN = r"\btype\s*\(\s*\w+\s*\)\s*(?:=|IN)\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\")"
_QUOTED_RE = re.compile(r"['\"]([^'\"]*)['\"]")

# Predicate position for labels: `WHERE n:Content`, `AND NOT a:Content`. Anchored
# on a boolean keyword so it cannot swallow Cypher map keys (`{uid: $x}`), the
# `CASE n:Label WHEN` form, or namespaced string values ("learn:extends_pattern").
_LABEL_PREDICATE_PATTERN = (
    r"\b(?:WHERE|AND|OR|NOT|WITH)\s+(?:NOT\s+)?[a-z_]\w*\s*:\s*([A-Z][A-Za-z0-9]*)"
)
# Under ignore_case the KEYWORDS relax but the NAME must not: a scoped `(?i:...)`
# group is what keeps `([A-Z][A-Za-z0-9]*)` strict. A blanket IGNORECASE here
# would make the capture accept lowercase and dissolve the PascalCase shape that
# distinguishes a label from a map key.
_LABEL_PREDICATE_PATTERN_I = (
    r"\b(?i:WHERE|AND|OR|NOT|WITH)\s+(?i:NOT\s+)?[A-Za-z_]\w*\s*:\s*([A-Z][A-Za-z0-9]*)"
)

# Mutation position for labels: `SET n:Ku`, `REMOVE n:Lesson`, `SET n:A:B`, and
# the comma-separated form `SET a:Ku, b:PathStep`. A label attached (or detached)
# here never appears in pattern position, so `_LABEL_RE` cannot see it — and a
# typo'd `SET n:Kuu` is worse than a typo'd read: it writes a label nothing will
# ever match.
#
# The clause's operand region is walked with BRACKET DEPTH, then split on its
# top-level commas, and each item judged independently. Depth is what a regex
# could not supply, and its absence produced the same finding six times over,
# each a narrower syntactic form: a comma separating items, a clause word inside
# a quoted value, `FINISH` and `OPTIONAL` missing from a hand-written terminator
# list, a trailing `;` / `)` / `}`, and finally a keyword nested in an expression
# — `SET n.ok = all(x IN $xs WHERE x > 0), n:Typo` ended at the inner `WHERE`
# (all Codex P2 on #831). A lookahead that matches a keyword ANYWHERE in the
# operand cannot tell a clause boundary from a word inside a sub-expression;
# nothing short of tracking structure can.
#
# Both halves need it. Anchoring on the FIRST item read `SET a:Ku, b:Typoo` as
# one item and never validated `b`; and Cypher freely mixes the two kinds of
# assignment (`SET n.title = $t, n:Ku`), so a walker stopping at the first
# non-label item is not enough either.
#
# `_NON_LEADING_CLAUSES` are the keywords that can END a SET clause without ever
# BEGINNING a statement, so they have no place in CYPHER_LEADING_CLAUSES. The
# rest is DERIVED from that tuple rather than hand-listed — hand-listing is what
# lost `FINISH` and `OPTIONAL`. Multi-word clauses contribute each of their
# words; a stray `CSV` or `DETACH` terminator costs nothing at depth 0.
_NON_LEADING_CLAUSES = (
    "FINISH", "LIMIT", "NEXT", "ON", "OPTIONAL", "ORDER",
    "SKIP", "UNION", "USING", "WHERE", "YIELD",
)  # fmt: skip
_MUTATION_TERMINATORS = tuple(
    sorted(
        {word for clause in CYPHER_LEADING_CLAUSES for word in clause.split()}
        | set(_NON_LEADING_CLAUSES)
    )
)
_MUTATION_HEAD_PATTERN = r"\b(?:SET|REMOVE)\s+"
_TERMINATOR_WORD_PATTERN = r"\b(?:" + "|".join(_MUTATION_TERMINATORS) + r")\b"
_OPENERS = "([{"
_CLOSERS = ")]}"

# The variable is case-neutral: Cypher allows `SET N:Ku` just as readily as
# `SET n:Ku` (Codex P2 on #831). The `SET`/`REMOVE` anchor plus the FULL-match
# requirement on each item is what keeps this precise — the lowercase-only shape
# `_LABEL_PREDICATE_RE` needs is load-bearing there because that regex has no
# clause anchor to lean on.
_LABEL_MUTATION_ITEM_RE = re.compile(r"\s*[A-Za-z_]\w*((?:\s*:\s*[A-Za-z_]\w*)+)\s*")


# --- Dialect table -----------------------------------------------------------
#
# Every regex anchored on a Cypher KEYWORD is compiled twice: once requiring
# uppercase (the default, for callers reading arbitrary Python strings where the
# requirement is a prose guard) and once relaxed (for callers whose input is
# Cypher by declaration). Selecting a whole dialect rather than threading a flag
# per regex is deliberate: the flag was first wired into the gate ALONE, and a
# half-threaded flag is a trap — CYP011 admitted a lowercase statement and then
# scanned it with case-sensitive scanners, so `set n:Bogus` still reported clean
# (Codex P2 on #831). A table makes "which regexes honour the mode" un-forgettable.
#
# `_LABEL_PREDICATE_PATTERN_I` is spelled out separately instead of compiled with
# a blanket IGNORECASE: it captures a NAME, and the strict `[A-Z][A-Za-z0-9]*`
# shape is what tells a label from a map key. The rest capture no name, so a
# blanket flag is safe for them.
@dataclass(frozen=True)
class _Dialect:
    """The keyword-anchored regexes, in one case mode."""

    context: re.Pattern[str]
    leading_clause: re.Pattern[str]
    mutation_head: re.Pattern[str]
    terminator: re.Pattern[str]
    type_predicate: re.Pattern[str]
    label_predicate: re.Pattern[str]


_STRICT = _Dialect(
    context=re.compile(_CYPHER_CONTEXT_PATTERN),
    leading_clause=re.compile(_LEADING_CLAUSE_PATTERN),
    mutation_head=re.compile(_MUTATION_HEAD_PATTERN),
    terminator=re.compile(_TERMINATOR_WORD_PATTERN),
    type_predicate=re.compile(_TYPE_PREDICATE_PATTERN),
    label_predicate=re.compile(_LABEL_PREDICATE_PATTERN),
)
_RELAXED = _Dialect(
    context=re.compile(_CYPHER_CONTEXT_PATTERN, re.IGNORECASE),
    leading_clause=re.compile(_LEADING_CLAUSE_PATTERN, re.IGNORECASE),
    mutation_head=re.compile(_MUTATION_HEAD_PATTERN, re.IGNORECASE),
    terminator=re.compile(_TERMINATOR_WORD_PATTERN, re.IGNORECASE),
    type_predicate=re.compile(_TYPE_PREDICATE_PATTERN, re.IGNORECASE),
    label_predicate=re.compile(_LABEL_PREDICATE_PATTERN_I),
)


def _dialect(declared_cypher: bool) -> _Dialect:
    return _RELAXED if declared_cypher else _STRICT


def mask_cypher_comments(text: str, *, keep_noqa: bool = False) -> str:
    """Blank out ``//`` line and ``/* */`` block comments, preserving offsets.

    Every masked character is replaced by a space and every newline is kept, so
    the result has the same length and the same line breaks as ``text`` — any
    offset or line number computed on the masked copy still points at the right
    place in the original.

    Quoted strings AND backtick-escaped identifiers are tracked, so neither a
    ``//`` inside a string literal (``'neo4j://host'``) nor one inside an escaped
    property name (`` n.`http://key` ``) is mistaken for a comment — masking a
    live clause away would turn this rule silent, which is the exact failure it
    exists to prevent. The two use different escapes: a backslash inside a
    quoted string, a DOUBLED backtick inside an identifier. Block comments do
    not nest, per the Cypher spec.

    ``keep_noqa`` leaves ``//`` comments carrying a ``noqa:`` marker intact —
    ``cypher_linter``'s statement splitter needs them to survive so a
    suppression stays attached to the line it suppresses. Vocabulary scanning
    wants no such carve-out: a comment cannot execute, so a name written in one
    is not load-bearing, which is the same reasoning that exempts docstrings.
    """
    return _mask_cypher(text, keep_noqa=keep_noqa, blank_strings=False)


def _blank(chars: list[str], start: int, end: int) -> None:
    """Space out ``chars[start:end]``, leaving newlines so line numbers hold."""
    for j in range(start, end):
        if chars[j] != "\n":
            chars[j] = " "


def _mask_cypher(text: str, *, keep_noqa: bool, blank_strings: bool) -> str:
    """One tokenizer, two masking policies. See ``mask_cypher_comments``.

    ``blank_strings`` additionally blanks the CONTENTS of quoted strings and
    backtick identifiers (the delimiters stay, so offsets and structure hold).
    Only the mutation scanner asks for it: it has to find where a `SET` clause
    ENDS, and an uppercase clause word inside a property value
    (``SET n.note = 'RETURN later', n:Typo``) would otherwise close the region
    early and hide every item after it. The other scanners must NOT use it —
    ``_TYPE_PREDICATE_RE`` reads vocabulary out of quoted operands on purpose.
    """
    chars = list(text)
    in_string: str | None = None
    string_body_start = 0
    i = 0
    while i < len(text):
        char = text[i]
        if in_string == "`":
            # Backtick identifiers escape by DOUBLING, not by backslash.
            if char == "`":
                if text[i + 1 : i + 2] == "`":
                    i += 2  # an escaped backtick — still inside the identifier
                    continue
                if blank_strings:
                    _blank(chars, string_body_start, i)
                in_string = None
        elif in_string is not None:
            if char == "\\":
                i += 2  # skip escaped character inside string
                continue
            if char == in_string:
                if blank_strings:
                    _blank(chars, string_body_start, i)
                in_string = None
        elif char in ("'", '"', "`"):
            in_string = char
            string_body_start = i + 1
        elif text[i : i + 2] == "//":
            end = text.find("\n", i)
            if end == -1:
                end = len(text)
            if not (keep_noqa and "noqa:" in text[i:end]):
                chars[i:end] = " " * (end - i)
            i = end
            continue
        elif text[i : i + 2] == "/*":
            end = text.find("*/", i + 2)
            end = len(text) if end == -1 else end + 2
            _blank(chars, i, end)
            i = end
            continue
        i += 1
    # An unterminated string runs to the end of the fragment.
    if blank_strings and in_string is not None:
        _blank(chars, string_body_start, len(text))
    return "".join(chars)


def _mutation_clause_items(text: str, dialect: _Dialect) -> list[tuple[str, int]]:
    """``(item text, offset)`` for every top-level item of every SET/REMOVE clause.

    Walks from each clause keyword tracking bracket depth, so structure decides
    the boundaries rather than a keyword's mere presence:

    - a clause keyword ends the region only at depth 0, leaving
      ``all(x IN $xs WHERE x > 0)`` intact;
    - a comma separates items only at depth 0, so a map literal's inner commas
      keep it a single (non-matching) item;
    - a closer that would take depth negative ends the region, which is what
      closes ``FOREACH (x IN xs | SET n:Ku)`` and ``CALL { ... SET n:Ku }``
      without needing to know what opened them;
    - ``;`` ends the region at depth 0.

    ``text`` must already be comment-masked and string-blanked, so no bracket,
    comma or keyword inside a comment or string literal can move the depth.
    """
    items: list[tuple[str, int]] = []
    for head in dialect.mutation_head.finditer(text):
        start = head.end()
        depth = 0
        item_start = start
        i = start
        while i < len(text):
            char = text[i]
            if char in _OPENERS:
                depth += 1
            elif char in _CLOSERS:
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                if char == ";":
                    break
                if char == ",":
                    items.append((text[item_start:i], item_start))
                    item_start = i + 1
                elif (
                    char.isalpha()
                    and _starts_a_clause(text, i)
                    and dialect.terminator.match(text, i)
                ):
                    break
            i += 1
        items.append((text[item_start:i], item_start))
    return items


def _starts_a_clause(text: str, i: int) -> bool:
    """False if position ``i`` is INSIDE the current item rather than after it.

    A keyword-shaped word that follows a ``.`` or a ``:`` is a property name or
    a label, not a new clause: ``SET n.order = 1, n:Bogus`` stopped at the
    property ``order``, and ``SET n:Return`` stopped inside the label, so every
    item from there on went unvalidated (Codex P2 on #831). The word-boundary
    the terminator regex asserts is satisfied by those separators, which is
    exactly why it cannot make this call on its own.

    Case is not what saves this: a PascalCase label like ``ORDER`` collides in
    strict mode too.
    """
    j = i - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    return j < 0 or text[j] not in ".:"


def _leads_with_cypher_clause(masked: str, dialect: _Dialect) -> bool:
    """True if ``masked`` opens with a Cypher clause keyword and has an operand.

    Takes ALREADY-masked text: comments have been blanked to spaces by then, so
    stripping leading whitespace is all that is needed to look past a planner
    hint in either comment form.

    The operand is looked for across the REST of the fragment, not just the rest
    of the clause's own line. Cypher wraps freely, and a query written as
    ``RETURN\\n  [(a)-[:X]->(b) | b] AS xs`` is no less real for it (Codex P2 on
    #831). Head position and uppercase still carry the prose guard; requiring
    the operand on the same line only ever added a wrapping restriction.
    """
    body = masked.lstrip()
    match = dialect.leading_clause.match(body)
    return match is not None and bool(body[match.end() :].strip())


def _is_cypher(masked: str, dialect: _Dialect) -> bool:
    """Both anchors, over already-masked text."""
    return dialect.context.search(masked) is not None or _leads_with_cypher_clause(masked, dialect)


def looks_like_cypher(fragment: str) -> bool:
    """True if ``fragment`` is admitted by either Cypher anchor.

    Anchor 1: a paren/sigil-anchored marker anywhere in the fragment.
    Anchor 2: a clause keyword at the fragment's head, followed by an operand.

    Comments are masked first, so neither anchor can be satisfied by
    commented-out Cypher. See the ``_CYPHER_CONTEXT_PATTERN`` /
    ``CYPHER_LEADING_CLAUSES`` block above for why one anchor cannot do both
    jobs.

    This is the predicate for text that MIGHT be Cypher. A caller holding text
    that IS Cypher — a `.cypher` file — should not consult it at all; see
    ``scan_names(declared_cypher=True)``.
    """
    return _is_cypher(mask_cypher_comments(fragment), _STRICT)


def scan_names(fragment: str, *, declared_cypher: bool = False) -> list[ScannedName]:
    """Recover every statically-known label / relationship type in ``fragment``.

    Covers both positions vocabulary can occupy:

    - **Pattern** — `(n:Label)`, `[r:TYPE]`, incl. multi-label `(n:A:B)` and
      alternation `[:A|B]`.
    - **Predicate** — `type(r) = 'X'`, `type(r) IN ['A','B']`, `WHERE n:Label`.
      A typo here makes the predicate unsatisfiable, which fails exactly as
      silently as a typo'd pattern.
    - **Mutation** — `SET n:Label`, `REMOVE n:Label`, incl. the comma-separated
      form `SET a:Ku, b:PathStep`. A label attached here is never written in
      pattern position, so the pattern regexes cannot see it, and a typo writes
      a label nothing will ever match.

    Comments are masked out first (offsets and line numbers preserved), so a
    name written in a `//` or `/* */` comment is not reported: a comment cannot
    execute, which is the same reasoning that exempts docstrings.

    Names touching an interpolation sentinel are skipped: `[:HAS_{domain}]`
    composes its type at runtime, so there is no static name to validate. That
    is a sanctioned below-boundary pattern, not a violation.

    **Known limit, deliberate: the PATTERN and PREDICATE scanners do not exclude
    quoted operands.** A name inside a Cypher string literal
    (``RETURN 'edge [:BOGUS] here'``) is scanned like any other. That has always
    been true of those regexes and is not blanket-fixable, because
    ``_TYPE_PREDICATE_RE`` reads vocabulary out of quoted operands *on purpose* —
    masking everywhere would trade a hypothetical false positive for a real,
    tested false negative. Zero sites in the tree hit it; the suppression comment
    is the escape hatch if one ever does. The MUTATION scanner is the exception
    and *is* quote-blind, because it alone needs to know where a clause ends.

    **Known limit, uniform: backtick-escaped vocabulary is not scanned.**
    ``(n:`Bogus`)``, ``[r:`BOGUS_EDGE`]``, ``SET n:`Bogus``` — none of the four
    position scanners has ever recovered one, because every name regex requires
    an identifier character right after the ``:``. Pinned by
    ``TestBacktickEscapedVocabulary`` so it stays a known limit rather than
    drifting into an assumed capability. Closing it means teaching all four
    positions at once; doing it for one would be the case-by-case patching this
    module's gate design argues against. Zero sites in the tree use the form —
    SKUEL labels and edge names are plain identifiers that never need escaping.
    """
    dialect = _dialect(declared_cypher)
    masked = mask_cypher_comments(fragment)
    if not declared_cypher and not _is_cypher(masked, dialect):
        return []
    unquoted = _mask_cypher(fragment, keep_noqa=False, blank_strings=True)

    found: list[ScannedName] = []

    def record(kind: NameKind, name: str, pos: int) -> None:
        found.append(ScannedName(kind=kind, value=name, line_offset=masked.count("\n", 0, pos)))

    # Pattern position
    for kind, pattern, name_re in (
        (NameKind.RELATIONSHIP, _REL_RE, _REL_NAME_RE),
        (NameKind.LABEL, _LABEL_RE, _LABEL_NAME_RE),
    ):
        for match in pattern.finditer(masked):
            # Strip the var-length bound BEFORE the interpolation check, not after.
            # `[:REQUIRES*1..{depth}]` interpolates only the DEPTH — the type name
            # is static and must still be validated. Testing the raw body first
            # saw the sentinel in the bound and skipped the whole relationship,
            # hiding every `*1..{depth}` traversal in the codebase (Codex P2 on #732).
            body = _VARLEN_RE.sub("", match.group(1))
            if INTERPOLATION_SENTINEL in body:
                continue
            # Same per-name positioning as the mutation scanner below: a
            # multi-label `(n:A:B)` recorded both at the group start.
            for part in _NAME_PART_RE.finditer(body):
                name = part.group()
                if name_re.fullmatch(name):
                    record(kind, name, match.start(1) + part.start())

    # Predicate position — type(r) = 'X' / type(r) IN ['A', 'B']
    for match in dialect.type_predicate.finditer(masked):
        operand = match.group(1)
        if INTERPOLATION_SENTINEL in operand:
            continue
        for quoted in _QUOTED_RE.finditer(operand):
            name = quoted.group(1).strip()
            if name and _REL_NAME_RE.fullmatch(name):
                record(NameKind.RELATIONSHIP, name, match.start(1) + quoted.start(1))

    # Predicate position — WHERE n:Label / AND NOT a:Label
    for match in dialect.label_predicate.finditer(masked):
        name = match.group(1)
        if _LABEL_NAME_RE.fullmatch(name):
            record(NameKind.LABEL, name, match.start(1))

    # Mutation position — SET n:Label / REMOVE n:A:B / SET a:Ku, b:PathStep.
    # Scanned over string-blanked text: this is the one scanner that has to know
    # where a clause ENDS, and an uppercase clause word inside a property value
    # would close the region early (Codex P2 on #831). Blanking is offset- and
    # length-preserving, so the positions recorded below stay truthful.
    for chunk, offset in _mutation_clause_items(unquoted, dialect):
        item = _LABEL_MUTATION_ITEM_RE.fullmatch(chunk)
        if item is None:
            continue
        # Each label at ITS OWN position, not the start of the colon group —
        # `SET n:Known:\n  Bogus` reported `Bogus` on `Known`'s line, which is
        # both a wrong location and a suppression that cannot be placed beside
        # the name it must suppress (Codex P2 on #831).
        for part in _NAME_PART_RE.finditer(item.group(1)):
            name = part.group()
            if _LABEL_NAME_RE.fullmatch(name):
                record(NameKind.LABEL, name, offset + item.start(1) + part.start())

    return found


def unregistered_names(
    fragment: str, vocabulary: Vocabulary, *, declared_cypher: bool = False
) -> list[ScannedName]:
    """Names in ``fragment`` that the enum registry does not know."""
    return [
        n
        for n in scan_names(fragment, declared_cypher=declared_cypher)
        if not vocabulary.is_registered(n)
    ]


# =============================================================================
# Python-side edge lists
# =============================================================================

# A bare edge name as it appears in a Python string: UPPER_SNAKE, nothing else.
# Anchored, so `"MATCH (n)"` and `"some prose"` cannot match.
_BARE_EDGE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# A pipe alternation written as a plain Python string — the `rel_types` spec
# shape (`"PARENT_OF|CHILD_OF"`). Two or more bare names, no Cypher syntax
# around them, so the pattern regexes above never see it.
_BARE_ALTERNATION_RE = re.compile(r"^[A-Z][A-Z0-9_]*(?:\|[A-Z][A-Z0-9_]*)+$")


def bare_alternation_parts(text: str) -> list[str] | None:
    """Split a bare ``"A|B|C"`` edge alternation, or ``None`` if not one."""
    if not _BARE_ALTERNATION_RE.match(text):
        return None
    return text.split("|")


def unregistered_edge_names(candidates: list[str], vocabulary: Vocabulary) -> list[str]:
    """Unregistered edge names in a group that is DEMONSTRABLY an edge list.

    The corroboration rule: a group of bare UPPER_SNAKE strings is treated as
    graph vocabulary only when at least one member is a registered
    ``RelationshipName``. That sibling is the evidence — without it, any list of
    UPPER_SNAKE constants (status codes, env-var names, header names) would be
    read as edges and the rule would drown in false positives.

    The deliberate trade: a group in which EVERY name is wrong is invisible.
    That is the safe direction to fail, and the three sites this rule was built
    from (``_INTENT_EDGE_SETS`` "practice"/"hierarchical", ``domain_queries``
    ``rel_types``) each carried a registered sibling.

    Returns ``[]`` when the group is not corroborated.
    """
    bare = [c for c in candidates if _BARE_EDGE_NAME_RE.match(c)]
    if len(bare) < 2:
        return []
    registered = [b for b in bare if b in vocabulary.relationships]
    if not registered:
        return []
    return [b for b in bare if b not in vocabulary.relationships]


def fstring_part_ids(tree: ast.AST) -> set[int]:
    """``id()``s of the string Constants that are literal PARTS of an f-string.

    ``ast.walk`` yields a JoinedStr *and* its Constant children. Scanning both
    double-counts, and worse, the children are torn fragments: `[:HAS_{domain}]`
    arrives as `[:HAS_` and `]`, and the first parses as a bogus relationship
    type `HAS_`. Callers scan the reconstructed whole (``render_fstring``) and
    skip every id in this set.
    """
    return {
        id(part)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for part in node.values
        if isinstance(part, ast.Constant)
    }


def render_fstring(node: ast.JoinedStr) -> str:
    """Flatten an f-string to text, interpolations replaced by the sentinel.

    Reconstructing the WHOLE f-string matters: walking its Constant children
    individually splits `[:HAS_{domain}]` into the fragments `[:HAS_` and `]`,
    and the first parses as a bogus relationship type `HAS_`.
    """
    return "".join(
        part.value
        if isinstance(part, ast.Constant) and isinstance(part.value, str)
        else INTERPOLATION_SENTINEL
        for part in node.values
    )
