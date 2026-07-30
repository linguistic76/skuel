"""Audit ``stale_names.py``'s own suppressor: what does ``SKIP_FILES`` keep invisible?

``SKIP_FILES`` skips ``docs/tools/HEALTH_CHECKS.md`` because a scanner's documentation
necessarily names the identifiers it tracks — sample output, the "What's tracked" table,
the matching-semantics paragraph. That justification is real and every hit in the file
today is such an example (verified by inspection, PR #876).

But the *mechanism* is file-wide while the *justification* is section-specific, and a
suppressor that hides more than it was granted is a silent blind spot — nothing is
reported, so nothing looks wrong. That is the same defect class as the placeholder
vocabulary in PR #872, which passed every test written for it while shadowing a live
repo file. Concrete evidence the risk is live: PR #872 added ~60 lines to that document,
including code identifiers, with zero coverage from this scanner.

So the skip stays, but it is now scored against what it keeps invisible: the set of
tracked identifiers appearing in a skipped file is pinned, and a NEW one fails. Keyed on
identifier, deliberately — line numbers shift on every edit to that document, and a
line-keyed pin would have to be rewritten (and rubber-stamped) each time.

If this test fails, one of two things happened. Either a genuinely stale identifier was
written into the file — fix the prose, that is the finding — or a new tracked name was
legitimately added as documentation, in which case add it below with a note.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import stale_names as sn  # type: ignore[import-not-found]

# Tracked identifiers that HEALTH_CHECKS.md legitimately names as examples, all inside
# its `### 3. stale_names.py` section or the `## Maintaining stale_names.py` paragraph
# that documents matching semantics. Measured on the live tree, PR #876.
EXPECTED_DOCUMENTED_EXAMPLES = {
    "ActivityDataReader",
    "ActivityReviewService",
    "AiFeedback",
    "EntityType.CURRICULUM",
    "KuStatus",
    "KuTaskCreateRequest",
    "KuType",
    "PageHead",
    "ProfileLayout",
    "active_tasks_rich",
    "core.models.ku.",
    "daisy_components",
    "from core.models.ku.ku_enums import",
    "htmx_a11y",
    "list_reports",
    "sel_routes",
}


def test_skip_files_entries_all_exist() -> None:
    """A skip pointing at a moved file suppresses nothing and hides the next real hit."""
    missing = [str(p) for p in sn.SKIP_FILES if not p.exists()]
    assert missing == [], f"SKIP_FILES entries no longer on disk: {missing}"


def test_skipped_files_hide_only_known_documentation_examples() -> None:
    """Score the suppressor against what it KEEPS invisible, not what it was written for."""
    hidden: set[str] = set()
    for path in sn.SKIP_FILES:
        hidden.update(name for _lineno, name, _kind, _replacement in sn.scan_file(path))

    unexpected = hidden - EXPECTED_DOCUMENTED_EXAMPLES
    assert unexpected == set(), (
        "SKIP_FILES is hiding tracked identifiers that are not known documentation "
        f"examples: {sorted(unexpected)}. Either the prose is genuinely stale (fix it) "
        "or the name is a new deliberate example (add it to EXPECTED_DOCUMENTED_EXAMPLES "
        "with a note)."
    )


def test_the_pin_is_not_vacuous() -> None:
    """A suppression audit that asserts an empty set would pass on a broken scanner.

    This is the positive control: the skipped file must actually still contain tracked
    identifiers, otherwise `SKIP_FILES` has become unnecessary and should be deleted
    rather than silently carried.
    """
    hidden = {name for path in sn.SKIP_FILES for _l, name, _k, _r in sn.scan_file(path)}
    assert hidden, (
        "no skipped file contains any tracked identifier — SKIP_FILES no longer "
        "suppresses anything and should be removed"
    )
    stale_expectations = EXPECTED_DOCUMENTED_EXAMPLES - hidden
    assert stale_expectations == set(), (
        "EXPECTED_DOCUMENTED_EXAMPLES lists names the file no longer contains — prune "
        f"them so this pin keeps describing reality: {sorted(stale_expectations)}"
    )
