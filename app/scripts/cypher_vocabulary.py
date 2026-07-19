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

# A fragment is only scanned if it looks like real Cypher. Paren/sigil-anchored
# markers essentially never appear in prose (mirrors lint_skuel's CYPHER_MARKERS).
# The `MATCH path = (...)` form needs its own arm: the clause keyword is separated
# from the first pattern by a path variable, so the bare `MATCH (` anchor misses
# every named-path query (which is most multi-hop traversal Cypher).
# The typed-DDL arm matters: Neo4j 5 spells index creation
# `CREATE FULLTEXT|VECTOR|RANGE|TEXT|POINT|LOOKUP INDEX ... FOR (n:Label)`, so an
# anchor requiring INDEX to follow CREATE *immediately* silently skips every one
# of them — including the live fulltext DDL in neo4j_adapter.py (Codex P2 on #732).
_CYPHER_CONTEXT_RE = re.compile(
    r"(?:MATCH|MERGE|CREATE)\s*\("
    r"|CREATE\s+(?:\w+\s+){0,2}?(?:INDEX|CONSTRAINT)\b"
    r"|(?:MATCH|MERGE|CREATE)\s+\w+\s*=\s*\("
    r"|UNWIND \$"
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


def looks_like_cypher(fragment: str) -> bool:
    """True if ``fragment`` contains an anchored Cypher clause marker."""
    return _CYPHER_CONTEXT_RE.search(fragment) is not None


def scan_names(fragment: str) -> list[ScannedName]:
    """Recover every statically-known label / relationship type in ``fragment``.

    Names touching an interpolation sentinel are skipped: `[:HAS_{domain}]`
    composes its type at runtime, so there is no static name to validate. That
    is a sanctioned below-boundary pattern, not a violation.
    """
    if not looks_like_cypher(fragment):
        return []

    found: list[ScannedName] = []
    for kind, pattern, name_re, splitter in (
        (NameKind.RELATIONSHIP, _REL_RE, _REL_NAME_RE, "|"),
        (NameKind.LABEL, _LABEL_RE, _LABEL_NAME_RE, ":"),
    ):
        for match in pattern.finditer(fragment):
            body = match.group(1)
            if INTERPOLATION_SENTINEL in body:
                continue
            line_offset = fragment.count("\n", 0, match.start(1))
            for raw in body.split(splitter):
                name = _VARLEN_RE.sub("", raw.strip().strip(":"))
                if name and name_re.fullmatch(name):
                    found.append(ScannedName(kind=kind, value=name, line_offset=line_offset))
    return found


def unregistered_names(fragment: str, vocabulary: Vocabulary) -> list[ScannedName]:
    """Names in ``fragment`` that the enum registry does not know."""
    return [n for n in scan_names(fragment) if not vocabulary.is_registered(n)]


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
