"""
KU Lateral Service - Domain-Specific Lateral Relationships
===========================================================

Manages lateral relationships specifically for Knowledge Units (KU) domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for knowledge relationships.

Common KU Lateral Relationships:
    - PREREQUISITE_FOR: KU A must be learned before KU B
    - ENABLES: Learning KU A unlocks ability to learn KU B
    - RELATED_TO: Topics in similar domain
    - SIMILAR_TO: Overlapping content or concepts

Usage:
    ku_lateral = KuLateralService(driver, ku_service)

    # Create prerequisite relationship
    await ku_lateral.create_prerequisite_relationship(
        prerequisite_uid="ku_python-basics",
        dependent_uid="ku_django",
        strength=0.95
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class KuLateralService:
    """
    Domain-specific service for Knowledge Unit lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - KU-specific relationship types (prerequisites, enables)
    """

    def __init__(
        self,
        driver: Any,
        ku_service: Any,  # KuOperations protocol
    ) -> None:
        """
        Initialize KU lateral service.

        Args:
            driver: Neo4j driver
            ku_service: KU domain service for validation
        """
        self.driver = driver
        self.ku_service = ku_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_prerequisite_relationship(
        self,
        prerequisite_uid: str,
        dependent_uid: str,
        strength: float = 0.8,
        topic_area: str | None = None,
    ) -> Result[bool]:
        """
        Create PREREQUISITE_FOR relationship between knowledge units.

        Args:
            prerequisite_uid: KU that must be learned first
            dependent_uid: KU that requires prerequisite
            strength: How essential prerequisite is (0.0-1.0)
            topic_area: Optional domain categorization

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Python Basics" PREREQUISITE_FOR "Django Framework"
        """
        if not 0.0 <= strength <= 1.0:
            return Errors.validation("strength must be between 0.0 and 1.0")

        # Note: KU is SHARED content (no ownership check needed)

        return await self.lateral_service.create_lateral_relationship(
            source_uid=prerequisite_uid,
            target_uid=dependent_uid,
            relationship_type=LateralRelationType.PREREQUISITE_FOR,
            metadata={
                "strength": strength,
                "topic_area": topic_area,
                "domain": "ku",
            },
            validate=True,
            auto_inverse=True,  # Creates REQUIRES_PREREQUISITE
        )

    async def create_enables_relationship(
        self,
        enabler_uid: str,
        enabled_uid: str,
        confidence: float = 0.8,
        topic_domain: str | None = None,
    ) -> Result[bool]:
        """
        Create ENABLES relationship (learning A unlocks B).

        Args:
            enabler_uid: KU that enables learning
            enabled_uid: KU that is unlocked
            confidence: Confidence in enabling relationship (0.0-1.0)
            topic_domain: Optional domain categorization

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Functions" ENABLES "Decorators"
            → Understanding functions enables learning decorators
        """
        if not 0.0 <= confidence <= 1.0:
            return Errors.validation("confidence must be between 0.0 and 1.0")

        return await self.lateral_service.create_lateral_relationship(
            source_uid=enabler_uid,
            target_uid=enabled_uid,
            relationship_type=LateralRelationType.ENABLES,
            metadata={
                "confidence": confidence,
                "topic_domain": topic_domain,
                "domain": "ku",
            },
            validate=True,
            auto_inverse=True,  # Creates ENABLED_BY
        )

    async def create_related_relationship(
        self,
        ku_a_uid: str,
        ku_b_uid: str,
        relationship_type: str,
        strength: float = 0.7,
        description: str | None = None,
    ) -> Result[bool]:
        """
        Create RELATED_TO relationship for semantic connection.

        Args:
            ku_a_uid: First KU
            ku_b_uid: Second KU
            relationship_type: Type of relationship (e.g., "same_domain", "applied_theory")
            strength: Strength of relation (0.0-1.0)
            description: Optional description of relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Algorithms" RELATED_TO "Data Structures"
            → Topics frequently studied together
        """
        if not 0.0 <= strength <= 1.0:
            return Errors.validation("strength must be between 0.0 and 1.0")

        return await self.lateral_service.create_lateral_relationship(
            source_uid=ku_a_uid,
            target_uid=ku_b_uid,
            relationship_type=LateralRelationType.RELATED_TO,
            metadata={
                "relationship_type": relationship_type,
                "strength": strength,
                "description": description,
                "domain": "ku",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_similar_relationship(
        self,
        ku_a_uid: str,
        ku_b_uid: str,
        similarity_score: float = 0.8,
        basis: str = "content",  # "content", "metadata", "user_behavior"
    ) -> Result[bool]:
        """
        Create SIMILAR_TO relationship for overlapping content.

        Args:
            ku_a_uid: First KU
            ku_b_uid: Second KU
            similarity_score: How similar (0.0-1.0)
            basis: Basis for similarity determination

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Python Lists" SIMILAR_TO "Python Tuples"
            → Similar data structure concepts
        """
        if not 0.0 <= similarity_score <= 1.0:
            return Errors.validation("similarity_score must be between 0.0 and 1.0")

        return await self.lateral_service.create_lateral_relationship(
            source_uid=ku_a_uid,
            target_uid=ku_b_uid,
            relationship_type=LateralRelationType.SIMILAR_TO,
            metadata={
                "similarity_score": similarity_score,
                "basis": basis,
                "domain": "ku",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_prerequisites(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get knowledge units that are prerequisites for this KU.

        Args:
            ku_uid: KU UID

        Returns:
            Result with list of prerequisite KUs
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ku_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="incoming",  # Things that point to this KU
            include_metadata=True,
        )

    async def get_enabled_by(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get knowledge units that enable learning this KU.

        Args:
            ku_uid: KU UID

        Returns:
            Result with list of enabling KUs
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ku_uid,
            relationship_types=[LateralRelationType.ENABLES],
            direction="incoming",  # Things that enable this KU
            include_metadata=True,
        )

    async def get_enables(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get knowledge units that this KU enables.

        Args:
            ku_uid: KU UID

        Returns:
            Result with list of enabled KUs
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ku_uid,
            relationship_types=[LateralRelationType.ENABLES],
            direction="outgoing",  # Things this KU enables
            include_metadata=True,
        )

    async def get_related_topics(
        self,
        ku_uid: str,
        min_strength: float = 0.5,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related knowledge units.

        Args:
            ku_uid: KU UID
            min_strength: Minimum relationship strength

        Returns:
            Result with list of related KUs
        """
        all_related = await self.lateral_service.get_lateral_relationships(
            entity_uid=ku_uid,
            relationship_types=[LateralRelationType.RELATED_TO],
            direction="both",
            include_metadata=True,
        )

        if all_related.is_error:
            return all_related

        # Filter by minimum strength
        filtered = [
            ku
            for ku in all_related.value
            if ku.get("metadata", {}).get("strength", 0) >= min_strength
        ]

        return Result.ok(filtered)

    async def get_similar_topics(
        self,
        ku_uid: str,
        min_similarity: float = 0.7,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get similar knowledge units.

        Args:
            ku_uid: KU UID
            min_similarity: Minimum similarity score

        Returns:
            Result with list of similar KUs
        """
        all_similar = await self.lateral_service.get_lateral_relationships(
            entity_uid=ku_uid,
            relationship_types=[LateralRelationType.SIMILAR_TO],
            direction="both",
            include_metadata=True,
        )

        if all_similar.is_error:
            return all_similar

        # Filter by minimum similarity
        filtered = [
            ku
            for ku in all_similar.value
            if ku.get("metadata", {}).get("similarity_score", 0) >= min_similarity
        ]

        return Result.ok(filtered)

    async def get_sibling_topics(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling KUs (same parent via ORGANIZES).

        Args:
            ku_uid: KU UID

        Returns:
            Result with list of sibling KUs
        """
        return await self.lateral_service.get_siblings(
            entity_uid=ku_uid,
            include_explicit_only=False,
        )


__all__ = ["KuLateralService"]
