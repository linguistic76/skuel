"""
Phase 3: EntryReport — The Loop's Response
==============================================

The evaluation entity. When a student submits work (Phase 2: UserEntry, ADR-054),
a teacher or AI responds with an EntryReport:

    Exercise → UserEntry → EntryReport → RevisedExercise → ...

Two sources, same EntityType, different ReportSource:

    ReportSource.HUMAN  → teacher uploads a .md file via TeacherReviewService
    ReportSource.LLM    → AI generates feedback via EntryReportService

assessment_outcome records the decision made:
    APPROVED        — teacher accepted the work; loop closes for this exercise
    NEEDS_REVISION  — teacher requests another attempt → RevisedExercise created
    AI_EVALUATED    — AI evaluated the submission (no teacher decision yet)

Graph pattern:
    (teacher:User)-[:OWNS]->(report:Entity:EntryReport)
    (report)-[:REPORT_FOR]->(entry:Entity:UserEntry)
    (report)-[:SHARES_WITH]->(student:User)  ← grants student read access

Note: subject_uid is GRAPH-NATIVE — projected from REPORT_FOR on read, not stored
as a Neo4j node property. Contrast with ActivityReport, which has no REPORT_FOR
edge and no subject_uid (it responds to patterns, not a single artifact).

Services:
    EntryReportService  — AI report generation (core/services/report/)
    TeacherReviewService   — teacher review workflow (core/services/report/)

See: /docs/architecture/REPORT_ARCHITECTURE.md
See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.entry_report_dto import EntryReportDTO

from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.enums.pipeline import ReportSource
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class EntryReport(UserOwnedEntity):
    """
    Immutable domain model for exercise reports (EntityType.ENTRY_REPORT).

    Extends UserOwnedEntity with 7 report-specific fields:
        processed_content   — the feedback body (LLM output or teacher prose)
        report_generated_at — timestamp of generation
        subject_uid         — GRAPH-NATIVE: UID of the submission being evaluated,
                              projected from the REPORT_FOR edge on read
        processor_type      — HUMAN (teacher) | LLM (AI)
        assessment_outcome  — APPROVED | NEEDS_REVISION | AI_EVALUATED
        report_file_path    — path to the uploaded .md file (HUMAN reports)
        assessment_score    — 0.0-1.0 for ASSESSMENT-scope exercises
        author_uid          — teacher UID for HUMAN reports; None for LLM

    Ownership vs authorship:
        user_uid (inherited)  — the student who OWNS the report (access control)
        author_uid            — the teacher who AUTHORED it (None for AI reports)
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.ENTRY_REPORT, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=ENTRY_REPORT, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.ENTRY_REPORT:
            raise ValueError(
                f"EntryReport constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # REPORT-SPECIFIC FIELDS
    # =========================================================================
    # LLM/teacher-generated analysis lives on ``processed_content`` (not the
    # inherited ``Entity.content`` field, which is reserved for user-drafted
    # text). Written by ``create_report_node`` as ``processed_content: $feedback``.
    processed_content: str | None = None
    report_generated_at: datetime | None = None
    # GRAPH-NATIVE: projected from the REPORT_FOR edge on read by
    # EntryReportBackend.get / list_for_submission, not stored as a
    # Neo4j node property. create_report_node writes the REPORT_FOR relationship;
    # reads hydrate this field via `RETURN n{.*, subject_uid: sub.uid}`.
    subject_uid: str | None = None  # UID of the submission this report is about
    processor_type: ReportSource | None = None  # HUMAN/LLM/AUTOMATIC
    assessment_outcome: AssessmentOutcome | None = None  # APPROVED/NEEDS_REVISION/AI_EVALUATED
    report_file_path: str | None = None  # Generated output file path
    assessment_score: float | None = None  # 0.0-1.0 score for ASSESSMENT-scope exercises
    # Authorship (decoupled from ownership):
    # user_uid (inherited) = student who OWNS the report (access ownership).
    # author_uid = teacher UID for HUMAN reports; None for LLM/AI reports.
    author_uid: str | None = None

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | EntryReportDTO") -> "EntryReport":
        """Create EntryReport from an EntityDTO or EntryReportDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "EntryReportDTO":
        """Convert to EntryReportDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.report.entry_report_dto import EntryReportDTO

        return domain_to_dto(self, EntryReportDTO)

    def __str__(self) -> str:
        return f"EntryReport(uid={self.uid}, title='{self.title}', subject={self.subject_uid})"

    def __repr__(self) -> str:
        return (
            f"EntryReport(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"processor_type={self.processor_type}, user_uid={self.user_uid}, "
            f"author_uid={self.author_uid})"
        )
