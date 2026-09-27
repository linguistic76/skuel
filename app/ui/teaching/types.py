"""Teaching UI view model types.

Frozen dataclasses for teaching queue and detail components, and the
dict-to-dataclass converters that build them.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.models.type_hints import UserUID


@dataclass(frozen=True)
class QueueItem:
    """A single item in the teacher review queue."""

    title: str = ""
    student_name: str = "Unknown"
    student_uid: str = ""
    status: str = "unknown"
    entity_type: str | None = None
    exercise_name: str | None = None
    revision: int | None = None  # the turn-in's version, printed beside the title
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
    """A submission as the teacher reviews it — the student's work and its place.

    ``exercise_uid`` is the turn-in's root exercise (the snapshot once the
    exercise is deleted); ``superseded`` marks a copy with a newer sibling
    this teacher can see, which takes no action.
    """

    title: str = "Untitled"
    entity_type: str | None = None
    status: str = ""
    student_name: str = "Unknown"
    student_uid: str = ""
    exercise_uid: str | None = None
    exercise_title: str | None = None
    revision: int | None = None
    exercise_instructions: str | None = None
    content: str | None = None
    original_filename: str | None = None
    superseded: bool = False


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
    revision: int | None = None
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
        revision=d.get("revision"),
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
        revision=d.get("revision"),
        original_filename=d.get("original_filename"),
    )


def submission_detail_from_dict(d: Mapping[str, Any]) -> SubmissionDetail:
    """Convert a teacher detail read (``SubmissionDetailResult``) to a SubmissionDetail.

    The one construction site: the review page and the per-student panel both
    render through it, so they cannot drift on which fields they carry.
    """
    return SubmissionDetail(
        title=d.get("title") or "Untitled",
        entity_type=d.get("entity_type"),
        status=(d.get("status") or "").lower(),
        student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
        student_uid=d.get("student_uid") or "",
        exercise_uid=d.get("exercise_uid"),
        exercise_title=d.get("exercise_title"),
        revision=d.get("revision"),
        exercise_instructions=d.get("exercise_instructions"),
        content=d.get("content"),
        original_filename=d.get("original_filename"),
        superseded=bool(d.get("superseded")),
    )
