"""
LP Lateral Service - Domain-Specific Lateral Relationships
===========================================================

Manages lateral relationships specifically for Learning Paths (LP) domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for learning path relationships.

Common LP Lateral Relationships:
    - PREREQUISITE_FOR: LP A should be completed before LP B
    - ALTERNATIVE_TO: Different curriculum paths to same goal
    - COMPLEMENTARY_TO: Paths that enhance each other
    - RELATED_TO: Paths in similar domains

Usage:
    lp_lateral = LpLateralService(driver, lp_service)

    # Create alternative relationship
    await lp_lateral.create_alternative_relationship(
        lp_a_uid="lp:abc123",
        lp_b_uid="lp:xyz789",
        comparison_criteria="Different approaches to web development",
        approach_differences=["Frontend-first", "Backend-first"]
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class LpLateralService:
    """
    Domain-specific service for Learning Path lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - LP-specific relationship types (alternatives, complementary)
    """

    def __init__(
        self,
        driver: Any,
        lp_service: Any,  # LpOperations protocol
    ) -> None:
        """
        Initialize LP lateral service.

        Args:
            driver: Neo4j driver
            lp_service: LP domain service for validation
        """
        self.driver = driver
        self.lp_service = lp_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_prerequisite_relationship(
        self,
        prerequisite_uid: str,
        dependent_uid: str,
        strength: float = 0.8,
        reasoning: str | None = None,
    ) -> Result[bool]:
        """
        Create PREREQUISITE_FOR relationship between learning paths.

        Args:
            prerequisite_uid: LP that should be completed first
            dependent_uid: LP that builds on prerequisite
            strength: How strongly recommended (0.0-1.0)
            reasoning: Optional explanation for sequencing

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Python Basics" PREREQUISITE_FOR "Web Development with Django"
        """
        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        # Note: LP is SHARED content (no ownership check needed)

        return await self.lateral_service.create_lateral_relationship(
            source_uid=prerequisite_uid,
            target_uid=dependent_uid,
            relationship_type=LateralRelationType.PREREQUISITE_FOR,
            metadata={
                "strength": strength,
                "reasoning": reasoning,
                "domain": "lp",
            },
            validate=True,
            auto_inverse=True,  # Creates REQUIRES_PREREQUISITE
        )

    async def create_alternative_relationship(
        self,
        lp_a_uid: str,
        lp_b_uid: str,
        comparison_criteria: str,
        approach_differences: list[str] | None = None,
    ) -> Result[bool]:
        """
        Create ALTERNATIVE_TO relationship for different curriculum paths.

        Args:
            lp_a_uid: First learning path
            lp_b_uid: Second learning path
            comparison_criteria: How to compare paths
            approach_differences: Optional list of key differences

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Frontend Bootcamp" ALTERNATIVE_TO "Full-Stack Bootcamp"
            → Different scopes to web development mastery
        """
        return await self.lateral_service.create_lateral_relationship(
            source_uid=lp_a_uid,
            target_uid=lp_b_uid,
            relationship_type=LateralRelationType.ALTERNATIVE_TO,
            metadata={
                "comparison_criteria": comparison_criteria,
                "approach_differences": approach_differences or [],
                "domain": "lp",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_complementary_relationship(
        self,
        lp_a_uid: str,
        lp_b_uid: str,
        synergy_description: str,
        combined_benefit: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic paths.

        Args:
            lp_a_uid: First learning path
            lp_b_uid: Second learning path
            synergy_description: How paths complement each other
            combined_benefit: Optional description of combined mastery

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Backend Development" COMPLEMENTARY_TO "DevOps Fundamentals"
            → Combined mastery enables full deployment pipeline
        """
        return await self.lateral_service.create_lateral_relationship(
            source_uid=lp_a_uid,
            target_uid=lp_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "combined_benefit": combined_benefit,
                "domain": "lp",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_related_relationship(
        self,
        lp_a_uid: str,
        lp_b_uid: str,
        relationship_type: str,
        strength: float = 0.7,
        description: str | None = None,
    ) -> Result[bool]:
        """
        Create RELATED_TO relationship for semantic connection.

        Args:
            lp_a_uid: First learning path
            lp_b_uid: Second learning path
            relationship_type: Type of relationship (e.g., "same_domain", "cross_discipline")
            strength: Strength of relation (0.0-1.0)
            description: Optional description of relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Machine Learning" RELATED_TO "Deep Learning"
            → Related specializations in AI domain
        """
        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        return await self.lateral_service.create_lateral_relationship(
            source_uid=lp_a_uid,
            target_uid=lp_b_uid,
            relationship_type=LateralRelationType.RELATED_TO,
            metadata={
                "relationship_type": relationship_type,
                "strength": strength,
                "description": description,
                "domain": "lp",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_prerequisites(
        self,
        lp_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get learning paths that are prerequisites for this path.

        Args:
            lp_uid: Learning path UID

        Returns:
            Result with list of prerequisite paths
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=lp_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="incoming",  # Things that point to this path
            include_metadata=True,
        )

    async def get_dependent_paths(
        self,
        lp_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get learning paths that build on this path.

        Args:
            lp_uid: Learning path UID

        Returns:
            Result with list of dependent paths
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=lp_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="outgoing",  # Things this path points to
            include_metadata=True,
        )

    async def get_alternative_paths(
        self,
        lp_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get alternative learning paths.

        Args:
            lp_uid: Learning path UID

        Returns:
            Result with list of alternative paths
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=lp_uid,
            relationship_types=[LateralRelationType.ALTERNATIVE_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_complementary_paths(
        self,
        lp_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get complementary learning paths.

        Args:
            lp_uid: Learning path UID

        Returns:
            Result with list of complementary paths
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=lp_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_related_paths(
        self,
        lp_uid: str,
        min_strength: float = 0.5,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related learning paths.

        Args:
            lp_uid: Learning path UID
            min_strength: Minimum relationship strength

        Returns:
            Result with list of related paths
        """
        all_related = await self.lateral_service.get_lateral_relationships(
            entity_uid=lp_uid,
            relationship_types=[LateralRelationType.RELATED_TO],
            direction="both",
            include_metadata=True,
        )

        if all_related.is_error:
            return all_related

        # Filter by minimum strength
        filtered = [
            path
            for path in all_related.value
            if path.get("metadata", {}).get("strength", 0) >= min_strength
        ]

        return Result.ok(filtered)

    async def get_sibling_paths(
        self,
        lp_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling learning paths (same parent category or domain).

        Args:
            lp_uid: Learning path UID

        Returns:
            Result with list of sibling paths
        """
        return await self.lateral_service.get_siblings(
            entity_uid=lp_uid,
            include_explicit_only=False,
        )


__all__ = ["LpLateralService"]
