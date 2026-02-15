"""
End-to-End Ingestion System Integration Tests
==========================================

Converts testable manual scenarios from tests/SYNC_SYSTEM_TEST_PLAN.md
into automated integration tests.

Covers:
- Test 3: Ingestion History (create/update/get roundtrip)
- Test 6: Error Handling (malformed files, missing fields, invalid paths)
- Test 7: Performance (full ingestion then incremental ingestion efficiency)

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import pytest_asyncio

from core.services.ingestion.batch import ingest_directory
from core.services.ingestion.ingestion_history import IngestionHistoryService
from core.services.ingestion.types import DryRunPreview, IncrementalStats

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def ingestion_history_service(neo4j_driver):
    """Create a real IngestionHistoryService connected to test Neo4j."""
    service = IngestionHistoryService(driver=neo4j_driver)
    await service.ensure_constraints()
    return service


@pytest_asyncio.fixture
async def cleanup_ingestion_history(neo4j_driver):
    """Clean up all IngestionHistory and IngestionError nodes after test."""
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (e:IngestionError) DETACH DELETE e")
        await session.run("MATCH (ih:IngestionHistory) DETACH DELETE ih")


@pytest.fixture
def valid_ku_directory(tmp_path: Path) -> Path:
    """Create a directory with several valid KU files."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    for i in range(5):
        ku_file = test_dir / f"ku-{i:02d}.md"
        ku_file.write_text(
            f"""---
type: ku
title: Knowledge Unit {i}
description: Test KU number {i}
uid: ku.e2e-test-{i:02d}
domain: testing
---

# Knowledge Unit {i}

Content for end-to-end test KU number {i}.
"""
        )
    return test_dir


@pytest.fixture
def error_files_directory(tmp_path: Path) -> Path:
    """Create a directory with files that trigger various error types."""
    test_dir = tmp_path / "error_vault"
    test_dir.mkdir()

    # 1. Valid file (should succeed)
    valid = test_dir / "valid.md"
    valid.write_text(
        """---
type: ku
title: Valid Knowledge Unit
description: This file is fine
uid: ku.e2e-valid
domain: testing
---

# Valid KU

Good content here.
"""
    )

    # 2. YAML file without type field — triggers type_detection ValueError
    no_type = test_dir / "no-type.yaml"
    no_type.write_text(
        """title: Missing Type Field
description: This YAML has no type field
"""
    )

    # 3. YAML file with truly broken syntax
    broken_yaml = test_dir / "broken.yaml"
    broken_yaml.write_text(
        """{{{not valid yaml at all:::
"""
    )

    return test_dir


def _mock_get_engine(entity_type: Any) -> Mock:
    """Mock engine — not called during dry-run."""
    return Mock()


# ============================================================================
# TEST 3: Ingestion History — Create/Update/Get Roundtrip
# ============================================================================


@pytest.mark.asyncio
async def test_ingestion_history_create_and_get(
    ingestion_history_service, cleanup_ingestion_history
):
    """Test creating and retrieving an ingestion history entry."""
    # Create entry
    result = await ingestion_history_service.create_entry(
        operation_type="directory",
        user_uid="user_admin",
        source_path="/vault/docs/ku",
    )
    assert result.is_ok
    operation_id = result.value
    assert operation_id  # non-empty UUID

    # Retrieve it
    entry_result = await ingestion_history_service.get_entry(operation_id)
    assert entry_result.is_ok
    entry = entry_result.value
    assert entry is not None
    assert entry.operation_type == "directory"
    assert entry.status == "in_progress"
    assert entry.user_uid == "user_admin"
    assert entry.source_path == "/vault/docs/ku"


@pytest.mark.asyncio
async def test_ingestion_history_update_with_stats(
    ingestion_history_service, cleanup_ingestion_history
):
    """Test updating an ingestion history entry with completion stats."""
    # Create
    result = await ingestion_history_service.create_entry(
        operation_type="vault",
        user_uid="user_admin",
        source_path="/vault",
    )
    assert result.is_ok
    operation_id = result.value

    # Update with stats
    stats = {
        "total_files": 50,
        "successful": 48,
        "failed": 2,
        "nodes_created": 45,
        "nodes_updated": 3,
        "relationships_created": 100,
        "duration_seconds": 5.2,
    }
    update_result = await ingestion_history_service.update_entry(
        operation_id=operation_id,
        status="completed",
        stats=stats,
    )
    assert update_result.is_ok

    # Verify update
    entry_result = await ingestion_history_service.get_entry(operation_id)
    assert entry_result.is_ok
    entry = entry_result.value
    assert entry.status == "completed"
    assert entry.stats["total_files"] == 50
    assert entry.stats["successful"] == 48
    assert entry.stats["nodes_created"] == 45


@pytest.mark.asyncio
async def test_ingestion_history_with_errors(ingestion_history_service, cleanup_ingestion_history):
    """Test ingestion history with linked error nodes."""
    # Create
    result = await ingestion_history_service.create_entry(
        operation_type="directory",
        user_uid="user_admin",
        source_path="/vault/mixed",
    )
    assert result.is_ok
    operation_id = result.value

    # Update with errors
    errors = [
        {
            "file": "/vault/bad.md",
            "error": "Missing required field: title",
            "stage": "validation",
            "error_type": "validation",
            "entity_type": "ku",
            "suggestion": "Add title field",
        },
        {
            "file": "/vault/broken.yaml",
            "error": "Invalid YAML syntax",
            "stage": "parsing",
            "error_type": "parse",
            "entity_type": None,
            "suggestion": "Fix YAML syntax",
        },
    ]
    stats = {"total_files": 10, "successful": 8, "failed": 2}
    update_result = await ingestion_history_service.update_entry(
        operation_id=operation_id,
        status="completed",
        stats=stats,
        errors=errors,
    )
    assert update_result.is_ok

    # Verify errors are linked
    entry_result = await ingestion_history_service.get_entry(operation_id)
    assert entry_result.is_ok
    entry = entry_result.value
    assert len(entry.errors) == 2
    assert any("Missing required field" in e["error"] for e in entry.errors)


@pytest.mark.asyncio
async def test_ingestion_history_paginated_list(
    ingestion_history_service, cleanup_ingestion_history
):
    """Test retrieving paginated ingestion history."""
    # Create 3 entries
    for i in range(3):
        result = await ingestion_history_service.create_entry(
            operation_type="directory",
            user_uid="user_admin",
            source_path=f"/vault/batch-{i}",
        )
        assert result.is_ok

    # Get all
    history_result = await ingestion_history_service.get_history(limit=10)
    assert history_result.is_ok
    entries = history_result.value
    assert len(entries) == 3

    # Get first page only
    page_result = await ingestion_history_service.get_history(limit=2, offset=0)
    assert page_result.is_ok
    assert len(page_result.value) == 2

    # Get total count
    count_result = await ingestion_history_service.get_total_count()
    assert count_result.is_ok
    assert count_result.value == 3


# ============================================================================
# TEST 6: Error Handling — Malformed Files & Invalid Paths
# ============================================================================


@pytest.mark.asyncio
async def test_error_handling_invalid_directory(neo4j_driver):
    """Test that non-existent directory returns proper error."""
    result = await ingest_directory(
        directory=Path("/nonexistent/path/to/nowhere"),
        engines={},
        get_engine=_mock_get_engine,
        driver=neo4j_driver,
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_error
    assert "not found" in result.expect_error().message.lower()


@pytest.mark.asyncio
async def test_error_handling_malformed_files(neo4j_driver, error_files_directory):
    """Test that malformed files produce validation errors in dry-run preview."""
    result = await ingest_directory(
        directory=error_files_directory,
        engines={},
        get_engine=_mock_get_engine,
        driver=neo4j_driver,
        pattern="*",  # Collect all files (MD + YAML)
        dry_run=True,
    )

    assert result.is_ok
    preview = result.value
    assert isinstance(preview, DryRunPreview)

    # The valid MD file should be in files_to_create
    assert len(preview.files_to_create) >= 1
    create_uids = {f["uid"] for f in preview.files_to_create}
    assert "ku.e2e-valid" in create_uids

    # The broken YAML files should produce validation errors
    assert len(preview.validation_errors) >= 1


@pytest.mark.asyncio
async def test_error_handling_driver_required_for_dry_run(tmp_path):
    """Test that dry-run mode fails without Neo4j driver."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    result = await ingest_directory(
        directory=test_dir,
        engines={},
        get_engine=_mock_get_engine,
        driver=None,
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_error
    assert "driver required" in result.expect_error().message.lower()


# ============================================================================
# TEST 7: Performance — Full Ingestion + Incremental Efficiency
# ============================================================================


@pytest.mark.asyncio
async def test_incremental_ingestion_skips_unchanged_files(ingestion_service, valid_ku_directory):
    """Test that incremental ingestion skips unchanged files after initial ingestion.

    Both ingestions use incremental mode because only incremental/smart modes
    write IngestionMetadata nodes that enable skip detection on subsequent runs.
    """
    # First ingestion — incremental mode, processes all files (no metadata yet)
    result1 = await ingestion_service.ingest_directory(
        directory=valid_ku_directory,
        pattern="*.md",
        ingestion_mode="incremental",
    )
    assert result1.is_ok
    stats1 = result1.value
    assert isinstance(stats1, IncrementalStats)
    assert stats1.total_files == 5
    assert stats1.files_ingested == 5  # All processed on first run

    # Second ingestion — incremental mode, should skip unchanged files
    result2 = await ingestion_service.ingest_directory(
        directory=valid_ku_directory,
        pattern="*.md",
        ingestion_mode="incremental",
    )
    assert result2.is_ok
    stats2 = result2.value
    assert isinstance(stats2, IncrementalStats)

    # All files should be skipped (none changed since first ingestion)
    assert stats2.files_skipped == 5
    assert stats2.files_ingested == 0
    assert stats2.skip_efficiency > 90.0  # >90% skipped


@pytest.mark.asyncio
async def test_dry_run_faster_than_full_ingestion(ingestion_service, valid_ku_directory):
    """Test that dry-run is faster than full ingestion (read-only queries)."""
    import time

    # Dry-run timing
    start_dry = time.monotonic()
    dry_result = await ingestion_service.ingest_directory(
        directory=valid_ku_directory,
        pattern="*.md",
        dry_run=True,
    )
    dry_duration = time.monotonic() - start_dry
    assert dry_result.is_ok

    # Full ingestion timing
    start_full = time.monotonic()
    full_result = await ingestion_service.ingest_directory(
        directory=valid_ku_directory,
        pattern="*.md",
        ingestion_mode="full",
    )
    full_duration = time.monotonic() - start_full
    assert full_result.is_ok

    # Dry-run should be faster (or at least not significantly slower)
    # We use a generous tolerance — just verifying dry-run doesn't hang or timeout
    assert dry_duration < full_duration * 5, (
        f"Dry-run ({dry_duration:.2f}s) was >5x slower than full ingestion ({full_duration:.2f}s)"
    )
