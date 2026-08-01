"""Teaching UI view model types.

Frozen dataclasses for teaching queue and detail components,
plus the action-availability status set and dict-to-dataclass converters.
"""

from dataclasses import dataclass
from typing import Any

from core.models.type_hints import UserUID

# ============================================================================
# Status → action availability
# ============================================================================

# Statuses on which the inline review panel offers teacher actions (submit
# feedback / request revision / approve). This is NOT the Needs Review rule:
# what awaits review is the student-scoped review queue
# (TeacherReviewService.get_review_queue — one collapse rule, two surfaces);
# this set only gates the per-submission action forms.
NEEDS_REVIEW_STATUSES: frozenset[str] = frozenset({"submitted", "active", "queued", "processing"})


@dataclass(frozen=True)
class QueueItem:
    """A single item in the teacher review queue."""

    title: str = ""
    student_name: str = "Unknown"
    student_uid: str = ""
    status: str = "unknown"
    entity_type: str | None = None
    exercise_name: str | None = None
    submission_uid: str = ""
    feedback_count: int = 0
    original_filename: str | None = None


@dataclass(frozen=True)
class StudentSummary:
    """Student card with submission counts."""

    student_uid: str = ""
    student_name: str = "Unknown"
    submission_count: int = 0
    reviewed_count: int = 0
    pending_count: int = 0


@dataclass(frozen=True)
class ClassSummary:
    """Class (group) card with member/exercise/pending counts."""

    uid: str = ""
    name: str = "Unnamed Class"
    description: str | None = None
    member_count: int = 0
    exercise_count: int = 0
    pending_count: int = 0
    is_active: bool = True


@dataclass(frozen=True)
class SubmissionDetail:
    """Submission content for teacher review."""

    title: str = "Untitled"
    entity_type: str | None = None
    status: str = ""
    student_name: str = "Unknown"
    student_uid: str = ""
    exercise_title: str | None = None
    exercise_instructions: str | None = None
    processed_content: str | None = None
    content: str | None = None
    original_filename: str | None = None
    file_path: str | None = None


@dataclass(frozen=True)
class SubmissionRow:
    """A submission row in exercise-detail or student-detail views."""

    uid: str = ""
    title: str = ""
    student_name: str = "Unknown"
    student_uid: str = ""
    status: str = "unknown"
    feedback_count: int = 0
    exercise_title: str | None = None
    original_filename: str | None = None


@dataclass(frozen=True)
class ClassMember:
    """A member row in the class detail view."""

    user_uid: UserUID = ""  # type: ignore[assignment]
    user_name: str = "Unknown"
    role: str = "student"
    submission_count: int = 0
    reviewed_count: int = 0
    pending_count: int = 0


# ============================================================================
# Dict-to-dataclass converters (pure functions, no async/service deps)
# ============================================================================


def queue_item_from_dict(d: dict[str, Any]) -> QueueItem:
    """Convert an orchestrator result dict to a QueueItem."""
    return QueueItem(
        title=d.get("title", ""),
        student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
        student_uid=d.get("student_uid", ""),
        status=d.get("status") or "unknown",
        entity_type=d.get("entity_type"),
        exercise_name=d.get("exercise_name"),
        submission_uid=d.get("submission_uid", ""),
        feedback_count=d.get("feedback_count", 0),
        original_filename=d.get("original_filename"),
    )


def submission_row_from_dict(d: dict[str, Any]) -> SubmissionRow:
    """Convert an orchestrator result dict to a SubmissionRow."""
    return SubmissionRow(
        uid=d.get("uid", ""),
        title=d.get("title", ""),
        student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
        student_uid=d.get("student_uid", ""),
        status=d.get("status") or "unknown",
        feedback_count=d.get("feedback_count", 0),
        exercise_title=d.get("exercise_title"),
        original_filename=d.get("original_filename"),
    )
