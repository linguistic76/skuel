#!/usr/bin/env python3
"""
Duplicate-heading guard for authored Markdown.

Catches the *structural* half of a failure class that bit PR #1153 four times: a
section body is rewritten, and a second copy of that section — or a summary of it —
is left behind still asserting the old version. The semantic half (a paraphrase
contradicting its body) is not mechanically detectable and this scanner does not
pretend to find it. What it does find is the shape that IS decidable: **two headings
with the same text, at the same level, under the same parent.** In #1153 that was
two ``## PR-5`` sections, the superseded one living beside its replacement.

Why ``git grep`` does not cover this: the duplicate is found by *position*, not by
string. Grepping the heading text returns both copies and looks correct — you have to
notice there are two, in a file long enough that nobody scrolls it end to end.

**The rule is scoped, and the scoping is the whole design.** Measured over the 508
authored Markdown files in ``docs/`` + ``.claude/skills/``:

    same text anywhere in the file .................. 137 hits  (unusable)
    same text + same level + same parent path .......   6 hits  (this rule)

The naive rule fires on every legitimately repeated subheading — ``### Tests`` under
each of five PR sections is good structure, not a defect. Only a repeat under the
*same parent* is a duplicate, because only then do the two headings claim to be the
same section of the same outline. A false positive in an always-on gate is worse than
a miss: a miss lets one duplicate through, a false positive reds every build.

Headings come from the CommonMark parser, never a regex — the sibling module
``markdown_fences`` documents what hand-rolled Markdown scanning costs (five
container-handling bugs in one review). The parser gets fenced ``## not-a-heading``
samples and list/blockquote nesting right for free. Two deliberate narrowings of what
it returns:

- **Blockquoted headings are skipped** (``token.level > 0``) — quoted material is
  someone else's outline, not this document's.
- **ATX (``##``) only; setext underlines are ignored.** Not a shortcut — a measured
  choice. The corpus contains ZERO intentional setext headings, and enabling them
  reported six phantom ones: an unfilled ADR template writes ``**Pros:**`` above an
  empty ``-`` bullet, and CommonMark reads a lone ``-`` after a paragraph as a setext
  underline rather than a list item, so the bold label renders as an ``<h2>``. Those
  repeats are a template artifact, not a superseded section, and reporting them would
  red the gate for something this scanner is not about. (The phantom ``<h2>``s are a
  real if minor rendering bug in ``ADR-TEMPLATE.md`` and ``ADR-010``; they belong to
  whoever fixes that template.) A genuine setext heading is therefore MISSED — accepted,
  because none exists and the alternative is a standing false positive.

Scope excludes ``docs/design-principles/`` — see ``FREEFORM_DIRS``.

Pinned by ``tests/unit/scripts/test_duplicate_headings.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from markdown_it import MarkdownIt

sys.path.insert(0, str(Path(__file__).parent))

from core.utils.terminal_colors import Colors

ROOT = Path(__file__).parent.parent.parent  # /home/mike/skuel/app

SCAN_DIRS = [
    ROOT / "docs",
    ROOT / ".claude" / "skills",
]

# Freeform capture, not authored structure. These hold pasted chat transcripts and
# raw working notes (``sandbox:/mnt/data/`` links, conversational ``## next``
# markers); a repeated heading there is faithful capture, and renaming one to satisfy
# a scanner would edit the record to fit the tool. Excluded by SCOPE, not suppressed:
# the run prints how many files it skipped, so the carve-out stays visible. Delete
# this to bring them in — the scanner needs no other change.
FREEFORM_DIRS = [
    ROOT / "docs" / "design-principles",
]

_PARSER = MarkdownIt("commonmark")


def _is_freeform(path: Path) -> bool:
    return any(path.is_relative_to(d) for d in FREEFORM_DIRS)


def get_md_files() -> tuple[list[Path], int]:
    """Authored Markdown to scan, plus the count skipped as freeform."""
    scanned: list[Path] = []
    skipped = 0
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if _is_freeform(path):
                skipped += 1
            else:
                scanned.append(path)
    return scanned, skipped


def extract_headings(content: str) -> list[tuple[int, int, str]]:
    """
    Every top-level heading as ``(line, depth, text)``, 1-based lines.

    ``depth`` is 1-6 from the ``h1``-``h6`` tag. Blockquote-nested and setext headings
    are dropped (see module docstring); fenced and indented code blocks never reach
    here because the parser does not emit headings for them.
    """
    tokens = _PARSER.parse(content)
    headings: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.level > 0:
            continue
        if not token.markup.startswith("#"):  # setext — see module docstring
            continue
        text = tokens[index + 1].content.strip() if index + 1 < len(tokens) else ""
        line = (token.map[0] + 1) if token.map else 0
        headings.append((line, int(token.tag[1:]), text))
    return headings


def find_duplicates(content: str) -> list[tuple[str, int, int, tuple[str, ...]]]:
    """
    Headings repeated at the same level under the same parent.

    Returns ``(text, first_line, duplicate_line, parent_path)`` per repeat. Comparison
    is case-insensitive: ``## Next`` and ``## next`` under one parent are the same
    section wearing two spellings, and anchor links cannot tell them apart either.
    """
    path: list[tuple[int, str]] = []
    seen: dict[tuple[tuple[str, ...], int, str], int] = {}
    duplicates: list[tuple[str, int, int, tuple[str, ...]]] = []

    for line, depth, text in extract_headings(content):
        while path and path[-1][0] >= depth:
            path.pop()
        parents = tuple(title for _, title in path)
        key = (parents, depth, text.casefold())
        if key in seen:
            duplicates.append((text, seen[key], line, parents))
        else:
            seen[key] = line
        path.append((depth, text))

    return duplicates


def check_file(md_file: Path) -> list[tuple[Path, str, int, int, tuple[str, ...]]]:
    content = md_file.read_text(encoding="utf-8", errors="replace")
    rel = md_file.relative_to(ROOT)
    return [
        (rel, text, first, dup, parents) for text, first, dup, parents in find_duplicates(content)
    ]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Find duplicate Markdown headings")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="List every file as it is scanned"
    )
    args = parser.parse_args()

    print(f"{Colors.BOLD}Duplicate Heading Guard{Colors.RESET}")
    print("=" * 60)

    md_files, skipped = get_md_files()
    freeform_note = f" ({skipped} freeform files skipped)" if skipped else ""
    print(
        f"Scanning {len(md_files)} Markdown files in docs/ and .claude/skills/{freeform_note}...\n"
    )

    findings: list[tuple[Path, str, int, int, tuple[str, ...]]] = []
    for md_file in md_files:
        if args.verbose:
            print(f"  {md_file.relative_to(ROOT)}")
        findings.extend(check_file(md_file))

    if not findings:
        print(f"{Colors.GREEN}✓ No duplicate headings{Colors.RESET}")
        return 0

    print(
        f"{Colors.RED}{Colors.BOLD}Duplicate headings — {len(findings)} repeat(s):{Colors.RESET}\n"
    )
    by_file: dict[Path, list[tuple[str, int, int, tuple[str, ...]]]] = {}
    for source, text, first, dup, parents in findings:
        by_file.setdefault(source, []).append((text, first, dup, parents))

    for source, items in sorted(by_file.items()):
        print(f"  {Colors.BOLD}{source}{Colors.RESET}")
        for text, first, dup, parents in items:
            scope = " › ".join(parents) if parents else "(top level)"
            print(
                f"    {Colors.YELLOW}L{dup:<5d}{Colors.RESET} "
                f"{Colors.RED}{text!r}{Colors.RESET} repeats L{first} under {scope}"
            )
        print()

    print(
        f"{Colors.YELLOW}A repeated heading under the same parent usually means a "
        f"superseded section outlived its replacement.{Colors.RESET}"
    )
    print(
        f"{Colors.YELLOW}Merge the two, or rename one so each section names itself "
        f"uniquely.{Colors.RESET}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
