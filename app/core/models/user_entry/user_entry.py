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
                                      SUBMITTED_TO_GROUP (the feedback request)

Audience
--------
Declared at submit time via `UnifiedSharingService`, in two verbs (ADR-088):
a feedback request (`SUBMITTED_TO_GROUP`, read by the group's owning
teachers) and a share (`SHARES_WITH` / `SHARED_WITH_GROUP`, openable by its
recipients). There is no implicit student->teacher routing inferred from
`FULFILLS_EXERCISE` traversal + role check; the student (or the exercise's
groups by default when `pipeline=TEACHER_REVIEW` + exercise link)
explicitly submits to teacher groups.

Revision tracking
-----------------
The live revision is the `FULFILLS_EXERCISE {revision}` edge: a second
attempt against the same exercise creates a new `UserEntry` with a new edge
carrying `revision=2`. The turn-in writer stamps the same number onto the
node as `turn_in_revision`, beside the exercise snapshot, so the version
survives the exercise's deletion exactly as the title does (Submit & Share
arc R12). There is no `revision_number` node property.

Title
-----
The title is the student's (Submit & Share arc PR 7 ruling). A turn-in
handed in with no title is titled "<root exercise title> v<N>" by the
writer; every surface prints the exercise-and-version label beside the
title from the snapshot, never from the title.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.user_entry.user_entry_dto import UserEntryDTO

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.user_owned_entity import UserOwnedEntity

# The title an exchange shows for a turn-in whose exercise is gone and whose
# snapshot carries no title (a pre-snapshot turn-in the backfill could not
# resolve to a live node). Every live turn-in snapshots the real title.
EXERCISE_REMOVED_TITLE = "Exercise removed"

# The five stored periodic-note kinds (ADR-073: journal *sessions* are never
# stored; periodic notes are the one deliberate stored journal feature). THE
# membership vocabulary — every consumer (UserEntryService.ensure_periodic_note,
# IngestionTracker's similarity gate, journals routes, the EXTRACT_ACTIVITIES
# bridge gate) imports this one frozenset; a second literal list would drift.
#
# Membership is load-bearing in four places at once — adding a kind here turns
# on its page, its save guard, its bridge bypass and its similarity gate
# together. It is the ladder of nesting periods a note can plan against:
# a day sits in a week, in a month, in a quarter, in a year.
PERIODIC_NOTE_KINDS: frozenset[str] = frozenset(
    {"daily", "weekly", "monthly", "quarterly", "yearly"}
)


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
    # companion-retrieval Cypher (canon P3) — and it cannot be shared: a
    # ``group:`` / ``user:`` / ``public`` audience on it is refused at every
    # door, while a feedback request (``teachers`` / ``teacher:``) is still
    # allowed (ADR-088 §1). Orthogonal to ``je_use`` (ingestion consent); the
    # owner's own surfaces (/gradebook, search) still show private notes.
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
    # TURN-IN SNAPSHOT — the exchange key (Submit & Share arc R12)
    # =========================================================================
    # Stamped by the turn-in writer (``create_with_exercise_link``) and never
    # by the author: the root exercise's uid and its title as they were at
    # submission. An entry that carries them IS a turn-in; the GradeBook and
    # the exchange thread group on the uid and fall back to the title when
    # the exercise has since been deleted (``DETACH DELETE`` removes the
    # ``FULFILLS_EXERCISE`` edge, never a property), so an exchange survives
    # its exercise and renders as "Exercise removed" instead of dropping into
    # Other feedback. A living vault entry carries neither.
    turn_in_exercise_uid: str | None = None
    turn_in_exercise_title: str | None = None
    turn_in_revision: int | None = None

    # =========================================================================
    # HELPERS
    # =========================================================================

    def is_periodic_note(self) -> bool:
        """True when this entry is a stored periodic note (see PERIODIC_NOTE_KINDS).

        The metadata ``entry_kind`` stamp is the discriminator. Routes use it to
        keep the periodic-note page/save surface off every other entry kind, and
        the EXTRACT_ACTIVITIES bridge gate uses it to keep LLM inference away
        from periodic-note prose — the periodic-note parse contract (E3,
        docs/roadmap/done/calendar-periodic-notes-arc.md): entities come only from
        checkbox lines + explicit ``@context()`` markers, never inferred.
        """
        return self.metadata.get("entry_kind") in PERIODIC_NOTE_KINDS

    def is_vault_note(self) -> bool:
        """True when this entry was ingested from a vault file it can be written back to.

        The metadata ``vault_file_path`` stamp is the discriminator — the same
        one the outbound pass keys the task round-trip on (ADR-070). An
        uploaded or API-created entry has none: a 🆔 task line copied into it
        must never pull the task's provenance away from its vault note.
        """
        return bool(self.metadata.get("vault_file_path"))

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
    def from_dto(cls, dto: EntityDTO | UserEntryDTO) -> UserEntry:
        """Create UserEntry from an EntityDTO or UserEntryDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> UserEntryDTO:
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
