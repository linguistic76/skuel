"""
Askesis Citation Service - Phase 4C: Citations as First-Class Citizen

Service for retrieving and formatting relationship citations for Askesis responses.

Core Principle: "Every Askesis response includes source and evidence"

Use Cases:
- Retrieve citations for knowledge unit prerequisites
- Format citations for Askesis chat responses
- Build bibliography for comprehensive responses
- Track source and evidence transparency

Philosophy:
🌳 Tree metaphor - Source and evidence ground the knowledge graph
- 🌱 Roots = Evidence (grounding in reality)
- 🌳 Trunk = Source (provenance classification)
- 🍃 Branches = Knowledge graph relationships
"""

from dataclasses import dataclass, field
from typing import Any

from core.models.query import ProvenanceQueries
from core.models.relationship_names import RelationshipName
from core.ports.base_protocols import BackendOperations
from core.utils.result_simplified import Errors, Result


@dataclass(frozen=True)
class RelationshipCitation:
    """
    Citation for a single relationship in the knowledge graph.

    Represents the source and evidence for one prerequisite/dependency relationship.

    Attributes:
        from_uid: Source node UID (e.g., "ku.django_models")
        from_title: Source node title (e.g., "Django Models")
        to_uid: Target node UID (e.g., "ku.python_oop")
        to_title: Target node title (e.g., "Python OOP")
        source: Provenance classification (e.g., "expert_verified", "curriculum")
        evidence: List of supporting references (e.g., citations, data, observations)
        confidence: Confidence level (0.0-1.0)
        notes: Optional human context/notes
        citation_text: Formatted citation for display
    """

    from_uid: str
    from_title: str
    to_uid: str
    to_title: str
    source: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 1.0
    notes: str | None = None
    citation_text: str = ""

    def __post_init__(self) -> None:
        """Generate citation text if not provided."""
        if not self.citation_text:
            object.__setattr__(self, "citation_text", self._generate_citation_text())

    def _generate_citation_text(self) -> str:
        """
        Generate formatted citation text.

        Format:
            Source: <source_label>

            Evidence:
              1. <evidence_item_1>
              2. <evidence_item_2>
              ...

            Note: <notes>
        """
        lines = [f"Source: {self._format_source()}"]

        if self.evidence:
            lines.append("\nEvidence:")
            for i, item in enumerate(self.evidence, 1):
                lines.append(f"  {i}. {item}")

        if self.notes:
            lines.append(f"\nNote: {self.notes}")

        return "\n".join(lines)

    def _format_source(self) -> str:
        """Format source as human-readable label."""
        source_labels = {
            "manual": "Manually created",
            "expert_verified": "Expert-verified",
            "curriculum": "SKUEL curriculum",
            "ai_generated": "AI-suggested",
            "inferred": "Automatically inferred",
            "research_verified": "Research-backed",
            "user_created": "User observation",
            "semantic": "Semantic similarity",
        }
        return source_labels.get(self.source, self.source)


@dataclass
class CitationBundle:
    """
    Bundle of citations for a knowledge unit.

    Represents all citations for prerequisites of a single knowledge unit.

    Attributes:
        knowledge_uid: Knowledge unit UID
        knowledge_title: Knowledge unit title
        citations: List of relationship citations
        citation_count: Total number of citations
        well_supported_count: Count of citations with 3+ evidence items
        source_distribution: Distribution of sources (e.g., {"expert_verified": 5, "curriculum": 3})
    """

    knowledge_uid: str
    knowledge_title: str
    citations: list[RelationshipCitation] = field(default_factory=list)
    citation_count: int = 0
    well_supported_count: int = 0
    source_distribution: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Calculate statistics from citations."""
        self.citation_count = len(self.citations)
        self.well_supported_count = sum(1 for c in self.citations if len(c.evidence) >= 3)

        # Calculate source distribution
        distribution: dict[str, int] = {}
        for citation in self.citations:
            distribution[citation.source] = distribution.get(citation.source, 0) + 1
        object.__setattr__(self, "source_distribution", distribution)

    def format_for_askesis(self) -> str:
        """
        Format citations for Askesis response.

        Returns formatted string with all citations for display in chat.

        Example:
            To learn Django Models, you should first understand these prerequisites:

            1. **Python OOP** (Critical prerequisite)

               Source: Expert-verified

               Evidence:
                 • Django Documentation: 'Understanding OOP is essential'
                 • 92% of learners completed OOP before Django (n=2,145)
                 • Verified by Django core team (2024-01-15)

               Note: Foundational for understanding models and views.

            2. **Python Functions** (Important prerequisite)
               ...
        """
        if not self.citations:
            return "No citations available for this knowledge unit."

        lines = [
            f"To learn **{self.knowledge_title}**, you should first understand these prerequisites:",
            "",
        ]

        for i, citation in enumerate(self.citations, 1):
            lines.append(f"{i}. **{citation.to_title}** (Prerequisite)")
            lines.append("")

            # Indent citation text
            citation_lines = citation.citation_text.split("\n")
            for line in citation_lines:
                lines.append(f"   {line}")

            lines.append("")  # Blank line between citations

        return "\n".join(lines)


class AskesisCitationService:
    """
    Service for retrieving and formatting citations for Askesis responses.

    Provides methods to:
    - Get citations for a knowledge unit's prerequisites
    - Format citations for Askesis chat display
    - Build bibliographies for comprehensive responses
    - Analyze source and evidence quality
    """

    def __init__(self, backend: BackendOperations) -> None:
        """
        Initialize citation service.

        Args:
            backend: Neo4j backend for executing queries
        """
        self.backend = backend

    async def get_citations_for_knowledge_unit(
        self,
        knowledge_uid: str,
        depth: int = 3,
        min_evidence_count: int = 0,
    ) -> Result[CitationBundle]:
        """
        Get all citations for a knowledge unit's prerequisites.

        Args:
            knowledge_uid: Knowledge unit UID
            depth: Maximum prerequisite chain depth (default: 3)
            min_evidence_count: Minimum evidence items to include (default: 0 = all)

        Returns:
            Result[CitationBundle] with all citations

        Example:
            result = await service.get_citations_for_knowledge_unit(
                "ku.django_models",
                depth=3,
                min_evidence_count=1  # Only well-documented prerequisites
            )
        """
        # Build citation export query
        query, params = ProvenanceQueries.build_citation_export_query(
            node_uid=knowledge_uid,
            node_label="Entity",
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
            depth=depth,
        )

        # Execute query
        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="get_citations",
                    message=f"Failed to retrieve citations for {knowledge_uid}",
                    details={"query_error": result.expect_error().message},
                )
            )

        records = result.value

        # Parse citations from records
        citations = []
        for record in records:
            # Filter by evidence count if specified
            evidence = record.get("evidence", [])
            if min_evidence_count > 0 and len(evidence) < min_evidence_count:
                continue

            citation = RelationshipCitation(
                from_uid=knowledge_uid,
                from_title="",  # Will be populated later if needed
                to_uid=record["prerequisite_uid"],
                to_title=record["prerequisite_title"],
                source=record["source"],
                evidence=evidence,
                confidence=record.get("confidence", 1.0),
                notes=record.get("notes"),
            )
            citations.append(citation)

        # Create citation bundle
        bundle = CitationBundle(
            knowledge_uid=knowledge_uid,
            knowledge_title="",  # Will be populated by caller if needed
            citations=citations,
        )

        return Result.ok(bundle)

    async def get_well_supported_citations(
        self,
        knowledge_uid: str,
        min_evidence_count: int = 3,
        depth: int = 3,
    ) -> Result[CitationBundle]:
        """
        Get only well-supported citations (3+ evidence items).

        Convenience method for high-quality citations only.

        Args:
            knowledge_uid: Knowledge unit UID
            min_evidence_count: Minimum evidence items (default: 3)
            depth: Maximum prerequisite chain depth (default: 3)

        Returns:
            Result[CitationBundle] with well-supported citations only
        """
        return await self.get_citations_for_knowledge_unit(
            knowledge_uid=knowledge_uid,
            depth=depth,
            min_evidence_count=min_evidence_count,
        )

    async def format_citations_for_askesis(
        self,
        knowledge_uid: str,
        knowledge_title: str,
        depth: int = 3,
        min_evidence_count: int = 1,
    ) -> Result[str]:
        """
        Get formatted citation text for Askesis response.

        Args:
            knowledge_uid: Knowledge unit UID
            knowledge_title: Knowledge unit title (for formatting)
            depth: Maximum prerequisite chain depth (default: 3)
            min_evidence_count: Minimum evidence items to include (default: 1)

        Returns:
            Result[str] with formatted citation text ready for Askesis display

        Example:
            result = await service.format_citations_for_askesis(
                "ku.django_models",
                "Django Models",
                min_evidence_count=1
            )

            # Use in Askesis response:
            response = f"{main_content}\n\n{result.value}"
        """
        # Get citations
        bundle_result = await self.get_citations_for_knowledge_unit(
            knowledge_uid=knowledge_uid,
            depth=depth,
            min_evidence_count=min_evidence_count,
        )

        if bundle_result.is_error:
            return Result.fail(bundle_result.expect_error())

        bundle = bundle_result.value

        # Set knowledge title
        object.__setattr__(bundle, "knowledge_title", knowledge_title)

        # Format for Askesis
        formatted_text = bundle.format_for_askesis()

        return Result.ok(formatted_text)

    async def analyze_citation_quality(
        self,
        knowledge_uid: str,
        depth: int = 5,
    ) -> Result[dict[str, Any]]:
        """
        Analyze citation quality for a knowledge unit.

        Provides statistics on source distribution, evidence strength, etc.

        Args:
            knowledge_uid: Knowledge unit UID
            depth: Maximum prerequisite chain depth (default: 5)

        Returns:
            Result[dict] with quality analysis

        Example:
            {
                "total_prerequisites": 8,
                "with_evidence": 6,
                "well_supported": 4,
                "evidence_percentage": 75.0,
                "source_distribution": {
                    "expert_verified": 3,
                    "curriculum": 2,
                    "ai_generated": 1
                },
                "quality_score": 0.78
            }
        """
        # Get all citations (no filtering)
        bundle_result = await self.get_citations_for_knowledge_unit(
            knowledge_uid=knowledge_uid,
            depth=depth,
            min_evidence_count=0,
        )

        if bundle_result.is_error:
            return Result.fail(bundle_result.expect_error())

        bundle = bundle_result.value

        # Calculate quality metrics
        total = bundle.citation_count
        with_evidence = sum(1 for c in bundle.citations if len(c.evidence) > 0)
        well_supported = bundle.well_supported_count

        # Quality score (weighted average)
        # - 40% source trustworthiness
        # - 60% evidence strength
        trusted_sources = {"expert_verified", "curriculum", "research_verified"}
        trusted_count = sum(1 for c in bundle.citations if c.source in trusted_sources)

        source_score = trusted_count / total if total > 0 else 0
        evidence_score = with_evidence / total if total > 0 else 0

        quality_score = 0.4 * source_score + 0.6 * evidence_score

        analysis = {
            "total_prerequisites": total,
            "with_evidence": with_evidence,
            "well_supported": well_supported,
            "evidence_percentage": round(100.0 * with_evidence / total, 1) if total > 0 else 0.0,
            "source_distribution": bundle.source_distribution,
            "quality_score": round(quality_score, 2),
        }

        return Result.ok(analysis)
