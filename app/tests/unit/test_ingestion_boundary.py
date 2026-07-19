"""
Hexagonal boundary guard for core/ingestion/ (ADR-044).

core/ingestion/ holds only pure, transport-agnostic ingestion pieces
(ingestion_types, vectors). All Neo4j driver/session access and
the Cypher that uses it were relocated below the boundary into
adapters/persistence/neo4j/ (PRs #53/#54). This test locks that in: it fails fast
if any core/ingestion module reaches for the Neo4j driver again.

This complements the SKUEL021 lint rule (which bans raw Cypher *strings*); here we
ban the *execution primitives* — driver imports and session/transaction runs —
which a lint scoped to clause markers would not catch.
"""

from __future__ import annotations

from pathlib import Path

# Anchor on the imported package, not this file's location — the guard must
# keep scanning the real core/ tree no matter where it lives under tests/
# (core/ is a namespace package: __file__ is None, __path__ carries the dir).
import core as _core_pkg

_CORE = Path(next(iter(_core_pkg.__path__))).resolve()
INGESTION_DIR = _CORE / "ingestion"

# Neo4j driver/session execution primitives that must not appear in core/ingestion.
FORBIDDEN_PATTERNS = (
    "from neo4j import",
    "import neo4j",
    ".session(",
    "session.run(",
    "tx.run(",
    "driver.execute_query(",
)


def test_core_ingestion_has_no_neo4j_driver_or_session_access() -> None:
    """core/ingestion must stay above the hexagonal boundary — no driver/session."""
    offenders: list[str] = []
    # rglob (not glob) so modules added under future subdirectories of
    # core/ingestion/ can't bypass the boundary guard.
    for py_file in sorted(INGESTION_DIR.rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'", "*")):
                continue  # skip comments / docstring prose
            offenders.extend(
                f"{py_file.name}:{line_num}: {pattern!r} in {stripped!r}"
                for pattern in FORBIDDEN_PATTERNS
                if pattern in line
            )

    assert not offenders, (
        "core/ingestion/ must stay above the hexagonal boundary (ADR-044): no Neo4j "
        "driver/session access. Relocate the offending code to an adapter backend in "
        "adapters/persistence/neo4j/ behind a core/ports protocol.\n  - " + "\n  - ".join(offenders)
    )
