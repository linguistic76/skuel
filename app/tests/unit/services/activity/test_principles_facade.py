"""
Unit tests for PrinciplesService facade orchestration methods.

Tests focus on explicit orchestration logic — NOT pure delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.principle_enums import PrincipleCategory
from core.models.principle.principle import Principle
from core.services.principles_service import PrinciplesService
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def principles_service(mock_backend: Mock, mock_graph_intel: Mock) -> PrinciplesService:
    service = PrinciplesService(
        backend=mock_backend,
        graph_intelligence_service=mock_graph_intel,
        event_bus=None,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.search = AsyncMock()
    service.learning = AsyncMock()
    service.alignment = AsyncMock()
    service.reflection = AsyncMock()
    service.planning = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestPrinciplesServiceCreate
# ---------------------------------------------------------------------------


class TestPrinciplesServiceCreate:
    @pytest.mark.asyncio
    async def test_create_principle_delegates_to_core(
        self, principles_service: PrinciplesService
    ) -> None:
        """create_principle delegates to core.create_principle with all params."""
        mock_principle = Mock()
        principles_service.core.create_principle = AsyncMock(
            return_value=Result.ok(mock_principle)
        )

        result = await principles_service.create_principle(
            label="Do the right thing",
            description="Always act with integrity",
            category=PrincipleCategory.ETHICAL,
            why_matters="Foundation of trust",
        )

        assert result.is_ok
        principles_service.core.create_principle.assert_called_once_with(
            "Do the right thing",
            "Always act with integrity",
            PrincipleCategory.ETHICAL,
            "Foundation of trust",
        )


# ---------------------------------------------------------------------------
# TestPrinciplesServicePortfolio
# ---------------------------------------------------------------------------


class TestPrinciplesServicePortfolio:
    @pytest.mark.asyncio
    async def test_get_user_principle_portfolio_calls_backend_list(
        self, principles_service: PrinciplesService, mock_backend: Mock
    ) -> None:
        """get_user_principle_portfolio calls backend.list with user_uid filter."""
        mock_principle = Mock()
        mock_backend.list = AsyncMock(return_value=Result.ok(([mock_principle], 1)))

        result = await principles_service.get_user_principle_portfolio("user_test")

        assert result.is_ok
        assert result.value["user_uid"] == "user_test"
        assert result.value["count"] == 1
        mock_backend.list.assert_called_once_with(
            filters={"user_uid": "user_test"}, limit=100
        )

    @pytest.mark.asyncio
    async def test_get_user_principle_portfolio_propagates_backend_error(
        self, principles_service: PrinciplesService, mock_backend: Mock
    ) -> None:
        """get_user_principle_portfolio propagates backend error."""
        mock_backend.list = AsyncMock(return_value=Result.fail(Errors.database("query", "DB error")))

        result = await principles_service.get_user_principle_portfolio("user_test")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_calculate_principle_integrity_calls_cross_domain_context(
        self, principles_service: PrinciplesService
    ) -> None:
        """calculate_principle_integrity calls relationships.get_cross_domain_context."""
        mock_context = {"tasks": [], "goals": []}
        principles_service.relationships.get_cross_domain_context = AsyncMock(
            return_value=Result.ok(mock_context)
        )

        result = await principles_service.calculate_principle_integrity(
            "user_test", "principle_abc"
        )

        assert result.is_ok
        assert result.value["principle_uid"] == "principle_abc"
        assert result.value["user_uid"] == "user_test"
        principles_service.relationships.get_cross_domain_context.assert_called_once_with(
            "principle_abc"
        )


# ---------------------------------------------------------------------------
# TestPrinciplesServiceSearch
# ---------------------------------------------------------------------------


class TestPrinciplesServiceSearch:
    @pytest.mark.asyncio
    async def test_search_principles_no_filter_returns_all_results(
        self, principles_service: PrinciplesService
    ) -> None:
        """search_principles with no filters returns all search results."""
        p1 = Mock()
        p1.category = PrincipleCategory.ETHICAL
        p2 = Mock()
        p2.category = PrincipleCategory.PERSONAL
        principles_service.search.search = AsyncMock(return_value=Result.ok([p1, p2]))

        result = await principles_service.search_principles("integrity")

        assert result.is_ok
        assert len(result.value) == 2

    @pytest.mark.asyncio
    async def test_search_principles_category_filter_narrows_results(
        self, principles_service: PrinciplesService
    ) -> None:
        """search_principles with category filter returns only matching principles."""
        p_ethics = Mock(spec=Principle)
        p_ethics.category = PrincipleCategory.ETHICAL
        p_discipline = Mock(spec=Principle)
        p_discipline.category = PrincipleCategory.PERSONAL
        principles_service.search.search = AsyncMock(
            return_value=Result.ok([p_ethics, p_discipline])
        )

        result = await principles_service.search_principles(
            "values", filters={"category": PrincipleCategory.ETHICAL}
        )

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].category == PrincipleCategory.ETHICAL


# ---------------------------------------------------------------------------
# TestPrinciplesServiceRelationships
# ---------------------------------------------------------------------------


class TestPrinciplesServiceRelationships:
    @pytest.mark.asyncio
    async def test_link_principle_to_knowledge_passes_relevance(
        self, principles_service: PrinciplesService
    ) -> None:
        """link_principle_to_knowledge passes relevance param to relationships."""
        principles_service.relationships.link_to_knowledge = AsyncMock(
            return_value=Result.ok(True)
        )

        await principles_service.link_principle_to_knowledge(
            "principle_abc", "ku_stoicism_xyz", relevance="foundational"
        )

        principles_service.relationships.link_to_knowledge.assert_called_once_with(
            "principle_abc",
            "ku_stoicism_xyz",
            relevance="foundational",
        )
