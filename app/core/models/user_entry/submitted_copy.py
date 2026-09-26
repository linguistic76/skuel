"""
Submitted copy — what a frozen copy of a vault note records about its source (R9)
================================================================================

A vault note is a draft: its ``audience:`` does nothing until
``status: submitted`` files a frozen copy through ``create_entry``, and only
the copy is submitted or shared (Submit & Share arc R9, ADR-088). The copy
carries two first-class properties the vault door hands ``create_entry``
beside the request — never inside it, so no JSON caller can claim another
note's provenance:

- ``submitted_from_uid`` — the living note's uid, the copy's provenance.
- ``submission_fingerprint`` — a digest of the whole authored snapshot the
  copy carries: title, content, description, tags, the ``private`` flag,
  the audience it was filed to and the exercise it answers.

The door files a new copy only when the note's fingerprint differs from its
newest copy's. The fingerprint is a record of what was authored, not a
second audience record (ADR-088 §3: the links alone grant access) — which
is why a Stop sharing on a copy is never read as an audience edit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.user_entry.user_entry_request import UserEntryCreateRequest


@dataclass(frozen=True)
class SubmittedCopy:
    """The provenance ``create_entry`` stamps on a frozen copy of a vault note."""

    submitted_from_uid: str
    fingerprint: str


def submission_fingerprint(request: UserEntryCreateRequest) -> str:
    """A digest of every authored field a copy request carries, canonically serialized.

    The audience is compared as a set (its vocabulary values, sorted) — the
    same audience listed in another order is the same submission. Tags keep
    their authored order, as the copy stores them.
    """
    snapshot = {
        "title": request.title,
        "content": request.content,
        "description": request.description,
        "tags": list(request.tags),
        "private": request.private,
        "audience": sorted(request.audience.values()),
        "exercise": request.fulfills_exercise_uid,
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["SubmittedCopy", "submission_fingerprint"]
