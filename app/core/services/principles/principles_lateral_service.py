"""
Principles Lateral Service - Domain-Specific Lateral Relationships
===================================================================

Manages lateral relationships specifically for Principles domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for principle/value relationships.

Common Principle Lateral Relationships:
    - RELATED_TO: Principles that reinforce each other
    - COMPLEMENTARY_TO: Principles that work together
    - CONFLICTS_WITH: Contradictory principles (value tensions)
    - PREREQUISITE_FOR: Foundation principle for higher principle

Usage:
    principles_lateral = PrinciplesLateralService(driver, principles_service)

    # Create complementary relationship
    await principles_lateral.create_complementary_relationship(
        principle_a_uid="principle_honesty_abc",
        principle_b_uid="principle_transparency_xyz",
        synergy_description="Both build trust through openness",
        value_alignment=0.9
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class PrinciplesLateralService:
    """
    Domain-specific service for Principle lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - Principle-specific relationship types (value alignment, conflicts)
    """

    def __init__(
        self,
        driver: Any,
        principles_service: Any,  # PrinciplesOperations protocol
    ) -> None:
        """
        Initialize principles lateral service.

        Args:
            driver: Neo4j driver
            principles_service: Principles domain service for validation
        """
        self.driver = driver
        self.principles_service = principles_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_related_relationship(
        self,
        principle_a_uid: str,
        principle_b_uid: str,
        relationship_type: str,
        strength: float = 0.8,
        description: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create RELATED_TO relationship for principles that reinforce each other.

        Args:
            principle_a_uid: First principle
            principle_b_uid: Second principle
            relationship_type: Type of relationship (e.g., "mutual_support", "shared_foundation")
            strength: Strength of relation (0.0-1.0)
            description: Optional description
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Integrity" RELATED_TO "Authenticity"
            → Both involve being true to oneself
        """
        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for principle_uid in [principle_a_uid, principle_b_uid]:
                ownership_result = await self.principles_service.verify_ownership(
                    principle_uid, user_uid
                )
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Principle {principle_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=principle_a_uid,
            target_uid=principle_b_uid,
            relationship_type=LateralRelationType.RELATED_TO,
            metadata={
                "relationship_type": relationship_type,
                "strength": strength,
                "description": description,
                "domain": "principles",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_complementary_relationship(
        self,
        principle_a_uid: str,
        principle_b_uid: str,
        synergy_description: str,
        value_alignment: float = 0.85,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic principles.

        Args:
            principle_a_uid: First principle
            principle_b_uid: Second principle
            synergy_description: How principles complement each other
            value_alignment: How aligned values are (0.0-1.0)
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Courage" COMPLEMENTARY_TO "Compassion"
            → Courage without compassion is recklessness, compassion without courage is enabling
        """
        if not 0.0 <= value_alignment <= 1.0:
            return Result.fail(Errors.validation("value_alignment must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for principle_uid in [principle_a_uid, principle_b_uid]:
                ownership_result = await self.principles_service.verify_ownership(
                    principle_uid, user_uid
                )
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Principle {principle_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=principle_a_uid,
            target_uid=principle_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "value_alignment": value_alignment,
                "domain": "principles",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_conflict_relationship(
        self,
        principle_a_uid: str,
        principle_b_uid: str,
        conflict_type: str,
        tension_description: str,
        severity: str = "moderate",
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create CONFLICTS_WITH relationship for contradictory principles.

        Args:
            principle_a_uid: First principle
            principle_b_uid: Second principle
            conflict_type: Type of conflict (e.g., "value_tension", "priority_conflict")
            tension_description: Description of the tension
            severity: "minor", "moderate", or "severe"
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Individual Freedom" CONFLICTS_WITH "Collective Responsibility"
            → Classic value tension requiring balance
        """
        # Verify ownership
        if user_uid:
            for principle_uid in [principle_a_uid, principle_b_uid]:
                ownership_result = await self.principles_service.verify_ownership(
                    principle_uid, user_uid
                )
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Principle {principle_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=principle_a_uid,
            target_uid=principle_b_uid,
            relationship_type=LateralRelationType.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "tension_description": tension_description,
                "severity": severity,
                "domain": "principles",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_prerequisite_relationship(
        self,
        prerequisite_uid: str,
        dependent_uid: str,
        strength: float = 0.8,
        reasoning: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create PREREQUISITE_FOR relationship for foundational principles.

        Args:
            prerequisite_uid: Foundation principle
            dependent_uid: Higher principle that builds on foundation
            strength: How essential foundation is (0.0-1.0)
            reasoning: Optional explanation
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Self-Awareness" PREREQUISITE_FOR "Self-Discipline"
            → Must understand yourself before you can discipline yourself
        """
        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for principle_uid in [prerequisite_uid, dependent_uid]:
                ownership_result = await self.principles_service.verify_ownership(
                    principle_uid, user_uid
                )
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Principle {principle_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=prerequisite_uid,
            target_uid=dependent_uid,
            relationship_type=LateralRelationType.PREREQUISITE_FOR,
            metadata={
                "strength": strength,
                "reasoning": reasoning,
                "domain": "principles",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=True,  # Creates REQUIRES_PREREQUISITE
        )

    async def get_related_principles(
        self,
        principle_uid: str,
        min_strength: float = 0.5,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related principles.

        Args:
            principle_uid: Principle UID
            min_strength: Minimum relationship strength
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of related principles
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.principles_service.verify_ownership(
                principle_uid, user_uid
            )
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Principle {principle_uid} not found or access denied")
                )

        all_related = await self.lateral_service.get_lateral_relationships(
            entity_uid=principle_uid,
            relationship_types=[LateralRelationType.RELATED_TO],
            direction="both",
            include_metadata=True,
        )

        if all_related.is_error:
            return all_related

        # Filter by minimum strength
        filtered = [
            principle
            for principle in all_related.value
            if principle.get("metadata", {}).get("strength", 0) >= min_strength
        ]

        return Result.ok(filtered)

    async def get_complementary_principles(
        self,
        principle_uid: str,
        min_alignment: float = 0.7,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get complementary principles.

        Args:
            principle_uid: Principle UID
            min_alignment: Minimum value alignment
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of complementary principles
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.principles_service.verify_ownership(
                principle_uid, user_uid
            )
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Principle {principle_uid} not found or access denied")
                )

        all_complementary = await self.lateral_service.get_lateral_relationships(
            entity_uid=principle_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

        if all_complementary.is_error:
            return all_complementary

        # Filter by minimum alignment
        filtered = [
            principle
            for principle in all_complementary.value
            if principle.get("metadata", {}).get("value_alignment", 0) >= min_alignment
        ]

        return Result.ok(filtered)

    async def get_conflicting_principles(
        self,
        principle_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get conflicting principles (value tensions).

        Args:
            principle_uid: Principle UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of conflicting principles
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.principles_service.verify_ownership(
                principle_uid, user_uid
            )
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Principle {principle_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=principle_uid,
            relationship_types=[LateralRelationType.CONFLICTS_WITH],
            direction="both",
            include_metadata=True,
        )

    async def get_prerequisite_principles(
        self,
        principle_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get foundational principles for this principle.

        Args:
            principle_uid: Principle UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of prerequisite principles
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.principles_service.verify_ownership(
                principle_uid, user_uid
            )
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Principle {principle_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=principle_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="incoming",
            include_metadata=True,
        )

    async def get_dependent_principles(
        self,
        principle_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get principles that build on this principle.

        Args:
            principle_uid: Principle UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of dependent principles
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.principles_service.verify_ownership(
                principle_uid, user_uid
            )
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Principle {principle_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=principle_uid,
            relationship_types=[LateralRelationType.PREREQUISITE_FOR],
            direction="outgoing",
            include_metadata=True,
        )

    async def get_sibling_principles(
        self,
        principle_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling principles (same parent principle or value system).

        Args:
            principle_uid: Principle UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of sibling principles
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.principles_service.verify_ownership(
                principle_uid, user_uid
            )
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Principle {principle_uid} not found or access denied")
                )

        return await self.lateral_service.get_siblings(
            entity_uid=principle_uid,
            include_explicit_only=False,
        )


__all__ = ["PrinciplesLateralService"]
