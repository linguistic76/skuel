"""
Unit tests for LessonService facade orchestration methods.

Tests focus on explicit orchestration logic (validation guards, multi-step
sequencing, enum conversion) — NOT pure delegation methods (*args/**kwargs).
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.services.lesson_service import LessonService
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
def lesson_service(mock_repo: Mock) -> LessonService:
    # LessonService has 9+ sub-services each with fail-fast dependencies.
    # Bypass __init__ entirely and wire sub-services directly — the pattern for
    # testing facade orchestration logic without touching infrastructure.
    service = object.__new__(LessonService)
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
# TestLessonServiceOrganizationGuard
# ---------------------------------------------------------------------------


class TestLessonServiceOrganizationGuard:
    @pytest.mark.asyncio
    async def test_organize_fails_when_organization_is_none(
        self, lesson_service: LessonService
    ) -> None:
        """organize() returns fail when organization service is None."""
        lesson_service.organization = None

        result = await lesson_service.organize("ku_parent_abc", "ku_child_xyz")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_unorganize_fails_when_organization_is_none(
        self, lesson_service: LessonService
    ) -> None:
        """unorganize() returns fail when organization service is None."""
        lesson_service.organization = None

        result = await lesson_service.unorganize("ku_parent_abc", "ku_child_xyz")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_organize_delegates_when_organization_available(
        self, lesson_service: LessonService
    ) -> None:
        """organize() delegates to organization service when available."""
        lesson_service.organization.organize = AsyncMock(return_value=Result.ok(True))

        result = await lesson_service.organize("ku_parent_abc", "ku_child_xyz")

        assert result.is_ok
        lesson_service.organization.organize.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_organized_children_fails_when_organization_is_none(
        self, lesson_service: LessonService
    ) -> None:
        """get_organized_children() returns fail when organization service is None."""
        lesson_service.organization = None

        result = await lesson_service.get_organized_children("ku_parent_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_find_organizers_fails_when_organization_is_none(
        self, lesson_service: LessonService
    ) -> None:
        """find_organizers() returns fail when organization service is None."""
        lesson_service.organization = None

        result = await lesson_service.find_organizers("ku_abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestLessonServiceGetKnowledgeRelationships
# ---------------------------------------------------------------------------


class TestLessonServiceGetLessonRelationships:
    @pytest.mark.asyncio
    async def test_missing_relationship_type_returns_validation_error(
        self, lesson_service: LessonService
    ) -> None:
        """get_lesson_relationships returns validation error when relationship_type is None."""
        result = await lesson_service.get_lesson_relationships("ku_abc123", relationship_type=None)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_invalid_relationship_type_returns_validation_error(
        self, lesson_service: LessonService
    ) -> None:
        """get_lesson_relationships returns validation error for unknown type string."""
        result = await lesson_service.get_lesson_relationships(
            "ku_abc123", relationship_type="not:a:valid:type"
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_valid_relationship_type_delegates_to_semantic(
        self, lesson_service: LessonService
    ) -> None:
        """get_lesson_relationships delegates to semantic service for valid type string."""
        lesson_service.semantic.get_relationships_by_type = AsyncMock(
            return_value=Result.ok([{"rel": "data"}])
        )
        valid_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING.value

        result = await lesson_service.get_lesson_relationships(
            "ku_abc123", relationship_type=valid_type
        )

        assert result.is_ok
        lesson_service.semantic.get_relationships_by_type.assert_called_once_with(
            uid="ku_abc123",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        )


# ---------------------------------------------------------------------------
# TestLessonServiceTagManagement
# ---------------------------------------------------------------------------


class TestLessonServiceTagManagement:
    @pytest.mark.asyncio
    async def test_add_lesson_tags_merges_without_duplicates(
        self, lesson_service: LessonService
    ) -> None:
        """add_lesson_tags merges new tags with existing without duplicates."""
        mock_ku = Mock()
        mock_ku.tags = ["existing", "tag"]
        lesson_service.core.get = AsyncMock(return_value=Result.ok(mock_ku))
        lesson_service.core.update = AsyncMock(return_value=Result.ok(mock_ku))

        await lesson_service.add_lesson_tags("ku_abc123", ["new", "existing"])

        call_args = lesson_service.core.update.call_args
        updated_tags = set(call_args[0][1]["tags"])
        assert updated_tags == {"existing", "tag", "new"}

    @pytest.mark.asyncio
    async def test_add_lesson_tags_propagates_core_get_failure(
        self, lesson_service: LessonService
    ) -> None:
        """add_lesson_tags propagates failure from core.get without calling core.update."""
        lesson_service.core.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "DB error"))
        )

        result = await lesson_service.add_lesson_tags("ku_abc123", ["tag1"])

        assert result.is_error
        lesson_service.core.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_lesson_tags_returns_not_found_for_missing_ku(
        self, lesson_service: LessonService
    ) -> None:
        """add_lesson_tags returns not_found when core.get returns None."""
        lesson_service.core.get = AsyncMock(return_value=Result.ok(None))

        result = await lesson_service.add_lesson_tags("ku_abc123", ["tag1"])

        assert result.is_error
        lesson_service.core.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_lesson_tags_filters_specified_tags(
        self, lesson_service: LessonService
    ) -> None:
        """remove_lesson_tags removes specified tags and keeps the rest."""
        mock_ku = Mock()
        mock_ku.tags = ["keep", "remove_me", "also_keep"]
        lesson_service.core.get = AsyncMock(return_value=Result.ok(mock_ku))
        lesson_service.core.update = AsyncMock(return_value=Result.ok(mock_ku))

        await lesson_service.remove_lesson_tags("ku_abc123", ["remove_me"])

        call_args = lesson_service.core.update.call_args
        updated_tags = call_args[0][1]["tags"]
        assert "remove_me" not in updated_tags
        assert "keep" in updated_tags
        assert "also_keep" in updated_tags

    @pytest.mark.asyncio
    async def test_remove_lesson_tags_propagates_core_get_failure(
        self, lesson_service: LessonService
    ) -> None:
        """remove_lesson_tags propagates failure from core.get without calling core.update."""
        lesson_service.core.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "DB error"))
        )

        result = await lesson_service.remove_lesson_tags("ku_abc123", ["tag1"])

        assert result.is_error
        lesson_service.core.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_lesson_tags_returns_not_found_for_missing_ku(
        self, lesson_service: LessonService
    ) -> None:
        """remove_lesson_tags returns not_found when core.get returns None."""
        lesson_service.core.get = AsyncMock(return_value=Result.ok(None))

        result = await lesson_service.remove_lesson_tags("ku_abc123", ["tag1"])

        assert result.is_error
        lesson_service.core.update.assert_not_called()
