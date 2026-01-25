"""
LifePath Intelligence Service
==============================

Provides intelligent recommendations based on word-action alignment.

This service bridges insights from:
- Vision analysis (what user SAID)
- UserContext (what user DOES)
- Alignment calculation (the gap)

And generates actionable recommendations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.user_service import UserService

logger = get_logger(__name__)


class LifePathIntelligenceService:
    """
    Intelligence service for life path recommendations.

    Generates personalized recommendations based on:
    1. Word-action alignment gaps
    2. Dimension-specific weaknesses
    3. User's current context
    """

    def __init__(
        self,
        user_service: UserService | None = None,
    ) -> None:
        """
        Initialize intelligence service.

        Args:
            user_service: User service for context
        """
        self.user_service = user_service
        logger.info("LifePathIntelligenceService initialized")

    async def get_recommendations(
        self,
        user_uid: str,
        alignment_data: dict[str, Any] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Generate personalized life path recommendations.

        Args:
            user_uid: User identifier
            alignment_data: Optional pre-calculated alignment data

        Returns:
            Result[list[dict]] with prioritized recommendations
        """
        logger.info(f"Generating recommendations for {user_uid}")

        if not alignment_data:
            return Result.ok(self._default_recommendations())

        recommendations = []

        # Analyze each dimension
        dimensions = alignment_data.get("dimensions", {})

        def get_dimension_score(item: tuple[str, float]) -> float:
            return item[1]

        # Priority 1: Lowest dimension
        lowest = min(dimensions.items(), key=get_dimension_score)
        recommendations.append(self._dimension_recommendation(lowest[0], lowest[1]))

        # Priority 2: Any dimension below 0.5
        for dim, score in dimensions.items():
            if score < 0.5 and dim != lowest[0]:
                recommendations.append(self._dimension_recommendation(dim, score))

        # Priority 3: Knowledge gaps
        knowledge_stats = alignment_data.get("knowledge_stats", {})
        if knowledge_stats.get("theoretical", 0) > knowledge_stats.get("embodied", 0):
            recommendations.append(
                {
                    "type": "knowledge_gap",
                    "priority": "medium",
                    "title": "Apply theoretical knowledge",
                    "description": "You have more theoretical knowledge than applied. Create habits or tasks to practice what you've learned.",
                    "action": "Create a habit that applies one of your theoretical knowledge units",
                }
            )

        # Priority 4: Momentum boost
        if dimensions.get("momentum", 0) < 0.5:
            recommendations.append(
                {
                    "type": "momentum",
                    "priority": "high",
                    "title": "Rebuild momentum",
                    "description": "Your activity toward your life path has decreased recently.",
                    "action": "Complete one small task today that aligns with your life path",
                }
            )

        # Ensure at least one recommendation
        if not recommendations:
            recommendations.append(
                {
                    "type": "maintenance",
                    "priority": "low",
                    "title": "Maintain your progress",
                    "description": "You're doing great! Keep up your current activities.",
                    "action": "Continue your daily habits",
                }
            )

        return Result.ok(recommendations)

    def _dimension_recommendation(self, dimension: str, score: float) -> dict[str, Any]:
        """Generate recommendation for a specific dimension."""
        dim_configs = {
            "knowledge": {
                "title": "Strengthen knowledge mastery",
                "description": "Your life path knowledge needs more attention.",
                "actions": [
                    "Study one knowledge unit from your life path today",
                    "Create flashcards for key concepts",
                    "Apply knowledge in a real task",
                ],
            },
            "activity": {
                "title": "Align daily activities",
                "description": "Your tasks and habits could better support your life path.",
                "actions": [
                    "Create a new habit that applies life path knowledge",
                    "Review your task list and add life path context",
                    "Schedule dedicated time for life path activities",
                ],
            },
            "goal": {
                "title": "Set aligned goals",
                "description": "Your goals need stronger connection to your life path.",
                "actions": [
                    "Create a goal that directly serves your life path",
                    "Link existing goals to your life path",
                    "Break down life path into milestone goals",
                ],
            },
            "principle": {
                "title": "Strengthen value alignment",
                "description": "Your principles could better guide your life path.",
                "actions": [
                    "Define a principle that supports your life path",
                    "Review decisions against your principles",
                    "Journal about how principles guide your path",
                ],
            },
            "momentum": {
                "title": "Rebuild activity momentum",
                "description": "Your recent activity toward life path has slowed.",
                "actions": [
                    "Complete one small life path task today",
                    "Check in with your habits daily",
                    "Set a reminder to review life path progress weekly",
                ],
            },
        }

        config = dim_configs.get(dimension, dim_configs["activity"])
        priority = "high" if score < 0.3 else "medium" if score < 0.6 else "low"

        return {
            "type": f"dimension_{dimension}",
            "dimension": dimension,
            "score": round(score, 2),
            "priority": priority,
            "title": config["title"],
            "description": config["description"],
            "actions": config["actions"],
        }

    def _default_recommendations(self) -> list[dict[str, Any]]:
        """Default recommendations when no alignment data available."""
        return [
            {
                "type": "getting_started",
                "priority": "high",
                "title": "Express your vision",
                "description": "Start by expressing your life vision in your own words.",
                "action": "Go to /lifepath/vision to capture your vision",
            },
            {
                "type": "getting_started",
                "priority": "medium",
                "title": "Designate your life path",
                "description": "Choose a Learning Path that embodies your vision.",
                "action": "Browse Learning Paths and select one as your life path",
            },
        ]

    async def get_daily_focus(
        self,
        user_uid: str,
        alignment_data: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Get today's focus area for life path progress.

        Returns a single, actionable focus for the day based on
        current alignment state.

        Args:
            user_uid: User identifier
            alignment_data: Optional pre-calculated alignment data

        Returns:
            Result[dict] with today's focus
        """
        if not alignment_data:
            return Result.ok(
                {
                    "focus": "Express your vision",
                    "reason": "Start by articulating what you want to become",
                    "action": "Write down your life vision in your own words",
                    "dimension": None,
                }
            )

        dimensions = alignment_data.get("dimensions", {})

        # Find the weakest dimension that can be improved today
        actionable_order = ["activity", "momentum", "knowledge", "goal", "principle"]

        for dim in actionable_order:
            score = dimensions.get(dim, 0)
            if score < 0.7:
                focus = self._get_daily_focus_for_dimension(dim, score)
                return Result.ok(focus)

        # All dimensions good - maintenance focus
        return Result.ok(
            {
                "focus": "Maintain your excellent progress",
                "reason": "All dimensions are well-aligned",
                "action": "Continue your daily habits and review your goals",
                "dimension": None,
            }
        )

    def _get_daily_focus_for_dimension(self, dimension: str, score: float) -> dict[str, Any]:
        """Get daily focus action for a specific dimension."""
        focuses = {
            "activity": {
                "focus": "Complete one life-path-aligned task",
                "reason": "Your daily activities need more alignment",
                "action": "Choose a task that applies knowledge from your life path",
            },
            "momentum": {
                "focus": "Take action toward your life path",
                "reason": "Your momentum has dropped recently",
                "action": "Do something small but meaningful for your life path today",
            },
            "knowledge": {
                "focus": "Study and apply one knowledge unit",
                "reason": "Your knowledge mastery needs attention",
                "action": "Spend 15 minutes learning and then apply what you learned",
            },
            "goal": {
                "focus": "Progress on a life-path-aligned goal",
                "reason": "Your goals need better life path connection",
                "action": "Work on a goal that directly serves your life path",
            },
            "principle": {
                "focus": "Make a principle-guided decision",
                "reason": "Your principles need stronger influence",
                "action": "When making decisions today, consult your principles first",
            },
        }

        focus = focuses.get(dimension, focuses["activity"])
        focus["dimension"] = dimension
        focus["current_score"] = round(score, 2)

        return focus
