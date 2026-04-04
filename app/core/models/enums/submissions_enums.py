"""
Reports Enums - Processing and Scheduling
===========================================

Enums for report processing pipelines, LLM configuration,
and scheduling scope.
"""

from enum import StrEnum


class SubmissionModality(StrEnum):
    """
    Format of submission expected by an Exercise or used by an ExerciseSubmission.

    FILE_UPLOAD: Student uploads a file (audio, PDF, document, image)
    STRUCTURED_FORM: Student fills out an inline form defined by Exercise.form_schema
    """

    FILE_UPLOAD = "file_upload"
    STRUCTURED_FORM = "structured_form"


class ExerciseScope(StrEnum):
    """
    Scope of an exercise (instruction template).

    PERSONAL: User's own AI feedback template (default)
    ASSIGNED: Teacher-created, assigned to a group (ADR-040)
    ASSESSMENT: Formal test/exam with scoring rubric and pass/fail criteria
    """

    PERSONAL = "personal"
    ASSIGNED = "assigned"
    ASSESSMENT = "assessment"


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


class EnrichmentMode(StrEnum):
    """Processing strategy for journal LLM enrichment.

    ACTIVITY_TRACKING: Extract and structure daily activities (default)
    IDEA_ARTICULATION: Develop and refine ideas from raw thoughts
    CRITICAL_THINKING: Explore topics with analytical depth
    """

    ACTIVITY_TRACKING = "activity_tracking"
    IDEA_ARTICULATION = "idea_articulation"
    CRITICAL_THINKING = "critical_thinking"


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
