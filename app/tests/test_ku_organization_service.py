#!/usr/bin/env python3
"""
KU Organization Service Test Suite
====================================

Tests for KuOrganizationService — ORGANIZES relationship management.

Any Ku can organize other Kus via ORGANIZES relationships (emergent identity).
This test suite covers:
- Organizer identity operations (is_organizer)
- Organization view operations (get hierarchical view)
- Organization operations (organize, unorganize, reorder)
- Discovery operations (find_organizers, list_root_organizers, get_organized_children)
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.ku.ku_organization_service import (
    KuOrganizationService,
    OrganizationView,
    OrganizedKu,
)
from core.utils.result_simplified import Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_ku_service() -> Mock:
    """Create mock KuService."""
    ku_service = Mock()
    ku_service.get = AsyncMock()
    return ku_service


@pytest.fixture
def mock_driver() -> Mock:
    """Create mock Neo4j driver."""
    driver = Mock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def organization_service(mock_ku_service, mock_driver) -> KuOrganizationService:
    """Create KuOrganizationService instance for testing."""
    return KuOrganizationService(ku_service=mock_ku_service, executor=mock_driver)


@pytest.fixture
def sample_ku() -> Mock:
    """Create a sample KU mock."""
    ku = Mock()
    ku.uid = "ku.python-reference"
    ku.title = "Python Reference"
    return ku


# ============================================================================
# IDENTITY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_is_organizer_true(organization_service, mock_driver):
    """Test is_organizer returns True when Ku has organized children."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"ku_exists": True, "is_organizer": True}]
    )

    result = await organization_service.is_organizer("ku.python-reference")

    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_is_organizer_false(organization_service, mock_driver):
    """Test is_organizer returns False when Ku has no children."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"ku_exists": True, "is_organizer": False}]
    )

    result = await organization_service.is_organizer("ku.standalone")

    assert result.is_ok
    assert result.value is False


@pytest.mark.asyncio
async def test_is_organizer_not_found(organization_service, mock_driver):
    """Test is_organizer returns error when Ku doesn't exist."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"ku_exists": False, "is_organizer": False}]
    )

    result = await organization_service.is_organizer("ku.nonexistent")

    assert result.is_error


# ============================================================================
# ORGANIZATION VIEW TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_organization_view_success(
    organization_service, mock_ku_service, mock_driver, sample_ku
):
    """Test get_organization_view returns hierarchy."""
    mock_ku_service.get.return_value = Result.ok(sample_ku)

    mock_driver.execute_query.return_value = Result.ok(
        [
            {"uid": "ku.python-basics", "title": "Python Basics", "order": 0},
            {"uid": "ku.python-advanced", "title": "Python Advanced", "order": 1},
        ]
    )

    result = await organization_service.get_organization_view("ku.python-reference")

    assert result.is_ok
    view = result.value
    assert isinstance(view, OrganizationView)
    assert view.root_uid == "ku.python-reference"
    assert view.root_title == "Python Reference"


@pytest.mark.asyncio
async def test_get_organization_view_not_found(organization_service, mock_ku_service):
    """Test get_organization_view returns error when Ku doesn't exist."""
    mock_ku_service.get.return_value = Result.ok(None)

    result = await organization_service.get_organization_view("ku.nonexistent")

    assert result.is_error


# ============================================================================
# ORGANIZATION OPERATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_organize_success(organization_service, mock_ku_service, mock_driver, sample_ku):
    """Test organize creates ORGANIZES relationship."""
    child_ku = Mock()
    child_ku.uid = "ku.python-basics"
    child_ku.title = "Python Basics"

    mock_ku_service.get.side_effect = [
        Result.ok(sample_ku),
        Result.ok(child_ku),
    ]

    mock_driver.execute_query.return_value = Result.ok([{"success": True}])

    result = await organization_service.organize("ku.python-reference", "ku.python-basics", order=1)

    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_organize_parent_not_found(organization_service, mock_ku_service):
    """Test organize fails when parent Ku doesn't exist."""
    mock_ku_service.get.return_value = Result.ok(None)

    result = await organization_service.organize("ku.nonexistent", "ku.python-basics")

    assert result.is_error


@pytest.mark.asyncio
async def test_unorganize_success(organization_service, mock_driver):
    """Test unorganize removes ORGANIZES relationship."""
    mock_driver.execute_query.return_value = Result.ok([{"success": True}])

    result = await organization_service.unorganize("ku.python-reference", "ku.python-basics")

    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_reorder_success(organization_service, mock_driver):
    """Test reorder updates relationship order."""
    mock_driver.execute_query.return_value = Result.ok([{"success": True}])

    result = await organization_service.reorder(
        "ku.python-reference", "ku.python-basics", new_order=5
    )

    assert result.is_ok
    assert result.value is True


# ============================================================================
# DISCOVERY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_find_organizers_success(organization_service, mock_driver):
    """Test find_organizers returns parent organizers."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {"uid": "ku.python-reference", "title": "Python Reference", "order": 0},
            {"uid": "ku.web-development", "title": "Web Development", "order": 2},
        ]
    )

    result = await organization_service.find_organizers("ku.python-basics")

    assert result.is_ok
    organizers = result.value
    assert len(organizers) == 2
    assert organizers[0]["uid"] == "ku.python-reference"
    assert organizers[1]["uid"] == "ku.web-development"


@pytest.mark.asyncio
async def test_list_root_organizers_success(organization_service, mock_driver):
    """Test list_root_organizers returns top-level organizers."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {"uid": "ku.python-reference", "title": "Python Reference", "child_count": 5},
            {"uid": "ku.javascript-guide", "title": "JavaScript Guide", "child_count": 3},
        ]
    )

    result = await organization_service.list_root_organizers(limit=50)

    assert result.is_ok
    roots = result.value
    assert len(roots) == 2
    assert roots[0]["child_count"] == 5


@pytest.mark.asyncio
async def test_get_organized_children_success(organization_service, mock_driver):
    """Test get_organized_children returns direct children."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {"uid": "ku.python-basics", "title": "Python Basics", "order": 0},
            {"uid": "ku.python-advanced", "title": "Python Advanced", "order": 1},
        ]
    )

    result = await organization_service.get_organized_children("ku.python-reference")

    assert result.is_ok
    children = result.value
    assert len(children) == 2
    assert children[0]["order"] == 0
    assert children[1]["order"] == 1


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


def test_organization_view_to_dict():
    """Test OrganizationView.to_dict() conversion."""
    child = OrganizedKu(uid="ku.child", title="Child", order=0, children=[])
    view = OrganizationView(
        root_uid="ku.root",
        root_title="Root Organizer",
        children=[child],
        total_kus=1,
    )

    result = view.to_dict()

    assert result["root_uid"] == "ku.root"
    assert result["root_title"] == "Root Organizer"
    assert result["is_organizer"] is True
    assert result["total_kus"] == 1
    assert len(result["children"]) == 1


def test_organization_view_not_organizer_when_no_children():
    """Test OrganizationView.is_organizer is False when no children."""
    view = OrganizationView(
        root_uid="ku.standalone",
        root_title="Standalone KU",
        children=[],
        total_kus=0,
    )

    result = view.to_dict()

    assert result["is_organizer"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
