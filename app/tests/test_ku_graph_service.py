"""
Test KU Graph Service
======================

Tests for the LessonGraphService focused sub-service.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain
from core.services.lesson.lesson_graph_service import LessonGraphService
from core.utils.result_simplified import Result


def make_ku_dto(uid="ku.test.1", title="Test Title", domain="tech"):
    """Helper to create complete CurriculumDTO for tests."""
    return CurriculumDTO(
        uid=uid,
        title=title,
        domain=Domain(domain),
        quality_score=0.0,
        complexity="medium",
        semantic_links=[],
        tags=[],
        metadata={},
    )


class TestKuGraphServiceInitialization:
    """Test LessonGraphService initialization."""

    def test_initialization_with_all_dependencies(self):
        """Test successful initialization with all dependencies."""
        repo = MagicMock()
        graph_intel = MagicMock()

        service = LessonGraphService(repo=repo, graph_intel=graph_intel)

        assert service.repo == repo
        assert service.graph_intel == graph_intel

    def test_initialization_without_optional_dependencies(self):
        """Test initialization works without optional graph_intel."""
        repo = MagicMock()

        service = LessonGraphService(repo=repo)

        assert service.repo == repo
        assert service.graph_intel is None

    def test_initialization_fails_without_repo(self):
        """Test that initialization fails without required repo."""
        with pytest.raises(ValueError, match="KU repository is required"):
            LessonGraphService(repo=None)


class TestGraphTraversal:
    """Test graph traversal operations."""

    @pytest.fixture
    def service(self) -> LessonGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        return LessonGraphService(repo=repo)

    @pytest.mark.asyncio
    async def test_find_prerequisites_unit_not_found(self, service):
        """Test find_prerequisites when unit doesn't exist."""
        service.repo.get = AsyncMock(return_value=Result.fail(MagicMock()))

        result = await service.find_prerequisites("ku.nonexistent")

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_find_prerequisites_success(self, service):
        """Test successful prerequisite discovery."""

        # Mock repo.get for source AND prerequisites
        async def get_unit(uid):
            if uid == "ku.test.1":
                return Result.ok(make_ku_dto("ku.test.1", "Source"))
            elif uid == "ku.prereq.1":
                return Result.ok(make_ku_dto("ku.prereq.1", "Prereq 1"))
            elif uid == "ku.prereq.2":
                return Result.ok(make_ku_dto("ku.prereq.2", "Prereq 2"))
            return Result.fail(MagicMock())

        service.repo.get = AsyncMock(side_effect=get_unit)

        # Mock backend method returns prerequisites - wrapped in Result.ok()
        service.repo.find_prerequisite_chain = AsyncMock(
            return_value=Result.ok(
                [{"prereq": {"uid": "ku.prereq.1"}}, {"prereq": {"uid": "ku.prereq.2"}}]
            )
        )

        result = await service.find_prerequisites("ku.test.1", depth=3)

        assert result.is_ok
        assert len(result.value) == 2

    @pytest.mark.asyncio
    async def test_find_next_steps_unit_not_found(self, service):
        """Test find_next_steps when unit doesn't exist."""
        service.repo.get = AsyncMock(return_value=Result.fail(MagicMock()))

        result = await service.find_next_steps("ku.nonexistent")

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_find_next_steps_success(self, service):
        """Test successful next steps discovery."""

        # Mock repo.get for source AND next steps
        async def get_unit(uid):
            if uid == "ku.test.1":
                return Result.ok(make_ku_dto("ku.test.1", "Source"))
            elif uid == "ku.next.1":
                return Result.ok(make_ku_dto("ku.next.1", "Next 1"))
            elif uid == "ku.next.2":
                return Result.ok(make_ku_dto("ku.next.2", "Next 2"))
            return Result.fail(MagicMock())

        service.repo.get = AsyncMock(side_effect=get_unit)

        # Mock backend method returns next steps
        service.repo.find_next_steps = AsyncMock(
            return_value=Result.ok(
                [{"target": {"uid": "ku.next.1"}}, {"target": {"uid": "ku.next.2"}}]
            )
        )

        result = await service.find_next_steps("ku.test.1", limit=10)

        assert result.is_ok
        assert len(result.value) == 2

    @pytest.mark.asyncio
    async def test_get_knowledge_with_context_success(self, service):
        """Test successful context retrieval."""
        # Mock main unit
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Main Unit")))

        # Mock find_prerequisites and find_next_steps
        service.find_prerequisites = AsyncMock(
            return_value=Result.ok([make_ku_dto("ku.prereq.1", "Prereq")])
        )
        service.find_next_steps = AsyncMock(
            return_value=Result.ok([make_ku_dto("ku.next.1", "Next")])
        )

        result = await service.get_lesson_with_context("ku.test.1", depth=2)

        assert result.is_ok
        context = result.value
        assert "unit" in context
        assert "prerequisites" in context
        assert "next_steps" in context
        assert context["total_prerequisites"] == 1
        assert context["total_next_steps"] == 1


class TestRelationshipManagement:
    """Test relationship creation and management."""

    @pytest.fixture
    def service(self) -> LessonGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        return LessonGraphService(repo=repo)

    @pytest.mark.asyncio
    async def test_link_prerequisite_unit_not_found(self, service):
        """Test link_prerequisite fails when unit doesn't exist."""
        service.repo.get = AsyncMock(return_value=Result.fail(MagicMock()))

        result = await service.link_prerequisite("ku.test.1", "ku.prereq.1")

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_link_prerequisite_success(self, service):
        """Test successful prerequisite linking."""
        # Mock both units exist
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto()))

        # Mock backend method
        service.repo.link_prerequisite = AsyncMock(return_value=Result.ok([]))

        result = await service.link_prerequisite("ku.test.1", "ku.prereq.1", is_mandatory=True)

        assert result.is_ok
        assert result.value is True
        service.repo.link_prerequisite.assert_called_once()

    @pytest.mark.asyncio
    async def test_link_parent_child_success(self, service):
        """Test successful parent-child linking."""
        # Mock both units exist
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto()))

        # Mock backend method
        service.repo.link_parent_child = AsyncMock(return_value=Result.ok([]))

        result = await service.link_parent_child("ku.parent.1", "ku.child.1")

        assert result.is_ok
        assert result.value is True
        service.repo.link_parent_child.assert_called_once()


class TestAnalysisRecommendations:
    """Test analysis and recommendation operations."""

    @pytest.fixture
    def service(self) -> LessonGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        graph_intel = MagicMock()
        return LessonGraphService(repo=repo, graph_intel=graph_intel)

    @pytest.mark.asyncio
    async def test_get_prerequisite_chain_success(self, service):
        """Test successful prerequisite chain retrieval."""
        # Mock find_prerequisites
        service.find_prerequisites = AsyncMock(
            return_value=Result.ok(
                [make_ku_dto("ku.prereq.1", "Prereq 1"), make_ku_dto("ku.prereq.2", "Prereq 2")]
            )
        )

        result = await service.get_prerequisite_chain("ku.test.1")

        assert result.is_ok
        chain = result.value
        assert "target_uid" in chain
        assert chain["target_uid"] == "ku.test.1"
        assert chain["total_count"] == 2
        assert "prerequisites" in chain
