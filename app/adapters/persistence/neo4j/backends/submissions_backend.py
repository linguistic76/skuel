"""
SubmissionsBackend — Persistence layer for the learning loop.

Owns the Cypher for all three active loop phases:
    Phase 2 (ExerciseSubmission) — CRUD, sharing, status transitions
    Phase 3 (ExerciseReport)     — create_report_node (REPORT_FOR), teacher review ops
    Phase 4 (atomic transition)  — create_report_and_revised_exercise in one Cypher tx

All behavior lives in five mixin files aligned to loop phases:
    _submission_crud_mixin.py          — Phase 2: submission CRUD + teacher feedback state
    _submission_lifecycle_mixin.py     — Phase 2→3: FULFILLS_EXERCISE, status updates
    _submission_assessment_mixin.py    — Phase 3: teacher review operations
    _submission_report_query_mixin.py  — Phase 3: REPORT_FOR traversals (reads)
    _submission_content_mixin.py       — all phases: enrichment context

Services that reach this backend:
    SubmissionsService       — Phase 2 (submit_file, submit_form, sharing)
    ExerciseReportService    — Phase 3 (AI report generation)
    TeacherReviewService     — Phase 3/4 (review queue, revision, approval)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j._submission_assessment_mixin import (
    _SubmissionAssessmentMixin,
)
from adapters.persistence.neo4j._submission_content_mixin import _SubmissionContentMixin
from adapters.persistence.neo4j._submission_crud_mixin import _SubmissionCrudMixin
from adapters.persistence.neo4j._submission_lifecycle_mixin import (
    _SubmissionLifecycleMixin,
)
from adapters.persistence.neo4j._submission_report_query_mixin import (
    _SubmissionReportQueryMixin,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.submissions.submission import Submission

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.journal.je_input import JeInput  # noqa: F401
    from core.models.journal.je_output import JeOutput  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401
    from core.models.submissions.report_schedule import ReportSchedule  # noqa: F401


class SubmissionsBackend(  # type: ignore[misc]  # Mixin MRO overrides are intentional
    _SubmissionCrudMixin,
    _SubmissionLifecycleMixin,
    _SubmissionAssessmentMixin,
    _SubmissionReportQueryMixin,
    _SubmissionContentMixin,
    UniversalNeo4jBackend[Submission],
):
    """
    Domain backend for Submission entities.

    Uses NeoLabel.ENTITY (not NeoLabel.SUBMISSION) because submissions span
    2 EntityTypes: SUBMISSION and EXERCISE_REPORT (via SubmissionsBackend).

    All behavior lives in the 5 mixins above:
        * _SubmissionCrudMixin       — content search, feedback counts, teacher EMA state
        * _SubmissionLifecycleMixin  — exercise-processing + FULFILLS/temporal/thematic rels
        * _SubmissionAssessmentMixin — assessment scoring + teacher-review workflow
        * _SubmissionReportQueryMixin — learning-loop chain + report cross-joins
        * _SubmissionContentMixin    — journal processing context + exercise-instruction reads

    Sharing and access control live in SharingBackend + UnifiedSharingService,
    operating across all entity types.
    """
