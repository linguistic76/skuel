"""
UserEntry Request Models (ADR-054)
===================================

Pydantic request models for the unified user-entry API. Replaces
`SubmissionCreateRequest` and the implicit per-service request shapes
used by the journal and exercise submission flows.

Audience is first-class on create, in one vocabulary (ADR-088): `audience`
is an `AudienceSpec` — `teachers` / `teacher:<group_uid>` file a feedback
request (`SUBMITTED_TO_GROUP`, TEACHER_REVIEW only), `group:<uid>` /
`user:<username>` share, `public` publishes, `private` names no one. An
absent audience on `pipeline=TEACHER_REVIEW` means `teachers`. There is no
implicit role-based audience inference.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
See: /docs/decisions/ADR-088-submit-and-share.md
"""

from typing import Any

from pydantic import Field, field_validator

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.request_base import CreateRequestBase, UpdateRequestBase
from core.models.type_hints import EntityUID
from core.models.user_entry.audience import AudienceSpec


class UserEntryCreateRequest(CreateRequestBase):
    """
    Create a `UserEntry`.

    One request covers every user-authored creation path: exercise
    turn-ins, journal audio uploads, free-form text, LLM-summary jobs,
    and plain file uploads. `pipeline` discriminates processing; the
    audience fields declare who sees the result.
    """

    # -------------------------------------------------------------------------
    # Core content
    # -------------------------------------------------------------------------
    uid: str | None = Field(
        default=None,
        description=(
            "Caller-supplied deterministic UID (e.g. vault note 'ue:daily:2026-06-16'). "
            "When set, the service upserts (MERGE-on-uid) so re-syncing an edited note "
            "updates in place; when None a random 'ue_<...>' UID is minted and the entry "
            "is created fresh."
        ),
    )
    title: str = Field(min_length=1, max_length=200, description="Entry title")
    content: str | None = Field(default=None, description="Text content (if any)")
    description: str | None = Field(default=None, description="Short entry description")
    status: EntityStatus | None = Field(
        default=None,
        description=(
            "Authored status (e.g. from vault frontmatter). None → pipeline "
            "default: SUBMITTED for TEACHER_REVIEW, ACTIVE otherwise."
        ),
    )
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form metadata")

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------
    pipeline: Pipeline = Field(
        default=Pipeline.NONE,
        description="Processing pipeline — dispatch discriminator",
    )
    private: bool = Field(
        default=False,
        description=(
            "Companion-retrieval opt-out (``private: true`` frontmatter). The "
            "note is never embedded or chunked and is hard-excluded from every "
            "companion-retrieval query, and it cannot be shared: a `group:`, "
            "`user:` or `public` audience on it is refused (ADR-088 §1). A "
            "feedback request (`teachers` / `teacher:`) is still allowed. "
            "Orthogonal to `je_use` (ingestion consent)."
        ),
    )
    modality: SubmissionModality | None = Field(
        default=None, description="How the entry was created (FILE_UPLOAD, STRUCTURED_FORM, ...)"
    )
    instructions: str | None = Field(default=None, description="Pipeline-specific instructions")
    journal_mode: str | None = Field(
        default=None, description="JournalMode captured at upload time"
    )

    # -------------------------------------------------------------------------
    # File metadata (populated by upload handler, not user input)
    # -------------------------------------------------------------------------
    original_filename: str | None = Field(default=None, description="Uploaded filename")
    file_path: str | None = Field(default=None, description="Server file path")
    file_size: int | None = Field(default=None, ge=0, description="File size in bytes")
    file_type: str | None = Field(default=None, description="MIME type")

    # -------------------------------------------------------------------------
    # Relationships — all optional, drive edge creation in the service
    # -------------------------------------------------------------------------
    fulfills_exercise_uid: EntityUID | None = Field(
        default=None,
        description=(
            "Exercise this entry fulfills. With pipeline=TEACHER_REVIEW, "
            "`teachers` (the default) files the feedback request with the "
            "exercise's assigned groups the submitter belongs to "
            "(SUBMITTED_TO_GROUP)."
        ),
    )
    about_path_step_uid: EntityUID | None = Field(
        default=None, description="PathStep this entry is situated in"
    )
    transforms_of_uid: EntityUID | None = Field(
        default=None,
        description=(
            "Source UserEntry this one transforms (set by the "
            "TRANSCRIBE_AND_STRUCTURE pipeline when producing the second entry)"
        ),
    )

    # -------------------------------------------------------------------------
    # Audience — declared at submit time in the one vocabulary (ADR-088),
    # resolved into links by AudienceResolver after the entry persists
    # -------------------------------------------------------------------------
    audience: AudienceSpec = Field(
        default_factory=AudienceSpec,
        description=(
            "Who the entry is for, in the one audience vocabulary: `teachers`, "
            "`teacher:<group_uid>` (a feedback request — pipeline=TEACHER_REVIEW "
            "only), `group:<uid>`, `user:<username>` (a share — the user must "
            "share a group with you), `public` (TEACHER-gated), `private` "
            "(exclusive). One value or a list. Absent on TEACHER_REVIEW means "
            "`teachers`; absent elsewhere means no links."
        ),
    )

    @field_validator("audience", mode="before")
    @classmethod
    def _parse_audience(cls, raw: object) -> AudienceSpec:
        """One parser for every door: a value, a list, or an already-parsed spec."""
        parsed = AudienceSpec.parse(raw)
        if parsed.is_error:
            raise ValueError(parsed.expect_error().message)
        return parsed.value


class UserEntryUpdateRequest(UpdateRequestBase):
    """
    Update a `UserEntry`.

    Content edits only. The audience is an independent graph concern, not a
    field here: it is declared at submit time (ADR-088 — the create request's
    `audience`, or a vault note's `audience:`) and resolved into edges by
    `AudienceResolver`. After that, a vault note widens it by re-syncing with
    a wider `audience:`; nothing narrows it, and a form-submitted entry has no
    post-submit door yet — see `docs/roadmap/sharing-http-door.md`.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class UserEntryProcessRequest(CreateRequestBase):
    """
    Trigger processing on an existing `UserEntry`.

    Used by the POST /api/user-entries/process endpoint. The dispatcher
    reads `pipeline` and (optionally) overrides `instructions` for this run.
    """

    uid: EntityUID = Field(description="UserEntry UID to process")
    pipeline: Pipeline | None = Field(
        default=None,
        description=(
            "Override the entry's stored pipeline for this run. Leave "
            "unset to use the entry's existing `pipeline` field."
        ),
    )
    instructions: str | None = Field(default=None, description="Override pipeline instructions")
    force: bool = Field(
        default=False,
        description="Re-run override for the completed-extraction guard (EXTRACT_ACTIVITIES)",
    )
