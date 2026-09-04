#!/usr/bin/env python3
"""History-in-code finder — an advisory census of comments and docstrings that
narrate a fix's story where the rule should stand.

The rule (CLAUDE.md § Docstring Philosophy · DOCSTRING_STANDARDS.md Anti-Pattern 4
· AGENTS.md § Style): a comment or docstring states what the code does now. What
it used to do, which PR changed it and when belong to the commit message and the
ADR or ``done/`` doc; a comment may point at the record, never retell it. This
tool measures how much prose in the tree still retells, and orders the files so
the sweep (``docs/roadmap/deferred-work.md`` § History-in-Code Sweep) takes the
heaviest first.

What it reads — and only this:

- COMMENT tokens, via ``tokenize``.
- Docstrings of Module / ClassDef / FunctionDef / AsyncFunctionDef, via
  ``ast.get_docstring`` (uncleaned, so every docstring line keeps its source line).

String literals, f-strings and log messages are never read. A date in DSL example
data, a month name in a fixture, a PR number in a user-facing message are not prose
about the code, and reading prose alone is what makes this census tighter than a
grep over the same trees.

Signals, counted per category (a line may carry several; ``dominant`` is the first
it carries in this order):

- ``pr_tag``   an arc-internal tag: ``PR-3``, ``(PR #1241``
- ``pr_ref``   a bare PR number: ``#965`` (3–4 digits, not inside a path or a word)
- ``date``     ``2026-08`` / ``2026-08-06``
- ``phrase``   used to · no longer · formerly · previously · was/were deleted ·
               was/were removed · stopped ‹verb›ing · fixed/since/until 20xx

Not flagged, by design:

- A pointer line — ``See:`` / ``Backend:`` opening the comment or the docstring
  line. A pointer at the record is the sanctioned form, whatever date or number
  the record's title carries.
- ``ADR-074`` and ``done/….md`` citations: they contain no signal token.
- The "utilized" idiom and the runtime sense, ruled out by grammar: ``Used to
  weight …`` (sentence-initial) and ``can be used to probe`` carry no history, so
  ``used to`` counts only in lowercase and not after a form of *be*;
  ``previously-recorded`` is a compound adjective about state, so ``previously``
  counts only unhyphenated.
- The known false positive is REPORTED, not special-cased: a docstring that
  documents a real date-typed field or a date format (``YYYY-MM-DD, e.g.
  2026-08-06``). There is no exemption syntax — one becomes a suppression ritual,
  and the sweep reads every hit anyway.

Advisory, never a gate: exit 0 whatever it finds; not in ``./dev quality``,
pre-commit or ``./dev health``. A prose lint is itself noise and flow-blind; this
is a census that orders a queue.

Usage:
    ./dev history-in-code                      # per-file table, most hits first
    ./dev history-in-code --top 20 --verbose   # the sweep queue, every hit listed
    ./dev history-in-code --json > hits.json   # machine-readable (status → stderr)
    ./dev history-in-code core/services/tasks  # any files or directories
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Tests and scripts/ are out: tests carry rationale legitimately, scripts are CLI prose.
DEFAULT_SCOPE: tuple[str, ...] = ("core", "adapters", "ui", "services_bootstrap")

# Order = dominance order: the first category a line carries names it.
SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pr_tag", re.compile(r"\bPR-\d\b|\(PR #\d+")),
    ("pr_ref", re.compile(r"(?<![\w/])#\d{3,4}\b")),
    ("date", re.compile(r"\b20\d\d-\d\d(?:-\d\d)?\b")),
    (
        "phrase",
        # Two grammar rulings inside the case-insensitive net: ``used to`` counts only
        # in lowercase and not after a form of *be* (``Used to weight …`` and ``can be
        # used to probe`` are the "utilized" idiom); ``previously`` counts only
        # unhyphenated (``previously-recorded`` is a compound adjective about state).
        re.compile(
            r"(?<!\bbe )(?<!\bis )(?<!\bare )(?<!\bwas )(?<!\bwere )(?<!\bbeen )(?<!\bbeing )(?-i:used to)"
            r"|no longer|formerly|previously(?!-)|was deleted|were deleted"
            r"|was removed|were removed|stopped \w+ing|fixed 20\d\d|since 20\d\d|until 20\d\d",
            re.IGNORECASE,
        ),
    ),
)
CATEGORIES: tuple[str, ...] = tuple(name for name, _ in SIGNALS)

# A pointer at the record — the sanctioned form — is never a hit.
POINTER_LINE = re.compile(r"^\s*(?:See|Backend):", re.IGNORECASE)

DOCSTRING_HOSTS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

Kind = str  # "comment" | "docstring"


@dataclass(frozen=True)
class Hit:
    """One prose line carrying at least one signal."""

    lineno: int
    kind: Kind
    categories: tuple[str, ...]
    text: str

    @property
    def dominant(self) -> str:
        return self.categories[0]


@dataclass(frozen=True)
class FileReport:
    """Every hit in one file, plus the size the density is measured against."""

    path: str
    source_lines: int
    hits: tuple[Hit, ...]

    @property
    def hit_count(self) -> int:
        return len(self.hits)

    @property
    def density(self) -> float:
        """Hits per 100 source lines — the tiebreak between files with equal hits."""
        if not self.source_lines:
            return 0.0
        return 100.0 * self.hit_count / self.source_lines

    def by_category(self) -> dict[str, int]:
        counts = Counter(category for hit in self.hits for category in hit.categories)
        return {category: counts.get(category, 0) for category in CATEGORIES}


def classify(text: str) -> tuple[str, ...]:
    """The categories one prose line carries, in dominance order; empty when clean."""
    if POINTER_LINE.match(text):
        return ()
    return tuple(name for name, pattern in SIGNALS if pattern.search(text))


def prose_lines(source: str) -> list[tuple[int, Kind, str]]:
    """Every comment line and every docstring line, as (lineno, kind, text).

    Comments come from the tokenizer, docstrings from the AST — nothing else in the
    source is read. Raises ``SyntaxError`` / ``tokenize.TokenError`` for source
    Python cannot parse; the caller reports such a file as skipped.
    """
    lines: list[tuple[int, Kind, str]] = [
        (token.start[0], "comment", token.string.lstrip("#").strip())
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, DOCSTRING_HOSTS):
            continue
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        # Uncleaned, so offset i of the value sits on source line start + i.
        start = node.body[0].lineno
        for offset, line in enumerate(docstring.split("\n")):
            if line.strip():
                lines.append((start + offset, "docstring", line.strip()))
    lines.sort()
    return lines


def scan_source(source: str, path: str) -> FileReport:
    """Census one file's prose; ``path`` is the label the report carries."""
    hits = tuple(
        Hit(lineno, kind, categories, text)
        for lineno, kind, text in prose_lines(source)
        if (categories := classify(text))
    )
    return FileReport(path=path, source_lines=len(source.splitlines()), hits=hits)


def python_files(paths: list[Path]) -> list[Path]:
    """The ``.py`` files under the given files and directories, deduplicated, sorted."""
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
            continue
        files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def label_for(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT):
        return resolved.relative_to(ROOT).as_posix()
    return path.as_posix()


def scan_paths(paths: list[Path]) -> tuple[list[FileReport], list[str]]:
    """Reports for every parseable file (hits or not) and the labels of the rest.

    A file Python cannot parse is listed, never silently dropped — a count that
    quietly excludes files is a census that lies about its own coverage.
    """
    reports: list[FileReport] = []
    skipped: list[str] = []
    for file in python_files(paths):
        label = label_for(file)
        try:
            source = file.read_text(encoding="utf-8")
            reports.append(scan_source(source, label))
        except SyntaxError, tokenize.TokenError, UnicodeDecodeError:
            skipped.append(label)
    return reports, skipped


def ranked(reports: list[FileReport], top: int | None) -> list[FileReport]:
    """Files with hits, most hits first (ties: denser, then path); ``top`` truncates.

    Hits, not density, orders the sweep: a file a reader meets history in twenty
    times is one PR-sized slice, while density alone front-loads one-line files.
    """
    with_hits = [report for report in reports if report.hits]
    with_hits.sort(key=_rank_key)
    return with_hits[:top] if top else with_hits


def _rank_key(report: FileReport) -> tuple[int, float, str]:
    return (-report.hit_count, -report.density, report.path)


def totals(reports: list[FileReport]) -> dict[str, int]:
    counts = Counter(
        category for report in reports for hit in report.hits for category in hit.categories
    )
    return {category: counts.get(category, 0) for category in CATEGORIES}


def json_document(
    reports: list[FileReport], skipped: list[str], scope: list[str], top: int | None
) -> dict[str, Any]:
    """The ``--json`` shape: totals over the whole scan, files ranked and truncated."""
    return {
        "advisory": True,
        "scope": scope,
        "files_scanned": len(reports),
        "files_with_hits": sum(1 for report in reports if report.hits),
        "total_hits": sum(report.hit_count for report in reports),
        "by_category": totals(reports),
        "skipped": skipped,
        "files": [
            {
                "path": report.path,
                "source_lines": report.source_lines,
                "hits": report.hit_count,
                "density": round(report.density, 2),
                "by_category": report.by_category(),
                "lines": [
                    {
                        "lineno": hit.lineno,
                        "kind": hit.kind,
                        "dominant": hit.dominant,
                        "categories": list(hit.categories),
                        "text": hit.text,
                    }
                    for hit in report.hits
                ],
            }
            for report in ranked(reports, top)
        ],
    }


def print_report(
    reports: list[FileReport], skipped: list[str], scope: list[str], top: int | None, verbose: bool
) -> None:
    rows = ranked(reports, top)
    print(f"History in code — advisory census over {' '.join(scope)}")
    print("(comments via tokenize, docstrings via ast; strings and log messages unread)\n")
    if not rows:
        print("No hits.")
    else:
        header = f"{'hits':>5} {'/100':>5} " + " ".join(f"{c:>7}" for c in CATEGORIES) + "  file"
        print(header)
        for report in rows:
            counts = report.by_category()
            cells = " ".join(f"{counts[c]:>7}" for c in CATEGORIES)
            print(f"{report.hit_count:>5} {report.density:>5.1f} {cells}  {report.path}")
            if verbose:
                for hit in report.hits:
                    text = hit.text if len(hit.text) <= 96 else hit.text[:93] + "..."
                    print(
                        f"        L{hit.lineno:<5} {hit.kind:<9} [{','.join(hit.categories)}] {text}"
                    )
    by_category = totals(reports)
    total_hits = sum(report.hit_count for report in reports)
    files_with_hits = sum(1 for report in reports if report.hits)
    shown = f" (showing {len(rows)})" if top and len(rows) < files_with_hits else ""
    print(
        f"\nTotal: {total_hits} lines in {files_with_hits} files{shown}; "
        f"{len(reports)} files scanned; " + " · ".join(f"{c} {n}" for c, n in by_category.items())
    )
    if skipped:
        print(f"Skipped (not parseable as Python): {', '.join(skipped)}")
    print("Advisory — exit 0 always. Sweep queue: ./dev history-in-code --top 20 --verbose")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Advisory census of history narrated in comments and docstrings (exit 0 always)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help=f"files or directories to scan (default: {' '.join(DEFAULT_SCOPE)})",
    )
    parser.add_argument(
        "--top", type=int, metavar="N", help="the N files with most hits — the sweep queue's order"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="list every hit under its file"
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="emit the census as JSON on stdout"
    )
    return parser


def resolve_paths(
    parser: argparse.ArgumentParser, given: list[str]
) -> tuple[list[Path], list[str]]:
    if not given:
        return [ROOT / name for name in DEFAULT_SCOPE], list(DEFAULT_SCOPE)
    paths = [Path(p) for p in given]
    for path in paths:
        if not path.exists():
            parser.error(f"no such path: {path}")
    return paths, [label_for(path) for path in paths]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths, scope = resolve_paths(parser, args.paths)
    reports, skipped = scan_paths(paths)
    if args.as_json:
        print(json.dumps(json_document(reports, skipped, scope, args.top), indent=2))
    else:
        print_report(reports, skipped, scope, args.top, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
