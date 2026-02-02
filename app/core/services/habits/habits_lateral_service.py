"""
Habits Lateral Service - Domain-Specific Lateral Relationships
===============================================================

Manages lateral relationships specifically for Habits domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for habit relationships.

Common Habit Lateral Relationships:
    - STACKS_WITH: Habit chaining (do B after A)
    - COMPLEMENTARY_TO: Synergistic habits that enhance each other
    - CONFLICTS_WITH: Incompatible habits
    - RELATED_TO: Habits supporting similar goals

Usage:
    habits_lateral = HabitsLateralService(driver, habits_service)

    # Create habit stacking relationship
    await habits_lateral.create_stacking_relationship(
        first_habit_uid="habit_meditate",
        second_habit_uid="habit_exercise",
        trigger="after"
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class HabitsLateralService:
    """
    Domain-specific service for Habit lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - Habit-specific relationship types (stacking, complementary)
    """

    def __init__(
        self,
        driver: Any,
        habits_service: Any,  # HabitsOperations protocol
    ) -> None:
        """
        Initialize habits lateral service.

        Args:
            driver: Neo4j driver
            habits_service: Habits domain service for validation
        """
        self.driver = driver
        self.habits_service = habits_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_stacking_relationship(
        self,
        first_habit_uid: str,
        second_habit_uid: str,
        trigger: str = "after",  # "after", "before", "during"
        strength: float = 0.8,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create STACKS_WITH relationship for habit chaining.

        Habit stacking: link new habit to existing habit via trigger.

        Args:
            first_habit_uid: First habit in sequence
            second_habit_uid: Second habit in sequence
            trigger: When to do second habit ("after", "before", "during")
            strength: How strong the stack (0.0-1.0)
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            Meditate STACKS_WITH Exercise (trigger="after")
            → "After meditating, do exercise"
        """
        if trigger not in {"after", "before", "during"}:
            return Result.fail(Errors.validation('trigger must be "after", "before", or "during"'))

        if not 0.0 <= strength <= 1.0:
            return Result.fail(Errors.validation("strength must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for habit_uid in [first_habit_uid, second_habit_uid]:
                ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        return await self.lateral_service.create_lateral_relationship(
            source_uid=first_habit_uid,
            target_uid=second_habit_uid,
            relationship_type=LateralRelationType.STACKS_WITH,
            metadata={
                "trigger": trigger,
                "strength": strength,
                "domain": "habits",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Directional based on trigger
        )

    async def create_complementary_relationship(
        self,
        habit_a_uid: str,
        habit_b_uid: str,
        synergy_description: str,
        synergy_score: float = 0.7,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic habits.

        Args:
            habit_a_uid: First habit
            habit_b_uid: Second habit
            synergy_description: How habits complement each other
            synergy_score: Strength of synergy (0.0-1.0)
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            Meditation COMPLEMENTARY_TO Exercise
            → "Mindfulness + physical activity = optimal wellness"
        """
        if not 0.0 <= synergy_score <= 1.0:
            return Result.fail(Errors.validation("synergy_score must be between 0.0 and 1.0"))

        # Verify ownership
        if user_uid:
            for habit_uid in [habit_a_uid, habit_b_uid]:
                ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        return await self.lateral_service.create_lateral_relationship(
            source_uid=habit_a_uid,
            target_uid=habit_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "synergy_score": synergy_score,
                "domain": "habits",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def create_conflict_relationship(
        self,
        habit_a_uid: str,
        habit_b_uid: str,
        conflict_type: str,
        severity: str = "moderate",
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create CONFLICTS_WITH relationship for incompatible habits.

        Args:
            habit_a_uid: First habit
            habit_b_uid: Second habit
            conflict_type: Type of conflict (time, energy, approach, etc.)
            severity: "minor", "moderate", or "severe"
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created

        Example:
            "Late Night Coding" CONFLICTS_WITH "Early Morning Workout"
            → Time/energy conflict
        """
        # Verify ownership
        if user_uid:
            for habit_uid in [habit_a_uid, habit_b_uid]:
                ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        return await self.lateral_service.create_lateral_relationship(
            source_uid=habit_a_uid,
            target_uid=habit_b_uid,
            relationship_type=LateralRelationType.CONFLICTS_WITH,
            metadata={
                "conflict_type": conflict_type,
                "severity": severity,
                "domain": "habits",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_habit_stack(
        self,
        habit_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all habits in the stacking chain.

        Args:
            habit_uid: Habit UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of stacked habits
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=habit_uid,
            relationship_types=[LateralRelationType.STACKS_WITH],
            direction="both",
            include_metadata=True,
        )

    async def get_complementary_habits(
        self,
        habit_uid: str,
        min_synergy: float = 0.5,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get habits that complement this habit.

        Args:
            habit_uid: Habit UID
            min_synergy: Minimum synergy score to include
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of complementary habits
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        all_complementary = await self.lateral_service.get_lateral_relationships(
            entity_uid=habit_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

        if all_complementary.is_error:
            return all_complementary

        # Filter by minimum synergy score
        filtered = [
            habit
            for habit in all_complementary.value
            if habit.get("metadata", {}).get("synergy_score", 0) >= min_synergy
        ]

        return Result.ok(filtered)

    async def get_conflicting_habits(
        self,
        habit_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get habits that conflict with this habit.

        Args:
            habit_uid: Habit UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of conflicting habits
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=habit_uid,
            relationship_types=[LateralRelationType.CONFLICTS_WITH],
            direction="both",
            include_metadata=True,
        )

    async def get_sibling_habits(
        self,
        habit_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling habits (same parent habit).

        Args:
            habit_uid: Habit UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of sibling habits
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.habits_service.verify_ownership(habit_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(Errors.not_found(f"Habit {habit_uid} not found or access denied"))

        return await self.lateral_service.get_siblings(
            entity_uid=habit_uid,
            include_explicit_only=False,
        )


__all__ = ["HabitsLateralService"]
