"""
Reports Enums - Processing, Scheduling, and Assignment
========================================================

Enums for report processing pipelines, LLM configuration,
scheduling, and project/assignment scope.
"""

from enum import StrEnum


class ExerciseScope(StrEnum):
    """
    Scope of an exercise (instruction template).

    PERSONAL: User's own AI feedback template (default)
    ASSIGNED: Teacher-created, assigned to a group (ADR-040)
    """

    PERSONAL = "personal"
    ASSIGNED = "assigned"


class FormattingStyle(StrEnum):
    """Style for formatting transcripts during LLM processing."""

    STRUCTURED = "structured"
    NARRATIVE = "narrative"
    BULLET_POINTS = "bullet_points"
    CONVERSATIONAL = "conversational"
    EXECUTIVE_SUMMARY = "executive_summary"


class AnalysisDepth(StrEnum):
    """Depth of analysis for transcript processing."""

    BASIC = "basic"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class ContextEnrichmentLevel(StrEnum):
    """Level of SKUEL enterprise context integration."""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    DEEP = "deep"


class ScheduleType(StrEnum):
    """Frequency of progress report generation."""

    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            ScheduleType.WEEKLY: "Weekly",
            ScheduleType.BIWEEKLY: "Every 2 Weeks",
            ScheduleType.MONTHLY: "Monthly",
        }[self]


class ProgressDepth(StrEnum):
    """Level of detail in generated progress reports."""

    SUMMARY = "summary"
    STANDARD = "standard"
    DETAILED = "detailed"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            ProgressDepth.SUMMARY: "Summary (counts only)",
            ProgressDepth.STANDARD: "Standard (counts + examples)",
            ProgressDepth.DETAILED: "Detailed (full breakdown)",
        }[self]
