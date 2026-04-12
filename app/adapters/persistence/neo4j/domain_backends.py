"""Backwards-compatibility shim for the domain backends package.

All concrete backend classes now live in ``adapters.persistence.neo4j.backends``,
grouped into cluster files by concern. This module re-exports them so existing
``from adapters.persistence.neo4j.domain_backends import XBackend`` call sites
continue to work unchanged.

See: Step 3 of the neo4j persistence layer decomposition plan.
"""

from __future__ import annotations

from adapters.persistence.neo4j.backends import (
    ActivityReportBackend,
    ActivityReportGeneratorBackend,
    ChoicesBackend,
    EventsBackend,
    ExerciseBackend,
    ExerciseReportBackend,
    FormSubmissionBackend,
    FormTemplateBackend,
    GoalsBackend,
    GroupBackend,
    HabitsBackend,
    InteractionBackend,
    JournalInputBackend,
    JournalOutputBackend,
    KuBackend,
    LateralRelationshipBackend,
    LpBackend,
    NotificationBackend,
    PrinciplesBackend,
    PsBackend,
    ReportScheduleBackend,
    ResourceBackend,
    ReviewQueueBackend,
    RevisedExerciseBackend,
    SharingBackend,
    SubmissionsBackend,
    TasksBackend,
)

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
