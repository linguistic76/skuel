"""Unit tests for lateral relationship graph queries.

Tests the three new service methods:
- get_blocking_chain()
- get_alternatives_with_comparison()
- get_relationship_graph()

These methods provide data for the Enhanced UX components.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import ErrorCategory, Errors, Result


@pytest.fixture
def mock_backend():
    """Mock LateralRelationshipBackend."""
    backend = MagicMock()
    backend.get_blocking_chain = AsyncMock()
    backend.get_alternatives_comparison = AsyncMock()
    backend.get_relationship_graph = AsyncMock()
    return backend


@pytest.fixture
def lateral_service(mock_backend):
    """LateralRelationshipService instance with mocked backend."""
    return LateralRelationshipService(backend=mock_backend)


class TestGetBlockingChain:
    """Tests for get_blocking_chain method."""

    @pytest.mark.asyncio
    async def test_empty_chain(self, lateral_service, mock_backend):
        """Test entity with no blockers returns empty chain."""
        # Mock: No blockers found
        mock_backend.get_blocking_chain.return_value = Result.ok([])

        result = await lateral_service.get_blocking_chain("task_xyz")

        assert not result.is_error
        assert result.value["total_blockers"] == 0
        assert result.value["chain_depth"] == 0
        assert result.value["levels"] == []
        assert result.value["critical_path"] == ["task_xyz"]

    @pytest.mark.asyncio
    async def test_single_level_chain(self, lateral_service, mock_backend):
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
        mock_backend.get_blocking_chain.return_value = Result.ok([mock_record])

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
    async def test_multi_level_chain(self, lateral_service, mock_backend):
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
        mock_backend.get_blocking_chain.return_value = Result.ok(mock_records)

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
    async def test_no_alternatives(self, lateral_service, mock_backend):
        """Test entity with no alternatives returns empty list."""
        mock_backend.get_alternatives_comparison.return_value = Result.ok([])

        result = await lateral_service.get_alternatives_with_comparison("goal_a")

        assert not result.is_error
        assert result.value == []

    @pytest.mark.asyncio
    async def test_single_alternative_with_comparison(self, lateral_service, mock_backend):
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
        }
        mock_backend.get_alternatives_comparison.return_value = Result.ok([mock_record])

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
    async def test_multiple_alternatives(self, lateral_service, mock_backend):
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
            },
        ]
        mock_backend.get_alternatives_comparison.return_value = Result.ok(mock_records)

        result = await lateral_service.get_alternatives_with_comparison("goal_a")

        assert not result.is_error
        alternatives = result.value
        assert len(alternatives) == 2

    @pytest.mark.asyncio
    async def test_built_keys_match_typeddict(self, lateral_service, mock_backend):
        """The runtime-built item keys match the AlternativeComparisonItem TypedDict.

        mypy type-checks the dict literal against AlternativeComparisonItem, but it
        cannot prove the dynamically-built dict matches the declared shape at
        runtime — this locks the boundary contract (PR4 of the arg-type campaign).
        """
        from core.ports.query_types import AlternativeComparisonItem

        mock_record = {
            "uid": "goal_b",
            "title": "Entrepreneurship",
            "description": "Start own business",
            "status": "active",
            "priority": "high",
            "entity_type": "Goal",
            "comparison_criteria": "career growth vs autonomy",
            "tradeoffs": "Higher risk",
            "timeframe": "3 years",
            "difficulty": "very_high",
            "resources": "self-funded",
        }
        mock_backend.get_alternatives_comparison.return_value = Result.ok([mock_record])

        result = await lateral_service.get_alternatives_with_comparison("goal_a")

        assert not result.is_error
        built_keys = set(result.value[0].keys())
        declared_keys = set(AlternativeComparisonItem.__annotations__)
        assert built_keys == declared_keys


class TestGetRelationshipGraph:
    """Tests for get_relationship_graph method."""

    @pytest.mark.asyncio
    async def test_isolated_entity(self, lateral_service, mock_backend):
        """Test entity with no relationships returns single node."""
        mock_backend.get_relationship_graph.return_value = Result.ok([])

        result = await lateral_service.get_relationship_graph("task_xyz", depth=2)

        assert not result.is_error
        graph = result.value
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["id"] == "task_xyz"
        assert graph["nodes"][0]["group"] == "center"
        assert len(graph["edges"]) == 0

    @pytest.mark.asyncio
    async def test_simple_graph(self, lateral_service, mock_backend):
        """Test entity with one related entity (2 nodes, 1 edge)."""
        mock_record = {
            "center_uid": "task_a",
            "center_title": "Task A",
            "center_type": "Task",  # Neo4j label (styling)
            "center_entity_type": "task",  # canonical value (detail URL)
            "center_status": "pending",
            "related_uid": "task_b",
            "related_title": "Task B",
            "related_type": "Task",
            "related_entity_type": "task",
            "related_status": "completed",
            "relationships": [{"type": "BLOCKS", "from": "task_b", "to": "task_a"}],
            "depth_level": 1,
        }
        mock_backend.get_relationship_graph.return_value = Result.ok([mock_record])

        result = await lateral_service.get_relationship_graph("task_a", depth=2)

        assert not result.is_error
        graph = result.value
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

        # Nodes carry the canonical entity_type (distinct from the Neo4j-label `type`)
        # so the route can resolve a real detail URL via entity_detail_href.
        related_node = next(n for n in graph["nodes"] if n["id"] == "task_b")
        assert related_node["entity_type"] == "task"
        assert related_node["type"] == "Task"  # label preserved for styling

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
    async def test_complex_graph(self, lateral_service, mock_backend):
        """Test entity with multiple relationships and types."""
        mock_records = [
            {
                "center_uid": "goal_a",
                "center_title": "Goal A",
                "center_type": "Goal",
                "center_entity_type": "goal",
                "center_status": "active",
                "related_uid": "goal_b",
                "related_title": "Goal B",
                "related_type": "Goal",
                "related_entity_type": "goal",
                "related_status": "completed",
                "relationships": [{"type": "PREREQUISITE_FOR", "from": "goal_b", "to": "goal_a"}],
                "depth_level": 1,
            },
            {
                "center_uid": "goal_a",
                "center_title": "Goal A",
                "center_type": "Goal",
                "center_entity_type": "goal",
                "center_status": "active",
                "related_uid": "goal_c",
                "related_title": "Goal C",
                "related_type": "Goal",
                "related_entity_type": "goal",
                "related_status": "active",
                "relationships": [{"type": "ALTERNATIVE_TO", "from": "goal_a", "to": "goal_c"}],
                "depth_level": 1,
            },
        ]
        mock_backend.get_relationship_graph.return_value = Result.ok(mock_records)

        result = await lateral_service.get_relationship_graph("goal_a", depth=2)

        assert not result.is_error
        graph = result.value
        assert len(graph["nodes"]) == 3  # center + 2 related
        assert len(graph["edges"]) == 2  # PREREQUISITE + ALTERNATIVE

        # Verify different relationship colors
        edge_colors = {edge["relationship_type"]: edge["color"]["color"] for edge in graph["edges"]}
        assert edge_colors["PREREQUISITE_FOR"] == "#F59E0B"  # Orange
        assert edge_colors["ALTERNATIVE_TO"] == "#3B82F6"  # Blue

    @pytest.mark.asyncio
    async def test_node_entity_type_resolves_to_real_detail_url(
        self, lateral_service, mock_backend
    ):
        """Graph nodes resolve to real detail routes via the canonical entity_type.

        Regression guard for the dead click-nav: the node's Neo4j label ("Ku") is NOT a
        route, so the route builds the URL from the entity_type property ("ku") through
        entity_detail_href — the same path shape the detail pages register.
        """
        from ui.patterns.entity_links import entity_detail_href

        mock_record = {
            "center_uid": "task_a",
            "center_title": "Task A",
            "center_type": "Task",
            "center_entity_type": "task",
            "center_status": "pending",
            "related_uid": "ku.pedagogy.zpd",
            "related_title": "ZPD",
            "related_type": "Ku",  # label — would have produced a dead /Ku/... link
            "related_entity_type": "ku",
            "related_status": "active",
            "relationships": [{"type": "RELATED_TO", "from": "task_a", "to": "ku.pedagogy.zpd"}],
            "depth_level": 1,
        }
        mock_backend.get_relationship_graph.return_value = Result.ok([mock_record])

        result = await lateral_service.get_relationship_graph("task_a", depth=2)
        assert not result.is_error

        # Replicate the route's enrichment (entity_detail_href on each node's entity_type).
        urls = {
            n["id"]: entity_detail_href(n.get("entity_type"), n["id"])
            for n in result.value["nodes"]
        }
        assert urls["task_a"] == "/tasks/detail?uid=task_a"
        assert urls["ku.pedagogy.zpd"] == "/explore/ku/ku.pedagogy.zpd"  # path-param shape, live


class TestOwnershipGate:
    """The ``user_uid`` / ``domain_service`` pair on the three enhanced-UX reads.

    These three methods once accepted no verifier at all, which made the routes
    above them unable to enforce ownership even if they wanted to (see
    RELATIONSHIPS_ARCHITECTURE.md § Ownership Coverage). The gate is asserted
    here at the service level so a future caller that bypasses
    ``LateralRouteFactory`` is covered too.
    """

    @pytest.fixture
    def refusing_service(self):
        """An OwnershipVerifier that owns nothing."""
        service = MagicMock()
        service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("Goal", "g"))
        )
        return service

    @pytest.fixture
    def accepting_service(self):
        """An OwnershipVerifier that owns everything."""
        service = MagicMock()
        service.verify_ownership = AsyncMock(return_value=Result.ok(MagicMock()))
        return service

    # --- refused: not-found, and the backend is never reached ---

    @pytest.mark.asyncio
    async def test_chain_refuses_unowned_entity(
        self, lateral_service, mock_backend, refusing_service
    ):
        result = await lateral_service.get_blocking_chain(
            "goal_theirs", user_uid="user_intruder", domain_service=refusing_service
        )

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND
        mock_backend.get_blocking_chain.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_alternatives_refuses_unowned_entity(
        self, lateral_service, mock_backend, refusing_service
    ):
        result = await lateral_service.get_alternatives_with_comparison(
            "goal_theirs", user_uid="user_intruder", domain_service=refusing_service
        )

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND
        mock_backend.get_alternatives_comparison.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_graph_refuses_unowned_entity(
        self, lateral_service, mock_backend, refusing_service
    ):
        result = await lateral_service.get_relationship_graph(
            "goal_theirs", depth=2, user_uid="user_intruder", domain_service=refusing_service
        )

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND
        mock_backend.get_relationship_graph.assert_not_awaited()

    # --- allowed: the owner reads normally ---

    @pytest.mark.asyncio
    async def test_owner_reads_chain(self, lateral_service, mock_backend, accepting_service):
        mock_backend.get_blocking_chain.return_value = Result.ok([])

        result = await lateral_service.get_blocking_chain(
            "goal_mine", user_uid="user_owner", domain_service=accepting_service
        )

        assert not result.is_error
        accepting_service.verify_ownership.assert_awaited_once_with("goal_mine", "user_owner")

    # --- shared content: no verifier means no check (curriculum KU/PS/LP) ---

    @pytest.mark.asyncio
    async def test_curriculum_read_skips_the_check(self, lateral_service, mock_backend):
        """``domain_service=None`` is the deliberate public path — not a refusal."""
        mock_backend.get_blocking_chain.return_value = Result.ok([])

        result = await lateral_service.get_blocking_chain(
            "ps.math.algebra", user_uid="user_anyone", domain_service=None
        )

        assert not result.is_error
        mock_backend.get_blocking_chain.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verifier_without_user_does_not_gate(
        self, lateral_service, mock_backend, refusing_service
    ):
        """Documented fail-open: the gate needs BOTH halves to engage.

        Asserted so the behaviour is a decision on record, not an accident —
        RELATIONSHIPS_ARCHITECTURE.md warns callers to always pass both.
        """
        mock_backend.get_blocking_chain.return_value = Result.ok([])

        result = await lateral_service.get_blocking_chain(
            "goal_theirs", user_uid=None, domain_service=refusing_service
        )

        assert not result.is_error
        refusing_service.verify_ownership.assert_not_awaited()
