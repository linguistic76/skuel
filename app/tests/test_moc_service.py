#!/usr/bin/env python3
"""
MOC Service Test Suite - KU-Based Architecture
===============================================

Tests for Map of Content (MOC) service operations.

**January 2026 - KU-Based Architecture:**
MOC is NOT a separate entity - it IS a Knowledge Unit that organizes other KUs.
A KU "is" a MOC when it has outgoing ORGANIZES relationships.

This test suite covers:
- MOC identity operations (is_moc)
- MOC view operations (get hierarchical view)
- MOC organization operations (organize, unorganize, reorder)
- MOC discovery operations (find_mocs_containing, list_root_mocs, get_children)
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.moc.moc_navigation_service import MocView, OrganizedKu
from core.services.moc_service import MOCService
from core.utils.result_simplified import Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_ku_service() -> Mock:
    """Create mock KuService."""
    ku_service = Mock()
    ku_service.get = AsyncMock()
    ku_service.create = AsyncMock()
    ku_service.delete = AsyncMock()
    return ku_service


@pytest.fixture
def mock_driver() -> Mock:
    """Create mock Neo4j driver."""
    driver = Mock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def moc_service(mock_ku_service, mock_driver) -> MOCService:
    """
    Create MOCService instance for testing.

    **Architecture (January 2026 - KU-based):**
    - ku_service is REQUIRED (fail-fast architecture)
    - driver is REQUIRED for graph operations
    - MOCService delegates to MocNavigationService internally
    """
    return MOCService(ku_service=mock_ku_service, driver=mock_driver)


@pytest.fixture
def sample_ku() -> Mock:
    """Create a sample KU mock."""
    ku = Mock()
    ku.uid = "ku.python-reference"
    ku.title = "Python Reference"
    return ku


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


def test_init_requires_ku_service(mock_driver):
    """Test that MOCService requires ku_service (fail-fast architecture)."""
    with pytest.raises(ValueError, match="ku_service is REQUIRED"):
        MOCService(ku_service=None, driver=mock_driver)


def test_init_requires_driver(mock_ku_service):
    """Test that MOCService requires driver (fail-fast architecture)."""
    with pytest.raises(ValueError, match="driver is REQUIRED"):
        MOCService(ku_service=mock_ku_service, driver=None)


def test_init_success(mock_ku_service, mock_driver):
    """Test successful MOCService initialization."""
    service = MOCService(ku_service=mock_ku_service, driver=mock_driver)

    assert service.ku_service == mock_ku_service
    assert service.driver == mock_driver
    assert service.navigation is not None


# ============================================================================
# MOC IDENTITY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_is_moc_true(moc_service, mock_driver):
    """Test is_moc returns True when KU has organized children."""
    # Setup - KU exists and has children
    mock_driver.execute_query.return_value = (
        [{"ku_exists": True, "is_moc": True}],
        None,
        None,
    )

    # Execute
    result = await moc_service.is_moc("ku.python-reference")

    # Verify
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_is_moc_false(moc_service, mock_driver):
    """Test is_moc returns False when KU has no children."""
    # Setup - KU exists but has no children
    mock_driver.execute_query.return_value = (
        [{"ku_exists": True, "is_moc": False}],
        None,
        None,
    )

    # Execute
    result = await moc_service.is_moc("ku.standalone")

    # Verify
    assert result.is_ok
    assert result.value is False


@pytest.mark.asyncio
async def test_is_moc_not_found(moc_service, mock_driver):
    """Test is_moc returns error when KU doesn't exist."""
    # Setup - KU doesn't exist
    mock_driver.execute_query.return_value = (
        [{"ku_exists": False, "is_moc": False}],
        None,
        None,
    )

    # Execute
    result = await moc_service.is_moc("ku.nonexistent")

    # Verify
    assert result.is_error


# ============================================================================
# MOC VIEW TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_moc_view_success(moc_service, mock_ku_service, mock_driver, sample_ku):
    """Test get returns MocView with hierarchy."""
    # Setup - KU exists
    mock_ku_service.get.return_value = Result.ok(sample_ku)

    # Setup - Children query
    mock_driver.execute_query.return_value = (
        [
            {"uid": "ku.python-basics", "title": "Python Basics", "order": 0},
            {"uid": "ku.python-advanced", "title": "Python Advanced", "order": 1},
        ],
        None,
        None,
    )

    # Execute
    result = await moc_service.get("ku.python-reference")

    # Verify
    assert result.is_ok
    moc_view = result.value
    assert isinstance(moc_view, MocView)
    assert moc_view.root_uid == "ku.python-reference"
    assert moc_view.root_title == "Python Reference"


@pytest.mark.asyncio
async def test_get_moc_view_not_found(moc_service, mock_ku_service):
    """Test get returns error when KU doesn't exist."""
    # Setup
    mock_ku_service.get.return_value = Result.ok(None)

    # Execute
    result = await moc_service.get("ku.nonexistent")

    # Verify
    assert result.is_error


# ============================================================================
# MOC ORGANIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_organize_success(moc_service, mock_ku_service, mock_driver, sample_ku):
    """Test organize creates ORGANIZES relationship."""
    # Setup - Both KUs exist
    child_ku = Mock()
    child_ku.uid = "ku.python-basics"
    child_ku.title = "Python Basics"

    mock_ku_service.get.side_effect = [
        Result.ok(sample_ku),  # Parent exists
        Result.ok(child_ku),  # Child exists
    ]

    # Setup - Relationship creation succeeds
    mock_driver.execute_query.return_value = ([{"success": True}], None, None)

    # Execute
    result = await moc_service.organize("ku.python-reference", "ku.python-basics", order=1)

    # Verify
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_organize_parent_not_found(moc_service, mock_ku_service):
    """Test organize fails when parent KU doesn't exist."""
    # Setup - Parent doesn't exist
    mock_ku_service.get.return_value = Result.ok(None)

    # Execute
    result = await moc_service.organize("ku.nonexistent", "ku.python-basics")

    # Verify
    assert result.is_error


@pytest.mark.asyncio
async def test_unorganize_success(moc_service, mock_driver):
    """Test unorganize removes ORGANIZES relationship."""
    # Setup
    mock_driver.execute_query.return_value = ([{"success": True}], None, None)

    # Execute
    result = await moc_service.unorganize("ku.python-reference", "ku.python-basics")

    # Verify
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_reorder_success(moc_service, mock_driver):
    """Test reorder updates relationship order."""
    # Setup
    mock_driver.execute_query.return_value = ([{"success": True}], None, None)

    # Execute
    result = await moc_service.reorder("ku.python-reference", "ku.python-basics", new_order=5)

    # Verify
    assert result.is_ok
    assert result.value is True


# ============================================================================
# MOC DISCOVERY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_find_mocs_containing_success(moc_service, mock_driver):
    """Test find_mocs_containing returns parent MOCs."""
    # Setup
    mock_driver.execute_query.return_value = (
        [
            {"uid": "ku.python-reference", "title": "Python Reference", "order": 0},
            {"uid": "ku.web-development", "title": "Web Development", "order": 2},
        ],
        None,
        None,
    )

    # Execute
    result = await moc_service.find_mocs_containing("ku.python-basics")

    # Verify
    assert result.is_ok
    mocs = result.value
    assert len(mocs) == 2
    assert mocs[0]["uid"] == "ku.python-reference"
    assert mocs[1]["uid"] == "ku.web-development"


@pytest.mark.asyncio
async def test_list_root_mocs_success(moc_service, mock_driver):
    """Test list_root_mocs returns top-level MOCs."""
    # Setup
    mock_driver.execute_query.return_value = (
        [
            {"uid": "ku.python-reference", "title": "Python Reference", "child_count": 5},
            {"uid": "ku.javascript-guide", "title": "JavaScript Guide", "child_count": 3},
        ],
        None,
        None,
    )

    # Execute
    result = await moc_service.list_root_mocs(limit=50)

    # Verify
    assert result.is_ok
    mocs = result.value
    assert len(mocs) == 2
    assert mocs[0]["child_count"] == 5


@pytest.mark.asyncio
async def test_get_children_success(moc_service, mock_driver):
    """Test get_children returns direct children."""
    # Setup
    mock_driver.execute_query.return_value = (
        [
            {"uid": "ku.python-basics", "title": "Python Basics", "order": 0},
            {"uid": "ku.python-advanced", "title": "Python Advanced", "order": 1},
        ],
        None,
        None,
    )

    # Execute
    result = await moc_service.get_children("ku.python-reference")

    # Verify
    assert result.is_ok
    children = result.value
    assert len(children) == 2
    assert children[0]["order"] == 0
    assert children[1]["order"] == 1


# ============================================================================
# KU CRUD DELEGATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_ku_delegates(moc_service, mock_ku_service, sample_ku):
    """Test create_ku delegates to KuService."""
    # Setup
    mock_ku_service.create.return_value = Result.ok(sample_ku)

    # Execute
    result = await moc_service.create_ku(uid="ku.new-ku", title="New KU")

    # Verify
    assert result.is_ok
    mock_ku_service.create.assert_called_once()


@pytest.mark.asyncio
async def test_get_ku_delegates(moc_service, mock_ku_service, sample_ku):
    """Test get_ku delegates to KuService."""
    # Setup
    mock_ku_service.get.return_value = Result.ok(sample_ku)

    # Execute
    result = await moc_service.get_ku("ku.python-reference")

    # Verify
    assert result.is_ok
    mock_ku_service.get.assert_called_once_with("ku.python-reference")


@pytest.mark.asyncio
async def test_delete_ku_delegates(moc_service, mock_ku_service):
    """Test delete_ku delegates to KuService."""
    # Setup
    mock_ku_service.delete.return_value = Result.ok(True)

    # Execute
    result = await moc_service.delete_ku("ku.python-reference")

    # Verify
    assert result.is_ok
    mock_ku_service.delete.assert_called_once_with("ku.python-reference")


# ============================================================================
# DATA CLASS TESTS
# ============================================================================


def test_organized_ku_to_dict():
    """Test OrganizedKu.to_dict() conversion."""
    child = OrganizedKu(uid="ku.child", title="Child", order=0, children=[])
    parent = OrganizedKu(uid="ku.parent", title="Parent", order=0, children=[child])

    result = parent.to_dict()

    assert result["uid"] == "ku.parent"
    assert result["title"] == "Parent"
    assert result["is_leaf"] is False
    assert len(result["children"]) == 1
    assert result["children"][0]["is_leaf"] is True


def test_moc_view_to_dict():
    """Test MocView.to_dict() conversion."""
    child = OrganizedKu(uid="ku.child", title="Child", order=0, children=[])
    moc_view = MocView(
        root_uid="ku.root",
        root_title="Root MOC",
        children=[child],
        total_kus=1,
    )

    result = moc_view.to_dict()

    assert result["root_uid"] == "ku.root"
    assert result["root_title"] == "Root MOC"
    assert result["is_moc"] is True
    assert result["total_kus"] == 1
    assert len(result["children"]) == 1


def test_moc_view_is_moc_false_when_no_children():
    """Test MocView.is_moc is False when no children."""
    moc_view = MocView(
        root_uid="ku.standalone",
        root_title="Standalone KU",
        children=[],
        total_kus=0,
    )

    result = moc_view.to_dict()

    assert result["is_moc"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
