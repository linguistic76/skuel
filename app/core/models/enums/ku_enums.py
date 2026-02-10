"""
Ku Enums - Unified Knowledge Unit Identity and Processing
==========================================================

Enums for the unified Ku model where "Ku is the heartbeat of SKUEL."

Organized in 6 sections:
1. Core Identity: KuType (role in derivation chain)
2. Processing Lifecycle: KuStatus, ProcessorType
3. Project/Assignment: ProjectScope (teacher assignment workflow)
4. Journal Processing: JournalType, JournalCategory, JournalMode
5. LLM Processing: FormattingStyle, AnalysisDepth, ContextEnrichmentLevel
6. Schedule: ScheduleType, ProgressDepth

Per One Path Forward: These replace all enums from the deleted report_enums.py.
"""

from enum import Enum


# =============================================================================
# 1. CORE IDENTITY
# =============================================================================


class KuType(str, Enum):
    """
    Type of Knowledge Unit — defines role in the derivation chain.

    The derivation chain:
        CURRICULUM (admin-created shared knowledge)
            | student submits against this
        ASSIGNMENT (student submission, user-owned)
            | processed by AI or reviewed by teacher
        AI_REPORT (AI-derived from assignment)
        FEEDBACK_REPORT (teacher feedback on assignment)

    Each KuType implies ownership:
        CURRICULUM: user_uid = None (shared content, admin-created)
        ASSIGNMENT: user_uid = student (user-owned)
        FEEDBACK_REPORT: user_uid = teacher (teacher-owned)
        AI_REPORT: user_uid = student (system-created on behalf of student)
    """

    CURRICULUM = "curriculum"
    ASSIGNMENT = "assignment"
    FEEDBACK_REPORT = "feedback_report"
    AI_REPORT = "ai_report"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            KuType.CURRICULUM: "Curriculum",
            KuType.ASSIGNMENT: "Assignment",
            KuType.FEEDBACK_REPORT: "Feedback Report",
            KuType.AI_REPORT: "AI Report",
        }[self]

    def requires_user_uid(self) -> bool:
        """Check if this KuType requires a user_uid (ownership)."""
        return self != KuType.CURRICULUM

    def is_user_owned(self) -> bool:
        """Check if this KuType represents user-owned content."""
        return self != KuType.CURRICULUM

    def is_derived(self) -> bool:
        """Check if this KuType is derived from another Ku (has parent)."""
        return self in {KuType.ASSIGNMENT, KuType.AI_REPORT, KuType.FEEDBACK_REPORT}

    def is_processable(self) -> bool:
        """Check if this KuType goes through a processing pipeline."""
        return self in {KuType.ASSIGNMENT, KuType.AI_REPORT}


# =============================================================================
# 2. PROCESSING LIFECYCLE
# =============================================================================


class KuStatus(str, Enum):
    """
    Processing lifecycle status for a Knowledge Unit.

    Lifecycle:
        DRAFT -> SUBMITTED -> QUEUED -> PROCESSING -> COMPLETED / FAILED
                                                        |
                                                 REVISION_REQUESTED -> resubmit
                                                        |
                                                     ARCHIVED

    CURRICULUM Ku are always COMPLETED (published knowledge).
    ASSIGNMENT Ku progress through the full lifecycle.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVISION_REQUESTED = "revision_requested"
    ARCHIVED = "archived"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            KuStatus.DRAFT: "Draft",
            KuStatus.SUBMITTED: "Submitted",
            KuStatus.QUEUED: "Queued",
            KuStatus.PROCESSING: "Processing",
            KuStatus.COMPLETED: "Completed",
            KuStatus.FAILED: "Failed",
            KuStatus.REVISION_REQUESTED: "Revision Requested",
            KuStatus.ARCHIVED: "Archived",
        }[self]

    def is_terminal(self) -> bool:
        """Check if this is a terminal (non-progressing) status."""
        return self in {KuStatus.COMPLETED, KuStatus.FAILED, KuStatus.ARCHIVED}

    def is_active(self) -> bool:
        """Check if this status indicates active processing."""
        return self in {KuStatus.SUBMITTED, KuStatus.QUEUED, KuStatus.PROCESSING}

    def can_transition_to(self, target: "KuStatus") -> bool:
        """Check if transition to target status is valid."""
        valid_transitions: dict[KuStatus, set[KuStatus]] = {
            KuStatus.DRAFT: {KuStatus.SUBMITTED, KuStatus.ARCHIVED},
            KuStatus.SUBMITTED: {KuStatus.QUEUED, KuStatus.PROCESSING, KuStatus.FAILED},
            KuStatus.QUEUED: {KuStatus.PROCESSING, KuStatus.FAILED},
            KuStatus.PROCESSING: {KuStatus.COMPLETED, KuStatus.FAILED},
            KuStatus.COMPLETED: {KuStatus.REVISION_REQUESTED, KuStatus.ARCHIVED},
            KuStatus.FAILED: {KuStatus.DRAFT, KuStatus.ARCHIVED},
            KuStatus.REVISION_REQUESTED: {KuStatus.DRAFT, KuStatus.ARCHIVED},
            KuStatus.ARCHIVED: set(),
        }
        return target in valid_transitions.get(self, set())


class ProcessorType(str, Enum):
    """
    Type of processor used for Ku content processing.

    Determines the processing pipeline:
        LLM: AI/LLM processing (OpenAI, etc.)
        HUMAN: Manual human review (teacher feedback)
        HYBRID: LLM + human review
        AUTOMATIC: System-determined processor
    """

    LLM = "llm"
    HUMAN = "human"
    HYBRID = "hybrid"
    AUTOMATIC = "automatic"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            ProcessorType.LLM: "AI Processing",
            ProcessorType.HUMAN: "Human Review",
            ProcessorType.HYBRID: "Hybrid (AI + Human)",
            ProcessorType.AUTOMATIC: "Automatic",
        }[self]


# =============================================================================
# 3. PROJECT / ASSIGNMENT
# =============================================================================


class ProjectScope(str, Enum):
    """
    Scope of a KuProject (instruction template).

    PERSONAL: User's own AI feedback template (default)
    ASSIGNED: Teacher-created, assigned to a group (ADR-040)
    """

    PERSONAL = "personal"
    ASSIGNED = "assigned"


# =============================================================================
# 4. JOURNAL PROCESSING
# =============================================================================


class JournalType(str, Enum):
    """
    Journal retention tiers.

    Two-tier journal system:
    - VOICE (PJ1): Ephemeral voice journals, max 3 stored, audio source
    - CURATED (PJ2): Permanent curated text/markdown journals
    """

    VOICE = "voice"
    CURATED = "curated"

    def is_ephemeral(self) -> bool:
        """Check if this type has auto-cleanup (max retention limit)."""
        return self == JournalType.VOICE

    def max_retention_count(self) -> int | None:
        """
        Return max retention count for ephemeral types, None for permanent.

        VOICE journals have FIFO cleanup - only most recent 3 are kept.
        CURATED journals are permanent (no limit).
        """
        if self == JournalType.VOICE:
            return 3
        return None

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            JournalType.VOICE: "Voice Journal",
            JournalType.CURATED: "Curated Journal",
        }[self]


class JournalCategory(str, Enum):
    """Categories for journal entries."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    REFLECTION = "reflection"
    GRATITUDE = "gratitude"
    GOALS = "goals"
    IDEAS = "ideas"
    DREAMS = "dreams"
    HEALTH = "health"
    WORK = "work"
    PERSONAL = "personal"
    LEARNING = "learning"
    PROJECT = "project"
    OTHER = "other"


class JournalMode(str, Enum):
    """
    Journal processing modes — determines output formatting strategy.

    Typical journal: 80% one mode + 20% mixed.
    System infers weights via LLM, user can override.

    ACTIVITY_TRACKING: Focus on extracting actionable entities
    IDEA_ARTICULATION: Focus on preserving original thought
    CRITICAL_THINKING: Focus on question exploration
    """

    ACTIVITY_TRACKING = "activity_tracking"
    IDEA_ARTICULATION = "idea_articulation"
    CRITICAL_THINKING = "critical_thinking"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            JournalMode.ACTIVITY_TRACKING: "Activity Tracking",
            JournalMode.IDEA_ARTICULATION: "Idea Articulation",
            JournalMode.CRITICAL_THINKING: "Critical Thinking",
        }[self]

    def get_description(self) -> str:
        """Get mode description for UI/help text."""
        return {
            JournalMode.ACTIVITY_TRACKING: "Extract tasks, goals, habits from your reflections",
            JournalMode.IDEA_ARTICULATION: "Preserve your ideas with minimal processing",
            JournalMode.CRITICAL_THINKING: "Organize your thoughts around questions",
        }[self]


# =============================================================================
# 5. LLM PROCESSING
# =============================================================================


class FormattingStyle(str, Enum):
    """Style for formatting transcripts during LLM processing."""

    STRUCTURED = "structured"
    NARRATIVE = "narrative"
    BULLET_POINTS = "bullet_points"
    CONVERSATIONAL = "conversational"
    EXECUTIVE_SUMMARY = "executive_summary"


class AnalysisDepth(str, Enum):
    """Depth of analysis for transcript processing."""

    BASIC = "basic"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class ContextEnrichmentLevel(str, Enum):
    """Level of SKUEL enterprise context integration."""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    DEEP = "deep"


# =============================================================================
# 6. SCHEDULE
# =============================================================================


class ScheduleType(str, Enum):
    """Frequency of progress Ku generation."""

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


class ProgressDepth(str, Enum):
    """Level of detail in generated progress Ku."""

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
