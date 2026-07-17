"""
ActivityReport - Activity Report Domain Model
==============================================

Frozen dataclass for AI-generated (or human-written) feedback about a user's
activity patterns over a time period (EntityType.ACTIVITY_REPORT).

Distinct from EntryReport — which responds to a specific submitted artifact.
ActivityReport responds to a user's aggregate behavior over a time window.

ReportSource discriminates the source:
    ReportSource.AUTOMATIC — system-generated on a schedule (default)
    ReportSource.LLM       — AI reasoned over activity graph data (on-demand)
    ReportSource.HUMAN     — admin reviewed activity domains manually

Inherits from UserOwnedEntity directly (NOT Submission — no file fields apply).

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.report.activity_report_dto import ActivityReportDTO

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import ReportSource
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class ActivityReport(UserOwnedEntity):
    """
    Immutable domain model for Activity Report entities (EntityType.ACTIVITY_REPORT).

    Represents feedback about a user's aggregate activity patterns over a time period.
    Distinct from EntryReport (which responds to a specific submission artifact).

    Fields:
        processor_type: Source of the feedback (AUTOMATIC/LLM/HUMAN)
        subject_uid: User whose activity this feedback is about
        time_period: Sliding window (7d, 14d, 30d, 90d)
        period_start: Exact start of the analysis window
        period_end: Exact end of the analysis window
        domains_covered: Activity domains included in analysis
        depth: Analysis depth (summary, standard, detailed)
        processed_content: Generated feedback text (LLM output or human-written)
        processing_error: Error message if generation failed
        insights_referenced: UIDs of active insights used in generation
        user_annotation: Additive commentary the user adds alongside AI synthesis
        user_revision: User-curated replacement for sharing (overrides processed_content)
        annotation_mode: Which mode the user chose ("additive" | "revision" | None)
        annotation_updated_at: When the annotation was last saved
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.ACTIVITY_REPORT, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=ACTIVITY_REPORT, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.ACTIVITY_REPORT:
            raise ValueError(
                f"ActivityReport constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # PROCESSOR
    # =========================================================================
    processor_type: ReportSource | None = None

    # =========================================================================
    # SUBJECT
    # =========================================================================
    subject_uid: str | None = None  # user_uid this feedback is about

    # =========================================================================
    # TIME WINDOW
    # =========================================================================
    time_period: str | None = None  # "7d" | "14d" | "30d" | "90d"
    period_start: datetime | None = None
    period_end: datetime | None = None

    # =========================================================================
    # ANALYSIS CONFIGURATION
    # =========================================================================
    domains_covered: tuple[str, ...] = field(default_factory=tuple)  # activity domain names
    depth: str | None = None  # summary | standard | detailed

    # =========================================================================
    # CONTENT
    # =========================================================================
    processed_content: str | None = None  # LLM output or human-written feedback
    processing_error: str | None = None

    # =========================================================================
    # INSIGHT REFERENCES
    # =========================================================================
    insights_referenced: tuple[str, ...] = field(default_factory=tuple)  # insight UIDs

    # =========================================================================
    # ANNOTATION
    # =========================================================================
    user_annotation: str | None = None  # Additive commentary alongside AI synthesis
    user_revision: str | None = None  # User-curated replacement for sharing
    annotation_mode: str | None = None  # "additive" | "revision" | None
    annotation_updated_at: datetime | None = None

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def create(
        cls,
        user_uid: UserUID,
        subject_uid: str,
        content: str,
        processor_type: ReportSource,
        period_start: datetime,
        period_end: datetime,
        time_period: str,
        domains: list[str] | None = None,
        depth: str = "standard",
        processing_error: str | None = None,
        insights_referenced: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "ActivityReport":
        """
        Factory method — generates uid, formats title, constructs ActivityReport.

        Called by both ProgressReportGenerator (LLM/AUTOMATIC) and
        ActivityReportService (HUMAN). The processor_type discriminates the source.
        """
        from core.utils.uid_generator import UIDGenerator

        uid = UIDGenerator.generate_uid("ar")
        title = (
            f"Activity Report — {period_start.strftime('%b %d')} "
            f"to {period_end.strftime('%b %d, %Y')}"
        )
        return cls(
            uid=uid,
            title=title,
            entity_type=EntityType.ACTIVITY_REPORT,
            user_uid=user_uid,
            subject_uid=subject_uid,
            processed_content=content,
            processor_type=processor_type,
            period_start=period_start,
            period_end=period_end,
            time_period=time_period,
            domains_covered=tuple(domains) if domains else (),
            depth=depth,
            processing_error=processing_error,
            insights_referenced=insights_referenced,
            metadata=metadata or {},
        )

    @classmethod
    def from_dto(cls, dto: "EntityDTO | ActivityReportDTO") -> "ActivityReport":
        """Create ActivityReport from an EntityDTO or ActivityReportDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "ActivityReportDTO":
        """Convert ActivityReport to domain-specific ActivityReportDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.report.activity_report_dto import ActivityReportDTO

        return domain_to_dto(self, ActivityReportDTO)

    def __str__(self) -> str:
        return f"ActivityReport(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"ActivityReport(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"time_period={self.time_period}, processor_type={self.processor_type})"
        )
