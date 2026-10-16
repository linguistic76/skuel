# mypy: disable-error-code="attr-defined,assignment"
"""
Unit tests for PsService facade orchestration methods.

Tests focus on explicit orchestration logic (validation guards, multi-step
sequencing, enum conversion) — NOT pure delegation methods (*args/**kwargs).
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.services.ps_service import PsService
from core.utils.result_simplified import Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_repo() -> Mock:
    backend = Mock()
    backend.get_many = AsyncMock(return_value=Result.ok([]))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def ps_service(mock_repo: Mock) -> PsService:
    # PsService has 12+ sub-services each with fail-fast dependencies.
    # Bypass __init__ entirely and wire sub-services directly — the pattern for
    # testing facade orchestration logic without touching infrastructure.
    service = object.__new__(PsService)
    service.core = AsyncMock()
    service.search_service = AsyncMock()
    service.search = service.search_service
    service.graph = AsyncMock()
    service.semantic = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.organization = AsyncMock()
    service.repo = mock_repo
    service.neo4j_adapter = None
    service.logger = Mock()
    return service


# ---------------------------------------------------------------------------
# TestPsServiceOrganizationGuard
# ---------------------------------------------------------------------------


class TestPsServiceOrganizationGuard:
    @pytest.mark.asyncio
    async def test_get_organized_children_fails_when_organization_is_none(
        self, ps_service: PsService
    ) -> None:
        """get_organized_children() returns fail when organization service is None."""
        ps_service.organization = None

        result = await ps_service.get_organized_children("ps:parent_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_find_organizers_fails_when_organization_is_none(
        self, ps_service: PsService
    ) -> None:
        """find_organizers() returns fail when organization service is None."""
        ps_service.organization = None

        result = await ps_service.find_organizers("ps:abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestPsServiceGetKnowledgeRelationships
# ---------------------------------------------------------------------------


class TestPsServiceGetStepRelationships:
    @pytest.mark.asyncio
    async def test_missing_relationship_type_returns_validation_error(
        self, ps_service: PsService
    ) -> None:
        """get_step_relationships returns validation error when relationship_type is None."""
        result = await ps_service.get_step_relationships("ps:abc123", relationship_type=None)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_invalid_relationship_type_returns_validation_error(
        self, ps_service: PsService
    ) -> None:
        """get_step_relationships returns validation error for unknown type string."""
        result = await ps_service.get_step_relationships(
            "ps:abc123", relationship_type="not:a:valid:type"
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_valid_relationship_type_delegates_to_semantic(
        self, ps_service: PsService
    ) -> None:
        """get_step_relationships delegates to semantic service for valid type string."""
        ps_service.semantic.get_relationships_by_type = AsyncMock(
            return_value=Result.ok([{"rel": "data"}])
        )
        valid_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING.value

        result = await ps_service.get_step_relationships("ps:abc123", relationship_type=valid_type)

        assert result.is_ok
        ps_service.semantic.get_relationships_by_type.assert_called_once_with(
            uid="ps:abc123",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        )


# ---------------------------------------------------------------------------
# TestPsServiceTagManagement
# ---------------------------------------------------------------------------
