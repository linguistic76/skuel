"""
UserEntry Request Models (ADR-054)
===================================

Pydantic request models for the unified user-entry API. Replaces
`SubmissionCreateRequest` and the implicit per-service request shapes
used by the journal and exercise submission flows.

Audience is first-class on create: when a student submits for teacher
review, the audience is declared on the request (or defaulted to the
exercise's assigned groups when `pipeline=TEACHER_REVIEW` + exercise
link). There is no implicit role-based audience inference.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from typing import Any

from pydantic import Field

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.request_base import CreateRequestBase, UpdateRequestBase
from core.models.type_hints import EntityUID


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
            "companion-retrieval query. Orthogonal to `visibility` (sharing) "
            "and `je_use` (ingestion consent)."
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
            "Exercise this entry fulfills. When set with "
            "pipeline=TEACHER_REVIEW and no explicit audience, the service "
            "auto-shares to the exercise's assigned groups."
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
    # Audience — declared at submit time, consumed by UnifiedSharingService
    # -------------------------------------------------------------------------
    share_with_groups: list[str] = Field(
        default_factory=list, description="Group UIDs to share with (SHARED_WITH_GROUP)"
    )
    share_with_users: list[str] = Field(
        default_factory=list, description="User UIDs to share with (SHARES_WITH)"
    )
    auto_share_to_exercise_groups: bool = Field(
        default=False,
        description=(
            "When True, resolve the exercise's assigned groups server-side "
            "and SHARED_WITH_GROUP this entry to each. Requires "
            "``fulfills_exercise_uid``; silently noop without it."
        ),
    )
    visibility: Visibility | None = Field(
        default=None,
        description=(
            "Visibility override. Defaults to PRIVATE; set PUBLIC for portfolio publication."
        ),
    )


class UserEntryUpdateRequest(UpdateRequestBase):
    """
    Update a `UserEntry`.

    Content edits only. Audience changes go through
    `UnifiedSharingService` (share/unshare endpoints), not this request —
    the audience is an independent graph concern.
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
