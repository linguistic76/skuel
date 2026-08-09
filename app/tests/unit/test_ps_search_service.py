# mypy: disable-error-code="attr-defined"
"""
Test PS (PathStep) Search Service
=================================

Tests for the PsSearchService - BaseService pattern (January 2026 harmonization).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.pathways.path_step import PathStep
from core.models.pathways.path_step_dto import PathStepDTO
from core.services.ps.ps_search_service import PsSearchService
from core.utils.result_simplified import Result


class TestPsSearchServiceInitialization:
    """Test PsSearchService initialization - BaseService pattern."""

    def test_initialization_with_all_dependencies(self):
        """Test successful initialization with backend, then attrs set post-construction."""
        backend = MagicMock()
        intelligence = MagicMock()
        query_builder = MagicMock()

        service = PsSearchService(backend=backend)
        service.intelligence = intelligence
        service.query_builder = query_builder

        assert service.backend == backend
        assert service.intelligence == intelligence
        assert service.query_builder == query_builder

    def test_initialization_with_minimal_dependencies(self):
        """Test initialization with only required backend."""
        backend = MagicMock()

        service = PsSearchService(backend=backend)

        assert service.backend == backend

    def test_entity_label_is_entity(self):
        """Test that entity_label returns 'Entity' (multi-label base)."""
        backend = MagicMock()
        service = PsSearchService(backend=backend)

        assert service.entity_label == "Entity"

    def test_class_attributes_configured_correctly(self):
        """Test that class attributes are configured for PS (PathStep) via DomainConfig."""
        backend = MagicMock()
        service = PsSearchService(backend=backend)

        # PsSearchService uses _config = DomainConfig(...) pattern
        # Access through _config, not legacy _dto_class attribute
        assert service._config.dto_class == PathStepDTO
        assert service._config.model_class == PathStep
        assert "title" in service._config.search_fields
        assert "intent" in service._config.search_fields
        assert "description" in service._config.search_fields
        assert service._config.user_ownership_relationship is None  # Shared content


class TestTextSearch:
    """Test text search operations inherited from BaseService."""

    @pytest.fixture
    def service(self) -> PsSearchService:
        """Create service with mocked dependencies."""
        backend = MagicMock()
        svc = PsSearchService(backend=backend)
        svc.query_builder = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_search_by_tags_empty_tags(self, service):
        """Test that empty tags list returns validation error."""
        result = await service.search_by_tags([])

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_by_tags_delegates_to_base(self, service):
        """Test tag search delegates to BaseService.search_by_tags."""
        # Mock the backend.array_any_match_raw with proper data format
        service.backend.array_any_match_raw = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "entity": {
                            "uid": "ps.test.1",
                            "title": "Match",
                            "domain": "tech",
                            "quality_score": 0.0,
                            "complexity": "medium",
                            "semantic_links": [],
                            "tags": [],
                        }
                    }
                ]
            )
        )

        await service.search_by_tags(["python", "advanced"], match_all=True)

        # The key assertion is that it calls the right backend method
        service.backend.array_any_match_raw.assert_called()


class TestFacadeDelegation:
    """Test that PsService facade correctly delegates to search service."""

    def test_facade_has_search_methods(self):
        """Test that all search methods exist on PsService."""
        from core.services.ps_service import PsService

        # Verify search methods exist on facade
        assert callable(getattr(PsService, "search_by_tags", None))
        assert callable(getattr(PsService, "search_steps", None))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
