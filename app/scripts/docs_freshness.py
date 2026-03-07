#!/usr/bin/env python3
"""
Documentation Freshness Checker

Detects stale documentation by comparing modification times between docs and the
code files they reference. When a referenced code file is newer than its
documentation, the doc is flagged as potentially stale.

Supports two tracking modes:
1. Code-based: Tracks code file mtimes (default)
2. Conceptual: Tracks manual review schedules via frontmatter

Usage:
    poetry run python scripts/docs_freshness.py                    # Full report
    poetry run python scripts/docs_freshness.py --json             # JSON output
    poetry run python scripts/docs_freshness.py --stale            # Only stale docs
    poetry run python scripts/docs_freshness.py --threshold=7      # Only show 7+ days
    poetry run python scripts/docs_freshness.py --critical-only    # Only 30+ days
    poetry run python scripts/docs_freshness.py --warnings         # Only 7-29 days
"""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from core.utils.frontmatter import parse_frontmatter as _parse_frontmatter


class TrackingType(str, Enum):
    """Type of freshness tracking for a document."""

    CODE_BASED = "code"  # Default: tracks code file mtimes
    CONCEPTUAL = "conceptual"  # Manual review-based tracking
    HYBRID = "hybrid"  # Both code AND periodic review


class StalenessConfig:
    """Configurable staleness thresholds."""

    def __init__(
        self,
        grace_period: int = 1,
        warning_threshold: int = 7,
        critical_threshold: int = 30,
    ):
        self.grace_period = grace_period
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold


@dataclass
class CodeReference:
    """Parsed code reference with metadata."""

    path: str
    ref_type: Literal["file", "directory", "package"]
    filter_pattern: str | None = None  # e.g., "*.py" for selective tracking


@dataclass
class StaleReference:
    """A code file that is newer than the documentation referencing it."""

    code_path: str
    code_mtime: str
    days_newer: int
    severity: Literal["grace", "warning", "critical"] = "warning"


@dataclass
class DocFreshness:
    """Freshness analysis for a single documentation file."""

    doc_path: str
    doc_mtime: str
    tracking_type: TrackingType = TrackingType.CODE_BASED

    # Code-based tracking
    stale_refs: list[StaleReference] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)
    total_refs: int = 0

    # Conceptual tracking
    last_reviewed: str | None = None
    review_frequency: str | None = None
    review_overdue: bool = False
    days_since_review: int = 0

    @property
    def is_stale(self) -> bool:
        if self.tracking_type == TrackingType.CODE_BASED:
            return len(self.stale_refs) > 0
        elif self.tracking_type == TrackingType.CONCEPTUAL:
            return self.review_overdue
        else:  # HYBRID
            return len(self.stale_refs) > 0 or self.review_overdue


@dataclass
class FreshnessReport:
    """Complete freshness report for all documentation."""

    generated_at: str
    total_docs: int
    stale_docs: int
    fresh_docs: int
    missing_refs_count: int
    code_based_docs: int
    conceptual_docs: int
    hybrid_docs: int
    results: list[DocFreshness] = field(default_factory=list)


# Regex patterns for code file references in documentation
PATTERNS = [
    # **File:** `/path/to/file.py`
    r"\*\*File:\*\*\s*`([^`]+)`",
    # **Directory:** `/core/ports/` (*.py only)
    r"\*\*Directory:\*\*\s*`([^`]+)`(?:\s*\(([^)]+)\))?",
    # **Package:** `/core/ports/`
    r"\*\*Package:\*\*\s*`([^`]+)`",
    # **Location:** `/path/to/file.py` (legacy)
    r"\*\*Location:\*\*\s*`([^`]+)`",
    # # File: /path/to/file.py (comment style in code blocks)
    r"^#\s*File:\s*(/[^\s]+)",
]


def _stale_refs_count(result: DocFreshness) -> int:
    """Sort key for DocFreshness - by number of stale refs descending."""
    return -len(result.stale_refs)


def calculate_severity(days_newer: int, config: StalenessConfig) -> str:
    """Determine staleness severity."""
    if days_newer <= config.grace_period:
        return "grace"
    elif days_newer >= config.critical_threshold:
        return "critical"
    else:
        return "warning"


def strip_line_numbers(path: str) -> str:
    """
    Remove line numbers and line ranges from a path.

    Examples:
        /path/file.py:123 -> /path/file.py
        /path/file.py:123-456 -> /path/file.py
    """
    return re.sub(r":\d+(?:-\d+)?$", "", path)


def strip_extra_info(path: str) -> str:
    """
    Remove parenthetical descriptions and other trailing info from paths.

    Examples:
        `/path/dir/` (package, ~3000 lines) -> /path/dir/
        `/path/file.py` (`method_name`) -> /path/file.py
    """
    path = path.strip()
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

    if path and not path.startswith("/"):
        path = "/" + path

    return path


def parse_code_references(doc_content: str) -> list[CodeReference]:
    """
    Extract all code file references from documentation content.

    Returns a list of CodeReference objects with type and filter metadata.
    """
    refs: dict[str, CodeReference] = {}

    for pattern in PATTERNS:
        for match in re.finditer(pattern, doc_content, re.MULTILINE):
            raw_path = match.group(1)
            normalized = normalize_path(raw_path)

            if not normalized:
                continue

            # Extract filter pattern if present (group 2)
            filter_pattern = None
            if len(match.groups()) > 1 and match.group(2):
                filter_pattern = match.group(2).strip()

            # Determine reference type
            if "Directory:" in pattern or "Package:" in pattern:
                ref_type = "directory"
            else:
                ref_type = "file"

            # Avoid duplicates, prefer most specific reference
            if normalized not in refs:
                refs[normalized] = CodeReference(
                    path=normalized, ref_type=ref_type, filter_pattern=filter_pattern
                )

    return list(refs.values())


def get_directory_mtime(
    dir_path: Path, filter_pattern: str | None, config: StalenessConfig
) -> datetime | None:
    """Get newest mtime in directory with optional filtering."""
    newest_mtime: datetime | None = None

    try:
        for file_path in dir_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Apply pattern filter if provided
            if filter_pattern is not None:
                if filter_pattern.startswith("*."):
                    # Extension filter (e.g., *.py)
                    if file_path.suffix != filter_pattern[1:]:
                        continue
                elif filter_pattern == "__init__.py":
                    # Specific filename
                    if file_path.name != "__init__.py":
                        continue
                else:
                    # Substring match
                    if filter_pattern not in file_path.name:
                        continue

            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if newest_mtime is None or mtime > newest_mtime:
                newest_mtime = mtime

    except PermissionError:
        pass

    return newest_mtime


def get_code_mtime(
    ref: CodeReference, project_root: Path, config: StalenessConfig
) -> tuple[datetime | None, bool]:
    """
    Get the modification time for a code reference.

    For directories, returns the newest mtime of any file within (with optional filtering).

    Returns:
        (mtime, exists) tuple
    """
    full_path = project_root / ref.path.lstrip("/")

    if not full_path.exists():
        return None, False

    if full_path.is_dir():
        mtime = get_directory_mtime(full_path, ref.filter_pattern, config)
        return mtime, mtime is not None
    else:
        return datetime.fromtimestamp(full_path.stat().st_mtime), True


def parse_frontmatter(doc_path: Path) -> dict:
    """
    Parse YAML frontmatter from a markdown file.

    Returns empty dict if no frontmatter found.
    """
    content = doc_path.read_text(encoding="utf-8")
    return _parse_frontmatter(content)[0]


def check_conceptual_freshness(
    doc_path: Path, frontmatter: dict, config: StalenessConfig
) -> DocFreshness:
    """Check freshness for conceptual docs based on review schedule."""
    doc_mtime = datetime.fromtimestamp(doc_path.stat().st_mtime)
    last_reviewed = frontmatter.get("last_reviewed")
    review_frequency = frontmatter.get("review_frequency", "quarterly")

    if not last_reviewed:
        # Never reviewed - mark as overdue
        return DocFreshness(
            doc_path=str(doc_path),
            doc_mtime=doc_mtime.strftime("%Y-%m-%d"),
            tracking_type=TrackingType.CONCEPTUAL,
            review_overdue=True,
            days_since_review=999,
            review_frequency=review_frequency,
        )

    # Parse review date (handle both string and datetime.date from YAML)
    try:
        if isinstance(last_reviewed, str):
            last_review_date = datetime.fromisoformat(last_reviewed)
        else:
            # Already a date object from YAML parsing
            last_review_date = datetime.combine(last_reviewed, datetime.min.time())
    except (ValueError, TypeError, AttributeError):
        # Invalid date format
        return DocFreshness(
            doc_path=str(doc_path),
            doc_mtime=doc_mtime.strftime("%Y-%m-%d"),
            tracking_type=TrackingType.CONCEPTUAL,
            review_overdue=True,
            days_since_review=999,
            review_frequency=review_frequency,
        )

    days_since = (datetime.now() - last_review_date).days

    # Convert back to string for storage if it was a date object
    if not isinstance(last_reviewed, str):
        last_reviewed = last_reviewed.isoformat()

    # Thresholds by frequency
    thresholds = {
        "monthly": 35,  # ~1 month + grace
        "quarterly": 100,  # ~3 months + grace
        "annual": 380,  # ~1 year + grace
    }

    threshold = thresholds.get(review_frequency, 100)
    review_overdue = days_since > threshold

    return DocFreshness(
        doc_path=str(doc_path),
        doc_mtime=doc_mtime.strftime("%Y-%m-%d"),
        tracking_type=TrackingType.CONCEPTUAL,
        last_reviewed=last_reviewed,
        review_frequency=review_frequency,
        review_overdue=review_overdue,
        days_since_review=days_since,
    )


def check_code_based_freshness(
    doc_path: Path, project_root: Path, config: StalenessConfig
) -> DocFreshness:
    """
    Check if a documentation file is fresher than all its code references.

    Returns a DocFreshness object with any stale or missing references.
    """
    doc_mtime = datetime.fromtimestamp(doc_path.stat().st_mtime)
    content = doc_path.read_text(encoding="utf-8")
    code_refs = parse_code_references(content)

    stale_refs: list[StaleReference] = []
    missing_refs: list[str] = []

    for ref in code_refs:
        code_mtime, exists = get_code_mtime(ref, project_root, config)

        if not exists:
            missing_refs.append(ref.path)
            continue

        if code_mtime and code_mtime > doc_mtime:
            days_newer = (code_mtime - doc_mtime).days
            severity = calculate_severity(days_newer, config)

            # Only include if above grace period
            if severity != "grace":
                stale_refs.append(
                    StaleReference(
                        code_path=ref.path,
                        code_mtime=code_mtime.strftime("%Y-%m-%d"),
                        days_newer=days_newer,
                        severity=severity,
                    )
                )

    rel_path = str(doc_path.relative_to(project_root))

    return DocFreshness(
        doc_path=rel_path,
        doc_mtime=doc_mtime.strftime("%Y-%m-%d"),
        tracking_type=TrackingType.CODE_BASED,
        stale_refs=stale_refs,
        missing_refs=missing_refs,
        total_refs=len(code_refs),
    )


def check_freshness(
    doc_path: Path, project_root: Path, config: StalenessConfig
) -> DocFreshness | None:
    """
    Check freshness of a document based on its tracking type.

    Returns None if the document should be skipped (no tracking info).
    """
    frontmatter = parse_frontmatter(doc_path)
    tracking = frontmatter.get("tracking", "code")

    # Normalize tracking type
    if tracking in ("code", "code-based", TrackingType.CODE_BASED):
        tracking_type = TrackingType.CODE_BASED
    elif tracking in ("conceptual", TrackingType.CONCEPTUAL):
        tracking_type = TrackingType.CONCEPTUAL
    elif tracking in ("hybrid", TrackingType.HYBRID):
        tracking_type = TrackingType.HYBRID
    else:
        # Default to code-based
        tracking_type = TrackingType.CODE_BASED

    # For code-based or hybrid, check code references
    if tracking_type in (TrackingType.CODE_BASED, TrackingType.HYBRID):
        result = check_code_based_freshness(doc_path, project_root, config)

        # If hybrid, also check review schedule
        if tracking_type == TrackingType.HYBRID:
            conceptual = check_conceptual_freshness(doc_path, frontmatter, config)
            result.tracking_type = TrackingType.HYBRID
            result.last_reviewed = conceptual.last_reviewed
            result.review_frequency = conceptual.review_frequency
            result.review_overdue = conceptual.review_overdue
            result.days_since_review = conceptual.days_since_review

        # Skip if no refs and not hybrid
        if result.total_refs == 0 and tracking_type == TrackingType.CODE_BASED:
            return None

        return result

    # For conceptual-only, check review schedule
    elif tracking_type == TrackingType.CONCEPTUAL:
        return check_conceptual_freshness(doc_path, frontmatter, config)

    return None


def scan_docs(docs_dir: Path, project_root: Path, config: StalenessConfig) -> list[DocFreshness]:
    """
    Scan all documentation files and check their freshness.

    Includes both /docs/*.md and CLAUDE.md.
    """
    results: list[DocFreshness] = []

    # Scan all .md files in docs directory
    for doc_path in sorted(docs_dir.rglob("*.md")):
        try:
            result = check_freshness(doc_path, project_root, config)
            if result is not None:
                results.append(result)
        except Exception as e:
            print(f"Warning: Failed to analyze {doc_path}: {e}", file=sys.stderr)

    # Also check CLAUDE.md if it exists
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        try:
            result = check_freshness(claude_md, project_root, config)
            if result is not None:
                results.append(result)
        except Exception as e:
            print(f"Warning: Failed to analyze CLAUDE.md: {e}", file=sys.stderr)

    return results


def generate_report(results: list[DocFreshness]) -> FreshnessReport:
    """Generate a summary report from freshness results."""
    stale = [r for r in results if r.is_stale]
    fresh = [r for r in results if not r.is_stale]
    missing_count = sum(len(r.missing_refs) for r in results)

    # Count by tracking type
    code_based = sum(1 for r in results if r.tracking_type == TrackingType.CODE_BASED)
    conceptual = sum(1 for r in results if r.tracking_type == TrackingType.CONCEPTUAL)
    hybrid = sum(1 for r in results if r.tracking_type == TrackingType.HYBRID)

    return FreshnessReport(
        generated_at=datetime.now().isoformat(),
        total_docs=len(results),
        stale_docs=len(stale),
        fresh_docs=len(fresh),
        missing_refs_count=missing_count,
        code_based_docs=code_based,
        conceptual_docs=conceptual,
        hybrid_docs=hybrid,
        results=results,
    )


def print_report(report: FreshnessReport, config: StalenessConfig) -> None:
    """Print a human-readable freshness report."""
    print("Documentation Freshness Report")
    print("=" * 60)
    print()

    # Get stale docs sorted by number of stale refs (most stale first)
    stale_results = [r for r in report.results if r.is_stale]
    stale_results.sort(key=_stale_refs_count)

    if stale_results:
        print(f"STALE ({len(stale_results)} docs):")
        print()

        for result in stale_results:
            print(f"  {result.doc_path} (updated {result.doc_mtime})")

            # Show code staleness
            if result.stale_refs:
                for ref in result.stale_refs:
                    severity_marker = "🔴" if ref.severity == "critical" else "🟡"
                    print(f"    {severity_marker} {ref.code_path} ({ref.days_newer} days newer)")

            # Show review staleness
            if result.review_overdue:
                print(
                    f"    📅 Review overdue ({result.days_since_review} days since {result.review_frequency} review)"
                )

            print()
    else:
        print("No stale documentation found!")
        print()

    print(f"FRESH: {report.fresh_docs} docs are up-to-date")
    print()
    print(
        f"TRACKING: {report.code_based_docs} code-based, {report.conceptual_docs} conceptual, {report.hybrid_docs} hybrid"
    )

    if report.missing_refs_count > 0:
        missing_docs = [r for r in report.results if r.missing_refs]
        print()
        print(
            f"MISSING: {report.missing_refs_count} refs in {len(missing_docs)} docs "
            f"reference non-existent files"
        )

    print()
    print("=" * 60)


def print_filtered_report(
    report: FreshnessReport, filter_type: str, config: StalenessConfig
) -> None:
    """Print filtered report (critical-only, warnings, or threshold)."""
    stale_results = [r for r in report.results if r.is_stale]

    if filter_type == "critical":
        filtered = [
            r for r in stale_results if any(ref.severity == "critical" for ref in r.stale_refs)
        ]
        title = "CRITICAL Stale Documentation (30+ days)"
    elif filter_type == "warnings":
        filtered = [
            r
            for r in stale_results
            if any(ref.severity == "warning" and ref.severity != "critical" for ref in r.stale_refs)
        ]
        title = "WARNING Stale Documentation (7-29 days)"
    else:
        filtered = stale_results
        title = "Stale Documentation"

    if not filtered:
        print(f"No {filter_type} stale documentation found!")
        return

    print(title)
    print("-" * 50)
    print()

    # Sort by most stale refs first
    filtered.sort(key=_stale_refs_count)

    for result in filtered:
        print(f"{result.doc_path}")
        print(f"  Last updated: {result.doc_mtime}")

        if result.stale_refs:
            print("  Stale references:")
            for ref in result.stale_refs:
                severity_marker = "🔴" if ref.severity == "critical" else "🟡"
                print(
                    f"    {severity_marker} {ref.code_path} (modified {ref.code_mtime}, {ref.days_newer} days newer)"
                )

        if result.review_overdue:
            print(
                f"  📅 Review overdue ({result.days_since_review} days since {result.review_frequency} review)"
            )

        print()

    print(f"Total: {len(filtered)} stale documents")


def main() -> None:
    args = sys.argv[1:]

    # Parse args
    threshold = None
    critical_only = "--critical-only" in args
    warnings_only = "--warnings" in args
    json_output = "--json" in args
    stale_only = "--stale" in args

    # Parse threshold arg
    for arg in args:
        if arg.startswith("--threshold="):
            try:
                threshold = int(arg.split("=")[1])
            except (ValueError, IndexError):
                print(f"Error: Invalid threshold value: {arg}", file=sys.stderr)
                sys.exit(1)

    # Load configuration (or use defaults)
    config = StalenessConfig()

    # Apply threshold if provided
    if threshold is not None:
        config.warning_threshold = threshold

    # Find project root and docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Scan and analyze
    results = scan_docs(docs_dir, project_root, config)
    report = generate_report(results)

    # Output based on flags
    if json_output:
        output = asdict(report)
        print(json.dumps(output, indent=2, default=str))
    elif critical_only:
        print_filtered_report(report, "critical", config)
    elif warnings_only:
        print_filtered_report(report, "warnings", config)
    elif stale_only:
        print_filtered_report(report, "stale", config)
    else:
        print_report(report, config)


if __name__ == "__main__":
    main()
