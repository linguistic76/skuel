"""
Activity Enums - Priority, Confidence, Calendar Types, and Assessment Levels
=============================================================================

Enums for priority, confidence, calendar/timeline types, and dual-track assessment.

Status enums (EntityStatus) live in entity_enums.py — THE unified status enum.
CompletionStatus (habit completion tracking) lives in habit_enums.py.
EngagementState tracks whether a curriculum-spawned activity is still engaged
or has been promoted to owned by the student.
"""

from __future__ import annotations

from enum import StrEnum


class Priority(StrEnum):
    """
    Universal priority levels used across all entities.

    Used by: Tasks, Events, Habits, Learning Sessions
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def to_numeric(self) -> int:
        """Convert to numeric value for scoring (LOW=1 ... CRITICAL=4)."""
        return _PRIORITY_NUMERIC_VALUES[self]

    def sort_order(self) -> int:
        """Sort order for priority lists (CRITICAL first, LOW last)."""
        return _PRIORITY_SORT_ORDERS[self]

    @classmethod
    def from_value(cls, value: object) -> Priority:
        """Normalize enum/string inputs to a priority, defaulting to MEDIUM."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            for priority in cls:
                if priority.value == value_lower or priority.name.lower() == value_lower:
                    return priority
        return cls.MEDIUM

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

    def get_badge_class(self) -> str:
        """Get Tailwind badge classes for priority display."""
        return {
            Priority.CRITICAL: "bg-red-100 text-red-800 border-red-200",
            Priority.HIGH: "bg-yellow-100 text-yellow-800 border-yellow-200",
            Priority.MEDIUM: "bg-blue-100 text-blue-800 border-blue-200",
            Priority.LOW: "bg-green-100 text-green-800 border-green-200",
        }.get(self, "bg-muted text-muted-foreground border-border")

    def get_text_class(self) -> str:
        """Get Tailwind text color class for priority display."""
        return {
            Priority.CRITICAL: "text-red-600",
            Priority.HIGH: "text-yellow-600",
            Priority.MEDIUM: "text-blue-600",
            Priority.LOW: "text-muted-foreground",
        }.get(self, "text-muted-foreground")

    def get_border_class(self) -> str:
        """Get Tailwind border-left class for priority display."""
        return {
            Priority.CRITICAL: "border-l-red-500",
            Priority.HIGH: "border-l-red-500",
            Priority.MEDIUM: "border-l-yellow-500",
            Priority.LOW: "border-l-green-500",
        }.get(self, "border-l-border")

    def get_dot_class(self) -> str:
        """Get Tailwind dot background class for priority display."""
        return {
            Priority.CRITICAL: "bg-red-500",
            Priority.HIGH: "bg-red-500",
            Priority.MEDIUM: "bg-yellow-500",
            Priority.LOW: "bg-green-500",
        }.get(self, "bg-muted")

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


_PRIORITY_NUMERIC_VALUES: dict[Priority, int] = {
    Priority.LOW: 1,
    Priority.MEDIUM: 2,
    Priority.HIGH: 3,
    Priority.CRITICAL: 4,
}

_PRIORITY_SORT_ORDERS: dict[Priority, int] = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


class Confidence(StrEnum):
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
    LOW = "low"  # ~0.5 — tentative, needs validation
    MEDIUM = "medium"  # ~0.7 — reasonably sure, working assumption
    HIGH = "high"  # ~0.9 — confident, well-validated
    CERTAIN = "certain"  # 1.0  — absolutely sure, foundational

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
            Confidence.LOW: "#F59E0B",  # Amber — tentative
            Confidence.MEDIUM: "#3B82F6",  # Blue — working assumption
            Confidence.HIGH: "#10B981",  # Green — validated
            Confidence.CERTAIN: "#6D28D9",  # Purple — foundational
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


class ActivityType(StrEnum):
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


class ProductivityLevel(StrEnum):
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


class ProgressLevel(StrEnum):
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


class ConsistencyLevel(StrEnum):
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


class EngagementLevel(StrEnum):
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


class DecisionQualityLevel(StrEnum):
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


class MasteryLevel(StrEnum):
    """
    Self-assessment level for knowledge mastery of a Ku (ADR-030).

    The user side of the Knowledge dual-track dimension: how well the user
    *feels* they have mastered an atomic Knowledge Unit. Compared against the
    system-measured Knowledge **substance score**
    (``KuIntelligenceService.calculate_user_substance`` — how much they have
    actually applied the Ku across their life) to surface the perception gap.

    NOTE: distinct from ``MasteryImpact`` (a contribution-weighting enum) — this
    is a self-rating, not an impact weight.
    """

    MASTERED = "mastered"  # Internalized — I can teach it and apply it fluently
    PROFICIENT = "proficient"  # Solid working command, occasional reference
    FAMILIAR = "familiar"  # Comfortable with the basics, still consolidating
    AWARE = "aware"  # I know what it is but rarely apply it
    NOVICE = "novice"  # Just encountered it — theoretical only

    def to_score(self) -> float:
        """Convert to numeric score (0.0-1.0)."""
        return {
            MasteryLevel.MASTERED: 1.0,
            MasteryLevel.PROFICIENT: 0.75,
            MasteryLevel.FAMILIAR: 0.5,
            MasteryLevel.AWARE: 0.25,
            MasteryLevel.NOVICE: 0.05,
        }.get(self, 0.5)

    @classmethod
    def from_score(cls, score: float) -> "MasteryLevel":
        """Convert numeric score to level."""
        if score >= 0.85:
            return cls.MASTERED
        elif score >= 0.6:
            return cls.PROFICIENT
        elif score >= 0.35:
            return cls.FAMILIAR
        elif score >= 0.1:
            return cls.AWARE
        else:
            return cls.NOVICE


class DualTrackDimension(StrEnum):
    """
    The three *user-level* dual-track perception-gap dimensions (ADR-030).

    Unlike the per-entity dimensions (Goals/Habits/Principles, keyed by the
    entity's own UID and persisted on the entity's ``dual_track_checkins``
    field), these assess the user across *all* their entities of a kind and
    have no ``:Entity`` row to attach to. Their check-ins are persisted on the
    ``User`` node, keyed by this enum's value — see ``User.dual_track_checkins``
    and ``UserService.append_dual_track_checkin``.

    The value doubles as the Self Check-In form field name and the storage key,
    so the route, the persistence method, and the cross-domain aggregator all
    agree on one canonical token per dimension.
    """

    PRODUCTIVITY = "productivity"  # Tasks — throughput / on-time / backlog
    ENGAGEMENT = "engagement"  # Events — attendance / participation
    DECISION_QUALITY = "decision_quality"  # Choices — outcome quality

    def label(self) -> str:
        """Human-readable label, e.g. ``decision_quality`` -> ``Decision Quality``."""
        return self.value.replace("_", " ").title()


class EngagementState(StrEnum):
    """Lifecycle state of an Activity instance spawned from a PathStep template.

    ``None`` on the instance means standalone (not curriculum-spawned).

    See: /.claude/skills/activity-domains/TEMPLATES.md
    """

    ENGAGED = "engaged"
    OWNED = "owned"

    def is_terminal(self) -> bool:
        """Return True if the student has taken ownership of this instance."""
        return self == EngagementState.OWNED

    def display_label(self) -> str:
        """Human-readable label for UI display."""
        return self.value.capitalize()
