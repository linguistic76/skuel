"""
Test KU Graph Service
======================

Tests for the ArticleGraphService focused sub-service.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain
from core.services.article.article_graph_service import ArticleGraphService
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
    """Test ArticleGraphService initialization."""

    def test_initialization_with_all_dependencies(self):
        """Test successful initialization with all dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        graph_intel = MagicMock()

        service = ArticleGraphService(repo=repo, neo4j_adapter=neo4j, graph_intel=graph_intel)

        assert service.repo == repo
        assert service.neo4j == neo4j
        assert service.graph_intel == graph_intel

    def test_initialization_without_optional_dependencies(self):
        """Test initialization works without optional graph_intel."""
        repo = MagicMock()
        neo4j = MagicMock()

        service = ArticleGraphService(repo=repo, neo4j_adapter=neo4j)

        assert service.repo == repo
        assert service.neo4j == neo4j
        assert service.graph_intel is None

    def test_initialization_fails_without_repo(self):
        """Test that initialization fails without required repo."""
        with pytest.raises(ValueError, match="KU repository is required"):
            ArticleGraphService(repo=None, neo4j_adapter=MagicMock())

    def test_initialization_fails_without_neo4j(self):
        """Test that initialization fails without required Neo4j adapter."""
        with pytest.raises(ValueError, match="Neo4j adapter is required"):
            ArticleGraphService(repo=MagicMock(), neo4j_adapter=None)


class TestGraphTraversal:
    """Test graph traversal operations."""

    @pytest.fixture
    def service(self) -> ArticleGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return ArticleGraphService(repo=repo, neo4j_adapter=neo4j)

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

        # Mock Neo4j query returns prerequisites - wrapped in Result.ok()
        service.neo4j.execute_query = AsyncMock(
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

        # Mock Neo4j query returns next steps (CypherGenerator uses "target" key)
        service.neo4j.execute_query = AsyncMock(
            return_value=[{"target": {"uid": "ku.next.1"}}, {"target": {"uid": "ku.next.2"}}]
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

        result = await service.get_article_with_context("ku.test.1", depth=2)

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
    def service(self) -> ArticleGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return ArticleGraphService(repo=repo, neo4j_adapter=neo4j)

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

        # Mock Neo4j execute_query
        service.neo4j.execute_query = AsyncMock(return_value=[])

        result = await service.link_prerequisite("ku.test.1", "ku.prereq.1", is_mandatory=True)

        assert result.is_ok
        assert result.value is True
        service.neo4j.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_link_parent_child_success(self, service):
        """Test successful parent-child linking."""
        # Mock both units exist
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto()))

        # Mock Neo4j execute_query
        service.neo4j.execute_query = AsyncMock(return_value=[])

        result = await service.link_parent_child("ku.parent.1", "ku.child.1")

        assert result.is_ok
        assert result.value is True
        service.neo4j.execute_query.assert_called_once()


class TestAnalysisRecommendations:
    """Test analysis and recommendation operations."""

    @pytest.fixture
    def service(self) -> ArticleGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        graph_intel = MagicMock()
        return ArticleGraphService(repo=repo, neo4j_adapter=neo4j, graph_intel=graph_intel)

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

    @pytest.mark.asyncio
    async def test_get_prerequisite_chain_with_user(self, service):
        """Test prerequisite chain with user context."""
        # Mock find_prerequisites
        prereq_dto = make_ku_dto("ku.prereq.1", "Prereq")
        service.find_prerequisites = AsyncMock(return_value=Result.ok([prereq_dto]))

        # Mock Neo4j user mastery query
        service.neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "ku_uid": "ku.prereq.1",
                    "score": 0.85,
                    "confidence": 0.9,
                    "last_practiced": "2025-10-12T00:00:00Z",
                }
            ]
        )

        result = await service.get_prerequisite_chain("ku.test.1", user_uid="user.123")

        assert result.is_ok
        chain = result.value
        assert chain["user_uid"] == "user.123"
        assert "user_mastery" in chain
        assert "ku.prereq.1" in chain["user_mastery"]

    @pytest.mark.asyncio
    async def test_analyze_knowledge_gaps_success(self, service):
        """Test knowledge gap analysis."""
        # Mock get_prerequisite_chain
        service.get_prerequisite_chain = AsyncMock(
            return_value=Result.ok(
                {"target_uid": "ku.test.1", "total_count": 3, "prerequisites": []}
            )
        )

        result = await service.analyze_knowledge_gaps("ku.test.1", "user.123")

        assert result.is_ok
        analysis = result.value
        assert "target_uid" in analysis
        assert "user_uid" in analysis
        assert analysis["user_uid"] == "user.123"

    @pytest.mark.asyncio
    async def test_get_learning_recommendations_success(self, service):
        """Test learning recommendations generation."""
        # Mock Neo4j recommendations query
        service.neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "uid": "ku.ready.1",
                    "title": "Ready to Learn",
                    "summary": "A unit ready to be learned",
                    "domain": "tech",
                    "readiness": 0.9,
                    "total_prereqs": 3,
                    "satisfied_prereqs": 3,
                    "enables_count": 5,
                },
                {
                    "uid": "ku.ready.2",
                    "title": "Another Ready Unit",
                    "summary": "Another unit ready to be learned",
                    "domain": "tech",
                    "readiness": 0.75,
                    "total_prereqs": 4,
                    "satisfied_prereqs": 3,
                    "enables_count": 2,
                },
            ]
        )

        result = await service.get_learning_recommendations("user.123", domain="tech")

        assert result.is_ok
        recommendations = result.value
        assert isinstance(recommendations, list)
        assert len(recommendations) == 2
        assert recommendations[0]["uid"] == "ku.ready.1"
        assert recommendations[0]["readiness_score"] == 0.9
        assert recommendations[0]["priority"] == "high"


class TestTimeAwareLearningPath:
    """Test metadata-aware learning path generation (Quick Win #2)."""

    @pytest.fixture
    def service(self) -> ArticleGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return ArticleGraphService(repo=repo, neo4j_adapter=neo4j)

    @pytest.mark.asyncio
    async def test_time_aware_path_target_not_found(self, service):
        """Test that missing target returns error."""
        service.repo.get = AsyncMock(return_value=Result.ok(None))

        result = await service.find_time_aware_learning_path(
            target_uid="ku.nonexistent", user_time_budget=120
        )

        assert result.is_error
        assert "not found" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_time_aware_path_invalid_complexity(self, service):
        """Test that invalid complexity level returns validation error."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1")))

        result = await service.find_time_aware_learning_path(
            target_uid="ku.test.1", user_time_budget=120, max_complexity="invalid"
        )

        assert result.is_error
        assert "invalid complexity" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_time_aware_path_no_paths_found(self, service):
        """Test that no paths matching constraints returns empty list (not error)."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1")))
        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(return_value=Result.ok([]))

        result = await service.find_time_aware_learning_path(
            target_uid="ku.test.1", user_time_budget=30, max_complexity="basic"
        )

        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_time_aware_path_success(self, service):
        """Test successful path generation with metadata."""
        # Mock target exists
        service.repo.get = AsyncMock(
            side_effect=[
                Result.ok(make_ku_dto("ku.target", "Target")),  # Target validation
                Result.ok(make_ku_dto("ku.prereq1", "Prereq 1")),  # Path node 1
                Result.ok(make_ku_dto("ku.prereq2", "Prereq 2")),  # Path node 2
                Result.ok(make_ku_dto("ku.target", "Target")),  # Path node 3
            ]
        )

        # Mock Neo4j path result
        mock_path = MagicMock()
        mock_path.nodes = [
            {"uid": "ku.prereq1"},
            {"uid": "ku.prereq2"},
            {"uid": "ku.target"},
        ]

        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "path": mock_path,
                        "total_time": 45.0,
                        "avg_complexity_score": 1.8,
                        "path_length": 3,
                    }
                ]
            )
        )

        result = await service.find_time_aware_learning_path(
            target_uid="ku.target", user_time_budget=120, max_complexity="intermediate"
        )

        assert result.is_ok
        paths = result.value
        assert len(paths) == 1

        path = paths[0]
        assert path["path"] == ["ku.prereq1", "ku.prereq2", "ku.target"]
        assert path["total_time"] == 45.0
        assert path["avg_complexity"] == 1.8
        assert path["path_length"] == 3
        assert path["complexity_label"] == "intermediate"
        assert len(path["units"]) == 3

    @pytest.mark.asyncio
    async def test_time_aware_path_multiple_alternatives(self, service):
        """Test that multiple alternative paths are returned sorted by time."""
        service.repo.get = AsyncMock(
            side_effect=[
                Result.ok(make_ku_dto("ku.target")),  # Target validation
                # Path 1 nodes
                Result.ok(make_ku_dto("ku.p1")),
                Result.ok(make_ku_dto("ku.target")),
                # Path 2 nodes
                Result.ok(make_ku_dto("ku.p2a")),
                Result.ok(make_ku_dto("ku.p2b")),
                Result.ok(make_ku_dto("ku.target")),
            ]
        )

        # Mock two paths: one short (30m), one longer (60m)
        mock_path1 = MagicMock()
        mock_path1.nodes = [{"uid": "ku.p1"}, {"uid": "ku.target"}]

        mock_path2 = MagicMock()
        mock_path2.nodes = [{"uid": "ku.p2a"}, {"uid": "ku.p2b"}, {"uid": "ku.target"}]

        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "path": mock_path1,
                        "total_time": 30.0,
                        "avg_complexity_score": 2.0,
                        "path_length": 2,
                    },
                    {
                        "path": mock_path2,
                        "total_time": 60.0,
                        "avg_complexity_score": 1.5,
                        "path_length": 3,
                    },
                ]
            )
        )

        result = await service.find_time_aware_learning_path(
            target_uid="ku.target", user_time_budget=90, limit=2
        )

        assert result.is_ok
        paths = result.value
        assert len(paths) == 2

        # Paths should be sorted by time (shortest first)
        assert paths[0]["total_time"] == 30.0
        assert paths[1]["total_time"] == 60.0

    @pytest.mark.asyncio
    async def test_complexity_score_to_label_conversion(self, service):
        """Test that numeric complexity scores convert correctly to labels."""
        assert service._complexity_score_to_label(1.0) == "basic"
        assert service._complexity_score_to_label(1.4) == "basic"
        assert service._complexity_score_to_label(1.6) == "intermediate"
        assert service._complexity_score_to_label(2.4) == "intermediate"
        assert service._complexity_score_to_label(2.6) == "advanced"
        assert service._complexity_score_to_label(3.0) == "advanced"


class TestHubScoreCaching:
    """Test hub score caching and foundational knowledge identification (Quick Win #3)."""

    @pytest.fixture
    def service(self) -> ArticleGraphService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return ArticleGraphService(repo=repo, neo4j_adapter=neo4j)

    @pytest.mark.asyncio
    async def test_update_hub_scores_success(self, service):
        """Test successful hub score computation."""
        # Mock Neo4j returns update count
        service.neo4j.execute_query = AsyncMock(return_value=[{"updated_count": 42}])

        result = await service.update_hub_scores()

        assert result.is_ok
        # Verify query was called
        service.neo4j.execute_query.assert_called_once()
        # Verify query computes degree centrality
        call_args = service.neo4j.execute_query.call_args
        query = call_args[0][0]
        assert "count(r)" in query
        assert "SET ku.hub_score" in query

    @pytest.mark.asyncio
    async def test_update_hub_scores_no_results(self, service):
        """Test hub score update with no results (empty graph)."""
        service.neo4j.execute_query = AsyncMock(return_value=[])

        result = await service.update_hub_scores()

        # Should still succeed (empty graph is valid)
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_update_hub_scores_database_error(self, service):
        """Test hub score update handles database errors."""
        service.neo4j.execute_query = AsyncMock(side_effect=Exception("Database connection failed"))

        result = await service.update_hub_scores()

        assert result.is_error
        # Check error category (not message text which varies)
        assert result.error.code.startswith("DB_")

    @pytest.mark.asyncio
    async def test_get_foundational_knowledge_success(self, service):
        """Test successful foundational knowledge retrieval."""
        # Mock repo.get for retrieved KUs
        service.repo.get = AsyncMock(
            side_effect=[
                Result.ok(make_ku_dto("ku.foundational1", "Foundation 1")),
                Result.ok(make_ku_dto("ku.foundational2", "Foundation 2")),
            ]
        )

        # Mock Neo4j returns high-hub KUs - wrapped in Result.ok()
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {"ku": {"uid": "ku.foundational1", "hub_score": 15}},
                    {"ku": {"uid": "ku.foundational2", "hub_score": 12}},
                ]
            )
        )

        result = await service.get_foundational_knowledge()

        assert result.is_ok
        foundational = result.value
        assert len(foundational) == 2
        assert foundational[0].uid == "ku.foundational1"
        assert foundational[1].uid == "ku.foundational2"

    @pytest.mark.asyncio
    async def test_get_foundational_knowledge_with_domain_filter(self, service):
        """Test foundational knowledge with domain filtering."""
        service.repo.get = AsyncMock(
            return_value=Result.ok(make_ku_dto("ku.tech_foundation", "Tech Foundation"))
        )
        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok([{"ku": {"uid": "ku.tech_foundation", "hub_score": 20}}])
        )

        result = await service.get_foundational_knowledge(domain="tech")

        assert result.is_ok
        # Verify domain filter in query
        call_args = service.neo4j.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "ku.domain" in query
        assert params.get("domain") == "tech"

    @pytest.mark.asyncio
    async def test_get_foundational_knowledge_custom_threshold(self, service):
        """Test foundational knowledge with custom hub score threshold."""
        service.repo.get = AsyncMock(
            return_value=Result.ok(make_ku_dto("ku.very_foundational", "Very Foundational"))
        )
        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok([{"ku": {"uid": "ku.very_foundational", "hub_score": 25}}])
        )

        result = await service.get_foundational_knowledge(min_hub_score=20)

        assert result.is_ok
        # Verify threshold in query
        call_args = service.neo4j.execute_query.call_args
        query = call_args[0][0]
        assert "ku.hub_score >= 20" in query

    @pytest.mark.asyncio
    async def test_get_foundational_knowledge_empty_results(self, service):
        """Test foundational knowledge with no high-hub KUs."""
        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(return_value=Result.ok([]))

        result = await service.get_foundational_knowledge(min_hub_score=50)

        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_get_foundational_knowledge_database_error(self, service):
        """Test foundational knowledge handles database errors."""
        service.neo4j.execute_query = AsyncMock(side_effect=Exception("Query execution failed"))

        result = await service.get_foundational_knowledge()

        assert result.is_error
        # Check error category (not message text which varies)
        assert result.error.code.startswith("DB_")


class TestFacadeDelegation:
    """Test that ArticleService facade correctly delegates to graph service."""

    @pytest.mark.asyncio
    async def test_facade_delegates_graph_methods(self):
        """Test that all graph methods are delegated."""
        from core.services.article_service import ArticleService

        # Create facade with mocked dependencies
        repo = MagicMock()
        content_repo = MagicMock()
        neo4j = MagicMock()
        query_builder = MagicMock()  # Required for ArticleSearchService
        graph_intel = MagicMock()

        service = ArticleService(
            repo=repo,
            content_repo=content_repo,
            neo4j_adapter=neo4j,
            query_builder=query_builder,
            graph_intelligence_service=graph_intel,
        )

        # Verify graph sub-service exists
        assert hasattr(service, "graph")
        assert service.graph is not None

        # Verify all graph methods exist on facade
        assert callable(service.find_prerequisites)
        assert callable(service.find_next_steps)
        assert callable(service.get_article_with_context)
        assert callable(service.link_prerequisite)
        assert callable(service.link_parent_child)
        assert callable(service.get_prerequisite_chain)
        assert callable(service.analyze_knowledge_gaps)
        assert callable(service.get_learning_recommendations)
        assert callable(service.find_time_aware_learning_path)
        assert callable(service.update_hub_scores)
        assert callable(service.get_foundational_knowledge)
        # Verify new application discovery methods
        assert callable(service.find_events_applying_knowledge)
        assert callable(service.find_habits_reinforcing_knowledge)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
