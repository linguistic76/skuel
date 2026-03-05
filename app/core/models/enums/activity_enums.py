"""
Activity Enums - Priority, Confidence, Calendar Types, and Assessment Levels
=============================================================================

Enums for priority, confidence, calendar/timeline types, and dual-track assessment.

Status enums (EntityStatus) live in entity_enums.py — THE unified status enum.
CompletionStatus (habit completion tracking) lives in habit_enums.py.
"""

from enum import Enum


class Priority(str, Enum):
    """
    Universal priority levels used across all entities.

    Used by: Tasks, Events, Habits, Learning Sessions
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def to_numeric(self) -> int:
        """Convert to numeric value for sorting (1-4)"""
        mapping = {Priority.LOW: 1, Priority.MEDIUM: 2, Priority.HIGH: 3, Priority.CRITICAL: 4}
        return mapping.get(self, 2)

    def get_color(self) -> str:
        """Get suggested color for UI rendering"""
        colors = {
            Priority.LOW: "#10B981",  # Green
            Priority.MEDIUM: "#3B82F6",  # Blue
            Priority.HIGH: "#F59E0B",  # Amber
            Priority.CRITICAL: "#DC2626",  # Red
        }
        return colors.get(self, "#6B7280")  # Gray default

    def get_calendar_color(self) -> str:
        """
        Get color for calendar/timeline display.

        Calendar uses a different palette than general UI:
        - LOW is gray (de-emphasized) rather than green
        - Colors are more saturated for visibility on calendar grids
        """
        colors = {
            Priority.LOW: "#9ca3af",  # Gray - de-emphasized on calendar
            Priority.MEDIUM: "#3b82f6",  # Blue
            Priority.HIGH: "#f97316",  # Orange - more urgent than amber
            Priority.CRITICAL: "#ef4444",  # Red
        }
        return colors.get(self, "#9ca3af")  # Gray default

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this priority level"""
        synonyms = {
            Priority.LOW: ("low", "minor", "trivial", "someday", "optional", "nice to have"),
            Priority.MEDIUM: ("medium", "normal", "standard", "moderate", "regular", "typical"),
            Priority.HIGH: ("high", "important", "soon", "urgent", "priority", "significant"),
            Priority.CRITICAL: (
                "critical",
                "urgent",
                "emergency",
                "now",
                "asap",
                "immediate",
                "blocker",
            ),
        }
        return synonyms.get(self, ())

    def get_search_description(self) -> str:
        """Human-readable description for search UI"""
        descriptions = {
            Priority.LOW: "Low priority - flexible timing",
            Priority.MEDIUM: "Medium priority - standard importance",
            Priority.HIGH: "High priority - needs attention soon",
            Priority.CRITICAL: "Critical - urgent action required",
        }
        return descriptions.get(self, "")

    @classmethod
    def from_search_text(cls, text: str) -> list["Priority"]:
        """Find matching priority levels from search text."""
        text_lower = text.lower()
        return [
            priority
            for priority in cls
            if any(synonym in text_lower for synonym in priority.get_search_synonyms())
        ]


class Confidence(str, Enum):
    """
    User-assessed certainty about an entity.

    Parallel to Priority — named levels map to ConfidenceLevel float constants.

    Used by:
    - UserOwnedEntity.confidence (entity-level self-assessment)
    - Lateral relationship metadata (relationship-level assertion strength)

    On a Task: "How confident am I that I'll complete this?"
    On a Goal: "How certain am I I'll achieve this?"
    On a Habit: "How sure am I this habit is serving me?"
    On a Principle: "How deeply held is this principle?"
    """

    UNCERTAIN = "uncertain"  # ~0.3 — exploratory, speculative
    LOW = "low"              # ~0.5 — tentative, needs validation
    MEDIUM = "medium"        # ~0.7 — reasonably sure, working assumption
    HIGH = "high"            # ~0.9 — confident, well-validated
    CERTAIN = "certain"      # 1.0  — absolutely sure, foundational

    def to_numeric(self) -> float:
        """Convert to float for Cypher queries (mirrors ConfidenceLevel constants)."""
        return {
            Confidence.UNCERTAIN: 0.3,
            Confidence.LOW: 0.5,
            Confidence.MEDIUM: 0.7,
            Confidence.HIGH: 0.9,
            Confidence.CERTAIN: 1.0,
        }.get(self, 0.7)

    def get_color(self) -> str:
        """Get suggested color for UI rendering (parallel to Priority.get_color())."""
        return {
            Confidence.UNCERTAIN: "#EF4444",  # Red — needs attention
            Confidence.LOW: "#F59E0B",         # Amber — tentative
            Confidence.MEDIUM: "#3B82F6",      # Blue — working assumption
            Confidence.HIGH: "#10B981",         # Green — validated
            Confidence.CERTAIN: "#6D28D9",      # Purple — foundational
        }.get(self, "#6B7280")

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this confidence level."""
        return {
            Confidence.UNCERTAIN: ("uncertain", "unsure", "speculative", "exploratory", "unknown"),
            Confidence.LOW: ("low confidence", "tentative", "unvalidated", "provisional"),
            Confidence.MEDIUM: ("medium confidence", "reasonable", "working assumption", "likely"),
            Confidence.HIGH: ("high confidence", "confident", "validated", "reliable", "solid"),
            Confidence.CERTAIN: ("certain", "sure", "absolute", "foundational", "definite"),
        }.get(self, ())

    @classmethod
    def from_numeric(cls, value: float) -> "Confidence":
        """Convert numeric float to nearest Confidence level."""
        if value >= 0.95:
            return cls.CERTAIN
        elif value >= 0.8:
            return cls.HIGH
        elif value >= 0.6:
            return cls.MEDIUM
        elif value >= 0.4:
            return cls.LOW
        else:
            return cls.UNCERTAIN

    @classmethod
    def from_search_text(cls, text: str) -> list["Confidence"]:
        """Find matching confidence levels from search text."""
        text_lower = text.lower()
        return [
            level
            for level in cls
            if any(synonym in text_lower for synonym in level.get_search_synonyms())
        ]


class ActivityType(str, Enum):
    """
    Types of activities that can appear on a calendar or be tracked.

    Each type may have different behaviors and rendering styles.
    """

    # Core activity types
    TASK = "task"  # Work to be done
    HABIT = "habit"  # Recurring behavior to build/break
    EVENT = "event"  # Time-bound occurrence
    LEARNING = "learning"  # Learning session or study time

    # Specialized types
    MILESTONE = "milestone"  # Important checkpoint/achievement
    DEADLINE = "deadline"  # Due date marker
    MEETING = "meeting"  # Specific type of event
    PRACTICE = "practice"  # Practice session (habit or learning)
    REVIEW = "review"  # Review session
    BREAK = "break"  # Scheduled break/rest time

    # Meta types
    BLOCK = "block"  # Time block reservation
    PLACEHOLDER = "placeholder"  # Tentative/placeholder item

    def get_icon(self) -> str:
        """Get emoji icon for this activity type"""
        icons = {
            ActivityType.TASK: "📝",
            ActivityType.HABIT: "🔄",
            ActivityType.EVENT: "📅",
            ActivityType.LEARNING: "📚",
            ActivityType.MILESTONE: "🎯",
            ActivityType.DEADLINE: "⏰",
            ActivityType.MEETING: "👥",
            ActivityType.PRACTICE: "🎹",
            ActivityType.REVIEW: "🔍",
            ActivityType.BREAK: "☕",
            ActivityType.BLOCK: "🔒",
            ActivityType.PLACEHOLDER: "📌",
        }
        return icons.get(self, "📋")

    def default_duration_minutes(self) -> int:
        """Get default duration for this activity type"""
        durations = {
            ActivityType.TASK: 60,
            ActivityType.HABIT: 30,
            ActivityType.EVENT: 60,
            ActivityType.LEARNING: 45,
            ActivityType.MILESTONE: 15,
            ActivityType.DEADLINE: 15,
            ActivityType.MEETING: 60,
            ActivityType.PRACTICE: 30,
            ActivityType.REVIEW: 30,
            ActivityType.BREAK: 15,
            ActivityType.BLOCK: 60,
            ActivityType.PLACEHOLDER: 30,
        }
        return durations.get(self, 30)


# =============================================================================
# DUAL-TRACK ASSESSMENT LEVELS (ADR-030 - January 2026)
# =============================================================================
# These enums support the dual-track assessment pattern, which compares
# user self-assessment (vision) with system measurement (action).


class ProductivityLevel(str, Enum):
    """
    Self-assessment level for task productivity.

    Used in dual-track assessment to compare user's perception
    of their productivity with system-measured completion rates.
    """

    HIGHLY_PRODUCTIVE = "highly_productive"  # Exceeding expectations
    PRODUCTIVE = "productive"  # Meeting expectations
    MODERATELY_PRODUCTIVE = "moderately_productive"  # Some room for improvement
    STRUGGLING = "struggling"  # Below expectations
    OVERWHELMED = "overwhelmed"  # Significantly behind

    def to_score(self) -> float:
        """Convert to numeric score (0.0-1.0)."""
        return {
            ProductivityLevel.HIGHLY_PRODUCTIVE: 1.0,
            ProductivityLevel.PRODUCTIVE: 0.8,
            ProductivityLevel.MODERATELY_PRODUCTIVE: 0.6,
            ProductivityLevel.STRUGGLING: 0.35,
            ProductivityLevel.OVERWHELMED: 0.15,
        }.get(self, 0.5)

    @classmethod
    def from_score(cls, score: float) -> "ProductivityLevel":
        """Convert numeric score to level."""
        if score >= 0.9:
            return cls.HIGHLY_PRODUCTIVE
        elif score >= 0.7:
            return cls.PRODUCTIVE
        elif score >= 0.5:
            return cls.MODERATELY_PRODUCTIVE
        elif score >= 0.25:
            return cls.STRUGGLING
        else:
            return cls.OVERWHELMED


class ProgressLevel(str, Enum):
    """
    Self-assessment level for goal progress.

    Used in dual-track assessment to compare user's perception
    of their progress with system-measured milestone completion.
    """

    ON_TRACK = "on_track"  # Progressing as expected or better
    STEADY = "steady"  # Making consistent progress
    SLOW = "slow"  # Progress slower than expected
    STALLED = "stalled"  # Little to no recent progress
    REGRESSING = "regressing"  # Moving away from goal

    def to_score(self) -> float:
        """Convert to numeric score (0.0-1.0)."""
        return {
            ProgressLevel.ON_TRACK: 1.0,
            ProgressLevel.STEADY: 0.75,
            ProgressLevel.SLOW: 0.5,
            ProgressLevel.STALLED: 0.25,
            ProgressLevel.REGRESSING: 0.1,
        }.get(self, 0.5)

    @classmethod
    def from_score(cls, score: float) -> "ProgressLevel":
        """Convert numeric score to level."""
        if score >= 0.85:
            return cls.ON_TRACK
        elif score >= 0.6:
            return cls.STEADY
        elif score >= 0.4:
            return cls.SLOW
        elif score >= 0.2:
            return cls.STALLED
        else:
            return cls.REGRESSING


class ConsistencyLevel(str, Enum):
    """
    Self-assessment level for habit consistency.

    Used in dual-track assessment to compare user's perception
    of their consistency with system-measured streak and completion data.
    """

    ROCK_SOLID = "rock_solid"  # Never miss, deeply ingrained
    CONSISTENT = "consistent"  # Rarely miss, well-established
    BUILDING = "building"  # More hits than misses, developing
    INCONSISTENT = "inconsistent"  # Sporadic completion
    STRUGGLING = "struggling"  # Rarely completing

    def to_score(self) -> float:
        """Convert to numeric score (0.0-1.0)."""
        return {
            ConsistencyLevel.ROCK_SOLID: 1.0,
            ConsistencyLevel.CONSISTENT: 0.8,
            ConsistencyLevel.BUILDING: 0.6,
            ConsistencyLevel.INCONSISTENT: 0.35,
            ConsistencyLevel.STRUGGLING: 0.15,
        }.get(self, 0.5)

    @classmethod
    def from_score(cls, score: float) -> "ConsistencyLevel":
        """Convert numeric score to level."""
        if score >= 0.9:
            return cls.ROCK_SOLID
        elif score >= 0.7:
            return cls.CONSISTENT
        elif score >= 0.5:
            return cls.BUILDING
        elif score >= 0.25:
            return cls.INCONSISTENT
        else:
            return cls.STRUGGLING


class EngagementLevel(str, Enum):
    """
    Self-assessment level for event engagement.

    Used in dual-track assessment to compare user's perception
    of their engagement with system-measured attendance and participation.
    """

    FULLY_ENGAGED = "fully_engaged"  # Active participant, fully present
    ENGAGED = "engaged"  # Good participation
    PRESENT = "present"  # Attending but not fully engaged
    DISENGAGED = "disengaged"  # Going through motions
    ABSENT = "absent"  # Not participating

    def to_score(self) -> float:
        """Convert to numeric score (0.0-1.0)."""
        return {
            EngagementLevel.FULLY_ENGAGED: 1.0,
            EngagementLevel.ENGAGED: 0.8,
            EngagementLevel.PRESENT: 0.5,
            EngagementLevel.DISENGAGED: 0.25,
            EngagementLevel.ABSENT: 0.0,
        }.get(self, 0.5)

    @classmethod
    def from_score(cls, score: float) -> "EngagementLevel":
        """Convert numeric score to level."""
        if score >= 0.9:
            return cls.FULLY_ENGAGED
        elif score >= 0.65:
            return cls.ENGAGED
        elif score >= 0.4:
            return cls.PRESENT
        elif score >= 0.15:
            return cls.DISENGAGED
        else:
            return cls.ABSENT


class DecisionQualityLevel(str, Enum):
    """
    Self-assessment level for choice/decision quality.

    Used in dual-track assessment to compare user's perception
    of their decision-making with system-measured outcome tracking.
    """

    EXCELLENT = "excellent"  # Decisions consistently lead to good outcomes
    GOOD = "good"  # Most decisions work out well
    ADEQUATE = "adequate"  # Mix of good and poor outcomes
    POOR = "poor"  # Decisions often lead to suboptimal outcomes
    STRUGGLING = "struggling"  # Significant difficulty making good decisions

    def to_score(self) -> float:
        """Convert to numeric score (0.0-1.0)."""
        return {
            DecisionQualityLevel.EXCELLENT: 1.0,
            DecisionQualityLevel.GOOD: 0.8,
            DecisionQualityLevel.ADEQUATE: 0.55,
            DecisionQualityLevel.POOR: 0.3,
            DecisionQualityLevel.STRUGGLING: 0.1,
        }.get(self, 0.5)

    @classmethod
    def from_score(cls, score: float) -> "DecisionQualityLevel":
        """Convert numeric score to level."""
        if score >= 0.85:
            return cls.EXCELLENT
        elif score >= 0.65:
            return cls.GOOD
        elif score >= 0.45:
            return cls.ADEQUATE
        elif score >= 0.2:
            return cls.POOR
        else:
            return cls.STRUGGLING
