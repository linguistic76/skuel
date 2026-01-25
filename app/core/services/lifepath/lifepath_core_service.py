"""
LifePath Core Service
======================

CRUD operations for Life Path designation management.

This service manages the user's life path designation:
- Setting/updating the designated LP
- Storing vision statements
- Managing the ULTIMATE_PATH relationship

Note: LifePath is NOT a stored entity - it's a designation on an LP.
The data is stored on the User node and via ULTIMATE_PATH relationship.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.lifepath import (
    AlignmentLevel,
    LifePathDesignation,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.lp_service import LpService

logger = get_logger(__name__)


class LifePathCoreService:
    """
    Core service for Life Path designation management.

    Manages the ULTIMATE_PATH relationship and vision data
    stored on the User node.
    """

    def __init__(
        self,
        driver: AsyncDriver | None = None,
        lp_service: LpService | None = None,
    ) -> None:
        """
        Initialize core service.

        Args:
            driver: Neo4j async driver
            lp_service: LP service for validation
        """
        self.driver = driver
        self.lp_service = lp_service
        logger.info("LifePathCoreService initialized")

    async def get_designation(self, user_uid: str) -> Result[LifePathDesignation | None]:
        """
        Get user's current life path designation.

        Returns None if user hasn't designated a life path yet.

        Args:
            user_uid: User identifier

        Returns:
            Result[LifePathDesignation | None]
        """
        if not self.driver:
            return Result.fail(Errors.system("Driver not available", operation="get_designation"))

        query = """
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[r:ULTIMATE_PATH]->(lp:Lp)
        RETURN u.vision_statement AS vision_statement,
               u.vision_themes AS vision_themes,
               u.vision_captured_at AS vision_captured_at,
               lp.uid AS life_path_uid,
               r.designated_at AS designated_at,
               u.life_path_alignment_score AS alignment_score
        """

        try:
            result = await self.driver.execute_query(
                query, {"user_uid": user_uid}, database_="neo4j"
            )

            if not result.records:
                return Result.ok(None)

            record = result.records[0]

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
        if not self.driver:
            return Result.fail(Errors.system("Driver not available", operation="save_vision"))

        now = datetime.now()

        query = """
        MATCH (u:User {uid: $user_uid})
        SET u.vision_statement = $vision_statement,
            u.vision_themes = $vision_themes,
            u.vision_captured_at = $captured_at
        RETURN u.uid AS user_uid
        """

        try:
            result = await self.driver.execute_query(
                query,
                {
                    "user_uid": user_uid,
                    "vision_statement": vision_statement,
                    "vision_themes": vision_themes,
                    "captured_at": now.isoformat(),
                },
                database_="neo4j",
            )

            if not result.records:
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

        Creates the ULTIMATE_PATH relationship.
        This is Step 2 of the vision capture flow.

        Args:
            user_uid: User identifier
            life_path_uid: UID of the LP to designate

        Returns:
            Result[LifePathDesignation] with updated data
        """
        if not self.driver:
            return Result.fail(
                Errors.system("Driver not available", operation="designate_life_path")
            )

        # Validate LP exists
        if self.lp_service:
            lp_result = await self.lp_service.core.get(life_path_uid)
            if lp_result.is_error:
                return Result.fail(Errors.not_found("Learning Path", life_path_uid))

        now = datetime.now()

        # Remove existing ULTIMATE_PATH (if any) and create new one
        query = """
        MATCH (u:User {uid: $user_uid})
        MATCH (lp:Lp {uid: $life_path_uid})

        // Remove existing designation
        OPTIONAL MATCH (u)-[old:ULTIMATE_PATH]->()
        DELETE old

        // Create new designation
        CREATE (u)-[r:ULTIMATE_PATH {designated_at: $designated_at}]->(lp)

        // Update user's life_path_uid for quick access
        SET u.life_path_uid = $life_path_uid

        RETURN u.vision_statement AS vision_statement,
               u.vision_themes AS vision_themes,
               u.vision_captured_at AS vision_captured_at,
               lp.uid AS life_path_uid,
               r.designated_at AS designated_at
        """

        try:
            result = await self.driver.execute_query(
                query,
                {
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "designated_at": now.isoformat(),
                },
                database_="neo4j",
            )

            if not result.records:
                return Result.fail(Errors.not_found("User or LP", f"{user_uid} or {life_path_uid}"))

            record = result.records[0]
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

        Removes the ULTIMATE_PATH relationship but keeps vision data.

        Args:
            user_uid: User identifier

        Returns:
            Result[bool] True if removed, False if no designation existed
        """
        if not self.driver:
            return Result.fail(
                Errors.system("Driver not available", operation="remove_designation")
            )

        query = """
        MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->()
        DELETE r
        SET u.life_path_uid = null
        RETURN count(r) > 0 AS removed
        """

        try:
            result = await self.driver.execute_query(
                query, {"user_uid": user_uid}, database_="neo4j"
            )

            if result.records:
                removed = result.records[0].get("removed", False)
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
        Update user's life path alignment score.

        Called by LifePathAlignmentService after calculation.

        Args:
            user_uid: User identifier
            alignment_score: Overall alignment (0.0-1.0)
            dimension_scores: Optional per-dimension scores

        Returns:
            Result[bool] True if updated
        """
        if not self.driver:
            return Result.fail(
                Errors.system("Driver not available", operation="update_alignment_score")
            )

        alignment_level = AlignmentLevel.from_score(alignment_score)

        query = """
        MATCH (u:User {uid: $user_uid})
        SET u.life_path_alignment_score = $alignment_score,
            u.life_path_alignment_level = $alignment_level,
            u.life_path_alignment_updated_at = datetime()
        RETURN u.uid AS uid
        """

        params: dict[str, Any] = {
            "user_uid": user_uid,
            "alignment_score": alignment_score,
            "alignment_level": alignment_level.value,
        }

        # Add dimension scores if provided
        if dimension_scores:
            query = query.replace(
                "u.life_path_alignment_updated_at = datetime()",
                """u.life_path_alignment_updated_at = datetime(),
                   u.knowledge_alignment = $knowledge_alignment,
                   u.activity_alignment = $activity_alignment,
                   u.goal_alignment = $goal_alignment,
                   u.principle_alignment = $principle_alignment,
                   u.momentum = $momentum""",
            )
            params.update(
                {
                    "knowledge_alignment": dimension_scores.get("knowledge", 0.0),
                    "activity_alignment": dimension_scores.get("activity", 0.0),
                    "goal_alignment": dimension_scores.get("goal", 0.0),
                    "principle_alignment": dimension_scores.get("principle", 0.0),
                    "momentum": dimension_scores.get("momentum", 0.0),
                }
            )

        try:
            result = await self.driver.execute_query(query, params, database_="neo4j")

            if result.records:
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
