"""
Integration Tests: Phase 4 Evidence Field & Citations
======================================================

Tests for Phase 4 implementation:
- EdgeMetadata evidence field
- Evidence helper methods
- Provenance query builders
- AskesisCitationService
- Citation integration with Askesis

Author: SKUEL Development Team
Date: November 23, 2025
"""

import pytest

from core.models.query import ProvenanceQueries
from core.models.semantic.edge_metadata import (
    EdgeMetadata,
    create_cited_metadata,
    create_research_backed_metadata,
    create_user_observation_metadata,
)
from core.services.askesis_citation_service import (
    AskesisCitationService,
    CitationBundle,
    RelationshipCitation,
)


class TestEdgeMetadataEvidence:
    """Test EdgeMetadata evidence field and methods."""

    def test_evidence_field_initialization(self):
        """Test evidence field is initialized as empty list."""
        metadata = EdgeMetadata()
        assert metadata.evidence == []
        assert isinstance(metadata.evidence, list)

    def test_evidence_field_with_data(self):
        """Test creating EdgeMetadata with evidence."""
        evidence_items = [
            "Django Documentation Ch. 3",
            "92% correlation (n=2,145)",
            "Verified by expert (2024-01-15)",
        ]

        metadata = EdgeMetadata(evidence=evidence_items)
        assert metadata.evidence == evidence_items
        assert len(metadata.evidence) == 3

    def test_to_neo4j_properties_includes_evidence(self):
        """Test evidence is included in Neo4j properties."""
        evidence = ["Citation 1", "Citation 2"]
        metadata = EdgeMetadata(evidence=evidence, confidence=0.9)

        props = metadata.to_neo4j_properties()

        assert "evidence" in props
        assert props["evidence"] == evidence
        assert props["confidence"] == 0.9

    def test_to_neo4j_properties_empty_evidence(self):
        """Test empty evidence is NOT included in properties."""
        metadata = EdgeMetadata(evidence=[])

        props = metadata.to_neo4j_properties()

        assert "evidence" not in props  # Empty evidence not stored

    def test_from_neo4j_properties_with_evidence(self):
        """Test parsing evidence from Neo4j properties."""
        props = {
            "confidence": 0.85,
            "strength": 0.8,
            "evidence": ["Citation A", "Citation B", "Citation C"],
            "source": "expert_verified",
        }

        metadata = EdgeMetadata.from_neo4j_properties(props)

        assert metadata.evidence == ["Citation A", "Citation B", "Citation C"]
        assert metadata.confidence == 0.85
        assert metadata.source == "expert_verified"

    def test_from_neo4j_properties_without_evidence(self):
        """Test parsing when evidence field is missing."""
        props = {
            "confidence": 0.8,
            "strength": 0.7,
        }

        metadata = EdgeMetadata.from_neo4j_properties(props)

        assert metadata.evidence == []  # Default to empty list

    def test_has_evidence_method(self):
        """Test has_evidence() method."""
        metadata_without = EdgeMetadata(evidence=[])
        metadata_with = EdgeMetadata(evidence=["Citation 1"])

        assert not metadata_without.has_evidence()
        assert metadata_with.has_evidence()

    def test_is_well_supported_method(self):
        """Test is_well_supported() method (3+ evidence items)."""
        metadata_weak = EdgeMetadata(evidence=["One", "Two"])
        metadata_strong = EdgeMetadata(evidence=["One", "Two", "Three"])
        metadata_very_strong = EdgeMetadata(evidence=["One", "Two", "Three", "Four"])

        assert not metadata_weak.is_well_supported()
        assert metadata_strong.is_well_supported()
        assert metadata_very_strong.is_well_supported()

    def test_add_evidence_method(self):
        """Test add_evidence() method (immutable pattern)."""
        original = EdgeMetadata(evidence=["Original citation"], confidence=0.8)

        # Add evidence - returns NEW instance
        updated = original.add_evidence("New citation")

        # Original is unchanged (frozen dataclass)
        assert original.evidence == ["Original citation"]

        # New instance has both citations
        assert updated.evidence == ["Original citation", "New citation"]
        assert updated.confidence == 0.8  # Other fields preserved

    def test_get_citation_text_method(self):
        """Test get_citation_text() formatting."""
        metadata = EdgeMetadata(
            source="expert_verified",
            evidence=["Citation 1", "Citation 2", "Citation 3"],
            notes="Critical for understanding",
        )

        citation_text = metadata.get_citation_text()

        assert "Source: Expert-verified" in citation_text
        assert "Evidence:" in citation_text
        assert "  1. Citation 1" in citation_text
        assert "  2. Citation 2" in citation_text
        assert "  3. Citation 3" in citation_text
        assert "Note: Critical for understanding" in citation_text

    def test_get_citation_text_no_evidence(self):
        """Test citation text with no evidence."""
        metadata = EdgeMetadata(source="manual", evidence=[])

        citation_text = metadata.get_citation_text()

        assert "Source: Manually created" in citation_text
        assert "Evidence:" not in citation_text


class TestEvidenceHelperFunctions:
    """Test evidence-aware helper functions."""

    def test_create_cited_metadata(self):
        """Test create_cited_metadata() helper."""
        metadata = create_cited_metadata(
            source="expert_verified",
            evidence=["Django Docs", "92% correlation", "Expert verification"],
            confidence=0.9,
            strength=0.8,
            notes="Critical prerequisite",
        )

        assert metadata.source == "expert_verified"
        assert len(metadata.evidence) == 3
        assert metadata.confidence == 0.9
        assert metadata.strength == 0.8
        assert metadata.notes == "Critical prerequisite"
        assert metadata.is_well_supported()

    def test_create_research_backed_metadata(self):
        """Test create_research_backed_metadata() helper."""
        metadata = create_research_backed_metadata(
            paper_citation="Smith et al. (2023) - Learning Sequence Analysis",
            additional_evidence=["n=1,247 learners", "p < 0.001"],
        )

        assert metadata.source == "research_verified"
        assert len(metadata.evidence) == 3  # Paper + 2 additional
        assert "Smith et al. (2023)" in metadata.evidence[0]
        assert "n=1,247 learners" in metadata.evidence
        assert metadata.is_well_supported()

    def test_create_user_observation_metadata(self):
        """Test create_user_observation_metadata() helper."""
        metadata = create_user_observation_metadata(
            observation="Required async understanding for WebSocket implementation",
            context="Project Apollo - real-time dashboard",
        )

        assert metadata.source == "user_created"
        assert len(metadata.evidence) == 1
        assert "async understanding" in metadata.evidence[0]
        assert metadata.notes == "Project Apollo - real-time dashboard"
        assert not metadata.is_well_supported()  # Only 1 evidence


class TestProvenanceQueries:
    """Test provenance query builders."""

    def test_build_trust_filtered_prerequisite_chain(self):
        """Test trust-filtered prerequisite chain query."""
        query, params = ProvenanceQueries.build_trust_filtered_prerequisite_chain(
            node_uid="ku.advanced_python",
            allowed_sources=["expert_verified", "curriculum"],
            depth=5,
            min_confidence=0.8,
        )

        assert isinstance(query, str)
        assert isinstance(params, dict)

        # Verify query structure
        assert "MATCH path" in query
        assert "WHERE all(r IN rs WHERE" in query
        assert "r.source IN $allowed_sources" in query
        assert "coalesce(r.confidence, 1.0) >= $min_confidence" in query

        # Verify parameters
        assert params["node_uid"] == "ku.advanced_python"
        assert params["allowed_sources"] == ["expert_verified", "curriculum"]
        assert params["min_confidence"] == 0.8

    def test_build_provenance_distribution_query(self):
        """Test provenance distribution analysis query."""
        query, params = ProvenanceQueries.build_provenance_distribution_query(
            node_label="Entity",
            relationship_type="REQUIRES",
        )

        assert isinstance(query, str)
        assert isinstance(params, dict)

        # Verify query structure
        assert "MATCH (start:Entity)-[r:REQUIRES]->(end:Entity)" in query
        assert "r.source as source" in query
        assert "count(r) as relationship_count" in query
        assert "avg(coalesce(r.confidence, 1.0))" in query
        assert "size(coalesce(r.evidence, []))" in query

    def test_build_ai_validation_queue_query(self):
        """Test AI validation queue query."""
        query, params = ProvenanceQueries.build_ai_validation_queue_query(
            min_confidence=0.7,
            min_usage_count=10,
            limit=100,
        )

        assert isinstance(query, str)
        assert isinstance(params, dict)

        # Verify query structure
        assert "WHERE r.source = 'ai_generated'" in query
        assert "coalesce(r.confidence, 0.0) >= $min_confidence" in query
        assert "coalesce(r.traversal_count, 0) >= $min_usage_count" in query
        assert "size(coalesce(r.evidence, [])) = 0" in query  # No evidence yet

        # Verify parameters
        assert params["min_confidence"] == 0.7
        assert params["min_usage_count"] == 10
        assert params["limit"] == 100

    def test_build_well_supported_prerequisites_query(self):
        """Test well-supported prerequisites query (3+ evidence)."""
        query, params = ProvenanceQueries.build_well_supported_prerequisites_query(
            node_uid="ku.django_models",
            min_evidence_count=3,
            depth=5,
        )

        assert isinstance(query, str)
        assert isinstance(params, dict)

        # Verify query structure
        assert (
            "WHERE all(r IN rs WHERE size(coalesce(r.evidence, [])) >= $min_evidence_count)"
            in query
        )
        assert "evidence_count: size(r.evidence)" in query

        # Verify parameters
        assert params["node_uid"] == "ku.django_models"
        assert params["min_evidence_count"] == 3

    def test_build_citation_export_query(self):
        """Test citation export query (bibliography generation)."""
        query, params = ProvenanceQueries.build_citation_export_query(
            node_uid="ku.python_oop",
            depth=3,
        )

        assert isinstance(query, str)
        assert isinstance(params, dict)

        # Verify query structure
        assert "MATCH (end:Entity {uid: $node_uid})" in query
        assert "WHERE size(coalesce(r[0].evidence, [])) > 0" in query
        assert "rel.evidence as evidence" in query
        assert "'Source: ' + rel.source" in query

        # Verify parameters
        assert params["node_uid"] == "ku.python_oop"


class TestRelationshipCitation:
    """Test RelationshipCitation dataclass."""

    def test_citation_initialization(self):
        """Test citation dataclass initialization."""
        citation = RelationshipCitation(
            from_uid="ku.django_models",
            from_title="Django Models",
            to_uid="ku.python_oop",
            to_title="Python OOP",
            source="expert_verified",
            evidence=["Django Docs Ch. 3", "92% correlation"],
            confidence=0.92,
            notes="Critical prerequisite",
        )

        assert citation.from_uid == "ku.django_models"
        assert citation.to_uid == "ku.python_oop"
        assert len(citation.evidence) == 2
        assert citation.confidence == 0.92

    def test_citation_text_auto_generation(self):
        """Test citation text is auto-generated."""
        citation = RelationshipCitation(
            from_uid="ku.a",
            from_title="A",
            to_uid="ku.b",
            to_title="B",
            source="expert_verified",
            evidence=["Citation 1", "Citation 2"],
        )

        assert citation.citation_text  # Should be auto-generated
        assert "Source: Expert-verified" in citation.citation_text
        assert "Citation 1" in citation.citation_text


class TestCitationBundle:
    """Test CitationBundle for knowledge units."""

    def test_bundle_initialization(self):
        """Test citation bundle initialization."""
        citations = [
            RelationshipCitation(
                from_uid="ku.a",
                from_title="A",
                to_uid="ku.b",
                to_title="B",
                source="expert_verified",
                evidence=["E1", "E2", "E3", "E4"],
            ),
            RelationshipCitation(
                from_uid="ku.a",
                from_title="A",
                to_uid="ku.c",
                to_title="C",
                source="curriculum",
                evidence=["E5"],
            ),
        ]

        bundle = CitationBundle(
            knowledge_uid="ku.a",
            knowledge_title="Knowledge A",
            citations=citations,
        )

        assert bundle.citation_count == 2
        assert bundle.well_supported_count == 1  # Only first has 3+ evidence
        assert bundle.source_distribution == {"expert_verified": 1, "curriculum": 1}

    def test_format_for_askesis(self):
        """Test formatting citations for Askesis display."""
        citations = [
            RelationshipCitation(
                from_uid="ku.django",
                from_title="Django",
                to_uid="ku.python_oop",
                to_title="Python OOP",
                source="expert_verified",
                evidence=["Django Docs"],
            ),
        ]

        bundle = CitationBundle(
            knowledge_uid="ku.django",
            knowledge_title="Django Models",
            citations=citations,
        )

        formatted = bundle.format_for_askesis()

        assert "To learn **Django Models**" in formatted
        assert "**Python OOP**" in formatted
        assert "Source: Expert-verified" in formatted


@pytest.mark.asyncio
class TestAskesisCitationServiceIntegration:
    """Integration tests for AskesisCitationService (requires mock backend)."""

    async def test_citation_service_initialization(self):
        """Test citation service can be initialized."""
        # This is a basic test - full integration requires Neo4j mock
        from unittest.mock import Mock

        mock_backend = Mock()
        service = AskesisCitationService(backend=mock_backend)

        assert service.backend == mock_backend


# Summary test showing complete Phase 4 workflow
def test_phase4_complete_workflow():
    """
    Integration test: Complete Phase 4 workflow.

    This test demonstrates the full flow:
    1. Create EdgeMetadata with evidence
    2. Convert to Neo4j properties
    3. Store in database (simulated)
    4. Retrieve from database
    5. Generate citation text
    """
    # Step 1: Create well-documented relationship
    metadata = create_cited_metadata(
        source="expert_verified",
        evidence=[
            "Django Documentation: 'Understanding OOP is essential'",
            "92% of learners completed OOP before Django (n=2,145)",
            "Verified by Django core team (2024-01-15)",
            "ACM Web Development curriculum recommendation",
        ],
        confidence=0.95,
        strength=0.9,
        notes="Critical foundational prerequisite",
    )

    # Step 2: Verify evidence is well-supported
    assert metadata.has_evidence()
    assert metadata.is_well_supported()
    assert len(metadata.evidence) == 4

    # Step 3: Convert to Neo4j properties
    props = metadata.to_neo4j_properties()
    assert "evidence" in props
    assert len(props["evidence"]) == 4

    # Step 4: Simulate database round-trip
    retrieved_metadata = EdgeMetadata.from_neo4j_properties(props)
    assert retrieved_metadata.evidence == metadata.evidence
    assert retrieved_metadata.confidence == 0.95

    # Step 5: Generate citation text for Askesis
    citation_text = retrieved_metadata.get_citation_text()

    assert "Source: Expert-verified" in citation_text
    assert "Evidence:" in citation_text
    assert "Django Documentation" in citation_text
    assert "92% of learners" in citation_text
    assert "Verified by Django core team" in citation_text
    assert "Note: Critical foundational prerequisite" in citation_text

    # Verify citation is transparent and grounded
    print("\n" + "=" * 80)
    print("PHASE 4 COMPLETE WORKFLOW - CITATION OUTPUT")
    print("=" * 80)
    print(citation_text)
    print("=" * 80)
