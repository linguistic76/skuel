"""
Integration Tests for Ingestion Dry-Run Mode
=============================================

Tests the dry-run preview functionality with real Neo4j and real file parsing.
These tests replace the 6 skipped unit tests that failed due to @patch creating
unpicklable MagicMock objects in async contexts (asyncio.to_thread).

The dry-run path only READS from Neo4j via check_existing_entities() — it never writes.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from pathlib import Path

from core.services.ingestion.batch import ingest_directory
from core.services.ingestion.types import DryRunPreview, IngestionStats

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_ku_file(tmp_path: Path) -> Path:
    """Create a valid KU markdown file for testing."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    ku_file = test_dir / "test-knowledge.md"
    ku_file.write_text(
        """---
type: ku
title: Test Knowledge Unit
description: A test KU for dry-run integration testing
uid: ku.test-knowledge-dry-run
domain: testing
---

# Test Knowledge Unit

This is test content for integration testing of the dry-run mode.
It has enough content to pass validation checks.
"""
    )
    return test_dir


@pytest.fixture
def two_ku_files(tmp_path: Path) -> Path:
    """Create two valid KU files — one for create, one for update detection."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    # File that will be detected as "new" (no matching node in Neo4j)
    new_file = test_dir / "new-topic.md"
    new_file.write_text(
        """---
type: ku
title: Brand New Topic
description: This KU does not exist in Neo4j
uid: ku.brand-new-topic
domain: testing
---

# Brand New Topic

Content for a brand new knowledge unit.
"""
    )

    # File that will be detected as "existing" (pre-created node)
    existing_file = test_dir / "existing-topic.md"
    existing_file.write_text(
        """---
type: ku
title: Existing Topic Updated
description: This KU already exists in Neo4j
uid: ku.existing-topic-dry-run
domain: testing
---

# Existing Topic

Content for an existing knowledge unit that would be updated.
"""
    )

    return test_dir


@pytest.fixture
def validation_error_files(tmp_path: Path) -> Path:
    """Create one valid file and one with a validation error."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    # Valid file
    valid_file = test_dir / "valid-ku.md"
    valid_file.write_text(
        """---
type: ku
title: Valid KU
description: Has all required fields
uid: ku.valid-ku
domain: testing
---

# Valid KU

This KU has proper content.
"""
    )

    # YAML file without type field — triggers type_detection ValueError
    invalid_file = test_dir / "invalid-entity.yaml"
    invalid_file.write_text(
        """description: No type field at all
title: Missing Type
"""
    )

    return test_dir


@pytest.fixture
def ten_ku_files(tmp_path: Path) -> Path:
    """Create 10 valid KU files for batch efficiency testing."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    for i in range(10):
        ku_file = test_dir / f"topic-{i:02d}.md"
        ku_file.write_text(
            f"""---
type: ku
title: Topic {i}
description: Test topic number {i}
uid: ku.batch-test-{i:02d}
domain: testing
---

# Topic {i}

Content for batch test topic {i}.
"""
        )

    return test_dir


@pytest_asyncio.fixture
async def pre_existing_ku(neo4j_driver):
    """Create a Entity nodes in Neo4j that will be detected as 'existing' by dry-run."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (k:Entity {uid: $uid})
            ON CREATE SET k.title = $title, k.created_at = datetime()
            """,
            uid="ku.existing-topic-dry-run",
            title="Existing Topic",
        )

    yield "ku.existing-topic-dry-run"

    # Cleanup
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (k:Entity {uid: $uid}) DETACH DELETE k",
            uid="ku.existing-topic-dry-run",
        )


# ============================================================================
# HELPER
# ============================================================================


def _mock_get_engine(entity_type: Any) -> Mock:
    """Provide a mock engine (not used in dry-run path)."""
    return Mock()


# ============================================================================
# TEST 1: Dry-run returns DryRunPreview with real file parsing
# ============================================================================


@pytest.mark.asyncio
async def test_dry_run_returns_preview(neo4j_driver, sample_ku_file):
    """Test that dry-run mode returns DryRunPreview with real Neo4j and real file parsing."""
    result = await ingest_directory(
        directory=sample_ku_file,
        engines={},
        get_engine=_mock_get_engine,
        driver=neo4j_driver,
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_ok
    preview = result.value
    assert isinstance(preview, DryRunPreview)
    assert preview.total_files == 1
    assert len(preview.files_to_create) == 1
    assert preview.files_to_create[0]["uid"] == "a.test-knowledge-dry-run"
    assert preview.files_to_create[0]["entity_type"] == "article"


# ============================================================================
# TEST 2: Dry-run categorizes creates vs updates
# ============================================================================


@pytest.mark.asyncio
async def test_dry_run_categorizes_creates_and_updates(neo4j_driver, two_ku_files, pre_existing_ku):
    """Test that dry-run correctly categorizes files as creates vs updates."""
    result = await ingest_directory(
        directory=two_ku_files,
        engines={},
        get_engine=_mock_get_engine,
        driver=neo4j_driver,
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_ok
    preview = result.value
    assert isinstance(preview, DryRunPreview)

    # One file is new, one already exists in Neo4j
    assert len(preview.files_to_create) == 1
    assert len(preview.files_to_update) == 1

    create_uids = {f["uid"] for f in preview.files_to_create}
    update_uids = {f["uid"] for f in preview.files_to_update}

    assert "ku.brand-new-topic" in create_uids
    assert "ku.existing-topic-dry-run" in update_uids


# ============================================================================
# TEST 3: Dry-run includes validation errors
# ============================================================================


@pytest.mark.asyncio
async def test_dry_run_includes_validation_errors(neo4j_driver, validation_error_files):
    """Test that dry-run includes validation errors for malformed files."""
    result = await ingest_directory(
        directory=validation_error_files,
        engines={},
        get_engine=_mock_get_engine,
        driver=neo4j_driver,
        pattern="*",  # Collect all files (MD + YAML)
        dry_run=True,
    )

    assert result.is_ok
    preview = result.value
    assert isinstance(preview, DryRunPreview)

    # One valid MD file parsed, one YAML file failed (no type field)
    assert len(preview.files_to_create) == 1
    assert preview.files_to_create[0]["uid"] == "ku.valid-ku"
    assert len(preview.validation_errors) > 0


# ============================================================================
# TEST 4: Empty directory returns IngestionStats (not DryRunPreview)
# ============================================================================


@pytest.mark.asyncio
async def test_dry_run_empty_directory(neo4j_driver, tmp_path):
    """Test dry-run with empty directory returns IngestionStats with total_files=0.

    batch.py:424 returns IngestionStats(total_files=0) for empty directories
    BEFORE reaching the dry-run code path at line 539.
    """
    test_dir = tmp_path / "empty_vault"
    test_dir.mkdir()

    result = await ingest_directory(
        directory=test_dir,
        engines={},
        get_engine=_mock_get_engine,
        driver=neo4j_driver,
        pattern="*.md",
        dry_run=True,
    )

    # Empty directory returns IngestionStats, not DryRunPreview
    assert result.is_ok
    stats = result.value
    assert isinstance(stats, IngestionStats)
    assert stats.total_files == 0


# ============================================================================
# TEST 5: UnifiedIngestionService dry-run end-to-end
# ============================================================================


@pytest.mark.asyncio
async def test_unified_ingestion_service_dry_run(ingestion_service, sample_ku_file):
    """Test dry-run through UnifiedIngestionService interface."""
    result = await ingestion_service.ingest_directory(
        directory=sample_ku_file,
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_ok
    preview = result.value
    assert isinstance(preview, DryRunPreview)
    assert preview.total_files >= 1


# ============================================================================
# TEST 6: Batch UID check efficiency (<=2 queries)
# ============================================================================


@pytest.mark.asyncio
async def test_dry_run_batch_uid_check(neo4j_driver, ten_ku_files):
    """Test that dry-run checks UIDs in batch (not individually).

    10 files should result in at most 2 driver queries:
    one constraint check + one batch UID existence check.
    """
    # Wrap driver to count execute_query calls
    call_count = 0
    original_execute = neo4j_driver.execute_query

    async def counting_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_execute(*args, **kwargs)

    neo4j_driver.execute_query = counting_execute

    try:
        result = await ingest_directory(
            directory=ten_ku_files,
            engines={},
            get_engine=_mock_get_engine,
            driver=neo4j_driver,
            pattern="*.md",
            dry_run=True,
        )

        assert result.is_ok
        preview = result.value
        assert isinstance(preview, DryRunPreview)
        assert preview.total_files == 10

        # Should batch check — at most 2 queries (not 10 individual ones)
        assert call_count <= 2, f"Expected <=2 driver queries, got {call_count}"
    finally:
        # Restore original
        neo4j_driver.execute_query = original_execute
