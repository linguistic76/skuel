"""
UI Component Data Types
=======================

Frozen dataclasses for UI component data structures.
Follows Pattern 3C: dict[str, Any] → frozen dataclasses

These types are used by UI components for rendering.
Even mock data should be properly typed.

Pattern:
- Frozen (immutable)
- Type-safe field access
- Self-documenting
- Follows SKUEL three-tier pattern even in UI layer
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class HabitMigration:
    """
    Habit essentiality level migration data.

    Tracks when a habit's essentiality level changed and why.

    Attributes:
        habit: Habit name
        from_level: Previous essentiality level (critical, essential, supporting, optional)
        to_level: New essentiality level
        migration_date: When the migration occurred
        reason: Explanation for the change
    """

    habit: str
    from_level: str
    to_level: str
    migration_date: date
    reason: str


@dataclass(frozen=True)
class BenchmarkData:
    """
    User vs. community benchmark comparison data.

    Compares user performance metrics against community averages.

    Attributes:
        metric: Name of the metric being compared
        user: User's value for this metric
        community: Community average value
        percentile: User's percentile rank (0-100)
    """

    metric: str
    user: float
    community: float
    percentile: int


@dataclass(frozen=True)
class AskesisInsight:
    """
    Individual AI insight for Askesis dashboard.

    Attributes:
        insight_type: Type of insight (learning_pattern, productivity, habit_formation)
        insight: The insight text
        confidence: Confidence score (0.0-1.0)
    """

    insight_type: str
    insight: str
    confidence: float


@dataclass(frozen=True)
class AskesisData:
    """
    Askesis AI assistant dashboard data.

    Aggregated data for the Askesis AI assistant interface.

    Attributes:
        uid: Unique identifier for this askesis instance
        user_uid: User's UID
        intelligence_confidence: Overall intelligence confidence (0.0-1.0)
        conversation_style: Conversation style (adaptive, formal, casual)
        is_conversation_ready: Whether the conversation system is ready
        total_conversations: Total number of conversations
        integration_success_rate: Success rate of integrations (0.0-1.0)
        learning_progress_score: Learning progress score (0.0-1.0)
        recent_insights: List of recent AI insights
    """

    uid: str
    user_uid: str
    intelligence_confidence: float
    conversation_style: str
    is_conversation_ready: bool
    total_conversations: int
    integration_success_rate: float
    learning_progress_score: float
    recent_insights: list[AskesisInsight]


@dataclass(frozen=True)
class LearningStatsData:
    """
    User learning statistics.

    Attributes:
        total_hours: Total hours invested in learning
        concepts_mastered: Number of concepts mastered
        active_streak: Current consecutive days learning streak
        completion_rate: Rate of completed vs started paths (0.0-1.0)
    """

    total_hours: float
    concepts_mastered: int
    active_streak: int
    completion_rate: float


@dataclass(frozen=True)
class ActivePathData:
    """
    Active learning path summary.

    Attributes:
        uid: Learning path UID
        title: Path title
        progress: Progress percentage (0-100)
        current_step: Current step/module name
        estimated_completion: Estimated time to completion
        difficulty: Difficulty level (beginner, intermediate, advanced)
        time_invested: Time spent on this path
    """

    uid: str
    title: str
    progress: float
    current_step: str
    estimated_completion: str
    difficulty: str
    time_invested: str


@dataclass(frozen=True)
class AchievementData:
    """
    User achievement/badge data.

    Attributes:
        achievement_type: Type of achievement (milestone, streak, mastery)
        title: Achievement title
        description: Achievement description
        earned_at: ISO timestamp when earned
    """

    achievement_type: str
    title: str
    description: str
    earned_at: str


@dataclass(frozen=True)
class UserLearningOverview:
    """
    Complete user learning dashboard overview.

    Attributes:
        user_uid: User's UID
        active_paths: List of currently active learning paths
        recent_achievements: Recent achievements earned
        learning_stats: Overall learning statistics
    """

    user_uid: str
    active_paths: list[ActivePathData]
    recent_achievements: list[AchievementData]
    learning_stats: LearningStatsData
