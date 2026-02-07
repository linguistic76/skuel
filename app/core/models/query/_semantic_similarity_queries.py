"""
Semantic Similarity Query Builders
===================================

Query builders that leverage semantic_distance field for similarity ranking.

Quick Win #4 Enhancement (November 23, 2025):
- Added semantic_distance filtering and ranking
- Enables similarity-based search and recommendations
- Leverages already-defined EdgeMetadata.semantic_distance field

See: /docs/improvement_proposals/EDGEMETADATA_UTILIZATION_SUMMARY.md
"""

from typing import Any


class SemanticSimilarityQueries:
    """
    Pure Cypher query builders for semantic similarity operations.

    All methods use EdgeMetadata.semantic_distance to rank results by
    conceptual similarity (computed from vector embeddings).

    Key Insight:
    - Lower semantic_distance = More similar concepts
    - semantic_distance is 0.0-1.0 scale (0 = identical, 1 = completely different)
    - Typical threshold: 0.3 for "similar", 0.5 for "related"
    """

    @staticmethod
    def build_similar_concepts_query(
        source_uid: str,
        relationship_types: list[str] | None = None,
        max_distance: float = 0.3,
        min_confidence: float = 0.7,
        limit: int = 10,
    ) -> tuple[str, dict[str, Any]]:
        """
        Find concepts similar to source based on semantic distance.

        Returns concepts ranked by similarity (most similar first).

        Args:
            source_uid: Source concept UID
            relationship_types: Optional list of relationship types to filter
                               (default: ["RELATED_TO", "SIMILAR_TO"])
            max_distance: Maximum semantic distance (default 0.3 = similar)
            min_confidence: Minimum relationship confidence (default 0.7)
            limit: Maximum results to return (default 10)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Find concepts similar to Python basics
            query, params = SemanticSimilarityQueries.build_similar_concepts_query(
                source_uid="ku.python_basics",
                max_distance=0.3,  # Only highly similar concepts
                limit=10
            )

            # Returns ranked by similarity:
            # 1. ku.python_fundamentals (distance: 0.05)
            # 2. ku.python_intro (distance: 0.12)
            # 3. ku.programming_basics (distance: 0.28)
        """
        # Default relationship types for similarity
        rel_types = relationship_types or ["RELATED_TO", "SIMILAR_TO"]
        rel_pattern = "|".join(rel_types)

        cypher = f"""
        MATCH (source {{uid: $source_uid}})-[r:{rel_pattern}]-(similar)

        // Filter by semantic distance and confidence
        WHERE r.semantic_distance IS NOT NULL
          AND r.semantic_distance <= $max_distance
          AND coalesce(r.confidence, 1.0) >= $min_confidence

        RETURN
            similar.uid as uid,
            similar.title as title,
            r.semantic_distance as similarity_score,
            coalesce(r.confidence, 1.0) as confidence,
            type(r) as relationship_type

        // Rank by similarity (lower distance = more similar)
        ORDER BY r.semantic_distance ASC
        LIMIT $limit
        """

        return cypher.strip(), {
            "source_uid": source_uid,
            "max_distance": max_distance,
            "min_confidence": min_confidence,
            "limit": limit,
        }

    @staticmethod
    def build_semantic_search_ranking_query(
        search_query_uid: str,
        candidate_uids: list[str],
        max_distance: float = 0.5,
    ) -> tuple[str, dict[str, Any]]:
        """
        Rank search results by semantic similarity to query concept.

        Use this to re-rank search results based on conceptual similarity
        rather than just keyword matching.

        Args:
            search_query_uid: UID of concept representing search intent
            candidate_uids: List of candidate result UIDs to rank
            max_distance: Maximum semantic distance to include (default 0.5)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # User searches for "React hooks"
            # Embedding service finds query_uid = "ku.react_hooks_concept"
            # Keyword search finds 50 candidates
            # Re-rank by semantic similarity:

            query, params = SemanticSimilarityQueries.build_semantic_search_ranking_query(
                search_query_uid="ku.react_hooks_concept",
                candidate_uids=["ku.useState", "ku.useEffect", "ku.react_lifecycle"],
                max_distance=0.5
            )

            # Returns ranked:
            # 1. ku.useState (distance: 0.08) - Highly relevant
            # 2. ku.useEffect (distance: 0.12) - Very relevant
            # 3. ku.react_lifecycle (distance: 0.45) - Somewhat relevant
        """
        cypher = """
        MATCH (query {uid: $query_uid})
        MATCH (candidate)
        WHERE candidate.uid IN $candidate_uids

        // Find semantic relationship (if exists)
        OPTIONAL MATCH (query)-[r:RELATED_TO|SIMILAR_TO]-(candidate)
        WHERE r.semantic_distance IS NOT NULL
          AND r.semantic_distance <= $max_distance

        RETURN
            candidate.uid as uid,
            candidate.title as title,
            coalesce(r.semantic_distance, 1.0) as similarity_score,
            CASE
                WHEN r.semantic_distance IS NULL THEN false
                ELSE true
            END as has_semantic_link

        // Rank by similarity (lower = more relevant)
        ORDER BY similarity_score ASC
        """

        return cypher.strip(), {
            "query_uid": search_query_uid,
            "candidate_uids": candidate_uids,
            "max_distance": max_distance,
        }

    @staticmethod
    def build_concept_clusters_query(
        domain: str | None = None,
        max_distance: float = 0.25,
        min_cluster_size: int = 3,
    ) -> tuple[str, dict[str, Any]]:
        """
        Discover concept clusters based on semantic similarity.

        Finds groups of highly similar concepts that form natural clusters.

        Args:
            domain: Optional domain filter (e.g., "TECH", "BUSINESS")
            max_distance: Maximum intra-cluster distance (default 0.25 = tight clusters)
            min_cluster_size: Minimum concepts per cluster (default 3)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Find concept clusters in TECH domain
            query, params = SemanticSimilarityQueries.build_concept_clusters_query(
                domain="TECH",
                max_distance=0.25,
                min_cluster_size=3
            )

            # Returns clusters like:
            # Cluster 1: React Hooks (useState, useEffect, useContext, useReducer)
            # Cluster 2: Python Web (Flask, Django, FastAPI)
            # Cluster 3: Database Design (normalization, indexing, schemas)
        """
        domain_filter = "AND ku.domain = $domain" if domain else ""

        cypher = f"""
        MATCH (ku1:Ku)-[r:RELATED_TO|SIMILAR_TO]-(ku2:Ku)
        WHERE r.semantic_distance IS NOT NULL
          AND r.semantic_distance <= $max_distance
          AND id(ku1) < id(ku2)  // Avoid duplicate pairs
          {domain_filter}

        // Group by cluster (connected components with tight similarity)
        WITH collect(DISTINCT ku1) + collect(DISTINCT ku2) as cluster_nodes

        // Filter clusters by minimum size
        WHERE size(cluster_nodes) >= $min_cluster_size

        RETURN
            [n IN cluster_nodes | {{uid: n.uid, title: n.title}}] as concepts,
            size(cluster_nodes) as cluster_size

        ORDER BY cluster_size DESC
        """

        params: dict[str, Any] = {
            "max_distance": max_distance,
            "min_cluster_size": min_cluster_size,
        }

        if domain:
            params["domain"] = domain

        return cypher.strip(), params

    @staticmethod
    def build_learning_path_similarity_query(
        target_uid: str,
        alternative_count: int = 3,
        max_distance: float = 0.4,
    ) -> tuple[str, dict[str, Any]]:
        """
        Find alternative learning paths based on semantic similarity.

        For each prerequisite, find semantically similar alternatives.

        Args:
            target_uid: Target concept UID
            alternative_count: Number of alternatives per prerequisite (default 3)
            max_distance: Maximum semantic distance for alternatives (default 0.4)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Learning React - find alternative prerequisites
            query, params = SemanticSimilarityQueries.build_learning_path_similarity_query(
                target_uid="ku.react_advanced",
                alternative_count=3,
                max_distance=0.4
            )

            # Returns:
            # Prerequisite: ku.javascript_basics
            #   Alternative 1: ku.modern_javascript (distance: 0.15)
            #   Alternative 2: ku.es6_fundamentals (distance: 0.22)
            #   Alternative 3: ku.js_core_concepts (distance: 0.38)
        """
        cypher = """
        MATCH (target {uid: $target_uid})<-[:REQUIRES_KNOWLEDGE]-(prereq)

        // Find semantically similar alternatives for each prerequisite
        OPTIONAL MATCH (prereq)-[r:RELATED_TO|SIMILAR_TO]-(alternative)
        WHERE r.semantic_distance IS NOT NULL
          AND r.semantic_distance <= $max_distance
          AND alternative.uid <> target.uid  // Don't suggest target itself

        WITH prereq, alternative, r.semantic_distance as distance
        ORDER BY prereq.uid, distance ASC

        // Group alternatives by prerequisite
        WITH prereq,
             collect({
                 uid: alternative.uid,
                 title: alternative.title,
                 similarity_score: distance
             })[0..$alternative_count] as alternatives

        RETURN
            prereq.uid as prerequisite_uid,
            prereq.title as prerequisite_title,
            alternatives

        ORDER BY prerequisite_title
        """

        return cypher.strip(), {
            "target_uid": target_uid,
            "alternative_count": alternative_count,
            "max_distance": max_distance,
        }

    @staticmethod
    def build_related_topics_timeline_query(
        source_uid: str,
        max_distance: float = 0.35,
        time_window_days: int = 90,
    ) -> tuple[str, dict[str, Any]]:
        """
        Find related topics that are temporally and semantically relevant.

        Combines semantic similarity with temporal validity for time-aware recommendations.

        Args:
            source_uid: Source concept UID
            max_distance: Maximum semantic distance (default 0.35)
            time_window_days: Days to look back/forward (default 90)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Find currently relevant topics related to React
            query, params = SemanticSimilarityQueries.build_related_topics_timeline_query(
                source_uid="ku.react",
                max_distance=0.35,
                time_window_days=90
            )

            # Returns:
            # ku.react_19 (distance: 0.10, released: 30 days ago)
            # ku.server_components (distance: 0.25, trending: current)
            # (EXCLUDES: ku.class_components - deprecated 2 years ago)
        """
        cypher = """
        MATCH (source {uid: $source_uid})-[r:RELATED_TO|SIMILAR_TO]-(related)

        // Semantic similarity filter
        WHERE r.semantic_distance IS NOT NULL
          AND r.semantic_distance <= $max_distance

          // Temporal relevance filter (only currently valid)
          AND (r.valid_from IS NULL OR r.valid_from <= datetime())
          AND (r.valid_until IS NULL OR r.valid_until >= datetime())

        // Calculate days since introduction (recency score)
        WITH related, r,
             CASE
                 WHEN r.valid_from IS NOT NULL
                 THEN duration.between(r.valid_from, datetime()).days
                 ELSE null
             END as days_since_introduced

        // Filter by time window
        WHERE days_since_introduced IS NULL
           OR days_since_introduced <= $time_window_days

        RETURN
            related.uid as uid,
            related.title as title,
            r.semantic_distance as similarity_score,
            days_since_introduced as recency_days,
            CASE
                WHEN days_since_introduced <= 30 THEN 'new'
                WHEN days_since_introduced <= 90 THEN 'recent'
                ELSE 'established'
            END as recency_category

        ORDER BY
            r.semantic_distance ASC,  // Most similar first
            days_since_introduced ASC  // Most recent within similarity tier
        """

        return cypher.strip(), {
            "source_uid": source_uid,
            "max_distance": max_distance,
            "time_window_days": time_window_days,
        }
