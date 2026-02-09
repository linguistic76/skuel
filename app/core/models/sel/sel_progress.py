"""
SEL Progress Tracking Models
============================

Models for tracking user progress through the Social Emotional Learning (SEL) framework.

These models support adaptive curriculum delivery by tracking:
- Progress through each SEL category
- Current learning level
- Overall SEL journey across all categories
"""

from dataclasses import dataclass, field
from datetime import datetime

from core.models.enums import LearningLevel, SELCategory


@dataclass(frozen=True)
class SELCategoryProgress:
    """
    Tracks user's progress through one SEL category.

    Provides metrics for adaptive curriculum delivery, showing what the user
    has mastered, what's in progress, and what's available next.
    """

    user_uid: str
    sel_category: SELCategory

    # Progress Metrics
    kus_mastered: int = 0
    kus_in_progress: int = 0
    kus_available: int = 0
    total_kus: int = 0

    # Computed Progress
    completion_percentage: float = 0.0  # 0-100
    current_level: LearningLevel = LearningLevel.BEGINNER

    # Journey Tracking
    started_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    estimated_completion_date: datetime | None = None  # type: ignore[assignment]

    def calculate_progress(self) -> float:
        """
        Calculate completion percentage.

        Returns:
            Float between 0-100 representing progress percentage
        """
        if self.total_kus == 0:
            return 0.0
        return (self.kus_mastered / self.total_kus) * 100

    def determine_level(self) -> LearningLevel:
        """
        Determine current learning level based on mastery.

        Business rules:
        - 0-24% complete → BEGINNER
        - 25-49% complete → INTERMEDIATE
        - 50-74% complete → ADVANCED
        - 75-100% complete → EXPERT

        Returns:
            LearningLevel appropriate for current progress
        """
        progress = self.calculate_progress()
        if progress < 25:
            return LearningLevel.BEGINNER
        elif progress < 50:
            return LearningLevel.INTERMEDIATE
        elif progress < 75:
            return LearningLevel.ADVANCED
        else:
            return LearningLevel.EXPERT

    def is_just_starting(self) -> bool:
        """Check if user is just starting this category"""
        return self.kus_mastered == 0

    def is_completed(self) -> bool:
        """Check if user has completed this category"""
        return self.completion_percentage >= 95.0  # Allow 95% for "completed"

    def needs_attention(self) -> bool:
        """
        Check if this category needs attention.

        Returns True if user has started but hasn't made progress recently.
        """
        if self.is_just_starting() or self.is_completed():
            return False

        # Check if last activity was more than 7 days ago
        days_since_activity = (datetime.now() - self.last_activity).days
        return days_since_activity > 7


@dataclass(frozen=True)
class SELJourney:
    """
    Complete SEL journey for a user across all categories.

    Provides a holistic view of the user's progress through the entire
    SEL framework, with recommendations for what to focus on next.
    """

    user_uid: str
    category_progress: dict[SELCategory, SELCategoryProgress]
    overall_completion: float = 0.0

    def get_next_recommended_category(self) -> SELCategory:
        """
        Recommend which SEL category to focus on next.

        Business rules:
        1. Start with Self-Awareness (foundation)
        2. Then Self-Management
        3. Then find category with least progress

        Returns:
            SELCategory that should be prioritized next
        """
        # Rule 1: Start with Self-Awareness (foundation)
        self_awareness_progress = self.category_progress[SELCategory.SELF_AWARENESS]
        if self_awareness_progress.completion_percentage < 30:
            return SELCategory.SELF_AWARENESS

        # Rule 2: Then Self-Management
        self_management_progress = self.category_progress[SELCategory.SELF_MANAGEMENT]
        if self_management_progress.completion_percentage < 30:
            return SELCategory.SELF_MANAGEMENT

        # Rule 3: Find category with least progress
        min_category = None
        min_progress = 100.0

        for category, progress in self.category_progress.items():
            if progress.completion_percentage < min_progress:
                min_progress = progress.completion_percentage
                min_category = category

        return min_category if min_category else SELCategory.SELF_AWARENESS

    def get_categories_needing_attention(self) -> list[SELCategory]:
        """
        Get list of categories that need attention.

        Returns:
            List of SELCategory values that haven't been active recently
        """
        needing_attention = []
        for category, progress in self.category_progress.items():
            if progress.needs_attention():
                needing_attention.append(category)
        return needing_attention

    def is_well_rounded(self) -> bool:
        """
        Check if user has balanced progress across all categories.

        Well-rounded means no category is more than 30% behind the average.

        Returns:
            True if progress is balanced across categories
        """
        if not self.category_progress:
            return False

        # Calculate average progress
        total_progress = sum(p.completion_percentage for p in self.category_progress.values())
        avg_progress = total_progress / len(self.category_progress)

        # Check if any category is too far behind
        for progress in self.category_progress.values():
            if avg_progress - progress.completion_percentage > 30:
                return False

        return True

    def get_strongest_category(self) -> SELCategory:
        """
        Get the SEL category with highest progress.

        Returns:
            SELCategory with most completion
        """
        max_category = None
        max_progress = 0.0

        for category, progress in self.category_progress.items():
            if progress.completion_percentage > max_progress:
                max_progress = progress.completion_percentage
                max_category = category

        return max_category if max_category else SELCategory.SELF_AWARENESS

    def get_weakest_category(self) -> SELCategory:
        """
        Get the SEL category with lowest progress.

        Returns:
            SELCategory with least completion
        """
        min_category = None
        min_progress = 100.0

        for category, progress in self.category_progress.items():
            if progress.completion_percentage < min_progress:
                min_progress = progress.completion_percentage
                min_category = category

        return min_category if min_category else SELCategory.SELF_AWARENESS
