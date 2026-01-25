"""
State Scoring - Pure Functions for State Analysis
==================================================

Pure functions for scoring user state and analyzing blockers.
Extracted to eliminate circular dependency between UserStateAnalyzer and ActionRecommendationEngine.

These functions operate on UserContext without any service dependencies,
enabling both services to use them without depending on each other.

Architecture:
- All functions are pure (no side effects, no service dependencies)
- Input: UserContext dataclass
- Output: Simple types (float, str, None, dict)

January 2026: Created as part of Askesis design improvement.
"""

from __future__ import annotations

from operator import itemgetter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.user import UserContext


def score_current_state(user_context: UserContext) -> float:
    """
    Score the current state quality.

    Uses positive and negative factors to calculate a state quality score.

    Positive factors:
    - Not blocked: +0.1
    - Workload under 70%: +0.1
    - No at-risk habits: +0.2

    Negative factors:
    - Has overdue items: -0.2
    - More than 5 blocked tasks: -0.1

    Args:
        user_context: User context to analyze

    Returns:
        State quality score (0.0 to 1.0)
    """
    score = 0.5  # Neutral baseline

    # Positive factors
    if not user_context.is_blocked:
        score += 0.1
    if user_context.current_workload_score < 0.7:
        score += 0.1
    if len(user_context.at_risk_habits) == 0:
        score += 0.2

    # Negative factors
    if user_context.has_overdue_items:
        score -= 0.2
    if len(user_context.blocked_task_uids) > 5:
        score -= 0.1

    return max(0.0, min(1.0, score))


def find_key_blocker(user_context: UserContext) -> str | None:
    """
    Find the key blocking prerequisite.

    Identifies the prerequisite that blocks the most items.
    This is useful for prioritizing what to learn next to maximize unblocking.

    Args:
        user_context: User context to analyze

    Returns:
        UID of key blocker (prerequisite that blocks the most items), or None if no blockers
    """
    if not user_context.prerequisites_needed:
        return None

    # Count how many items each prerequisite blocks
    blocker_counts: dict[str, int] = {}
    for prereqs in user_context.prerequisites_needed.values():
        for prereq in prereqs:
            blocker_counts[prereq] = blocker_counts.get(prereq, 0) + 1

    # Return the prerequisite that blocks the most items
    if blocker_counts:
        return max(blocker_counts.items(), key=itemgetter(1))[0]
    return None


def calculate_momentum(user_context: UserContext) -> float:
    """
    Calculate overall momentum score.

    Considers three factors:
    - Task completion momentum: Based on recently completed tasks
    - Habit consistency momentum: Based on average streak length
    - Learning velocity: Based on knowledge acquisition rate

    Args:
        user_context: User context to analyze

    Returns:
        Momentum score (0.0 to 1.0)
    """
    factors = []

    # Task completion momentum (up to 10 completed tasks = 1.0)
    if user_context.completed_task_uids:
        factors.append(min(1.0, len(user_context.completed_task_uids) / 10))

    # Habit consistency momentum (14-day average streak = 1.0)
    if user_context.habit_streaks:
        avg_streak = sum(user_context.habit_streaks.values()) / len(user_context.habit_streaks)
        factors.append(min(1.0, avg_streak / 14))

    # Learning velocity
    factors.append(user_context.calculate_learning_velocity())

    return sum(factors) / len(factors) if factors else 0.0


def calculate_domain_balance(user_context: UserContext) -> float:
    """
    Calculate balance across domains.

    Uses standard deviation of domain progress to measure balance.
    Lower std_dev = better balance.

    Args:
        user_context: User context to analyze

    Returns:
        Balance score (0.0 to 1.0), where 1.0 is perfectly balanced
    """
    if not user_context.domain_progress:
        return 0.5

    progress_values = list(user_context.domain_progress.values())
    if not progress_values:
        return 0.5

    mean = sum(progress_values) / len(progress_values)
    variance = sum((x - mean) ** 2 for x in progress_values) / len(progress_values)
    std_dev = variance**0.5

    # Lower std_dev = better balance
    # Convert to 0-1 scale (inverse relationship)
    # 0.5 = max expected std_dev for "poor balance"
    return max(0.0, 1.0 - (std_dev / 0.5))
