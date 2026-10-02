"""Every graph write the vault doors make says what keeps it the vault owner's.

The link-writer census (``tests/unit/services/test_link_writer_census.py``) holds the
app's edge writers under ``core/services/``. The vault's writers are the ingestion
backends' methods, called from ``core/services/ingestion/`` — a vault file reaches the
graph through them, so each call site is held here to the rule that keeps a file in
one user's vault from writing into another user's graph (ADR-070 Decision 11). A call site this
census does not know fails until it is named with its answer.
"""

from __future__ import annotations

import ast
from pathlib import Path

_INGESTION = Path(__file__).resolve().parents[4] / "core" / "services" / "ingestion"

# The ingestion backends' graph writes, plus the UserEntry door the vault hands its
# notes to.
_WRITERS = {
    "ingest_edge",
    "upsert_nodes",
    "create_relationships",
    "upsert_with_relationships",
    "refresh_moc_organizes",
    "create_group_ownership",
    "create_entry",
}

# ``"<file>::<function>::<call>"`` -> what keeps the write the vault owner's.
ADMITTED: dict[str, str] = {
    "batch.py::_ingest_edge_batch::write_backend.ingest_edge": (
        "a personal vault's Edge file is refused at parse (vault_policy); the writer "
        "binds both ends to :Entity, so no Edge file writes an access edge"
    ),
    "unified_ingestion_service.py::ingest_edge::self._write_backend.ingest_edge": (
        "reached only from ingest_file, after its vault-kind refusal — same writer"
    ),
    "unified_ingestion_service.py::ingest_file::self.ingest_edge": (
        "after vault_refusal(kind, None, data)"
    ),
    "batch.py::ingest_directory::bulk_backend.upsert_nodes": (
        "the node template's owner gate: a node someone else owns takes no write"
    ),
    "unified_ingestion_service.py::ingest_file::self._bulk_backend.upsert_with_relationships": (
        "the same owner gate; refused rows write no edge; personal targets admitted first"
    ),
    "batch.py::ingest_directory::bulk_backend.create_relationships": (
        "personal targets admitted before phase 1 (admit_frontmatter_targets); "
        "refused rows dropped from the pass"
    ),
    "unified_ingestion_service.py::_apply_moc_links::self._write_backend.refresh_moc_organizes": (
        "targets resolve only through the MOC's own vault's tracker rows"
    ),
    "unified_ingestion_service.py::ingest_file::self._write_backend.create_group_ownership": (
        "a Group file is refused in a personal vault; its owner is the vault's "
        "resolved owner; a refused upsert returns before it"
    ),
    "user_entry_ingestion.py::ingest_user_entry::user_entry_service.create_entry": (
        "UserEntryBackend.upsert gates its write on the existing owner"
    ),
    "user_entry_ingestion.py::_file_submission_copy::user_entry_service.create_entry": (
        "a frozen copy is always a fresh node the vault owner owns"
    ),
}


def _call_sites() -> set[str]:
    sites: set[str] = set()
    for path in sorted(_INGESTION.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _WRITERS
                ):
                    sites.add(f"{path.name}::{function.name}::{ast.unparse(node.func)}")
    return sites


def test_every_vault_writer_is_named() -> None:
    unknown = sorted(_call_sites() - ADMITTED.keys())
    assert not unknown, (
        "a vault write with no stated admission — name what keeps it the vault "
        f"owner's in ADMITTED: {unknown}"
    )


def test_no_stale_census_rows() -> None:
    stale = sorted(ADMITTED.keys() - _call_sites())
    assert not stale, f"census rows that name no call site any more: {stale}"
