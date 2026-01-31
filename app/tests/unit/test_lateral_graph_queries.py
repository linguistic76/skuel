"""Unit tests for lateral relationship graph queries (Phase 5).

Tests the three new service methods:
- get_blocking_chain()
- get_alternatives_with_comparison()
- get_relationship_graph()

These methods provide data for the Enhanced UX components.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def lateral_service(mock_driver):
    """LateralRelationshipService instance with mocked driver."""
    return LateralRelationshipService(mock_driver)


class TestGetBlockingChain:
    """Tests for get_blocking_chain method."""

    @pytest.mark.asyncio
    async def test_empty_chain(self, lateral_service, mock_driver):
        """Test entity with no blockers returns empty chain."""
        # Mock: No blockers found
        mock_result = MagicMock()
        mock_result.records = []
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_blocking_chain("task_xyz")

        assert not result.is_error
        assert result.value["total_blockers"] == 0
        assert result.value["chain_depth"] == 0
        assert result.value["levels"] == []
        assert result.value["critical_path"] == ["task_xyz"]

    @pytest.mark.asyncio
    async def test_single_level_chain(self, lateral_service, mock_driver):
        """Test entity with one blocker (depth 1)."""
        # Mock: One blocker at depth 1
        mock_record = {
            "uid": "task_setup",
            "title": "Setup Environment",
            "status": "completed",
            "entity_type": "Task",
            "depth": 1,
            "blocks_count": 1,
        }
        mock_result = MagicMock()
        mock_result.records = [mock_record]
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_blocking_chain("task_deploy")

        assert not result.is_error
        data = result.value
        assert data["total_blockers"] == 1
        assert data["chain_depth"] == 1
        assert len(data["levels"]) == 1
        assert data["levels"][0]["depth"] == 1
        assert data["levels"][0]["entities"][0]["uid"] == "task_setup"
        assert "task_setup" in data["critical_path"]
        assert "task_deploy" in data["critical_path"]

    @pytest.mark.asyncio
    async def test_multi_level_chain(self, lateral_service, mock_driver):
        """Test entity with multiple blocking levels (depth 3)."""
        # Mock: Three levels of blockers
        mock_records = [
            {
                "uid": "task_a",
                "title": "Task A",
                "status": "completed",
                "entity_type": "Task",
                "depth": 3,
                "blocks_count": 1,
            },
            {
                "uid": "task_b",
                "title": "Task B",
                "status": "in_progress",
                "entity_type": "Task",
                "depth": 2,
                "blocks_count": 1,
            },
            {
                "uid": "task_c",
                "title": "Task C",
                "status": "pending",
                "entity_type": "Task",
                "depth": 1,
                "blocks_count": 1,
            },
        ]
        mock_result = MagicMock()
        mock_result.records = mock_records
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_blocking_chain("task_d")

        assert not result.is_error
        data = result.value
        assert data["total_blockers"] == 3
        assert data["chain_depth"] == 3
        assert len(data["levels"]) == 3
        # Levels should be sorted by depth (descending)
        assert data["levels"][0]["depth"] == 3  # Deepest first
        assert data["levels"][1]["depth"] == 2
        assert data["levels"][2]["depth"] == 1


class TestGetAlternativesWithComparison:
    """Tests for get_alternatives_with_comparison method."""

    @pytest.mark.asyncio
    async def test_no_alternatives(self, lateral_service, mock_driver):
        """Test entity with no alternatives returns empty list."""
        mock_result = MagicMock()
        mock_result.records = []
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_alternatives_with_comparison("goal_a")

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_single_alternative_with_comparison(self, lateral_service, mock_driver):
        """Test entity with one alternative including comparison data."""
        mock_record = {
            "uid": "goal_b",
            "title": "Entrepreneurship",
            "description": "Start own business",
            "status": "active",
            "priority": "high",
            "entity_type": "Goal",
            "comparison_criteria": "career growth vs autonomy",
            "tradeoffs": "Higher risk, more freedom",
            "timeframe": "3 years",
            "difficulty": "very_high",
            "resources": "self-funded",
            "all_properties": {},
            "rel_properties": {
                "comparison_criteria": "career growth vs autonomy",
                "tradeoffs": "Higher risk, more freedom",
                "timeframe": "3 years",
            },
        }
        mock_result = MagicMock()
        mock_result.records = [mock_record]
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_alternatives_with_comparison("goal_a")

        assert not result.is_error
        alternatives = result.value
        assert len(alternatives) == 1
        alt = alternatives[0]
        assert alt["uid"] == "goal_b"
        assert alt["title"] == "Entrepreneurship"
        assert alt["comparison_data"]["timeframe"] == "3 years"
        assert alt["comparison_data"]["difficulty"] == "very_high"
        assert alt["metadata"]["tradeoffs"] == "Higher risk, more freedom"

    @pytest.mark.asyncio
    async def test_multiple_alternatives(self, lateral_service, mock_driver):
        """Test entity with multiple alternatives."""
        mock_records = [
            {
                "uid": "goal_b",
                "title": "Corporate",
                "description": "Executive path",
                "status": "active",
                "priority": "high",
                "entity_type": "Goal",
                "comparison_criteria": "stability",
                "tradeoffs": "Less autonomy",
                "timeframe": "5 years",
                "difficulty": "high",
                "resources": "company",
                "all_properties": {},
                "rel_properties": {"timeframe": "5 years"},
            },
            {
                "uid": "goal_c",
                "title": "Freelance",
                "description": "Independent consultant",
                "status": "pending",
                "priority": "medium",
                "entity_type": "Goal",
                "comparison_criteria": "flexibility",
                "tradeoffs": "Variable income",
                "timeframe": "1 year",
                "difficulty": "medium",
                "resources": "self",
                "all_properties": {},
                "rel_properties": {"timeframe": "1 year"},
            },
        ]
        mock_result = MagicMock()
        mock_result.records = mock_records
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_alternatives_with_comparison("goal_a")

        assert not result.is_error
        alternatives = result.value
        assert len(alternatives) == 2


class TestGetRelationshipGraph:
    """Tests for get_relationship_graph method."""

    @pytest.mark.asyncio
    async def test_isolated_entity(self, lateral_service, mock_driver):
        """Test entity with no relationships returns single node."""
        mock_result = MagicMock()
        mock_result.records = []
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_relationship_graph("task_xyz", depth=2)

        assert not result.is_error
        graph = result.value
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["id"] == "task_xyz"
        assert graph["nodes"][0]["group"] == "center"
        assert len(graph["edges"]) == 0

    @pytest.mark.asyncio
    async def test_simple_graph(self, lateral_service, mock_driver):
        """Test entity with one related entity (2 nodes, 1 edge)."""
        mock_record = {
            "center_uid": "task_a",
            "center_title": "Task A",
            "center_type": "Task",
            "center_status": "pending",
            "related_uid": "task_b",
            "related_title": "Task B",
            "related_type": "Task",
            "related_status": "completed",
            "relationships": [
                {"type": "BLOCKS", "from": "task_b", "to": "task_a"}
            ],
            "depth_level": 1,
        }
        mock_result = MagicMock()
        mock_result.records = [mock_record]
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_relationship_graph("task_a", depth=2)

        assert not result.is_error
        graph = result.value
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

        # Check edge properties
        edge = graph["edges"][0]
        assert edge["from"] == "task_b"
        assert edge["to"] == "task_a"
        assert edge["relationship_type"] == "BLOCKS"
        assert edge["arrows"] == "to"
        assert "color" in edge
        # BLOCKS should be red
        assert edge["color"]["color"] == "#EF4444"

    @pytest.mark.asyncio
    async def test_complex_graph(self, lateral_service, mock_driver):
        """Test entity with multiple relationships and types."""
        mock_records = [
            {
                "center_uid": "goal_a",
                "center_title": "Goal A",
                "center_type": "Goal",
                "center_status": "active",
                "related_uid": "goal_b",
                "related_title": "Goal B",
                "related_type": "Goal",
                "related_status": "completed",
                "relationships": [
                    {"type": "PREREQUISITE_FOR", "from": "goal_b", "to": "goal_a"}
                ],
                "depth_level": 1,
            },
            {
                "center_uid": "goal_a",
                "center_title": "Goal A",
                "center_type": "Goal",
                "center_status": "active",
                "related_uid": "goal_c",
                "related_title": "Goal C",
                "related_type": "Goal",
                "related_status": "active",
                "relationships": [
                    {"type": "ALTERNATIVE_TO", "from": "goal_a", "to": "goal_c"}
                ],
                "depth_level": 1,
            },
        ]
        mock_result = MagicMock()
        mock_result.records = mock_records
        mock_driver.execute_query.return_value = mock_result

        result = await lateral_service.get_relationship_graph("goal_a", depth=2)

        assert not result.is_error
        graph = result.value
        assert len(graph["nodes"]) == 3  # center + 2 related
        assert len(graph["edges"]) == 2  # PREREQUISITE + ALTERNATIVE

        # Verify different relationship colors
        edge_colors = {edge["relationship_type"]: edge["color"]["color"] for edge in graph["edges"]}
        assert edge_colors["PREREQUISITE_FOR"] == "#F59E0B"  # Orange
        assert edge_colors["ALTERNATIVE_TO"] == "#3B82F6"  # Blue
