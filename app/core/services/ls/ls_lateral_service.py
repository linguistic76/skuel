"""
LS Lateral Service - Domain-Specific Lateral Relationships
===========================================================

Manages lateral relationships specifically for Learning Steps (LS) domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for learning step relationships.

Common LS Lateral Relationships:
    - PREREQUISITE_FOR: LS A must be completed before LS B
    - ALTERNATIVE_TO: Different approaches to same learning outcome
    - RELATED_TO: Steps in similar learning domains
    - COMPLEMENTARY_TO: Steps that enhance each other

Usage:
    ls_lateral = LsLateralService(driver, ls_service)

    # Create prerequisite relationship
    await ls_lateral.create_prerequisite_relationship(
        prerequisite_uid="ls:abc123",
        dependent_uid="ls:xyz789",
        strength=0.9
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class LsLateralService:
    """
    Domain-specific service for Learning Step lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - LS-specific relationship types (prerequisites, alternatives)
    """

    def __init__(
        self,
        driver: Any,
        ls_service: Any,  # LsOperations protocol
    ) -> None:
        """
        Initialize LS lateral service.

        Args:
            driver: Neo4j driver
            ls_service: LS domain service for validation
        """
        self.driver = driver
        self.ls_service = ls_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_prerequisite_relationship(
        self,
        prerequisite_uid: str,
        dependent_uid: str,
        strength: float = 0.9,
        reasoning: str | None = None,
    ) -> Result[bool]:
        """
        Create PREREQUISITE_FOR relationship between learning steps.

        Args:
            prerequisite_uid: LS that must be completed first
            dependent_uid: LS that requires prerequisite
            strength: How essential prerequisite is (0.0-1.0)
            reasoning: Optional explanation for prerequisite

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Variables Lesson" PREREQUISITE_FOR "Functions Lesson"
        """
        if not 0.0 <= strength <= 1.0:
            return Errors.validation("strength must be between 0.0 and 1.0")

        # Note: LS is SHARED content (no ownership check needed)

        return await self.lateral_service.create_lateral_relationship(
            source_uid=prerequisite_uid,
            target_uid=dependent_uid,
            relationship_type=LateralRelationType.PREREQUISITE_FOR,
            metadata={
                "strength": strength,
                "reasoning": reasoning,
                "domain": "ls",
            },
            validate=True,
            auto_inverse=True,  # Creates REQUIRES_PREREQUISITE
        )

    async def create_alternative_relationship(
        self,
        ls_a_uid: str,
        ls_b_uid: str,
        comparison_criteria: str,
        approach_type: str | None = None,
    ) -> Result[bool]:
        """
        Create ALTERNATIVE_TO relationship for different learning approaches.

        Args:
            ls_a_uid: First learning step
            ls_b_uid: Second learning step
            comparison_criteria: How to compare alternatives
            approach_type: Type of alternative (e.g., "visual_vs_textual", "theory_vs_practice")

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Video Tutorial" ALTERNATIVE_TO "Written Tutorial"
            → Different learning modalities for same outcome
        """
        return await self.lateral_service.create_lateral_relationship(
            source_uid=ls_a_uid,
            target_uid=ls_b_uid,
            relationship_type=LateralRelationType.ALTERNATIVE_TO,
            metadata={
                "comparison_criteria": comparison_criteria,
                "approach_type": approach_type,
                "domain": "ls",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_related_relationship(
        self,
        ls_a_uid: str,
        ls_b_uid: str,
        relationship_type: str,
        strength: float = 0.7,
        description: str | None = None,
    ) -> Result[bool]:
        """
        Create RELATED_TO relationship for semantic connection.

        Args:
            ls_a_uid: First learning step
            ls_b_uid: Second learning step
            relationship_type: Type of relationship (e.g., "same_topic", "applied_theory")
            strength: Strength of relation (0.0-1.0)
            description: Optional description of relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Array Methods" RELATED_TO "Array Exercises"
            → Theory and practice steps
        """
        if not 0.0 <= strength <= 1.0:
            return Errors.validation("strength must be between 0.0 and 1.0")

        return await self.lateral_service.create_lateral_relationship(
            source_uid=ls_a_uid,
            target_uid=ls_b_uid,
            relationship_type=LateralRelationType.RELATED_TO,
            metadata={
                "relationship_type": relationship_type,
                "strength": strength,
                "description": description,
                "domain": "ls",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_complementary_relationship(
        self,
        ls_a_uid: str,
        ls_b_uid: str,
        synergy_description: str,
        learning_benefit: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic steps.

        Args:
            ls_a_uid: First learning step
            ls_b_uid: Second learning step
            synergy_description: How steps complement each other
            learning_benefit: Optional description of combined benefit

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Reading Code" COMPLEMENTARY_TO "Writing Code"
            → Combined practice strengthens both skills
        """
        return await self.lateral_service.create_lateral_relationship(
            source_uid=ls_a_uid,
            target_uid=ls_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "learning_benefit": learning_benefit,
                "domain": "ls",
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_prerequisites(
        self,
        ls_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get learning steps that are prerequisites for this step.

        Args:
            ls_uid: Learning step UID

        Returns:
            Result with list of prerequisite steps
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ls_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="incoming",  # Things that point to this step
            include_metadata=True,
        )

    async def get_dependent_steps(
        self,
        ls_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get learning steps that depend on this step.

        Args:
            ls_uid: Learning step UID

        Returns:
            Result with list of dependent steps
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ls_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="outgoing",  # Things this step points to
            include_metadata=True,
        )

    async def get_alternative_steps(
        self,
        ls_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get alternative learning steps.

        Args:
            ls_uid: Learning step UID

        Returns:
            Result with list of alternative steps
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ls_uid,
            relationship_types=[LateralRelationType.ALTERNATIVE_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_related_steps(
        self,
        ls_uid: str,
        min_strength: float = 0.5,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related learning steps.

        Args:
            ls_uid: Learning step UID
            min_strength: Minimum relationship strength

        Returns:
            Result with list of related steps
        """
        all_related = await self.lateral_service.get_lateral_relationships(
            entity_uid=ls_uid,
            relationship_types=[LateralRelationType.RELATED_TO],
            direction="both",
            include_metadata=True,
        )

        if all_related.is_error:
            return all_related

        # Filter by minimum strength
        filtered = [
            step
            for step in all_related.value
            if step.get("metadata", {}).get("strength", 0) >= min_strength
        ]

        return Result.ok(filtered)

    async def get_complementary_steps(
        self,
        ls_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get complementary learning steps.

        Args:
            ls_uid: Learning step UID

        Returns:
            Result with list of complementary steps
        """
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=ls_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_sibling_steps(
        self,
        ls_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling learning steps (same parent learning path).

        Args:
            ls_uid: Learning step UID

        Returns:
            Result with list of sibling steps
        """
        return await self.lateral_service.get_siblings(
            entity_uid=ls_uid,
            include_explicit_only=False,
        )


__all__ = ["LsLateralService"]
