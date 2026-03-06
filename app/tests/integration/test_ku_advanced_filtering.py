"""
Integration tests for advanced KU relationship filtering features.

Tests:
- Confidence/strength filtering
- Relationship type filtering
- Property-based batch queries
- KU-specific helper methods
"""

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.curriculum.curriculum import Curriculum
from core.models.enums import Domain, SELCategory
from core.services.article.article_relationship_helpers import (
    KuRelationshipFilters,
    KuRelationshipTypeFilters,
)


@pytest.mark.asyncio
class TestKuConfidenceFiltering:
    """Integration tests for confidence-based KU relationship filtering."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    @pytest_asyncio.fixture
    async def sample_kus_with_relationships(self, ku_backend):
        """Create sample KUs with varying relationship strengths."""
        # Create knowledge units
        ku_basics = Curriculum(
            uid="ku:python_basics",
            title="Python Basics",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        ku_functions = Curriculum(
            uid="ku:python_functions",
            title="Python Functions",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        ku_oop = Curriculum(
            uid="ku:python_oop",
            title="Python OOP",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        ku_advanced = Curriculum(
            uid="ku:python_advanced",
            title="Advanced Python",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )

        result = await ku_backend.create(ku_basics)
        assert result.is_ok, f"Setup failed: Could not create Ku Basics: {result.error}"
        result = await ku_backend.create(ku_functions)
        assert result.is_ok, f"Setup failed: Could not create Ku Functions: {result.error}"
        result = await ku_backend.create(ku_oop)
        assert result.is_ok, f"Setup failed: Could not create Ku Oop: {result.error}"
        result = await ku_backend.create(ku_advanced)
        assert result.is_ok, f"Setup failed: Could not create Ku Advanced: {result.error}"

        # Create relationships with varying strengths
        # January 2026: Use unified relationship names from RelationshipName enum
        await ku_backend.create_relationships_batch(
            [
                # Strong prerequisite (0.9 strength)
                (
                    "ku:python_functions",
                    "ku:python_basics",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.9, "prerequisite_type": "foundational"},
                ),
                # Medium prerequisite (0.6 strength)
                (
                    "ku:python_oop",
                    "ku:python_basics",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.6, "prerequisite_type": "foundational"},
                ),
                # Strong advanced prerequisite (0.85 strength)
                (
                    "ku:python_advanced",
                    "ku:python_oop",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.85, "prerequisite_type": "advanced"},
                ),
                # Weak prerequisite (0.4 strength)
                (
                    "ku:python_advanced",
                    "ku:python_functions",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.4, "prerequisite_type": "foundational"},
                ),
                # Strong enablement
                (
                    "ku:python_basics",
                    "ku:python_functions",
                    "ENABLES_KNOWLEDGE",
                    {"enablement_strength": 0.8},
                ),
                # Weak enablement
                (
                    "ku:python_basics",
                    "ku:python_oop",
                    "ENABLES_KNOWLEDGE",
                    {"enablement_strength": 0.5},
                ),
            ]
        )

        return [
            "ku:python_basics",
            "ku:python_functions",
            "ku:python_oop",
            "ku:python_advanced",
        ]

    async def test_high_confidence_prerequisites_filtering(
        self, ku_backend, sample_kus_with_relationships
    ):
        """Test filtering prerequisites by high confidence (strength >= 0.8)."""
        # Build query for high-confidence prerequisites
        query, params = KuRelationshipFilters.build_high_confidence_prerequisites_query(
            min_strength=0.8
        )

        params["uids"] = sample_kus_with_relationships

        # Execute query
        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        # Build results map
        has_high_conf_prereqs = {
            record["uid"]: record["has_relationships"] for record in result.value
        }

        # Verify only KUs with strength >= 0.8 prerequisites are flagged
        assert has_high_conf_prereqs["ku:python_functions"] is True  # 0.9 strength
        assert has_high_conf_prereqs["ku:python_advanced"] is True  # 0.85 strength
        assert has_high_conf_prereqs["ku:python_oop"] is False  # 0.6 strength (too low)
        assert has_high_conf_prereqs["ku:python_basics"] is False  # No outgoing prerequisites

    async def test_medium_confidence_prerequisites_filtering(
        self, ku_backend, sample_kus_with_relationships
    ):
        """Test filtering prerequisites by medium confidence (strength >= 0.5)."""
        query, params = KuRelationshipFilters.build_high_confidence_prerequisites_query(
            min_strength=0.5
        )

        params["uids"] = sample_kus_with_relationships

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        has_medium_conf_prereqs = {
            record["uid"]: record["has_relationships"] for record in result.value
        }

        # Verify KUs with strength >= 0.5
        assert has_medium_conf_prereqs["ku:python_functions"] is True  # 0.9
        assert has_medium_conf_prereqs["ku:python_oop"] is True  # 0.6
        assert (
            has_medium_conf_prereqs["ku:python_advanced"] is True
        )  # 0.85 (OOP), 0.4 (functions) - has one >= 0.5
        assert has_medium_conf_prereqs["ku:python_basics"] is False  # No prerequisites

    async def test_get_high_strength_prerequisite_uids(
        self, ku_backend, sample_kus_with_relationships
    ):
        """Test getting actual UIDs of high-strength prerequisites."""
        query, params = KuRelationshipFilters.build_get_high_strength_prerequisites_query(
            min_strength=0.8, limit_per_ku=50
        )

        params["uids"] = sample_kus_with_relationships

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        # Build map of uid -> prerequisite uids
        prereq_map = {record["uid"]: record["related_uids"] for record in result.value}

        # Verify high-strength prerequisites
        assert prereq_map["ku:python_functions"] == ["ku:python_basics"]  # 0.9 strength
        assert prereq_map["ku:python_advanced"] == [
            "ku:python_oop"
        ]  # 0.85 strength (0.4 filtered out)
        assert prereq_map["ku:python_oop"] == []  # 0.6 strength filtered out
        assert prereq_map["ku:python_basics"] == []  # No prerequisites

    async def test_strong_enablements_filtering(self, ku_backend, sample_kus_with_relationships):
        """Test filtering by strong enablement relationships."""
        query, params = KuRelationshipFilters.build_strong_enablements_query(
            min_enablement_strength=0.7
        )

        params["uids"] = sample_kus_with_relationships

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        has_strong_enablements = {
            record["uid"]: record["has_relationships"] for record in result.value
        }

        # Verify strong enablements (>= 0.7)
        assert has_strong_enablements["ku:python_basics"] is True  # 0.8 enablement
        assert has_strong_enablements["ku:python_functions"] is False  # No outgoing enablements
        assert has_strong_enablements["ku:python_oop"] is False  # No enablements
        assert has_strong_enablements["ku:python_advanced"] is False  # No enablements

    async def test_get_strong_enablement_uids(self, ku_backend, sample_kus_with_relationships):
        """Test getting UIDs of strongly enabled KUs."""
        query, params = KuRelationshipFilters.build_get_strong_enablements_query(
            min_enablement_strength=0.7, limit_per_ku=100
        )

        params["uids"] = sample_kus_with_relationships

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        enablement_map = {record["uid"]: record["related_uids"] for record in result.value}

        # Verify strong enablements
        assert enablement_map["ku:python_basics"] == [
            "ku:python_functions"
        ]  # 0.8 enablement (0.5 filtered out)
        assert enablement_map["ku:python_functions"] == []
        assert enablement_map["ku:python_oop"] == []
        assert enablement_map["ku:python_advanced"] == []


@pytest.mark.asyncio
class TestKuTypeFiltering:
    """Integration tests for relationship type filtering."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    @pytest_asyncio.fixture
    async def sample_kus_with_types(self, ku_backend):
        """Create sample KUs with different prerequisite types."""
        ku_basics = Curriculum(
            uid="ku:math_basics",
            title="Math Basics",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        ku_algebra = Curriculum(
            uid="ku:algebra",
            title="Algebra",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        ku_calculus = Curriculum(
            uid="ku:calculus",
            title="Calculus",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )

        result = await ku_backend.create(ku_basics)
        assert result.is_ok, f"Setup failed: Could not create Ku Basics: {result.error}"
        result = await ku_backend.create(ku_algebra)
        assert result.is_ok, f"Setup failed: Could not create Ku Algebra: {result.error}"
        result = await ku_backend.create(ku_calculus)
        assert result.is_ok, f"Setup failed: Could not create Ku Calculus: {result.error}"

        # Create relationships with different types
        # January 2026: Use unified relationship names from RelationshipName enum
        await ku_backend.create_relationships_batch(
            [
                # Foundational prerequisite
                (
                    "ku:algebra",
                    "ku:math_basics",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.9, "prerequisite_type": "foundational"},
                ),
                # Advanced prerequisite
                (
                    "ku:calculus",
                    "ku:algebra",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.85, "prerequisite_type": "advanced"},
                ),
            ]
        )

        return ["ku:math_basics", "ku:algebra", "ku:calculus"]

    async def test_foundational_prerequisites_filtering(self, ku_backend, sample_kus_with_types):
        """Test filtering for foundational prerequisites only."""
        query, params = KuRelationshipTypeFilters.build_foundational_prerequisites_query()

        params["uids"] = sample_kus_with_types

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        has_foundational = {record["uid"]: record["has_relationships"] for record in result.value}

        # Only ku:algebra has foundational prerequisite
        assert has_foundational["ku:algebra"] is True
        assert has_foundational["ku:calculus"] is False  # Has advanced, not foundational
        assert has_foundational["ku:math_basics"] is False  # No prerequisites

    async def test_advanced_prerequisites_filtering(self, ku_backend, sample_kus_with_types):
        """Test filtering for advanced prerequisites only."""
        query, params = KuRelationshipTypeFilters.build_advanced_prerequisites_query()

        params["uids"] = sample_kus_with_types

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        has_advanced = {record["uid"]: record["has_relationships"] for record in result.value}

        # Only ku:calculus has advanced prerequisite
        assert has_advanced["ku:calculus"] is True
        assert has_advanced["ku:algebra"] is False  # Has foundational, not advanced
        assert has_advanced["ku:math_basics"] is False  # No prerequisites


@pytest.mark.asyncio
class TestBatchPerformance:
    """Performance verification for batch filtering queries."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    @pytest_asyncio.fixture
    async def many_kus_with_relationships(self, ku_backend):
        """Create many KUs for performance testing."""
        import asyncio

        # Create 30 KUs
        ku_uids = [f"ku:perf_test_{i}" for i in range(30)]

        create_tasks = [
            ku_backend.create(
                Curriculum(
                    uid=uid,
                    title=f"Test KU {i}",
                    domain=Domain.TECH,
                    sel_category=SELCategory.SELF_MANAGEMENT,
                )
            )
            for i, uid in enumerate(ku_uids)
        ]

        await asyncio.gather(*create_tasks)

        # Create relationships (vary strengths)
        # January 2026: Use unified relationship names from RelationshipName enum
        relationships = []
        for i in range(1, 30):
            strength = 0.5 + (i % 5) * 0.1  # Strengths: 0.5, 0.6, 0.7, 0.8, 0.9
            relationships.append(
                (
                    ku_uids[i],
                    ku_uids[i - 1],
                    "REQUIRES_KNOWLEDGE",
                    {"strength": strength, "prerequisite_type": "foundational"},
                )
            )

        await ku_backend.create_relationships_batch(relationships)

        return ku_uids

    async def test_batch_filtering_correctness(self, ku_backend, many_kus_with_relationships):
        """Verify batch filtering returns correct results."""
        query, params = KuRelationshipFilters.build_high_confidence_prerequisites_query(
            min_strength=0.8
        )

        params["uids"] = many_kus_with_relationships

        result = await ku_backend.execute_query(query, params)
        assert result.is_ok

        # Should have ~12 KUs with strength >= 0.8 (0.8 and 0.9 in the pattern)
        has_high_conf = {record["uid"]: record["has_relationships"] for record in result.value}

        high_conf_count = sum(1 for v in has_high_conf.values() if v)

        # Verify expected count (approximately 40% of KUs with prerequisites)
        assert 10 <= high_conf_count <= 15  # Should be around 12
