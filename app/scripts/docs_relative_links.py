#!/usr/bin/env python3
"""
Rewrite docs→docs markdown links to the path-relative form.

The rule: a markdown link whose BOTH ends are inside ``docs/`` is written relative to
the citing file (``../patterns/FOO.md``; a sibling is just ``FOO.md``). Every other
citation — a doc citing ``/core/…``, a skill or CLAUDE.md citing a doc — stays
repo-root-absolute. Two forms, one per direction; never two spellings of one direction.

Why it exists. ``docs/`` opens as an Obsidian vault (``docs/.obsidian/app.json``:
``useMarkdownLinks`` + ``newLinkFormat: relative``), and Obsidian's rename propagation
reaches only the links it resolves — the relative ones. A ``/docs/…`` link is invisible
to it, so on the first Obsidian-driven rename every absolute docs→docs citation rots
silently while the relative ones are rewritten. One sweep BEFORE any Obsidian editing
removes the question, and removes the second spelling Obsidian's autocomplete would
otherwise sit beside forever.

What it changes: the path part of a ``[text](/docs/…)`` link whose target EXISTS under
``docs/``, rewritten to ``os.path.relpath`` from the citing file's directory — anchor
kept, link text untouched, spaces re-encoded as ``%20``, one link at a time (a line may
hold several). Links are found with the dead-link checker's own grammar
(``MARKDOWN_LINK_RE`` / ``extract_markdown_links``) and resolved with its
``resolve_path``, so what this rewrites is exactly what that checker checks — inside
fences and inline code included, as that pass reads them.

What it leaves alone, deliberately:

- A DEAD ``/docs/…`` target. Those belong to
  ``docs/roadmap/dead-doc-links-sweep-queue.md`` under its own ruling: fix the citing
  prose, and look for a RENAMED successor before deleting a citation. Rewriting a dead
  absolute path to a dead relative one only renames the finding and invalidates that
  queue's counts.
- A GENERATED doc (``CROSS_REFERENCE_INDEX.md``, ``BASESERVICE_METHOD_INDEX.md``): the
  next regeneration would undo the edit. Its generator emits the relative form itself;
  a convertible link found there is REFUSED and reported — fix the generator.

It mutates files, so it proves its claim at run time. Per link: the rewritten target
resolves to the same file as the original, asserted BEFORE anything is written (one
mismatch aborts the whole run). Corpus-wide: ``--apply`` refuses dirty targets (through
``docs_updated_field.dirty_docs`` — the one implementation, the one that survives
porcelain's C-quoted paths), re-reads every written file against its plan, and
re-scans. The claim is "0 absolute docs→docs links", and it is checked, not assumed.

NOT wired into ``./dev health`` (ruled 2026-09-04: script-only, advisory). Run it when
absolute docs→docs links reappear — the default mode names every one.

Usage::

    uv run python scripts/docs_relative_links.py            # report; exit 1 if any
    uv run python scripts/docs_relative_links.py --apply    # rewrite + verify
    ./dev docs-links [--apply]                              # the same, via dev
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "health"))

# scripts/ and scripts/health/ are not packages — the sibling imports resolve at
# runtime via sys.path but not for MyPy (matches quote_frontmatter_titles.py). The
# checker is imported as a module, not by name, so a test can point `ddl.ROOT` at a
# fixture tree and every resolution here follows it.
import dead_doc_links as ddl  # type: ignore[import-not-found]
from docs_updated_field import (  # type: ignore[import-not-found]
    REPO_ROOT,
    dirty_docs,
    tracked_docs,
)

from core.utils.terminal_colors import Colors

DOCS_PREFIX = "/docs/"


class PremiseError(Exception):
    """The corpus is not in the shape this rewrite was designed for; nothing is written."""


@dataclass(frozen=True)
class Rewrite:
    """One link: which doc and line, what it says, what it will say."""

    path: str  # repo-root-relative, as `tracked_docs` names it
    line_no: int
    old: str
    new: str


def _docs_dir() -> Path:
    return (ddl.ROOT / "docs").resolve()


def relative_target(raw: str, source: Path) -> str | None:
    """The relative spelling of ``raw`` from ``source``'s directory, or ``None`` when
    the link is not a convertible docs→docs link.

    Convertible: the destination starts with ``/docs/`` once ``%``-decoded, and it
    resolves to an EXISTING path inside ``docs/`` — so ``/docs/../core/x.py`` and a dead
    target are both left as written.
    """
    path_part, hash_sign, anchor = raw.partition("#")
    path_part = path_part.strip()
    if not urllib.parse.unquote(path_part).startswith(DOCS_PREFIX):
        return None
    target = ddl.resolve_path(raw, source)
    if target is None or not target.exists():
        return None
    resolved = target.resolve()
    if not resolved.is_relative_to(_docs_dir()):
        return None
    relative = Path(os.path.relpath(resolved, source.resolve().parent)).as_posix()
    if path_part.endswith("/"):
        relative += "/"
    return relative.replace(" ", "%20") + hash_sign + anchor


def _rewrite_line(
    line: str, source: Path, checkable: set[str]
) -> tuple[str, list[tuple[str, str]]]:
    """One line with every convertible link rewritten, plus its ``(old, new)`` pairs."""
    pairs: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        raw = match.group(2).strip()
        if raw not in checkable:
            return match.group(0)
        new = relative_target(raw, source)
        if new is None:
            return match.group(0)
        pairs.append((raw, new))
        return f"[{match.group(1)}]({new})"

    return ddl.MARKDOWN_LINK_RE.sub(replace, line), pairs


def rewrite_content(content: str, source: Path) -> tuple[str, list[tuple[int, str, str]]]:
    """``(content_after, [(line_no, old, new), …])`` with every convertible link rewritten.

    Only destinations the checker would check are candidates — the set is keyed by the
    raw destination alone, which is exactly what ``_is_checkable_link_target`` reads, so
    the line split here cannot disagree with the checker's own.
    """
    checkable = {raw for _line_no, _text, raw in ddl.extract_markdown_links(content)}
    lines = content.split("\n")
    changes: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        lines[index], pairs = _rewrite_line(line, source, checkable)
        changes.extend((index + 1, old, new) for old, new in pairs)
    return "\n".join(lines), changes


def verify_resolution(rewrite: Rewrite) -> None:
    """The rewritten link must resolve to the same file as the original — the whole
    claim of a form-only sweep — and must stay checkable (no raw space)."""
    source = REPO_ROOT / rewrite.path
    before = ddl.resolve_path(rewrite.old, source)
    after = ddl.resolve_path(rewrite.new, source)
    if before is None or after is None or before.resolve() != after.resolve():
        raise PremiseError(
            f"{rewrite.path}:{rewrite.line_no}: ({rewrite.old}) resolves to {before} but "
            f"({rewrite.new}) resolves to {after} — rewrite refused"
        )
    if " " in rewrite.new.partition("#")[0]:
        raise PremiseError(
            f"{rewrite.path}:{rewrite.line_no}: ({rewrite.new}) carries a raw space, which "
            "the checker treats as not-a-link — rewrite refused"
        )


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def plan(paths: list[str]) -> dict[str, tuple[str, list[Rewrite]]]:
    """``{path: (content_after, rewrites)}`` for every doc in ``paths`` with a change."""
    planned: dict[str, tuple[str, list[Rewrite]]] = {}
    for path in paths:
        after, changes = rewrite_content(_read(path), REPO_ROOT / path)
        if changes:
            planned[path] = (after, [Rewrite(path, n, old, new) for n, old, new in changes])
    return planned


def scan() -> tuple[list[Rewrite], list[Rewrite], int]:
    """``(rewrites in hand-maintained docs, convertible links in generated docs, docs
    scanned)`` over every tracked doc."""
    stampable, generated = tracked_docs()
    hand = [r for _after, rewrites in plan(stampable).values() for r in rewrites]
    gen = [r for _after, rewrites in plan(generated).values() for r in rewrites]
    return hand, gen, len(stampable) + len(generated)


def verify_clean(paths: list[str]) -> None:
    """Refuse to rewrite a doc with uncommitted changes — a failed write must be
    recoverable from git, and the result must be reviewable as its own diff."""
    conflicts = sorted(dirty_docs() & set(paths))
    if conflicts:
        raise PremiseError(
            f"{len(conflicts)} target docs have uncommitted changes; commit or stash "
            f"them first. First: {conflicts[:3]}"
        )


def apply(planned: dict[str, tuple[str, list[Rewrite]]]) -> None:
    """Prove every rewrite, then write, then re-read: each file must hold its plan."""
    for _after, rewrites in planned.values():
        for rewrite in rewrites:
            verify_resolution(rewrite)
    verify_clean(list(planned))
    for path, (after, _rewrites) in planned.items():
        (REPO_ROOT / path).write_text(after, encoding="utf-8")
    for path, (after, _rewrites) in planned.items():
        if _read(path) != after:
            raise PremiseError(f"{path}: after writing, the file does not match its plan")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="rewrite the files (default: report and change nothing; exit 1 if any)",
    )
    args = parser.parse_args()

    if not sys.stdout.isatty():
        Colors.disable()

    rewrites, generated_hits, scanned = scan()
    files = sorted({r.path for r in rewrites})
    print(
        f"{Colors.BOLD}docs→docs link form{Colors.RESET} — {scanned} tracked docs, "
        f"{len(rewrites)} absolute docs→docs link(s) in {len(files)} file(s)"
    )
    for rewrite in rewrites:
        print(
            f"  {Colors.YELLOW}{rewrite.path}:{rewrite.line_no}{Colors.RESET}: "
            f"({rewrite.old}) → ({rewrite.new})"
        )
    for rewrite in generated_hits:
        print(
            f"  {Colors.RED}{rewrite.path}:{rewrite.line_no}{Colors.RESET}: REFUSED — "
            f"generated doc; make its generator emit ({rewrite.new})"
        )

    if not rewrites and not generated_hits:
        print(f"\n{Colors.GREEN}✓ Every docs→docs link is relative{Colors.RESET}")
        return 0

    if not args.apply:
        refused = f", {len(generated_hits)} refused" if generated_hits else ""
        print(
            f"\n{Colors.CYAN}Dry run — {len(rewrites)} link(s) in {len(files)} file(s) "
            f"would be rewritten{refused}. Re-run with --apply to write.{Colors.RESET}"
        )
        return 1

    if generated_hits:
        print(
            f"\n{Colors.RED}✗ {len(generated_hits)} link(s) in generated docs refused — "
            f"nothing written. Fix the generator, regenerate, then re-run.{Colors.RESET}"
        )
        return 2

    try:
        apply(plan(files))
    except PremiseError as failure:
        print(f"{Colors.RED}✗ {failure}{Colors.RESET}")
        return 2

    still, still_generated, _ = scan()
    if still or still_generated:
        remaining = still + still_generated
        print(
            f"{Colors.RED}✗ {len(remaining)} absolute docs→docs link(s) remain after "
            f"writing: {[(r.path, r.line_no) for r in remaining[:3]]}{Colors.RESET}"
        )
        return 2

    print(
        f"\n{Colors.GREEN}✓ Rewrote {len(rewrites)} link(s) in {len(files)} file(s); "
        f"every docs→docs link is relative{Colors.RESET}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
