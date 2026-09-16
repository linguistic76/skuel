#!/usr/bin/env python3
"""Print the coverage gap picture — three Markdown tables from a ``coverage.json``.

Reads the JSON report ``scripts/run_tests.py --cov`` writes (``coverage.json``, the
path in pyproject's ``[tool.coverage.json]``) and prints, to stdout:

  1. per-package line rates — the top two path segments (``core/services``,
     ``adapters/inbound``, ``ui``), packages of at least 200 statements, lowest first;
  2. files with zero coverage, at least 20 statements, largest first;
  3. large files (at least 150 statements) under 50 %, most missed statements first.

Markdown, so the same text reads in a terminal and renders as tables when the weekly
composed run appends it to its step summary (``.github/workflows/composed-test-run.yml``).

An instrument, never a gate: the exit code is non-zero only when the report cannot be
read. No coverage number carries a threshold anywhere in SKUEL — pass rate is the
quality metric; this is where to look for the next test worth writing.

Why the JSON report and not the Cobertura ``coverage.xml`` written beside it: the run
names four source trees (``--cov=core --cov=adapters --cov=ui --cov=services_bootstrap``),
and coverage's XML writer records each file relative to ITS OWN tree, keyed by that
relative name — ``core/auth/__init__.py`` and ``ui/auth/__init__.py`` are one entry,
``auth/graph_auth.py`` names no tree, and the package ``.`` merges the roots of all four.
The JSON report keys every file by its path from the app root, so nothing collides and
every row here is a path a reader can open.

Usage:
    uv run python scripts/coverage_summary.py [coverage.json]
    ./dev coverage-summary [path]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPORT = Path("coverage.json")

# The thresholds that make a row worth a reader's glance. A tiny module at 0 % is
# usually an ``__init__`` or a stub; a package under 200 statements swings on one
# test. All three tables are size-gated so the picture is about mass, not noise.
PACKAGE_MIN_STATEMENTS = 200
ZERO_COVERAGE_MIN_STATEMENTS = 20
LOW_COVERAGE_MIN_STATEMENTS = 150
LOW_COVERAGE_MAX_RATE = 0.5

# Row caps keep the step summary readable; a capped table says how many rows it hides.
ZERO_COVERAGE_MAX_ROWS = 60
LOW_COVERAGE_MAX_ROWS = 40


@dataclass(frozen=True)
class FileCoverage:
    """One measured file: its path from the app root and its statement counts."""

    path: str
    statements: int
    covered: int

    @property
    def missed(self) -> int:
        return self.statements - self.covered

    @property
    def rate(self) -> float:
        """Covered fraction; a file with no statements counts as fully covered."""
        return self.covered / self.statements if self.statements else 1.0


@dataclass(frozen=True)
class PackageCoverage:
    """A package row: the summed statements of every file under one key."""

    key: str
    statements: int
    covered: int

    @property
    def rate(self) -> float:
        return self.covered / self.statements if self.statements else 1.0


@dataclass(frozen=True)
class CoverageReport:
    """What one ``coverage.json`` says: every file, the totals, and its provenance."""

    files: tuple[FileCoverage, ...]
    total_statements: int
    total_covered: int
    generated_at: str
    coverage_version: str

    @property
    def rate(self) -> float:
        return self.total_covered / self.total_statements if self.total_statements else 1.0


class ReportError(Exception):
    """The report file is missing, unreadable, or not a coverage.py JSON report."""


def load_report(path: Path) -> CoverageReport:
    """Parse a coverage.py JSON report (format 3: ``meta`` / ``files`` / ``totals``)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"{path} is not JSON: {exc}") from exc

    try:
        files = tuple(
            FileCoverage(
                path=file_path,
                statements=int(entry["summary"]["num_statements"]),
                covered=int(entry["summary"]["covered_lines"]),
            )
            for file_path, entry in data["files"].items()
        )
        totals = data["totals"]
        meta = data.get("meta", {})
        return CoverageReport(
            files=files,
            total_statements=int(totals["num_statements"]),
            total_covered=int(totals["covered_lines"]),
            generated_at=str(meta.get("timestamp", "unknown time")),
            coverage_version=str(meta.get("version", "unknown version")),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ReportError(
            f"{path} is not a coverage.py JSON report (expected meta/files/totals): {exc!r}"
        ) from exc


def package_key(file_path: str) -> str:
    """The package a file is tallied under: its first two path segments.

    ``core/services/ku/ku_service.py`` → ``core/services``; ``ui/theme.py`` → ``ui``.
    A file directly under a tree root belongs to the tree.
    """
    parts = file_path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def per_package(files: tuple[FileCoverage, ...]) -> list[PackageCoverage]:
    """Packages of at least ``PACKAGE_MIN_STATEMENTS``, lowest rate first."""
    statements: Counter[str] = Counter()
    covered: Counter[str] = Counter()
    for file in files:
        key = package_key(file.path)
        statements[key] += file.statements
        covered[key] += file.covered
    rows = [
        PackageCoverage(key=key, statements=total, covered=covered[key])
        for key, total in statements.items()
        if total >= PACKAGE_MIN_STATEMENTS
    ]
    return sorted(rows, key=_package_sort_key)


def _package_sort_key(row: PackageCoverage) -> tuple[float, str]:
    return (row.rate, row.key)


def zero_coverage(files: tuple[FileCoverage, ...]) -> list[FileCoverage]:
    """Files nothing executed, at least ``ZERO_COVERAGE_MIN_STATEMENTS``, largest first."""
    rows = [
        file
        for file in files
        if file.covered == 0 and file.statements >= ZERO_COVERAGE_MIN_STATEMENTS
    ]
    return sorted(rows, key=_largest_first)


def _largest_first(file: FileCoverage) -> tuple[int, str]:
    return (-file.statements, file.path)


def large_low_coverage(files: tuple[FileCoverage, ...]) -> list[FileCoverage]:
    """Files of at least ``LOW_COVERAGE_MIN_STATEMENTS`` under 50 %, most missed first.

    Zero-coverage files are listed by :func:`zero_coverage` and are not repeated here.
    """
    rows = [
        file
        for file in files
        if file.statements >= LOW_COVERAGE_MIN_STATEMENTS
        and file.covered > 0
        and file.rate < LOW_COVERAGE_MAX_RATE
    ]
    return sorted(rows, key=_most_missed_first)


def _most_missed_first(file: FileCoverage) -> tuple[int, str]:
    return (-file.missed, file.path)


def _pct(rate: float) -> str:
    return f"{100 * rate:.1f} %"


def _n(value: int) -> str:
    return f"{value:,}"


def render(report: CoverageReport) -> str:
    """The three tables as Markdown, headed by the total."""
    lines = [
        f"## Coverage — {_pct(report.rate)} of {_n(report.total_statements)} statements"
        f" ({_n(report.total_covered)} covered)",
        "",
        f"_{len(report.files):,} files measured; report written {report.generated_at}"
        f" by coverage {report.coverage_version}. An instrument, not a gate — no threshold._",
        "",
    ]

    packages = per_package(report.files)
    lines += [
        f"### Per package (≥ {PACKAGE_MIN_STATEMENTS} statements, lowest first)",
        "",
        "| Package | Statements | Covered | Rate |",
        "|---|---:|---:|---:|",
    ]
    lines += [
        f"| `{row.key}` | {_n(row.statements)} | {_n(row.covered)} | {_pct(row.rate)} |"
        for row in packages
    ]
    if not packages:
        lines.append(f"| _none of ≥ {PACKAGE_MIN_STATEMENTS} statements_ | | | |")

    zero = zero_coverage(report.files)
    lines += [
        "",
        f"### Files with zero coverage (≥ {ZERO_COVERAGE_MIN_STATEMENTS} statements)"
        f" — {len(zero)} files, {_n(sum(f.statements for f in zero))} statements",
        "",
        "| Statements | File |",
        "|---:|---|",
    ]
    lines += [f"| {_n(f.statements)} | `{f.path}` |" for f in zero[:ZERO_COVERAGE_MAX_ROWS]]
    if len(zero) > ZERO_COVERAGE_MAX_ROWS:
        lines.append(f"| … | _{len(zero) - ZERO_COVERAGE_MAX_ROWS} more_ |")
    if not zero:
        lines.append("| _none_ | |")

    low = large_low_coverage(report.files)
    lines += [
        "",
        f"### Large files (≥ {LOW_COVERAGE_MIN_STATEMENTS} statements)"
        f" under {_pct(LOW_COVERAGE_MAX_RATE)} — {len(low)} files",
        "",
        "| Rate | Statements | Missed | File |",
        "|---:|---:|---:|---|",
    ]
    lines += [
        f"| {_pct(f.rate)} | {_n(f.statements)} | {_n(f.missed)} | `{f.path}` |"
        for f in low[:LOW_COVERAGE_MAX_ROWS]
    ]
    if len(low) > LOW_COVERAGE_MAX_ROWS:
        lines.append(f"| … | | | _{len(low) - LOW_COVERAGE_MAX_ROWS} more_ |")
    if not low:
        lines.append("| _none_ | | | |")

    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    """``coverage_summary.py [coverage.json]`` — tables to stdout, problems to stderr."""
    parser = argparse.ArgumentParser(
        prog="coverage_summary.py",
        description="Print the coverage gap picture (three Markdown tables) from a coverage.json.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "report",
        nargs="?",
        default=DEFAULT_REPORT,
        type=Path,
        help=f"the JSON report to read (default: {DEFAULT_REPORT})",
    )
    args = parser.parse_args(argv)
    try:
        report = load_report(args.report)
    except ReportError as exc:
        print(f"coverage_summary: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
