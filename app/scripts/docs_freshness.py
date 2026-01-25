#!/usr/bin/env python3
"""
Documentation Freshness Checker

Detects stale documentation by comparing modification times between docs and the
code files they reference. When a referenced code file is newer than its
documentation, the doc is flagged as potentially stale.

Usage:
    poetry run python scripts/docs_freshness.py           # Full report
    poetry run python scripts/docs_freshness.py --json    # JSON output
    poetry run python scripts/docs_freshness.py --stale   # Only stale docs
"""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class StaleReference:
    """A code file that is newer than the documentation referencing it."""

    code_path: str
    code_mtime: str
    days_newer: int


@dataclass
class DocFreshness:
    """Freshness analysis for a single documentation file."""

    doc_path: str
    doc_mtime: str
    stale_refs: list[StaleReference] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)
    total_refs: int = 0

    @property
    def is_stale(self) -> bool:
        return len(self.stale_refs) > 0


@dataclass
class FreshnessReport:
    """Complete freshness report for all documentation."""

    generated_at: str
    total_docs: int
    stale_docs: int
    fresh_docs: int
    missing_refs_count: int
    results: list[DocFreshness] = field(default_factory=list)


# Regex patterns for code file references in documentation
PATTERNS = [
    # **File:** `/path/to/file.py` or **Location:** `/path/to/file.py`
    # Also handles: `/path/to/file.py:123` (line numbers) and `/path/ (directory)`
    r"\*\*(?:File|Location):\*\*\s*`([^`]+)`",
    # # File: /path/to/file.py (comment style in code blocks)
    r"^#\s*File:\s*(/[^\s]+)",
]


def _stale_refs_count(result: DocFreshness) -> int:
    """Sort key for DocFreshness - by number of stale refs descending."""
    return -len(result.stale_refs)


def strip_line_numbers(path: str) -> str:
    """
    Remove line numbers and line ranges from a path.

    Examples:
        /path/file.py:123 -> /path/file.py
        /path/file.py:123-456 -> /path/file.py
    """
    # Remove :line or :line-line suffix
    return re.sub(r":\d+(?:-\d+)?$", "", path)


def strip_extra_info(path: str) -> str:
    """
    Remove parenthetical descriptions and other trailing info from paths.

    Examples:
        `/path/dir/` (package, ~3000 lines) -> /path/dir/
        `/path/file.py` (`method_name`) -> /path/file.py
    """
    # Already stripped by backtick extraction in most cases
    # Handle cases where content after backticks is included
    path = path.strip()

    # Remove trailing descriptions in parens if present
    path = re.sub(r"\s*\([^)]*\)\s*$", "", path)

    return path


def normalize_path(path: str) -> str:
    """
    Normalize a code reference path for filesystem lookup.

    Handles:
        - Line numbers (:123, :123-456)
        - Trailing descriptions
        - Missing leading slash
    """
    path = strip_line_numbers(path)
    path = strip_extra_info(path)
    path = path.strip()

    # Ensure leading slash for consistency
    if path and not path.startswith("/"):
        path = "/" + path

    return path


def extract_code_refs(doc_path: Path) -> list[str]:
    """
    Extract all code file references from a documentation file.

    Returns a list of normalized paths to code files/directories.
    """
    content = doc_path.read_text(encoding="utf-8")
    refs = set()

    for pattern in PATTERNS:
        for match in re.finditer(pattern, content, re.MULTILINE):
            raw_path = match.group(1)
            normalized = normalize_path(raw_path)
            if normalized:
                refs.add(normalized)

    return sorted(refs)


def get_newest_mtime_in_dir(dir_path: Path) -> datetime | None:
    """
    Get the newest modification time of any file in a directory (recursively).

    Returns None if directory is empty or doesn't contain any files.
    """
    newest_mtime: datetime | None = None

    try:
        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if newest_mtime is None or mtime > newest_mtime:
                    newest_mtime = mtime
    except PermissionError:
        pass

    return newest_mtime


def get_code_mtime(code_path: str, project_root: Path) -> tuple[datetime | None, bool]:
    """
    Get the modification time for a code path.

    For directories, returns the newest mtime of any file within.

    Returns:
        (mtime, exists) tuple
    """
    # Convert to absolute path within project
    if code_path.startswith("/"):
        full_path = project_root / code_path.lstrip("/")
    else:
        full_path = project_root / code_path

    if not full_path.exists():
        return None, False

    if full_path.is_dir():
        mtime = get_newest_mtime_in_dir(full_path)
        return mtime, mtime is not None
    else:
        return datetime.fromtimestamp(full_path.stat().st_mtime), True


def check_freshness(doc_path: Path, project_root: Path) -> DocFreshness:
    """
    Check if a documentation file is fresher than all its code references.

    Returns a DocFreshness object with any stale or missing references.
    """
    doc_mtime = datetime.fromtimestamp(doc_path.stat().st_mtime)
    code_refs = extract_code_refs(doc_path)

    stale_refs: list[StaleReference] = []
    missing_refs: list[str] = []

    for ref in code_refs:
        code_mtime, exists = get_code_mtime(ref, project_root)

        if not exists:
            missing_refs.append(ref)
            continue

        if code_mtime and code_mtime > doc_mtime:
            days_newer = (code_mtime - doc_mtime).days
            stale_refs.append(
                StaleReference(
                    code_path=ref,
                    code_mtime=code_mtime.strftime("%Y-%m-%d"),
                    days_newer=days_newer,
                )
            )

    rel_path = str(doc_path.relative_to(project_root))

    return DocFreshness(
        doc_path=rel_path,
        doc_mtime=doc_mtime.strftime("%Y-%m-%d"),
        stale_refs=stale_refs,
        missing_refs=missing_refs,
        total_refs=len(code_refs),
    )


def scan_docs(docs_dir: Path, project_root: Path) -> list[DocFreshness]:
    """
    Scan all documentation files and check their freshness.

    Includes both /docs/*.md and CLAUDE.md.
    """
    results: list[DocFreshness] = []

    # Scan all .md files in docs directory
    for doc_path in sorted(docs_dir.rglob("*.md")):
        try:
            result = check_freshness(doc_path, project_root)
            # Only include docs that have code references
            if result.total_refs > 0:
                results.append(result)
        except Exception as e:
            print(f"Warning: Failed to analyze {doc_path}: {e}", file=sys.stderr)

    # Also check CLAUDE.md if it exists
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        try:
            result = check_freshness(claude_md, project_root)
            if result.total_refs > 0:
                results.append(result)
        except Exception as e:
            print(f"Warning: Failed to analyze CLAUDE.md: {e}", file=sys.stderr)

    return results


def generate_report(results: list[DocFreshness]) -> FreshnessReport:
    """Generate a summary report from freshness results."""
    stale = [r for r in results if r.is_stale]
    fresh = [r for r in results if not r.is_stale]
    missing_count = sum(len(r.missing_refs) for r in results)

    return FreshnessReport(
        generated_at=datetime.now().isoformat(),
        total_docs=len(results),
        stale_docs=len(stale),
        fresh_docs=len(fresh),
        missing_refs_count=missing_count,
        results=results,
    )


def print_report(report: FreshnessReport) -> None:
    """Print a human-readable freshness report."""
    print("Documentation Freshness Report")
    print("=" * 60)
    print()

    # Get stale docs sorted by number of stale refs (most stale first)
    stale_results = [r for r in report.results if r.is_stale]
    stale_results.sort(key=_stale_refs_count)

    if stale_results:
        print(f"STALE ({len(stale_results)} docs reference newer code):")
        print()

        for result in stale_results:
            print(f"  {result.doc_path} (updated {result.doc_mtime})")
            for ref in result.stale_refs:
                print(f"    - {ref.code_path} ({ref.days_newer} days newer)")
            print()
    else:
        print("No stale documentation found!")
        print()

    print(f"FRESH: {report.fresh_docs} docs are up-to-date")

    if report.missing_refs_count > 0:
        missing_docs = [r for r in report.results if r.missing_refs]
        print(
            f"MISSING: {report.missing_refs_count} refs in {len(missing_docs)} docs "
            f"reference non-existent files (run docs_discovery.py --broken-links)"
        )

    print()
    print("=" * 60)


def print_stale_only(report: FreshnessReport) -> None:
    """Print only stale documentation details."""
    stale_results = [r for r in report.results if r.is_stale]

    if not stale_results:
        print("No stale documentation found!")
        return

    print("Stale Documentation (references newer code files)")
    print("-" * 50)
    print()

    # Sort by most stale refs first
    stale_results.sort(key=_stale_refs_count)

    for result in stale_results:
        print(f"{result.doc_path}")
        print(f"  Last updated: {result.doc_mtime}")
        print("  Stale references:")
        for ref in result.stale_refs:
            print(f"    - {ref.code_path} (modified {ref.code_mtime}, {ref.days_newer} days newer)")
        print()

    print(f"Total: {len(stale_results)} stale documents")


def main() -> None:
    args = sys.argv[1:]

    # Find project root and docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Scan and analyze
    results = scan_docs(docs_dir, project_root)
    report = generate_report(results)

    # Output based on flags
    if "--json" in args:
        output = asdict(report)
        print(json.dumps(output, indent=2, default=str))
    elif "--stale" in args:
        print_stale_only(report)
    else:
        print_report(report)


if __name__ == "__main__":
    main()
