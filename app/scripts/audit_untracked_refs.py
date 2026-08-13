#!/usr/bin/env python3
"""Untracked-reference guard — nothing tracked may cite the scratch tier.

SKUEL's thinking surface is ``app/plans/`` (plus ``~/.claude/plans/``): gitignored,
zero-ceremony, free to be wrong and free to delete. Its counterpart rule is that
**nothing tracked may cite it** — that prohibition IS the graduation trigger. The
moment a docstring, test, ADR, or CLAUDE.md needs to point at a document, that
document must be tracked, so it graduates to ``docs/roadmap/`` (open work) or
``docs/roadmap/done/`` (already executed). See CLAUDE.md § Documentation Architecture.

Why this is enforced rather than trusted: a citation of a gitignored path is
invisible to CI, absent from every worktree, and gone for anyone who clones. It
also rots silently — an audit in August 2026 found **35 such citations across 21
files, 23 of them pointing at documents that no longer existed anywhere**, including
absolute ``/home/mike/...`` paths committed to a public repo. Nothing detected them:
``scripts/health/dead_doc_links.py`` validates links inside ``.md`` files only, so a
dead path inside a Python docstring was never checked.

Two violation classes:

1. **A tracked file cites a scratch document** — any path of the shape
   ``plans/<name>.<ext>`` (with or without a leading ``/``, ``.claude/``, or an
   absolute home prefix). A bare ``plans/`` with no filename is NOT a violation:
   that is the ``.gitignore`` pattern and the prose in CLAUDE.md that defines this
   very rule.
2. **A tracked file LIVES under a scratch directory** — ``plans/`` is gitignored,
   but gitignore does not apply to already-tracked files, so files committed before
   the ignore stay tracked and make the tier incoherent. Four such files were found
   and untracked in August 2026.

Run: ``uv run python scripts/audit_untracked_refs.py``. Also ``./dev quality`` check
6c, a step in CI's gate-required **``content_boundary``** job, and asserted by
``tests/unit/test_untracked_refs.py``.

``content_boundary`` and not ``lint`` because that job is always-on: this guard reads
every tracked file, and ``app/.envrc`` and ``app/CLAUDE.md`` are matched by no path
filter at all, so under ``lint``'s ``py`` filter a docs-only PR would skip it. The CI
step is not optional belt-and-braces — ``tests/unit/scripts/test_quality_ci_parity.py``
fails any ``./dev quality`` check lacking a gate-required home, and its
``ALWAYS_ON_ONLY`` set pins this one to an unconditional job specifically.
Exit 0 = clean, 1 = violations.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# A citation of a document inside a scratch directory. The filename (with an
# extension) is required — that is what separates a POINTER AT a scratch doc from
# prose about the tier itself ("an untracked `plans/` file", the `plans/` ignore
# pattern, "moves to app/plans/done/"). Those must stay legal or this guard would
# flag the rule that defines it.
SCRATCH_CITATION = re.compile(
    r"""
    (?:^|[\s`'"(\[<])          # start, or a delimiter — never mid-identifier
    (?:[\w./~-]*?)             # optional leading path ( /home/mike/.claude/ , ./ , … )
    (?<!docs/)                 # NOT docs/plans/ — that would be TRACKED content, not scratch
    plans/                     # the scratch directory
    (?:[\w.-]+/)*              # optional subdirectories
    [\w.-]+\.[A-Za-z0-9]+      # a FILENAME WITH AN EXTENSION — the pointer itself
    """,
    re.VERBOSE,
)

# Files allowed to contain the pattern: this guard and its test necessarily spell
# out what they forbid.
EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "scripts/audit_untracked_refs.py",
        "tests/unit/test_untracked_refs.py",
    }
)

# Any tracked file under one of these directories is itself a violation.
SCRATCH_DIRS: tuple[str, ...] = ("plans/",)

_SKIP_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".pdf", ".woff2"})


def tracked_files() -> list[str]:
    """Repo-relative paths of every file git tracks under ``app/``."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def find_violations() -> tuple[list[tuple[str, int, str]], list[str]]:
    """Return (citations, tracked-under-scratch) violations."""
    citations: list[tuple[str, int, str]] = []
    under_scratch: list[str] = []

    for rel in tracked_files():
        if rel in EXEMPT_PATHS:
            continue
        if any(rel.startswith(d) or f"/{d}" in f"/{rel}" for d in SCRATCH_DIRS):
            under_scratch.append(rel)
            continue

        path = REPO_ROOT / rel
        if path.suffix.lower() in _SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            # errors="replace" rather than catching UnicodeDecodeError: binary
            # content decodes to noise that cannot match a citation, and a single
            # except clause keeps this runnable on any interpreter. (Ruff's py314
            # target rewrites `except (A, B):` into PEP 758's unparenthesized
            # form, which older interpreters reject — CI pins 3.14, a developer's
            # `python3` may not.)
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable — nothing to cite

        for lineno, line in enumerate(text.splitlines(), 1):
            if SCRATCH_CITATION.search(line):
                citations.append((rel, lineno, line.strip()))

    return citations, under_scratch


def main() -> int:
    citations, under_scratch = find_violations()

    if not citations and not under_scratch:
        print("✅ Untracked-reference guard: no tracked file cites the scratch tier")
        return 0

    if citations:
        print(f"\n❌ {len(citations)} tracked reference(s) to a gitignored scratch document:\n")
        for rel, lineno, line in citations:
            print(f"  {rel}:{lineno}")
            print(f"      {line[:120]}")
        print(
            "\n  Fix: graduate the document (docs/roadmap/ if open, docs/roadmap/done/ if\n"
            "  already executed), or delete the pointer when it is provenance the citing\n"
            "  text already carries. Never leave a tracked file pointing at plans/."
        )

    if under_scratch:
        print(f"\n❌ {len(under_scratch)} tracked file(s) living under a scratch directory:\n")
        for rel in under_scratch:
            print(f"  {rel}")
        print(
            "\n  plans/ is gitignored, but gitignore does not apply to already-tracked\n"
            "  files. Fix: `git rm --cached <path>` (the file stays on disk), or graduate\n"
            "  it into docs/ if something tracked needs to cite it."
        )

    print("\nSee CLAUDE.md § Documentation Architecture for the graduation rule.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
