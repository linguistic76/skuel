"""Backend cluster package — re-exports all domain backends.

Backends are grouped into cluster files by concern; this package exposes
them at a single import surface. Callers should import from the specific
cluster module (e.g. ``backends.activity_backends``) — this barrel exists
for introspection and MyPy override convenience.
"""

from __future__ import annotations

from adapters.persistence.neo4j.backends.activity_backends import (
    ChoicesBackend,
    EventsBackend,
    GoalsBackend,
    HabitsBackend,
    PrinciplesBackend,
    TasksBackend,
)
from adapters.persistence.neo4j.backends.collab_backends import (
    GroupBackend,
    LateralRelationshipBackend,
    NotificationBackend,
    ReviewQueueBackend,
)
from adapters.persistence.neo4j.backends.curriculum_backends import (
    ExerciseBackend,
    ExerciseReportBackend,
    KuBackend,
    LpBackend,
    PsBackend,
    RevisedExerciseBackend,
)
from adapters.persistence.neo4j.backends.forms_backends import (
    FormSubmissionBackend,
    FormTemplateBackend,
)
from adapters.persistence.neo4j.backends.journal_backends import (
    JournalInputBackend,
    JournalOutputBackend,
)
from adapters.persistence.neo4j.backends.misc_backends import (
    ActivityReportBackend,
    ActivityReportGeneratorBackend,
    InteractionBackend,
    ReportScheduleBackend,
    ResourceBackend,
)
from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.submissions_backend import SubmissionsBackend

__all__ = [
    "ActivityReportBackend",
    "ActivityReportGeneratorBackend",
    "ChoicesBackend",
    "EventsBackend",
    "ExerciseBackend",
    "ExerciseReportBackend",
    "FormSubmissionBackend",
    "FormTemplateBackend",
    "GoalsBackend",
    "GroupBackend",
    "HabitsBackend",
    "InteractionBackend",
    "JournalInputBackend",
    "JournalOutputBackend",
    "KuBackend",
    "LateralRelationshipBackend",
    "LpBackend",
    "NotificationBackend",
    "PrinciplesBackend",
    "PsBackend",
    "ReportScheduleBackend",
    "ResourceBackend",
    "ReviewQueueBackend",
    "RevisedExerciseBackend",
    "SharingBackend",
    "SubmissionsBackend",
    "TasksBackend",
]
