"""Every CALL subquery below the persistence boundary carries a variable scope clause.

Neo4j 5.23+ (and the whole calendar line SKUEL runs on — AuraDB and the
``neo4j:2026.x`` integration container alike) deprecates the importing-``WITH``
subquery form::

    CALL {            # deprecated — the server warns on EVERY execution
      WITH n, props
      ...
    }

in favour of the variable scope clause::

    CALL (n, props) { ... }      # correlated
    CALL () { ... }              # uncorrelated

The warning is not cosmetic: it fires as a ``FeatureDeprecationWarning``
notification on every vault sync and every cross-domain read that hits one of
these queries, and the form is scheduled for removal. This guard scans the
source text of every module under ``adapters/persistence`` — the one place
Cypher may be authored (SKUEL021) — so a new or reverted ``CALL {`` cannot land
quietly. A per-query shape test (``test_zpd_backend_query_shape.py``) pins the
positive form for one backend; this is the tree-wide negative.

An f-string template doubles the brace (``CALL {{``); the regex below matches
that spelling too, since the first ``{`` still directly follows ``CALL``.
"""

from __future__ import annotations

import re
from pathlib import Path

PERSISTENCE_ROOT = Path(__file__).resolve().parents[3] / "adapters" / "persistence"

# `CALL` followed only by whitespace and an opening brace = no scope clause.
# `CALL (...) {` has a parenthesised list between the keyword and the brace and
# does not match; `CALL db.index...` / `CALL apoc...` have no brace and do not
# match either.
_UNSCOPED_CALL_SUBQUERY = re.compile(r"\bCALL\s*\{")


def _cypher_bearing_sources() -> list[Path]:
    files = sorted(
        p
        for suffix in ("*.py", "*.cypher")
        for p in PERSISTENCE_ROOT.rglob(suffix)
        if "__pycache__" not in p.parts
    )
    assert files, f"no sources found under {PERSISTENCE_ROOT}"
    return files


def test_no_call_subquery_without_variable_scope_clause() -> None:
    offenders: list[str] = []
    for path in _cypher_bearing_sources():
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _UNSCOPED_CALL_SUBQUERY.search(line):
                offenders.append(
                    f"{path.relative_to(PERSISTENCE_ROOT.parent.parent)}:{line_no}: {line.strip()}"
                )
    assert not offenders, (
        "CALL subquery without a variable scope clause (deprecated importing-WITH form). "
        "Write `CALL (vars) { ... }` — or `CALL () { ... }` when uncorrelated — and drop "
        "the importing WITH:\n  " + "\n  ".join(offenders)
    )


def test_guard_regex_distinguishes_the_two_spellings() -> None:
    """The regex itself is the guard — pin what it does and does not catch."""
    assert _UNSCOPED_CALL_SUBQUERY.search("CALL {\n  WITH n")
    assert _UNSCOPED_CALL_SUBQUERY.search("CALL {{\n  WITH n")  # f-string template
    assert _UNSCOPED_CALL_SUBQUERY.search("  CALL{ RETURN 1 }")
    assert not _UNSCOPED_CALL_SUBQUERY.search("CALL (n, props) {")
    assert not _UNSCOPED_CALL_SUBQUERY.search("CALL () {{")
    assert not _UNSCOPED_CALL_SUBQUERY.search("CALL db.index.vector.queryNodes($index, $k, $vec)")
    assert not _UNSCOPED_CALL_SUBQUERY.search("OPTIONAL CALL (p) {")
