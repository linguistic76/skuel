"""
Tasks Lateral Service - Domain-Specific Lateral Relationships
==============================================================

Manages lateral relationships specifically for Tasks domain.

This service wraps the core LateralRelationshipService with domain-specific
logic, validation, and business rules for task relationships.

Common Task Lateral Relationships:
    - BLOCKS: Task A must complete before Task B (hard dependency)
    - PREREQUISITE_FOR: Task A recommended before Task B (soft dependency)
    - ALTERNATIVE_TO: Different implementation approaches
    - RELATED_TO: Tasks working toward similar goals

Usage:
    tasks_lateral = TasksLateralService(driver, tasks_service)

    # Create blocking relationship between tasks
    await tasks_lateral.create_blocking_relationship(
        blocker_uid="task_setup_env",
        blocked_uid="task_deploy",
        reason="Must setup environment before deployment"
    )

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class TasksLateralService:
    """
    Domain-specific service for Task lateral relationships.

    Delegates to core LateralRelationshipService while adding:
    - Domain-specific validation
    - Business rules enforcement
    - Convenient wrapper methods
    - Task-specific relationship types
    """

    def __init__(
        self,
        driver: Any,
        tasks_service: Any,  # TasksOperations protocol
    ) -> None:
        """
        Initialize tasks lateral service.

        Args:
            driver: Neo4j driver
            tasks_service: Tasks domain service for validation
        """
        self.driver = driver
        self.tasks_service = tasks_service
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
        Create BLOCKS relationship between two tasks (hard dependency).

        Args:
            blocker_uid: Task that must complete first
            blocked_uid: Task that is blocked
            reason: Why blocker must complete first
            severity: "required", "recommended", or "suggested"
            user_uid: User creating the relationship (for validation)

        Returns:
            Result[bool]: Success if relationship created
        """
        # Verify ownership if user_uid provided
        if user_uid:
            for task_uid in [blocker_uid, blocked_uid]:
                ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
                if ownership_result.is_error:
                    return Errors.not_found(f"Task {task_uid} not found or access denied")

        # Create BLOCKS relationship via core service
        return await self.lateral_service.create_lateral_relationship(
            source_uid=blocker_uid,
            target_uid=blocked_uid,
            relationship_type=LateralRelationType.BLOCKS,
            metadata={
                "reason": reason,
                "severity": severity,
                "domain": "tasks",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=True,  # Auto-create BLOCKED_BY inverse
        )

    async def create_prerequisite_relationship(
        self,
        prerequisite_uid: str,
        dependent_uid: str,
        strength: float = 0.8,
        topic_area: str | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create PREREQUISITE_FOR relationship (soft dependency).

        Use this for recommended ordering rather than hard blocking.

        Args:
            prerequisite_uid: Task recommended to complete first
            dependent_uid: Task that benefits from prerequisite
            strength: How strongly recommended (0.0-1.0)
            topic_area: Optional categorization
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created
        """
        if not 0.0 <= strength <= 1.0:
            return Errors.validation("strength must be between 0.0 and 1.0")

        # Verify ownership
        if user_uid:
            for task_uid in [prerequisite_uid, dependent_uid]:
                ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
                if ownership_result.is_error:
                    return Errors.not_found(f"Task {task_uid} not found or access denied")

        return await self.lateral_service.create_lateral_relationship(
            source_uid=prerequisite_uid,
            target_uid=dependent_uid,
            relationship_type=LateralRelationType.PREREQUISITE_FOR,
            metadata={
                "strength": strength,
                "topic_area": topic_area,
                "domain": "tasks",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=True,
        )

    async def create_alternative_relationship(
        self,
        task_a_uid: str,
        task_b_uid: str,
        comparison_criteria: str,
        tradeoffs: list[str] | None = None,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create ALTERNATIVE_TO relationship (different implementation approaches).

        Args:
            task_a_uid: First task option
            task_b_uid: Second task option
            comparison_criteria: How to compare the alternatives
            tradeoffs: List of tradeoffs between approaches
            user_uid: User creating the relationship

        Returns:
            Result[bool]: Success if relationship created
        """
        # Verify ownership
        if user_uid:
            for task_uid in [task_a_uid, task_b_uid]:
                ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
                if ownership_result.is_error:
                    return Errors.not_found(f"Task {task_uid} not found or access denied")

        return await self.lateral_service.create_lateral_relationship(
            source_uid=task_a_uid,
            target_uid=task_b_uid,
            relationship_type=LateralRelationType.ALTERNATIVE_TO,
            metadata={
                "comparison_criteria": comparison_criteria,
                "tradeoffs": tradeoffs or [],
                "domain": "tasks",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_blocking_tasks(
        self,
        task_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get tasks that block this task (prerequisites).

        Args:
            task_uid: Task UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of blocking tasks
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Task {task_uid} not found or access denied")

        # Get incoming BLOCKS relationships
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=task_uid,
            relationship_types=[LateralRelationType.BLOCKS],
            direction="incoming",
            include_metadata=True,
        )

    async def get_blocked_tasks(
        self,
        task_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get tasks blocked by this task (dependents).

        Args:
            task_uid: Task UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of blocked tasks
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Task {task_uid} not found or access denied")

        # Get outgoing BLOCKS relationships
        return await self.lateral_service.get_lateral_relationships(
            entity_uid=task_uid,
            relationship_types=[LateralRelationType.BLOCKS],
            direction="outgoing",
            include_metadata=True,
        )

    async def get_alternative_tasks(
        self,
        task_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get alternative task implementations.

        Args:
            task_uid: Task UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of alternative tasks
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Task {task_uid} not found or access denied")

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=task_uid,
            relationship_types=[LateralRelationType.ALTERNATIVE_TO],
            direction="both",
            include_metadata=True,
        )

    async def get_sibling_tasks(
        self,
        task_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling tasks (same parent task or goal).

        Args:
            task_uid: Task UID
            user_uid: Optional user for ownership verification

        Returns:
            Result with list of sibling tasks
        """
        # Verify ownership
        if user_uid:
            ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
            if ownership_result.is_error:
                return Errors.not_found(f"Task {task_uid} not found or access denied")

        return await self.lateral_service.get_siblings(
            entity_uid=task_uid,
            include_explicit_only=False,
        )

    async def delete_blocking_relationship(
        self,
        blocker_uid: str,
        blocked_uid: str,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Delete BLOCKS relationship between tasks.

        Args:
            blocker_uid: Blocking task UID
            blocked_uid: Blocked task UID
            user_uid: Optional user for ownership verification

        Returns:
            Result[bool]: Success if relationship deleted
        """
        # Verify ownership
        if user_uid:
            for task_uid in [blocker_uid, blocked_uid]:
                ownership_result = await self.tasks_service.verify_ownership(task_uid, user_uid)
                if ownership_result.is_error:
                    return Errors.not_found(f"Task {task_uid} not found or access denied")

        return await self.lateral_service.delete_lateral_relationship(
            source_uid=blocker_uid,
            target_uid=blocked_uid,
            relationship_type=LateralRelationType.BLOCKS,
            delete_inverse=True,
        )


__all__ = ["TasksLateralService"]
