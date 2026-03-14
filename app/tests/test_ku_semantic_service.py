"""
Test KU Semantic Service
=========================

Tests for the LessonSemanticService focused sub-service.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
    SemanticTriple,
)
from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain
from core.services.lesson.lesson_semantic_service import LessonSemanticService
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


class TestKuSemanticServiceInitialization:
    """Test LessonSemanticService initialization."""

    def test_initialization_with_all_dependencies(self):
        """Test successful initialization with all dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        intelligence = MagicMock()

        service = LessonSemanticService(repo=repo, neo4j_adapter=neo4j, intelligence=intelligence)

        assert service.repo == repo
        assert service.neo4j == neo4j
        assert service.intelligence == intelligence

    def test_initialization_without_optional_intelligence(self):
        """Test initialization works without optional intelligence service."""
        repo = MagicMock()
        neo4j = MagicMock()

        service = LessonSemanticService(repo=repo, neo4j_adapter=neo4j)

        assert service.repo == repo
        assert service.neo4j == neo4j
        assert service.intelligence is None

    def test_initialization_fails_without_repo(self):
        """Test that initialization fails without required repo."""
        with pytest.raises(ValueError, match="KU repository is required"):
            LessonSemanticService(repo=None, neo4j_adapter=MagicMock())

    def test_initialization_fails_without_neo4j(self):
        """Test that initialization fails without required Neo4j adapter."""
        with pytest.raises(ValueError, match="Neo4j adapter is required"):
            LessonSemanticService(repo=MagicMock(), neo4j_adapter=None)


class TestCreateWithSemanticRelationships:
    """Test creating knowledge units with semantic relationships."""

    @pytest.fixture
    def service(self) -> LessonSemanticService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return LessonSemanticService(repo=repo, neo4j_adapter=neo4j)

    @pytest.mark.asyncio
    async def test_create_with_relationships_success(self, service):
        """Test successful creation with semantic relationships."""
        # Mock repo.create to return new KU
        service.repo.create = AsyncMock(return_value=Result.ok(make_ku_dto("ku.new.1", "New Unit")))

        # Mock repo.get to return refreshed KU
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.new.1", "New Unit")))

        # Mock Neo4j execute_query
        service.neo4j.execute_query = AsyncMock(return_value=[])

        # Create relationships
        metadata = RelationshipMetadata(confidence=0.9)
        relationships = [
            SemanticTriple(
                subject="ku.placeholder",  # Will be replaced with new UID
                predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
                object="ku.prereq.1",
                metadata=metadata,
            )
        ]

        ku_data = {"title": "New Unit", "content": "Test content", "domain": "tech"}

        result = await service.create_with_semantic_relationships(
            ku_data=ku_data, relationships=relationships
        )

        assert result.is_ok
        assert result.value.uid == "ku.new.1"
        service.neo4j.execute_query.assert_called()

    @pytest.mark.asyncio
    async def test_create_fails_when_ku_creation_fails(self, service):
        """Test that creation fails gracefully when KU creation fails."""
        # Mock repo.create to fail
        service.repo.create = AsyncMock(return_value=Result.fail(MagicMock()))

        ku_data = {"title": "Test", "content": "Content", "domain": "tech"}
        relationships = []

        result = await service.create_with_semantic_relationships(
            ku_data=ku_data, relationships=relationships
        )

        assert not result.is_ok


class TestSemanticNeighborhood:
    """Test semantic neighborhood operations."""

    @pytest.fixture
    def service(self) -> LessonSemanticService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return LessonSemanticService(repo=repo, neo4j_adapter=neo4j)

    @pytest.mark.asyncio
    async def test_get_semantic_neighborhood_unit_not_found(self, service):
        """Test get_semantic_neighborhood when unit doesn't exist."""
        service.repo.get = AsyncMock(return_value=Result.fail(MagicMock()))

        result = await service.get_semantic_neighborhood("ku.nonexistent")

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_get_semantic_neighborhood_success(self, service):
        """Test successful semantic neighborhood retrieval."""
        # Mock source unit
        service.repo.get = AsyncMock(
            side_effect=lambda uid: Result.ok(make_ku_dto(uid, f"Unit {uid}"))
        )

        # Mock Neo4j query returns neighbors - wrapped in Result.ok()
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "neighbor": {"uid": "ku.neighbor.1", "title": "Neighbor 1"},
                        "relationship": {
                            "type": "REQUIRES_THEORETICAL_UNDERSTANDING",
                            "confidence": 0.9,
                            "strength": 0.8,
                        },
                    },
                    {
                        "neighbor": {"uid": "ku.neighbor.2", "title": "Neighbor 2"},
                        "relationship": {
                            "type": "BUILDS_MENTAL_MODEL",
                            "confidence": 0.85,
                            "strength": 0.9,
                        },
                    },
                ]
            )
        )

        # Specify semantic types to avoid None issue
        semantic_types = [
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.BUILDS_MENTAL_MODEL,
        ]

        result = await service.get_semantic_neighborhood(
            "ku.test.1", depth=2, semantic_types=semantic_types, min_confidence=0.7
        )

        assert result.is_ok
        neighborhood = result.value
        assert neighborhood["central_uid"] == "ku.test.1"
        assert neighborhood["depth"] == 2
        assert neighborhood["total_neighbors"] == 2
        assert neighborhood["total_relationships"] == 2

    @pytest.mark.asyncio
    async def test_get_semantic_neighborhood_with_type_filter(self, service):
        """Test neighborhood retrieval with semantic type filtering."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Wrap in Result.ok() - service expects Result[list]
        service.neo4j.execute_query = AsyncMock(return_value=Result.ok([]))

        semantic_types = [
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.BUILDS_MENTAL_MODEL,
        ]

        result = await service.get_semantic_neighborhood(
            "ku.test.1", depth=3, semantic_types=semantic_types
        )

        assert result.is_ok
        assert result.value["semantic_types_used"] == [st.value for st in semantic_types]


class TestRelationshipManagement:
    """Test semantic relationship management operations."""

    @pytest.fixture
    def service(self) -> LessonSemanticService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return LessonSemanticService(repo=repo, neo4j_adapter=neo4j)

    @pytest.mark.asyncio
    async def test_add_semantic_relationship_success(self, service):
        """Test successful semantic relationship addition."""
        # Mock both units exist
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto()))

        # Mock Neo4j execute_query
        service.neo4j.execute_query = AsyncMock(return_value=[])

        result = await service.add_semantic_relationship(
            subject_uid="ku.test.1",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            object_uid="ku.prereq.1",
            confidence=0.9,
            strength=0.8,
            notes="Test relationship",
        )

        assert result.is_ok
        assert result.value is True
        service.neo4j.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_semantic_relationship_subject_not_found(self, service):
        """Test add relationship fails when subject doesn't exist."""
        service.repo.get = AsyncMock(return_value=Result.fail(MagicMock()))

        result = await service.add_semantic_relationship(
            subject_uid="ku.nonexistent",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            object_uid="ku.prereq.1",
        )

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_remove_semantic_relationship_success(self, service):
        """Test successful semantic relationship removal."""
        # Mock Neo4j delete returns count
        service.neo4j.execute_query = AsyncMock(return_value=[{"deleted": 1}])

        result = await service.remove_semantic_relationship(
            subject_uid="ku.test.1",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            object_uid="ku.prereq.1",
        )

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_remove_semantic_relationship_not_found(self, service):
        """Test remove relationship fails when relationship doesn't exist."""
        # Mock Neo4j delete returns 0 deleted
        service.neo4j.execute_query = AsyncMock(return_value=[{"deleted": 0}])

        result = await service.remove_semantic_relationship(
            subject_uid="ku.test.1",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            object_uid="ku.prereq.1",
        )

        assert not result.is_ok

    @pytest.mark.asyncio
    async def test_get_relationships_by_type_outgoing(self, service):
        """Test getting outgoing relationships by type."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Fix: execute_query returns Result.ok([...]), not bare list
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "target": {"uid": "ku.target.1", "title": "Target 1"},
                        "r": {"confidence": 0.9, "strength": 0.8, "notes": "Test"},
                        "subject_uid": "ku.test.1",
                        "object_uid": "ku.target.1",
                    }
                ]
            )
        )

        result = await service.get_relationships_by_type(
            uid="ku.test.1",
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            direction="outgoing",
        )

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0]["object_uid"] == "ku.target.1"

    @pytest.mark.asyncio
    async def test_get_relationships_by_type_incoming(self, service):
        """Test getting incoming relationships by type."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Fix: execute_query returns Result.ok([...]), not bare list
        service.neo4j.execute_query = AsyncMock(return_value=Result.ok([]))

        result = await service.get_relationships_by_type(
            uid="ku.test.1",
            predicate=SemanticRelationshipType.PROVIDES_FOUNDATION_FOR,
            direction="incoming",
        )

        assert result.is_ok
        assert len(result.value) == 0


class TestRelationshipDiscovery:
    """Test relationship discovery and inference operations."""

    @pytest.fixture
    def service(self) -> LessonSemanticService:
        """Create service with mocked dependencies."""
        repo = MagicMock()
        neo4j = MagicMock()
        return LessonSemanticService(repo=repo, neo4j_adapter=neo4j)

    @pytest.mark.asyncio
    async def test_discover_semantic_bridges_success(self, service):
        """Test successful cross-domain bridge discovery."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Fix: execute_query returns Result.ok([...]), not bare list
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "target": {
                            "uid": "ku.bridge.1",
                            "title": "Bridge Target",
                            "domain": "business",
                        },
                        "bridge_type": "SHARES_PRINCIPLE_WITH",
                        "shared_concept": "ku.concept.1",
                        "combined_confidence": 1.6,
                    }
                ]
            )
        )

        result = await service.discover_semantic_bridges(uid="ku.test.1", max_results=10)

        assert result.is_ok
        assert len(result.value) == 1
        bridge = result.value[0]
        assert bridge["target_uid"] == "ku.bridge.1"
        assert bridge["target_domain"] == "business"
        assert bridge["transferability"] == 0.8  # 1.6 / 2.0

    @pytest.mark.asyncio
    async def test_discover_semantic_bridges_with_domain_filter(self, service):
        """Test bridge discovery with target domain filter."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Fix: execute_query returns Result.ok([...]), not bare list
        service.neo4j.execute_query = AsyncMock(return_value=Result.ok([]))

        result = await service.discover_semantic_bridges(
            uid="ku.test.1", target_domain="business", max_results=5
        )

        assert result.is_ok
        # Verify Neo4j was called with domain parameter
        call_args = service.neo4j.execute_query.call_args
        assert call_args[0][1]["target_domain"] == "business"

    @pytest.mark.asyncio
    async def test_infer_relationships_success(self, service):
        """Test successful relationship inference."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Fix: execute_query returns Result.ok([...]), not bare list
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "target": {"uid": "ku.inferred.1", "title": "Inferred Target"},
                        "inferred_type": "REQUIRES_THEORETICAL_UNDERSTANDING",
                        "via_uid": "ku.intermediate.1",
                        "confidence": 0.81,  # 0.9 * 0.9
                    }
                ]
            )
        )

        result = await service.infer_relationships(
            uid="ku.test.1", max_inferences=10, min_confidence=0.7
        )

        assert result.is_ok
        assert len(result.value) == 1
        inference = result.value[0]
        assert inference["target_uid"] == "ku.inferred.1"
        assert inference["confidence"] == 0.81
        assert "Transitive relationship" in inference["reasoning"]

    @pytest.mark.asyncio
    async def test_infer_relationships_filters_by_confidence(self, service):
        """Test that inference respects minimum confidence threshold."""
        service.repo.get = AsyncMock(return_value=Result.ok(make_ku_dto("ku.test.1", "Test")))

        # Fix: execute_query returns Result.ok([...]), not bare list
        # Return inference with low confidence
        service.neo4j.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "target": {"uid": "ku.low.1", "title": "Low Confidence"},
                        "inferred_type": "REQUIRES_THEORETICAL_UNDERSTANDING",
                        "via_uid": "ku.via.1",
                        "confidence": 0.5,  # Below min_confidence
                    }
                ]
            )
        )

        result = await service.infer_relationships(
            uid="ku.test.1", max_inferences=10, min_confidence=0.7
        )

        assert result.is_ok
        assert len(result.value) == 0  # Filtered out by confidence


class TestFacadeDelegation:
    """Test that LessonService facade correctly delegates to semantic service."""

    @pytest.mark.asyncio
    async def test_facade_delegates_semantic_methods(self):
        """Test that all semantic methods are delegated."""
        from core.services.lesson_service import LessonService

        # Create facade with mocked dependencies
        repo = MagicMock()
        content_repo = MagicMock()
        neo4j = MagicMock()
        query_builder = MagicMock()  # Required for LessonSearchService
        graph_intel = MagicMock()

        service = LessonService(
            repo=repo,
            content_repo=content_repo,
            neo4j_adapter=neo4j,
            query_builder=query_builder,
            graph_intelligence_service=graph_intel,
        )

        # Verify semantic sub-service exists
        assert hasattr(service, "semantic")
        assert service.semantic is not None

        # Verify all semantic methods exist on facade
        assert callable(service.create_with_semantic_relationships)
        assert callable(service.get_semantic_neighborhood)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
