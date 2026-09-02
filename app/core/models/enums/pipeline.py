"""
Pipeline Enum — user-entry processing dispatch.

Replaces `ProcessorType` for the "what happens to a user entry" dimension.
Per ADR-054: `ProcessorType` splits into `Pipeline` (entry processing) and
`ReportSource` (report provenance).

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from enum import StrEnum


class Pipeline(StrEnum):
    """
    Processing pipeline for a `UserEntry`.

    Drives `UserEntryProcessingService.process()` dispatch. The entry's
    `entity_type` is always `user_entry`; `pipeline` discriminates what
    (if anything) happens to it after creation.

    Values:
        NONE                      — no processing; plain submission / text entry
        TRANSCRIBE                — audio → text (Deepgram)
        TRANSCRIBE_AND_STRUCTURE  — audio → transcribed entry → LLM-structured
                                    second entry (legacy; preserved for existing
                                    UserEntry nodes)
        LLM_SUMMARY               — text/file → LLM summary
        EXTRACT_ACTIVITIES        — text → DSL parse → real entities (tasks,
                                    goals, habits, ...) with EXTRACTED_FROM
                                    provenance (ADR-069)
        TEACHER_REVIEW            — no processing; entry waits in teacher queue
                                    via SHARED_WITH_GROUP
        REFERENCE                 — RESERVED for the planned per-user stored
                                    journal-exemplar layer (private, no
                                    processing, excluded from UserContext /
                                    Askesis). Has no producer today: je_raw/ +
                                    je_pro/ are read *off disk* as few-shot
                                    processing-style exemplars; exemplar use
                                    persists ZERO (ADR-073 §4). (A je_pro file
                                    may separately consent to ingestion via
                                    frontmatter — that stores a KNOWLEDGE
                                    entry, not a REFERENCE one; 2026-07-11
                                    amendment.) This value stores the future
                                    #2b split — per-user styled exemplars stored
                                    privately — distinct from the #1 global
                                    (product-default) exemplar set. Registered
                                    PLANNED until that layer is built.
        KNOWLEDGE                 — "Developed files": the user's own notes in
                                    the vault ``knowledge/`` doorway, shared to
                                    teach SKUEL about them. Stored as-is, no
                                    processing. Unlike REFERENCE it FEEDS
                                    UserContext (the personal-notes context
                                    digest) rather than being archived; but it
                                    is not a learning-loop submission, so it is
                                    excluded from submission counts.
    """

    NONE = "none"
    TRANSCRIBE = "transcribe"
    TRANSCRIBE_AND_STRUCTURE = "transcribe_and_structure"
    LLM_SUMMARY = "llm_summary"
    EXTRACT_ACTIVITIES = "extract_activities"
    TEACHER_REVIEW = "teacher_review"
    REFERENCE = "reference"
    KNOWLEDGE = "knowledge"

    def allows_sharing(self) -> bool:
        """Whether a UserEntry on this pipeline may carry a non-private audience.

        Two pipelines are private by contract: `TRANSCRIBE_AND_STRUCTURE` (the
        legacy audio → structured-entry chain — raw audio and its LLM output
        are personal reflection, the historical `JeInput`/`JeOutput` norm) and
        `REFERENCE` (the reserved per-user exemplar layer, ADR-073 §4). Enforced
        pre-persist in `AudienceResolver.validate` and coerced to
        `audience=private` at the vault/YAML door (`build_user_entry_request`);
        the `/submit` form hides the audience picker when this returns `False`.

        `Pipeline.JOURNAL` was deleted 2026-09-02 — every role it had has a
        successor: a journal session is ephemeral (ADR-073) or an opt-in
        `:ConversationSession` (ADR-078); a vault context note is `KNOWLEDGE`
        (with `private:` as the retrieval opt-out). Never reintroduce it.

        See: ADR-054 §5 (Journal input → output, preserved).
        """
        return self not in (
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            Pipeline.REFERENCE,
        )

    def shares_by_default(self) -> bool:
        """Whether an absent ``audience:`` at the vault/YAML door means "my teachers".

        Submission-shaped pipelines keep ADR-054's default — the student is
        handing something in, so it goes to every group they are a student of
        (``AudienceResolver.resolve_default_teachers``). ``KNOWLEDGE`` does not:
        a developed-files note teaches SKUEL about the user and is theirs unless
        they say otherwise (ruling 2026-09-02), so an absent audience means
        private and only an explicit ``audience:`` shares it. The never-shareable
        pair is ``False`` here too; ``allows_sharing`` coerces them regardless.
        """
        return self.allows_sharing() and self is not Pipeline.KNOWLEDGE


class JeUse(StrEnum):
    """
    Dual-duty scoping for a ``je_pro/`` vault file (ADR-073 § je_pro doorway).

    je_pro files serve two roles: the processed half of stem-matched few-shot
    exemplar pairs (with ``je_raw/``), and — when frontmatter-consented — a
    stored understanding channel. ONE enum field scopes both (two booleans were
    rejected: they can self-contradict). TWO consumers must respect it:
    the exemplar loader (``_load_journal_exemplars``) skips UNDERSTANDING
    files, and the ingestion gate (``je_pro_skip_reason``) skips EXEMPLAR
    files.

    Values:
        BOTH           — exemplar AND understanding (the default when absent)
        EXEMPLAR       — processing-style exemplar only; never ingested
                         ("learn nothing about me from this")
        UNDERSTANDING  — understanding channel only; never used as a
                         processing-style exemplar
    """

    BOTH = "both"
    EXEMPLAR = "exemplar"
    UNDERSTANDING = "understanding"

    @classmethod
    def from_string(cls, value: object) -> JeUse | None:
        """Parse a frontmatter ``je_use:`` value.

        Absent/empty → BOTH (the documented default). Unrecognized → ``None``
        so callers decide the failure mode (the ingestion gate fails closed —
        garbled consent is not consent; the exemplar loader also skips).
        """
        if value is None or not str(value).strip():
            return cls.BOTH
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return None


class ProcessingMode(StrEnum):
    """
    How a journals upload is processed (ADR-073 zero-persistence file/audio door).

    Chosen in the upload composer and carried on the wire as the
    ``processing_mode`` form field. Drives BOTH upload doors: the single-file
    path (``_process_single_upload``) and the batch path
    (``JournalBatchService.run_batch_over_dir``).

    **Deliberately NOT ``Pipeline``.** The near-identical member names are a
    real trap: ``Pipeline`` is a *persisted* ``UserEntry`` field carrying
    audience semantics (``Pipeline.allows_sharing()``), while this door
    persists **nothing** and never creates a ``UserEntry`` (ADR-073). Reusing
    ``Pipeline`` here would re-couple precisely what ADR-073 separated.

    Values:
        TRANSCRIBE_ONLY             — audio → raw transcript in ``je_out/`` (default)
        TRANSCRIBE_AND_INSTRUCTIONS — audio → transcript → LLM-structured ``_out.md``
        INSTRUCTIONS_ONLY           — text file → LLM-compiled ``_out.md``

    See: /docs/decisions/ADR-073-journals-zero-persistence-vault-memory.md
    """

    TRANSCRIBE_ONLY = "transcribe_only"
    TRANSCRIBE_AND_INSTRUCTIONS = "transcribe_and_instructions"
    INSTRUCTIONS_ONLY = "instructions_only"

    @classmethod
    def default(cls) -> ProcessingMode:
        """The composer's default selection — mirrors the Alpine initial state."""
        return cls.TRANSCRIBE_ONLY

    @classmethod
    def from_string(cls, value: object) -> ProcessingMode | None:
        """Parse a ``processing_mode`` form value.

        Absent/empty → ``default()`` (the form's own default, unchanged
        behaviour). Unrecognized → ``None`` so callers fail **closed**: an
        unknown mode must be rejected before any Deepgram or LLM spend, on
        both upload doors. Mirrors ``JeUse.from_string``'s contract rather
        than ``JournalMode``'s defaulting one — silently coercing a bad value
        to a default is what let an unknown mode reach the transcribe tail
        after burning quota.
        """
        if value is None or not str(value).strip():
            return cls.default()
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return None


class ReportSource(StrEnum):
    """
    Provenance of a report (`EntryReport`, `ActivityReport`).

    Replaces `ProcessorType` for the "who authored this report" dimension.
    A report always has a source; a user entry always has a pipeline.
    The two concepts are orthogonal and were previously conflated.

    Values:
        HUMAN      — teacher-authored feedback
        LLM        — AI-generated (OpenAI et al.)
        HYBRID     — LLM draft + human review
        AUTOMATIC  — system-determined (rubric auto-scoring, etc.)
    """

    HUMAN = "human"
    LLM = "llm"
    HYBRID = "hybrid"
    AUTOMATIC = "automatic"

    def get_display_name(self) -> str:
        return {
            ReportSource.HUMAN: "Human Review",
            ReportSource.LLM: "AI Processing",
            ReportSource.HYBRID: "Hybrid (AI + Human)",
            ReportSource.AUTOMATIC: "Automatic",
        }[self]

    def get_short_label(self) -> str:
        """Compact provenance label for badges and preview cards."""
        return {
            ReportSource.HUMAN: "Teacher",
            ReportSource.LLM: "AI",
            ReportSource.HYBRID: "AI + Teacher",
            ReportSource.AUTOMATIC: "Auto",
        }[self]


class ExchangeStatus(StrEnum):
    """
    Where one (student, exercise) exchange stands, from the student's side.

    Derived per exercise line on the GradeBook (feedback-loop UX arc 2 C2) —
    never stored on a node. Exactly one status per line:

        WAITING            — latest entry has no report yet; ball with reviewer
        FEEDBACK_RECEIVED  — a report exists on the latest entry
        REVISION_REQUESTED — latest entry status is revision_requested;
                             ball back with the student
    """

    WAITING = "waiting"
    FEEDBACK_RECEIVED = "feedback_received"
    REVISION_REQUESTED = "revision_requested"

    @classmethod
    def derive(cls, latest_entry_status: str | None, has_report: bool) -> ExchangeStatus:
        """The one derivation rule for an exchange line's status.

        ``revision_requested`` on the latest entry wins even though that
        entry has a report — the revision request IS the feedback, and the
        next move is the student's.
        """
        if latest_entry_status == cls.REVISION_REQUESTED.value:
            return cls.REVISION_REQUESTED
        if has_report:
            return cls.FEEDBACK_RECEIVED
        return cls.WAITING

    def get_display_name(self) -> str:
        return {
            ExchangeStatus.WAITING: "Waiting",
            ExchangeStatus.FEEDBACK_RECEIVED: "Feedback received",
            ExchangeStatus.REVISION_REQUESTED: "Revision requested",
        }[self]

    def get_badge_class(self) -> str:
        """Tailwind classes for the line's status text / chip accent."""
        return {
            ExchangeStatus.WAITING: "bg-amber-100 text-amber-800",
            ExchangeStatus.FEEDBACK_RECEIVED: "bg-emerald-100 text-emerald-800",
            ExchangeStatus.REVISION_REQUESTED: "bg-orange-100 text-orange-800",
        }[self]
