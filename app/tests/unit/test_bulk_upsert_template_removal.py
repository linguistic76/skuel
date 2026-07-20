"""
Guard: the unreachable `.cypher` template system stays deleted (tranche 5).

`BulkUpsertBackend` once carried a file-backed template loader. Nothing could
reach it:

- ``ensure_constraints`` resolved ``{entity_label.lower()}_constraints.cypher``,
  but the files were named ``vectors.cypher`` / ``knowledge_units.cypher`` /
  ``life_principles.cypher``. No label has ever produced a matching filename, so
  the constraint path was a silent no-op for every entity type from day one.
- ``upsert_batch`` only loaded a named template when a caller passed
  ``template_name=``, and it had no callers at all. Its one historical caller,
  ``scripts/ingest_knowledge_vault.py``, was deleted in May 2026 (PR #56) as
  never-functional.

The templates were therefore the sole "writers" of the labels ``Vector``,
``State``, ``LifePrinciple``, ``JournalEntry`` and the edges ``MENTIONS_IN``,
``GROUNDED_BY``, ``FROM``, ``TO`` — none of which any environment can hold.

Uniqueness constraints are real, and they come from elsewhere: ``Neo4jAdapter``
bootstrap and ``Neo4jSchemaManager``. This module pins that the dead path does
not come back, not that constraints are unimportant.

See: docs/patterns/CYPHER_VOCABULARY_FINDINGS.md § 10
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.persistence.neo4j import bulk_upsert_backend
from adapters.persistence.neo4j.cypher_executor import CypherExecutor, CypherTemplate
from core.ports.ingestion_protocols import BulkUpsertOperations

ADAPTERS_ROOT = Path(bulk_upsert_backend.__file__).parent


def test_no_cypher_templates_directory() -> None:
    """The template tree is gone, not merely unused."""
    assert not (ADAPTERS_ROOT / "cypher_templates").exists()


def test_no_cypher_files_under_persistence_adapters() -> None:
    """A new `.cypher` file here would have no loader to reach it.

    Migrations and index DDL live under ``scripts/``; the persistence adapter
    package builds its Cypher in Python.
    """
    stray = list(ADAPTERS_ROOT.rglob("*.cypher"))
    assert stray == [], f"unreachable .cypher templates reintroduced: {stray}"


@pytest.mark.parametrize("name", ["ensure_constraints", "upsert_batch"])
def test_dead_backend_methods_are_gone(name: str) -> None:
    assert not hasattr(bulk_upsert_backend.BulkUpsertBackend, name)


@pytest.mark.parametrize("name", ["ensure_constraints", "upsert_batch"])
def test_dead_protocol_methods_are_gone(name: str) -> None:
    """The port must not re-declare what no implementation serves."""
    assert not hasattr(BulkUpsertOperations, name)


@pytest.mark.parametrize("name", ["_get_template", "_create_default_upsert_template"])
def test_template_loader_helpers_are_gone(name: str) -> None:
    assert not hasattr(bulk_upsert_backend, name)


def test_file_backed_template_loading_is_gone() -> None:
    """``CypherTemplate.from_file`` existed only to read those templates."""
    assert not hasattr(CypherTemplate, "from_file")


def test_constraint_execution_helper_is_gone() -> None:
    """``execute_constraints`` had exactly one caller, the dead constraint path."""
    assert not hasattr(CypherExecutor, "execute_constraints")


def test_live_bulk_write_surface_survives() -> None:
    """The deletion must not have taken the ingestion write path with it.

    These four are what ingestion actually calls; they build their Cypher in
    Python and never touched the template directory.
    """
    for name in (
        "upsert_nodes",
        "create_relationships",
        "upsert_with_relationships",
        "delete_batch",
    ):
        assert hasattr(bulk_upsert_backend.BulkUpsertBackend, name), name
        assert hasattr(BulkUpsertOperations, name), name
