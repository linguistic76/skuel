"""
Knowledge Unit Relationship Filtering Helpers
==============================================

Advanced filtering utilities for KU relationships with confidence, strength,
and type-based filtering.

**ADVANCED FEATURES (November 17, 2025):**

This module provides convenience helpers for working with knowledge unit
relationships, particularly for filtering by relationship quality metrics
like strength and confidence.

Key Features:
- Confidence filtering for prerequisite chains
- Strength-based relationship filtering
- Type-specific batch operations
- High-quality relationship discovery

Architecture:
- Builds on CypherGenerator's property filtering capabilities
- Returns standard Result[T] for consistency
- Supports batch operations for performance
"""

from __future__ import annotations

from typing import Any

from core.models.relationship_names import RelationshipName


class KuRelationshipFilters:
    """
    Convenience helpers for filtering KU relationships.

    **USE THIS FOR:**
    - Finding high-confidence prerequisites
    - Discovering strong knowledge connections
    - Filtering by relationship type
    - Quality-based knowledge graph queries
    """

    # ========================================================================
    # CONFIDENCE FILTERING (November 17, 2025)
    # ========================================================================

    @staticmethod
    def build_high_confidence_prerequisites_query(
        min_strength: float = 0.8,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query for checking high-confidence prerequisites.

        **QUALITY CONTROL:**
        Only returns prerequisites with strength >= min_strength.
        Use this to focus on critical prerequisites and avoid noise.

        Args:
            min_strength: Minimum relationship strength (default 0.8)

        Returns:
            Tuple of (query_template, params) for batch execution

        Example:
            query, params = KuRelationshipFilters.build_high_confidence_prerequisites_query(
                min_strength=0.8
            )
            params["uids"] = ku_uids
            result = await backend.execute_query(query, params)
            # Returns: [{"uid": "ku:python", "has_relationships": True}, ...]
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )
        from core.models.relationship_names import RelationshipName

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.REQUIRES_KNOWLEDGE.value],
            direction="outgoing",
            property_filters={"strength__gte": min_strength},
        )

    @staticmethod
    def build_strong_enablements_query(
        min_enablement_strength: float = 0.7,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query for checking strong enablement relationships.

        **LEARNING PATH CONSTRUCTION:**
        Use this to find knowledge units that strongly enable other concepts.
        Useful for building effective learning paths.

        Args:
            min_enablement_strength: Minimum enablement strength (default 0.7)

        Returns:
            Tuple of (query_template, params) for batch execution

        Example:
            query, params = KuRelationshipFilters.build_strong_enablements_query(
                min_enablement_strength=0.7
            )
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )
        from core.models.relationship_names import RelationshipName

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.ENABLES_KNOWLEDGE.value],
            direction="outgoing",
            property_filters={"enablement_strength__gte": min_enablement_strength},
        )

    @staticmethod
    def build_strong_relationships_query(
        min_strength: float = 0.7,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query for checking strong RELATED_TO relationships.

        **KNOWLEDGE DISCOVERY:**
        Use this to find strongly related concepts for recommendations
        and knowledge graph exploration.

        Args:
            min_strength: Minimum relationship strength (default 0.7)

        Returns:
            Tuple of (query_template, params) for batch execution

        Example:
            query, params = KuRelationshipFilters.build_strong_relationships_query(
                min_strength=0.7
            )
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.RELATED_TO.value],
            direction="both",
            property_filters={"strength__gte": min_strength},
        )

    # ========================================================================
    # GET RELATED UIDs WITH FILTERING (November 17, 2025)
    # ========================================================================

    @staticmethod
    def build_get_high_strength_prerequisites_query(
        min_strength: float = 0.8,
        limit_per_ku: int = 50,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query to get UIDs of high-strength prerequisites.

        **LEARNING PATH GENERATION:**
        Returns actual prerequisite UIDs (not just existence check).
        Use this to build prerequisite chains for learning paths.

        Args:
            min_strength: Minimum prerequisite strength (default 0.8)
            limit_per_ku: Max prerequisites per KU (default 50)

        Returns:
            Tuple of (query_template, params) for batch execution

        Example:
            query, params = KuRelationshipFilters.build_get_high_strength_prerequisites_query(
                min_strength=0.8,
                limit_per_ku=50
            )
            params["uids"] = ku_uids
            result = await backend.execute_query(query, params)
            # Returns: [{"uid": "ku:python", "related_uids": ["ku:basics", "ku:variables"]}, ...]
        """
        from core.models.query import (
            build_batch_get_related_with_filters,
        )
        from core.models.relationship_names import RelationshipName

        return build_batch_get_related_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.REQUIRES_KNOWLEDGE.value],
            direction="outgoing",
            property_filters={"strength__gte": min_strength},
            limit_per_node=limit_per_ku,
        )

    @staticmethod
    def build_get_strong_enablements_query(
        min_enablement_strength: float = 0.7,
        limit_per_ku: int = 100,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query to get UIDs of strongly enabled knowledge units.

        **FORWARD LEARNING PATHS:**
        Shows what knowledge units this KU strongly enables.
        Use for "what can I learn next?" recommendations.

        Args:
            min_enablement_strength: Minimum enablement strength (default 0.7)
            limit_per_ku: Max enabled KUs per source (default 100)

        Returns:
            Tuple of (query_template, params) for batch execution
        """
        from core.models.query import (
            build_batch_get_related_with_filters,
        )
        from core.models.relationship_names import RelationshipName

        return build_batch_get_related_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.ENABLES_KNOWLEDGE.value],
            direction="outgoing",
            property_filters={"enablement_strength__gte": min_enablement_strength},
            limit_per_node=limit_per_ku,
        )

    @staticmethod
    def build_get_strongly_related_query(
        min_strength: float = 0.7,
        limit_per_ku: int = 100,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query to get UIDs of strongly related knowledge units.

        **KNOWLEDGE GRAPH EXPLORATION:**
        Discovers related concepts with high relationship strength.
        Use for recommendations and knowledge graph visualization.

        Args:
            min_strength: Minimum relationship strength (default 0.7)
            limit_per_ku: Max related KUs per source (default 100)

        Returns:
            Tuple of (query_template, params) for batch execution
        """
        from core.models.query import (
            build_batch_get_related_with_filters,
        )

        return build_batch_get_related_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.RELATED_TO.value],
            direction="both",
            property_filters={"strength__gte": min_strength},
            limit_per_node=limit_per_ku,
        )


class KuRelationshipTypeFilters:
    """
    Type-specific filtering helpers for knowledge relationships.

    **USE THIS FOR:**
    - Filtering by prerequisite type (foundational vs advanced)
    - Filtering by relationship type (conceptual vs practical)
    - Hierarchical filtering (broader/narrower concepts)
    """

    @staticmethod
    def build_foundational_prerequisites_query() -> tuple[str, dict[str, Any]]:
        """
        Build query for foundational prerequisites only.

        **LEARNING PATH FOUNDATIONS:**
        Returns only prerequisites marked as "foundational" type.
        Use this to identify critical base knowledge.

        Returns:
            Tuple of (query_template, params) for batch execution

        Example:
            query, params = KuRelationshipTypeFilters.build_foundational_prerequisites_query()
            params["uids"] = ku_uids
            result = await backend.execute_query(query, params)
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )
        from core.models.relationship_names import RelationshipName

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.REQUIRES_KNOWLEDGE.value],
            direction="outgoing",
            property_filters={"prerequisite_type": "foundational"},
        )

    @staticmethod
    def build_advanced_prerequisites_query() -> tuple[str, dict[str, Any]]:
        """
        Build query for advanced prerequisites only.

        **ADVANCED LEARNING PATHS:**
        Returns only prerequisites marked as "advanced" type.
        Use for specialized or deep learning paths.

        Returns:
            Tuple of (query_template, params) for batch execution
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )
        from core.models.relationship_names import RelationshipName

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.REQUIRES_KNOWLEDGE.value],
            direction="outgoing",
            property_filters={"prerequisite_type": "advanced"},
        )

    @staticmethod
    def build_narrower_concepts_query(
        min_specificity_level: int = 1,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query for narrower (more specific) concepts.

        **KNOWLEDGE HIERARCHY:**
        Finds more specific concepts below this knowledge unit.
        Use for drilling down into details.

        Args:
            min_specificity_level: Minimum specificity level (default 1)

        Returns:
            Tuple of (query_template, params) for batch execution

        Example:
            query, params = KuRelationshipTypeFilters.build_narrower_concepts_query(
                min_specificity_level=2
            )
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.HAS_NARROWER.value],
            direction="outgoing",
            property_filters={"specificity_level__gte": min_specificity_level},
        )

    @staticmethod
    def build_broader_concepts_query(
        min_abstraction_level: int = 1,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build query for broader (more general) concepts.

        **KNOWLEDGE HIERARCHY:**
        Finds more general concepts above this knowledge unit.
        Use for understanding context and bigger picture.

        Args:
            min_abstraction_level: Minimum abstraction level (default 1)

        Returns:
            Tuple of (query_template, params) for batch execution
        """
        from core.models.query import (
            build_batch_relationship_exists_with_filters,
        )

        return build_batch_relationship_exists_with_filters(
            node_label="Ku",
            relationship_types=[RelationshipName.HAS_BROADER.value],
            direction="outgoing",
            property_filters={"abstraction_level__gte": min_abstraction_level},
        )
