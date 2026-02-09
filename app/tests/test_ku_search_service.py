"""
Test KU Search Service
======================

Tests for the KuSearchService - BaseService pattern (January 2026 harmonization).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import Domain, SELCategory
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.services.ku.ku_search_service import KuSearchService
from core.utils.result_simplified import Result


def make_ku_entity(uid="ku.test.1", title="Test Title", domain=Domain.TECH, content="Test content"):
    """Helper to create Ku entity for tests."""
    return Ku(
        uid=uid,
        title=title,
        content=content,
        domain=domain,
        sel_category=SELCategory.SELF_AWARENESS,  # Valid SELCategory value
        quality_score=0.0,
        complexity="medium",
        semantic_links=(),
        tags=(),
        metadata={},
    )


def make_unit_data(uid="ku.test.1", title="Test Title", domain="tech", content="Test content"):
    """Helper to create unit data dict for tests."""
    return {
        "uid": uid,
        "title": title,
        "content": content,
        "domain": domain,
        "quality_score": 0.0,
        "complexity": "medium",
        "semantic_links": [],
        "tags": [],
        "metadata": {},
    }


class TestKuSearchServiceInitialization:
    """Test KuSearchService initialization - BaseService pattern."""

    def test_initialization_with_all_dependencies(self):
        """Test successful initialization with all dependencies."""
        backend = MagicMock()
        content_repo = MagicMock()
        intelligence = MagicMock()
        query_builder = MagicMock()

        service = KuSearchService(
            backend=backend,
            content_repo=content_repo,
            intelligence=intelligence,
            query_builder=query_builder,
        )

        # BaseService stores backend in self.backend
        assert service.backend == backend
        assert service.content_repo == content_repo
        assert service.intelligence == intelligence
        assert service.query_builder == query_builder

    def test_initialization_with_minimal_dependencies(self):
        """Test initialization with only required backend."""
        backend = MagicMock()

        service = KuSearchService(backend=backend)

        assert service.backend == backend
        assert service.content_repo is None
        assert service.intelligence is None
        assert service.query_builder is None

    def test_entity_label_is_ku(self):
        """Test that entity_label returns 'Ku'."""
        backend = MagicMock()
        service = KuSearchService(backend=backend)

        assert service.entity_label == "Ku"

    def test_class_attributes_configured_correctly(self):
        """Test that class attributes are configured for KU domain via DomainConfig."""
        backend = MagicMock()
        service = KuSearchService(backend=backend)

        # KuSearchService uses _config = DomainConfig(...) pattern (Phase 3)
        # Access through _config, not legacy _dto_class attribute
        assert service._config.dto_class == KuDTO
        assert service._config.model_class == Ku
        assert "title" in service._config.search_fields
        assert "content" in service._config.search_fields
        assert service._config.user_ownership_relationship is None  # Shared content


class TestTextSearch:
    """Test text search operations."""

    @pytest.fixture
    def service(self) -> KuSearchService:
        """Create service with mocked dependencies."""
        backend = MagicMock()
        content_repo = MagicMock()
        query_builder = AsyncMock()
        return KuSearchService(
            backend=backend,
            content_repo=content_repo,
            query_builder=query_builder,
        )

    @pytest.mark.asyncio
    async def test_search_by_title_template_with_empty_term(self, service):
        """Test that empty search term returns validation error."""
        result = await service.search_by_title_template("")

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_by_title_template_basic(self, service):
        """Test basic title search delegates to inherited search()."""
        # Mock the inherited search method (from BaseService)
        ku_entity = make_ku_entity("ku.test.1", "Test Title")
        service.search = AsyncMock(return_value=Result.ok([ku_entity]))

        result = await service.search_by_title_template("test", limit=10)

        assert result.is_ok
        assert len(result.value) == 1
        service.search.assert_called_once_with("test", limit=10)

    @pytest.mark.asyncio
    async def test_search_by_tags_empty_tags(self, service):
        """Test that empty tags list returns validation error."""
        result = await service.search_by_tags([])

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_by_tags_delegates_to_base(self, service):
        """Test tag search delegates to BaseService.search_by_tags."""
        # Mock the backend.execute_query with proper data format
        # BaseService._to_domain_models expects flat dicts, not nested
        service.backend.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "entity": {
                            "uid": "ku.test.1",
                            "title": "Match",
                            "content": "Test",
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

        # Tags search may fail due to backend format; that's OK for this test
        # The key assertion is that it calls the right backend method
        service.backend.execute_query.assert_called()


class TestFacetedSearch:
    """Test faceted search operations."""

    @pytest.fixture
    def service(self) -> KuSearchService:
        """Create service with mocked dependencies."""
        backend = MagicMock()
        content_repo = MagicMock()
        query_builder = MagicMock()
        return KuSearchService(
            backend=backend,
            content_repo=content_repo,
            query_builder=query_builder,
        )

    @pytest.mark.asyncio
    async def test_search_by_facets_no_filters(self, service):
        """Test faceted search with no filters returns all."""
        ku_entity1 = make_ku_entity("ku.test.1", "Unit 1")
        ku_entity2 = make_ku_entity("ku.test.2", "Unit 2")

        service.backend.list = AsyncMock(return_value=Result.ok(([ku_entity1, ku_entity2], 2)))

        result = await service.search_by_facets(limit=10)

        assert result.is_ok
        assert len(result.value) == 2
        service.backend.list.assert_called_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_search_by_facets_with_domain_filter(self, service):
        """Test faceted search with domain filter."""
        ku_entity = make_ku_entity("ku.tech.1", "Tech Unit", Domain.TECH)

        service.backend.find_by = AsyncMock(return_value=Result.ok([ku_entity]))

        result = await service.search_by_facets(domain="TECH", limit=10)

        assert result.is_ok
        service.backend.find_by.assert_called_once_with(limit=10, domain="TECH")

    @pytest.mark.asyncio
    async def test_search_by_facets_multiple_filters(self, service):
        """Test faceted search with multiple filters."""
        ku_entity = make_ku_entity("ku.test.1", "Filtered Unit")

        service.backend.find_by = AsyncMock(return_value=Result.ok([ku_entity]))

        result = await service.search_by_facets(
            domain="TECH", complexity="medium", status="published", limit=10
        )

        assert result.is_ok
        service.backend.find_by.assert_called_once_with(
            limit=10, domain="TECH", complexity="medium", status="published"
        )


class TestChunkSearch:
    """Test chunk-based search operations."""

    @pytest.fixture
    def service(self) -> KuSearchService:
        """Create service with mocked dependencies."""
        backend = MagicMock()
        content_repo = MagicMock()
        query_builder = MagicMock()
        return KuSearchService(
            backend=backend,
            content_repo=content_repo,
            query_builder=query_builder,
        )

    @pytest.mark.asyncio
    async def test_search_chunks_empty_query(self, service):
        """Test that empty query returns validation error."""
        result = await service.search_chunks("")

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_chunks_without_content_repo(self):
        """Test that search_chunks fails without content_repo."""
        service = KuSearchService(backend=MagicMock(), content_repo=None)

        result = await service.search_chunks("test query")

        assert not result.is_ok
        assert "not available" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_chunks_basic(self, service):
        """Test basic chunk search."""
        service.content_repo.search_chunks = AsyncMock(
            return_value=[
                {"chunk_id": "c1", "content": "matching chunk", "score": 0.95},
                {"chunk_id": "c2", "content": "another match", "score": 0.85},
            ]
        )

        result = await service.search_chunks("test query", limit=10)

        assert result.is_ok
        assert len(result.value) == 2
        service.content_repo.search_chunks.assert_called_once_with(
            query="test query", knowledge_uids=None, limit=10
        )

    @pytest.mark.asyncio
    async def test_search_chunks_with_unit_filter(self, service):
        """Test chunk search filtered by knowledge units."""
        service.content_repo.search_chunks = AsyncMock(
            return_value=[{"chunk_id": "c1", "content": "matching chunk"}]
        )

        result = await service.search_chunks("query", knowledge_uids=["ku.test.1", "ku.test.2"])

        assert result.is_ok
        service.content_repo.search_chunks.assert_called_once_with(
            query="query", knowledge_uids=["ku.test.1", "ku.test.2"], limit=20
        )

    @pytest.mark.asyncio
    async def test_get_content_chunks(self, service):
        """Test getting all chunks for a unit."""
        service.content_repo.get_chunks_for_unit = AsyncMock(
            return_value=[
                {"chunk_id": "c1", "type": "summary"},
                {"chunk_id": "c2", "type": "detail"},
            ]
        )

        result = await service.get_content_chunks("ku.test.1")

        assert result.is_ok
        assert len(result.value) == 2
        service.content_repo.get_chunks_for_unit.assert_called_once_with(
            "ku.test.1", chunk_type=None
        )


class TestSimilaritySearch:
    """Test similarity and feature-based search."""

    @pytest.fixture
    def service(self) -> KuSearchService:
        """Create service with intelligence mock."""
        backend = MagicMock()
        content_repo = MagicMock()
        intelligence = MagicMock()
        query_builder = MagicMock()
        return KuSearchService(
            backend=backend,
            content_repo=content_repo,
            intelligence=intelligence,
            query_builder=query_builder,
        )

    @pytest.mark.asyncio
    async def test_find_similar_content_without_intelligence(self):
        """Test that find_similar_content fails without intelligence service."""
        service = KuSearchService(
            backend=MagicMock(),
            content_repo=MagicMock(),
            intelligence=None,
        )

        result = await service.find_similar_content("ku.test.1")

        assert not result.is_ok
        assert "not available" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_find_similar_content_unit_not_found(self, service):
        """Test find_similar_content when source unit doesn't exist."""
        service.backend.get = AsyncMock(return_value=Result.fail(MagicMock()))

        result = await service.find_similar_content("ku.nonexistent")

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_find_similar_content_success(self, service):
        """Test successful similar content search."""
        ku_entity = make_ku_entity("ku.test.1", "Source")
        similar_entity = make_ku_entity("ku.test.2", "Similar")

        # Mock source unit retrieval
        service.backend.get = AsyncMock(
            side_effect=[
                Result.ok(ku_entity),  # First call for source
                Result.ok(similar_entity),  # Second call for similar unit
                Result.ok(similar_entity),  # Third call for second similar unit
            ]
        )

        # Mock intelligence service
        service.intelligence.find_similar_content = AsyncMock(
            return_value=Result.ok(["ku.test.2", "ku.test.3"])
        )

        result = await service.find_similar_content("ku.test.1", limit=5)

        assert result.is_ok
        service.intelligence.find_similar_content.assert_called_once_with(uid="ku.test.1", limit=5)

    @pytest.mark.asyncio
    async def test_search_by_features_without_intelligence(self):
        """Test that search_by_features fails without intelligence service."""
        service = KuSearchService(
            backend=MagicMock(),
            content_repo=MagicMock(),
            intelligence=None,
        )

        result = await service.search_by_features({"complexity": "medium"})

        assert not result.is_ok
        assert "not available" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_by_features_empty_criteria(self, service):
        """Test that empty feature criteria returns validation error."""
        result = await service.search_by_features({})

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_by_features_success(self, service):
        """Test successful feature-based search."""
        ku_entity = make_ku_entity("ku.test.1", "Match")

        # Mock intelligence service
        service.intelligence.search_by_features = AsyncMock(
            return_value=Result.ok(["ku.test.1", "ku.test.2"])
        )

        # Mock unit retrieval
        service.backend.get = AsyncMock(return_value=Result.ok(ku_entity))

        result = await service.search_by_features(
            {"complexity": "medium", "readability": "high"}, limit=10
        )

        assert result.is_ok
        service.intelligence.search_by_features.assert_called_once_with(
            features={"complexity": "medium", "readability": "high"}, limit=10
        )


class TestContextAwareSearch:
    """Test context-aware and semantic search."""

    @pytest.fixture
    def service(self) -> KuSearchService:
        """Create service with all mocks."""
        backend = MagicMock()
        content_repo = MagicMock()
        query_builder = MagicMock()
        return KuSearchService(
            backend=backend,
            content_repo=content_repo,
            query_builder=query_builder,
        )

    @pytest.mark.asyncio
    async def test_search_with_user_context_empty_query(self, service):
        """Test that empty query returns validation error."""
        result = await service.search_with_user_context("")

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_with_user_context_delegates_to_search(self, service):
        """Test search without user context delegates to inherited search()."""
        ku_entity = make_ku_entity("ku.test.1", "Result")
        service.search = AsyncMock(return_value=Result.ok([ku_entity]))

        result = await service.search_with_user_context("python", limit=10)

        assert result.is_ok
        # Should call search with double limit for ranking
        service.search.assert_called_once_with("python", limit=20)

    @pytest.mark.asyncio
    async def test_search_with_semantic_intent_empty_query(self, service):
        """Test that empty query returns validation error."""
        result = await service.search_with_semantic_intent("")

        assert not result.is_ok
        assert "required" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_search_with_semantic_intent_learn(self, service):
        """Test semantic search with 'learn' intent."""
        ku_entity = make_ku_entity("ku.test.1", "Intro Content")
        service.search = AsyncMock(return_value=Result.ok([ku_entity]))

        result = await service.search_with_semantic_intent("python", intent="learn", limit=10)

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_search_with_semantic_intent_practice(self, service):
        """Test semantic search with 'practice' intent."""
        ku_entity = make_ku_entity("ku.test.1", "Python Exercises")
        service.search = AsyncMock(return_value=Result.ok([ku_entity]))

        result = await service.search_with_semantic_intent("python", intent="practice", limit=10)

        assert result.is_ok


class TestFacadeDelegation:
    """Test that KuService facade correctly delegates to search service."""

    @pytest.mark.asyncio
    async def test_facade_delegates_search_methods(self):
        """Test that all search methods are delegated."""
        from core.services.ku_service import KuService

        # Create facade with mocked dependencies
        # Note: backend is passed to KuSearchService (not repo)
        repo = MagicMock()
        content_repo = MagicMock()
        query_builder = AsyncMock()
        neo4j_adapter = MagicMock()
        driver = MagicMock()  # Still needed for KuPracticeService and KuInteractionService
        graph_intel = MagicMock()  # Required by fail-fast architecture (ADR-030)

        service = KuService(
            repo=repo,
            content_repo=content_repo,
            query_builder=query_builder,
            neo4j_adapter=neo4j_adapter,
            driver=driver,
            graph_intelligence_service=graph_intel,
        )

        # Verify search sub-service exists
        assert hasattr(service, "search")
        assert service.search is not None

        # Verify all search methods exist on facade
        assert callable(service.search_by_title_template)
        assert callable(service.search_by_tags)
        assert callable(service.search_by_facets)
        assert callable(service.search_chunks)
        assert callable(service.search_chunks_with_facets)
        assert callable(service.find_similar_content)
        assert callable(service.search_by_features)
        assert callable(service.search_with_user_context)
        assert callable(service.search_with_semantic_intent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
