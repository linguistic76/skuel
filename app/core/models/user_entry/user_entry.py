"""
UserEntry - Unified User-Authored Content (ADR-054)
====================================================

Frozen dataclass for all user-authored content: exercise turn-ins, journal
entries, uploaded files, free-form text. Replaces `Submission`,
`ExerciseSubmission`, `JeInput`, and `JeOutput`.

Dispatch model
--------------
The old split used `entity_type` as a type-based switch
(`EXERCISE_SUBMISSION` vs `JE_INPUT` vs `JE_OUTPUT`). `UserEntry` replaces
that with a `pipeline: Pipeline` field. `entity_type` is always
`EntityType.USER_ENTRY`; `pipeline` drives processing:

    Pipeline.NONE                     plain submission, no processing
    Pipeline.TRANSCRIBE               audio -> text (Deepgram)
    Pipeline.TRANSCRIBE_AND_STRUCTURE audio -> transcribed entry -> LLM-
                                      structured second entry (journal flow)
    Pipeline.LLM_SUMMARY              text/file -> LLM summary
    Pipeline.TEACHER_REVIEW           no processing; teacher review queue via
                                      SHARED_WITH_GROUP

Audience
--------
Declared at submit time via `UnifiedSharingService`. There is no implicit
student->teacher sharing inferred from `FULFILLS_EXERCISE` traversal +
role check; the student (or auto-share default when `pipeline=TEACHER_REVIEW`
+ exercise link) explicitly shares to teacher groups.

Revision tracking
-----------------
`revision_number` is NOT a node field. It lives on the
`FULFILLS_EXERCISE {revision}` edge. A second attempt against the same
exercise creates a new `UserEntry` with a new `FULFILLS_EXERCISE` edge
carrying `revision=2`.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.user_entry.user_entry_dto import UserEntryDTO

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.type_hints import UserUID
from core.models.user_owned_entity import UserOwnedEntity

# The three stored periodic-note kinds (ADR-073: journal *sessions* are never
# stored; periodic notes are the one deliberate stored journal feature). THE
# membership vocabulary — every consumer (UserEntryService.ensure_periodic_note,
# IngestionTracker's similarity gate, journals routes, the EXTRACT_ACTIVITIES
# bridge gate) imports this one frozenset; a second literal list would drift.
PERIODIC_NOTE_KINDS: frozenset[str] = frozenset({"daily", "weekly", "monthly"})


@dataclass(frozen=True, kw_only=True)
class UserEntry(UserOwnedEntity):
    """
    Immutable domain model for unified user-authored content.

    Inherits all common fields from `UserOwnedEntity` (identity, content,
    status, sharing, meta, embedding, user_uid, priority) and adds the
    file + processing + modality fields needed for any user-authored
    artifact.

    `entity_type` is forced to `EntityType.USER_ENTRY` in `__post_init__`.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.USER_ENTRY, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=USER_ENTRY, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.USER_ENTRY:
            raise ValueError(
                f"UserEntry constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # FILE (uploads) — all nullable; a text-only entry has none of these
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None  # MIME type (e.g., "audio/mpeg")

    # =========================================================================
    # PROCESSING
    # =========================================================================
    pipeline: Pipeline = Pipeline.NONE  # Dispatch discriminator
    # ``private: true`` frontmatter — the note never grows a vector: no entity
    # embedding, no :ContentChunk subtree, plus a hard WHERE exclusion in every
    # companion-retrieval Cypher (canon P3). Gates companion retrieval ONLY —
    # orthogonal to ``visibility`` (sharing) and ``je_use`` (ingestion consent);
    # the owner's own surfaces (/gradebook, search) still show private notes.
    private: bool = False
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None  # Pipeline-specific instructions (e.g. LLM prompt)
    journal_mode: str | None = None  # JournalMode value captured at upload time
    max_retention: int | None = None  # FIFO cleanup limit (None = permanent)

    # =========================================================================
    # MODALITY — how the entry was created (orthogonal to pipeline, per ADR §1)
    # =========================================================================
    modality: SubmissionModality | None = None

    # =========================================================================
    # DECLARED EXERCISE INTENT — vault living channel
    # =========================================================================
    # The exercise this entry is being worked against, as declared by the
    # author (``fulfills_exercise_uid:`` frontmatter on a deterministic-uid
    # vault file, or the create request). This is INTENT, not the turn-in:
    # the turn-in truth stays on the ``FULFILLS_EXERCISE {revision}`` edge,
    # which only frozen submission copies carry. A living vault entry has
    # the property and never the edge; removing the frontmatter line removes
    # the property on the next sync (intent withdrawn). Mirrors the
    # ``Exercise.path_step_uid`` membership-property precedent.
    fulfills_exercise_uid: str | None = None

    # =========================================================================
    # TITLE GENERATION — ports Submission.generate_exercise_title unchanged;
    # revision is passed explicitly by the caller (it lives on the edge, not
    # the node).
    # =========================================================================

    @classmethod
    def generate_exercise_title(
        cls,
        exercise_title: str,
        user_uid: UserUID,
        revision_number: int = 1,
        revision_date: date | None = None,
    ) -> str:
        """Auto-generate the canonical exercise turn-in title.

        Format: {Exercise Title} — {user_id}
        Revision: {Exercise Title} — {user_id} #{revision_number}, {Mar 02}
        """
        user_id = user_uid.removeprefix("user_")
        base = f"{exercise_title} \u2014 {user_id}"
        if revision_number > 1:
            date_str = (revision_date or date.today()).strftime("%b %d")
            return f"{base} #{revision_number}, {date_str}"
        return base

    # =========================================================================
    # HELPERS
    # =========================================================================

    def is_periodic_note(self) -> bool:
        """True when this entry is a stored periodic note (daily/weekly/monthly).

        The metadata ``entry_kind`` stamp is the discriminator. Routes use it to
        keep the periodic-note page/save surface off every other entry kind, and
        the EXTRACT_ACTIVITIES bridge gate uses it to keep LLM inference away
        from periodic-note prose — the periodic-note parse contract (E3,
        docs/roadmap/done/calendar-periodic-notes-arc.md): entities come only from
        checkbox lines + explicit ``@context()`` markers, never inferred.
        """
        return self.metadata.get("entry_kind") in PERIODIC_NOTE_KINDS

    def get_processing_duration(self) -> float | None:
        """Get processing duration in seconds, or None if not applicable."""
        if not self.processing_started_at or not self.processing_completed_at:
            return None
        delta = self.processing_completed_at - self.processing_started_at
        if isinstance(delta, timedelta):
            return delta.total_seconds()
        try:
            return float(delta.seconds)
        except AttributeError:
            try:
                return float(delta)
            except (TypeError, ValueError):  # fmt: skip
                return None

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of content (body text or processed content)."""
        text = self.content or self.processed_content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this entry exists (pipeline-aware)."""
        if self.description:
            return self.description
        if self.summary:
            return self.summary
        return f"UserEntry(pipeline={self.pipeline.value}): {self.title}"

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | UserEntryDTO") -> "UserEntry":
        """Create UserEntry from an EntityDTO or UserEntryDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "UserEntryDTO":
        """Convert UserEntry to domain-specific UserEntryDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.user_entry.user_entry_dto import UserEntryDTO

        return domain_to_dto(self, UserEntryDTO)

    def __str__(self) -> str:
        return f"UserEntry(uid={self.uid}, pipeline={self.pipeline.value}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"UserEntry(uid='{self.uid}', pipeline={self.pipeline}, "
            f"title='{self.title}', status={self.status}, user_uid={self.user_uid})"
        )
