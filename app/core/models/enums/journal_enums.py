"""
Journal Enums - Single Source of Truth
======================================

Consolidated enums for the Journal domain (January 2026).
Previously duplicated in journal_dto.py and journal_pure.py.

Per One Path Forward: One definition, imported everywhere.

Updated January 2026: Added JournalType enum for proper separation
of Journals and Assignments domains per architecture plan.
"""

from enum import Enum


class JournalType(str, Enum):
    """
    Journal retention tiers.

    Two-tier journal system (January 2026):
    - VOICE (PJ1): Ephemeral voice journals, max 3 stored, audio source
    - CURATED (PJ2): Permanent curated text/markdown journals

    This enum replaces the journal-related values in ReportType,
    providing proper domain separation between Journals and Reports.
    """

    VOICE = "voice"  # PJ1: Ephemeral, max 3, audio
    CURATED = "curated"  # PJ2: Permanent, text/markdown

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


class ContentType(Enum):
    """Types of content in the system."""

    JOURNAL = "journal"
    AUDIO_TRANSCRIPT = "audio_transcript"
    NOTE = "note"
    ARTICLE = "article"
    REFLECTION = "reflection"


class ContentStatus(Enum):
    """Status of content processing."""

    DRAFT = "draft"
    TRANSCRIBED = "transcribed"
    PROCESSED = "processed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentVisibility(Enum):
    """Visibility levels for content."""

    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class JournalCategory(Enum):
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
