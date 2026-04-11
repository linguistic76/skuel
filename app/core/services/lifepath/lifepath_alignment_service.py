"""
LifePath Alignment Service
===========================

Calculates alignment between user's life path and actual behavior.

This service answers: "Am I living my life path?"

All queries use the Entity model with entity_type discriminator:
- Life path: Entity {entity_type: 'life_path'}
- Learning steps: Entity {entity_type: 'path_step'}
- Knowledge: Entity {entity_type: 'curriculum'}
- Tasks: Entity {entity_type: 'task'}
- Habits: Entity {entity_type: 'habit'}
- Goals: Entity {entity_type: 'goal'}
- Principles: Entity {entity_type: 'principle'}

Core Philosophy: "Everything flows toward the life path"
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from core.models.enums.principle_enums import AlignmentLevel
from core.models.type_hints import UserUID
from core.ports.query_types import LifePathAlignmentResult
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.lifepath_protocols import LifePathBackendOperations
    from core.services.lp_service import LpService
    from core.services.ps_service import PsService
    from core.services.user.unified_user_context import UserContext

logger = get_logger(__name__)


class LifePathAlignmentService:
    """
    Service for calculating life path alignment.

    Measures how well user's actual behavior (tracked in UserContext)
    aligns with their designated life path.

    Alignment Dimensions (5):
    1. Knowledge Alignment (25%): Mastery of life path knowledge
    2. Activity Alignment (25%): Tasks/habits supporting life path
    3. Goal Alignment (20%): Active goals contributing to life path
    4. Principle Alignment (15%): Values supporting life path direction
    5. Momentum (15%): Recent activity trend toward life path
    """

    def __init__(
        self,
        backend: LifePathBackendOperations | None = None,
        lp_service: LpService | None = None,
        ku_service: PsService | None = None,
    ) -> None:
        """
        Initialize alignment service.

        Args:
            backend: LifePathBackendOperations for database operations
            lp_service: LP service for path details
            ku_service: KU service for knowledge substance
        """
        self.backend = backend
        self.lp_service = lp_service
        self.ku_service = ku_service
        logger.info("LifePathAlignmentService initialized")

    async def calculate_alignment(self, context: UserContext) -> Result[LifePathAlignmentResult]:
        """
        Calculate comprehensive life path alignment.

        This is THE most important metric in SKUEL - measures whether
        user is LIVING their life path or just learning about it.

        Args:
            context: Pre-built UserContext for the subject user

        Returns:
            Result containing comprehensive alignment analysis
        """
        user_uid = context.user_uid
        logger.info(f"Calculating life path alignment for user {user_uid}")

        # Get user's life path
        life_path_uid = await self._get_user_life_path(user_uid)
        if not life_path_uid:
            return Result.ok(self._no_designation_response())

        # Get life path details
        lp_details = await self._get_life_path_details(life_path_uid)

        # Calculate each dimension
        knowledge_score = await self._calculate_knowledge_alignment(user_uid, life_path_uid)
        activity_score = await self._calculate_activity_alignment(user_uid, life_path_uid)
        goal_score = await self._calculate_goal_alignment(user_uid, life_path_uid)
        principle_score = await self._calculate_principle_alignment(user_uid, life_path_uid)
        momentum_score = await self._calculate_momentum(user_uid, life_path_uid)

        # Calculate weighted overall score
        overall_score = (
            knowledge_score * 0.25
            + activity_score * 0.25
            + goal_score * 0.20
            + principle_score * 0.15
            + momentum_score * 0.15
        )

        alignment_level = AlignmentLevel.from_score(overall_score)

        # Get knowledge substance stats
        knowledge_stats = await self._get_knowledge_substance_stats(user_uid, life_path_uid)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            knowledge_score=knowledge_score,
            activity_score=activity_score,
            goal_score=goal_score,
            principle_score=principle_score,
            momentum_score=momentum_score,
        )

        result: LifePathAlignmentResult = {
            "life_path_uid": life_path_uid,
            "life_path_title": lp_details.get("title", "Unknown"),
            "alignment_score": round(overall_score, 3),
            "alignment_level": alignment_level.value,
            "dimensions": {
                "knowledge": round(knowledge_score, 3),
                "activity": round(activity_score, 3),
                "goal": round(goal_score, 3),
                "principle": round(principle_score, 3),
                "momentum": round(momentum_score, 3),
            },
            "knowledge_stats": knowledge_stats,
            "recommendations": recommendations,
            "calculated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Alignment calculated for {user_uid}: {overall_score:.2f} ({alignment_level.value})"
        )

        return Result.ok(result)

    async def _get_user_life_path(self, user_uid: UserUID) -> str | None:
        """Get user's designated life path UID."""
        if not self.backend:
            return None

        result = await self.backend.get_user_life_path(user_uid)
        if result.is_error:
            logger.error(
                "Failed to get life path - returning None",
                extra={
                    "user_uid": user_uid,
                    "error_message": str(result.error),
                },
            )
            return None

        records = result.value or []
        if records:
            return records[0].get("life_path_uid")
        return None

    async def _get_life_path_details(self, life_path_uid: str) -> dict[str, str]:
        """Get life path title and metadata."""
        if self.lp_service:
            lp_result = await self.lp_service.core.get(life_path_uid)
            if lp_result.is_ok and lp_result.value:
                return {
                    "title": lp_result.value.title,
                    "description": lp_result.value.description or "",
                }
        return {"title": "Unknown", "description": ""}

    async def _calculate_knowledge_alignment(self, user_uid: UserUID, life_path_uid: str) -> float:
        """
        Calculate knowledge dimension (25% weight).

        Measures mastery of knowledge units in the life path.
        Uses Knowledge Substance Philosophy - applied knowledge > theory.
        """
        if not self.backend:
            return 0.0

        result = await self.backend.calculate_knowledge_alignment(user_uid, life_path_uid)
        if result.is_error:
            logger.error(
                "Knowledge alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("knowledge_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_activity_alignment(self, user_uid: UserUID, life_path_uid: str) -> float:
        """
        Calculate activity dimension (25% weight).

        Measures how tasks and habits support the life path.
        """
        if not self.backend:
            return 0.0

        result = await self.backend.calculate_activity_alignment(user_uid, life_path_uid)
        if result.is_error:
            logger.error(
                "Activity alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("activity_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_goal_alignment(self, user_uid: UserUID, life_path_uid: str) -> float:
        """
        Calculate goal dimension (20% weight).

        Measures if active goals contribute to life path.
        """
        if not self.backend:
            return 0.0

        result = await self.backend.calculate_goal_alignment(user_uid, life_path_uid)
        if result.is_error:
            logger.error(
                "Goal alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("goal_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_principle_alignment(self, user_uid: UserUID, life_path_uid: str) -> float:
        """
        Calculate principle dimension (15% weight).

        Measures if user's principles support the life path direction.
        """
        if not self.backend:
            return 0.0

        result = await self.backend.calculate_principle_alignment(user_uid, life_path_uid)
        if result.is_error:
            logger.error(
                "Principle alignment calculation failed - returning 0.0",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.0

        records = result.value or []
        if records:
            score = records[0].get("principle_alignment")
            return float(score) if score else 0.0
        return 0.0

    async def _calculate_momentum(self, user_uid: UserUID, life_path_uid: str) -> float:
        """
        Calculate momentum dimension (15% weight).

        Measures recent activity trend toward life path.
        Compares last 7 days vs previous 7 days.
        """
        if not self.backend:
            return 0.0

        now = datetime.now()
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)

        result = await self.backend.calculate_momentum(
            user_uid=user_uid,
            life_path_uid=life_path_uid,
            seven_days_ago=seven_days_ago.isoformat(),
            fourteen_days_ago=fourteen_days_ago.isoformat(),
        )
        if result.is_error:
            logger.error(
                "Momentum calculation failed - returning 0.5",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return 0.5

        records = result.value or []
        if records:
            score = records[0].get("momentum")
            return float(score) if score else 0.5
        return 0.5

    async def _get_knowledge_substance_stats(
        self, user_uid: UserUID, life_path_uid: str
    ) -> dict[str, int]:
        """Get counts of embodied vs theoretical knowledge."""
        if not self.backend:
            return {"total": 0, "embodied": 0, "theoretical": 0}

        result = await self.backend.get_knowledge_substance_stats(user_uid, life_path_uid)
        if result.is_error:
            logger.error(
                "Knowledge stats query failed - returning defaults",
                extra={
                    "user_uid": user_uid,
                    "life_path_uid": life_path_uid,
                    "error_message": str(result.error),
                },
            )
            return {"total": 0, "embodied": 0, "theoretical": 0}

        records = result.value or []
        if records:
            r = records[0]
            return {
                "total": int(r.get("total") or 0),
                "embodied": int(r.get("embodied") or 0),
                "theoretical": int(r.get("theoretical") or 0),
            }
        return {"total": 0, "embodied": 0, "theoretical": 0}

    def _generate_recommendations(
        self,
        knowledge_score: float,
        activity_score: float,
        goal_score: float,
        principle_score: float,
        momentum_score: float,
    ) -> list[str]:
        """Generate actionable recommendations based on dimension scores."""
        recommendations = []

        if knowledge_score < 0.5:
            recommendations.append("Focus on mastering the knowledge units in your life path")

        if activity_score < 0.5:
            recommendations.append("Create habits that apply your life path knowledge daily")

        if goal_score < 0.5:
            recommendations.append("Set goals that directly contribute to your life path")

        if principle_score < 0.5:
            recommendations.append(
                "Align your principles more closely with your life path direction"
            )

        if momentum_score < 0.5:
            recommendations.append("Increase your daily activities toward your life path")

        if not recommendations:
            recommendations.append("Great work! Continue your current trajectory")

        return recommendations

    def _no_designation_response(self) -> LifePathAlignmentResult:
        """Response when user hasn't designated a life path."""
        return {
            "life_path_uid": None,
            "alignment_score": 0.0,
            "alignment_level": "undefined",
            "dimensions": {
                "knowledge": 0.0,
                "activity": 0.0,
                "goal": 0.0,
                "principle": 0.0,
                "momentum": 0.0,
            },
            "knowledge_stats": {"total": 0, "embodied": 0, "theoretical": 0},
            "recommendations": [
                "Express your vision to get started!",
                "Use the vision capture to articulate your life goals",
            ],
            "message": "No life path designated. Express your vision to begin.",
        }
