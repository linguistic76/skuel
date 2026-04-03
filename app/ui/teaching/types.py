"""Teaching UI view model types.

Frozen dataclasses for teaching dashboard, queue, and detail components.
"""

from dataclasses import dataclass

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
    ku_uid: str = ""
    feedback_count: int = 0
    original_filename: str | None = None


@dataclass(frozen=True)
class ExerciseSummary:
    """Exercise card with submission counts."""

    uid: str = ""
    title: str = "Untitled Exercise"
    scope: str | None = None
    total_count: int = 0
    reviewed_count: int = 0
    pending_count: int = 0


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
class TeachingDashboardStats:
    """Overview dashboard statistics."""

    pending_count: int = 0
    total_students: int = 0
    total_exercises: int = 0
    total_groups: int = 0


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
