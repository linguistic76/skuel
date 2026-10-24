"""
UID Grammar — the one rule every node uid is read against
=========================================================

A uid is lowercase ASCII from ``[a-z0-9._-]`` and takes one of two shapes:

- **Authored** — ``{prefix}.{slug}`` or ``{prefix}.{ns}.{slug}``, written in the
  content vault (``ku.mindfulness.attention``, ``resource.tao-te-ching``). The
  middle segment is a human grouping hint the system never reads.
- **Generated** — ``{prefix}_{16 hex}``, minted by code (``task_3f9a0c41d2e87b65``).

A prefix is a lowercase word (``ku``, ``ps``, ``task``, ``ue``); a segment is
lowercase words joined by ``-``; a generated uid's opaque part is
``OPAQUE_HEX`` lowercase hex digits, whether random or a hash. No segment holds a
``_`` or a ``:``, so no generated uid fits inside another uid, and composites
like ``hc.{user}.{habit}.{ts}`` are outside the shapes. ``:`` is in no node uid.

``classify`` reads any uid against the grammar. ``authored_uid_problem`` is the
ingestion check for a uid a file supplies — its ``uid:`` line, or the one its
file name gives — and takes no exemption. ``generated_uid`` builds a generated
uid and refuses one outside the grammar; ``hashed_uid`` builds one whose opaque
part is a hash of the parts that identify the node, so the same parts always
name the same node; ``UIDGenerator.generate_random_uid`` builds a random one.
``is_known_uid`` is the read-side check: a uid that fits, or has a shape an
exemption names. ``slugify`` folds text to the segment alphabet.
``UID_PATTERN`` is the two shapes as one regular expression that Cypher's ``=~``
reads as Python does, for a check the server runs.

``UID_EXEMPTIONS`` names each shape live code mints outside the grammar, the
functions that mint it, and what retires the entry (``retired_by``); the census
(``./dev uid-census``) names each live uid outside the grammar by the exemption
that mints its shape — and fails on it all the same: an exemption explains a uid,
it never admits one to the graph. ``tests/unit/utils/test_uid_grammar.py`` fails
when an exemption's writer no longer mints its shape.

See: /docs/decisions/ADR-013-ku-uid-flat-identity.md § Amendment (2026-10-18)
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md § Separator Grammar
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

UID_CHARSET: Final = re.compile(r"[a-z0-9._-]+")

_PREFIX: Final = r"[a-z][a-z0-9]*"
_SEGMENT: Final = r"[a-z0-9]+(?:-[a-z0-9]+)*"

#: Hex digits of a generated uid's opaque part — 64 bits, random or hashed. Two of
#: n such uids share a value with probability about n² / 2⁶⁵: 3e-10 at 100k nodes,
#: 3e-8 at a million.
OPAQUE_HEX: Final = 16

_AUTHORED: Final = rf"(?:\.{_SEGMENT}){{1,2}}"
_GENERATED: Final = rf"_[0-9a-f]{{{OPAQUE_HEX}}}"

AUTHORED_UID: Final = re.compile(rf"(?P<prefix>{_PREFIX}){_AUTHORED}")
GENERATED_UID: Final = re.compile(rf"(?P<prefix>{_PREFIX}){_GENERATED}")

#: Both shapes as one pattern with no named group, which Java's regex — Cypher's
#: ``n.uid =~ $pattern``, a whole-string match — reads as Python's does. A uid
#: matches it exactly when ``classify`` reads it ``FITS``.
UID_PATTERN: Final = rf"{_PREFIX}(?:{_AUTHORED}|{_GENERATED})"
UID_PREFIX: Final = re.compile(_PREFIX)
OPAQUE_PART: Final = re.compile(rf"[0-9a-f]{{{OPAQUE_HEX}}}")


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


def is_generated_uid(uid: str, prefix: str) -> bool:
    """Whether ``uid`` is a generated uid of ``prefix`` — ``{prefix}_{16 hex}``."""
    match = GENERATED_UID.fullmatch(uid)
    return match is not None and match["prefix"] == prefix


def generated_uid(prefix: str, opaque: str) -> str:
    """The generated uid ``{prefix}_{opaque}``.

    Raises:
        ValueError: when ``prefix`` is not a lowercase word or ``opaque`` is not
            ``OPAQUE_HEX`` lowercase hex digits — a caller's bug, never input.
    """
    if not UID_PREFIX.fullmatch(prefix):
        raise ValueError(f"uid prefix '{prefix}' is not a lowercase word ([a-z][a-z0-9]*)")
    if not OPAQUE_PART.fullmatch(opaque):
        raise ValueError(f"opaque uid part '{opaque}' is not {OPAQUE_HEX} lowercase hex digits")
    return f"{prefix}_{opaque}"


def hashed_uid(prefix: str, *parts: str) -> str:
    """The generated uid ``{prefix}_{hash}`` of the parts that identify a node.

    The hash is sha256 over the parts joined by NUL, cut to ``OPAQUE_HEX``
    hex digits. Deterministic: the same parts mint the same uid, so a writer that
    re-creates a node re-creates its uid. A part is never empty and never holds
    NUL, so no two lists of parts join to the same text.

    Raises:
        ValueError: when there are no parts, a part is empty or holds NUL, or the
            prefix is not a lowercase word — a caller's bug, never input.
    """
    if not parts:
        raise ValueError("a hashed uid needs at least one identifying part")
    for part in parts:
        if not part or "\0" in part:
            raise ValueError(f"identifying part {part!r} is empty or holds NUL")
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:OPAQUE_HEX]
    return generated_uid(prefix, digest)


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


_UUID: Final = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

UID_EXEMPTIONS: Final[tuple[UidExemption, ...]] = (
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


def exemptions_for(uid: str) -> tuple[UidExemption, ...]:
    """Every exemption whose shape ``uid`` has — empty when none does.

    Two exemptions can name one string, and a shape alone cannot say which writer
    minted it, so every match is returned rather than the first.
    """
    return tuple(exemption for exemption in UID_EXEMPTIONS if exemption.matches(uid))


def is_known_uid(uid: str) -> bool:
    """Whether ``uid`` can name a node: it fits the grammar, or an exemption names its shape."""
    return classify(uid) is UidVerdict.FITS or bool(exemptions_for(uid))


__all__ = [
    "AUTHORED_UID",
    "GENERATED_UID",
    "OPAQUE_HEX",
    "UID_CHARSET",
    "UID_EXEMPTIONS",
    "UID_PATTERN",
    "UidExemption",
    "UidVerdict",
    "authored_uid_problem",
    "classify",
    "exemptions_for",
    "generated_uid",
    "hashed_uid",
    "is_generated_uid",
    "is_known_uid",
    "slugify",
]
