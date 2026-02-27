"""
Unit Tests for Ingestion Dry-Run Mode
======================================

Tests the dry-run preview logic using mock Neo4j driver (no database needed).

Test Categories:
1. Entity Existence Checking (batch query logic)
2. Relationship Preview (with mocked file parsing)
3. Error Handling (missing driver, non-existent directory)

Integration tests for end-to-end dry-run with real Neo4j and real file parsing
live in: tests/integration/test_ingestion_dry_run_integration.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from core.services.ingestion.batch import check_existing_entities, ingest_directory

# ============================================================================
# TEST FIXTURES - Mock Neo4j Driver and Responses
# ============================================================================


class SimpleMockDriver:
    """Simple mock driver that avoids pickle issues with AsyncMock."""

    def __init__(self, existing_uids: dict[str, bool] | None = None):
        self.existing_uids = existing_uids or {}
        self.call_count = 0

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None, database_: str = "neo4j"
    ):
        """Mock execute_query that handles UID existence checks."""
        self.call_count += 1
        params = params or {}

        # Handle UID existence check queries
        if "uids" in params:
            uids = params.get("uids", [])
            records = []
            for uid in uids:
                # Create simple dict-like record
                # Use default parameter to capture value in lambda closure
                record_data = {"uid": uid, "exists": self.existing_uids.get(uid, False)}

                # Create record object that supports subscript access
                def make_getitem(data):
                    return lambda _self, k: data[k]

                def make_get(data):
                    return lambda _self, k, default=None: data.get(k, default)

                record_obj = type(
                    "Record",
                    (),
                    {
                        "__getitem__": make_getitem(record_data),
                        "get": make_get(record_data),
                    },
                )()
                records.append(record_obj)

            return type("Result", (), {"records": records})()

        # Handle constraint checks (return empty result)
        return type("Result", (), {"records": []})()


@pytest.fixture
def mock_existing_uids():
    """Mock UIDs that exist in database."""
    return {
        "ku_existing-content_123": True,
        "ku_another-existing_456": True,
        "ku_new-content_789": False,
    }


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for testing."""
    return SimpleMockDriver()


@pytest.fixture
def mock_driver_with_uids(mock_existing_uids):
    """Mock driver that returns existence data."""
    return SimpleMockDriver(existing_uids=mock_existing_uids)


# ============================================================================
# TEST 1: Entity Existence Checking
# ============================================================================


@pytest.mark.asyncio
async def test_check_existing_entities_empty_list(mock_neo4j_driver):
    """Test checking empty UID list returns empty dict."""
    result = await check_existing_entities(mock_neo4j_driver, [])
    assert result == {}


@pytest.mark.asyncio
async def test_check_existing_entities_with_uids(mock_driver_with_uids):
    """Test checking multiple UIDs returns correct existence map."""
    uids = [
        "ku_existing-content_123",
        "ku_new-content_789",
        "ku_another-existing_456",
    ]

    result = await check_existing_entities(mock_driver_with_uids, uids)

    assert result["ku_existing-content_123"] is True
    assert result["ku_another-existing_456"] is True
    assert result["ku_new-content_789"] is False
    assert len(result) == 3


@pytest.mark.asyncio
async def test_check_existing_entities_all_new(mock_driver_with_uids):
    """Test checking UIDs that don't exist."""
    uids = ["ku_brand-new_111", "ku_never-seen_222"]

    result = await check_existing_entities(mock_driver_with_uids, uids)

    assert result["ku_brand-new_111"] is False
    assert result["ku_never-seen_222"] is False


# ============================================================================
# TEST 2: Relationship Preview
# ============================================================================


@pytest.mark.asyncio
@patch("core.services.ingestion.batch.collect_files")
@patch("core.services.ingestion.batch.parse_file_sync")
async def test_dry_run_includes_relationships(
    mock_parse,
    mock_collect,
    mock_driver_with_uids,
    tmp_path,
):
    """Test that dry-run preview includes relationships to be created."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    test_file = test_dir / "test.md"
    test_file.write_text("# Test")
    mock_collect.return_value = [test_file]

    from core.models.enums.entity_enums import EntityType

    # Mock entity with relationships
    mock_parse.return_value = (
        EntityType.KU,
        {
            "uid": "ku_new-content_789",
            "title": "Test KU",
            "type": "ku",
            "prerequisite_uids": ["ku_prereq_111", "ku_prereq_222"],
            "enables_uids": ["ku_enables_333"],
            "_file_path": str(test_file),
        },
        None,
    )

    def mock_get_engine(entity_type):
        return Mock()

    # Mock ENTITY_CONFIGS with source_field -> RelationshipConfig mapping
    # (matches real config shape: source_field is the key in entity data)
    with patch("core.services.ingestion.batch.ENTITY_CONFIGS") as mock_configs:
        mock_config = Mock()
        mock_config.relationship_config = {
            "prerequisite_uids": {
                "rel_type": "PREREQUISITE",
                "target_label": "Entity",
                "direction": "incoming",
            },
            "enables_uids": {
                "rel_type": "ENABLES",
                "target_label": "Entity",
                "direction": "outgoing",
            },
        }
        mock_configs.get.return_value = mock_config

        result = await ingest_directory(
            directory=test_dir,
            engines={},
            get_engine=mock_get_engine,
            driver=mock_driver_with_uids,
            pattern="*.md",
            dry_run=True,
        )

    assert result.is_ok
    preview = result.value

    # Verify relationships are included
    assert len(preview.relationships_to_create) > 0
    rel_types = {rel["type"] for rel in preview.relationships_to_create}
    assert "PREREQUISITE" in rel_types or "ENABLES" in rel_types


# ============================================================================
# TEST 3: Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_dry_run_requires_driver(tmp_path):
    """Test that dry-run mode fails without Neo4j driver."""
    test_dir = tmp_path / "test_vault"
    test_dir.mkdir()

    def mock_get_engine(entity_type):
        return Mock()

    result = await ingest_directory(
        directory=test_dir,
        engines={},
        get_engine=mock_get_engine,
        driver=None,  # No driver provided
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_error
    assert "driver required" in result.expect_error().message.lower()


@pytest.mark.asyncio
async def test_dry_run_nonexistent_directory(mock_driver_with_uids):
    """Test dry-run with non-existent directory."""
    non_existent = Path("/nonexistent/path")

    def mock_get_engine(entity_type):
        return Mock()

    result = await ingest_directory(
        directory=non_existent,
        engines={},
        get_engine=mock_get_engine,
        driver=mock_driver_with_uids,
        pattern="*.md",
        dry_run=True,
    )

    assert result.is_error
    assert "not found" in result.expect_error().message.lower()
