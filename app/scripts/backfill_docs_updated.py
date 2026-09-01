#!/usr/bin/env python3
"""
One-shot backfill: seed ``updated:`` on every doc from its own commit history.

Run once, when the auto-stamp ships. Every doc afterwards is stamped by the
pre-commit hook; this script exists only because the hook cannot reach backwards.

**What date it writes, and why not simply "today".** Each file gets its own last
*substantive* commit date, so ~10 months of real dating survives the transition
(the fork ruled in the shipping PR; the alternative — stamp everything to the
backfill date — costs no logic but makes every doc claim the same day and erases the
history the field was supposed to carry). The price is one permanent rule, which the
guard carries anyway: **stamp-only commits are skipped**. Without it this very
script invalidates itself — it becomes the newest commit for every file it rewrites,
so every historical date it just wrote would predate it.

**It mutates ~370 files, so it re-derives its premise at run time and aborts.**
The plan below was measured on one tree; nothing re-checks it unless this script
does. Five abort conditions, each guarding a way the premise can be false by the
time it runs — see ``verify_premise``. A script that "ran successfully" against a
stale premise produces a confident, wrong diff over the whole corpus.

Usage::

    uv run python scripts/backfill_docs_updated.py              # plan only
    uv run python scripts/backfill_docs_updated.py --apply      # write

The commit that lands the result MUST bypass the stamper, or the hook overwrites
every historical date with today and the backfill is undone in the act of
committing it::

    SKUEL_SKIP_DOC_STAMP=1 git commit -m "..."

The script prints this line at the end of a successful ``--apply`` run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# scripts/ is not a package — these modules are run as scripts, so the sibling
# import resolves at runtime via sys.path[0] but not for MyPy (matches the same
# ignore in scripts/health/stale_names.py).
from docs_updated_field import (  # type: ignore[import-not-found]
    FUTURE_SKEW_DAYS,
    REPO_ROOT,
    ROT_WINDOW_DAYS,
    apply_stamp,
    find_updated,
    load_history,
    tracked_docs,
)

from core.utils.terminal_colors import Colors


@dataclass(frozen=True)
class Plan:
    path: str
    current: str | None
    target: date
    reason: str


class PremiseError(Exception):
    """The tree is not the tree this backfill was designed against."""


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def verify_premise(docs: list[str], history: dict[str, object]) -> None:
    """Re-derive every claim this backfill rests on. Raise on any mismatch.

    1. **Every doc joins its history.** ``git ls-files`` run from ``app/`` yields
       CWD-relative paths while ``git log`` yields repo-root-relative ones; joining
       the two matches nothing, every file looks current, and a measurement reads a
       clean ``0 stale``. That is not a hypothetical — it happened on the first
       census of this corpus. A partial join here would silently under-write.
    2. **No target has uncommitted changes.** Rewriting a dirty file either clobbers
       the author's edit or drags it into the backfill commit, where it stops being
       stamp-only and the guard then fails on that file forever.
    3. **No doc carries two `updated:` keys.** Which one is authoritative is a human
       call, and rewriting the first silently would leave the second shadowing it.
    4. **No doc carries an unparsable `updated:`.** Same reason: overwriting a value
       nobody has read is how information is lost quietly.
    5. **Nothing is staged.** The result has to be reviewable as its own diff.
    """
    unjoined = [path for path in docs if path not in history]
    if unjoined:
        raise PremiseError(
            f"{len(unjoined)} docs have no commit history — the path bases do not "
            f"join (expected repo-root-relative on both sides). First: {unjoined[:3]}"
        )

    dirty = {
        line[3:]
        for line in _git("status", "--porcelain", "--", "app/docs").split("\n")
        if line.strip()
    }
    conflicts = sorted(dirty & set(docs))
    if conflicts:
        raise PremiseError(
            f"{len(conflicts)} in-scope docs have uncommitted changes; commit or "
            f"stash them first. First: {conflicts[:3]}"
        )

    staged = [line for line in _git("diff", "--cached", "--name-only").split("\n") if line]
    if staged:
        raise PremiseError(
            f"{len(staged)} files are already staged; the backfill must be its own "
            f"reviewable diff. First: {staged[:3]}"
        )

    duplicates: list[str] = []
    unparsable: list[str] = []
    for path in docs:
        field = find_updated((REPO_ROOT / path).read_text(encoding="utf-8"))
        if field is None:
            continue
        if field.occurrences > 1:
            duplicates.append(path)
        elif field.parsed is None:
            unparsable.append(f"{path} ({field.value!r})")
    if duplicates:
        raise PremiseError(
            f"{len(duplicates)} docs carry two `updated:` keys — a human must pick "
            f"one: {duplicates}"
        )
    if unparsable:
        raise PremiseError(
            f"{len(unparsable)} docs carry a non-ISO `updated:` — fix by hand rather "
            f"than overwrite: {unparsable}"
        )


def build_plan(docs: list[str], history: dict) -> list[Plan]:  # type: ignore[type-arg]
    """Which docs to rewrite, and to what.

    Only docs the guard would currently REJECT are touched. A doc already stamped
    within the rot window is left exactly as it is — rewriting it to its last
    substantive commit would move a correct date backwards for no gain, and would
    enlarge a diff that has to be read by a human.
    """
    plans: list[Plan] = []
    for path in docs:
        record = history[path]
        field = find_updated((REPO_ROOT / path).read_text(encoding="utf-8"))
        target = record.last_substantive

        if field is None:
            plans.append(Plan(path, None, target, "missing"))
            continue

        stamped = field.parsed
        assert stamped is not None  # verify_premise rejected the alternative
        if (stamped - record.newest).days > FUTURE_SKEW_DAYS:
            plans.append(Plan(path, field.value, target, "future"))
        elif (record.last_substantive - stamped).days > ROT_WINDOW_DAYS:
            plans.append(Plan(path, field.value, target, "stale"))
    return plans


def apply(plans: list[Plan]) -> None:
    """Write the plan, then re-read every file and confirm it says what was planned.

    The confirmation is not ceremony: ``apply_stamp`` has four shapes (rewrite,
    rewrite-quoted, insert-into-block, create-block) and a bug in any one of them
    would look exactly like a successful run across 370 files.
    """
    for plan in plans:
        target = REPO_ROOT / plan.path
        original = target.read_text(encoding="utf-8")
        stamped = apply_stamp(original, plan.target)
        if stamped == original:
            raise PremiseError(
                f"{plan.path}: stamp produced no change but was planned as "
                f"{plan.reason!r} — the rewrite did not take"
            )
        target.write_text(stamped, encoding="utf-8")

    for plan in plans:
        field = find_updated((REPO_ROOT / plan.path).read_text(encoding="utf-8"))
        if field is None or field.parsed != plan.target:
            raise PremiseError(
                f"{plan.path}: after writing, `updated:` reads "
                f"{field.value if field else None!r}, expected {plan.target}"
            )
        if field.occurrences != 1:
            raise PremiseError(
                f"{plan.path}: {field.occurrences} `updated:` keys after writing — "
                f"a second key was appended instead of the first rewritten"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the files (default: print the plan and change nothing)",
    )
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    docs = tracked_docs()
    history = load_history(set(docs))

    try:
        verify_premise(docs, history)  # type: ignore[arg-type]
    except PremiseError as failure:
        print(f"{Colors.RED}✗ Premise check failed — nothing written{Colors.RESET}")
        print(f"  {failure}")
        return 2

    plans = build_plan(docs, history)
    by_reason: dict[str, int] = {}
    for plan in plans:
        by_reason[plan.reason] = by_reason.get(plan.reason, 0) + 1

    print(f"{Colors.BOLD}Backfill plan{Colors.RESET} — {len(docs)} docs in scope")
    for reason, count in sorted(by_reason.items()):
        print(f"  {reason:<10} {count}")
    print(f"  {'unchanged':<10} {len(docs) - len(plans)}")
    print()
    for plan in plans[:10]:
        print(
            f"  {Colors.YELLOW}{plan.path}{Colors.RESET}: "
            f"{plan.current or '(no key)'} → {plan.target} [{plan.reason}]"
        )
    if len(plans) > 10:
        print(f"  {Colors.DIM}… and {len(plans) - 10} more{Colors.RESET}")

    if not plans:
        print(f"\n{Colors.GREEN}✓ Nothing to backfill{Colors.RESET}")
        return 0

    if not args.apply:
        print(f"\n{Colors.CYAN}Dry run — re-run with --apply to write.{Colors.RESET}")
        return 0

    try:
        apply(plans)
    except PremiseError as failure:
        print(f"{Colors.RED}✗ Write verification failed{Colors.RESET}")
        print(f"  {failure}")
        return 2

    print(f"\n{Colors.GREEN}✓ Wrote {len(plans)} docs{Colors.RESET}")
    print(
        f"{Colors.YELLOW}Commit with the stamper bypassed, or the hook overwrites "
        f"every historical date with today:{Colors.RESET}"
    )
    print("    SKUEL_SKIP_DOC_STAMP=1 git commit -m '...'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
