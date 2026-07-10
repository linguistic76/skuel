"""
Tests for GraphIntelligenceService - Pure Cypher Analytics

Tests all five core graph intelligence methods:
1. Hub detection (degree centrality)
2. Knowledge similarity (Jaccard)
3. Prerequisite chain analysis
4. Learning cluster detection
5. Knowledge importance calculation

Date: October 26, 2025
"""

from unittest.mock import AsyncMock

import pytest

from core.models.enums import Domain
from core.services.infrastructure.graph_intelligence_service import (
    GraphIntelligenceService,
)
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_backend() -> AsyncMock:
    """Mock CrossDomainBackendOperations for testing."""
    return AsyncMock()


@pytest.fixture
def service(mock_backend) -> GraphIntelligenceService:
    """Create GraphIntelligenceService with mock backend."""
    return GraphIntelligenceService(mock_backend)


class TestFindKnowledgeHubs:
    """Test hub detection via degree centrality"""

    @pytest.mark.asyncio
    async def test_find_hubs_basic(self, service, mock_backend):
        """Test finding knowledge hubs with basic parameters"""
        mock_backend.find_knowledge_hubs.return_value = Result.ok(
            [
                {
                    "uid": "ku.math.algebra",
                    "title": "Algebra Fundamentals",
                    "domain": "tech",
                    "total_connections": 15,
                    "incoming_count": 10,
                    "outgoing_count": 5,
                    "centrality_score": 15.0,
                },
                {
                    "uid": "ku.programming.python",
                    "title": "Python Programming",
                    "domain": "tech",
                    "total_connections": 12,
                    "incoming_count": 8,
                    "outgoing_count": 4,
                    "centrality_score": 12.0,
                },
            ]
        )

        result = await service.find_knowledge_hubs(domain=Domain.TECH, min_connections=5, limit=10)

        assert result.is_ok
        assert len(result.value) == 2
        assert result.value[0]["uid"] == "ku.math.algebra"
        assert result.value[0]["connections"] == 15
        assert result.value[0]["centrality_score"] == 15.0

    @pytest.mark.asyncio
    async def test_find_hubs_no_domain_filter(self, service, mock_backend):
        """Test finding hubs without domain filter"""
        mock_backend.find_knowledge_hubs.return_value = Result.ok([])

        result = await service.find_knowledge_hubs(domain=None, min_connections=5)

        assert result.is_ok
        assert len(result.value) == 0

    @pytest.mark.asyncio
    async def test_find_hubs_high_confidence(self, service, mock_backend):
        """Test finding hubs with high confidence threshold"""
        mock_backend.find_knowledge_hubs.return_value = Result.ok(
            [
                {
                    "uid": "ku.high.quality",
                    "title": "High Quality Knowledge",
                    "domain": "tech",
                    "total_connections": 20,
                    "incoming_count": 15,
                    "outgoing_count": 5,
                    "centrality_score": 20.0,
                }
            ]
        )

        result = await service.find_knowledge_hubs(min_confidence=0.9, min_connections=10)

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0]["connections"] == 20

    @pytest.mark.asyncio
    async def test_find_hubs_database_error(self, service, mock_backend):
        """Test error handling when database fails"""
        mock_backend.find_knowledge_hubs.return_value = Result.fail(
            Errors.database(operation="find_knowledge_hubs", message="Database connection failed")
        )

        result = await service.find_knowledge_hubs()

        assert result.is_error


class TestFindSimilarKnowledge:
    """Test similarity detection via Jaccard"""

    @pytest.mark.asyncio
    async def test_find_similar_basic(self, service, mock_backend):
        """Test finding similar knowledge with basic parameters"""
        mock_backend.find_similar_knowledge.return_value = Result.ok(
            [
                {
                    "uid": "ku.programming.javascript",
                    "title": "JavaScript Programming",
                    "domain": "tech",
                    "similarity": 0.67,
                    "shared_count": 12,
                    "total_neighbors": 18,
                },
                {
                    "uid": "ku.programming.ruby",
                    "title": "Ruby Programming",
                    "domain": "tech",
                    "similarity": 0.54,
                    "shared_count": 10,
                    "total_neighbors": 15,
                },
            ]
        )

        result = await service.find_similar_knowledge(
            ku_uid="ku.programming.python", min_similarity=0.5
        )

        assert result.is_ok
        assert len(result.value) == 2
        assert result.value[0]["similarity"] == 0.67
        assert result.value[0]["shared_neighbors"] == 12

    @pytest.mark.asyncio
    async def test_find_similar_high_threshold(self, service, mock_backend):
        """Test finding similar knowledge with high similarity threshold"""
        mock_backend.find_similar_knowledge.return_value = Result.ok(
            [
                {
                    "uid": "ku.very.similar",
                    "title": "Very Similar Knowledge",
                    "domain": "tech",
                    "similarity": 0.85,
                    "shared_count": 20,
                    "total_neighbors": 24,
                }
            ]
        )

        result = await service.find_similar_knowledge(ku_uid="ku.source", min_similarity=0.8)

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0]["similarity"] == 0.85

    @pytest.mark.asyncio
    async def test_find_similar_no_results(self, service, mock_backend):
        """Test finding similar knowledge when no similar units exist"""
        mock_backend.find_similar_knowledge.return_value = Result.ok([])

        result = await service.find_similar_knowledge(
            ku_uid="ku.isolated.topic", min_similarity=0.3
        )

        assert result.is_ok
        assert len(result.value) == 0


class TestAnalyzePrerequisiteDepth:
    """Test prerequisite chain analysis"""

    @pytest.mark.asyncio
    async def test_analyze_depth_basic(self, service, mock_backend):
        """Test analyzing prerequisite depth with basic chain"""
        mock_backend.analyze_prerequisite_depth.return_value = Result.ok(
            [
                {
                    "max_depth": 5,
                    "avg_depth": 3.2,
                    "total_paths": 8,
                    "root_uids": ["ku.math.algebra", "ku.programming.basics"],
                    "complexity_score": 40,
                }
            ]
        )

        result = await service.analyze_prerequisite_depth(ku_uid="ku.advanced.machine_learning")

        assert result.is_ok
        assert result.value["max_depth"] == 5
        assert result.value["avg_depth"] == 3.2
        assert result.value["total_paths"] == 8
        assert len(result.value["root_prerequisites"]) == 2
        assert result.value["complexity_score"] == 40

    @pytest.mark.asyncio
    async def test_analyze_depth_no_prerequisites(self, service, mock_backend):
        """Test analyzing depth when no prerequisites exist"""
        mock_backend.analyze_prerequisite_depth.return_value = Result.ok(
            [
                {
                    "max_depth": None,
                    "avg_depth": None,
                    "total_paths": 0,
                    "root_uids": [],
                    "complexity_score": 0,
                }
            ]
        )

        result = await service.analyze_prerequisite_depth(ku_uid="ku.foundational.concept")

        assert result.is_ok
        assert result.value["max_depth"] == 0
        assert result.value["avg_depth"] == 0.0
        assert result.value["total_paths"] == 0
        assert result.value["root_prerequisites"] == []
        assert result.value["complexity_score"] == 0

    @pytest.mark.asyncio
    async def test_analyze_depth_shallow_chain(self, service, mock_backend):
        """Test analyzing depth with shallow prerequisite chain"""
        mock_backend.analyze_prerequisite_depth.return_value = Result.ok(
            [
                {
                    "max_depth": 1,
                    "avg_depth": 1.0,
                    "total_paths": 2,
                    "root_uids": ["ku.basic.concept"],
                    "complexity_score": 2,
                }
            ]
        )

        result = await service.analyze_prerequisite_depth(ku_uid="ku.simple.topic")

        assert result.is_ok
        assert result.value["max_depth"] == 1
        assert result.value["complexity_score"] == 2


class TestFindLearningClusters:
    """Test cluster detection via triangle density"""

    @pytest.mark.asyncio
    async def test_find_clusters_basic(self, service, mock_backend):
        """Test finding learning clusters with basic parameters"""
        mock_backend.find_learning_clusters.return_value = Result.ok(
            [
                {
                    "uid": "ku.web.html",
                    "title": "HTML Fundamentals",
                    "domain": "tech",
                    "neighbor_count": 8,
                    "triangles": 12,
                    "density": 0.71,
                },
                {
                    "uid": "ku.web.css",
                    "title": "CSS Styling",
                    "domain": "tech",
                    "neighbor_count": 7,
                    "triangles": 10,
                    "density": 0.65,
                },
            ]
        )

        result = await service.find_learning_clusters(domain=Domain.TECH, min_density=0.6)

        assert result.is_ok
        assert len(result.value) == 2
        assert result.value[0]["density"] == 0.71
        assert result.value[0]["triangles"] == 12

    @pytest.mark.asyncio
    async def test_find_clusters_high_density(self, service, mock_backend):
        """Test finding clusters with high density threshold"""
        mock_backend.find_learning_clusters.return_value = Result.ok(
            [
                {
                    "uid": "ku.tight.cluster",
                    "title": "Tightly Connected Module",
                    "domain": "tech",
                    "neighbor_count": 10,
                    "triangles": 20,
                    "density": 0.85,
                }
            ]
        )

        result = await service.find_learning_clusters(min_density=0.8)

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0]["density"] == 0.85

    @pytest.mark.asyncio
    async def test_find_clusters_no_results(self, service, mock_backend):
        """Test finding clusters when none meet density threshold"""
        mock_backend.find_learning_clusters.return_value = Result.ok([])

        result = await service.find_learning_clusters(min_density=0.9)

        assert result.is_ok
        assert len(result.value) == 0


class TestCalculateKnowledgeImportance:
    """Test composite importance calculation"""

    @pytest.mark.asyncio
    async def test_calculate_importance_basic(self, service, mock_backend):
        """Test calculating importance with basic metrics"""
        mock_backend.calculate_knowledge_importance.return_value = Result.ok(
            [
                {
                    "importance_score": 42.5,
                    "degree_centrality": 24.0,
                    "prerequisite_importance": 15.0,
                    "cluster_coefficient": 0.45,
                    "avg_confidence": 0.82,
                }
            ]
        )

        result = await service.calculate_knowledge_importance(ku_uid="ku.programming.algorithms")

        assert result.is_ok
        assert result.value["importance_score"] == 42.5
        assert result.value["degree_centrality"] == 24.0
        assert result.value["prerequisite_importance"] == 15.0
        assert result.value["cluster_coefficient"] == 0.45
        assert result.value["avg_confidence"] == 0.82

    @pytest.mark.asyncio
    async def test_calculate_importance_high_score(self, service, mock_backend):
        """Test calculating importance for highly important knowledge"""
        mock_backend.calculate_knowledge_importance.return_value = Result.ok(
            [
                {
                    "importance_score": 85.0,
                    "degree_centrality": 50.0,
                    "prerequisite_importance": 30.0,
                    "cluster_coefficient": 0.75,
                    "avg_confidence": 0.95,
                }
            ]
        )

        result = await service.calculate_knowledge_importance(ku_uid="ku.foundational.concept")

        assert result.is_ok
        assert result.value["importance_score"] == 85.0
        assert result.value["degree_centrality"] == 50.0

    @pytest.mark.asyncio
    async def test_calculate_importance_low_score(self, service, mock_backend):
        """Test calculating importance for peripheral knowledge"""
        mock_backend.calculate_knowledge_importance.return_value = Result.ok(
            [
                {
                    "importance_score": 5.0,
                    "degree_centrality": 2.0,
                    "prerequisite_importance": 1.0,
                    "cluster_coefficient": 0.1,
                    "avg_confidence": 0.6,
                }
            ]
        )

        result = await service.calculate_knowledge_importance(ku_uid="ku.specialized.topic")

        assert result.is_ok
        assert result.value["importance_score"] == 5.0

    @pytest.mark.asyncio
    async def test_calculate_importance_not_found(self, service, mock_backend):
        """Test calculating importance when knowledge unit doesn't exist"""
        mock_backend.calculate_knowledge_importance.return_value = Result.ok([])

        result = await service.calculate_knowledge_importance(ku_uid="ku.nonexistent")

        assert result.is_error
        assert "Entity" in str(result.error)
        assert "ku.nonexistent" in str(result.error)
