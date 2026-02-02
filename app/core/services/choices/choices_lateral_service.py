"""
Choices Lateral Service - Domain-Specific Lateral Relationships
================================================================

Manages lateral relationships specifically for Choices domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for choice/decision relationships.

Common Choice Lateral Relationships:
    - ALTERNATIVE_TO: Mutually exclusive options
    - BLOCKS: Choice A prevents Choice B
    - COMPLEMENTARY_TO: Choices that work well together
    - CONFLICTS_WITH: Incompatible choices

Usage:
    choices_lateral = ChoicesLateralService(driver, choices_service)

    # Create alternative relationship
    await choices_lateral.create_alternative_relationship(
        choice_a_uid="choice_career-a_abc",
        choice_b_uid="choice_career-b_xyz",
        comparison_criteria="Different career paths",
        tradeoffs=["Remote vs. On-site", "High-pay vs. Work-life balance"]
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class ChoicesLateralService:
    """
    Domain-specific service for Choice lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - Choice-specific relationship types (alternatives, blocking)
    """

    def __init__(
        self,
        driver: Any,
        choices_service: Any,  # ChoicesOperations protocol
    ) -> None:
        """
        Initialize choices lateral service.

        Args:
            driver: Neo4j driver
            choices_service: Choices domain service for validation
        """
        self.driver = driver
        self.choices_service = choices_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_alternative_relationship(
        self,
        choice_a_uid: str,
        choice_b_uid: str,
        comparison_criteria: str,
        tradeoffs: list[str] | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create ALTERNATIVE_TO relationship for mutually exclusive options.

        Args:
            choice_a_uid: First choice
            choice_b_uid: Second choice
            comparison_criteria: How to compare options
            tradeoffs: List of key tradeoffs between options
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Accept Job A" ALTERNATIVE_TO "Accept Job B"
            → Mutually exclusive career decisions
        """
        # Verify ownership
        if user_uid:
            for choice_uid in [choice_a_uid, choice_b_uid]:
                ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Choice {choice_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=choice_a_uid,
            target_uid=choice_b_uid,
            relationship_type=LateralRelationType.ALTERNATIVE_TO,
            metadata={
                "comparison_criteria": comparison_criteria,
                "tradeoffs": tradeoffs or [],
                "domain": "choices",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_blocking_relationship(
        self,
        blocker_uid: str,
        blocked_uid: str,
        reason: str,
        reversibility: str = "irreversible",
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create BLOCKS relationship (Choice A prevents Choice B).

        Args:
            blocker_uid: Choice that blocks
            blocked_uid: Choice that is blocked
            reason: Why blocker prevents blocked
            reversibility: "irreversible" or "reversible" (can undo blocker)
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Drop Out of College" BLOCKS "Apply for Graduate School"
            → Decision A prevents future option B
        """
        # Verify ownership
        if user_uid:
            for choice_uid in [blocker_uid, blocked_uid]:
                ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Choice {choice_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=blocker_uid,
            target_uid=blocked_uid,
            relationship_type=LateralRelationType.BLOCKS,
            metadata={
                "reason": reason,
                "reversibility": reversibility,
                "domain": "choices",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=True,  # Creates BLOCKED_BY
        )

    async def create_complementary_relationship(
        self,
        choice_a_uid: str,
        choice_b_uid: str,
        synergy_description: str,
        combined_benefit: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic choices.

        Args:
            choice_a_uid: First choice
            choice_b_uid: Second choice
            synergy_description: How choices work together
            combined_benefit: Optional description of combined result
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Learn Python" COMPLEMENTARY_TO "Learn Data Science"
            → Choices that enhance each other
        """
        # Verify ownership
        if user_uid:
            for choice_uid in [choice_a_uid, choice_b_uid]:
                ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Choice {choice_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=choice_a_uid,
            target_uid=choice_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "combined_benefit": combined_benefit,
                "domain": "choices",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_conflict_relationship(
        self,
        choice_a_uid: str,
        choice_b_uid: str,
        conflict_type: str,
        severity: str = "moderate",
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create CONFLICTS_WITH relationship for incompatible choices.

        Args:
            choice_a_uid: First choice
            choice_b_uid: Second choice
            conflict_type: Type of conflict (values, time, resources, approach)
            severity: "minor", "moderate", or "severe"
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Prioritize Family Time" CONFLICTS_WITH "Work 80-hour Weeks"
            → Value conflict
        """
        # Verify ownership
        if user_uid:
            for choice_uid in [choice_a_uid, choice_b_uid]:
                ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(
                        Errors.not_found(f"Choice {choice_uid} not found or access denied")
                    )

        return await self.lateral_service.create_lateral_relationship(
            source_uid=choice_a_uid,
            target_uid=choice_b_uid,
            relationship_type=LateralRelationType.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "severity": severity,
                "domain": "choices",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_alternative_choices(
        self,
        choice_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get alternative choices.

        Args:
            choice_uid: Choice UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of alternative choices
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Choice {choice_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=choice_uid,
            relationship_types=[LateralRelationType.ALTERNATIVE_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_blocking_choices(
        self,
        choice_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get choices that block this choice.

        Args:
            choice_uid: Choice UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of blocking choices
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Choice {choice_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=choice_uid,
            relationship_types=[LateralRelationType.BLOCKS],
            direction="incoming",
            include_metadata=True,
        )

    async def get_blocked_choices(
        self,
        choice_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get choices blocked by this choice.

        Args:
            choice_uid: Choice UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of blocked choices
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Choice {choice_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=choice_uid,
            relationship_types=[LateralRelationType.BLOCKS],
            direction="outgoing",
            include_metadata=True,
        )

    async def get_complementary_choices(
        self,
        choice_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get complementary choices.

        Args:
            choice_uid: Choice UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of complementary choices
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Choice {choice_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=choice_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_conflicting_choices(
        self,
        choice_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get conflicting choices.

        Args:
            choice_uid: Choice UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of conflicting choices
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Choice {choice_uid} not found or access denied")
                )

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=choice_uid,
            relationship_types=[LateralRelationType.CONFLICTS_WITH],
            direction="both",
            include_metadata=True,
        )

    async def get_sibling_choices(
        self,
        choice_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling choices (same parent choice or decision tree).

        Args:
            choice_uid: Choice UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of sibling choices
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.choices_service.verify_ownership(choice_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Choice {choice_uid} not found or access denied")
                )

        return await self.lateral_service.get_siblings(
            entity_uid=choice_uid,
            include_explicit_only=False,
        )


__all__ = ["ChoicesLateralService"]
