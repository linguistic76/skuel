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
just as well as live code (primitives.py taught one from a docstring). The
``static/js/*.js`` Tailwind source tree (``@source "../js/*.js"``) is scanned
as raw text — it emits production class strings too.

**Allowlist is payload-multiset-pinned and honest in both directions**: a
ledger file carrying an arbitrary class NOT in its pin reports it as a
violation (even if a permitted one vanished in the same change — count
pinning missed that swap); a pinned class missing from its file reports
"tighten the pin" so the ledger can never go stale silently.

**Strict since PR6** (campaign complete — burndown zero): CI's lint job and
``./dev quality`` check 5c run ``--strict`` (exit 1 on any finding). The
default invocation stays advisory (exit 0) for local iteration.

Usage:
    uv run python scripts/audit_font_sizes.py           # advisory report
    uv run python scripts/audit_font_sizes.py --strict  # exit 1 on any finding
                                                        # (the CI / ./dev quality mode)

Exit codes: 0 = always (advisory), 1 = only with --strict and findings present.
"""

import argparse
import ast
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

# Shared with lint_skuel.py — one exclusion vocabulary, one walk helper.
sys.path.insert(0, str(Path(__file__).parent))
from quality_discovery import iter_python_files  # type: ignore[import-not-found]

# Same narrowed scope as audit_raw_headers.py: production UI code only —
# tests/ and scripts/ may quote arbitrary class strings freely.
EXTRA_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({"scripts", "tests"})

# Any arbitrary text-[...] value, with variant prefixes (sm:, dark:, hover:…).
# `text-*` is ambiguous (font-size OR color), and enumerating size spellings
# proved unwinnable (digits, clamp, calc, min, max, round, length: hints, … —
# Codex, PR #1057 rounds 2-3) — so the match is generic and the CLOSED set,
# color payloads, is excluded below.
ARBITRARY_TEXT = re.compile(r"(?:[\w-]+:)*text-\[([^\]\s]+)\]")

# Tailwind's parenthesized custom-property shorthand: text-(length:--fs)
# compiles to font-size:var(--fs) (Codex, PR #1057 round 4). Only the
# `length:`-hinted form is a font size — un-hinted text-(--x) and
# text-(color:--x) resolve to color, exactly like their bracket twins.
SHORTHAND_LENGTH = re.compile(r"(?:[\w-]+:)*text-\(length:[^)\s]+\)")

# Tailwind's arbitrary-property form: [font-size:13px] / [font-size:var(--fs)]
# emits a font-size declaration with no text- prefix at all (Codex, PR #1062).
# The property is named, so every payload is a font size by construction.
# The (?<!-) lookbehind keeps bracketed VARIANT payloads out: in
# supports-[font-size:12px]:block the bracket follows `supports-` and
# compiles to an @supports query, not a font size (Codex, PR #1062 round 2).
# A real variant prefix (sm:, dark:) ends in `:`, which the lookbehind allows.
ARBITRARY_PROPERTY = re.compile(r"(?:[\w-]+:)*(?<!-)\[font-size:[^\]\s]+\]")

# Payloads that compile to `color`, not `font-size`: explicit color: hint,
# hex, color functions, bare var() (un-hinted vars on text-* resolve to
# color; a length:var(--x) hint IS a font size and is deliberately not here),
# and the color-ish keywords. Named colors (text-[red]) are not excluded —
# the house bans raw colors anyway (semantic tokens rule), so a false
# positive there is a report worth reading, and the allowlist can absorb a
# deliberate one.
COLOR_PAYLOAD = re.compile(
    r"^(?:color:|#|(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color|color-mix|light-dark)\(|var\(|currentcolor$|transparent$|inherit$)",
    re.IGNORECASE,
)


def _iter_size_matches(text: str) -> Iterator[re.Match[str]]:
    """Arbitrary font-size matches: text-[...], text-(length:...), [font-size:...]."""
    for match in ARBITRARY_TEXT.finditer(text):
        if not COLOR_PAYLOAD.match(match.group(1)):
            yield match
    yield from SHORTHAND_LENGTH.finditer(text)
    yield from ARBITRARY_PROPERTY.finditer(text)


# ---------------------------------------------------------------------------
# Exception ledger — permanent arbitrary sites, pinned by exact payload
# multiset (ADR-084 § 3). A count pin let a permitted class be swapped for an
# unrelated arbitrary size without detection (Codex, PR #1057 round 4);
# pinning the classes themselves closes that. A class not in the pin =
# violation; a pinned class not in the file = tighten the pin.
# ---------------------------------------------------------------------------

ALLOWED_ARBITRARY: dict[str, tuple[str, ...]] = {
    # clamp() fluid heroes — deliberate responsive design (ADR-084)
    "ui/explore/reading_plan.py": (
        "text-[clamp(24px,5vw,30px)]",
        "text-[clamp(14px,2.6vw,15.5px)]",
        "text-[clamp(28px,6vw,40px)]",
        "text-[clamp(16px,3vw,19px)]",
        "text-[clamp(18px,3.6vw,21px)]",
    ),
    # 32px + sm:40px hero H1 pair (components.py:140)
    "ui/calendar/components.py": ("text-[32px]", "sm:text-[40px]"),
    # 44px planning-board headline (mirrors ALLOWED_H1 rationale)
    "ui/today/page.py": ("text-[44px]",),
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
        matches.extend((node.lineno, match.group(0)) for match in _iter_size_matches(node.value))
    return matches


def _find_matches_text(source: str) -> list[tuple[int, str]]:
    """Raw-text scan (JS) — line numbers computed from match offsets."""
    return [
        (source.count("\n", 0, match.start()) + 1, match.group(0))
        for match in _iter_size_matches(source)
    ]


Matcher = Callable[[str], list[tuple[int, str]]]


def _scan_targets(root: Path) -> Iterator[tuple[Path, Matcher]]:
    """Every file Tailwind scans for class literals, with its matcher.

    Python UI trees get the AST scan; ``static/js/*.js`` is ALSO a Tailwind
    class source (``@source "../js/*.js"`` in ``static/css/input.css`` — the
    page-local Alpine bundles emit class strings), so it gets a raw-text scan
    (Codex, PR #1057). The glob mirrors the @source exactly: top-level only,
    which keeps vendored trees out.
    """
    for path in iter_python_files(root, extra_dir_names=EXTRA_EXCLUDED_DIR_NAMES):
        yield path, _find_matches
    for path in sorted((root / "static" / "js").glob("*.js")):
        yield path, _find_matches_text


def audit(root: Path, strict: bool) -> int:
    violations: list[tuple[str, list[tuple[int, str]]]] = []
    over_pin: list[tuple[str, list[str]]] = []  # (rel, classes present but not pinned)
    under_pin: list[tuple[str, list[str]]] = []  # (rel, classes pinned but not present)
    burndown_total = 0
    seen_allowlisted: set[str] = set()

    for path, find_matches in _scan_targets(root):
        rel = _relative(path, root)
        source = path.read_text(encoding="utf-8", errors="replace")

        if rel in ALLOWED_ARBITRARY:
            seen_allowlisted.add(rel)

        # Cheap pre-filter: only parse files that can possibly match.
        if "text-[" not in source and "text-(" not in source and "[font-size:" not in source:
            if rel in ALLOWED_ARBITRARY:
                under_pin.append((rel, sorted(ALLOWED_ARBITRARY[rel])))
            continue

        matches = find_matches(source)

        if rel in ALLOWED_ARBITRARY:
            found = Counter(text for _, text in matches)
            pinned = Counter(ALLOWED_ARBITRARY[rel])
            extra = found - pinned
            missing = pinned - found
            if extra:
                over_pin.append((rel, sorted(extra.elements())))
                burndown_total += sum(extra.values())
            if missing:
                under_pin.append((rel, sorted(missing.elements())))
        elif matches:
            violations.append((rel, matches))
            burndown_total += len(matches)

    # Allowlist entries the walk never visited (file deleted, renamed, or
    # moved into an excluded tree) would otherwise vanish silently — report
    # them as fully under their pin so --strict cannot pass with a stale
    # ledger (Codex, PR #1057).
    under_pin.extend(
        (rel, sorted(ALLOWED_ARBITRARY[rel]))
        for rel in sorted(set(ALLOWED_ARBITRARY) - seen_allowlisted)
    )

    findings = len(violations) + len(over_pin) + len(under_pin)

    if over_pin:
        print("\n🔴 Ledger files carrying arbitrary sites NOT in their pin (convert them):")
        for rel, classes in over_pin:
            print(f"  {rel}: {', '.join(classes)} — convert to the named scale (ADR-084)")

    if under_pin:
        print("\n⚠️  Pinned sites missing from their ledger file (stale ledger — tighten the pin):")
        for rel, classes in under_pin:
            print(
                f"  {rel}: {', '.join(classes)} — update ALLOWED_ARBITRARY in "
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
        "  Convert sites to the named scale (text-10/11/13/15 or stock\n"
        "  text-xs/sm/base/lg/xl/3xl) — see docs/decisions/ADR-084-compact-font-size-tokens.md.\n"
        "  CI and ./dev quality run this audit with --strict (blocking) since PR6."
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
