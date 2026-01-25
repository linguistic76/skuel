"""
LifePath Service Facade
========================

Domain #14: The Destination - "Everything flows toward the life path"

This facade orchestrates all LifePath operations:
- Vision capture (user's words)
- Designation management (LP selection)
- Alignment calculation (vision→action measurement)
- Intelligence (recommendations)

Philosophy:
    "The user's vision is understood via the words user uses to communicate,
    the UserContext is determined via user's actions."

Sub-services:
- .vision: Capture and analyze user's vision statement
- .core: Designation CRUD operations
- .alignment: Calculate alignment score
- .intelligence: Generate recommendations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.lifepath import (
    WordActionAlignment,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

from .lifepath_alignment_service import LifePathAlignmentService
from .lifepath_core_service import LifePathCoreService
from .lifepath_intelligence_service import LifePathIntelligenceService
from .lifepath_vision_service import LifePathVisionService

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.ku_service import KuService
    from core.services.llm_service import LLMService
    from core.services.lp_service import LpService
    from core.services.user.unified_user_context import UserContext
    from core.services.user_service import UserService

logger = get_logger(__name__)


class LifePathService:
    """
    LifePath Domain Facade - Domain #14: The Destination.

    Answers: "Am I living my life path?"

    This service bridges:
    - User's VISION (expressed in their own words)
    - User's ACTIONS (tracked via UserContext)
    - ALIGNMENT (measured via 5 dimensions)

    Usage:
        # Capture vision
        vision = await lifepath.vision.capture_vision(user_uid, "I want to become...")

        # Get LP recommendations
        recommendations = await lifepath.vision.recommend_learning_paths(vision.themes)

        # Designate life path
        designation = await lifepath.core.designate_life_path(user_uid, lp_uid)

        # Calculate alignment
        alignment = await lifepath.alignment.calculate_alignment(user_uid)

        # Get recommendations
        recs = await lifepath.intelligence.get_recommendations(user_uid, alignment)
    """

    def __init__(
        self,
        driver: AsyncDriver | None = None,
        lp_service: LpService | None = None,
        ku_service: KuService | None = None,
        user_service: UserService | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        """
        Initialize LifePath service with all sub-services.

        Args:
            driver: Neo4j async driver
            lp_service: LP service for path operations
            ku_service: KU service for knowledge operations
            user_service: User service for context
            llm_service: LLM service for vision analysis
        """
        self.driver = driver

        # Sub-services
        self.vision = LifePathVisionService(
            llm_service=llm_service,
            lp_service=lp_service,
        )

        self.core = LifePathCoreService(
            driver=driver,
            lp_service=lp_service,
        )

        self.alignment = LifePathAlignmentService(
            driver=driver,
            lp_service=lp_service,
            ku_service=ku_service,
            user_service=user_service,
        )

        self.intelligence = LifePathIntelligenceService(
            user_service=user_service,
        )

        logger.info("LifePathService facade initialized with 4 sub-services")

    # =========================================================================
    # CONVENIENCE METHODS (delegate to sub-services)
    # =========================================================================

    async def capture_and_recommend(
        self,
        user_uid: str,
        vision_statement: str,
    ) -> Result[dict[str, Any]]:
        """
        Complete vision capture flow: capture → extract themes → recommend LPs.

        This is the main entry point for new users expressing their vision.

        Args:
            user_uid: User identifier
            vision_statement: User's vision in their own words

        Returns:
            Result with vision capture and LP recommendations
        """
        # Step 1: Capture and extract themes
        vision_result = await self.vision.capture_vision(user_uid, vision_statement)
        if vision_result.is_error:
            return Result.fail(vision_result.expect_error())

        vision = vision_result.value

        # Step 2: Save vision to user
        save_result = await self.core.save_vision(
            user_uid=user_uid,
            vision_statement=vision_statement,
            vision_themes=list(vision.theme_keywords),
        )
        if save_result.is_error:
            logger.warning(f"Failed to save vision: {save_result.expect_error()}")
            # Continue anyway - vision was captured

        # Step 3: Get LP recommendations
        recommendations_result = await self.vision.recommend_learning_paths(vision.theme_keywords)

        recommendations = []
        if recommendations_result.is_ok:
            recommendations = [
                {
                    "lp_uid": r.lp_uid,
                    "lp_name": r.lp_name,
                    "match_score": r.match_score,
                    "matching_themes": list(r.matching_themes),
                }
                for r in recommendations_result.value
            ]

        return Result.ok(
            {
                "vision": {
                    "statement": vision.vision_statement,
                    "themes": vision.theme_keywords,
                    "captured_at": vision.captured_at.isoformat(),
                },
                "recommendations": recommendations,
                "next_step": "Select a Learning Path to designate as your life path",
            }
        )

    async def designate_and_calculate(
        self,
        user_uid: str,
        life_path_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Complete designation flow: designate LP → calculate alignment.

        Args:
            user_uid: User identifier
            life_path_uid: LP to designate

        Returns:
            Result with designation and initial alignment
        """
        # Step 1: Designate the life path
        designation_result = await self.core.designate_life_path(user_uid, life_path_uid)
        if designation_result.is_error:
            return Result.fail(designation_result.expect_error())

        designation = designation_result.value

        # Step 2: Calculate initial alignment
        alignment_result = await self.alignment.calculate_alignment(user_uid)

        alignment_data = {}
        if alignment_result.is_ok:
            alignment_data = alignment_result.value

            # Update stored alignment score
            await self.core.update_alignment_score(
                user_uid=user_uid,
                alignment_score=alignment_data.get("alignment_score", 0.0),
                dimension_scores=alignment_data.get("dimensions"),
            )

        # Step 3: Get initial recommendations
        recommendations_result = await self.intelligence.get_recommendations(
            user_uid, alignment_data
        )

        recommendations = []
        if recommendations_result.is_ok:
            recommendations = recommendations_result.value

        return Result.ok(
            {
                "designation": {
                    "life_path_uid": designation.life_path_uid,
                    "designated_at": designation.designated_at.isoformat()
                    if designation.designated_at
                    else None,
                    "vision_statement": designation.vision_statement,
                },
                "alignment": alignment_data,
                "recommendations": recommendations,
            }
        )

    async def get_full_status(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get complete life path status for a user.

        Combines designation, alignment, and recommendations.

        Args:
            user_uid: User identifier

        Returns:
            Result with complete life path status
        """
        # Get designation
        designation_result = await self.core.get_designation(user_uid)
        if designation_result.is_error:
            return Result.fail(designation_result.expect_error())

        designation = designation_result.value

        if not designation:
            return Result.ok(
                {
                    "has_vision": False,
                    "has_designation": False,
                    "alignment": None,
                    "recommendations": await self._get_getting_started_recommendations(),
                    "next_step": "Express your vision to get started",
                }
            )

        # Get alignment
        alignment_data = {}
        if designation.has_designation:
            alignment_result = await self.alignment.calculate_alignment(user_uid)
            if alignment_result.is_ok:
                alignment_data = alignment_result.value

        # Get recommendations
        recommendations = []
        recommendations_result = await self.intelligence.get_recommendations(
            user_uid, alignment_data
        )
        if recommendations_result.is_ok:
            recommendations = recommendations_result.value

        # Get daily focus
        daily_focus = None
        daily_focus_result = await self.intelligence.get_daily_focus(user_uid, alignment_data)
        if daily_focus_result.is_ok:
            daily_focus = daily_focus_result.value

        return Result.ok(
            {
                "has_vision": designation.has_vision,
                "has_designation": designation.has_designation,
                "vision": {
                    "statement": designation.vision_statement,
                    "themes": list(designation.vision_themes),
                    "captured_at": designation.vision_captured_at.isoformat()
                    if designation.vision_captured_at
                    else None,
                }
                if designation.has_vision
                else None,
                "designation": {
                    "life_path_uid": designation.life_path_uid,
                    "designated_at": designation.designated_at.isoformat()
                    if designation.designated_at
                    else None,
                }
                if designation.has_designation
                else None,
                "alignment": alignment_data,
                "recommendations": recommendations,
                "daily_focus": daily_focus,
            }
        )

    async def _get_getting_started_recommendations(self) -> list[dict[str, Any]]:
        """Get recommendations for users without a vision."""
        return [
            {
                "type": "getting_started",
                "priority": "high",
                "title": "Express your vision",
                "description": "Start by expressing your life vision in your own words.",
                "action": "Go to /lifepath/vision to capture your vision",
            },
        ]

    async def check_word_action_alignment(
        self,
        user_uid: str,
        user_context: UserContext,
    ) -> Result[WordActionAlignment]:
        """
        Check alignment between user's stated words and actions.

        This is the core bridge that answers:
        "Are you LIVING what you SAID?"

        Args:
            user_uid: User identifier
            user_context: User's current context

        Returns:
            Result[WordActionAlignment] with gap analysis
        """
        # Get user's vision themes
        designation_result = await self.core.get_designation(user_uid)
        if designation_result.is_error:
            return Result.fail(designation_result.expect_error())

        designation = designation_result.value
        if not designation or not designation.vision_themes:
            return Result.ok(
                WordActionAlignment(
                    user_uid=user_uid,
                    vision_themes=(),
                    action_themes=(),
                    alignment_score=0.0,
                    insights=("No vision captured yet. Express your vision first.",),
                    recommendations=("Go to /lifepath/vision to capture your vision",),
                )
            )

        # Calculate word-action alignment
        return await self.vision.calculate_word_action_alignment(
            list(designation.vision_themes),
            user_context,
        )
