#!/usr/bin/env python3
"""
Guard for the docs ``updated:`` frontmatter stamp.

The pre-commit hook (``scripts/stamp_docs_updated.py``) writes the field; this check
is what makes writing it *trustworthy*. A hook can be bypassed with ``--no-verify``,
uninstalled, or silently stop running after a refactor — and none of those announce
themselves. Without a guard the corpus rots back to what was measured on
2026-08-29: 194 of 219 dated docs carrying a valid-*looking* date that was months out.

**Why not just check the field is present, unique, parseable and not in the future.**
That was proposed as the simple option and is recorded as rejected: on a doc that was
correctly stamped once and whose hook then stopped running, the old value stays
present, unique, parseable and non-future — so all four checks pass forever, on
exactly the rot the guard exists to catch. The date comparison is the check; the
other four exist because a comparison alone is blind to a doc that arrives with no
date at all.

**Why a rot threshold and not equality** (ruled 2026-09-01). The mandated merge is
``gh pr merge --squash``, which builds the final commit server-side where no hook
runs — and rewrites the *author* date as well as the committer date, so "compare the
author date instead" is not an escape hatch either. A correctly stamped doc
therefore trails its own merge commit by the review latency. Equality would red the
gate on every merge. ``ROT_WINDOW_DAYS`` absorbs that and still catches the measured
problem: 149 of the 162 docs stale on 2026-08-31 lag by more than a week.

**Why stamp-only commits are skipped.** The backfill that seeded this corpus becomes
the newest commit for every file it rewrote. Compared naively, every historical date
it just wrote predates it and the guard fails on nearly the whole corpus the day it
lands. The exclusion is stated as a permanent rule rather than a hardcoded SHA so a
future stamp-only commit gets the same treatment — and it needs line-level diffs,
which is why ``docs_updated_field.load_history`` runs a second pass instead of one
``git log --name-only``.

Runs in ~5s over 412 docs, so it belongs in ``./dev health`` (the ~80s
``health-mypy`` is the thing deliberately kept out).

Pinned by ``tests/unit/scripts/test_docs_updated.py``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# scripts/ is not a package — these modules are run as scripts, so the sibling
# import resolves at runtime via sys.path[0] but not for MyPy (matches the same
# ignore in scripts/health/stale_names.py).
from docs_updated_field import (  # type: ignore[import-not-found]
    FUTURE_SKEW_DAYS,
    REPO_ROOT,
    ROT_WINDOW_DAYS,
    FileHistory,
    ShallowHistoryError,
    find_updated,
    load_history,
    tracked_docs,
)

from core.utils.terminal_colors import Colors


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str
    detail: str


# Ordered: a structural defect is reported as itself, not as a date comparison that
# happens to fail. A doc with no field has no date to compare, and saying "stale by
# N days" about it would be a lie.
_ORDER = ["missing", "duplicate", "unparsable", "future", "stale"]

_REMEDY = {
    "missing": (
        "No `updated:` in the leading frontmatter block. The pre-commit hook adds "
        "one to every staged doc — a doc without it was committed with --no-verify, "
        "or the hook is not installed (app/scripts/install_git_hooks.sh)."
    ),
    "duplicate": (
        "Two `updated:` keys in the leading block. Keep one; the hook rewrites the "
        "first and the second would shadow it in any YAML reader."
    ),
    "unparsable": (
        "`updated:` is not a bare ISO date. Write `updated: YYYY-MM-DD` "
        "(quoted is fine)."
    ),
    "future": (
        "`updated:` is later than every commit that touched the file — a date no "
        "commit could have produced. A lower-bound-only check would pass this "
        "forever and mask every unstamped edit until the date arrived."
    ),
    "stale": (
        f"`updated:` lags the file's last substantive commit by more than "
        f"{ROT_WINDOW_DAYS} days. Commit with the hook installed and it is rewritten "
        f"for you; `git commit --no-verify` is what produces this."
    ),
}


def evaluate(path: str, content: str, history: FileHistory) -> Finding | None:
    """One doc's verdict, or None when it is correctly stamped."""
    field = find_updated(content)
    if field is None:
        return Finding(path, "missing", "no `updated:` key")
    if field.occurrences > 1:
        return Finding(path, "duplicate", f"{field.occurrences} `updated:` keys")

    stamped = field.parsed
    if stamped is None:
        return Finding(path, "unparsable", f"updated: {field.value!r}")

    ahead = (stamped - history.newest).days
    if ahead > FUTURE_SKEW_DAYS:
        return Finding(
            path,
            "future",
            f"updated: {stamped} is {ahead}d past the newest commit "
            f"({history.newest})",
        )

    lag = (history.last_substantive - stamped).days
    if lag > ROT_WINDOW_DAYS:
        return Finding(
            path,
            "stale",
            f"updated: {stamped} is {lag}d behind the last substantive commit "
            f"({history.last_substantive})",
        )
    return None


def collect() -> tuple[list[Finding], int, int]:
    docs, generated = tracked_docs()
    history = load_history(set(docs))

    findings: list[Finding] = []
    for path in docs:
        content = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        finding = evaluate(path, content, history[path])
        if finding is not None:
            findings.append(finding)
    return findings, len(docs), generated


def main() -> int:
    if not sys.stdout.isatty():
        Colors.disable()

    try:
        findings, scanned, generated = collect()
    except ShallowHistoryError as refusal:
        # Exit 2, distinct from 1 (= found defects): "could not measure" and "measured,
        # all clean" must never be the same signal, and neither may be silence.
        print(f"{Colors.RED}✗ Cannot measure `updated:` staleness{Colors.RESET}")
        print(f"  {refusal}")
        return 2
    # Named, not swallowed: an exclusion nobody can see is indistinguishable from a
    # blind spot (the `duplicate_headings.py` freeform carve-out sets the precedent).
    carve_out = (
        f", {generated} generated doc(s) excluded — their own drift tests guarantee "
        f"freshness"
        if generated
        else ""
    )

    if not findings:
        print(
            f"{Colors.GREEN}✓ docs `updated:` stamps are current "
            f"({scanned} docs{carve_out}){Colors.RESET}"
        )
        return 0

    by_kind: dict[str, list[Finding]] = {}
    for finding in findings:
        by_kind.setdefault(finding.kind, []).append(finding)

    print(
        f"{Colors.RED}{Colors.BOLD}Docs `updated:` stamp — "
        f"{len(findings)} of {scanned} docs wrong:{Colors.RESET}\n"
    )
    for kind in _ORDER:
        group = by_kind.get(kind)
        if not group:
            continue
        print(f"  {Colors.BOLD}{kind}{Colors.RESET} ({len(group)})")
        print(f"    {Colors.DIM}{_REMEDY[kind]}{Colors.RESET}")
        for finding in sorted(group, key=lambda item: item.path)[:20]:
            print(f"      {Colors.YELLOW}{finding.path}{Colors.RESET} — {finding.detail}")
        if len(group) > 20:
            print(f"      {Colors.DIM}… and {len(group) - 20} more{Colors.RESET}")
        print()

    print(
        f"{Colors.YELLOW}The stamp is only evidence of freshness within the "
        f"{ROT_WINDOW_DAYS}-day window this check enforces — never cite `updated:` "
        f"as staleness evidence outside it.{Colors.RESET}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
