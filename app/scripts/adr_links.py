#!/usr/bin/env python3
"""
ADR reference resolution for ``related_adrs``
=============================================

One resolver for the two scripts that read ``related_adrs`` from
``.claude/skills/skills_metadata.yaml`` — ``generate_cross_reference_index.py``
(which renders the refs as links) and ``validate_cross_references.py`` (which
checks them). They are the only consumers of the field.

Both previously spelled the filename themselves, and both got it wrong in the
same two ways:

  - ``f"ADR-{ref}.md"`` assumes ADRs have no slug. They all do, so 12 of the 13
    ADR link targets the generated index rendered were dead — the whole of
    ``docs/CROSS_REFERENCE_INDEX.md``'s dead-link count (30 findings, measured
    2026-09-01).
  - The same expression appends a second ``.md`` to a ref that already names a
    file, so the escape hatch from the first bug was itself broken.

**A duplicate ADR number is refused, never guessed.** ``docs/decisions/`` holds
three ``ADR-030-*`` files and two ``ADR-037-*``, so a bare number does not always
name one ADR. The validator used to resolve those by ``glob()`` into a dict,
last write winning — and ``Path.glob`` yields directory order, so *which* file a
ref meant could change when an unrelated ADR was added. Picking silently from an
arbitrary order is the failure this module exists to remove: on zero or several
matches it raises, naming the ref and every candidate, and the remedy is to write
the full filename in the metadata (three refs there do).

Renumbering the duplicate ADRs is a separate, unscheduled question — see
``docs/roadmap/deferred-work.md`` § Dead-Doc-Links Instrument.
"""

import re
from pathlib import Path

# The two authored spellings, and nothing else. Both patterns are ANCHORED AT BOTH
# ENDS, which is the whole precondition: an unanchored `^(?:ADR-)?(\d+)` reads
# `ADR-050-typo`, `ADR-050junk` and `ADR-050.md.bak` as the number 050 and resolves
# each of them, silently, to the real ADR-050 — a malformed ref linked to a decision
# nobody named it after (Codex P2, PR #1218). Rejecting the *shape* covers every
# spelling of the mistake at once; enumerating bad suffixes never would.
#
# The number is captured as WRITTEN, padding included, because it is also the glob's
# stem — `ADR-37-*.md` matches nothing, and reporting that is better than silently
# re-padding a ref into a file its author never named.
ADR_BARE_RE = re.compile(r"^(?:ADR-)?(\d+)$")
# `[^/]` is load-bearing, not decoration: it is what stops `ADR-1-x/../y.md` from
# resolving through the directory and rendering a link nobody authored.
ADR_FILENAME_RE = re.compile(r"^ADR-(\d+)(?:-[^/]*)?\.md$")


class AdrReferenceError(ValueError):
    """A ``related_adrs`` reference does not name exactly one file in ``docs/decisions/``."""


def _number_token(ref: str) -> str:
    """The reference's ADR number, as authored — rejecting any other spelling.

    This is the grammar gate for every entry point in the module, so a reference
    that is neither of the two documented forms never reaches a glob, a file check
    or a display label.
    """
    match = ADR_BARE_RE.match(ref) or ADR_FILENAME_RE.match(ref)
    if match is None:
        raise AdrReferenceError(
            f"related_adrs entry {ref!r} is not a valid ADR reference — expected a "
            "bare `ADR-NNN` or a full `ADR-NNN-slug.md` filename."
        )
    return match.group(1)


def adr_display(ref: str) -> str:
    """The short ``ADR-NNN`` label to show a reader, whichever form was authored.

    Only the link *target* carries the slug: a table of
    ``ADR-037-lateral-relationships-visualization-phase5.md`` reads worse than one
    of ``ADR-037``, and the display text is not what was broken.
    """
    return f"ADR-{_number_token(ref)}"


def adr_sort_key(ref: str) -> tuple[int, str]:
    """Order ADRs by number, then by spelling.

    The spelling breaks ties, so the two files sharing a number sort stably rather
    than in whatever order the metadata happens to name them — the generated
    artifact is byte-compared against a fresh render, so any residual ambiguity in
    the ordering surfaces as unexplained drift.
    """
    return int(_number_token(ref)), ref


def resolve_adr_filename(ref: str, decisions_dir: Path) -> str:
    """The one file in ``decisions_dir`` that ``ref`` names.

    Raises ``AdrReferenceError`` when the reference names no file or several —
    naming the ref and every candidate, because the caller cannot tell which was
    meant and neither can this function.
    """
    number = _number_token(ref)

    if ref.endswith(".md"):
        # Shape is already guaranteed by the grammar gate above — only existence
        # is left to check.
        if (decisions_dir / ref).is_file():
            return ref
        raise AdrReferenceError(
            f"related_adrs entry {ref!r} names no file in {decisions_dir.as_posix()}/. "
            "Give the bare filename of an existing ADR."
        )

    candidates = sorted(path.name for path in decisions_dir.glob(f"ADR-{number}-*.md"))
    slugless = decisions_dir / f"ADR-{number}.md"
    if slugless.is_file():
        candidates.append(slugless.name)

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        raise AdrReferenceError(
            f"related_adrs entry {ref!r} matches no ADR in "
            f"{decisions_dir.as_posix()}/ (looked for ADR-{number}-*.md and "
            f"ADR-{number}.md)."
        )

    raise AdrReferenceError(
        f"related_adrs entry {ref!r} matches {len(candidates)} ADRs — "
        f"{', '.join(candidates)}. Replace the bare number with the full "
        "filename of the one intended; this resolver will not choose."
    )
