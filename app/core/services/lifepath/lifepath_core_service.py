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
entity_type changed from 'learning_path' to 'life_path'.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.dto_helpers import parse_datetime_field
from core.models.enums.principle_enums import AlignmentLevel
from core.models.type_hints import UserUID
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .lifepath_types import LifePathDesignation

if TYPE_CHECKING:
    from core.ports.lifepath_protocols import LifePathBackendOperations
    from core.ports.query_types import AlignmentDimensions, LifePathComposition
    from core.services.lp_service import LpService

logger = get_logger(__name__)


class LifePathCoreService:
    """
    Core service for Life Path designation management.

    Manages the ULTIMATE_PATH relationship, vision data on the User node,
    and alignment scores on the ULTIMATE_PATH relationship.
    """

    def __init__(
        self,
        backend: LifePathBackendOperations | None = None,
        lp_service: LpService | None = None,
    ) -> None:
        """
        Initialize core service.

        Args:
            backend: LifePathBackendOperations for database operations
            lp_service: LP service for validation
        """
        self.backend = backend
        self.lp_service = lp_service
        logger.info("LifePathCoreService initialized")

    async def get_designation(self, user_uid: UserUID) -> Result[LifePathDesignation | None]:
        """
        Get user's current life path designation.

        Returns None if user hasn't designated a life path yet.
        Reads alignment scores from the ULTIMATE_PATH relationship.

        Args:
            user_uid: User identifier

        Returns:
            Result[LifePathDesignation | None]
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend not available", operation="get_designation"))

        try:
            result = await self.backend.get_designation(user_uid)

            if result.is_error:
                logger.error(f"Failed to get designation for {user_uid}: {result.error}")
                return Result.fail(
                    Errors.database("get_designation", f"Failed to get designation: {result.error}")
                )

            if not result.value:
                return Result.ok(None)

            record = dict(result.value[0])
            # Timestamps are persisted as ISO strings — coerce them back to
            # datetime so LifePathDesignation consumers can call .isoformat()
            parse_datetime_field(record, "vision_captured_at")
            parse_datetime_field(record, "designated_at")

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

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get designation for {user_uid}: {e}")
            return Result.fail(
                Errors.database("get_designation", f"Failed to get designation: {e}")
            )

    async def save_vision(
        self,
        user_uid: UserUID,
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
        if not self.backend:
            return Result.fail(Errors.system("Backend not available", operation="save_vision"))

        now = datetime.now()

        try:
            result = await self.backend.save_vision(
                user_uid=user_uid,
                vision_statement=vision_statement,
                vision_themes=vision_themes,
                captured_at=now.isoformat(),
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

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to save vision for {user_uid}: {e}")
            return Result.fail(Errors.database("save_vision", f"Failed to save vision: {e}"))

    async def designate_life_path(
        self,
        user_uid: UserUID,
        life_path_uid: str,
    ) -> Result[LifePathDesignation]:
        """
        Designate a Learning Path as the user's life path.

        Creates the ULTIMATE_PATH relationship and sets the target
        Ku's entity_type from 'learning_path' to 'life_path'.

        Args:
            user_uid: User identifier
            life_path_uid: UID of the LP to designate

        Returns:
            Result[LifePathDesignation] with updated data
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="designate_life_path")
            )

        # Validate LP exists
        if self.lp_service:
            lp_result = await self.lp_service.core.get(life_path_uid)
            if lp_result.is_error:
                return Result.fail(Errors.not_found("Learning Path", life_path_uid))

        now = datetime.now()

        try:
            result = await self.backend.designate_life_path(
                user_uid=user_uid,
                life_path_uid=life_path_uid,
                designated_at=now.isoformat(),
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

            record = dict(records[0])
            parse_datetime_field(record, "vision_captured_at")
            # Read the timestamp BACK rather than reporting `now`. Designation
            # is idempotent, so re-designating the current path preserves the
            # date the learner originally committed to it — and reporting `now`
            # would tell the caller the commitment had just been made.
            parse_datetime_field(record, "designated_at")
            logger.info(f"Life path {life_path_uid} designated for user {user_uid}")

            return Result.ok(
                LifePathDesignation(
                    user_uid=user_uid,
                    vision_statement=record.get("vision_statement") or "",
                    vision_themes=tuple(record.get("vision_themes") or []),
                    vision_captured_at=record.get("vision_captured_at"),
                    life_path_uid=life_path_uid,
                    designated_at=record.get("designated_at") or now,
                )
            )

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to designate life path for {user_uid}: {e}")
            return Result.fail(
                Errors.database("designate_life_path", f"Failed to designate life path: {e}")
            )

    async def remove_designation(self, user_uid: UserUID) -> Result[bool]:
        """
        Remove user's life path designation.

        Removes the ULTIMATE_PATH relationship, reverts the Ku's entity_type
        back to 'learning_path', but keeps vision data on the User node.

        STAGED (2026-06-12, bloat campaign 10): no route/UI consumes this yet —
        the forward direction is a "release this path" action on the /lifepath
        dashboard (the 1:1 designation invariant needs an exit door). Collision-
        masked from the bloat detector (the backend call below shares the name),
        so it cannot live in PLANNED_METHODS; this note is the staging record.

        Args:
            user_uid: User identifier

        Returns:
            Result[bool] True if removed, False if no designation existed
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="remove_designation")
            )

        try:
            result = await self.backend.remove_designation(user_uid)

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

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to remove designation for {user_uid}: {e}")
            return Result.fail(
                Errors.database("remove_designation", f"Failed to remove designation: {e}")
            )

    async def update_alignment_score(
        self,
        user_uid: UserUID,
        alignment_score: float,
        dimension_scores: AlignmentDimensions | None = None,
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
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="update_alignment_score")
            )

        alignment_level = AlignmentLevel.from_score(alignment_score)

        params: dict[str, Any] = {
            "user_uid": user_uid,
            "alignment_score": alignment_score,
            "alignment_level": alignment_level.value,
        }

        if dimension_scores:
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
            result = await self.backend.update_alignment_score(params)

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
                snapshot_result = await self.backend.record_alignment_snapshot(
                    user_uid=user_uid, score=alignment_score
                )
                if snapshot_result.is_error:
                    logger.warning(
                        f"Alignment snapshot write failed for {user_uid}: {snapshot_result.error}"
                    )
                return Result.ok(True)

            return Result.ok(False)

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to update alignment score for {user_uid}: {e}")
            return Result.fail(
                Errors.database("update_alignment_score", f"Failed to update alignment score: {e}")
            )

    async def get_alignment_trend_data(
        self, user_uid: UserUID, days: int = 31
    ) -> Result[list[dict[str, Any]]]:
        """
        Get historical alignment snapshots for trend analysis.

        Returns snapshots ordered newest first, covering the given window.
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="get_alignment_trend_data")
            )
        try:
            result = await self.backend.get_alignment_snapshots(user_uid=user_uid, days=days)
            if result.is_error:
                return Result.fail(result)
            return Result.ok(result.value or [])
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get alignment trend data for {user_uid}: {e}")
            return Result.fail(
                Errors.database("get_alignment_trend_data", f"Failed to get snapshots: {e}")
            )

    async def get_life_path_composition(
        self, life_path_uid: str
    ) -> Result[LifePathComposition | None]:
        """What the designated path is made of — its title and ordered steps.

        Not ``LpService.get``, which returns the path alone: this answers the
        path AND its ordered steps in one pass, which is what every caller of it
        actually needs.

        (It was once the only read that WORKED on a designated path: designation
        used to flip ``entity_type`` in place, tripping ``LearningPath``'s
        honest-leaf-identity guard (G6) in the LP service. That mutation is gone
        — designation is the ULTIMATE_PATH edge alone — so the LP read is no
        longer broken, and this method is kept on its own merits.)

        Backend: LifePathBackend.get_life_path_composition — HAS_STEP traversal.
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="get_life_path_composition")
            )
        try:
            return await self.backend.get_life_path_composition(life_path_uid)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get composition for life path {life_path_uid}: {e}")
            return Result.fail(
                Errors.database("get_life_path_composition", f"Failed to get composition: {e}")
            )
