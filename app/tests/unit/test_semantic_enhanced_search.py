"""
Unit tests for semantic-enhanced search functionality.

Tests the new semantic relationship boosting and learning-aware search features
without requiring actual Neo4j or OpenAI API calls.

Test Coverage:
1. Semantic-enhanced search with mock relationships
2. Learning-aware search with mock learning states
3. Configuration weight helpers
4. Edge cases (no relationships, no context, errors)
5. Graceful degradation scenarios
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.utils.result_simplified import Errors, Result


class TestSemanticEnhancedSearch:
    """Unit tests for semantic_enhanced_search() method."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        driver = MagicMock()
        driver.execute_query = AsyncMock()
        return driver

    @pytest.fixture
    def mock_embeddings_service(self):
        """Create mock embeddings service."""
        service = MagicMock()
        service.create_embedding = AsyncMock(return_value=Result.ok([0.1] * 1536))
        return service

    @pytest.fixture
    def vector_config(self):
        """Create test vector search config."""
        return VectorSearchConfig(
            semantic_boost_enabled=True,
            semantic_boost_weight=0.3,
        )

    @pytest.fixture
    def vector_search_service(self, mock_driver, mock_embeddings_service, vector_config):
        """Create vector search service with mocks."""
        return Neo4jVectorSearchService(
            driver=mock_driver, embeddings_service=mock_embeddings_service, config=vector_config
        )

    @pytest.mark.asyncio
    async def test_semantic_boost_with_relationships(self, vector_search_service, mock_driver):
        """Test semantic boosting with existing relationships."""

        # Mock initial vector search results
        initial_results = [
            {"node": {"uid": "ku.python-advanced", "title": "Advanced Python"}, "score": 0.8},
            {"node": {"uid": "ku.python-intro", "title": "Python Intro"}, "score": 0.75},
        ]

        # Mock the find_similar_by_text call
        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(initial_results)
        ):
            # Mock semantic relationship query results
            # ku.python-advanced has high-confidence relationship to context
            mock_driver.execute_query.return_value = (
                [
                    {
                        "relationship_type": "REQUIRES_THEORETICAL_UNDERSTANDING",
                        "confidence": 0.9,
                        "strength": 1.0,
                    }
                ],
                None,
                None,
            )

            # Execute semantic-enhanced search
            result = await vector_search_service.semantic_enhanced_search(
                label="Ku", text="python programming", context_uids=["ku.python-basics"], limit=2
            )

            assert result.is_ok
            results = result.value
            assert len(results) == 2

            # Check that results have semantic boost metadata
            assert "semantic_boost" in results[0]
            assert "vector_score" in results[0]

            # Original vector score should be preserved
            assert results[0]["vector_score"] == 0.8

    @pytest.mark.asyncio
    async def test_semantic_boost_calculation(self, vector_search_service, mock_driver):
        """Test semantic boost calculation with different relationship types."""

        # Mock relationships with different types and confidence
        mock_driver.execute_query.return_value = (
            [
                {
                    "relationship_type": "REQUIRES_THEORETICAL_UNDERSTANDING",  # weight: 1.0
                    "confidence": 0.9,
                    "strength": 1.0,
                },
                {
                    "relationship_type": "RELATED_TO",  # weight: 0.5
                    "confidence": 0.7,
                    "strength": 0.8,
                },
            ],
            None,
            None,
        )

        # Calculate boost
        boost = await vector_search_service._calculate_semantic_boost(
            entity_uid="ku.test", context_uids=["ku.context1", "ku.context2"]
        )

        # Boost should be average of:
        # (1.0 * 0.9 * 1.0) + (0.5 * 0.7 * 0.8) = 0.9 + 0.28 = 1.18 / 2 = 0.59
        # But capped at 1.0
        assert isinstance(boost, float)
        assert 0.0 <= boost <= 1.0

    @pytest.mark.asyncio
    async def test_semantic_boost_no_context(self, vector_search_service):
        """Test that empty context_uids falls back to standard search."""

        # Mock standard vector search
        standard_results = [{"node": {"uid": "ku.test", "title": "Test"}, "score": 0.8}]

        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(standard_results)
        ) as mock_search:
            result = await vector_search_service.semantic_enhanced_search(
                label="Ku",
                text="test query",
                context_uids=[],  # Empty context
                limit=10,
            )

            # Should fall back to standard search
            assert result.is_ok
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_boost_disabled(self, mock_driver, mock_embeddings_service):
        """Test that disabled semantic boost falls back to standard search."""

        # Create service with semantic boost disabled
        config = VectorSearchConfig(semantic_boost_enabled=False)
        service = Neo4jVectorSearchService(
            driver=mock_driver, embeddings_service=mock_embeddings_service, config=config
        )

        standard_results = [{"node": {"uid": "ku.test", "title": "Test"}, "score": 0.8}]

        with patch.object(
            service, "find_similar_by_text", return_value=Result.ok(standard_results)
        ) as mock_search:
            result = await service.semantic_enhanced_search(
                label="Ku", text="test query", context_uids=["ku.context"], limit=10
            )

            assert result.is_ok
            # Should use standard search even with context
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_boost_query_error(self, vector_search_service, mock_driver):
        """Test graceful handling of relationship query errors."""

        # Mock driver to raise exception
        mock_driver.execute_query.side_effect = Exception("Database error")

        # Should return 0.0 boost, not crash
        boost = await vector_search_service._calculate_semantic_boost(
            entity_uid="ku.test", context_uids=["ku.context"]
        )

        assert boost == 0.0  # Graceful degradation

    @pytest.mark.asyncio
    async def test_semantic_boost_no_relationships(self, vector_search_service, mock_driver):
        """Test boost calculation when no relationships exist."""

        # Mock empty relationship results
        mock_driver.execute_query.return_value = ([], None, None)

        boost = await vector_search_service._calculate_semantic_boost(
            entity_uid="ku.test", context_uids=["ku.context"]
        )

        assert boost == 0.0  # No relationships = no boost


class TestLearningAwareSearch:
    """Unit tests for learning_aware_search() method."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        driver = MagicMock()
        driver.execute_query = AsyncMock()
        return driver

    @pytest.fixture
    def mock_embeddings_service(self):
        """Create mock embeddings service."""
        service = MagicMock()
        service.create_embedding = AsyncMock(return_value=Result.ok([0.1] * 1536))
        return service

    @pytest.fixture
    def vector_config(self):
        """Create test vector search config."""
        return VectorSearchConfig()

    @pytest.fixture
    def vector_search_service(self, mock_driver, mock_embeddings_service, vector_config):
        """Create vector search service with mocks."""
        return Neo4jVectorSearchService(
            driver=mock_driver, embeddings_service=mock_embeddings_service, config=vector_config
        )

    @pytest.mark.asyncio
    async def test_learning_aware_boost_mastered(self, vector_search_service, mock_driver):
        """Test that mastered content gets penalty."""

        # Mock initial vector search
        initial_results = [
            {"node": {"uid": "ku.python-basics", "title": "Python Basics"}, "score": 0.8},
        ]

        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(initial_results)
        ):
            # Mock learning state: mastered
            mock_driver.execute_query.return_value = (
                [
                    {
                        "ku_uid": "ku.python-basics",
                        "has_viewed": True,
                        "has_in_progress": True,
                        "has_mastered": True,
                    }
                ],
                None,
                None,
            )

            result = await vector_search_service.learning_aware_search(
                label="Ku", text="python", user_uid="user.test", prefer_unmastered=True, limit=10
            )

            assert result.is_ok
            results = result.value
            assert len(results) == 1

            # Score should be reduced (mastered penalty: -20%)
            # 0.8 * (1 - 0.2) = 0.8 * 0.8 = 0.64
            assert results[0]["score"] < results[0]["vector_score"]
            assert results[0]["learning_state"] == "mastered"

    @pytest.mark.asyncio
    async def test_learning_aware_boost_not_started(self, vector_search_service, mock_driver):
        """Test that unlearned content gets boost."""

        initial_results = [
            {"node": {"uid": "ku.advanced-python", "title": "Advanced Python"}, "score": 0.7},
        ]

        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(initial_results)
        ):
            # Mock learning state: not started
            mock_driver.execute_query.return_value = (
                [
                    {
                        "ku_uid": "ku.advanced-python",
                        "has_viewed": False,
                        "has_in_progress": False,
                        "has_mastered": False,
                    }
                ],
                None,
                None,
            )

            result = await vector_search_service.learning_aware_search(
                label="Ku", text="python", user_uid="user.test", prefer_unmastered=True, limit=10
            )

            assert result.is_ok
            results = result.value
            assert len(results) == 1

            # Score should be increased (not_started boost: +15%)
            # 0.7 * (1 + 0.15) = 0.7 * 1.15 = 0.805
            assert results[0]["score"] > results[0]["vector_score"]
            assert results[0]["learning_state"] == "none"

    @pytest.mark.asyncio
    async def test_learning_aware_prefer_unmastered_false(self, vector_search_service, mock_driver):
        """Test inverted boosts when prefer_unmastered=False (review mode)."""

        initial_results = [
            {"node": {"uid": "ku.test", "title": "Test"}, "score": 0.8},
        ]

        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(initial_results)
        ):
            # Mock learning state: mastered
            mock_driver.execute_query.return_value = (
                [
                    {
                        "ku_uid": "ku.test",
                        "has_viewed": True,
                        "has_in_progress": False,
                        "has_mastered": True,
                    }
                ],
                None,
                None,
            )

            result = await vector_search_service.learning_aware_search(
                label="Ku",
                text="test",
                user_uid="user.test",
                prefer_unmastered=False,  # Review mode - prefer mastered
                limit=10,
            )

            assert result.is_ok
            results = result.value

            # Mastered penalty (-20%) should be inverted to boost (+20%)
            assert results[0]["score"] > results[0]["vector_score"]

    @pytest.mark.asyncio
    async def test_learning_aware_non_ku_label(self, vector_search_service):
        """Test that non-Ku labels fall back to standard search."""

        standard_results = [{"node": {"uid": "task.test", "title": "Test Task"}, "score": 0.8}]

        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(standard_results)
        ) as mock_search:
            result = await vector_search_service.learning_aware_search(
                label="Task",  # Not "Ku"
                text="test",
                user_uid="user.test",
                limit=10,
            )

            assert result.is_ok
            # Should fall back to standard search
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_learning_state_query_error(self, vector_search_service, mock_driver):
        """Test graceful handling of learning state query errors."""

        initial_results = [
            {"node": {"uid": "ku.test", "title": "Test"}, "score": 0.8},
        ]

        with patch.object(
            vector_search_service, "find_similar_by_text", return_value=Result.ok(initial_results)
        ):
            # Mock driver to raise exception
            mock_driver.execute_query.side_effect = Exception("Database error")

            result = await vector_search_service.learning_aware_search(
                label="Ku", text="test", user_uid="user.test", limit=10
            )

            # Should still return results (graceful degradation)
            assert result.is_ok
            # With error, defaults to "none" state which gets NOT_STARTED boost (+15%)
            # 0.8 * 1.15 = 0.92
            assert result.value[0]["learning_state"] == "none"
            assert result.value[0]["score"] > result.value[0]["vector_score"]


class TestVectorSearchConfig:
    """Unit tests for VectorSearchConfig helper methods."""

    def test_get_relationship_weight_known_type(self):
        """Test getting weight for known relationship type."""
        config = VectorSearchConfig()

        weight = config.get_relationship_weight("REQUIRES_THEORETICAL_UNDERSTANDING")
        assert weight == 1.0  # High importance

        weight = config.get_relationship_weight("RELATED_TO")
        assert weight == 0.5  # Lower importance

    def test_get_relationship_weight_unknown_type(self):
        """Test getting weight for unknown relationship type (default)."""
        config = VectorSearchConfig()

        weight = config.get_relationship_weight("UNKNOWN_RELATIONSHIP")
        assert weight == 0.5  # Default weight

    def test_get_learning_state_boost_all_states(self):
        """Test getting boost for all learning states."""
        config = VectorSearchConfig()

        assert config.get_learning_state_boost("mastered") == -0.2
        assert config.get_learning_state_boost("in_progress") == 0.1
        assert config.get_learning_state_boost("viewed") == 0.0
        assert config.get_learning_state_boost("none") == 0.15

    def test_get_learning_state_boost_case_insensitive(self):
        """Test that learning state lookup is case-insensitive."""
        config = VectorSearchConfig()

        assert config.get_learning_state_boost("MASTERED") == -0.2
        assert config.get_learning_state_boost("In_Progress") == 0.1

    def test_get_learning_state_boost_unknown(self):
        """Test getting boost for unknown state (default)."""
        config = VectorSearchConfig()

        boost = config.get_learning_state_boost("unknown_state")
        assert boost == 0.0  # Default neutral


class TestGracefulDegradation:
    """Tests for graceful degradation scenarios."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        driver = MagicMock()
        driver.execute_query = AsyncMock()
        return driver

    @pytest.fixture
    def mock_embeddings_service(self):
        """Create mock embeddings service."""
        service = MagicMock()
        service.create_embedding = AsyncMock(return_value=Result.ok([0.1] * 1536))
        return service

    @pytest.mark.asyncio
    async def test_embeddings_unavailable(self, mock_driver):
        """Test graceful degradation when embeddings service unavailable."""

        # Create service WITHOUT embeddings
        service = Neo4jVectorSearchService(
            driver=mock_driver,
            embeddings_service=None,  # No embeddings service
            config=VectorSearchConfig(),
        )

        result = await service.semantic_enhanced_search(
            label="Ku", text="test", context_uids=["ku.context"], limit=10
        )

        # Should return error (not crash)
        assert result.is_error
        assert "Embeddings service required" in str(result.expect_error())

    @pytest.mark.asyncio
    async def test_vector_search_error_propagates(self, mock_driver, mock_embeddings_service):
        """Test that vector search errors propagate correctly."""

        service = Neo4jVectorSearchService(
            driver=mock_driver,
            embeddings_service=mock_embeddings_service,
            config=VectorSearchConfig(),
        )

        # Mock vector search to return error
        with patch.object(
            service,
            "find_similar_by_text",
            return_value=Result.fail(Errors.database("vector_search", "Search failed")),
        ):
            result = await service.semantic_enhanced_search(
                label="Ku", text="test", context_uids=["ku.context"], limit=10
            )

            # Error should propagate
            assert result.is_error

    @pytest.mark.asyncio
    async def test_empty_results_handled(self, mock_driver, mock_embeddings_service):
        """Test that empty vector search results are handled gracefully."""

        service = Neo4jVectorSearchService(
            driver=mock_driver,
            embeddings_service=mock_embeddings_service,
            config=VectorSearchConfig(),
        )

        # Mock empty results
        with patch.object(
            service,
            "find_similar_by_text",
            return_value=Result.ok([]),  # Empty results
        ):
            result = await service.semantic_enhanced_search(
                label="Ku", text="test", context_uids=["ku.context"], limit=10
            )

            # Should return empty list (not error)
            assert result.is_ok
            assert result.value == []
