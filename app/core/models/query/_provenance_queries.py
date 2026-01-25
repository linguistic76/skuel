"""
Provenance Query Builders - Phase 4B: Trust-Based Intelligence

Query builders for source and evidence-based filtering and analysis.

Core Principle: "Every relationship is traceable to its origin"

Use Cases:
- Trust filtering: Show only expert-verified prerequisites
- Data quality: Analyze provenance distribution
- AI validation: Queue AI relationships for review
- Auto-promotion: Upgrade high-quality AI relationships
- Evidence strength: Filter by citation count
- Citation export: Generate bibliographies

Author: SKUEL Development Team
Date: November 23, 2025
"""

from typing import Any


class ProvenanceQueries:
    """
    Provenance-based query builders for trust and evidence filtering.

    All methods return (cypher_query: str, params: dict) tuples.
    """

    @staticmethod
    def build_trust_filtered_prerequisite_chain(
        node_uid: str,
        node_label: str = "Ku",
        relationship_type: str = "REQUIRES",
        allowed_sources: list[str] | None = None,
        depth: int = 5,
        min_confidence: float = 0.7,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build prerequisite chain filtered by trusted sources.

        Use Case: "Show only expert-verified prerequisites"

        Args:
            node_uid: Starting node UID
            node_label: Neo4j label (default: KnowledgeUnit)
            relationship_type: Relationship type (default: REQUIRES)
            allowed_sources: List of trusted sources (default: expert_verified, curriculum)
            depth: Maximum traversal depth (default: 5)
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            (cypher_query, params) tuple

        Example:
            query, params = ProvenanceQueries.build_trust_filtered_prerequisite_chain(
                node_uid="ku.advanced_python",
                allowed_sources=["expert_verified", "curriculum"]
            )
        """
        if allowed_sources is None:
            allowed_sources = ["expert_verified", "curriculum"]

        cypher = f"""
        MATCH path = (end:{node_label} {{uid: $node_uid}})<-[rs:{relationship_type}*1..{depth}]-(start)
        WHERE all(r IN rs WHERE
            r.source IN $allowed_sources AND
            coalesce(r.confidence, 1.0) >= $min_confidence
        )
        WITH path, rs, start
        WHERE NOT (start)<-[:{relationship_type}]-()
        RETURN start, path, length(path) as depth,
               [r IN rs | {{source: r.source, confidence: r.confidence, evidence: r.evidence}}] as metadata
        ORDER BY depth DESC
        """

        params = {
            "node_uid": node_uid,
            "allowed_sources": allowed_sources,
            "min_confidence": min_confidence,
        }

        return cypher, params

    @staticmethod
    def build_provenance_distribution_query(
        node_label: str = "Ku",
        relationship_type: str = "REQUIRES",
        user_uid: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Analyze provenance distribution across relationships.

        Use Case: "Data quality audit - what % of relationships are AI-generated vs expert-verified?"

        Args:
            node_label: Neo4j label (default: KnowledgeUnit)
            relationship_type: Relationship type (default: REQUIRES)
            user_uid: Optional user filter (if provided, only user's relationships)

        Returns:
            (cypher_query, params) tuple

        Example:
            query, params = ProvenanceQueries.build_provenance_distribution_query()

            # Results:
            # source          | count | percentage | avg_confidence | with_evidence
            # expert_verified | 1,247 | 45.2%      | 0.95          | 98.2%
            # curriculum      | 856   | 31.0%      | 0.92          | 100.0%
            # ai_generated    | 523   | 18.9%      | 0.78          | 12.4%
            # manual          | 134   | 4.9%       | 0.85          | 45.5%
        """
        user_filter = ""
        if user_uid:
            user_filter = "WHERE start.user_uid = $user_uid OR end.user_uid = $user_uid"

        cypher = f"""
        MATCH (start:{node_label})-[r:{relationship_type}]->(end:{node_label})
        {user_filter}
        WITH r.source as source,
             count(r) as relationship_count,
             avg(coalesce(r.confidence, 1.0)) as avg_confidence,
             sum(CASE WHEN size(coalesce(r.evidence, [])) > 0 THEN 1 ELSE 0 END) as with_evidence_count
        WITH source, relationship_count, avg_confidence, with_evidence_count,
             sum(relationship_count) OVER () as total_count
        RETURN
            source,
            relationship_count as count,
            round(100.0 * relationship_count / total_count, 1) as percentage,
            round(avg_confidence, 2) as avg_confidence,
            round(100.0 * with_evidence_count / relationship_count, 1) as evidence_percentage
        ORDER BY relationship_count DESC
        """

        params = {}
        if user_uid:
            params["user_uid"] = user_uid

        return cypher, params

    @staticmethod
    def build_ai_validation_queue_query(
        node_label: str = "Ku",
        relationship_type: str = "REQUIRES",
        min_confidence: float = 0.7,
        min_usage_count: int = 10,
        limit: int = 100,
    ) -> tuple[str, dict[str, Any]]:
        """
        Queue AI-generated relationships for expert validation.

        Use Case: "Prioritize high-usage AI relationships for review"

        Strategy:
        - Only AI-generated relationships
        - High confidence (min_confidence threshold)
        - High usage (traversal_count >= min_usage_count)
        - No evidence yet (needs validation)

        Args:
            node_label: Neo4j label (default: KnowledgeUnit)
            relationship_type: Relationship type (default: REQUIRES)
            min_confidence: Minimum confidence (default: 0.7)
            min_usage_count: Minimum traversal count (default: 10)
            limit: Maximum results (default: 100)

        Returns:
            (cypher_query, params) tuple

        Example:
            query, params = ProvenanceQueries.build_ai_validation_queue_query(
                min_confidence=0.8,
                min_usage_count=50
            )

            # Results: High-quality AI relationships worth validating
            # start_uid | end_uid | confidence | usage_count | created_at
        """
        cypher = f"""
        MATCH (start:{node_label})-[r:{relationship_type}]->(end:{node_label})
        WHERE r.source = 'ai_generated'
          AND coalesce(r.confidence, 0.0) >= $min_confidence
          AND coalesce(r.traversal_count, 0) >= $min_usage_count
          AND size(coalesce(r.evidence, [])) = 0
        RETURN
            start.uid as start_uid,
            start.title as start_title,
            end.uid as end_uid,
            end.title as end_title,
            r.confidence as confidence,
            r.strength as strength,
            r.traversal_count as usage_count,
            r.created_at as created_at,
            r.notes as notes
        ORDER BY r.traversal_count DESC, r.confidence DESC
        LIMIT $limit
        """

        params = {
            "min_confidence": min_confidence,
            "min_usage_count": min_usage_count,
            "limit": limit,
        }

        return cypher, params

    @staticmethod
    def build_provenance_upgrade_candidates_query(
        node_label: str = "Ku",
        relationship_type: str = "REQUIRES",
        min_confidence: float = 0.85,
        min_strength: float = 0.8,
        min_usage_count: int = 50,
        limit: int = 50,
    ) -> tuple[str, dict[str, Any]]:
        """
        Find AI relationships that should be auto-promoted to verified.

        Use Case: "Upgrade high-quality AI relationships to verified status"

        Criteria for auto-promotion:
        - AI-generated source
        - High confidence (>= 0.85)
        - High strength (>= 0.8)
        - High usage (>= 50 traversals)
        - Proven reliability through usage

        Args:
            node_label: Neo4j label (default: KnowledgeUnit)
            relationship_type: Relationship type (default: REQUIRES)
            min_confidence: Minimum confidence (default: 0.85)
            min_strength: Minimum strength (default: 0.8)
            min_usage_count: Minimum traversal count (default: 50)
            limit: Maximum results (default: 50)

        Returns:
            (cypher_query, params) tuple

        Example:
            query, params = ProvenanceQueries.build_provenance_upgrade_candidates_query()

            # Results: AI relationships ready for promotion
            # These can be auto-upgraded to "research_verified" or similar
        """
        cypher = f"""
        MATCH (start:{node_label})-[r:{relationship_type}]->(end:{node_label})
        WHERE r.source = 'ai_generated'
          AND coalesce(r.confidence, 0.0) >= $min_confidence
          AND coalesce(r.strength, 0.0) >= $min_strength
          AND coalesce(r.traversal_count, 0) >= $min_usage_count
        RETURN
            start.uid as start_uid,
            start.title as start_title,
            end.uid as end_uid,
            end.title as end_title,
            r.confidence as confidence,
            r.strength as strength,
            r.traversal_count as usage_count,
            r.created_at as created_at,
            r.evidence as current_evidence,
            'Auto-promotion candidate: ' +
                toString(r.traversal_count) + ' uses, ' +
                'confidence ' + toString(round(r.confidence * 100)) + '%' as recommendation
        ORDER BY r.traversal_count DESC, r.confidence DESC
        LIMIT $limit
        """

        params = {
            "min_confidence": min_confidence,
            "min_strength": min_strength,
            "min_usage_count": min_usage_count,
            "limit": limit,
        }

        return cypher, params

    @staticmethod
    def build_well_supported_prerequisites_query(
        node_uid: str,
        node_label: str = "Ku",
        relationship_type: str = "REQUIRES",
        min_evidence_count: int = 3,
        depth: int = 5,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build prerequisite chain filtered by evidence strength.

        Use Case: "Show only well-documented prerequisites (3+ evidence items)"

        Args:
            node_uid: Starting node UID
            node_label: Neo4j label (default: KnowledgeUnit)
            relationship_type: Relationship type (default: REQUIRES)
            min_evidence_count: Minimum evidence items (default: 3)
            depth: Maximum traversal depth (default: 5)

        Returns:
            (cypher_query, params) tuple

        Example:
            query, params = ProvenanceQueries.build_well_supported_prerequisites_query(
                node_uid="ku.advanced_python",
                min_evidence_count=3
            )

            # Returns: Only prerequisites with 3+ evidence items
        """
        cypher = f"""
        MATCH path = (end:{node_label} {{uid: $node_uid}})<-[rs:{relationship_type}*1..{depth}]-(start)
        WHERE all(r IN rs WHERE size(coalesce(r.evidence, [])) >= $min_evidence_count)
        WITH path, rs, start
        WHERE NOT (start)<-[:{relationship_type}]-()
        RETURN start, path, length(path) as depth,
               [r IN rs | {{
                   source: r.source,
                   confidence: r.confidence,
                   evidence: r.evidence,
                   evidence_count: size(r.evidence)
               }}] as metadata
        ORDER BY depth DESC
        """

        params = {
            "node_uid": node_uid,
            "min_evidence_count": min_evidence_count,
        }

        return cypher, params

    @staticmethod
    def build_citation_export_query(
        node_uid: str,
        node_label: str = "Ku",
        relationship_type: str = "REQUIRES",
        depth: int = 3,
    ) -> tuple[str, dict[str, Any]]:
        """
        Export bibliography/citations for a knowledge unit.

        Use Case: "Generate bibliography for Askesis response"

        Returns all evidence from prerequisite chain formatted for citation.

        Args:
            node_uid: Starting node UID
            node_label: Neo4j label (default: KnowledgeUnit)
            relationship_type: Relationship type (default: REQUIRES)
            depth: Maximum traversal depth (default: 3)

        Returns:
            (cypher_query, params) tuple

        Example:
            query, params = ProvenanceQueries.build_citation_export_query(
                node_uid="ku.django_models"
            )

            # Results:
            # prerequisite_uid | prerequisite_title | source | evidence | citation_text
            # ku.python_oop    | Python OOP         | expert | [...]    | "Source: Expert-verified..."
        """
        cypher = f"""
        MATCH (end:{node_label} {{uid: $node_uid}})<-[r:{relationship_type}*1..{depth}]-(prereq:{node_label})
        WITH prereq, r
        WHERE size(coalesce(r[0].evidence, [])) > 0
        UNWIND r as rel
        WITH DISTINCT prereq, rel
        RETURN
            prereq.uid as prerequisite_uid,
            prereq.title as prerequisite_title,
            rel.source as source,
            rel.evidence as evidence,
            rel.notes as notes,
            rel.confidence as confidence,
            'Source: ' + rel.source + '\\nEvidence:\\n' +
                reduce(s = '', item IN rel.evidence | s + '  • ' + item + '\\n') as citation_text
        ORDER BY prereq.title
        """

        params = {
            "node_uid": node_uid,
        }

        return cypher, params
