"""
Hexagonal boundary guard for core/utils/ (ADR-044).

core/utils/ holds pure, transport-agnostic helpers. Its one remaining raw-Cypher
leak — ``connection_fetcher.py``, which both *authored* and *executed* Cypher via
an injected ``QueryExecutor`` — was relocated below the boundary into
``adapters/persistence/neo4j/connection_fetch_backend.py`` behind the
``ConnectionFetchOperations`` port (``core/ports/connection_fetch_protocols.py``).
The pure data (``ConnectionConfig`` + the six per-domain constants) stayed in
core as ``core/utils/connection_configs.py``.

This test locks that in. The SKUEL021 lint gate does NOT cover ``core/utils/``,
and a naive line-scan widening would false-positive on the legitimate docstring
Cypher *examples* that live in this directory (processor_functions.py,
neo4j_mapper.py, result_simplified.py, decorators.py, error_boundary.py). So we
guard structurally with AST instead: docstrings and comments are not Call /
Import nodes, and docstring string literals are skipped by identity — they
cannot trip this check.

Banned in core/utils:
  - neo4j driver imports (``import neo4j`` / ``from neo4j import ...``). The
    ``neo4j.exceptions`` exception classes are the one sanctioned exemption
    (exception_types.py, per ADR-063) — they are not the driver/session.
  - query-execution calls (``*.execute_query(...)`` — the QueryExecutor primitive)
  - raw Cypher in string literals that are *used* (assigned, passed, returned).
    Inert bare string-expression statements — docstrings and ``USAGE EXAMPLES``
    blocks that legitimately quote Cypher — are skipped by identity.

Follow-up (noted): teach SKUEL021's checker to skip docstring/string-literal
regions, then widen its ``is_below_boundary`` gate to include ``/core/utils/``
for lint-level (not just test-level) structural enforcement.
"""

from __future__ import annotations

import ast
from pathlib import Path

UTILS_DIR = Path(__file__).resolve().parents[1] / "core" / "utils"

# High-signal Cypher clause markers — mirror SKUEL021; these essentially never
# appear in prose.
CYPHER_MARKERS = (
    "MATCH (",
    "MERGE (",
    "OPTIONAL MATCH (",
    "CREATE (",
    "UNWIND $",
    "CALL db.",
)

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
    offenders: list[str] = []

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
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in inert_ids
            and any(marker in node.value for marker in CYPHER_MARKERS)
        ):
            offenders.append(f"{py_file.name}:{node.lineno}: raw Cypher in a string literal")

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
