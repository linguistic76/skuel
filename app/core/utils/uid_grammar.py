"""
UID Grammar — the one rule every node uid is read against
=========================================================

A uid is lowercase ASCII from ``[a-z0-9._-]`` and takes one of two shapes:

- **Authored** — ``{prefix}.{slug}`` or ``{prefix}.{ns}.{slug}``, written in the
  content vault (``ku.mindfulness.attention``, ``resource.tao-te-ching``). The
  middle segment is a human grouping hint the system never reads.
- **Generated** — ``{prefix}_{opaque}``, minted by code (``task_a1b2c3d4``).

A prefix is a lowercase word (``ku``, ``ps``, ``task``, ``ue``); a segment is
lowercase words joined by ``-``; an opaque part is lowercase letters and digits.
No segment holds a ``_`` or a ``:``, so no generated uid fits inside another
uid, and composites like ``hc.user_admin.habit_…`` are outside the shapes.
``:`` is in no node uid.

``classify`` reads any uid against the grammar. ``authored_uid_problem`` is the
ingestion check for a uid a file supplies — its ``uid:`` line, or the one its
file name gives — and takes no exemption. ``generated_uid`` builds a generated
uid and refuses one outside the grammar. ``slugify`` folds text to the segment
alphabet.

``UID_EXEMPTIONS`` names each shape live code mints outside the grammar, the
functions that mint it, and what retires the entry (``retired_by``); the census
(``./dev uid-census``) reports each live uid against them, and
``tests/unit/utils/test_uid_grammar.py`` fails when an exemption's writer no
longer mints its shape.

See: /docs/decisions/ADR-013-ku-uid-flat-identity.md § Amendment (2026-10-18)
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md § Separator Grammar
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

UID_CHARSET: Final = re.compile(r"[a-z0-9._-]+")

_PREFIX: Final = r"[a-z][a-z0-9]*"
_SEGMENT: Final = r"[a-z0-9]+(?:-[a-z0-9]+)*"

AUTHORED_UID: Final = re.compile(rf"(?P<prefix>{_PREFIX})(?:\.{_SEGMENT}){{1,2}}")
GENERATED_UID: Final = re.compile(rf"(?P<prefix>{_PREFIX})_[a-z0-9]+")
UID_PREFIX: Final = re.compile(_PREFIX)
OPAQUE_PART: Final = re.compile(r"[a-z0-9]+")


class UidVerdict(StrEnum):
    """How a uid reads against the grammar."""

    FITS = "fits"  # authored or generated shape
    OUTSIDE = "outside"  # a character outside [a-z0-9._-]
    SHAPE = "shape"  # in the charset, but neither shape


def classify(uid: str) -> UidVerdict:
    """Read ``uid`` against the grammar."""
    if not UID_CHARSET.fullmatch(uid):
        return UidVerdict.OUTSIDE
    if AUTHORED_UID.fullmatch(uid) or GENERATED_UID.fullmatch(uid):
        return UidVerdict.FITS
    return UidVerdict.SHAPE


def authored_uid_problem(uid: str, expected_prefix: str) -> str | None:
    """Why ``uid`` is not an authored uid of ``expected_prefix``, or ``None``.

    The sentence names the rule the uid breaks, for an author to act on.
    """
    if not UID_CHARSET.fullmatch(uid):
        return (
            f"uid '{uid}' has a character outside [a-z0-9._-] — use lowercase letters, "
            "digits and hyphens, with dots between segments"
        )
    if not uid.startswith(f"{expected_prefix}."):
        return f"uid '{uid}' must start with '{expected_prefix}.'"
    if not AUTHORED_UID.fullmatch(uid):
        return (
            f"uid '{uid}' is not '{expected_prefix}.{{slug}}' or "
            f"'{expected_prefix}.{{ns}}.{{slug}}' — each segment is lowercase words "
            "joined by single hyphens"
        )
    return None


def generated_uid(prefix: str, opaque: str) -> str:
    """The generated uid ``{prefix}_{opaque}``.

    Raises:
        ValueError: when ``prefix`` is not a lowercase word or ``opaque`` is not
            lowercase letters and digits — a caller's bug, never input.
    """
    if not UID_PREFIX.fullmatch(prefix):
        raise ValueError(f"uid prefix '{prefix}' is not a lowercase word ([a-z][a-z0-9]*)")
    if not OPAQUE_PART.fullmatch(opaque):
        raise ValueError(f"opaque uid part '{opaque}' is not lowercase letters and digits")
    return f"{prefix}_{opaque}"


def slugify(text: str) -> str:
    """Fold ``text`` to one uid segment: lowercase ASCII words joined by ``-``.

    Markdown links reduce to their link text (``[Foo](https://bar)`` → ``foo``);
    accented letters fold to their base letter (``café`` → ``cafe``); every other
    character outside ``[a-z0-9]`` is dropped, and runs of spaces, hyphens and
    underscores become one ``-``. Text with no ASCII letter or digit gives ``""``.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[-_\s]+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Shapes live code mints outside the grammar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UidExemption:
    """A shape live code mints outside the grammar, and what retires it.

    ``writers`` are ``module:qualname`` paths of the functions that mint the
    shape. ``retired_by`` names what deletes the entry.
    """

    name: str
    pattern: re.Pattern[str]
    writers: tuple[str, ...]
    retired_by: str

    def matches(self, uid: str) -> bool:
        return self.pattern.fullmatch(uid) is not None


# A frontmatter or Edge-file reference may name a periodic note by this uid
# (``preparer.is_sanctioned_machine_uid``), so it is named on its own.
PERIODIC_NOTE_EXEMPTION: Final = UidExemption(
    name="periodic_note",
    pattern=re.compile(r"ue:(?:daily|weekly|monthly|quarterly|yearly):[^:]+:[^:]+"),
    writers=("core.models.user_entry.user_entry:periodic_note_uid",),
    retired_by="uid arc PR 3 (periodic notes)",
)

_UUID: Final = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

UID_EXEMPTIONS: Final[tuple[UidExemption, ...]] = (
    UidExemption(
        name="chunk",
        pattern=re.compile(r".+:chunk:\d+"),
        writers=("core.models.ps_content.content_chunks:ContentChunk.chunk_id",),
        retired_by="uid arc PR 2 (chunks + Content)",
    ),
    PERIODIC_NOTE_EXEMPTION,
    UidExemption(
        name="named_generated",
        pattern=re.compile(rf"{_PREFIX}_{_SEGMENT}_[0-9a-f]{{8}}"),
        writers=(
            "core.utils.uid_generator:UIDGenerator.generate_uid",
            "core.services.ingestion.vault_policy:personal_file_uid",
        ),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="habit_completion",
        pattern=re.compile(r"hc\..+\.\d+"),
        writers=("core.services.habits.habits_completion_service:habit_completion_uid",),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="insight",
        pattern=re.compile(r"insight\.[a-z0-9_]+\.[^.:]*\.\d{14}"),
        writers=("core.models.insight.persisted_insight:PersistedInsight.generate_uid",),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="default_group",
        pattern=re.compile(r"group_default_.+"),
        writers=("core.models.group.group:default_group_uid",),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="search_event",
        pattern=re.compile(_UUID),
        writers=("core.services.search_event_recorder:search_event_uid",),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="transcription",
        pattern=re.compile(rf"transcription:{_UUID}"),
        writers=("core.services.transcription.transcription_service:transcription_uid",),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="instruction_set",
        pattern=re.compile(r"instructions:.+"),
        writers=("core.services.content_enrichment_service:instruction_set_uid",),
        retired_by="uid arc PR 4 (remaining generated shapes)",
    ),
    UidExemption(
        name="invoice",
        pattern=re.compile(rf"invoice:{_UUID}"),
        writers=(
            "core.models.finance.invoice:invoice_create_request_to_dto",
            "core.models.finance.invoice:create_invoice",
        ),
        retired_by="the local invoice module's deletion (ADR-052 Phase 5; invoicing is ChargeKeep)",
    ),
)


def exemption_for(uid: str) -> UidExemption | None:
    """The exemption whose shape ``uid`` has, or ``None``."""
    return next((exemption for exemption in UID_EXEMPTIONS if exemption.matches(uid)), None)


__all__ = [
    "AUTHORED_UID",
    "GENERATED_UID",
    "PERIODIC_NOTE_EXEMPTION",
    "UID_CHARSET",
    "UID_EXEMPTIONS",
    "UidExemption",
    "UidVerdict",
    "authored_uid_problem",
    "classify",
    "exemption_for",
    "generated_uid",
    "slugify",
]
