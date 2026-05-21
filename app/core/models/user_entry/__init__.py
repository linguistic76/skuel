"""
UserEntry Package — Unified User-Authored Content (ADR-054)
===========================================================

`UserEntry` collapses four parallel entity types into one:
    - Submission (abstract base)
    - ExerciseSubmission (empty leaf)
    - JeInput (journal raw input)
    - JeOutput (journal processed output)

All user-authored content — exercise turn-ins, journal entries, uploaded
files, free-form text — is a `UserEntry`. Dispatch is driven by the
`pipeline` field (`Pipeline` enum), not by `entity_type`. Audience is
declared at submit time via `UnifiedSharingService`.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_dto import UserEntryDTO
from core.models.user_entry.user_entry_request import (
    UserEntryCreateRequest,
    UserEntryProcessRequest,
    UserEntryUpdateRequest,
)

__all__ = [
    "UserEntry",
    "UserEntryDTO",
    "UserEntryCreateRequest",
    "UserEntryProcessRequest",
    "UserEntryUpdateRequest",
]
