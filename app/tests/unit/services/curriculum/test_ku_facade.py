"""
Unit tests for ArticleService facade orchestration methods.

Tests focus on explicit orchestration logic (validation guards, multi-step
sequencing, enum conversion) — NOT pure delegation methods (*args/**kwargs).
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.services.article_service import ArticleService
from core.utils.result_simplified import Errors, Result

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
def ku_service(mock_repo: Mock) -> ArticleService:
    # ArticleService has 9+ sub-services each with fail-fast dependencies.
    # Bypass __init__ entirely and wire sub-services directly — the pattern for
    # testing facade orchestration logic without touching infrastructure.
    service = object.__new__(ArticleService)
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
# TestKuServiceOrganizationGuard
# ---------------------------------------------------------------------------


class TestKuServiceOrganizationGuard:
    @pytest.mark.asyncio
    async def test_organize_fails_when_organization_is_none(self, ku_service: ArticleService) -> None:
        """organize() returns fail when organization service is None."""
        ku_service.organization = None

        result = await ku_service.organize("ku_parent_abc", "ku_child_xyz")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_unorganize_fails_when_organization_is_none(self, ku_service: ArticleService) -> None:
        """unorganize() returns fail when organization service is None."""
        ku_service.organization = None

        result = await ku_service.unorganize("ku_parent_abc", "ku_child_xyz")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_organize_delegates_when_organization_available(
        self, ku_service: ArticleService
    ) -> None:
        """organize() delegates to organization service when available."""
        ku_service.organization.organize = AsyncMock(return_value=Result.ok(True))

        result = await ku_service.organize("ku_parent_abc", "ku_child_xyz")

        assert result.is_ok
        ku_service.organization.organize.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_organized_children_fails_when_organization_is_none(
        self, ku_service: ArticleService
    ) -> None:
        """get_organized_children() returns fail when organization service is None."""
        ku_service.organization = None

        result = await ku_service.get_organized_children("ku_parent_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_find_organizers_fails_when_organization_is_none(
        self, ku_service: ArticleService
    ) -> None:
        """find_organizers() returns fail when organization service is None."""
        ku_service.organization = None

        result = await ku_service.find_organizers("ku_abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestKuServiceGetKnowledgeRelationships
# ---------------------------------------------------------------------------


class TestKuServiceGetKnowledgeRelationships:
    @pytest.mark.asyncio
    async def test_missing_relationship_type_returns_validation_error(
        self, ku_service: ArticleService
    ) -> None:
        """get_knowledge_relationships returns validation error when relationship_type is None."""
        result = await ku_service.get_knowledge_relationships("ku_abc123", relationship_type=None)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_invalid_relationship_type_returns_validation_error(
        self, ku_service: ArticleService
    ) -> None:
        """get_knowledge_relationships returns validation error for unknown type string."""
        result = await ku_service.get_knowledge_relationships(
            "ku_abc123", relationship_type="not:a:valid:type"
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_valid_relationship_type_delegates_to_semantic(
        self, ku_service: ArticleService
    ) -> None:
        """get_knowledge_relationships delegates to semantic service for valid type string."""
        ku_service.semantic.get_relationships_by_type = AsyncMock(
            return_value=Result.ok([{"rel": "data"}])
        )
        valid_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING.value

        result = await ku_service.get_knowledge_relationships(
            "ku_abc123", relationship_type=valid_type
        )

        assert result.is_ok
        ku_service.semantic.get_relationships_by_type.assert_called_once_with(
            uid="ku_abc123",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        )


# ---------------------------------------------------------------------------
# TestKuServiceTagManagement
# ---------------------------------------------------------------------------


class TestKuServiceTagManagement:
    @pytest.mark.asyncio
    async def test_add_knowledge_tags_merges_without_duplicates(
        self, ku_service: ArticleService
    ) -> None:
        """add_knowledge_tags merges new tags with existing without duplicates."""
        mock_ku = Mock()
        mock_ku.tags = ["existing", "tag"]
        ku_service.core.get = AsyncMock(return_value=Result.ok(mock_ku))
        ku_service.core.update = AsyncMock(return_value=Result.ok(mock_ku))

        await ku_service.add_knowledge_tags("ku_abc123", ["new", "existing"])

        call_args = ku_service.core.update.call_args
        updated_tags = set(call_args[0][1]["tags"])
        assert updated_tags == {"existing", "tag", "new"}

    @pytest.mark.asyncio
    async def test_add_knowledge_tags_propagates_core_get_failure(
        self, ku_service: ArticleService
    ) -> None:
        """add_knowledge_tags propagates failure from core.get without calling core.update."""
        ku_service.core.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "DB error"))
        )

        result = await ku_service.add_knowledge_tags("ku_abc123", ["tag1"])

        assert result.is_error
        ku_service.core.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_knowledge_tags_returns_not_found_for_missing_ku(
        self, ku_service: ArticleService
    ) -> None:
        """add_knowledge_tags returns not_found when core.get returns None."""
        ku_service.core.get = AsyncMock(return_value=Result.ok(None))

        result = await ku_service.add_knowledge_tags("ku_abc123", ["tag1"])

        assert result.is_error
        ku_service.core.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_knowledge_tags_filters_specified_tags(
        self, ku_service: ArticleService
    ) -> None:
        """remove_knowledge_tags removes specified tags and keeps the rest."""
        mock_ku = Mock()
        mock_ku.tags = ["keep", "remove_me", "also_keep"]
        ku_service.core.get = AsyncMock(return_value=Result.ok(mock_ku))
        ku_service.core.update = AsyncMock(return_value=Result.ok(mock_ku))

        await ku_service.remove_knowledge_tags("ku_abc123", ["remove_me"])

        call_args = ku_service.core.update.call_args
        updated_tags = call_args[0][1]["tags"]
        assert "remove_me" not in updated_tags
        assert "keep" in updated_tags
        assert "also_keep" in updated_tags

    @pytest.mark.asyncio
    async def test_remove_knowledge_tags_propagates_core_get_failure(
        self, ku_service: ArticleService
    ) -> None:
        """remove_knowledge_tags propagates failure from core.get without calling core.update."""
        ku_service.core.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "DB error"))
        )

        result = await ku_service.remove_knowledge_tags("ku_abc123", ["tag1"])

        assert result.is_error
        ku_service.core.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_knowledge_tags_returns_not_found_for_missing_ku(
        self, ku_service: ArticleService
    ) -> None:
        """remove_knowledge_tags returns not_found when core.get returns None."""
        ku_service.core.get = AsyncMock(return_value=Result.ok(None))

        result = await ku_service.remove_knowledge_tags("ku_abc123", ["tag1"])

        assert result.is_error
        ku_service.core.update.assert_not_called()
