#!/usr/bin/env python3
"""
Arbitrary Font-Size Audit
=========================

Advisory scan for arbitrary Tailwind font sizes (``text-[13px]``,
``sm:text-[40px]``, ``text-[clamp(...)]``) in production UI code. SKUEL's
type scale is named (ADR-084): the compact steps ``text-10`` / ``text-11`` /
``text-13`` / ``text-15`` live in ``static/css/input.css`` ``@theme inline``,
and everything else lands on Tailwind's stock scale (``text-xs`` …
``text-3xl``). New ``text-[Npx]`` literals re-open the drift this campaign
closed.

**Scan surface** — every string constant in the AST (``ast.Constant`` str
nodes, which also cover dict values, module/function constants, implicit
concatenation, and the constant parts of f-strings) — deliberately INCLUDING
docstrings: a class string quoted in a docstring teaches the anti-pattern
just as well as live code (primitives.py taught one from a docstring).

**Allowlist is count-pinned and honest in both directions**: a file over its
pin reports the overage as a violation; a file under its pin reports "tighten
the pin" so the ledger can never go stale silently.

**Advisory, not blocking** (exit 0) while the PR2–PR5 sweeps burn down the
backlog — the remaining-findings count printed at the end is the burndown
metric quoted in each sweep PR body. ``--strict`` (exit 1 on any finding)
flips on in the final campaign PR.

Usage:
    uv run python scripts/audit_font_sizes.py           # advisory report
    uv run python scripts/audit_font_sizes.py --strict  # exit 1 on any finding

Exit codes: 0 = always (advisory), 1 = only with --strict and findings present.
"""

import argparse
import ast
import re
import sys
from pathlib import Path

# Shared with lint_skuel.py — one exclusion vocabulary, one walk helper.
sys.path.insert(0, str(Path(__file__).parent))
from quality_discovery import iter_python_files  # type: ignore[import-not-found]

# Same narrowed scope as audit_raw_headers.py: production UI code only —
# tests/ and scripts/ may quote arbitrary class strings freely.
EXTRA_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({"scripts", "tests"})

# Arbitrary font-size literal, with any variant prefixes (sm:, dark:, hover:…)
# and clamp() fluid values. Excludes arbitrary colors/vars (text-[#fff],
# text-[var(--x)]) — those are not font sizes.
ARBITRARY_FONT_SIZE = re.compile(r"(?:[\w-]+:)*text-\[(?:\d|clamp)")

# ---------------------------------------------------------------------------
# Exception ledger — permanent arbitrary sites, pinned by exact match count
# (ADR-084 § 3). Over the pin = violation; under the pin = tighten the pin.
# ---------------------------------------------------------------------------

ALLOWED_ARBITRARY: dict[str, int] = {
    "ui/explore/reading_plan.py": 5,  # clamp() fluid heroes — deliberate responsive design (ADR-084)
    "ui/calendar/components.py": 2,  # 32px + sm:40px hero H1 pair (components.py:140)
    "ui/today/page.py": 1,  # 44px planning-board headline (mirrors ALLOWED_H1 rationale)
}


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _find_matches(source: str) -> list[tuple[int, str]]:
    """Return (lineno, matched_text) per arbitrary-font-size occurrence.

    Walks every ``ast.Constant`` string node — f-strings' constant parts are
    themselves Constant nodes inside ``ast.JoinedStr``, so the walk covers
    them without a separate branch. A single string carrying two literals
    (``text-[32px] sm:text-[40px]``) counts twice: the pin counts SITES,
    not strings.
    """
    matches: list[tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return matches

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        matches.extend(
            (node.lineno, match.group(0)) for match in ARBITRARY_FONT_SIZE.finditer(node.value)
        )
    return matches


def audit(root: Path, strict: bool) -> int:
    violations: list[tuple[str, list[tuple[int, str]]]] = []
    over_pin: list[tuple[str, int, int]] = []  # (rel, found, pinned)
    under_pin: list[tuple[str, int, int]] = []
    burndown_total = 0
    seen_allowlisted: set[str] = set()

    for path in iter_python_files(root, extra_dir_names=EXTRA_EXCLUDED_DIR_NAMES):
        rel = _relative(path, root)
        source = path.read_text(encoding="utf-8", errors="replace")

        if rel in ALLOWED_ARBITRARY:
            seen_allowlisted.add(rel)

        # Cheap pre-filter: only parse files that can possibly match.
        if "text-[" not in source:
            if rel in ALLOWED_ARBITRARY:
                under_pin.append((rel, 0, ALLOWED_ARBITRARY[rel]))
            continue

        matches = _find_matches(source)
        count = len(matches)

        if rel in ALLOWED_ARBITRARY:
            pinned = ALLOWED_ARBITRARY[rel]
            if count > pinned:
                over_pin.append((rel, count, pinned))
                burndown_total += count - pinned
            elif count < pinned:
                under_pin.append((rel, count, pinned))
        elif count:
            violations.append((rel, matches))
            burndown_total += count

    # Allowlist entries the walk never visited (file deleted, renamed, or
    # moved into an excluded tree) would otherwise vanish silently — report
    # them as under their pin so --strict cannot pass with a stale ledger
    # (Codex, PR #1057).
    under_pin.extend(
        (rel, 0, ALLOWED_ARBITRARY[rel])
        for rel in sorted(set(ALLOWED_ARBITRARY) - seen_allowlisted)
    )

    findings = len(violations) + len(over_pin) + len(under_pin)

    if over_pin:
        print("\n🔴 Allowlisted files OVER their pin (new arbitrary sites in a ledger file):")
        for rel, found, pinned in over_pin:
            print(f"  {rel}: {found} found, {pinned} pinned — convert the new sites (ADR-084)")

    if under_pin:
        print("\n⚠️  Allowlisted files UNDER their pin (stale ledger — tighten the pin):")
        for rel, found, pinned in under_pin:
            print(
                f"  {rel}: {found} found, {pinned} pinned — update ALLOWED_ARBITRARY in "
                "scripts/audit_font_sizes.py"
            )

    if violations:
        print("\n⚠️  Arbitrary font sizes outside the exception ledger (migrate per ADR-084):")
        for rel, matches in violations:
            sites = ", ".join(f"{lineno}:{text}" for lineno, text in matches)
            print(f"  {rel} ({len(matches)}): {sites}")

    if findings == 0:
        print("✅ Font-size audit: no arbitrary sizes outside the exception ledger")
        return 0

    print(
        f"\n  Burndown: {burndown_total} arbitrary font-size site(s) outside the ledger "
        f"in {len(violations) + len(over_pin)} file(s)."
    )
    print(
        "  This is advisory during the ADR-084 sweep PRs — convert sites to the named\n"
        "  scale (text-10/11/13/15 or stock text-xs/sm/base/lg/xl/3xl) per the mapping\n"
        "  table in docs/decisions/ADR-084-compact-font-size-tokens.md."
    )

    return 1 if strict else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit arbitrary Tailwind font sizes in UI code")
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 on any finding (default: advisory/exit 0)"
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    sys.exit(audit(root, strict=args.strict))


if __name__ == "__main__":
    main()
