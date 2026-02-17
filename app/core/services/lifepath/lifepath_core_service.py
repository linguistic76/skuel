"""
LifePath Core Service
======================

CRUD operations for Life Path designation management.

This service manages the user's life path designation:
- Setting/updating the designated LP
- Storing vision statements
- Managing the ULTIMATE_PATH relationship

Note: LifePath is NOT a stored entity - it's a designation on an LP.
Vision data is stored on the User node. Alignment scores are stored
on the ULTIMATE_PATH relationship. The designated Ku gets its
ku_type changed from 'learning_path' to 'life_path'.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.ku_enums import AlignmentLevel
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .lifepath_types import LifePathDesignation

if TYPE_CHECKING:
    from core.services.lp_service import LpService
    from core.services.protocols import QueryExecutor

logger = get_logger(__name__)


class LifePathCoreService:
    """
    Core service for Life Path designation management.

    Manages the ULTIMATE_PATH relationship, vision data on the User node,
    and alignment scores on the ULTIMATE_PATH relationship.
    """

    def __init__(
        self,
        executor: QueryExecutor | None = None,
        lp_service: LpService | None = None,
    ) -> None:
        """
        Initialize core service.

        Args:
            executor: Query executor for database operations
            lp_service: LP service for validation
        """
        self.executor = executor
        self.lp_service = lp_service
        logger.info("LifePathCoreService initialized")

    async def get_designation(self, user_uid: str) -> Result[LifePathDesignation | None]:
        """
        Get user's current life path designation.

        Returns None if user hasn't designated a life path yet.
        Reads alignment scores from the ULTIMATE_PATH relationship.

        Args:
            user_uid: User identifier

        Returns:
            Result[LifePathDesignation | None]
        """
        if not self.executor:
            return Result.fail(Errors.system("Executor not available", operation="get_designation"))

        query = """
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[r:ULTIMATE_PATH]->(lp:Ku {ku_type: 'life_path'})
        RETURN u.vision_statement AS vision_statement,
               u.vision_themes AS vision_themes,
               u.vision_captured_at AS vision_captured_at,
               lp.uid AS life_path_uid,
               r.designated_at AS designated_at,
               r.alignment_score AS alignment_score
        """

        try:
            result = await self.executor.execute_query(query, {"user_uid": user_uid})

            if result.is_error:
                logger.error(f"Failed to get designation for {user_uid}: {result.error}")
                return Result.fail(
                    Errors.database("get_designation", f"Failed to get designation: {result.error}")
                )

            if not result.value:
                return Result.ok(None)

            record = result.value[0]

            # User exists but may not have a designation
            vision_statement = record.get("vision_statement") or ""

            if not vision_statement and not record.get("life_path_uid"):
                # No vision or designation yet
                return Result.ok(None)

            designation = LifePathDesignation(
                user_uid=user_uid,
                vision_statement=vision_statement,
                vision_themes=tuple(record.get("vision_themes") or []),
                vision_captured_at=record.get("vision_captured_at"),
                life_path_uid=record.get("life_path_uid"),
                designated_at=record.get("designated_at"),
                alignment_score=record.get("alignment_score") or 0.0,
            )

            return Result.ok(designation)

        except Exception as e:
            logger.error(f"Failed to get designation for {user_uid}: {e}")
            return Result.fail(
                Errors.database("get_designation", f"Failed to get designation: {e}")
            )

    async def save_vision(
        self,
        user_uid: str,
        vision_statement: str,
        vision_themes: list[str],
    ) -> Result[LifePathDesignation]:
        """
        Save user's vision statement and extracted themes.

        This is Step 1 of the vision capture flow.
        Vision is stored on the User node.

        Args:
            user_uid: User identifier
            vision_statement: User's vision in their own words
            vision_themes: Extracted theme keywords

        Returns:
            Result[LifePathDesignation] with updated data
        """
        if not self.executor:
            return Result.fail(Errors.system("Executor not available", operation="save_vision"))

        now = datetime.now()

        query = """
        MATCH (u:User {uid: $user_uid})
        SET u.vision_statement = $vision_statement,
            u.vision_themes = $vision_themes,
            u.vision_captured_at = $captured_at
        RETURN u.uid AS user_uid
        """

        try:
            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": user_uid,
                    "vision_statement": vision_statement,
                    "vision_themes": vision_themes,
                    "captured_at": now.isoformat(),
                },
            )

            if result.is_error:
                logger.error(f"Failed to save vision for {user_uid}: {result.error}")
                return Result.fail(
                    Errors.database("save_vision", f"Failed to save vision: {result.error}")
                )

            if not result.value:
                return Result.fail(Errors.not_found("User", user_uid))

            logger.info(f"Vision saved for user {user_uid}")

            return Result.ok(
                LifePathDesignation(
                    user_uid=user_uid,
                    vision_statement=vision_statement,
                    vision_themes=tuple(vision_themes),
                    vision_captured_at=now,
                )
            )

        except Exception as e:
            logger.error(f"Failed to save vision for {user_uid}: {e}")
            return Result.fail(Errors.database("save_vision", f"Failed to save vision: {e}"))

    async def designate_life_path(
        self,
        user_uid: str,
        life_path_uid: str,
    ) -> Result[LifePathDesignation]:
        """
        Designate a Learning Path as the user's life path.

        Creates the ULTIMATE_PATH relationship and sets the target
        Ku's ku_type from 'learning_path' to 'life_path'.

        Args:
            user_uid: User identifier
            life_path_uid: UID of the LP to designate

        Returns:
            Result[LifePathDesignation] with updated data
        """
        if not self.executor:
            return Result.fail(
                Errors.system("Executor not available", operation="designate_life_path")
            )

        # Validate LP exists
        if self.lp_service:
            lp_result = await self.lp_service.core.get(life_path_uid)
            if lp_result.is_error:
                return Result.fail(Errors.not_found("Learning Path", life_path_uid))

        now = datetime.now()

        # Remove existing ULTIMATE_PATH (if any), revert old LP's ku_type,
        # then create new designation
        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (lp:Ku {uid: $life_path_uid, ku_type: 'learning_path'})

        // Revert previous designation's ku_type back to learning_path
        OPTIONAL MATCH (u)-[old:ULTIMATE_PATH]->(old_lp:Ku {ku_type: 'life_path'})
        SET old_lp.ku_type = 'learning_path'
        DELETE old

        // Create new designation and promote ku_type
        WITH u, lp
        CREATE (u)-[r:ULTIMATE_PATH {designated_at: $designated_at}]->(lp)
        SET lp.ku_type = 'life_path'

        RETURN u.vision_statement AS vision_statement,
               u.vision_themes AS vision_themes,
               u.vision_captured_at AS vision_captured_at,
               lp.uid AS life_path_uid,
               r.designated_at AS designated_at
        """

        try:
            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "designated_at": now.isoformat(),
                },
            )

            if result.is_error:
                return Result.fail(
                    Errors.database(
                        "designate_life_path", f"Failed to designate life path: {result.error}"
                    )
                )

            records = result.value or []
            if not records:
                return Result.fail(Errors.not_found("User or LP", f"{user_uid} or {life_path_uid}"))

            record = records[0]
            logger.info(f"Life path {life_path_uid} designated for user {user_uid}")

            return Result.ok(
                LifePathDesignation(
                    user_uid=user_uid,
                    vision_statement=record.get("vision_statement") or "",
                    vision_themes=tuple(record.get("vision_themes") or []),
                    vision_captured_at=record.get("vision_captured_at"),
                    life_path_uid=life_path_uid,
                    designated_at=now,
                )
            )

        except Exception as e:
            logger.error(f"Failed to designate life path for {user_uid}: {e}")
            return Result.fail(
                Errors.database("designate_life_path", f"Failed to designate life path: {e}")
            )

    async def remove_designation(self, user_uid: str) -> Result[bool]:
        """
        Remove user's life path designation.

        Removes the ULTIMATE_PATH relationship, reverts the Ku's ku_type
        back to 'learning_path', but keeps vision data on the User node.

        Args:
            user_uid: User identifier

        Returns:
            Result[bool] True if removed, False if no designation existed
        """
        if not self.executor:
            return Result.fail(
                Errors.system("Executor not available", operation="remove_designation")
            )

        query = """
        MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->(lp:Ku {ku_type: 'life_path'})
        SET lp.ku_type = 'learning_path'
        DELETE r
        RETURN count(r) > 0 AS removed
        """

        try:
            result = await self.executor.execute_query(query, {"user_uid": user_uid})

            if result.is_error:
                return Result.fail(
                    Errors.database(
                        "remove_designation", f"Failed to remove designation: {result.error}"
                    )
                )

            records = result.value or []
            if records:
                removed = records[0].get("removed", False)
                if removed:
                    logger.info(f"Life path designation removed for user {user_uid}")
                return Result.ok(removed)

            return Result.ok(False)

        except Exception as e:
            logger.error(f"Failed to remove designation for {user_uid}: {e}")
            return Result.fail(
                Errors.database("remove_designation", f"Failed to remove designation: {e}")
            )

    async def update_alignment_score(
        self,
        user_uid: str,
        alignment_score: float,
        dimension_scores: dict[str, float] | None = None,
    ) -> Result[bool]:
        """
        Update life path alignment score on the ULTIMATE_PATH relationship.

        Called by LifePathAlignmentService after calculation.

        Args:
            user_uid: User identifier
            alignment_score: Overall alignment (0.0-1.0)
            dimension_scores: Optional per-dimension scores

        Returns:
            Result[bool] True if updated
        """
        if not self.executor:
            return Result.fail(
                Errors.system("Executor not available", operation="update_alignment_score")
            )

        alignment_level = AlignmentLevel.from_score(alignment_score)

        # Store alignment scores on the ULTIMATE_PATH relationship
        query = """
        MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->(lp:Ku {ku_type: 'life_path'})
        SET r.alignment_score = $alignment_score,
            r.alignment_level = $alignment_level,
            r.alignment_updated_at = datetime()
        """

        params: dict[str, Any] = {
            "user_uid": user_uid,
            "alignment_score": alignment_score,
            "alignment_level": alignment_level.value,
        }

        # Add dimension scores if provided
        if dimension_scores:
            query += """,
            r.knowledge_alignment = $knowledge_alignment,
            r.activity_alignment = $activity_alignment,
            r.goal_alignment = $goal_alignment,
            r.principle_alignment = $principle_alignment,
            r.momentum = $momentum
            """
            params.update(
                {
                    "knowledge_alignment": dimension_scores.get("knowledge", 0.0),
                    "activity_alignment": dimension_scores.get("activity", 0.0),
                    "goal_alignment": dimension_scores.get("goal", 0.0),
                    "principle_alignment": dimension_scores.get("principle", 0.0),
                    "momentum": dimension_scores.get("momentum", 0.0),
                }
            )

        query += "\nRETURN r.alignment_score AS score"

        try:
            result = await self.executor.execute_query(query, params)

            if result.is_error:
                return Result.fail(
                    Errors.database(
                        "update_alignment_score",
                        f"Failed to update alignment score: {result.error}",
                    )
                )

            records = result.value or []
            if records:
                logger.info(
                    f"Alignment score updated for {user_uid}: {alignment_score:.2f} ({alignment_level.value})"
                )
                return Result.ok(True)

            return Result.ok(False)

        except Exception as e:
            logger.error(f"Failed to update alignment score for {user_uid}: {e}")
            return Result.fail(
                Errors.database("update_alignment_score", f"Failed to update alignment score: {e}")
            )
