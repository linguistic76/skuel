#!/usr/bin/env python3
"""
One-shot: quote every frontmatter ``title:`` whose plain scalar is not valid YAML.

Why it exists. 34 of 414 tracked docs (measured 2026-09-04 on ``0195e79b2``) carried
``title: ADR-013: KU UID Flat Identity Design`` — a colon-space inside a plain scalar,
which YAML rejects (``mapping values are not allowed here``). Every YAML-reading
consumer — ``parse_frontmatter``, ``validate_cross_references.py``, Obsidian's
Properties view — then sees an EMPTY block for that doc: its ``title``, ``category``,
``status`` and ``related_skills`` are present in the file and invisible to every
tool. The ``updated:`` stamp avoids the trap by never YAML-parsing (see
``docs_updated_field.py``); this script removes the trap itself, so that rule stays a
defence rather than a workaround.

What it changes: the ``title:`` line only, rewritten as a double-quoted scalar with
``"`` and ``\\`` escaped. **Never re-serialised** — a ``yaml.safe_load``/``dump``
round trip would reorder keys, restyle every quoted date and drop comments across
the whole block, turning a one-line fix into a corpus-wide diff nobody can review.
The edit is line-scoped in the FILE's own lines between the fences, never at an
offset into the parsed block (``split_frontmatter``'s opening fence swallows a blank
line after ``---``, so raw and file indices are not always one apart).

**It mutates files, so it re-derives its premise at run time and aborts.** Per doc:
the block must fail ``yaml.safe_load`` BEFORE, the block must have exactly one
column-0 ``title:`` line whose scalar is unquoted and carries no ``#`` comment, and
the block must parse AFTER with ``["title"]`` equal to the original scalar text —
which is the proof that the title line was the ONLY failing cause (any other defect
leaves the block failing and the doc is refused, named, unwritten). Corpus-wide,
``--apply`` refuses to run against dirty targets, and re-scans every tracked doc
afterwards: the claim is "0 docs fail YAML", and it is checked, not assumed.

A generated doc that fails is refused, not edited — the next regeneration would
undo the edit; the generator is the thing to fix.

Usage::

    uv run python scripts/quote_frontmatter_titles.py            # report; exit 1 if any
    uv run python scripts/quote_frontmatter_titles.py --apply    # write + verify

Kept after its one run: the check mode is the corpus-wide "every frontmatter block
parses" probe, and a new doc with an unquoted colon-title is one paste away.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

# scripts/ is not a package — the sibling import resolves at runtime via
# sys.path[0] but not for MyPy (matches backfill_docs_updated.py).
from docs_updated_field import (  # type: ignore[import-not-found]
    REPO_ROOT,
    dirty_docs,
    tracked_docs,
)

from core.utils.frontmatter import split_frontmatter
from core.utils.terminal_colors import Colors

_FENCE = re.compile(r"^---[ \t\r]*$")
_TITLE_LINE = re.compile(r"^title\s*:(?P<value>.*)$")


class PremiseError(Exception):
    """A doc is not the shape this fix was designed for; nothing is written."""


@dataclass(frozen=True)
class Fix:
    """One doc's planned edit — the whole file after the title line is quoted."""

    path: str
    original_title: str
    quoted_line: str
    content_after: str


def _carriage_return(line: str) -> str:
    return "\r" if line.endswith("\r") else ""


def block_parses(content: str) -> bool:
    """Does the leading frontmatter block ``yaml.safe_load``? True when there is none."""
    raw, _ = split_frontmatter(content)
    if raw is None:
        return True
    try:
        yaml.safe_load(raw)
    except yaml.YAMLError:
        return False
    return True


def quote_title(content: str) -> tuple[str, str, str]:
    """Return ``(content_after, original_scalar, quoted_line)`` for a doc whose block
    fails YAML on its unquoted ``title:`` alone.

    Raises ``PremiseError`` for every other shape: a block that already parses, no or
    several ``title:`` lines, a title already quoted, a ``#`` in the scalar (a YAML
    comment the quoting would silently fold into the title), or a block that STILL
    fails after the title is quoted — that last one means a second defect, which
    this script does not own.
    """
    if block_parses(content):
        raise PremiseError("frontmatter already parses — nothing to quote")

    lines = content.split("\n")
    closing = next(
        (index for index in range(1, len(lines)) if _FENCE.match(lines[index])),
        None,
    )
    if closing is None:
        raise PremiseError("frontmatter fence never closes")

    hits = [
        (index, match) for index in range(1, closing) if (match := _TITLE_LINE.match(lines[index]))
    ]
    if len(hits) != 1:
        raise PremiseError(f"{len(hits)} column-0 `title:` lines in the block, expected 1")

    index, match = hits[0]
    cr = _carriage_return(lines[index])
    scalar = match.group("value").rstrip("\r").strip()
    if not scalar:
        raise PremiseError("`title:` is empty")
    if scalar[0] in "\"'":
        raise PremiseError(f"`title:` is already quoted ({scalar!r}) — the failure is elsewhere")
    if " #" in scalar or scalar.startswith("#"):
        raise PremiseError(
            f"`title:` carries a `#` ({scalar!r}) — YAML reads a comment there; quote by hand"
        )

    # JSON string syntax is a valid YAML double-quoted scalar; `ensure_ascii=False`
    # keeps non-ASCII characters literal instead of `\uXXXX`-escaping them.
    quoted_line = f"title: {json.dumps(scalar, ensure_ascii=False)}{cr}"
    candidate = list(lines)
    candidate[index] = quoted_line
    content_after = "\n".join(candidate)

    raw, _ = split_frontmatter(content_after)
    if raw is None:
        raise PremiseError("block vanished after the edit")
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as failure:
        raise PremiseError(
            f"block still fails YAML with the title quoted — a second defect: {failure}"
        ) from failure
    parsed_title = parsed.get("title") if isinstance(parsed, dict) else parsed
    if parsed_title != scalar:
        raise PremiseError(f"round trip mismatch: parsed title {parsed_title!r} != {scalar!r}")
    return content_after, scalar, quoted_line


def scan() -> tuple[list[str], list[str], list[str]]:
    """``(failing_stampable, failing_generated, all_docs)`` over every tracked doc."""
    stampable, generated = tracked_docs()
    failing = [p for p in stampable if not block_parses(_read(p))]
    failing_generated = [p for p in generated if not block_parses(_read(p))]
    return failing, failing_generated, stampable + generated


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def build_plan(failing: list[str]) -> tuple[list[Fix], list[tuple[str, str]]]:
    """A ``Fix`` per doc whose only defect is the title, and the refusals by name."""
    fixes: list[Fix] = []
    refused: list[tuple[str, str]] = []
    for path in failing:
        try:
            after, scalar, line = quote_title(_read(path))
        except PremiseError as why:
            refused.append((path, str(why)))
            continue
        fixes.append(Fix(path, scalar, line, after))
    return fixes, refused


def verify_clean(paths: list[str]) -> None:
    """Refuse to rewrite a doc with uncommitted changes — a failed write must be
    recoverable from git, and the result must be reviewable as its own diff."""
    conflicts = sorted(dirty_docs() & set(paths))
    if conflicts:
        raise PremiseError(
            f"{len(conflicts)} target docs have uncommitted changes; commit or stash "
            f"them first. First: {conflicts[:3]}"
        )


def apply(fixes: list[Fix]) -> None:
    """Write every fix, then re-read and confirm each says what was planned."""
    for fix in fixes:
        (REPO_ROOT / fix.path).write_text(fix.content_after, encoding="utf-8")
    for fix in fixes:
        content = _read(fix.path)
        raw, _ = split_frontmatter(content)
        parsed = yaml.safe_load(raw) if raw is not None else None
        parsed_title = parsed.get("title") if isinstance(parsed, dict) else parsed
        if parsed_title != fix.original_title:
            raise PremiseError(
                f"{fix.path}: after writing, title reads {parsed_title!r}, "
                f"expected {fix.original_title!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the files (default: report and change nothing; exit 1 if any fail)",
    )
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    failing, failing_generated, docs = scan()
    fixes, refused = build_plan(failing)

    print(
        f"{Colors.BOLD}Frontmatter YAML{Colors.RESET} — {len(docs)} tracked docs, "
        f"{len(failing) + len(failing_generated)} fail to parse"
    )
    for fix in fixes:
        print(f"  {Colors.YELLOW}{fix.path}{Colors.RESET}: {fix.quoted_line.rstrip()}")
    for path, why in refused:
        print(f"  {Colors.RED}{path}{Colors.RESET}: REFUSED — {why}")
    for path in failing_generated:
        print(f"  {Colors.RED}{path}{Colors.RESET}: REFUSED — generated doc; fix its generator")

    if not failing and not failing_generated:
        print(f"\n{Colors.GREEN}✓ Every frontmatter block parses{Colors.RESET}")
        return 0

    if not args.apply:
        print(
            f"\n{Colors.CYAN}Dry run — {len(fixes)} doc(s) would be quoted"
            f"{f', {len(refused) + len(failing_generated)} refused' if refused or failing_generated else ''}."
            f" Re-run with --apply to write.{Colors.RESET}"
        )
        return 1

    if refused or failing_generated:
        print(
            f"\n{Colors.RED}✗ {len(refused) + len(failing_generated)} doc(s) refused — "
            f"nothing written. Fix them by hand, then re-run.{Colors.RESET}"
        )
        return 2

    try:
        verify_clean([fix.path for fix in fixes])
        apply(fixes)
    except PremiseError as failure:
        print(f"{Colors.RED}✗ {failure}{Colors.RESET}")
        return 2

    still_failing, still_generated, _ = scan()
    if still_failing or still_generated:
        print(
            f"{Colors.RED}✗ {len(still_failing) + len(still_generated)} doc(s) still fail "
            f"after writing: {(still_failing + still_generated)[:3]}{Colors.RESET}"
        )
        return 2

    print(
        f"\n{Colors.GREEN}✓ Quoted {len(fixes)} title(s); every frontmatter block parses{Colors.RESET}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
