"""
Hexagonal boundary guard for core/utils/ (ADR-044).

core/utils/ holds pure, transport-agnostic helpers. Its one remaining raw-Cypher
leak — ``connection_fetcher.py``, which both *authored* and *executed* Cypher via
an injected ``QueryExecutor`` — was relocated below the boundary into
``adapters/persistence/neo4j/connection_fetch_backend.py`` behind the
``ConnectionFetchOperations`` port (``core/ports/connection_fetch_protocols.py``).
The pure data (``ConnectionConfig`` + the six per-domain constants) stayed in
core as ``core/utils/connection_configs.py``.

This test locks that in. It predates the SKUEL021 lint gate covering
``core/utils/``: a naive line-scan widening would have false-positived on the
legitimate docstring Cypher *examples* that live in this directory
(processor_functions.py, neo4j_mapper.py, result_simplified.py, decorators.py,
error_boundary.py), so we guarded structurally with AST instead — docstrings and
comments are not Call / Import nodes, and docstring string literals are skipped
by identity, so they cannot trip this check.

SKUEL021 has since been taught the same docstring-aware AST technique and its
gate widened to all of ``core/`` (it now lint-enforces the raw-Cypher ban here).
This test is intentionally KEPT for its execution-primitive bans — neo4j driver
imports and ``.execute_query(`` calls, which SKUEL021 does not cover.

The direction of the borrowing has since reversed. This file used to hand-copy
SKUEL021's Cypher markers, and the copy drifted: it sat a marker behind
(``OPTIONAL MATCH path``) and never learned the statement-head anchor, so the
sub-check was quietly weaker than the rule it claimed to mirror. Borrowing only
the *predicate* then proved insufficient too — the two disagreed on f-strings,
because judging a torn ``Constant`` is not the same as judging the rendered
whole. Detection now comes from ``SkuelLinter.iter_authored_cypher``, walk and
all, so agreement is structural rather than carefully maintained; the
RELATIONSHIP_NAMES mirror got the same resolution. The execution-primitive bans
stay local and independent — they are this file's unduplicated value.

Banned in core/utils:
  - neo4j driver imports (``import neo4j`` / ``from neo4j import ...``). The
    ``neo4j.exceptions`` exception classes are the one sanctioned exemption
    (exception_types.py, per ADR-063) — they are not the driver/session.
  - query-execution calls (``*.execute_query(...)`` — the QueryExecutor primitive)
  - raw Cypher in string literals that are *used* (assigned, passed, returned).
    Inert bare string-expression statements — docstrings and ``USAGE EXAMPLES``
    blocks that legitimately quote Cypher — are skipped by identity.

Done (follow-up landed): SKUEL021's checker is now AST-based with the same
docstring-skip technique, and its gate covers all of ``core/`` — so the
raw-Cypher ban here is lint-enforced too. This test pairs that (derived) check
with the execution-primitive bans, which SKUEL021 does not cover.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Anchor on the imported package, not this file's location — the guard must
# keep scanning the real core/ tree no matter where it lives under tests/
# (core/ is a namespace package: __file__ is None, __path__ carries the dir).
import core as _core_pkg

_CORE = Path(next(iter(_core_pkg.__path__))).resolve()
UTILS_DIR = _CORE / "utils"

# scripts/ has no __init__.py — add it to sys.path for import.
#
# Raw-Cypher detection is SkuelLinter's, walk and all (`iter_authored_cypher`).
# This file used to hand-copy the marker tuple, and the copy drifted exactly the
# way the RELATIONSHIP_NAMES mirror did before it was deleted (see
# `TestRelationshipNamesDrift`): it fell a marker behind (`OPTIONAL MATCH path`).
# Borrowing only the predicate was not enough either — the two then disagreed on
# f-strings, because judging a torn `Constant` is not the same as judging the
# rendered whole (Codex, PR #829). Sharing the traversal is what makes agreement
# structural. The execution-primitive bans below stay local; they are this
# file's real, unduplicated value.
sys.path.insert(0, str(_CORE.parent / "scripts"))

from lint_skuel import SkuelLinter  # type: ignore[import-not-found]  # noqa: E402

# Query-execution method names that signal Cypher running from core/utils.
# ``execute_query`` is Neo4j-specific (the QueryExecutor port) — banning it does
# not risk catching unrelated calls the way a bare ``.run(`` / ``.session(``
# would in a large directory.
EXECUTION_METHODS = frozenset({"execute_query"})

# The one sanctioned neo4j import in core/ (ADR-063): exception_types.py pulls
# the SDK exception *classes* (not the driver/session) to build NEO4J_EXCEPTIONS.
_SANCTIONED_NEO4J_MODULE = "neo4j.exceptions"


def _is_banned_neo4j_module(module: str) -> bool:
    """True if ``module`` is the neo4j driver/session (not the sanctioned exceptions)."""
    if module == _SANCTIONED_NEO4J_MODULE or module.startswith(_SANCTIONED_NEO4J_MODULE + "."):
        return False
    return module == "neo4j" or module.startswith("neo4j.")


def _inert_string_constant_ids(tree: ast.AST) -> set[int]:
    """Return id()s of string Constants that are inert bare-expression statements.

    Docstrings *and* mid-module ``USAGE EXAMPLES`` blocks are bare string
    statements — never assigned, passed, or executed — and legitimately quote
    Cypher. They are skipped by identity so the raw-Cypher-string check only
    fires on Cypher that is actually *used*.
    """
    inert_ids: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            inert_ids.add(id(node.value))
    return inert_ids


def _scan_file(py_file: Path) -> list[str]:
    """Return boundary offenders found in a single core/utils module."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    inert_ids = _inert_string_constant_ids(tree)
    offenders: list[str] = [
        f"{py_file.name}:{node.lineno}: raw Cypher in a string literal"
        for node, _marker in SkuelLinter.iter_authored_cypher(tree, inert_ids)
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                f"{py_file.name}:{node.lineno}: neo4j driver import ('{alias.name}')"
                for alias in node.names
                if _is_banned_neo4j_module(alias.name)
            )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if _is_banned_neo4j_module(mod):
                offenders.append(f"{py_file.name}:{node.lineno}: neo4j driver import ('{mod}')")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in EXECUTION_METHODS
        ):
            offenders.append(
                f"{py_file.name}:{node.lineno}: query-execution call ('.{node.func.attr}(...)')"
            )

    return offenders


def test_core_utils_has_no_raw_cypher_or_query_execution() -> None:
    """core/utils must stay above the hexagonal boundary — no Cypher, no execution."""
    offenders: list[str] = []
    # rglob (not glob) so modules added under future subdirectories of
    # core/utils/ can't bypass the boundary guard.
    for py_file in sorted(UTILS_DIR.rglob("*.py")):
        offenders.extend(_scan_file(py_file))

    assert not offenders, (
        "core/utils/ must stay above the hexagonal boundary (ADR-044): no raw Cypher "
        "and no query execution. Relocate the offending code to an adapter backend in "
        "adapters/persistence/neo4j/ behind a core/ports protocol (see "
        "ConnectionFetchBackend / ConnectionFetchOperations for the pattern).\n  - "
        + "\n  - ".join(offenders)
    )


def test_scan_agrees_with_skuel021_on_composite_strings(tmp_path: Path) -> None:
    """The guard and the rule must not disagree on f-strings or concatenation.

    Sharing only the predicate was not enough: judging a torn ``Constant`` is
    not the same as judging the rendered whole, so this guard used to report
    prose f-strings and miss real ones (Codex, PR #829). Sharing the traversal
    makes agreement structural — this pins it.
    """
    cases = [
        # (source, expect_offender)
        ('mode = "x"\nmsg = f"cascade {mode} DETACH DELETE (default False)"\n', False),
        ('mode = "x"\nmsg = "cascade " + mode + " DETACH DELETE (default False)"\n', False),
        ('v = 1\nq = f"RETURN {v}"\nrun(q)\n', True),
        ('p = "n.uid"\nq = "RETURN " + p\nrun(q)\n', True),
        ('uid = 1\nq = f"MATCH (n) WHERE n.id = {uid} RETURN n"\nrun(q)\n', True),
        ('method = "DELETE"\n', False),
    ]
    for index, (source, expect_offender) in enumerate(cases):
        module = tmp_path / f"case_{index}.py"
        module.write_text(source, encoding="utf-8")
        cypher = [o for o in _scan_file(module) if "raw Cypher" in o]
        assert bool(cypher) is expect_offender, f"case {index} disagreed: {source!r} -> {cypher}"
