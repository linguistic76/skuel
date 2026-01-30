"""
Goals Lateral Service - Domain-Specific Lateral Relationships
==============================================================

Manages lateral relationships specifically for Goals domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for goal relationships.

Common Goal Lateral Relationships:
    - BLOCKS: Goal A must complete before sibling Goal B
    - ALTERNATIVE_TO: Mutually exclusive career path goals
    - COMPLEMENTARY_TO: Goals that reinforce each other
    - RELATED_TO: Semantically connected goals

Usage:
    goals_lateral = GoalsLateralService(driver, goals_service)

    # Create blocking relationship between sibling goals
    await goals_lateral.create_blocking_relationship(
        blocker_uid="goal_learn_python",
        blocked_uid="goal_build_django_app",
        reason="Must learn Python before building Django app"
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class GoalsLateralService:
    """
    Domain-specific service for Goal lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - Goal-specific relationship types
    """

    def __init__(
        self,
        driver: Any,
        goals_service: Any,  # GoalsOperations protocol
    ) -> None:
        """
        Initialize goals lateral service.

        Args:
            driver: Neo4j driver
            goals_service: Goals domain service for validation
        """
        self.driver = driver
        self.goals_service = goals_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_blocking_relationship(
        self,
        blocker_uid: str,
        blocked_uid: str,
        reason: str,
        severity: str = "required",
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create BLOCKS relationship between two goals.

        Args:
            blocker_uid: Goal that must complete first
            blocked_uid: Goal that is blocked
            reason: Why blocker must complete first
            severity: "required", "recommended", or "suggested"
            user_uid: User creating the relationship (for validation)

        Returns:
            Result[bool]: Success if relationship created

        Validation:
            - Both goals must exist
            - Both goals must belong to user (if user_uid provided)
            - Goals should be siblings or related branches
            - No circular blocking dependencies

        Example:
            ```python
            result = await goals_lateral.create_blocking_relationship(
                blocker_uid="goal_python_basics",
                blocked_uid="goal_advanced_python",
                reason="Must master basics before advanced topics",
                severity="required"
            )
            ```
        """
        # Verify ownership if user_uid provided
        if user_uid:
            for goal_uid in [blocker_uid, blocked_uid]:
                ownership_result = await self.goals_service.verify_ownership(
                    goal_uid, user_uid
                )
                if ownership_result.is_error:
                    return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Create BLOCKS relationship via core service
        return await self.lateral_service.create_lateral_relationship(
            source_uid=blocker_uid,
            target_uid=blocked_uid,
            relationship_type=LateralRelationType.BLOCKS,
            metadata={
                "reason": reason,
                "severity": severity,
                "domain": "goals",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=True,  # Auto-create BLOCKED_BY inverse
        )

    async def create_alternative_relationship(
        self,
        goal_a_uid: str,
        goal_b_uid: str,
        comparison_criteria: str,
        tradeoffs: list[str] | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create ALTERNATIVE_TO relationship (mutually exclusive goals).

        Args:
            goal_a_uid: First goal option
            goal_b_uid: Second goal option
            comparison_criteria: How to compare the alternatives
            tradeoffs: List of tradeoffs between the options
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            ```python
            result = await goals_lateral.create_alternative_relationship(
                goal_a_uid="goal_career_medicine",
                goal_b_uid="goal_career_engineering",
                comparison_criteria="Career path selection",
                tradeoffs=[
                    "Medicine: longer training, direct patient impact",
                    "Engineering: faster career start, broader application"
                ]
            )
            ```
        """
        # Verify ownership
        if user_uid:
            for goal_uid in [goal_a_uid, goal_b_uid]:
                ownership_result = await self.goals_service.verify_ownership(
                    goal_uid, user_uid
                )
                if ownership_result.is_error:
                    return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Create symmetric ALTERNATIVE_TO relationship
        return await self.lateral_service.create_lateral_relationship(
            source_uid=goal_a_uid,
            target_uid=goal_b_uid,
            relationship_type=LateralRelationType.ALTERNATIVE_TO,
            metadata={
                "comparison_criteria": comparison_criteria,
                "tradeoffs": tradeoffs or [],
                "domain": "goals",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric - only need one direction
        )

    async def create_complementary_relationship(
        self,
        goal_a_uid: str,
        goal_b_uid: str,
        synergy_description: str,
        synergy_score: float = 0.7,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship (goals that enhance each other).

        Args:
            goal_a_uid: First goal
            goal_b_uid: Second goal
            synergy_description: How goals complement each other
            synergy_score: Strength of synergy (0.0-1.0)
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            ```python
            result = await goals_lateral.create_complementary_relationship(
                goal_a_uid="goal_improve_public_speaking",
                goal_b_uid="goal_advance_career",
                synergy_description="Public speaking skills directly support career advancement",
                synergy_score=0.85
            )
            ```
        """
        if not 0.0 <= synergy_score <= 1.0:
            return Errors.validation("synergy_score must be between 0.0 and 1.0")

        # Verify ownership
        if user_uid:
            for goal_uid in [goal_a_uid, goal_b_uid]:
                ownership_result = await self.goals_service.verify_ownership(
                    goal_uid, user_uid
                )
                if ownership_result.is_error:
                    return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Create symmetric COMPLEMENTARY_TO relationship
        return await self.lateral_service.create_lateral_relationship(
            source_uid=goal_a_uid,
            target_uid=goal_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "synergy_score": synergy_score,
                "domain": "goals",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_blocking_goals(
        self,
        goal_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get goals that block this goal (prerequisites).

        Args:
            goal_uid: Goal UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of blocking goals

        Example:
            ```python
            result = await goals_lateral.get_blocking_goals("goal_advanced_python")
            # Returns: [{"uid": "goal_python_basics", "reason": "...", ...}]
            ```
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.goals_service.verify_ownership(goal_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Get incoming BLOCKS relationships
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=goal_uid,
            relationship_types=[LateralRelationType.BLOCKS],
            direction="incoming",
            include_metadata=True,
        )

    async def get_blocked_goals(
        self,
        goal_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get goals blocked by this goal (dependents).

        Args:
            goal_uid: Goal UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of blocked goals
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.goals_service.verify_ownership(goal_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Get outgoing BLOCKS relationships
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=goal_uid,
            relationship_types=[LateralRelationType.BLOCKS],
            direction="outgoing",
            include_metadata=True,
        )

    async def get_alternative_goals(
        self,
        goal_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get alternative goals (mutually exclusive options).

        Args:
            goal_uid: Goal UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of alternative goals
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.goals_service.verify_ownership(goal_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Get ALTERNATIVE_TO relationships (symmetric - get both directions)
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=goal_uid,
            relationship_types=[LateralRelationType.ALTERNATIVE_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_sibling_goals(
        self,
        goal_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling goals (same parent goal).

        Args:
            goal_uid: Goal UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of sibling goals (derived from hierarchy)
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.goals_service.verify_ownership(goal_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Get siblings (derived from hierarchy)
        return await self.lateral_service.get_siblings(
            entity_uid=goal_uid,
            include_explicit_only=False,  # Derive from SUBGOAL relationships
        )

    async def delete_blocking_relationship(
        self,
        blocker_uid: str,
        blocked_uid: str,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Delete BLOCKS relationship between goals.

        Args:
            blocker_uid: Blocking goal UID
            blocked_uid: Blocked goal UID
            user_uid: Optional user for ownership verification

        Returns:
            Result[bool]: Success if relationship deleted
        """
        # Verify ownership
        if user_uid:
            for goal_uid in [blocker_uid, blocked_uid]:
                ownership_result = await self.goals_service.verify_ownership(
                    goal_uid, user_uid
                )
                if ownership_result.is_error:
                    return Errors.not_found(f"Goal {goal_uid} not found or access denied")

        # Delete BLOCKS relationship
        return await self.lateral_service.delete_lateral_relationship(
            source_uid=blocker_uid,
            target_uid=blocked_uid,
            relationship_type=LateralRelationType.BLOCKS,
            delete_inverse=True,  # Also delete BLOCKED_BY inverse
        )


__all__ = ["GoalsLateralService"]
