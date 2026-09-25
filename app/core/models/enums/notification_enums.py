"""
Notification Enums
==================

The vocabulary of in-app notifications: what a bell can ring about, and how
each kind presents (icon, badge variant, label). Presentation lives on the
enum so the card renders from the member, never from a string table
(ENUM_ARCHITECTURE § Dynamic Enum Pattern).

Which page a notification opens is NOT a member trait: the card resolves it
from the notification's ``source_type`` + ``source_uid`` through
``entity_detail_href`` — with one override, ``SUBMISSION_FOR_REVIEW``, whose
door is the teacher's review page rather than the entry's own detail page.

See: /docs/roadmap/submission-sharing-arc.md (R10 — who is rung for what)
"""

from __future__ import annotations

from enum import StrEnum


class NotificationType(StrEnum):
    """What a notification is about — the stored ``notification_type`` value."""

    # --- feedback on the student's own work (rings the student) ---
    FEEDBACK_RECEIVED = "feedback_received"  # a teacher's EntryReport on a turn-in
    SUBMISSION_APPROVED = "submission_approved"  # the turn-in was approved
    REVISION_REQUESTED = "revision_requested"  # the teacher asked for changes
    REVISED_EXERCISE_CREATED = "revised_exercise_created"  # revision instructions are ready
    ACTIVITY_REPORT_RECEIVED = "activity_report_received"  # an admin wrote an activity report

    # --- work arriving for the recipient (rings a teacher / a person) ---
    SUBMISSION_FOR_REVIEW = "submission_for_review"  # a student submitted for feedback
    SHARED_WITH_YOU = "shared_with_you"  # someone shared their work with you

    @classmethod
    def from_string(cls, value: str) -> NotificationType | None:
        """Resolve a stored value; ``None`` for a value this build does not know.

        A notification written by a build that knew a kind this one does not
        must still list and open — the card falls back to a generic bell.
        """
        try:
            return cls(value)
        except ValueError:
            return None

    def get_icon(self) -> str:
        """The emoji the card leads with."""
        icons = {
            NotificationType.FEEDBACK_RECEIVED: "💬",
            NotificationType.SUBMISSION_APPROVED: "✅",
            NotificationType.REVISION_REQUESTED: "✏️",
            NotificationType.REVISED_EXERCISE_CREATED: "📝",
            NotificationType.ACTIVITY_REPORT_RECEIVED: "📊",
            NotificationType.SUBMISSION_FOR_REVIEW: "📥",
            NotificationType.SHARED_WITH_YOU: "🔗",
        }
        return icons[self]

    def get_badge_variant(self) -> str:
        """The badge variant name (a ``ui.feedback.BadgeT`` value) for the kind's badge."""
        variants = {
            NotificationType.FEEDBACK_RECEIVED: "info",
            NotificationType.SUBMISSION_APPROVED: "success",
            NotificationType.REVISION_REQUESTED: "warning",
            NotificationType.REVISED_EXERCISE_CREATED: "warning",
            NotificationType.ACTIVITY_REPORT_RECEIVED: "info",
            NotificationType.SUBMISSION_FOR_REVIEW: "primary",
            NotificationType.SHARED_WITH_YOU: "accent",
        }
        return variants[self]

    def get_label(self) -> str:
        """The badge text."""
        labels = {
            NotificationType.FEEDBACK_RECEIVED: "Feedback",
            NotificationType.SUBMISSION_APPROVED: "Approved",
            NotificationType.REVISION_REQUESTED: "Revision requested",
            NotificationType.REVISED_EXERCISE_CREATED: "Revision instructions",
            NotificationType.ACTIVITY_REPORT_RECEIVED: "Activity report",
            NotificationType.SUBMISSION_FOR_REVIEW: "For review",
            NotificationType.SHARED_WITH_YOU: "Shared with you",
        }
        return labels[self]


__all__ = ["NotificationType"]
