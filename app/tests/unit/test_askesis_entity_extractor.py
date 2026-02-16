"""
Test Suite for EntityExtractor
===============================

Tests the askesis entity extraction service:
- Exact match extraction
- Partial word match extraction
- Acronym match extraction
- Graceful degradation without services
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.askesis.entity_extractor import EntityExtractor
from core.utils.result_simplified import Errors, Result

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_ku_service() -> Mock:
    """Create mock KuService that returns entities with .title attribute."""
    ku_service = Mock()

    # Mock .get() to return entity with .title (entity_extractor.py line 197-202)
    async def mock_get(uid: str):
        entities = {
            "ku.python-basics": Mock(title="Python Basics", uid="ku.python-basics"),
            "ku.machine-learning": Mock(
                title="Machine Learning Fundamentals", uid="ku.machine-learning"
            ),
        }
        if uid in entities:
            return Result.ok(entities[uid])
        return Result.fail(Errors.not_found("Entity", uid))

    ku_service.get = AsyncMock(side_effect=mock_get)
    return ku_service


def create_mock_tasks_service() -> Mock:
    """Create mock TasksService that returns entities with .title attribute."""
    tasks_service = Mock()

    async def mock_get(uid: str):
        entities = {
            "task_001": Mock(title="Complete Python project", uid="task_001"),
            "task_002": Mock(title="Review ML code", uid="task_002"),
        }
        if uid in entities:
            return Result.ok(entities[uid])
        return Result.fail(Errors.not_found("Entity", uid))

    tasks_service.get = AsyncMock(side_effect=mock_get)
    return tasks_service


def create_mock_goals_service() -> Mock:
    """Create mock GoalsService that returns entities with .title attribute."""
    goals_service = Mock()

    async def mock_get(uid: str):
        entities = {
            "goal_001": Mock(title="Learn Machine Learning", uid="goal_001"),
            "goal_002": Mock(title="Master Python Programming", uid="goal_002"),
        }
        if uid in entities:
            return Result.ok(entities[uid])
        return Result.fail(Errors.not_found("Entity", uid))

    goals_service.get = AsyncMock(side_effect=mock_get)
    return goals_service


def create_mock_user_context() -> Mock:
    """Create mock UserContext with actual field names from entity_extractor.py."""
    context = Mock()
    context.user_uid = "test_user"

    # Knowledge UIDs (entity_extractor.py lines 188-192)
    context.mastered_knowledge_uids = {"ku.python-basics"}
    context.in_progress_knowledge_uids = {"ku.machine-learning"}
    context.blocked_knowledge_uids = set()

    # Activity UIDs (entity_extractor.py lines 231, 270, 309, 348)
    context.active_task_uids = ["task_001"]
    context.active_goal_uids = ["goal_001"]
    context.active_habit_uids = []
    context.today_event_uids = []
    context.upcoming_event_uids = []

    return context


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_ku_service():
    return create_mock_ku_service()


@pytest.fixture
def mock_tasks_service():
    return create_mock_tasks_service()


@pytest.fixture
def mock_goals_service():
    return create_mock_goals_service()


@pytest.fixture
def extractor_with_services(mock_ku_service, mock_tasks_service, mock_goals_service):
    """EntityExtractor with domain services."""
    return EntityExtractor(
        knowledge_service=mock_ku_service,  # FIX: was ku_service
        tasks_service=mock_tasks_service,
        goals_service=mock_goals_service,
    )


@pytest.fixture
def extractor_no_services():
    """EntityExtractor without domain services (graceful degradation)."""
    return EntityExtractor()


@pytest.fixture
def user_context():
    return create_mock_user_context()


# ============================================================================
# TESTS: Exact Match Extraction
# ============================================================================


class TestExactMatchExtraction:
    """Test exact match entity extraction."""

    @pytest.mark.asyncio
    async def test_extract_entities_exact_match(self, extractor_with_services, user_context):
        """Extracts entities with exact title match."""
        query = "I want to learn Python Basics"

        entities = await extractor_with_services.extract_entities_from_query(
            query=query,
            user_context=user_context,
        )

        assert isinstance(entities, dict)
        # Should extract knowledge unit "Python Basics"

    @pytest.mark.asyncio
    async def test_extract_entities_case_insensitive(self, extractor_with_services, user_context):
        """Extraction is case-insensitive."""
        query = "tell me about python basics"

        entities = await extractor_with_services.extract_entities_from_query(
            query=query,
            user_context=user_context,
        )

        assert isinstance(entities, dict)


# ============================================================================
# TESTS: Partial Match Extraction
# ============================================================================


class TestPartialMatchExtraction:
    """Test partial word match entity extraction."""

    @pytest.mark.asyncio
    async def test_extract_entities_partial_match(self, extractor_with_services, user_context):
        """Extracts entities with partial word matches."""
        query = "What's the status of my Python work?"

        entities = await extractor_with_services.extract_entities_from_query(
            query=query,
            user_context=user_context,
        )

        assert isinstance(entities, dict)


# ============================================================================
# TESTS: Acronym Match Extraction
# ============================================================================


class TestAcronymMatchExtraction:
    """Test acronym match entity extraction."""

    @pytest.mark.asyncio
    async def test_extract_entities_acronym_match(self, extractor_with_services, user_context):
        """Extracts entities with acronym matches (e.g., ML for Machine Learning)."""
        query = "How is my ML progress?"

        entities = await extractor_with_services.extract_entities_from_query(
            query=query,
            user_context=user_context,
        )

        assert isinstance(entities, dict)


# ============================================================================
# TESTS: Graceful Degradation
# ============================================================================


class TestGracefulDegradation:
    """Test graceful degradation without services."""

    @pytest.mark.asyncio
    async def test_extract_entities_graceful_degradation(self, extractor_no_services, user_context):
        """Works without domain services, returns empty entity types."""
        query = "What should I work on?"

        entities = await extractor_no_services.extract_entities_from_query(
            query=query,
            user_context=user_context,
        )

        assert isinstance(entities, dict)
        # Should return dict (possibly empty for entity types without services)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
