"""Audit ``stale_names.py``'s own suppressor: what does ``SKIP_FILES`` keep invisible?

``SKIP_FILES`` skips ``docs/tools/HEALTH_CHECKS.md`` because a scanner's documentation
necessarily names the identifiers it tracks — sample output, the "What's tracked" table,
the matching-semantics paragraph. The justification is real; the *mechanism* is file-wide
while the justification is section-specific, and a suppressor broader than its grant is a
silent blind spot. Concrete evidence the risk is live: PR #872 added ~60 lines to that
document, including code identifiers, with zero coverage from this scanner.

So the skip stays and is scored against what it keeps invisible — **by section**.

The first cut of this audit pinned a *set of identifier names*, and Codex correctly broke
it (PR #876): a genuinely stale `KuType` written into `## Known Limitations` left the name
set unchanged, because `KuType` was already allowlisted as a legitimate example elsewhere.
Every test still passed. That is the same defect this file exists to catch — scoring a
suppressor on identity rather than on the thing that actually varies — so the pin now asks
*where* each hidden hit sits, which is the question the justification is about. It also
drops the name allowlist entirely: section scoping is strictly stronger, and a hand-listed
set of 16 names was a rubber-stamp waiting to happen.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import stale_names as sn  # type: ignore[import-not-found]

# Headings under which naming a tracked identifier is the documentation's job. Anything
# outside these is prose the scanner should have been auditing all along.
JUSTIFIED_HEADINGS = {
    "### 3. `stale_names.py` — Deprecated Identifiers in Doc Code Blocks",
    "## Maintaining `stale_names.py`",
}

_HEADING_RE = re.compile(r"^#{1,6} ")


def _enclosing_heading(lines: list[str], lineno: int) -> str:
    """Heading that governs ``lineno`` — itself if it is one, else the nearest above.

    Including the line itself is load-bearing: a tracked identifier can appear IN a
    heading (``## Known `KuType` limitations``), and attributing that hit to the *previous*
    heading lets a stale heading inherit a justified section's grant and pass silently
    (Codex, PR #876). The first cut of this excluded the current line and a test pinned
    that as intended — the audit and its pin agreed with each other and both were wrong.
    """
    for candidate in reversed(lines[:lineno]):
        if _HEADING_RE.match(candidate):
            return candidate.strip()
    return ""


def _hidden_hits() -> list[tuple[Path, int, str, str]]:
    """Every stale-name hit currently suppressed, with its enclosing heading."""
    found = []
    for path in sn.SKIP_FILES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, name, _kind, _replacement in sn.scan_file(path):
            found.append((path, lineno, name, _enclosing_heading(lines, lineno)))
    return found


def test_skip_files_entries_all_exist() -> None:
    """A skip pointing at a moved file suppresses nothing and hides the next real hit."""
    missing = [str(p) for p in sn.SKIP_FILES if not p.exists()]
    assert missing == [], f"SKIP_FILES entries no longer on disk: {missing}"


def test_suppressed_hits_all_sit_under_a_justified_heading() -> None:
    """Score the suppressor against what it KEEPS invisible, by location."""
    stray = [
        f"{path.name}:{lineno} {name!r} under {heading!r}"
        for path, lineno, name, heading in _hidden_hits()
        if heading not in JUSTIFIED_HEADINGS
    ]
    assert stray == [], (
        "SKIP_FILES is hiding tracked identifiers outside the sections that document "
        f"the scanner: {stray}. Either the prose is genuinely stale (fix it — that is the "
        "finding) or a new section legitimately documents tracked names, in which case add "
        "its heading to JUSTIFIED_HEADINGS."
    )


def test_every_skipped_path_earns_its_skip() -> None:
    """Positive control, PER PATH — an aggregate check lets a new entry ride along.

    Checked in aggregate, this passed for a second file added to `SKIP_FILES` before it
    contained any tracked identifier at all: `HEALTH_CHECKS.md` supplied the hits, so the
    new file silently hid its first future stale name (Codex, PR #876). A suppression
    granted to a file that needs none is the whole defect class this file audits.
    """
    hits = _hidden_hits()
    assert hits, "no skipped file contains any tracked identifier — remove SKIP_FILES"
    for path in sn.SKIP_FILES:
        own = [h for h in hits if h[0] == path]
        assert own, (
            f"{path.name} is in SKIP_FILES but contains no tracked identifier, so the "
            "skip suppresses nothing today and will silently hide its first real hit — "
            "remove the entry until it is actually needed"
        )


def test_justified_headings_all_earn_their_grant() -> None:
    """A heading allowlisted but no longer hiding anything is a standing over-grant."""
    covered = {heading for _p, _l, _n, heading in _hidden_hits()}
    unused = JUSTIFIED_HEADINGS - covered
    assert unused == set(), (
        f"JUSTIFIED_HEADINGS lists headings that hide nothing: {sorted(unused)} — prune "
        "them so the grant keeps matching the need"
    )


def test_heading_lookup_finds_the_nearest_preceding_heading() -> None:
    """The lookup is what the section scoping rests on, so pin it directly.

    An off-by-one here would silently attribute a stray hit to the justified section above
    it — the audit would keep passing while hiding exactly what it was built to surface.
    """
    lines = ["## First", "a", "### Second", "b", "c"]
    assert _enclosing_heading(lines, 2) == "## First"
    assert _enclosing_heading(lines, 4) == "### Second"
    assert _enclosing_heading(lines, 5) == "### Second"
    assert _enclosing_heading(["no headings", "here"], 2) == ""
    # A hit ON a heading line belongs to THAT heading. This assertion previously read
    # `== "## First"` and was wrong in the direction that silently accepts a stale
    # heading under a justified section's grant.
    assert _enclosing_heading(lines, 3) == "### Second"
    assert _enclosing_heading(lines, 1) == "## First"
