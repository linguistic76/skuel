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
        JOURNAL                   — Journals domain entry; processing driven by
                                    JournalTier (FOUNDER: three-stage DNWF,
                                    STANDARD: single-response). Always private.
        REFERENCE                 — Archive/training material (je_raw/, je_pro/).
                                    Stored as-is, no processing. Excluded from
                                    UserContext counts and Askesis context.
                                    Always private.
    """

    NONE = "none"
    TRANSCRIBE = "transcribe"
    TRANSCRIBE_AND_STRUCTURE = "transcribe_and_structure"
    LLM_SUMMARY = "llm_summary"
    EXTRACT_ACTIVITIES = "extract_activities"
    TEACHER_REVIEW = "teacher_review"
    JOURNAL = "journal"
    REFERENCE = "reference"

    def allows_sharing(self) -> bool:
        """Whether a UserEntry on this pipeline may carry a non-private audience.

        `TRANSCRIBE_AND_STRUCTURE` is the journal pipeline. Journals inherit
        the historical `JeInput`/`JeOutput` privacy norm — raw audio + its
        LLM-structured output are personal reflection, not shareable
        artifacts. Enforced pre-persist in `_validate_audience`; the `/submit`
        form hides the audience picker when this returns `False` (the
        dedicated `/journals/submit` form never offered one).

        See: ADR-054 §5 (Journal input → output, preserved).
        """
        return self not in (
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            Pipeline.JOURNAL,
            Pipeline.REFERENCE,
        )


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
