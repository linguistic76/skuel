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
_CYPHER_CONTEXT_RE = re.compile(
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
# Known, deliberate limit: lowercase Cypher (`"return 1 as ping"`) is not
# admitted. Matching case-insensitively would light up ordinary prose.
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
_LEADING_CLAUSE_RE = re.compile(
    r"^(?:" + "|".join(sorted(CYPHER_LEADING_CLAUSES, key=len, reverse=True)) + r")(?=\s)"
)

# `[r:TYPE]` / `[:TYPE]` / `[r:A|B*1..3]`. The body stops at the first `]`,
# whitespace, or brace — a property map or a var-length bound ends the name.
_REL_RE = re.compile(r"\[\s*(?:[A-Za-z_]\w*)?\s*:\s*([^\]\s{}]+)")

# `(n:Label)` / `(:Label)` / `(n:Entity:Ku)`. Same stopping rule.
_LABEL_RE = re.compile(r"\(\s*(?:[A-Za-z_]\w*)?\s*:\s*([^)\s{}]+)")

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
_TYPE_PREDICATE_RE = re.compile(
    r"\btype\s*\(\s*\w+\s*\)\s*(?:=|IN)\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\")"
)
_QUOTED_RE = re.compile(r"['\"]([^'\"]*)['\"]")

# Predicate position for labels: `WHERE n:Content`, `AND NOT a:Content`. Anchored
# on a boolean keyword so it cannot swallow Cypher map keys (`{uid: $x}`), the
# `CASE n:Label WHEN` form, or namespaced string values ("learn:extends_pattern").
_LABEL_PREDICATE_RE = re.compile(
    r"\b(?:WHERE|AND|OR|NOT|WITH)\s+(?:NOT\s+)?[a-z_]\w*:([A-Z][A-Za-z0-9]*)"
)

# Mutation position for labels: `SET n:Ku`, `REMOVE n:Lesson`, `SET n:A:B`. A
# label attached (or detached) here never appears in pattern position, so
# `_LABEL_RE` cannot see it — and a typo'd `SET n:Kuu` is worse than a typo'd
# read: it writes a label nothing will ever match. Anchored on the clause keyword
# and a lowercase variable so it cannot swallow `SET n.prop = $x` (dot, not
# colon) or a map literal.
_LABEL_MUTATION_RE = re.compile(r"\b(?:SET|REMOVE)\s+[a-z_]\w*((?::[A-Za-z_]\w*)+)")

# Cypher block comments (non-nesting, per the spec) — stripped before the head
# anchor looks for a leading clause. See `_leads_with_cypher_clause`.
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _leads_with_cypher_clause(fragment: str) -> bool:
    """True if ``fragment``'s first real line opens with a Cypher clause + operand.

    Leading blank lines and BOTH Cypher comment forms are skipped, so a query
    that opens with a planner-hint comment still anchors on its first real
    clause. Block comments have to be handled here rather than left to the
    caller: ``cypher_linter`` masks them out of ``.cypher`` files before this
    ever runs, but SKUEL030 hands over an AST string literal verbatim, so a
    ``/* hint */`` opener would otherwise reopen exactly the blind spot the head
    anchor exists to close.
    """
    for raw in _BLOCK_COMMENT_RE.sub(" ", fragment).split("\n"):
        head = raw.strip()
        if not head or head.startswith("//"):
            continue
        match = _LEADING_CLAUSE_RE.match(head)
        return match is not None and bool(head[match.end() :].strip())
    return False


def looks_like_cypher(fragment: str) -> bool:
    """True if ``fragment`` is admitted by either Cypher anchor.

    Anchor 1: a paren/sigil-anchored marker anywhere in the fragment.
    Anchor 2: a clause keyword at the fragment's head, followed by an operand.

    See the ``_CYPHER_CONTEXT_RE`` / ``CYPHER_LEADING_CLAUSES`` block above for
    why one anchor cannot do both jobs.
    """
    return _CYPHER_CONTEXT_RE.search(fragment) is not None or _leads_with_cypher_clause(fragment)


def scan_names(fragment: str) -> list[ScannedName]:
    """Recover every statically-known label / relationship type in ``fragment``.

    Covers both positions vocabulary can occupy:

    - **Pattern** — `(n:Label)`, `[r:TYPE]`, incl. multi-label `(n:A:B)` and
      alternation `[:A|B]`.
    - **Predicate** — `type(r) = 'X'`, `type(r) IN ['A','B']`, `WHERE n:Label`.
      A typo here makes the predicate unsatisfiable, which fails exactly as
      silently as a typo'd pattern.
    - **Mutation** — `SET n:Label`, `REMOVE n:Label`. A label attached here is
      never written in pattern position, so the pattern regexes cannot see it,
      and a typo writes a label nothing will ever match.

    Names touching an interpolation sentinel are skipped: `[:HAS_{domain}]`
    composes its type at runtime, so there is no static name to validate. That
    is a sanctioned below-boundary pattern, not a violation.

    **Known limit, deliberate: quoted operands are not excluded.** A name inside
    a Cypher string literal (``RETURN 'SET n:Bogus' AS example``) is scanned like
    any other, in every position — this has always been true of the pattern and
    label-predicate regexes and is not specific to the mutation scanner. It is
    not fixable by masking quotes, because the ``type(r) = 'X'`` scanner reads
    vocabulary out of quoted operands *on purpose*: masking would trade a
    hypothetical false positive for a real, tested false negative. Zero sites in
    the tree hit it; the suppression comment is the escape hatch if one ever
    does.
    """
    if not looks_like_cypher(fragment):
        return []

    found: list[ScannedName] = []

    def record(kind: NameKind, name: str, pos: int) -> None:
        found.append(ScannedName(kind=kind, value=name, line_offset=fragment.count("\n", 0, pos)))

    # Pattern position
    for kind, pattern, name_re, splitter in (
        (NameKind.RELATIONSHIP, _REL_RE, _REL_NAME_RE, "|"),
        (NameKind.LABEL, _LABEL_RE, _LABEL_NAME_RE, ":"),
    ):
        for match in pattern.finditer(fragment):
            # Strip the var-length bound BEFORE the interpolation check, not after.
            # `[:REQUIRES*1..{depth}]` interpolates only the DEPTH — the type name
            # is static and must still be validated. Testing the raw body first
            # saw the sentinel in the bound and skipped the whole relationship,
            # hiding every `*1..{depth}` traversal in the codebase (Codex P2 on #732).
            body = _VARLEN_RE.sub("", match.group(1))
            if INTERPOLATION_SENTINEL in body:
                continue
            for raw in body.split(splitter):
                name = raw.strip().strip(":")
                if name and name_re.fullmatch(name):
                    record(kind, name, match.start(1))

    # Predicate position — type(r) = 'X' / type(r) IN ['A', 'B']
    for match in _TYPE_PREDICATE_RE.finditer(fragment):
        operand = match.group(1)
        if INTERPOLATION_SENTINEL in operand:
            continue
        for quoted in _QUOTED_RE.finditer(operand):
            name = quoted.group(1).strip()
            if name and _REL_NAME_RE.fullmatch(name):
                record(NameKind.RELATIONSHIP, name, match.start(1) + quoted.start(1))

    # Predicate position — WHERE n:Label / AND NOT a:Label
    for match in _LABEL_PREDICATE_RE.finditer(fragment):
        name = match.group(1)
        if _LABEL_NAME_RE.fullmatch(name):
            record(NameKind.LABEL, name, match.start(1))

    # Mutation position — SET n:Label / REMOVE n:Label / SET n:A:B
    for match in _LABEL_MUTATION_RE.finditer(fragment):
        for raw in match.group(1).split(":"):
            name = raw.strip()
            if name and _LABEL_NAME_RE.fullmatch(name):
                record(NameKind.LABEL, name, match.start(1))

    return found


def unregistered_names(fragment: str, vocabulary: Vocabulary) -> list[ScannedName]:
    """Names in ``fragment`` that the enum registry does not know."""
    return [n for n in scan_names(fragment) if not vocabulary.is_registered(n)]


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
