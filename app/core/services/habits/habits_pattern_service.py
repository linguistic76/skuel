"""
Habits Pattern Service
=======================

Atomic Habits pattern recognition with confidence scoring.

Extracts pattern analysis logic from habits_ui.py route handler
into testable service methods with static pattern extractors.

Methods:
- analyze_patterns: Full pattern analysis with ownership check
- _extract_success_patterns: 5 pattern types (static)
- _extract_failure_patterns: 4 pattern types (static)
"""

from dataclasses import dataclass
from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.habits.patterns")


@dataclass(frozen=True)
class PatternAnalysis:
    """Result of Atomic Habits pattern recognition."""

    name: str
    total_completions: int
    success_patterns: list[dict[str, Any]]
    failure_patterns: list[dict[str, Any]]


class HabitsPatternService:
    """
    Atomic Habits pattern recognition service.

    Analyzes habits using the Atomic Habits framework to identify
    success and failure patterns with confidence scoring.
    """

    def __init__(self, habits_core: Any) -> None:
        """Initialize with habits core service for ownership verification."""
        self.habits_core = habits_core

    async def analyze_patterns(self, habit_uid: str, user_uid: str) -> Result[PatternAnalysis]:
        """Full pattern analysis with ownership check."""
        # Ownership verification
        habit_result = await self.habits_core.verify_ownership(habit_uid, user_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        analysis = habit.get_atomic_habits_analysis()

        success_patterns = self._extract_success_patterns(analysis)
        failure_patterns = self._extract_failure_patterns(analysis)

        return Result.ok(
            PatternAnalysis(
                name=habit.title,
                total_completions=analysis["habit_quality"]["total_completions"],
                success_patterns=success_patterns,
                failure_patterns=failure_patterns,
            )
        )

    @staticmethod
    def _extract_success_patterns(analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract success patterns from Atomic Habits analysis."""
        patterns: list[dict[str, Any]] = []

        # Pattern 1: Identity-based success
        identity = analysis["identity"]
        if identity["is_identity_based"] and identity["identity_strength"] > 0.5:
            patterns.append(
                {
                    "pattern": f"Identity reinforcement: '{identity['reinforces_identity']}'",
                    "confidence": identity["identity_strength"],
                    "recommendation": (
                        f"Keep reinforcing this identity - "
                        f"{identity['votes_to_establishment']} more completions to full establishment"
                    ),
                }
            )

        # Pattern 2: Behavioral design completeness
        design_score = analysis["behavioral_design"]["design_completeness"]
        if design_score >= 0.66:
            patterns.append(
                {
                    "pattern": f"Strong habit design ({int(design_score * 100)}% complete)",
                    "confidence": design_score,
                    "recommendation": "Clear cue-routine-reward loop is working",
                }
            )

        # Pattern 3: Streak momentum
        quality = analysis["habit_quality"]
        if quality["is_on_streak"] and quality["current_streak"] > 3:
            streak_confidence = min(0.9, 0.5 + (quality["current_streak"] / 30))
            patterns.append(
                {
                    "pattern": f"Momentum building: {quality['current_streak']}-day streak",
                    "confidence": streak_confidence,
                    "recommendation": "Momentum matters - maintain the streak!",
                }
            )

        # Pattern 4: Success rate
        if quality["success_rate"] > 0.6:
            patterns.append(
                {
                    "pattern": f"High success rate: {int(quality['success_rate'] * 100)}%",
                    "confidence": quality["success_rate"],
                    "recommendation": "Current approach is working - keep it up",
                }
            )

        # Pattern 5: System integration
        system = analysis["system_contribution"]
        if system["part_of_system"]:
            patterns.append(
                {
                    "pattern": f"Part of goal system ({system['supports_goal_count']} goals)",
                    "confidence": system["consistency_score"],
                    "recommendation": "Systems-based approach is effective",
                }
            )

        return patterns

    @staticmethod
    def _extract_failure_patterns(analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract failure patterns from Atomic Habits analysis."""
        patterns: list[dict[str, Any]] = []
        quality = analysis["habit_quality"]
        design = analysis["behavioral_design"]

        # Failure 1: Low success rate
        if quality["success_rate"] < 0.5:
            patterns.append(
                {
                    "pattern": f"Low success rate: {int(quality['success_rate'] * 100)}%",
                    "confidence": 1.0 - quality["success_rate"],
                    "recommendation": "Consider making habit easier or more rewarding",
                }
            )

        # Failure 2: Broken streak
        if not quality["is_on_streak"] and quality["best_streak"] > 0:
            patterns.append(
                {
                    "pattern": f"Streak broken (previous best: {quality['best_streak']} days)",
                    "confidence": 0.75,
                    "recommendation": f"Rebuild streak - you've achieved {quality['best_streak']} days before",
                }
            )

        # Failure 3: Incomplete design
        design_score = design["design_completeness"]
        if design_score < 0.66:
            missing_elements = []
            if not design["has_cue"]:
                missing_elements.append("cue")
            if not design["has_reward"]:
                missing_elements.append("reward")

            if missing_elements:
                patterns.append(
                    {
                        "pattern": f"Incomplete habit design (missing: {', '.join(missing_elements)})",
                        "confidence": 1.0 - design_score,
                        "recommendation": f"Define clear {missing_elements[0]} to strengthen habit loop",
                    }
                )

        # Failure 4: No goal system
        if not analysis["system_contribution"]["part_of_system"]:
            patterns.append(
                {
                    "pattern": "Habit not linked to goals (no systems thinking)",
                    "confidence": 0.70,
                    "recommendation": "Link this habit to a goal to create a system",
                }
            )

        return patterns
